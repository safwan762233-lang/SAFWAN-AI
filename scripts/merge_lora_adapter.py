"""Merge a trained PEFT LoRA adapter into its original Hugging Face base model.

Run in a separate Linux + NVIDIA CUDA training environment. This does not
convert the merged model to GGUF or install it into Ollama.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def validate_paths(adapter: str, output: str) -> tuple[Path, Path]:
    adapter_path = Path(adapter).expanduser().resolve()
    output_path = Path(output).expanduser().resolve()
    if not adapter_path.is_dir():
        raise ValueError(f"Adapter directory does not exist: {adapter_path}")
    if not (adapter_path / "adapter_config.json").is_file():
        raise ValueError("Adapter directory must contain adapter_config.json")
    if output_path == adapter_path or adapter_path in output_path.parents:
        raise ValueError("Output directory must not be inside the adapter directory")
    if output_path.exists() and any(output_path.iterdir()):
        raise ValueError(f"Output directory is not empty: {output_path}")
    return adapter_path, output_path


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", required=True, help="PEFT LoRA adapter directory")
    parser.add_argument("--model", default="Qwen/Qwen2.5-3B-Instruct",
                        help="Exact original Hugging Face base model used for training")
    parser.add_argument("--output", default="./safwan-merged-model",
                        help="New directory for merged full model")
    parser.add_argument("--validate-only", action="store_true")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        adapter_path, output_path = validate_paths(args.adapter, args.output)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if args.validate_only:
        print(f"Adapter: {adapter_path}")
        print(f"Base model: {args.model}")
        print(f"Output: {output_path}")
        print("Path validation passed. No model was loaded or changed.")
        return

    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import PeftModel
    except ImportError as exc:
        raise SystemExit(
            "Missing optional training packages. Install PyTorch for your CUDA setup, "
            "then run: pip install -r requirements-training.txt"
        ) from exc

    if not torch.cuda.is_available():
        raise SystemExit("CUDA GPU not detected. This merge workflow intentionally does not run on CPU.")
    output_path.mkdir(parents=True, exist_ok=True)
    print("Loading the original base model in FP16. This can require substantial GPU RAM and disk space.")
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=False)
    base = AutoModelForCausalLM.from_pretrained(
        args.model,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=False,
    )
    peft_model = PeftModel.from_pretrained(base, str(adapter_path))
    merged = peft_model.merge_and_unload()
    merged.save_pretrained(output_path, safe_serialization=True, max_shard_size="4GB")
    tokenizer.save_pretrained(output_path)
    print(f"Merged Hugging Face model saved to: {output_path}")
    print("Next: convert this merged directory to GGUF with llama.cpp, then import the GGUF into Ollama.")
    print("The original adapter and base model were not modified.")


if __name__ == "__main__":
    main()
