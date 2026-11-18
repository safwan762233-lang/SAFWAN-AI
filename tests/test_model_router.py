from app.model_router import classify_task, select_models


def test_classifies_coding_and_reasoning_tasks():
    assert classify_task([{"role": "user", "content": "Help debug this Python API"}]) == "coding"
    assert classify_task([{"role": "user", "content": "Analyze and compare these plans"}]) == "reasoning"
    assert classify_task([{"role": "user", "content": "Hello there"}]) == "general"


def test_selects_only_installed_models_and_uses_fallback(monkeypatch):
    import app.model_router as router
    monkeypatch.setattr(router, "SAFWAN_CODING_MODEL", "deepseek-coder:6.7b")
    monkeypatch.setattr(router, "OLLAMA_MODEL", "qwen2.5:7b")
    monkeypatch.setattr(router, "SAFWAN_FALLBACK_MODEL", "llama3.2:3b")
    task, models = select_models(
        [{"role": "user", "content": "Write Python code"}],
        ["qwen2.5:7b", "llama3.2:3b"],
    )
    assert task == "coding"
    assert models == ["qwen2.5:7b", "llama3.2:3b"]


def test_requested_installed_model_has_priority(monkeypatch):
    import app.model_router as router
    monkeypatch.setattr(router, "OLLAMA_MODEL", "qwen2.5:7b")
    monkeypatch.setattr(router, "SAFWAN_FALLBACK_MODEL", "")
    task, models = select_models(
        [{"role": "user", "content": "Hello"}],
        ["qwen2.5:7b", "mistral:7b"],
        "mistral:7b",
    )
    assert task == "general"
    assert models == ["mistral:7b", "qwen2.5:7b"]
