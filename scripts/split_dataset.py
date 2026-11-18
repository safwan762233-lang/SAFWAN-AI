"""Create deterministic train/validation JSONL files without exact duplicate leakage."""
import argparse
import json
import random
from pathlib import Path

from scripts.train_lora import load_examples


def split_examples(examples, validation_ratio=0.1, seed=42):
    if not 0.05 <= validation_ratio <= 0.4:
        raise ValueError("validation ratio must be between 0.05 and 0.4")
    if len(examples) < 2:
        raise ValueError("At least 2 unique examples are required for a split")
    items = list(examples)
    random.Random(seed).shuffle(items)
    validation_count = max(1, round(len(items) * validation_ratio))
    validation_count = min(validation_count, len(items) - 1)
    return items[validation_count:], items[:validation_count]


def write_jsonl(path, examples):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for item in examples:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Split approved SAFWAN examples")
    parser.add_argument("--data", required=True)
    parser.add_argument("--output-dir", default="./safwan-dataset")
    parser.add_argument("--validation-ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    examples = load_examples(args.data)
    train, validation = split_examples(examples, args.validation_ratio, args.seed)
    out = Path(args.output_dir)
    write_jsonl(out / "train.jsonl", train)
    write_jsonl(out / "validation.jsonl", validation)
    print(f"Unique examples: {len(examples)}")
    print(f"Training examples: {len(train)}")
    print(f"Validation examples: {len(validation)}")
    print(f"Files saved in: {out.resolve()}")


if __name__ == "__main__":
    main()
