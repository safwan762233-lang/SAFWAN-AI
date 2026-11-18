import json
import pytest
from scripts.train_lora import load_examples


def test_load_examples_validates_and_deduplicates(tmp_path):
    path = tmp_path / "approved.jsonl"
    item = {"messages": [
        {"role": "user", "content": "Explain DNS"},
        {"role": "assistant", "content": "DNS maps names to IP addresses."}
    ]}
    path.write_text(json.dumps(item) + "\n" + json.dumps(item) + "\n", encoding="utf-8")
    examples = load_examples(str(path))
    assert len(examples) == 1
    assert examples[0]["messages"][0]["role"] == "user"


def test_load_examples_rejects_invalid_json(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSON"):
        load_examples(str(path))


def test_load_examples_rejects_missing_assistant(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text(json.dumps({"messages":[{"role":"user","content":"Hi"}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="user and assistant"):
        load_examples(str(path))
