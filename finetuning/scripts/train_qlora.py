from __future__ import annotations

import argparse
from collections import Counter
import json
import os
import random
import re
from pathlib import Path
from typing import Any

import torch
from datasets import Dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    DataCollatorForLanguageModeling,
    Trainer,
    TrainingArguments,
    set_seed,
)
import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_config(path: Path) -> dict[str, Any]:
    raw_text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        raw = yaml.safe_load(raw_text)
    else:
        raw = json.loads(raw_text)
    raw = expand_env_vars(raw)
    return normalize_config(raw)


def expand_env_vars(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: expand_env_vars(item) for key, item in value.items()}
    if isinstance(value, list):
        return [expand_env_vars(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"\$\{([^}]+)\}", lambda match: os.getenv(match.group(1), match.group(0)), value)
    return value


def normalize_config(raw: dict[str, Any]) -> dict[str, Any]:
    if "paths" not in raw:
        return raw

    paths = raw.get("paths", {})
    model_cfg = raw.get("model", {})
    lora_cfg = raw.get("lora", {})
    training_cfg = raw.get("training", {})
    runtime_cfg = raw.get("runtime", {})
    ablation_cfg = raw.get("ablation", {})

    report_to = runtime_cfg.get("report_to", [])
    if isinstance(report_to, str):
        report_to = [report_to]

    return {
        "model_name_or_path": paths.get("model_path") or model_cfg.get("base_model_path"),
        "train_file": paths.get("train_jsonl"),
        "validation_file": paths.get("val_jsonl"),
        "output_dir": paths.get("output_dir"),
        "load_in_4bit": model_cfg.get("load_in_4bit", True),
        "bnb_4bit_use_double_quant": model_cfg.get("bnb_4bit_use_double_quant", True),
        "bnb_4bit_quant_type": model_cfg.get("bnb_4bit_quant_type", "nf4"),
        "bnb_4bit_compute_dtype": model_cfg.get("bnb_4bit_compute_dtype", "bfloat16"),
        "torch_dtype": model_cfg.get("torch_dtype", model_cfg.get("bnb_4bit_compute_dtype", "bfloat16")),
        "device_map": model_cfg.get("device_map", "auto"),
        "lora_r": lora_cfg.get("r", 16),
        "lora_alpha": lora_cfg.get("alpha", 32),
        "lora_dropout": lora_cfg.get("dropout", 0.05),
        "target_modules": lora_cfg.get("target_modules"),
        "max_seq_length": training_cfg.get("max_seq_length", 2048),
        "per_device_train_batch_size": training_cfg.get("per_device_train_batch_size", 1),
        "per_device_eval_batch_size": training_cfg.get("per_device_eval_batch_size", 1),
        "gradient_accumulation_steps": training_cfg.get("gradient_accumulation_steps", 16),
        "learning_rate": training_cfg.get("learning_rate", 1e-4),
        "num_train_epochs": training_cfg.get("num_train_epochs", 1.0),
        "warmup_ratio": training_cfg.get("warmup_ratio", 0.05),
        "weight_decay": training_cfg.get("weight_decay", 0.0),
        "bf16": training_cfg.get("bf16", True),
        "fp16": training_cfg.get("fp16", False),
        "gradient_checkpointing": training_cfg.get("gradient_checkpointing", True),
        "logging_steps": training_cfg.get("logging_steps", 10),
        "eval_steps": training_cfg.get("eval_steps", 100),
        "save_steps": training_cfg.get("save_steps", 100),
        "save_total_limit": training_cfg.get("save_total_limit", 3),
        "lr_scheduler_type": training_cfg.get("lr_scheduler_type", "cosine"),
        "seed": training_cfg.get("seed", 42),
        "report_to": report_to,
        "resume_from_checkpoint": runtime_cfg.get("resume_from_checkpoint"),
        "train_subset_ratio": ablation_cfg.get("train_fraction") if ablation_cfg.get("enabled") else None,
    }


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def has_unresolved_placeholder(value: Any) -> bool:
    return isinstance(value, str) and bool(re.search(r"\$\{[^}]+\}", value))


def validate_required_config(config: dict[str, Any], allow_unresolved_runtime_paths: bool = False) -> list[str]:
    issues: list[str] = []
    required_fields = ("model_name_or_path", "train_file", "validation_file", "output_dir")
    for field in required_fields:
        value = config.get(field)
        if not value:
            issues.append(f"Missing required config field: {field}")
            continue
        if has_unresolved_placeholder(value) and not (allow_unresolved_runtime_paths and field in {"model_name_or_path", "output_dir"}):
            issues.append(f"Unresolved environment placeholder in config field: {field}={value}")
    return issues


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def maybe_subset(rows: list[dict[str, Any]], ratio: float | None, max_examples: int | None, seed: int) -> list[dict[str, Any]]:
    if not rows:
        return rows
    subset = list(rows)
    random.Random(seed).shuffle(subset)
    if ratio is not None and 0 < ratio < 1:
        subset = subset[: max(1, int(len(subset) * ratio))]
    if max_examples is not None and max_examples > 0:
        subset = subset[:max_examples]
    return subset


def validate_chat_rows(rows: list[dict[str, Any]], label: str) -> list[str]:
    errors: list[str] = []
    for index, row in enumerate(rows, start=1):
        if not row.get("example_id"):
            errors.append(f"{label} row {index}: missing example_id")
        messages = row.get("messages")
        if not isinstance(messages, list) or not messages:
            errors.append(f"{label} row {index}: messages must be a non-empty list")
            continue
        if messages[-1].get("role") != "assistant":
            errors.append(f"{label} row {index}: last message must be assistant")
        for turn_index, message in enumerate(messages, start=1):
            if message.get("role") not in {"system", "user", "assistant"}:
                errors.append(f"{label} row {index} turn {turn_index}: invalid role {message.get('role')!r}")
            content = message.get("content")
            if not isinstance(content, str) or not content.strip():
                errors.append(f"{label} row {index} turn {turn_index}: empty content")
    return errors


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    task_counts = Counter(row.get("task", "unknown") for row in rows)
    return {
        "rows": len(rows),
        "tasks": dict(sorted(task_counts.items())),
        "sample_ids": [row.get("example_id", "") for row in rows[:5]],
    }


def render_messages(messages: list[dict[str, str]]) -> str:
    parts: list[str] = []
    for message in messages:
        role = message.get("role", "user").upper()
        parts.append(f"{role}: {message.get('content', '').strip()}")
    return "\n\n".join(parts).strip()


def serialize_chat(tokenizer: AutoTokenizer, messages: list[dict[str, str]]) -> str:
    if getattr(tokenizer, "chat_template", None):
        return tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=False,
        )
    return render_messages(messages)


