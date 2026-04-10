import os
from pathlib import Path
from typing import Any

from huggingface_hub import snapshot_download
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

DEFAULT_BASE_MODEL_ID = "cjvt/GaMS3-12B-Instruct"
DEFAULT_FINETUNING_ROOT = "LLM/finetuning"
DEFAULT_LOCAL_MODELS_DIR = "LLM/models"
DEFAULT_OFFLOAD_DIR = "LLM/models/offload"

REQUIRED_ADAPTER_FILES = [
    "adapter_config.json",
    "adapter_model.safetensors",
    "tokenizer.json",
    "tokenizer_config.json",
]


def create_llm_resources(
    base_model_id: str | None = None,
    finetuning_root: str = DEFAULT_FINETUNING_ROOT,
    local_models_dir: str = DEFAULT_LOCAL_MODELS_DIR,
    offload_dir: str = DEFAULT_OFFLOAD_DIR,
    device_map: str | None = None,
    use_4bit: bool | None = None,
    enable_cpu_offload: bool | None = None,
    hf_token: str | None = None,
    trust_remote_code: bool = True,
) -> dict[str, Any]:
    resolved_base_model_id = _resolve_base_model_id(base_model_id)
    model_basename = _model_basename(resolved_base_model_id)

    finetuning_root_path = Path(finetuning_root)
    adapter_path = _resolve_adapter_path(finetuning_root_path, model_basename)

    local_model_path = Path(local_models_dir) / model_basename
    offload_path = Path(offload_dir)
    offload_path.mkdir(parents=True, exist_ok=True)

    token = hf_token or os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_HUB_TOKEN")
    device_map_effective = _resolve_device_map(device_map)
    requested_use_4bit = _resolve_use_4bit(use_4bit)
    enable_cpu_offload_effective = _resolve_enable_cpu_offload(enable_cpu_offload)

    _ensure_local_base_model(resolved_base_model_id, local_model_path, token)

    tokenizer_source = str(adapter_path) if adapter_path is not None else str(local_model_path)
    tokenizer = AutoTokenizer.from_pretrained(
        tokenizer_source,
        trust_remote_code=trust_remote_code,
        token=token,
        local_files_only=True,
    )

    model, effective_use_4bit, quantization_fallback_reason = _load_base_model(
        local_model_path=local_model_path,
        offload_path=offload_path,
        token=token,
        trust_remote_code=trust_remote_code,
        device_map=device_map_effective,
        use_4bit=requested_use_4bit,
        enable_cpu_offload=enable_cpu_offload_effective,
    )

    load_mode = "base-only"
    adapter_dir_used = None
    adapter_found = adapter_path is not None

    if adapter_path is not None:
        try:
            model = PeftModel.from_pretrained(
                model,
                str(adapter_path),
                is_trainable=False,
                device_map=device_map_effective,
                low_cpu_mem_usage=True,
            )
        except TypeError:
            model = PeftModel.from_pretrained(
                model,
                str(adapter_path),
                is_trainable=False,
                device_map=None,
                low_cpu_mem_usage=False,
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to load LoRA adapter from '{adapter_path}': {exc}") from exc

        model.eval()
        if hasattr(model, "merge_and_unload"):
            try:
                model = model.merge_and_unload()
                model.eval()
            except Exception:
                pass

        load_mode = "base+adapter"
        adapter_dir_used = str(adapter_path)

    model.eval()

    if tokenizer.pad_token is None and tokenizer.eos_token is not None:
        tokenizer.pad_token = tokenizer.eos_token

    return {
        "tokenizer": tokenizer,
        "model": model,
        "base_model_id": resolved_base_model_id,
        "model_basename": model_basename,
        "local_model_dir": str(local_model_path),
        "offload_dir": str(offload_path),
        "finetuning_root": str(finetuning_root_path),
        "adapter_found": adapter_found,
        "adapter_dir_used": adapter_dir_used,
        "load_mode": load_mode,
        "device_map": device_map_effective,
        "requested_use_4bit": requested_use_4bit,
        "effective_use_4bit": effective_use_4bit,
        "quantization_fallback_reason": quantization_fallback_reason,
        "enable_cpu_offload": enable_cpu_offload_effective,
        "device": _infer_device(model),
    }


def chat_with_model(
    resources: dict[str, Any],
    messages: list[dict[str, str]],
    max_new_tokens: int = 256,
    temperature: float = 0.2,
    top_p: float = 0.9,
    do_sample: bool = True,
) -> str:
    _validate_messages(messages)

    tokenizer = resources.get("tokenizer")
    model = resources.get("model")
    if tokenizer is None or model is None:
        raise ValueError("Invalid resources. Expected keys: 'tokenizer' and 'model'.")

    prompt_inputs = tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,
        return_tensors="pt",
    )

    model_device = _get_model_device(model)
    prompt_inputs = prompt_inputs.to(model_device)
    attention_mask = torch.ones_like(prompt_inputs)

    generation_kwargs = {
        "max_new_tokens": max_new_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "do_sample": do_sample,
        "pad_token_id": tokenizer.pad_token_id,
        "eos_token_id": tokenizer.eos_token_id,
    }

    with torch.inference_mode():
        output_ids = model.generate(
            input_ids=prompt_inputs,
            attention_mask=attention_mask,
            **generation_kwargs,
        )

    new_tokens = output_ids[0][prompt_inputs.shape[-1] :]
    response = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
    return response


