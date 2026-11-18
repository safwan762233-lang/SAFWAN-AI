"""Owner-account login and revocable bearer sessions.

This is a single-workspace admin login foundation, not tenant isolation.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .auth_core import is_admin_authorized, token_digest
from .config import SAFWAN_APP_TOKEN
from .db import connect

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
PBKDF2_ITERATIONS = 310_000
SESSION_HOURS = 12


def _password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"{salt.hex()}:{digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, expected = stored.split(":", 1)
        actual = _password_hash(password, bytes.fromhex(salt_hex)).split(":", 1)[1]
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


class SetupInput(BaseModel):
    username: str = Field(min_length=3, max_length=60, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=128)


class LoginInput(BaseModel):
    username: str = Field(min_length=3, max_length=60)
    password: str = Field(min_length=1, max_length=128)


@router.post("/setup")
def setup_owner(body: SetupInput, authorization: Optional[str] = Header(default=None)):
    if not SAFWAN_APP_TOKEN:
        raise HTTPException(503, "Set SAFWAN_APP_TOKEN before creating the owner account")
    if authorization != f"Bearer {SAFWAN_APP_TOKEN}":
        raise HTTPException(401, "Master token required")
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        count = con.execute("SELECT COUNT(*) FROM auth_users").fetchone()[0]
        if count:
            raise HTTPException(409, "An owner account already exists")
        cur = con.execute(
            "INSERT INTO auth_users(username,password_hash) VALUES(?,?)",
            (body.username.strip().lower(), _password_hash(body.password)),
        )
    return {"user_id": cur.lastrowid, "username": body.username.strip().lower(),
            "status": "created", "next_step": "Log in at /api/auth/login"}


@router.post("/login")
def login(body: LoginInput):
    username = body.username.strip().lower()
    with connect() as con:
        user = con.execute(
            "SELECT id,username,password_hash FROM auth_users WHERE username=? AND is_active=1",
            (username,),
        ).fetchone()
        if not user or not _verify_password(body.password, user["password_hash"]):
            raise HTTPException(401, "Invalid username or password")
        token = secrets.token_urlsafe(48)
        expires = (datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
        con.execute(
            "INSERT INTO auth_sessions(user_id,token_hash,expires_at) VALUES(?,?,?)",
            (user["id"], token_digest(token), expires),
        )
    return {"access_token": token, "token_type": "bearer", "expires_in": SESSION_HOURS * 3600,
            "username": user["username"]}


@router.get("/me")
def me(authorization: Optional[str] = Header(default=None)):
    if not is_admin_authorized(authorization):
        raise HTTPException(401, "Login required")
    token = authorization[7:].strip()
    if SAFWAN_APP_TOKEN and token == SAFWAN_APP_TOKEN:
        return {"authenticated": True, "auth_type": "master_token"}
    with connect() as con:
        row = con.execute(
            """SELECT u.id,u.username,s.expires_at FROM auth_sessions s
               JOIN auth_users u ON u.id=s.user_id
               WHERE s.token_hash=? AND s.revoked_at IS NULL
                 AND s.expires_at>CURRENT_TIMESTAMP""",
            (token_digest(token),),
        ).fetchone()
    if not row:
        raise HTTPException(401, "Session expired")
    return {"authenticated": True, "auth_type": "session", "user_id": row["id"],
            "username": row["username"], "expires_at": row["expires_at"]}


@router.post("/logout")
def logout(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Login required")
    token = authorization[7:].strip()
    if SAFWAN_APP_TOKEN and token == SAFWAN_APP_TOKEN:
        raise HTTPException(400, "Master token cannot be logged out; disconnect it in the browser")
    with connect() as con:
        cur = con.execute(
            "UPDATE auth_sessions SET revoked_at=CURRENT_TIMESTAMP WHERE token_hash=? AND revoked_at IS NULL",
            (token_digest(token),),
        )
    if not cur.rowcount:
        raise HTTPException(401, "Invalid or already revoked session")
    return {"status": "logged_out"}
