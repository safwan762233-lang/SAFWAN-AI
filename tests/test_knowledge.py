from fastapi.testclient import TestClient

import app.db as db
import app.knowledge as knowledge
from app.main import app


def _fake_embeddings(texts):
    vectors = []
    for text in texts:
        lowered = text.lower()
        if "company policy" in lowered or "remote work" in lowered or "fridays" in lowered:
            vectors.append([1.0, 0.0, 0.0])
        elif "vacation" in lowered or "annual leave" in lowered or "take off" in lowered or "days" in lowered:
            vectors.append([0.0, 1.0, 0.0])
        else:
            vectors.append([0.8, 0.1, 0.0])
    return vectors


def test_upload_search_and_delete_text_document(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_PATH", str(tmp_path / "knowledge.sqlite3"))
    monkeypatch.setattr(knowledge, "SAFWAN_APP_TOKEN", "test-admin-secret")
    monkeypatch.setattr(knowledge, "create_embeddings", _fake_embeddings)
    db.init_db()
    client = TestClient(app)
    admin = {"Authorization": "Bearer test-admin-secret"}

    response = client.post(
        "/api/knowledge/upload",
        headers=admin,
        files={"file": ("company-policy.txt", b"SAFWAN company policy allows remote work on Fridays.", "text/plain")},
    )
    assert response.status_code == 200
    document_id = response.json()["id"]
    assert response.json()["chunks"] == 1
    assert response.json()["embedded"] is True

    results = client.post(
        "/api/knowledge/search",
        headers=admin,
        json={"query": "working from home on the last weekday"},
    )
    assert results.status_code == 200
    assert results.json()["mode"] == "hybrid"
    assert results.json()["results"][0]["filename"] == "company-policy.txt"
    assert "remote work" in results.json()["results"][0]["content"]

    listed = client.get("/api/knowledge/documents", headers=admin)
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == document_id
    assert listed.json()[0]["embedded_chunks"] == 1

    deleted = client.delete(f"/api/knowledge/documents/{document_id}", headers=admin)
    assert deleted.status_code == 200
    assert client.get("/api/knowledge/documents", headers=admin).json() == []


def test_semantic_search_finds_related_words_without_keyword_overlap(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_PATH", str(tmp_path / "semantic.sqlite3"))
    monkeypatch.setattr(knowledge, "SAFWAN_APP_TOKEN", "test-admin-secret")
    monkeypatch.setattr(knowledge, "create_embeddings", _fake_embeddings)
    db.init_db()
    with db.connect() as con:
        cur = con.execute(
            "INSERT INTO knowledge_documents(filename,file_type,char_count) VALUES(?,?,?)",
            ("leave-policy.txt", "txt", 45),
        )
        con.execute(
            "INSERT INTO knowledge_chunks(document_id,chunk_index,content,embedding_json) VALUES(?,?,?,?)",
            (cur.lastrowid, 0, "Employees receive annual leave under the vacation policy.", '[0.0, 1.0, 0.0]'),
        )

    results = knowledge.search_knowledge("How many days can staff take off?", limit=2)
    assert results
    assert results[0]["filename"] == "leave-policy.txt"
    assert results[0]["method"] == "hybrid"
    assert results[0]["semantic_score"] > 0.9


def test_reindex_fills_missing_embeddings(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_PATH", str(tmp_path / "reindex.sqlite3"))
    monkeypatch.setattr(knowledge, "SAFWAN_APP_TOKEN", "test-admin-secret")
    monkeypatch.setattr(knowledge, "create_embeddings", _fake_embeddings)
    db.init_db()
    with db.connect() as con:
        cur = con.execute(
            "INSERT INTO knowledge_documents(filename,file_type,char_count) VALUES(?,?,?)",
            ("old.txt", "txt", 20),
        )
        con.execute(
            "INSERT INTO knowledge_chunks(document_id,chunk_index,content) VALUES(?,?,?)",
            (cur.lastrowid, 0, "Older document without a vector."),
        )
    client = TestClient(app)
    response = client.post("/api/knowledge/reindex", headers={"Authorization": "Bearer test-admin-secret"})
    assert response.status_code == 200
    assert response.json()["indexed"] == 1
    with db.connect() as con:
        vector = con.execute("SELECT embedding_json FROM knowledge_chunks").fetchone()[0]
    assert vector is not None


def test_knowledge_upload_requires_admin(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_PATH", str(tmp_path / "knowledge-auth.sqlite3"))
    monkeypatch.setattr(knowledge, "SAFWAN_APP_TOKEN", "test-admin-secret")
    db.init_db()
    client = TestClient(app)
    response = client.post(
        "/api/knowledge/upload",
        files={"file": ("notes.txt", b"Private notes", "text/plain")},
    )
    assert response.status_code == 401
