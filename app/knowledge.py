import io
import json
import math
import re
from typing import Optional

import httpx
from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .config import OLLAMA_BASE_URL, SAFWAN_APP_TOKEN, SAFWAN_EMBEDDING_MODEL
from .db import connect
from .auth_core import require_admin

router = APIRouter(prefix="/api/knowledge", tags=["Local knowledge"])

MAX_FILE_BYTES = 10 * 1024 * 1024
ALLOWED_TYPES = {".txt", ".md", ".pdf", ".docx"}


def _admin_guard(authorization: Optional[str]) -> None:
    require_admin(authorization, "Invalid admin token", SAFWAN_APP_TOKEN)


def _extract_text(filename: str, raw: bytes) -> str:
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    try:
        if suffix in (".txt", ".md"):
            return raw.decode("utf-8-sig")
        if suffix == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        if suffix == ".docx":
            from docx import Document
            document = Document(io.BytesIO(raw))
            paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
            for table in document.tables:
                for row in table.rows:
                    paragraphs.append(" | ".join(cell.text for cell in row.cells))
            return "\n".join(paragraphs)
    except Exception as exc:
        raise HTTPException(400, f"Could not read document: {exc}") from exc
    raise HTTPException(415, "Supported formats: TXT, MD, PDF, DOCX")


def _chunks(text: str, size: int = 1000, overlap: int = 150):
    cleaned = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not cleaned:
        return []
    result = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + size)
        if end < len(cleaned):
            boundary = cleaned.rfind(" ", start + size // 2, end)
            if boundary > start:
                end = boundary
        part = cleaned[start:end].strip()
        if part:
            result.append(part)
        if end >= len(cleaned):
            break
        start = max(start + 1, end - overlap)
    return result


def create_embeddings(texts):
    """Create local vectors through the Ollama /api/embed endpoint."""
    if not texts:
        return []
    try:
        response = httpx.post(
            f"{OLLAMA_BASE_URL}/api/embed",
            json={"model": SAFWAN_EMBEDDING_MODEL, "input": texts},
            timeout=httpx.Timeout(30, connect=3),
        )
        response.raise_for_status()
        vectors = response.json().get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise ValueError("Ollama returned an unexpected embeddings response")
        cleaned = []
        for vector in vectors:
            if not isinstance(vector, list) or not vector:
                raise ValueError("Ollama returned an empty embedding")
            values = [float(value) for value in vector]
            if not all(math.isfinite(value) for value in values):
                raise ValueError("Embedding contains invalid numbers")
            cleaned.append(values)
        return cleaned
    except Exception as exc:
        raise RuntimeError(
            f"Local embedding model '{SAFWAN_EMBEDDING_MODEL}' is unavailable. "
            f"Run 'ollama pull {SAFWAN_EMBEDDING_MODEL}' and check Ollama. Details: {exc}"
        ) from exc


def _cosine(left, right):
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def _keyword_scores(query, rows):
    words = {w.lower() for w in re.findall(r"[\w\u0980-\u09ff]{2,}", query)}
    scores = []
    for row in rows:
        terms = {w.lower() for w in re.findall(r"[\w\u0980-\u09ff]{2,}", row["content"])}
        scores.append(len(words & terms) / max(1, len(words)))
    return scores


def search_knowledge(query: str, limit: int = 4):
    with connect() as con:
        rows = con.execute(
            """SELECT c.content,c.embedding_json,d.filename
               FROM knowledge_chunks c
               JOIN knowledge_documents d ON d.id=c.document_id"""
        ).fetchall()
    if not rows:
        return []
    keyword_scores = _keyword_scores(query, rows)
    query_vector = None
    try:
        query_vector = create_embeddings([query])[0]
    except RuntimeError:
        pass

    scored = []
    for index, row in enumerate(rows):
        keyword_score = keyword_scores[index]
        vector_score = 0.0
        if query_vector and row["embedding_json"]:
            try:
                vector_score = max(0.0, _cosine(query_vector, json.loads(row["embedding_json"])))
            except (ValueError, TypeError, json.JSONDecodeError):
                vector_score = 0.0
        if query_vector:
            score = 0.80 * vector_score + 0.20 * keyword_score
            method = "hybrid" if row["embedding_json"] else "keyword"
        else:
            score = keyword_score
            method = "keyword"
        if score > 0:
            scored.append((score, row["filename"], row["content"], method, vector_score, keyword_score))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {"filename": name, "content": content, "score": round(score, 4),
         "method": method, "semantic_score": round(semantic, 4),
         "keyword_score": round(keyword, 4)}
        for score, name, content, method, semantic, keyword in scored[:limit]
    ]


