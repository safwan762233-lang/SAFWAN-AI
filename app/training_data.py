"""Human-reviewed fine-tuning dataset preparation. Does not train models."""
import json
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from .config import SAFWAN_APP_TOKEN
from .db import connect

router = APIRouter()

def _authorize(authorization: Optional[str]):
    if not SAFWAN_APP_TOKEN:
        raise HTTPException(503, "Training data management is disabled: set SAFWAN_APP_TOKEN first")
    if authorization != f"Bearer {SAFWAN_APP_TOKEN}":
        raise HTTPException(401, "Unauthorized")

class ExampleInput(BaseModel):
    prompt: str = Field(min_length=1, max_length=12000)
    ideal_answer: str = Field(min_length=1, max_length=30000)
    category: str = Field(default="general", min_length=1, max_length=80)
    source: str = Field(default="manual", max_length=80)

class ExampleUpdate(BaseModel):
    prompt: str = Field(min_length=1, max_length=12000)
    ideal_answer: str = Field(min_length=1, max_length=30000)
    category: str = Field(default="general", min_length=1, max_length=80)

class StatusInput(BaseModel):
    status: str = Field(pattern="^(draft|approved|rejected)$")

@router.post("/api/training-data")
def create_example(body: ExampleInput, authorization: Optional[str] = Header(default=None)):
    _authorize(authorization)
    with connect() as con:
        cur = con.execute(
            "INSERT INTO training_examples(prompt,ideal_answer,category,source) VALUES(?,?,?,?)",
            (body.prompt.strip(), body.ideal_answer.strip(), body.category.strip(), body.source.strip()),
        )
        return {"id": cur.lastrowid, "status": "draft"}

@router.get("/api/training-data")
def list_examples(status: str = Query(default="all", pattern="^(all|draft|approved|rejected)$"),
                  limit: int = Query(default=100, ge=1, le=500),
                  authorization: Optional[str] = Header(default=None)):
    _authorize(authorization)
    where = "" if status == "all" else "WHERE status=?"
    params = () if status == "all" else (status,)
    with connect() as con:
        rows = con.execute(
            f"SELECT id,prompt,ideal_answer,category,status,source,created_at,updated_at FROM training_examples {where} ORDER BY id DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        counts = {row["status"]: row["count"] for row in con.execute(
            "SELECT status,COUNT(*) AS count FROM training_examples GROUP BY status"
        ).fetchall()}
    return {"counts": {key: counts.get(key, 0) for key in ("draft","approved","rejected")},
            "items": [dict(row) for row in rows]}

@router.patch("/api/training-data/{example_id}")
def update_example(example_id: int, body: ExampleUpdate, authorization: Optional[str] = Header(default=None)):
    _authorize(authorization)
    with connect() as con:
        cur = con.execute(
            "UPDATE training_examples SET prompt=?,ideal_answer=?,category=?,status='draft',updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (body.prompt.strip(), body.ideal_answer.strip(), body.category.strip(), example_id),
        )
        if not cur.rowcount:
            raise HTTPException(404, "Training example not found")
    return {"id": example_id, "status": "draft", "note": "Edited examples return to draft and require review again."}

@router.patch("/api/training-data/{example_id}/status")
def set_status(example_id: int, body: StatusInput, authorization: Optional[str] = Header(default=None)):
    _authorize(authorization)
    with connect() as con:
        cur = con.execute(
            "UPDATE training_examples SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (body.status, example_id),
        )
        if not cur.rowcount:
            raise HTTPException(404, "Training example not found")
    return {"id": example_id, "status": body.status}

@router.delete("/api/training-data/{example_id}")
def delete_example(example_id: int, authorization: Optional[str] = Header(default=None)):
    _authorize(authorization)
    with connect() as con:
        cur = con.execute("DELETE FROM training_examples WHERE id=?", (example_id,))
        if not cur.rowcount:
            raise HTTPException(404, "Training example not found")
    return {"deleted": True, "id": example_id}

@router.get("/api/training-data/export.jsonl", response_class=PlainTextResponse)
def export_approved(authorization: Optional[str] = Header(default=None)):
    _authorize(authorization)
    with connect() as con:
        rows = con.execute(
            "SELECT prompt,ideal_answer FROM training_examples WHERE status='approved' ORDER BY id"
        ).fetchall()
    lines = [json.dumps({"messages":[
        {"role":"user","content":row["prompt"]},
        {"role":"assistant","content":row["ideal_answer"]},
    ]}, ensure_ascii=False) for row in rows]
    return PlainTextResponse("\n".join(lines) + ("\n" if lines else ""),
                             media_type="application/x-ndjson",
                             headers={"Content-Disposition": 'attachment; filename="safwan-training-approved.jsonl"'})
