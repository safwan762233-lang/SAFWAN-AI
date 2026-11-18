"""Transparent heuristic evaluation and local model comparison."""
import time
import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from .config import OLLAMA_BASE_URL, SAFWAN_APP_TOKEN
from .db import connect
from .auth_core import require_admin
from .ollama import list_models, OllamaError

router = APIRouter()

class EvaluationInput(BaseModel):
    prompt: str = Field(min_length=1, max_length=12000)
    answer: str = Field(min_length=1, max_length=30000)
    expected_answer: str | None = Field(default=None, max_length=12000)
    model: str = Field(default="manual", max_length=120)

class CompareInput(BaseModel):
    prompt: str = Field(min_length=1, max_length=12000)
    models: list[str] = Field(default_factory=list, max_length=4)

def _authorize(authorization):
    require_admin(authorization, legacy_token=SAFWAN_APP_TOKEN)

def score_answer(prompt, answer, expected_answer=None):
    """Heuristics only: useful signals, not a truth or factuality guarantee."""
    words = answer.split()
    length_score = min(100, round(len(words) / 80 * 100))
    prompt_terms = {w.lower().strip(".,!?;:()[]{}") for w in prompt.split() if len(w) > 3}
    answer_terms = {w.lower().strip(".,!?;:()[]{}") for w in words if len(w) > 3}
    relevance = round(100 * len(prompt_terms & answer_terms) / max(1, len(prompt_terms)))
    structure = 100 if any(mark in answer for mark in ("\n-", "\n1.", "\n#", ":")) else 60
    clarity = 100 if len(words) >= 8 and len(answer) <= 12000 else 50
    expected_overlap = None
    if expected_answer:
        expected_terms = {w.lower().strip(".,!?;:()[]{}") for w in expected_answer.split() if len(w) > 3}
        expected_overlap = round(100 * len(expected_terms & answer_terms) / max(1, len(expected_terms)))
    overall = round((length_score * 0.15) + (relevance * 0.4) + (structure * 0.15) + (clarity * 0.3))
    return {
        "overall_score": overall,
        "signals": {"length": length_score, "prompt_relevance": relevance, "structure": structure, "clarity": clarity},
        "expected_answer_overlap": expected_overlap,
        "warning": "Heuristic indicators only. Scores do not verify factual correctness, safety, or completeness.",
    }

def save_evaluation(prompt, model, score, duration_ms, kind):
    import json
    with connect() as con:
        cur = con.execute(
            """INSERT INTO evaluations(prompt, model, overall_score, duration_ms, evaluation_type, score_json)
               VALUES(?,?,?,?,?,?)""",
            (prompt[:1200], model, score["overall_score"], max(0, int(duration_ms)), kind,
             json.dumps(score, ensure_ascii=False)),
        )
        return cur.lastrowid

@router.post("/api/evaluations/score")
def score_endpoint(body: EvaluationInput, authorization: str | None = Header(default=None)):
    _authorize(authorization)
    score = score_answer(body.prompt, body.answer, body.expected_answer)
    evaluation_id = save_evaluation(body.prompt, body.model, score, 0, "manual")
    return {"id": evaluation_id, "model": body.model, **score}

@router.post("/api/evaluations/compare")
async def compare_endpoint(body: CompareInput, authorization: str | None = Header(default=None)):
    _authorize(authorization)
    try:
        installed = await list_models()
    except OllamaError as exc:
        raise HTTPException(503, str(exc))
    selected = body.models or installed[:3]
    if not selected or len(selected) > 4:
        raise HTTPException(400, "Choose between 1 and 4 installed models")
    if any(model not in installed for model in selected):
        raise HTTPException(400, "Every requested model must be installed in Ollama")
    results = []
    for model in selected:
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(180, connect=8)) as client:
                response = await client.post(
                    f"{OLLAMA_BASE_URL}/api/chat",
                    json={"model": model, "messages": [
                        {"role": "system", "content": "Answer the user clearly. Do not invent facts."},
                        {"role": "user", "content": body.prompt},
                    ], "stream": False, "options": {"temperature": 0.35}},
                )
                response.raise_for_status()
                answer = response.json()["message"]["content"]
            duration = round((time.perf_counter() - started) * 1000)
            score = score_answer(body.prompt, answer)
            evaluation_id = save_evaluation(body.prompt, model, score, duration, "model_comparison")
            results.append({"id": evaluation_id, "model": model, "answer": answer,
                            "duration_ms": duration, **score})
        except Exception as exc:
            duration = round((time.perf_counter() - started) * 1000)
            results.append({"model": model, "error": str(exc), "duration_ms": duration})
    return {"results": results, "note": "Scores are heuristic indicators, not a factual accuracy benchmark."}

@router.get("/api/evaluations")
def evaluation_history(limit: int = 50, authorization: str | None = Header(default=None)):
    _authorize(authorization)
    limit = max(1, min(limit, 200))
    with connect() as con:
        rows = con.execute(
            """SELECT id, prompt, model, overall_score, duration_ms, evaluation_type, created_at
               FROM evaluations ORDER BY id DESC LIMIT ?""", (limit,)
        ).fetchall()
        summary = con.execute(
            """SELECT COUNT(*) AS evaluations, ROUND(AVG(overall_score),1) AS average_score,
                      ROUND(AVG(duration_ms)) AS average_duration_ms
               FROM evaluations"""
        ).fetchone()
    return {"summary": dict(summary), "items": [dict(row) for row in rows]}


@router.get("/api/deployment/status")
async def deployment_status(authorization: str | None = Header(default=None)):
    """Admin-only view of installed runtime models and recorded evaluation signals."""
    _authorize(authorization)
    try:
        installed = await list_models()
    except OllamaError as exc:
        raise HTTPException(503, str(exc))
    with connect() as con:
        rows = con.execute(
            """SELECT model, COUNT(*) AS evaluations,
                      ROUND(AVG(overall_score), 1) AS average_score,
                      ROUND(AVG(duration_ms)) AS average_duration_ms,
                      MAX(created_at) AS last_evaluated_at
               FROM evaluations GROUP BY model ORDER BY evaluations DESC"""
        ).fetchall()
        recent = con.execute(
            """SELECT id, model, overall_score, duration_ms, evaluation_type, created_at
               FROM evaluations ORDER BY id DESC LIMIT 10"""
        ).fetchall()
    return {
        "runtime": "connected",
        "installed_models": installed,
        "evaluation_summary_by_model": [dict(row) for row in rows],
        "recent_evaluations": [dict(row) for row in recent],
        "note": "Evaluation scores are heuristic signals only; they do not prove factual accuracy, safety, or model quality.",
    }
