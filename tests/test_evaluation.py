from fastapi.testclient import TestClient
import app.db as db
import app.evaluation as evaluation
from app.main import app


def test_score_answer_returns_bounded_heuristic_signals():
    result = evaluation.score_answer("Explain Python API design", "Python API design uses routes and clear validation.")
    assert 0 <= result["overall_score"] <= 100
    assert result["signals"]["prompt_relevance"] > 0
    assert "do not verify factual correctness" in result["warning"]


def test_evaluation_endpoints_require_master_token(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_PATH", str(tmp_path / "evaluation.sqlite3"))
    monkeypatch.setattr(evaluation, "SAFWAN_APP_TOKEN", "admin-secret")
    db.init_db()
    client = TestClient(app)
    assert client.get("/api/evaluations").status_code == 401
    response = client.post("/api/evaluations/score", json={
        "prompt": "Explain Python API", "answer": "Python APIs expose routes and validate input."
    })
    assert response.status_code == 401


def test_manual_evaluation_saved_and_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_PATH", str(tmp_path / "evaluation.sqlite3"))
    monkeypatch.setattr(evaluation, "SAFWAN_APP_TOKEN", "admin-secret")
    db.init_db()
    client = TestClient(app)
    headers = {"Authorization": "Bearer admin-secret"}
    response = client.post("/api/evaluations/score", headers=headers, json={
        "prompt": "Explain Python API", "answer": "A Python API exposes routes and validates input.",
        "expected_answer": "Python API routes validate input", "model": "qwen2.5:7b"
    })
    assert response.status_code == 200
    assert response.json()["expected_answer_overlap"] is not None
    report = client.get("/api/evaluations", headers=headers)
    assert report.status_code == 200
    assert report.json()["summary"]["evaluations"] == 1
