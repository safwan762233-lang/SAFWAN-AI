from fastapi.testclient import TestClient

import app.auth as auth
import app.db as db
from app.main import app


def test_owner_setup_login_me_and_logout(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_PATH", str(tmp_path / "auth.sqlite3"))
    monkeypatch.setattr(auth, "SAFWAN_APP_TOKEN", "setup-master-token")
    db.init_db()
    client = TestClient(app)

    denied = client.post("/api/auth/setup", json={
        "username": "owner", "password": "strong-password-123"
    })
    assert denied.status_code == 401

    created = client.post("/api/auth/setup", headers={
        "Authorization": "Bearer setup-master-token"
    }, json={"username": "Owner", "password": "strong-password-123"})
    assert created.status_code == 200
    assert created.json()["username"] == "owner"

    duplicate = client.post("/api/auth/setup", headers={
        "Authorization": "Bearer setup-master-token"
    }, json={"username": "other", "password": "strong-password-456"})
    assert duplicate.status_code == 409

    bad_login = client.post("/api/auth/login", json={
        "username": "owner", "password": "wrong-password"
    })
    assert bad_login.status_code == 401

    login = client.post("/api/auth/login", json={
        "username": "OWNER", "password": "strong-password-123"
    })
    assert login.status_code == 200
    token = login.json()["access_token"]
    assert token
    headers = {"Authorization": f"Bearer {token}"}

    profile = client.get("/api/auth/me", headers=headers)
    assert profile.status_code == 200
    assert profile.json()["username"] == "owner"

    assert client.get("/api/business/dashboard", headers=headers).status_code == 200
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_login_requires_valid_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_PATH", str(tmp_path / "auth-empty.sqlite3"))
    db.init_db()
    client = TestClient(app)
    response = client.post("/api/auth/login", json={
        "username": "missing", "password": "nope"
    })
    assert response.status_code == 401
