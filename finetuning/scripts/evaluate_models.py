from __future__ import annotations

import argparse
from collections import Counter
import gc
import json
import os
from pathlib import Path
import re
from typing import Any

from peft import PeftModel
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SYSTEM_PROMPT = (
    "Si slovenski administrativni pomočnik. Odgovarjaj zvesto podanemu besedilu, "
    "v formalnem in jasnem slogu. Če je zahtevan JSON, vrni veljaven JSON brez dodatnega komentarja."
)


TURN_END_TOKENS = ("<end_of_turn>", "<|eot_id|>")
TURN_START_TOKENS = ("<start_of_turn>", "<|start_header_id|>")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare baseline, QLoRA, and LoRA models on held-out datasets.")
    parser.add_argument("--config", required=True, help="Path to the YAML or JSON comparison config.")
    parser.add_argument("--max-samples-per-dataset", type=int, default=None, help="Optional cap for quick smoke tests.")
    return parser.parse_args()


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def expand_env_vars(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: expand_env_vars(item) for key, item in value.items()}
    if isinstance(value, list):
        return [expand_env_vars(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"\$\{([^}]+)\}", lambda match: os.getenv(match.group(1), match.group(0)), value)
    return value


def load_config(path: Path) -> dict[str, Any]:
    raw_text = path.read_text(encoding="utf-8")
    raw = yaml.safe_load(raw_text) if path.suffix.lower() in {".yaml", ".yml"} else json.loads(raw_text)
    return expand_env_vars(raw)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def compute_dtype(name: str | None) -> torch.dtype:
    if not name:
        return torch.bfloat16
    mapping = {
        "float16": torch.float16,
        "fp16": torch.float16,
        "bfloat16": torch.bfloat16,
        "bf16": torch.bfloat16,
        "float32": torch.float32,
        "fp32": torch.float32,
    }
    return mapping.get(name.lower(), torch.bfloat16)


def render_messages(messages: list[dict[str, str]]) -> str:
    return "\n\n".join(f"{message['role'].upper()}: {message['content'].strip()}" for message in messages).strip()


def build_prompt(tokenizer: Any, messages: list[dict[str, str]]) -> str:
    if getattr(tokenizer, "chat_template", None):
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    return f"{render_messages(messages)}\n\nASSISTANT:"


def first_model_device(model: Any) -> torch.device:
    if getattr(model, "hf_device_map", None):
        for value in model.hf_device_map.values():
            if isinstance(value, str) and value not in {"cpu", "disk"}:
                return torch.device(value)
            if isinstance(value, int):
                return torch.device(f"cuda:{value}")
    if torch.cuda.is_available():
        return torch.device("cuda:0")
    return torch.device("cpu")


def load_model_bundle(model_cfg: dict[str, Any]) -> tuple[Any, Any]:
    model_name_or_path = model_cfg["model_name_or_path"]
    tokenizer_source = model_cfg.get("tokenizer_path") or model_cfg.get("adapter_path") or model_name_or_path
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_source, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "left"

    quantization_config = None
    if model_cfg.get("load_in_4bit", False):
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=model_cfg.get("bnb_4bit_use_double_quant", True),
            bnb_4bit_quant_type=model_cfg.get("bnb_4bit_quant_type", "nf4"),
            bnb_4bit_compute_dtype=compute_dtype(model_cfg.get("bnb_4bit_compute_dtype", "float16")),
        )

    model_kwargs: dict[str, Any] = {
        "trust_remote_code": True,
        "quantization_config": quantization_config,
        "dtype": compute_dtype(model_cfg.get("torch_dtype", "bfloat16")),
        "low_cpu_mem_usage": model_cfg.get("low_cpu_mem_usage", True),
    }
    device_map = model_cfg.get("device_map", "auto")
    if device_map is not None:
        model_kwargs["device_map"] = device_map

    model = AutoModelForCausalLM.from_pretrained(model_name_or_path, **model_kwargs)
    adapter_path = model_cfg.get("adapter_path")
    if adapter_path:
        model = PeftModel.from_pretrained(model, adapter_path)
    model.eval()
    if hasattr(model.config, "use_cache"):
        model.config.use_cache = True
    return model, tokenizer


