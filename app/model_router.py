"""Local Ollama model selection and lightweight performance tracking."""
import time
from .config import OLLAMA_MODEL, SAFWAN_CODING_MODEL, SAFWAN_REASONING_MODEL, SAFWAN_FALLBACK_MODEL
from .db import connect


def classify_task(messages):
    text = " ".join(str(m.get("content", "")) for m in (messages or []) if m.get("role") == "user").lower()
    coding = ("python", "javascript", "code", "debug", "program", "api", "sql", "html", "css", "কোড", "প্রোগ্রাম")
    reasoning = ("analyze", "analysis", "compare", "reason", "strategy", "plan", "ব্যাখ্যা", "বিশ্লেষণ", "তুলনা", "পরিকল্পনা")
    if any(term in text for term in coding):
        return "coding"
    if any(term in text for term in reasoning):
        return "reasoning"
    return "general"


def select_models(messages, available_models, requested_model=None):
    """Return ordered, installed model candidates; never invent an unavailable model."""
    available = set(available_models or [])
    task = classify_task(messages)
    preferred = {
        "coding": SAFWAN_CODING_MODEL,
        "reasoning": SAFWAN_REASONING_MODEL,
        "general": OLLAMA_MODEL,
    }[task]
    candidates = [requested_model, preferred, OLLAMA_MODEL, SAFWAN_FALLBACK_MODEL]
    ordered = []
    for candidate in candidates:
        if candidate and candidate in available and candidate not in ordered:
            ordered.append(candidate)
    if not ordered:
        raise ValueError("No usable model is installed in Ollama. Pull a model and check OLLAMA_MODEL.")
    return task, ordered


def record_model_usage(task, model, success, duration_ms):
    try:
        with connect() as con:
            con.execute(
                """INSERT INTO model_usage(task, model, success, duration_ms)
                   VALUES(?,?,?,?)""",
                (task, model, 1 if success else 0, max(0, int(duration_ms))),
            )
    except Exception:
        # Telemetry must never prevent an otherwise successful chat response.
        pass


def get_model_usage(limit=20):
    with connect() as con:
        totals = con.execute(
            """SELECT model, COUNT(*) AS requests,
                      SUM(success) AS successes,
                      ROUND(AVG(duration_ms)) AS avg_duration_ms
               FROM model_usage GROUP BY model ORDER BY requests DESC"""
        ).fetchall()
        recent = con.execute(
            """SELECT task, model, success, duration_ms, created_at
               FROM model_usage ORDER BY id DESC LIMIT ?""", (limit,)
        ).fetchall()
    return {"by_model": [dict(row) for row in totals], "recent": [dict(row) for row in recent]}
