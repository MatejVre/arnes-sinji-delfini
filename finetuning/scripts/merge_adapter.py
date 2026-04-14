from __future__ import annotations

import argparse
import json
from pathlib import Path

from peft import PeftModel
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge a PEFT adapter into the base model and save a standalone export.")
    parser.add_argument("--base-model", required=True, help="Base model path or Hugging Face model id.")
    parser.add_argument("--adapter-path", required=True, help="Path to the adapter directory produced by training.")
    parser.add_argument("--output-dir", required=True, help="Directory where the merged model will be saved.")
    parser.add_argument("--dtype", default="bfloat16", help="Model load dtype: bfloat16, float16, or float32.")
    parser.add_argument("--device-map", default="auto", help="Transformers device_map value. Use auto by default.")
    parser.add_argument("--max-shard-size", default="10GB", help="Shard size for save_pretrained.")
    parser.add_argument("--unsafe-serialization", action="store_true", help="Save .bin weights instead of safetensors.")
    return parser.parse_args()


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


def main() -> None:
    args = parse_args()
    adapter_path = Path(args.adapter_path).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    tokenizer_source = adapter_path if (adapter_path / "tokenizer_config.json").exists() else args.base_model
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_source, trust_remote_code=True)

    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        trust_remote_code=True,
        dtype=compute_dtype(args.dtype),
        device_map=args.device_map,
        low_cpu_mem_usage=True,
    )
    peft_model = PeftModel.from_pretrained(model, str(adapter_path))
    merged_model = peft_model.merge_and_unload()

    merged_model.save_pretrained(
        output_dir,
        safe_serialization=not args.unsafe_serialization,
        max_shard_size=args.max_shard_size,
    )
    tokenizer.save_pretrained(output_dir)

    manifest = {
        "base_model": args.base_model,
        "adapter_path": str(adapter_path),
        "output_dir": str(output_dir),
        "dtype": args.dtype,
        "device_map": args.device_map,
        "safe_serialization": not args.unsafe_serialization,
    }
    (output_dir / "merge_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
