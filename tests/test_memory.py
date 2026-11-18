from fastapi.testclient import TestClient

import app.db as db
import app.memory as memory
from app.main import app


def _fake_embeddings(texts):
    vectors = []
    for value in texts:
        lowered = value.lower()
        if "cloud" in lowered or "linux" in lowered:
            vectors.append([1.0, 0.0, 0.0])
        elif "food" in lowered or "factory" in lowered:
            vectors.append([0.0, 1.0, 0.0])
        else:
            vectors.append([0.5, 0.5, 0.0])
    return vectors


def test_memory_crud_and_semantic_search(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_PATH", str(tmp_path / "memory.sqlite3"))
    monkeypatch.setattr(memory, "SAFWAN_APP_TOKEN", "test-admin-secret")
    monkeypatch.setattr(memory, "SAFWAN_MEMORY_ENABLED", True)
    monkeypatch.setattr(memory, "create_embeddings", _fake_embeddings)
    db.init_db()
    client = TestClient(app)
    headers = {"Authorization": "Bearer test-admin-secret"}

    saved = client.post(
        "/api/memory",
        headers=headers,
        json={"content": "I am learning Linux networking and cloud computing for my career.", "category": "goal"},
    )
    assert saved.status_code == 200
    memory_id = saved.json()["id"]

    listed = client.get("/api/memory", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["items"][0]["category"] == "goal"

    results = client.post(
        "/api/memory/search",
        headers=headers,
        json={"query": "server administration and cloud infrastructure"},
    )
    assert results.status_code == 200
    assert results.json()["results"][0]["id"] == memory_id

    deleted = client.delete(f"/api/memory/{memory_id}", headers=headers)
    assert deleted.status_code == 200
    assert client.get("/api/memory", headers=headers).json()["count"] == 0


def test_automatic_memory_skips_short_and_secret_messages(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_PATH", str(tmp_path / "memory-safety.sqlite3"))
    monkeypatch.setattr(memory, "SAFWAN_MEMORY_ENABLED", True)
    monkeypatch.setattr(memory, "create_embeddings", _fake_embeddings)
    db.init_db()

    assert memory.remember("Hello there") is None
    assert memory.remember("My password: do-not-store-this secret phrase") is None
    assert memory.remember("I want to learn Linux and cloud computing to find a better job.") is not None
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM memory_items").fetchone()[0] == 1


def test_memory_requires_master_token_and_can_clear_all(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_PATH", str(tmp_path / "memory-clear.sqlite3"))
    monkeypatch.setattr(memory, "SAFWAN_APP_TOKEN", "test-admin-secret")
    monkeypatch.setattr(memory, "SAFWAN_MEMORY_ENABLED", True)
    monkeypatch.setattr(memory, "create_embeddings", _fake_embeddings)
    db.init_db()
    client = TestClient(app)

    assert client.get("/api/memory").status_code == 401
    headers = {"Authorization": "Bearer test-admin-secret"}
    for n in range(2):
        client.post("/api/memory", headers=headers, json={
            "content": f"Remember that my long term project number {n} is important.",
            "category": "project",
        })
    cleared = client.delete("/api/memory", headers=headers)
    assert cleared.status_code == 200
    assert cleared.json()["deleted"] == 2
    assert client.get("/api/memory", headers=headers).json()["count"] == 0