def _load_base_model(
    local_model_path: Path,
    offload_path: Path,
    token: str | None,
    trust_remote_code: bool,
    device_map: str,
    use_4bit: bool,
    enable_cpu_offload: bool,
):
    quantization_fallback_reason = None
    quantization_config = None
    if use_4bit:
        if not torch.cuda.is_available():
            quantization_fallback_reason = "4-bit requested but CUDA is unavailable; falling back to non-quantized load."
            use_4bit = False
        else:
            quantization_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
                llm_int8_enable_fp32_cpu_offload=enable_cpu_offload,
            )

    kwargs = {
        "trust_remote_code": trust_remote_code,
        "token": token,
        "torch_dtype": "auto",
        "local_files_only": True,
        "device_map": device_map,
        "offload_folder": str(offload_path),
        "offload_state_dict": True,
    }
    if quantization_config is not None:
        kwargs["quantization_config"] = quantization_config

    try:
        model = AutoModelForCausalLM.from_pretrained(str(local_model_path), **kwargs)
    except Exception as exc:
        if use_4bit and _is_quantization_compat_error(exc):
            fallback_reason = (
                "4-bit compatibility error detected; retrying with non-quantized loading. "
                f"Original error: {exc}"
            )
            fallback_model = _load_non_quantized_model(
                local_model_path=local_model_path,
                offload_path=offload_path,
                token=token,
                trust_remote_code=trust_remote_code,
                device_map=device_map,
            )
            return fallback_model, False, fallback_reason
        raise RuntimeError(
            f"Failed to load local base model from '{local_model_path}': {exc}"
        ) from exc

    if not torch.cuda.is_available():
        model = model.to("cpu")
    return model, use_4bit, quantization_fallback_reason


def _load_non_quantized_model(
    local_model_path: Path,
    offload_path: Path,
    token: str | None,
    trust_remote_code: bool,
    device_map: str,
):
    kwargs = {
        "trust_remote_code": trust_remote_code,
        "token": token,
        "torch_dtype": "auto",
        "local_files_only": True,
        "device_map": device_map,
        "offload_folder": str(offload_path),
        "offload_state_dict": True,
    }
    try:
        model = AutoModelForCausalLM.from_pretrained(str(local_model_path), **kwargs)
    except Exception as exc:
        raise RuntimeError(
            f"Fallback non-quantized load also failed for '{local_model_path}': {exc}"
        ) from exc

    if not torch.cuda.is_available():
        model = model.to("cpu")
    return model


