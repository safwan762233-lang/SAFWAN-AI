import app.intelligence as intelligence


def test_intelligence_context_filters_and_bounds_references(monkeypatch):
    monkeypatch.setattr(intelligence, "get_business_context_data", lambda: {"products": 3})
    monkeypatch.setattr(intelligence, "search_knowledge", lambda query, limit=4: [
        {"filename": "guide.txt", "content": "A" * 3000, "score": 0.91},
        {"filename": "weak.txt", "content": "Do not include me", "score": 0.01},
    ])
    monkeypatch.setattr(intelligence, "search_memories", lambda query, limit=4: [
        {"category": "goal", "content": "Learn cloud administration", "score": 0.7},
    ])

    result = intelligence.build_intelligence_context("How do I plan?")
    assert result["business_snapshot"] == {"products": 3}
    assert len(result["relevant_documents"]) == 1
    assert len(result["relevant_documents"][0]["content"]) == intelligence.MAX_REFERENCE_CHARS
    assert result["relevant_documents"][0]["source"] == "guide.txt"
    assert result["relevant_memories"][0]["source"] == "goal"
    assert any("untrusted reference data" in rule for rule in result["context_rules"])


def test_intelligence_context_without_query_skips_retrieval(monkeypatch):
    monkeypatch.setattr(intelligence, "get_business_context_data", lambda: {"customers": 0})

    def fail(*args, **kwargs):
        raise AssertionError("retrieval should not run without a query")

    monkeypatch.setattr(intelligence, "search_knowledge", fail)
    monkeypatch.setattr(intelligence, "search_memories", fail)
    result = intelligence.build_intelligence_context("")
    assert result["business_snapshot"] == {"customers": 0}
    assert result["relevant_documents"] == []
    assert result["relevant_memories"] == []