def build_dataset(rows: list[dict[str, Any]], tokenizer: AutoTokenizer, max_seq_length: int) -> Dataset:
    serialized_rows = [
        {
            "example_id": row["example_id"],
            "text": serialize_chat(tokenizer, row["messages"]),
            "metadata": row.get("metadata", {}),
        }
        for row in rows
    ]
    dataset = Dataset.from_list(serialized_rows)

    def tokenize(batch: dict[str, list[Any]]) -> dict[str, list[Any]]:
        encoded = tokenizer(
            batch["text"],
            truncation=True,
            max_length=max_seq_length,
            padding=False,
        )
        encoded["labels"] = [ids[:] for ids in encoded["input_ids"]]
        return encoded

    tokenized = dataset.map(
        tokenize,
        batched=True,
        remove_columns=dataset.column_names,
        desc="Tokenizing chat dataset",
    )
    return tokenized


def compute_dtype(name: str) -> torch.dtype:
    mapping = {
        "float16": torch.float16,
        "fp16": torch.float16,
        "bfloat16": torch.bfloat16,
        "bf16": torch.bfloat16,
        "float32": torch.float32,
        "fp32": torch.float32,
    }
    return mapping.get(name.lower(), torch.bfloat16)


def load_model_and_tokenizer(config: dict[str, Any]) -> tuple[Any, Any]:
    model_name_or_path = config["model_name_or_path"]
    tokenizer = AutoTokenizer.from_pretrained(model_name_or_path, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    quantization_config = None
    if config.get("load_in_4bit", True):
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=config.get("bnb_4bit_use_double_quant", True),
            bnb_4bit_quant_type=config.get("bnb_4bit_quant_type", "nf4"),
            bnb_4bit_compute_dtype=compute_dtype(config.get("bnb_4bit_compute_dtype", "bfloat16")),
        )

    model = AutoModelForCausalLM.from_pretrained(
        model_name_or_path,
        trust_remote_code=True,
        quantization_config=quantization_config,
        dtype=compute_dtype(config.get("torch_dtype", "bfloat16")),
        device_map=config.get("device_map", "auto"),
    )
    model.config.use_cache = False
    return model, tokenizer