class KnowledgeSearch(BaseModel):
    query: str = Field(min_length=2, max_length=2000)


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(default=None),
):
    _admin_guard(authorization)
    filename = (file.filename or "document").replace("\\", "/").split("/")[-1]
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix not in ALLOWED_TYPES:
        raise HTTPException(415, "Supported formats: TXT, MD, PDF, DOCX")
    raw = await file.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise HTTPException(413, "Maximum upload size is 10 MB")
    text = _extract_text(filename, raw)
    parts = _chunks(text)
    if not parts:
        raise HTTPException(422, "No readable text found in this document")
    embeddings = None
    embedding_error = None
    try:
        embeddings = create_embeddings(parts)
    except RuntimeError as exc:
        embedding_error = str(exc)
    with connect() as con:
        cur = con.execute(
            "INSERT INTO knowledge_documents(filename,file_type,char_count) VALUES(?,?,?)",
            (filename, suffix[1:], len(text)),
        )
        document_id = cur.lastrowid
        con.executemany(
            """INSERT INTO knowledge_chunks(document_id,chunk_index,content,embedding_json)
               VALUES(?,?,?,?)""",
            [(document_id, i, part, json.dumps(embeddings[i]) if embeddings else None)
             for i, part in enumerate(parts)],
        )
    return {"id": document_id, "filename": filename, "characters": len(text),
            "chunks": len(parts), "embedded": bool(embeddings),
            "embedding_model": SAFWAN_EMBEDDING_MODEL,
            "embedding_warning": embedding_error}


@router.get("/documents")
def list_documents(authorization: Optional[str] = Header(default=None)):
    _admin_guard(authorization)
    with connect() as con:
        rows = con.execute(
            """SELECT d.id,d.filename,d.file_type,d.char_count,d.created_at,
                      COUNT(c.id) AS chunks,
                      SUM(CASE WHEN c.embedding_json IS NOT NULL THEN 1 ELSE 0 END) AS embedded_chunks
               FROM knowledge_documents d LEFT JOIN knowledge_chunks c ON c.document_id=d.id
               GROUP BY d.id ORDER BY d.id DESC"""
        ).fetchall()
    return [dict(row) for row in rows]


@router.delete("/documents/{document_id}")
def delete_document(document_id: int, authorization: Optional[str] = Header(default=None)):
    _admin_guard(authorization)
    with connect() as con:
        cur = con.execute("DELETE FROM knowledge_documents WHERE id=?", (document_id,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Document not found")
    return {"id": document_id, "status": "deleted"}


@router.post("/reindex")
def reindex_documents(authorization: Optional[str] = Header(default=None)):
    _admin_guard(authorization)
    with connect() as con:
        rows = con.execute(
            "SELECT id,content FROM knowledge_chunks WHERE embedding_json IS NULL ORDER BY id"
        ).fetchall()
    if not rows:
        return {"status": "complete", "indexed": 0, "remaining": 0}
    indexed = 0
    batch_size = 32
    try:
        for offset in range(0, len(rows), batch_size):
            batch = rows[offset:offset + batch_size]
            vectors = create_embeddings([row["content"] for row in batch])
            with connect() as con:
                con.executemany(
                    "UPDATE knowledge_chunks SET embedding_json=? WHERE id=?",
                    [(json.dumps(vector), row["id"]) for row, vector in zip(batch, vectors)],
                )
            indexed += len(batch)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    with connect() as con:
        remaining = con.execute(
            "SELECT COUNT(*) FROM knowledge_chunks WHERE embedding_json IS NULL"
        ).fetchone()[0]
    return {"status": "complete" if remaining == 0 else "partial",
            "indexed": indexed, "remaining": remaining,
            "embedding_model": SAFWAN_EMBEDDING_MODEL}


@router.post("/search")
def search_documents(
    body: KnowledgeSearch,
    authorization: Optional[str] = Header(default=None),
):
    _admin_guard(authorization)
    results = search_knowledge(body.query)
    mode = "hybrid" if any(item["method"] == "hybrid" for item in results) else "keyword"
    return {"mode": mode, "embedding_model": SAFWAN_EMBEDDING_MODEL, "results": results}
