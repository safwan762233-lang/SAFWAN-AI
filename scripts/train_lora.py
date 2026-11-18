"""Optional QLoRA/LoRA fine-tuning for an approved SAFWAN JSONL dataset.

Run on Linux with a compatible NVIDIA CUDA GPU. This creates an adapter, not a new
foundation model. Install requirements-training.txt separately.
"""
import argparse
import json
import os
from pathlib import Path


def load_examples(path: str):
    examples = []
    seen = set()
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_no}: {exc}") from exc
            messages = item.get("messages")
            if not isinstance(messages, list) or len(messages) < 2:
                raise ValueError(f"Line {line_no}: expected a messages array with user and assistant")
            roles = [m.get("role") for m in messages if isinstance(m, dict)]
            if "user" not in roles or "assistant" not in roles:
                raise ValueError(f"Line {line_no}: user and assistant messages are required")
            if any(not isinstance(m.get("content"), str) or not m["content"].strip()
                   for m in messages if isinstance(m, dict)):
                raise ValueError(f"Line {line_no}: every message needs non-empty text content")
            key = json.dumps(messages, ensure_ascii=False, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            examples.append({"messages": messages})
    if not examples:
        raise ValueError("Dataset is empty. Export approved examples from SAFWAN AI first.")
    return examples


def main():
    parser = argparse.ArgumentParser(description="Fine-tune an instruction model with LoRA")
    parser.add_argument("--data", required=True, help="Training JSONL export")
    parser.add_argument("--validation-data", default="", help="Optional held-out validation JSONL")
    parser.add_argument("--output", default="./safwan-lora-adapter")
    parser.add_argument("--model", default=os.getenv("SAFWAN_TRAIN_MODEL", "Qwen/Qwen2.5-3B-Instruct"))
    parser.add_argument("--max-length", type=int, default=1024)
    parser.add_argument("--epochs", type=float, default=2)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accumulation", type=int, default=8)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    examples = load_examples(args.data)
    print(f"Dataset valid: {len(examples)} unique examples")
    if args.validate_only:
        print("Validation only: no model downloaded and no training started.")
        return
    if len(examples) < 20:
        raise SystemExit("Safety stop: at least 20 reviewed examples are required to start this experimental pipeline. More diverse, high-quality data is strongly recommended.")
    if args.max_length < 128 or args.max_length > 8192:
        raise SystemExit("--max-length must be between 128 and 8192")
    if args.epochs <= 0 or args.epochs > 10:
        raise SystemExit("--epochs must be >0 and <=10")

    try:
        import torch
        from datasets import Dataset
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        from transformers import (
            AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig,
            DataCollatorForLanguageModeling, Trainer, TrainingArguments,
        )
    except ImportError as exc:
        raise SystemExit(
            "Training packages are missing. On a supported Linux CUDA environment, "
            "install requirements-training.txt. Details: " + str(exc)
        )
    if not torch.cuda.is_available():
        raise SystemExit("No CUDA GPU detected. This QLoRA script intentionally stops instead of attempting CPU training.")

    tokenizer = AutoTokenizer.from_pretrained(args.model, use_fast=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        quantization_config=quant_config,
        device_map="auto",
    )
    model = prepare_model_for_kbit_training(model)
    model.config.use_cache = False
    model = get_peft_model(model, LoraConfig(
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    ))
    model.print_trainable_parameters()

    rendered = []
    for example in examples:
        text = tokenizer.apply_chat_template(
            example["messages"], tokenize=False, add_generation_prompt=False
        )
        rendered.append({"text": text})
    dataset = Dataset.from_list(rendered)

    def tokenize(batch):
        return tokenizer(batch["text"], truncation=True, max_length=args.max_length)

    tokenized = dataset.map(tokenize, batched=True, remove_columns=["text"])
    validation_tokenized = None
    if args.validation_data:
        validation_examples = load_examples(args.validation_data)
        validation_rendered = [{"text": tokenizer.apply_chat_template(
            item["messages"], tokenize=False, add_generation_prompt=False
        )} for item in validation_examples]
        validation_dataset = Dataset.from_list(validation_rendered)
        validation_tokenized = validation_dataset.map(
            tokenize, batched=True, remove_columns=["text"]
        )
    training_args = TrainingArguments(
        output_dir=args.output,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accumulation,
        learning_rate=2e-4,
        logging_steps=5,
        save_strategy="epoch",
        evaluation_strategy="epoch" if validation_tokenized is not None else "no",
        load_best_model_at_end=validation_tokenized is not None,
        fp16=True,
        optim="paged_adamw_8bit",
        report_to="none",
        gradient_checkpointing=True,
        remove_unused_columns=False,
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized,
        eval_dataset=validation_tokenized,
        data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
    )
    trainer.train()
    model.save_pretrained(args.output)
    tokenizer.save_pretrained(args.output)
    print(f"LoRA adapter saved to: {args.output}")
    print("The base model is not copied or modified. Evaluate the adapter before serving it.")


if __name__ == "__main__":
    main()
