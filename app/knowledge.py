import io
import re
from typing import Optional

from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .config import SAFWAN_APP_TOKEN
from .db import connect

router = APIRouter(prefix="/api/knowledge", tags=["Local knowledge"])

MAX_FILE_BYTES = 10 * 1024 * 1024
ALLOWED_TYPES = {".txt", ".md", ".pdf", ".docx"}


def _admin_guard(authorization: Optional[str]) -> None:
    if not SAFWAN_APP_TOKEN:
        raise HTTPException(503, "Document management is disabled: set SAFWAN_APP_TOKEN first")
    if authorization != f"Bearer {SAFWAN_APP_TOKEN}":
        raise HTTPException(401, "Invalid admin token")


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


def search_knowledge(query: str, limit: int = 4):
    words = {w.lower() for w in re.findall(r"[\w\u0980-\u09ff]{2,}", query)}
    if not words:
        return []
    with connect() as con:
        rows = con.execute(
            """SELECT c.content, d.filename FROM knowledge_chunks c
               JOIN knowledge_documents d ON d.id=c.document_id"""
        ).fetchall()
    scored = []
    for row in rows:
        text = row["content"]
        terms = {w.lower() for w in re.findall(r"[\w\u0980-\u09ff]{2,}", text)}
        score = len(words & terms)
        if score:
            scored.append((score, row["filename"], text))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"filename": name, "content": content, "matched_terms": score}
            for score, name, content in scored[:limit]]


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
    with connect() as con:
        cur = con.execute(
            "INSERT INTO knowledge_documents(filename,file_type,char_count) VALUES(?,?,?)",
            (filename, suffix[1:], len(text)),
        )
        document_id = cur.lastrowid
        con.executemany(
            "INSERT INTO knowledge_chunks(document_id,chunk_index,content) VALUES(?,?,?)",
            [(document_id, i, part) for i, part in enumerate(parts)],
        )
    return {"id": document_id, "filename": filename, "characters": len(text), "chunks": len(parts)}


@router.get("/documents")
def list_documents(authorization: Optional[str] = Header(default=None)):
    _admin_guard(authorization)
    with connect() as con:
        rows = con.execute(
            """SELECT d.id,d.filename,d.file_type,d.char_count,d.created_at,
                      COUNT(c.id) AS chunks
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


@router.post("/search")
def search_documents(
    body: KnowledgeSearch,
    authorization: Optional[str] = Header(default=None),
):
    _admin_guard(authorization)
    return {"results": search_knowledge(body.query)}
