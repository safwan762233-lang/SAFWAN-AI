from fastapi.testclient import TestClient
import app.db as db
import app.training_data as training_data
from app.main import app

def test_training_data_requires_master_token(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_PATH", str(tmp_path / "training.sqlite3"))
    monkeypatch.setattr(training_data, "SAFWAN_APP_TOKEN", "admin-secret")
    db.init_db()
    client = TestClient(app)
    assert client.get("/api/training-data").status_code == 401

def test_create_review_and_export_only_approved(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_PATH", str(tmp_path / "training.sqlite3"))
    monkeypatch.setattr(training_data, "SAFWAN_APP_TOKEN", "admin-secret")
    db.init_db()
    client = TestClient(app)
    headers = {"Authorization": "Bearer admin-secret"}
    created = client.post("/api/training-data", headers=headers, json={
        "prompt": "Explain DNS", "ideal_answer": "DNS translates domain names to IP addresses."
    })
    assert created.status_code == 200
    example_id = created.json()["id"]
    assert created.json()["status"] == "draft"
    assert client.get("/api/training-data/export.jsonl", headers=headers).text == ""
    approved = client.patch(f"/api/training-data/{example_id}/status", headers=headers,
                            json={"status": "approved"})
    assert approved.status_code == 200
    export = client.get("/api/training-data/export.jsonl", headers=headers)
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("application/x-ndjson")
    assert '"role": "user"' in export.text and "DNS translates" in export.text
    edited = client.patch(f"/api/training-data/{example_id}", headers=headers, json={
        "prompt": "Explain DNS simply", "ideal_answer": "DNS maps names to IP addresses."
    })
    assert edited.status_code == 200 and edited.json()["status"] == "draft"
    assert client.get("/api/training-data/export.jsonl", headers=headers).text == ""

def test_training_data_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_PATH", str(tmp_path / "training.sqlite3"))
    monkeypatch.setattr(training_data, "SAFWAN_APP_TOKEN", "admin-secret")
    db.init_db()
    client = TestClient(app)
    headers = {"Authorization": "Bearer admin-secret"}
    item = client.post("/api/training-data", headers=headers, json={
        "prompt": "Question", "ideal_answer": "Answer"
    }).json()
    assert client.delete(f"/api/training-data/{item['id']}", headers=headers).json()["deleted"] is True
