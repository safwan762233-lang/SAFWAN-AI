import hashlib
import secrets
import time
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .config import OLLAMA_MODEL, SAFWAN_APP_TOKEN
from .db import connect
from .business import get_business_context_data
from .ollama import chat, OllamaError

router = APIRouter(tags=["SAFWAN API v1"])


def _digest(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _admin_guard(authorization: Optional[str]) -> None:
    if not SAFWAN_APP_TOKEN:
        raise HTTPException(503, "API key administration is disabled: set SAFWAN_APP_TOKEN first")
    if authorization != f"Bearer {SAFWAN_APP_TOKEN}":
        raise HTTPException(401, "Invalid admin token")


def _api_key_guard(authorization: Optional[str]) -> int:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "A SAFWAN API key is required")
    raw_key = authorization[7:].strip()
    if not raw_key.startswith("safwan_"):
        raise HTTPException(401, "Invalid SAFWAN API key")
    digest = _digest(raw_key)
    with connect() as con:
        row = con.execute(
            "SELECT id FROM api_keys WHERE key_hash=? AND revoked_at IS NULL",
            (digest,),
        ).fetchone()
    if not row:
        raise HTTPException(401, "Invalid or revoked SAFWAN API key")
    return int(row["id"])


class APIKeyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)


class ChatCompletionInput(BaseModel):
    model: str = Field(default="safwan-local", max_length=80)
    messages: list[ChatMessage] = Field(min_length=1, max_length=100)


@router.post("/api/keys", tags=["API key administration"])
def create_api_key(body: APIKeyCreate, authorization: Optional[str] = Header(default=None)):
    _admin_guard(authorization)
    raw_key = "safwan_" + secrets.token_urlsafe(32)
    prefix = raw_key[:16]
    with connect() as con:
        cur = con.execute(
            "INSERT INTO api_keys(name,key_prefix,key_hash) VALUES(?,?,?)",
            (body.name.strip(), prefix, _digest(raw_key)),
        )
        key_id = cur.lastrowid
    return {
        "id": key_id,
        "name": body.name.strip(),
        "key": raw_key,
        "key_prefix": prefix,
        "warning": "Copy this key now. It cannot be displayed again.",
    }


@router.get("/api/keys", tags=["API key administration"])
def list_api_keys(authorization: Optional[str] = Header(default=None)):
    _admin_guard(authorization)
    with connect() as con:
        rows = con.execute(
            "SELECT id,name,key_prefix,created_at,revoked_at FROM api_keys ORDER BY id DESC"
        ).fetchall()
    return [dict(row) for row in rows]


@router.delete("/api/keys/{key_id}", tags=["API key administration"])
def revoke_api_key(key_id: int, authorization: Optional[str] = Header(default=None)):
    _admin_guard(authorization)
    with connect() as con:
        cur = con.execute(
            "UPDATE api_keys SET revoked_at=CURRENT_TIMESTAMP WHERE id=? AND revoked_at IS NULL",
            (key_id,),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Active API key not found")
    return {"id": key_id, "status": "revoked"}


@router.get("/v1/models")
def v1_models(authorization: Optional[str] = Header(default=None)):
    _api_key_guard(authorization)
    return {
        "object": "list",
        "data": [{
            "id": "safwan-local",
            "object": "model",
            "created": int(time.time()),
            "owned_by": "safwan-ai",
        }],
    }


@router.post("/v1/chat/completions")
async def chat_completions(
    body: ChatCompletionInput,
    authorization: Optional[str] = Header(default=None),
):
    _api_key_guard(authorization)
    if body.model not in ("safwan-local", OLLAMA_MODEL):
        raise HTTPException(404, f"Model '{body.model}' is not available through SAFWAN AI")
    messages = [{"role": item.role, "content": item.content} for item in body.messages]
    try:
        answer, used_model = await chat(messages, OLLAMA_MODEL, get_business_context_data())
    except OllamaError as exc:
        raise HTTPException(503, str(exc))
    return {
        "id": "chatcmpl-" + secrets.token_hex(12),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "safwan-local",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": answer},
            "finish_reason": "stop",
        }],
        "safwan": {"runtime_model": used_model},
    }
