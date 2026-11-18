import os
from dotenv import load_dotenv

load_dotenv()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
SAFWAN_APP_TOKEN = os.getenv("SAFWAN_APP_TOKEN", "").strip()
SAFWAN_API_RPM = max(1, int(os.getenv("SAFWAN_API_RPM", "60")))
SAFWAN_EMBEDDING_MODEL = os.getenv("SAFWAN_EMBEDDING_MODEL", "nomic-embed-text")
DATABASE_PATH = os.getenv("DATABASE_PATH", "data/safwan_ai.sqlite3")

SYSTEM_PROMPT = """You are SAFWAN AI, a careful business assistant.
Support Bangla, Banglish and English; reply in the user's language.
Help with business planning, customer communication, operations, sales summaries,
inventory reasoning, quotations and draft documents.
Never invent business figures, legal requirements, sources or completed actions.
Label assumptions and estimates. Ask for missing facts when they materially matter.
For legal, tax, financial, medical or safety decisions, recommend qualified review.
"""
SAFWAN_MEMORY_ENABLED = os.getenv("SAFWAN_MEMORY_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
