from fastapi.testclient import TestClient

import app.db as db
import app.knowledge as knowledge
from app.main import app


def test_upload_search_and_delete_text_document(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_PATH", str(tmp_path / "knowledge.sqlite3"))
    monkeypatch.setattr(knowledge, "SAFWAN_APP_TOKEN", "test-admin-secret")
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

    results = client.post(
        "/api/knowledge/search",
        headers=admin,
        json={"query": "remote work Fridays"},
    )
    assert results.status_code == 200
    assert results.json()["results"][0]["filename"] == "company-policy.txt"
    assert "remote work" in results.json()["results"][0]["content"]

    listed = client.get("/api/knowledge/documents", headers=admin)
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == document_id

    deleted = client.delete(f"/api/knowledge/documents/{document_id}", headers=admin)
    assert deleted.status_code == 200
    assert client.get("/api/knowledge/documents", headers=admin).json() == []


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
