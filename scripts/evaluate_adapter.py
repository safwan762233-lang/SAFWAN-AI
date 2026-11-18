"""Compare a base model and its LoRA adapter on a held-out JSONL set.

Scores are simple token-overlap diagnostics, not factuality or safety benchmarks.
Requires a supported NVIDIA CUDA environment and optional training dependencies.
"""
import argparse
import json
import re
import time
from pathlib import Path

from scripts.train_lora import load_examples


def token_f1(prediction, reference):
    pred = re.findall(r"\w+", prediction.lower())
    ref = re.findall(r"\w+", reference.lower())
    if not pred or not ref:
        return 0.0
    from collections import Counter
    overlap = sum((Counter(pred) & Counter(ref)).values())
    if not overlap:
        return 0.0
    precision = overlap / len(pred)
    recall = overlap / len(ref)
    return 2 * precision * recall / (precision + recall)


def main():
    parser = argparse.ArgumentParser(description="Evaluate base model versus LoRA adapter")
    parser.add_argument("--data", required=True, help="Held-out JSONL test set")
    parser.add_argument("--adapter", required=True, help="Saved LoRA adapter directory")
    parser.add_argument("--model", default="Qwen/Qwen2.5-3B-Instruct")
    parser.add_argument("--output", default="./safwan-evaluation.json")
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    examples = load_examples(args.data)[:args.limit]
    if not examples:
        raise SystemExit("No evaluation examples found.")
    try:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    except ImportError as exc:
        raise SystemExit("Install requirements-training.txt in a supported environment: " + str(exc))
    if not torch.cuda.is_available():
        raise SystemExit("No CUDA GPU detected. This evaluation script requires CUDA.")

    tokenizer = AutoTokenizer.from_pretrained(args.model, use_fast=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    quant = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )
    base = AutoModelForCausalLM.from_pretrained(
        args.model, quantization_config=quant, device_map="auto"
    )
    base.eval()
    adapter = PeftModel.from_pretrained(base, args.adapter)
    adapter.eval()

    results = []
    for index, example in enumerate(examples, 1):
        messages = example["messages"]
        target_index = max(i for i, message in enumerate(messages) if message["role"] == "assistant")
        reference = messages[target_index]["content"]
        prompt_messages = messages[:target_index]
        prompt = tokenizer.apply_chat_template(
            prompt_messages, tokenize=False, add_generation_prompt=True
        )
        inputs = tokenizer(prompt, return_tensors="pt").to("cuda")
        row = {"index": index, "reference": reference}
        for label in ("base", "adapter"):
            started = time.perf_counter()
            with torch.inference_mode():
                if label == "base":
                    with adapter.disable_adapter():
                        output = adapter.generate(
                            **inputs,
                            max_new_tokens=args.max_new_tokens,
                            do_sample=False,
                            pad_token_id=tokenizer.pad_token_id,
                        )
                else:
                    output = adapter.generate(
                        **inputs,
                        max_new_tokens=args.max_new_tokens,
                        do_sample=False,
                        pad_token_id=tokenizer.pad_token_id,
                    )
            elapsed = time.perf_counter() - started
            generated = tokenizer.decode(
                output[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True
            ).strip()
            row[label] = {
                "answer": generated,
                "token_f1": round(token_f1(generated, reference), 4),
                "latency_seconds": round(elapsed, 3),
            }
        results.append(row)
        print(f"Evaluated {index}/{len(examples)}")

    summary = {}
    for label in ("base", "adapter"):
        summary[label] = {
            "mean_token_f1": round(sum(r[label]["token_f1"] for r in results) / len(results), 4),
            "mean_latency_seconds": round(sum(r[label]["latency_seconds"] for r in results) / len(results), 3),
        }
    report = {
        "base_model": args.model,
        "adapter_path": args.adapter,
        "examples": len(results),
        "summary": summary,
        "warning": "Token F1 and latency are diagnostics only; human review is required for factuality, safety, completeness, and usefulness.",
        "results": results,
    }
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report saved: {target.resolve()}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
