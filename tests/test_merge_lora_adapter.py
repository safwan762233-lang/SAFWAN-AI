from pathlib import Path

import pytest

from scripts.merge_lora_adapter import validate_paths


def test_validate_adapter_directory(tmp_path):
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    (adapter / "adapter_config.json").write_text("{}", encoding="utf-8")
    output = tmp_path / "merged"
    found_adapter, found_output = validate_paths(str(adapter), str(output))
    assert found_adapter == adapter.resolve()
    assert found_output == output.resolve()


def test_reject_missing_adapter(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        validate_paths(str(tmp_path / "missing"), str(tmp_path / "out"))


def test_reject_adapter_without_config(tmp_path):
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    with pytest.raises(ValueError, match="adapter_config.json"):
        validate_paths(str(adapter), str(tmp_path / "out"))


def test_reject_output_inside_adapter(tmp_path):
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    (adapter / "adapter_config.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="inside"):
        validate_paths(str(adapter), str(adapter / "merged"))