def get_stop_token_ids(tokenizer: Any) -> int | list[int] | None:
    stop_ids: list[int] = []
    if tokenizer.eos_token_id is not None:
        stop_ids.append(int(tokenizer.eos_token_id))

    for token in TURN_END_TOKENS:
        try:
            token_id = tokenizer.convert_tokens_to_ids(token)
        except Exception:
            token_id = None
        if isinstance(token_id, int) and token_id >= 0 and token_id not in stop_ids:
            stop_ids.append(token_id)

    if not stop_ids:
        return None
    if len(stop_ids) == 1:
        return stop_ids[0]
    return stop_ids


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def tokenize_words(value: str) -> list[str]:
    return re.findall(r"\w+", normalize_text(value).lower(), flags=re.UNICODE)


def lcs_length(left: list[str], right: list[str]) -> int:
    if not left or not right:
        return 0
    previous = [0] * (len(right) + 1)
    for token_left in left:
        current = [0]
        for index, token_right in enumerate(right, start=1):
            if token_left == token_right:
                current.append(previous[index - 1] + 1)
            else:
                current.append(max(current[-1], previous[index]))
        previous = current
    return previous[-1]


def token_f1(prediction: str, reference: str) -> float:
    pred_counts = Counter(tokenize_words(prediction))
    ref_counts = Counter(tokenize_words(reference))
    overlap = sum(min(pred_counts[token], ref_counts[token]) for token in pred_counts)
    if overlap == 0:
        return 0.0
    pred_total = sum(pred_counts.values())
    ref_total = sum(ref_counts.values())
    precision = overlap / pred_total if pred_total else 0.0
    recall = overlap / ref_total if ref_total else 0.0
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def rouge_l_f1(prediction: str, reference: str) -> float:
    pred_tokens = tokenize_words(prediction)
    ref_tokens = tokenize_words(reference)
    if not pred_tokens or not ref_tokens:
        return 0.0
    lcs = lcs_length(pred_tokens, ref_tokens)
    precision = lcs / len(pred_tokens)
    recall = lcs / len(ref_tokens)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def parse_json_text(value: str) -> Any | None:
    try:
        return json.loads(value)
    except Exception:
        return None