def _is_quantization_compat_error(exc: Exception) -> bool:
    message = str(exc)
    return (
        "Params4bit.__new__() got an unexpected keyword argument '_is_hf_initialized'" in message
        or "Params4bit.__new__()" in message
        or "Configured CUDA binary not found at" in message
        or "libbitsandbytes_cuda" in message
    )


def _resolve_base_model_id(base_model_id: str | None) -> str:
    if base_model_id and base_model_id.strip():
        return base_model_id.strip()
    return os.getenv("LLM_BASE_MODEL_ID", DEFAULT_BASE_MODEL_ID).strip()


def _model_basename(base_model_id: str) -> str:
    return base_model_id.split("/")[-1].strip()


def _resolve_use_4bit(use_4bit: bool | None) -> bool:
    if use_4bit is not None:
        return use_4bit

    raw = os.getenv("LLM_USE_4BIT", "1").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _resolve_enable_cpu_offload(enable_cpu_offload: bool | None) -> bool:
    if enable_cpu_offload is not None:
        return enable_cpu_offload

    raw = os.getenv("LLM_ENABLE_CPU_OFFLOAD", "1").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _resolve_device_map(device_map: str | None) -> str:
    if device_map is not None:
        return device_map
    return os.getenv("LLM_DEVICE_MAP", "auto").strip()


def _ensure_local_base_model(base_model_id: str, local_model_path: Path, token: str | None) -> None:
    model_indicator = local_model_path / "config.json"
    if model_indicator.exists():
        return

    local_model_path.mkdir(parents=True, exist_ok=True)
    try:
        snapshot_download(
            repo_id=base_model_id,
            local_dir=str(local_model_path),
            token=token,
        )
    except Exception as exc:
        message = str(exc)
        gated_hint = "403" in message or "401" in message or "gated" in message.lower()
        if gated_hint and not token:
            raise RuntimeError(
                "Failed to download base model. The repository may be gated/private; set HF_TOKEN or "
                "HUGGINGFACE_HUB_TOKEN."
            ) from exc
        raise RuntimeError(
            f"Failed to download base model '{base_model_id}' to '{local_model_path}': {exc}"
        ) from exc


def _resolve_adapter_path(finetuning_root: Path, model_basename: str) -> Path | None:
    candidate = finetuning_root / model_basename
    if not candidate.exists() or not candidate.is_dir():
        return None

    missing = [name for name in REQUIRED_ADAPTER_FILES if not (candidate / name).exists()]
    if missing:
        return None
    return candidate


def _validate_messages(messages: list[dict[str, str]]) -> None:
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages must be a non-empty list of {'role', 'content'} items.")

    allowed_roles = {"system", "user", "assistant"}
    for i, message in enumerate(messages):
        if not isinstance(message, dict):
            raise ValueError(f"messages[{i}] must be a dict.")
        role = message.get("role")
        content = message.get("content")
        if role not in allowed_roles:
            raise ValueError(f"messages[{i}].role must be one of {sorted(allowed_roles)}.")
        if not isinstance(content, str) or not content.strip():
            raise ValueError(f"messages[{i}].content must be a non-empty string.")


def _get_model_device(model) -> torch.device:
    hf_device_map = getattr(model, "hf_device_map", None)
    if isinstance(hf_device_map, dict):
        for device in hf_device_map.values():
            if isinstance(device, str) and device not in {"cpu", "disk"}:
                return torch.device(device)

    if hasattr(model, "device"):
        return model.device

    try:
        return next(model.parameters()).device
    except StopIteration as exc:
        raise RuntimeError("Unable to infer model device from parameters.") from exc


def _infer_device(model) -> str:
    try:
        return str(_get_model_device(model))
    except Exception:
        return "unknown"
