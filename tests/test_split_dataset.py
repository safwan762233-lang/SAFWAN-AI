import json
import pytest
from scripts.split_dataset import split_examples


def make_examples(count):
    return [{"messages":[
        {"role":"user","content":f"Question {i}"},
        {"role":"assistant","content":f"Answer {i}"}
    ]} for i in range(count)]


def test_split_is_reproducible_and_disjoint():
    examples = make_examples(30)
    train1, val1 = split_examples(examples, 0.2, 17)
    train2, val2 = split_examples(examples, 0.2, 17)
    assert train1 == train2
    assert val1 == val2
    train_keys = {json.dumps(x, sort_keys=True) for x in train1}
    val_keys = {json.dumps(x, sort_keys=True) for x in val1}
    assert train_keys.isdisjoint(val_keys)
    assert len(train1) + len(val1) == 30


def test_split_requires_two_examples():
    with pytest.raises(ValueError, match="At least 2"):
        split_examples(make_examples(1))


def test_split_rejects_bad_ratio():
    with pytest.raises(ValueError, match="between 0.05 and 0.4"):
        split_examples(make_examples(10), 0.8)
