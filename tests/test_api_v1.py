import pytest
from fastapi.testclient import TestClient

import app.db as db
import app.api_v1 as api_v1
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_PATH", str(tmp_path / "api-test.sqlite3"))
    monkeypatch.setattr(api_v1, "SAFWAN_APP_TOKEN", "test-admin-secret")
    db.init_db()
    return TestClient(app)


def test_api_key_lifecycle_and_models(client):
    assert client.get("/v1/models").status_code == 401
    admin = {"Authorization": "Bearer test-admin-secret"}
    created = client.post("/api/keys", headers=admin, json={"name": "Test integration"})
    assert created.status_code == 200
    key_data = created.json()
    assert key_data["key"].startswith("safwan_")
    api_headers = {"Authorization": "Bearer " + key_data["key"]}

    models = client.get("/v1/models", headers=api_headers)
    assert models.status_code == 200
    assert models.json()["data"][0]["id"] == "safwan-local"

    listed = client.get("/api/keys", headers=admin)
    assert listed.status_code == 200
    assert listed.json()[0]["key_prefix"] == key_data["key_prefix"]
    assert "key_hash" not in listed.text
    assert key_data["key"] not in listed.text

    revoked = client.delete(f"/api/keys/{key_data['id']}", headers=admin)
    assert revoked.status_code == 200
    assert client.get("/v1/models", headers=api_headers).status_code == 401


def test_openai_compatible_chat_completion(client, monkeypatch):
    async def fake_chat(messages, model=None, business_context=None):
        assert messages[-1]["content"] == "Hello SAFWAN"
        return "Hello from SAFWAN AI", "qwen2.5:7b"

    monkeypatch.setattr(api_v1, "chat", fake_chat)
    admin = {"Authorization": "Bearer test-admin-secret"}
    key = client.post("/api/keys", headers=admin, json={"name": "Chat test"}).json()["key"]
    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer " + key},
        json={"model": "safwan-local", "messages": [{"role": "user", "content": "Hello SAFWAN"}]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "chat.completion"
    assert data["choices"][0]["message"]["content"] == "Hello from SAFWAN AI"
    assert data["safwan"]["runtime_model"] == "qwen2.5:7b"


def test_api_key_admin_requires_master_token(client):
    assert client.post("/api/keys", json={"name": "No auth"}).status_code == 401
    assert client.get("/api/keys").status_code == 401
