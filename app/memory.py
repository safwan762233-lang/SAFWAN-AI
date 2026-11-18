import json
import re
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .config import SAFWAN_APP_TOKEN, SAFWAN_MEMORY_ENABLED
from .db import connect
from .knowledge import create_embeddings, _cosine, _keyword_scores

router = APIRouter(prefix="/api/memory", tags=["Long-term memory"])


def _guard(authorization: Optional[str]) -> None:
    if not SAFWAN_APP_TOKEN:
        raise HTTPException(503, "Memory management is disabled: set SAFWAN_APP_TOKEN first")
    if authorization != f"Bearer {SAFWAN_APP_TOKEN}":
        raise HTTPException(401, "Invalid admin token")


def remember(content: str, source_conversation_id: Optional[int] = None,
             category: str = "conversation") -> Optional[int]:
    """Store a useful user statement locally. Skip short messages and likely secrets."""
    clean = " ".join((content or "").split()).strip()
    if not SAFWAN_MEMORY_ENABLED or len(clean) < 40:
        return None
    if re.search(r"(?i)(password|passwd|api[_ -]?key|secret|token)\s*[:=]", clean):
        return None
    vector = None
    try:
        vector = create_embeddings([clean])[0]
    except RuntimeError:
        pass
    with connect() as con:
        cur = con.execute(
            "INSERT INTO memory_items(content,category,source_conversation_id,embedding_json) VALUES(?,?,?,?)",
            (clean[:4000], category, source_conversation_id,
             json.dumps(vector) if vector else None),
        )
        return int(cur.lastrowid)


def search_memories(query: str, limit: int = 4):
    with connect() as con:
        rows = con.execute(
            "SELECT id,content,category,embedding_json,created_at FROM memory_items ORDER BY id DESC LIMIT 1000"
        ).fetchall()
    if not rows:
        return []
    try:
        query_vector = create_embeddings([query])[0]
    except RuntimeError:
        query_vector = None
    keyword_scores = _keyword_scores(query, rows)
    scored = []
    for i, row in enumerate(rows):
        semantic = 0.0
        if query_vector and row["embedding_json"]:
            try:
                semantic = max(0.0, _cosine(query_vector, json.loads(row["embedding_json"])))
            except (ValueError, TypeError, json.JSONDecodeError):
                pass
        keyword = keyword_scores[i]
        score = 0.8 * semantic + 0.2 * keyword if query_vector else keyword
        if score > 0:
            scored.append((score, row, semantic, keyword))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {"id": row["id"], "content": row["content"], "category": row["category"],
         "created_at": row["created_at"], "score": round(score, 4)}
        for score, row, _, _ in scored[:limit]
    ]


class MemoryCreate(BaseModel):
    content: str = Field(min_length=5, max_length=4000)
    category: str = Field(default="fact", min_length=2, max_length=40)


class MemorySearch(BaseModel):
    query: str = Field(min_length=2, max_length=2000)


@router.get("")
def list_memories(authorization: Optional[str] = Header(default=None)):
    _guard(authorization)
    with connect() as con:
        rows = con.execute(
            "SELECT id,content,category,created_at,updated_at FROM memory_items ORDER BY id DESC LIMIT 500"
        ).fetchall()
    return {"enabled": SAFWAN_MEMORY_ENABLED, "count": len(rows), "items": [dict(row) for row in rows]}


@router.post("")
def add_memory(body: MemoryCreate, authorization: Optional[str] = Header(default=None)):
    _guard(authorization)
    memory_id = remember(body.content, category=body.category)
    if memory_id is None:
        raise HTTPException(503, "Memory is disabled or the content was not eligible to save")
    return {"id": memory_id, "status": "saved"}


@router.post("/search")
def memory_search(body: MemorySearch, authorization: Optional[str] = Header(default=None)):
    _guard(authorization)
    return {"results": search_memories(body.query)}


@router.delete("/{memory_id}")
def delete_memory(memory_id: int, authorization: Optional[str] = Header(default=None)):
    _guard(authorization)
    with connect() as con:
        cur = con.execute("DELETE FROM memory_items WHERE id=?", (memory_id,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Memory not found")
    return {"id": memory_id, "status": "deleted"}


@router.delete("")
def clear_memories(authorization: Optional[str] = Header(default=None)):
    _guard(authorization)
    with connect() as con:
        cur = con.execute("DELETE FROM memory_items")
        count = cur.rowcount
    return {"deleted": count, "status": "cleared"}