def prepare_peft_model(model: Any, config: dict[str, Any]) -> Any:
    if config.get("load_in_4bit", True):
        model = prepare_model_for_kbit_training(
            model,
            use_gradient_checkpointing=config.get("gradient_checkpointing", True),
        )

    lora_config = LoraConfig(
        r=config.get("lora_r", 16),
        lora_alpha=config.get("lora_alpha", 32),
        lora_dropout=config.get("lora_dropout", 0.05),
        bias=config.get("lora_bias", "none"),
        task_type="CAUSAL_LM",
        target_modules=config.get(
            "target_modules",
            ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        ),
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()
    return model


def build_training_arguments(config: dict[str, Any], output_dir: Path, has_eval: bool) -> TrainingArguments:
    return TrainingArguments(
        output_dir=str(output_dir),
        per_device_train_batch_size=config.get("per_device_train_batch_size", 1),
        per_device_eval_batch_size=config.get("per_device_eval_batch_size", 1),
        gradient_accumulation_steps=config.get("gradient_accumulation_steps", 16),
        learning_rate=config.get("learning_rate", 1e-4),
        num_train_epochs=config.get("num_train_epochs", 1.0),
        warmup_ratio=config.get("warmup_ratio", 0.05),
        weight_decay=config.get("weight_decay", 0.0),
        logging_steps=config.get("logging_steps", 10),
        save_steps=config.get("save_steps", 100),
        eval_steps=config.get("eval_steps", 100),
        save_total_limit=config.get("save_total_limit", 3),
        bf16=config.get("bf16", True),
        fp16=config.get("fp16", False),
        gradient_checkpointing=config.get("gradient_checkpointing", True),
        dataloader_num_workers=config.get("dataloader_num_workers", 0),
        report_to=config.get("report_to", []),
        do_train=True,
        do_eval=has_eval,
        eval_strategy="steps" if has_eval else "no",
        save_strategy="steps",
        load_best_model_at_end=bool(has_eval and config.get("load_best_model_at_end", True)),
        metric_for_best_model=config.get("metric_for_best_model", "eval_loss"),
        greater_is_better=config.get("greater_is_better", False),
        remove_unused_columns=False,
        lr_scheduler_type=config.get("lr_scheduler_type", "cosine"),
        seed=config.get("seed", 42),
    )


def save_run_metadata(output_dir: Path, config: dict[str, Any], train_rows: list[dict[str, Any]], val_rows: list[dict[str, Any]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "config": config,
        "train_examples": len(train_rows),
        "val_examples": len(val_rows),
    }
    (output_dir / "resolved_run_config.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a QLoRA adapter on chat-formatted JSONL data.")
    parser.add_argument("--config", required=True, help="Path to the JSON config file.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate config and dataset structure without loading the model or starting training.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = resolve_path(args.config)
    config = load_config(config_path)
    config_issues = validate_required_config(config, allow_unresolved_runtime_paths=args.dry_run)
    if config_issues:
        if not args.dry_run:
            raise ValueError("\n".join(config_issues))

    seed = config.get("seed", 42)
    set_seed(seed)

    train_file = resolve_path(config["train_file"])
    val_file = resolve_path(config["validation_file"])
    output_dir_value = config.get("output_dir", "")
    if args.dry_run and (not output_dir_value or has_unresolved_placeholder(output_dir_value)):
        output_dir = ROOT / "runs" / "dry_run"
    else:
        output_dir = resolve_path(output_dir_value)

    train_rows = maybe_subset(
        load_jsonl(train_file),
        config.get("train_subset_ratio"),
        config.get("max_train_examples"),
        seed,
    )
    val_rows = maybe_subset(
        load_jsonl(val_file),
        config.get("validation_subset_ratio"),
        config.get("max_eval_examples"),
        seed,
    )
    dataset_errors = validate_chat_rows(train_rows, "train") + validate_chat_rows(val_rows, "validation")
    if dataset_errors:
        raise ValueError("\n".join(dataset_errors[:50]))

    if args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        dry_run_summary = {
            "mode": "dry_run",
            "config_path": str(config_path),
            "config_warnings": config_issues,
            "train_file": str(train_file),
            "validation_file": str(val_file),
            "output_dir": str(output_dir),
            "train_summary": summarize_rows(train_rows),
            "validation_summary": summarize_rows(val_rows),
        }
        (output_dir / "dry_run_summary.json").write_text(
            json.dumps(dry_run_summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(dry_run_summary, ensure_ascii=False, indent=2))
        return

    model, tokenizer = load_model_and_tokenizer(config)
    model = prepare_peft_model(model, config)

    train_dataset = build_dataset(train_rows, tokenizer, config.get("max_seq_length", 2048))
    eval_dataset = build_dataset(val_rows, tokenizer, config.get("max_seq_length", 2048)) if val_rows else None
    training_args = build_training_arguments(config, output_dir, eval_dataset is not None)
    save_run_metadata(output_dir, config, train_rows, val_rows)

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
    )

    trainer.train(resume_from_checkpoint=config.get("resume_from_checkpoint"))
    trainer.save_model()
    tokenizer.save_pretrained(output_dir)


if __name__ == "__main__":
    main()
