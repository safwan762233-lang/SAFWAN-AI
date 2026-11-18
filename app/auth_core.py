import hashlib
from typing import Optional
from fastapi import HTTPException
from .config import SAFWAN_APP_TOKEN
from .db import connect


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def is_admin_authorized(authorization: Optional[str]) -> bool:
    if not authorization or not authorization.startswith("Bearer "):
        return False
    token = authorization[7:].strip()
    if not token:
        return False
    if SAFWAN_APP_TOKEN and token == SAFWAN_APP_TOKEN:
        return True
    digest = token_digest(token)
    with connect() as con:
        row = con.execute(
            """SELECT id FROM auth_sessions
               WHERE token_hash=? AND revoked_at IS NULL
                 AND expires_at > CURRENT_TIMESTAMP""",
            (digest,),
        ).fetchone()
    return row is not None


def require_admin(authorization: Optional[str], message: str = "Unauthorized") -> None:
    if not is_admin_authorized(authorization):
        raise HTTPException(401, message)