def extract_first_json_object(value: str) -> str | None:
    start = value.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(value)):
        char = value[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = value[start : index + 1].strip()
                if parse_json_text(candidate) is not None:
                    return candidate
                return None
    return None


def postprocess_prediction(task: str, raw_text: str) -> str:
    text = raw_text or ""

    for token in TURN_END_TOKENS + TURN_START_TOKENS:
        if token in text:
            text = text.split(token, 1)[0]

    text = text.strip()
    text = re.sub(r"^\s*model\s*\n+", "", text, flags=re.IGNORECASE)

    if task in {"classification", "information_extraction"}:
        json_candidate = extract_first_json_object(text)
        if json_candidate is not None:
            parsed = parse_json_text(json_candidate)
            if parsed is not None:
                return json.dumps(parsed, ensure_ascii=False, indent=2)
        return text.strip()

    cleaned_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower() == "model":
            break
        if stripped.startswith("```"):
            break
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def flatten_json(value: Any, prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    if isinstance(value, dict):
        for key, nested in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            flat.update(flatten_json(nested, child_prefix))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            child_prefix = f"{prefix}[{index}]"
            flat.update(flatten_json(nested, child_prefix))
    else:
        flat[prefix or "$"] = normalize_text("" if value is None else str(value))
    return flat


def build_messages_from_record(record: dict[str, Any]) -> list[dict[str, str]]:
    if "messages" in record:
        return record["messages"][:-1]
    return [
        {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
        {"role": "user", "content": f"{record['instruction']}\n\n{record['input_context']}"},
    ]


def extract_reference(record: dict[str, Any]) -> str:
    if "messages" in record:
        return record["messages"][-1]["content"]
    return record.get("gold_output", "")


def generate_text(
    model: Any,
    tokenizer: Any,
    messages: list[dict[str, str]],
    generation_cfg: dict[str, Any],
    task: str,
) -> tuple[str, str]:
    prompt = build_prompt(tokenizer, messages)
    encoded = tokenizer(prompt, return_tensors="pt")
    target_device = first_model_device(model)
    encoded = {key: value.to(target_device) for key, value in encoded.items()}

    generation_kwargs = {
        "max_new_tokens": generation_cfg.get("max_new_tokens", 256),
        "do_sample": generation_cfg.get("do_sample", False),
        "pad_token_id": tokenizer.pad_token_id,
        "eos_token_id": get_stop_token_ids(tokenizer),
    }
    if generation_kwargs["do_sample"]:
        generation_kwargs["temperature"] = generation_cfg.get("temperature", 0.7)
        generation_kwargs["top_p"] = generation_cfg.get("top_p", 0.95)
        if "top_k" in generation_cfg:
            generation_kwargs["top_k"] = generation_cfg["top_k"]

    with torch.inference_mode():
        generated = model.generate(**encoded, **generation_kwargs)
    completion_ids = generated[0][encoded["input_ids"].shape[1] :]
    raw_completion = tokenizer.decode(completion_ids, skip_special_tokens=False)
    cleaned_prediction = postprocess_prediction(task, raw_completion).strip()
    return raw_completion, cleaned_prediction


def evaluate_prediction(task: str, prediction: str, reference: str) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "exact_match": float(normalize_text(prediction) == normalize_text(reference)),
        "token_f1": token_f1(prediction, reference),
        "rouge_l_f1": rouge_l_f1(prediction, reference),
    }

    if task in {"classification", "information_extraction"}:
        pred_json = parse_json_text(prediction)
        ref_json = parse_json_text(reference)
        metrics["json_valid"] = float(pred_json is not None)
        metrics["json_exact_match"] = float(pred_json == ref_json) if pred_json is not None and ref_json is not None else 0.0
        if pred_json is not None and ref_json is not None:
            pred_flat = flatten_json(pred_json)
            ref_flat = flatten_json(ref_json)
            pred_pairs = {f"{key}={value}" for key, value in pred_flat.items()}
            ref_pairs = {f"{key}={value}" for key, value in ref_flat.items()}
            tp = len(pred_pairs & ref_pairs)
            fp = len(pred_pairs - ref_pairs)
            fn = len(ref_pairs - pred_pairs)
            metrics["json_tp"] = tp
            metrics["json_fp"] = fp
            metrics["json_fn"] = fn
        else:
            metrics["json_tp"] = 0
            metrics["json_fp"] = 0
            metrics["json_fn"] = len(flatten_json(ref_json)) if ref_json is not None else 0
    return metrics


def aggregate_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {}

    numeric_keys = {
        key
        for record in records
        for key, value in record["metrics"].items()
        if isinstance(value, (int, float)) and key not in {"json_tp", "json_fp", "json_fn"}
    }
    summary = {"count": len(records)}
    for key in sorted(numeric_keys):
        summary[key] = round(sum(float(record["metrics"].get(key, 0.0)) for record in records) / len(records), 4)

    json_tp = sum(int(record["metrics"].get("json_tp", 0)) for record in records)
    json_fp = sum(int(record["metrics"].get("json_fp", 0)) for record in records)
    json_fn = sum(int(record["metrics"].get("json_fn", 0)) for record in records)
    if json_tp or json_fp or json_fn:
        precision = json_tp / (json_tp + json_fp) if json_tp + json_fp else 0.0
        recall = json_tp / (json_tp + json_fn) if json_tp + json_fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        summary["json_field_precision"] = round(precision, 4)
        summary["json_field_recall"] = round(recall, 4)
        summary["json_field_f1"] = round(f1, 4)
    return summary


def build_markdown_report(summary: dict[str, Any]) -> str:
    lines = ["# Model Comparison Summary", ""]
    for dataset_name, dataset_summary in summary.items():
        lines.append(f"## {dataset_name}")
        lines.append("")
        for model_name, model_summary in dataset_summary.items():
            lines.append(f"### {model_name}")
            lines.append("")
            lines.append("| Task | Count | Exact | Token F1 | Rouge-L F1 | JSON Valid | JSON Exact | JSON Field F1 |")
            lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
            for task_name, task_summary in sorted(model_summary.items()):
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            task_name,
                            str(task_summary.get("count", 0)),
                            f"{task_summary.get('exact_match', 0.0):.4f}",
                            f"{task_summary.get('token_f1', 0.0):.4f}",
                            f"{task_summary.get('rouge_l_f1', 0.0):.4f}",
                            f"{task_summary.get('json_valid', 0.0):.4f}",
                            f"{task_summary.get('json_exact_match', 0.0):.4f}",
                            f"{task_summary.get('json_field_f1', 0.0):.4f}",
                        ]
                    )
                    + " |"
                )
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    args = parse_args()
    config_path = resolve_path(args.config)
    config = load_config(config_path)

    output_dir = resolve_path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    datasets_cfg = config.get("datasets", [])
    models_cfg = config.get("models", [])
    generation_cfg = config.get("generation", {})
    overall_summary: dict[str, Any] = {}

    for dataset_cfg in datasets_cfg:
        dataset_name = dataset_cfg["name"]
        dataset_path = resolve_path(dataset_cfg["path"])
        rows = load_jsonl(dataset_path)
        if args.max_samples_per_dataset:
            rows = rows[: args.max_samples_per_dataset]

        print(f"[compare] dataset={dataset_name} rows={len(rows)}")

        prepared_rows: list[dict[str, Any]] = []
        for row in rows:
            prepared_rows.append(
                {
                    "id": row.get("eval_id") or row.get("example_id"),
                    "task": row.get("task", "unknown"),
                    "messages": build_messages_from_record(row),
                    "reference": extract_reference(row),
                    "source": row,
                }
            )

        dataset_output_dir = output_dir / dataset_name
        dataset_output_dir.mkdir(parents=True, exist_ok=True)
        overall_summary[dataset_name] = {}

        for model_cfg in models_cfg:
            model_name = model_cfg["name"]
            print(f"[compare] loading model={model_name}")
            model, tokenizer = load_model_bundle(model_cfg)
            model_records: list[dict[str, Any]] = []
            predictions_path = dataset_output_dir / f"{model_name}_predictions.jsonl"

            with predictions_path.open("w", encoding="utf-8") as handle:
                for index, prepared in enumerate(prepared_rows, start=1):
                    raw_prediction, prediction = generate_text(
                        model,
                        tokenizer,
                        prepared["messages"],
                        generation_cfg,
                        prepared["task"],
                    )
                    metrics = evaluate_prediction(prepared["task"], prediction, prepared["reference"])
                    record = {
                        "id": prepared["id"],
                        "task": prepared["task"],
                        "raw_prediction": raw_prediction,
                        "prediction": prediction,
                        "reference": prepared["reference"],
                        "metrics": metrics,
                    }
                    model_records.append(record)
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                    if index % 25 == 0 or index == len(prepared_rows):
                        print(f"[compare] dataset={dataset_name} model={model_name} completed={index}/{len(prepared_rows)}")

            per_task_summary: dict[str, Any] = {}
            tasks = sorted({record["task"] for record in model_records})
            for task in tasks:
                per_task_summary[task] = aggregate_metrics([record for record in model_records if record["task"] == task])
            overall_summary[dataset_name][model_name] = per_task_summary

            del model
            del tokenizer
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    (output_dir / "comparison_summary.json").write_text(
        json.dumps(overall_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "comparison_summary.md").write_text(
        build_markdown_report(overall_summary),
        encoding="utf-8",
    )

    manifest = {
        "config_path": str(config_path),
        "output_dir": str(output_dir),
        "datasets": [dataset["name"] for dataset in datasets_cfg],
        "models": [model["name"] for model in models_cfg],
        "summary_file": str(output_dir / "comparison_summary.json"),
        "markdown_report": str(output_dir / "comparison_summary.md"),
    }
    (output_dir / "comparison_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
