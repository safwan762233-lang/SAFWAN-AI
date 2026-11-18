# SAFWAN AI

Local-first, self-hostable business AI workspace. No paid external AI API.

## MVP
- Responsive chat interface (Bangla, Banglish, English)
- Local/self-hosted Ollama inference
- SQLite conversation history
- Model status endpoint and conversation export
- Designed for local Windows use and self-hosted server deployment

This is an early MVP, not a ChatGPT-level foundation model. It runs an open-weight model downloaded and operated by you. Prompts are sent only to the Ollama server you configure.

## Windows 10 setup
1. Install Python 3.10+ and Ollama: https://ollama.com/download
2. Run `ollama pull qwen2.5:7b` in Command Prompt. If memory is insufficient, try `ollama pull qwen2.5:3b` and set that model in `.env`.
3. Extract the source and open Command Prompt in the project folder.
4. Run:
```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8000
```
5. Open http://127.0.0.1:8000

## Server deployment
Set `OLLAMA_BASE_URL` to the private address of an Ollama server you control. Put any remotely accessible deployment behind HTTPS, authentication, and a firewall/reverse proxy. Do not expose the development server directly to the public internet.

## Environment
- `OLLAMA_BASE_URL` (default `http://127.0.0.1:11434`)
- `OLLAMA_MODEL` (default `qwen2.5:7b`)
- `SAFWAN_APP_TOKEN` (optional API bearer token)
- `DATABASE_PATH` (default local SQLite database)

## Not implemented yet
Multi-user accounts, billing, roles, audit logs, document RAG, web research with citations, voice, agent actions, and enterprise integrations are roadmap items, not working features.

MIT license for this starter application. Model weights have separate licenses; verify commercial terms before selling a product that bundles or redistributes a model.


## Business management API (v0.2)
Working backend endpoints:
- Dashboard metrics: product count, inventory value, low-stock count, customer count, confirmed sales.
- Customer create/list.
- Product create/list with unique SKU and non-negative price/stock validation.
- Draft sales with line-item totals.
- Explicit sale confirmation re-checks stock and deducts inventory.
- Sales list.

Interactive API documentation: `/docs`.
- `GET /api/business/dashboard`
- `GET/POST /api/business/customers`
- `GET/POST /api/business/products`
- `GET/POST /api/business/sales`
- `POST /api/business/sales/{sale_id}/confirm`

All records are stored in local SQLite. Sales remain drafts until explicitly confirmed; creating a draft does not deduct stock.

## Security and deployment warning
The default setup is for local development only. Keep it bound to `127.0.0.1`. The optional bearer token is not a complete multi-user authentication system. Do not expose this server to the public internet yet. Public deployment requires proper login/session security, HTTPS, CSRF protection, rate limiting, tenant isolation, backups, audit logs, and secrets management.

## Not implemented yet
Multi-user accounts, billing, roles, audit logs, document RAG, grounded web research with citations, voice, agent actions, native Android app, and enterprise integrations remain roadmap items, not working features.


## SAFWAN AI API v1 (first-party API gateway)

SAFWAN AI now exposes its own API namespace. Client applications use SAFWAN-issued API keys; requests are processed by the self-hosted Ollama model configured by the operator. No paid external AI API is used.

### Enable API key administration

Set a strong, private `SAFWAN_APP_TOKEN` in `.env` before starting the server. This master token is only for creating, listing, and revoking API keys; never give it to client applications.

### API key administration

Use the master token as a Bearer token:

- `POST /api/keys` with JSON `{"name":"My integration"}` creates a key.
- `GET /api/keys` lists key names, prefixes, and status (never the full secret).
- `DELETE /api/keys/{id}` revokes a key.

The full API key is returned only once when created. Store it securely. The database stores a SHA-256 hash, not the raw key.

### Client API

- `GET /v1/models` lists the public model alias `safwan-local`.
- `POST /v1/chat/completions` accepts an OpenAI-style JSON request with `model` and `messages` (currently `user` and `assistant` roles; non-streaming only).

Example request:

```bash
curl http://127.0.0.1:8000/v1/chat/completions \\
  -H "Authorization: Bearer safwan_YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"model":"safwan-local","messages":[{"role":"user","content":"Summarize my business priorities."}]}'
```

The SAFWAN API is an application API and model gateway, not a newly trained foundation model. At this stage inference still runs on the operator's configured local/self-hosted Ollama model. Streaming, usage billing, tenant isolation, and production-grade account management are not implemented yet. Keep the service private until the security roadmap is completed.

### Usage tracking and rate limiting

- `SAFWAN_API_RPM` sets the per-key request limit per rolling 60-second window (default: `60`, minimum: `1`).
- Each authenticated request to `/v1/models` and `/v1/chat/completions` is recorded in SQLite.
- Excess requests receive HTTP `429` with `Retry-After: 60`.
- `GET /api/usage?hours=24` returns total requests, per-key request counts, rate-limited counts, and recent request records. It requires the master `SAFWAN_APP_TOKEN`.
- This is an initial single-instance rate limiter backed by SQLite. For multiple server instances or public production use, move counters to a shared atomic store such as Redis and add stronger operational controls.


## API management dashboard

The web workspace includes an API Management section. Enter the `SAFWAN_APP_TOKEN` master token to create, list, rename, and revoke API keys and review usage reports. The token is held in page memory only and is cleared when you disconnect or reload the page; do not use this dashboard on an untrusted computer. A newly created API key is displayed once—copy it immediately and store it securely.

Administration endpoints:
- `PATCH /api/keys/{id}` renames an active API key.
- `GET /api/usage?hours=24` shows per-key request totals and recent events.


## Local document knowledge (basic retrieval)

The Knowledge Base section supports private uploads of TXT, Markdown, PDF, and DOCX files (10 MB maximum per file). Text is extracted locally, split into overlapping chunks, and stored in SQLite. SAFWAN AI retrieves matching chunks for a user's question and includes them as reference context in both the web chat and the first-party API chat.

- `POST /api/knowledge/upload` — upload one document (master token required).
- `GET /api/knowledge/documents` — list indexed documents.
- `POST /api/knowledge/search` — test keyword retrieval.
- `DELETE /api/knowledge/documents/{id}` — delete a document and its chunks.

This first version uses local keyword-overlap retrieval, not vector embeddings or semantic search. Scanned/image-only PDFs may produce no extractable text; OCR is not included. Files are stored as extracted text in SQLite rather than retained as original file binaries. Do not upload sensitive documents until the deployment has proper user authentication, access controls, encryption, and backups.


## Phase 5: Local semantic knowledge search

The Knowledge Base supports local semantic + keyword hybrid retrieval using Ollama embeddings. No hosted embedding API is used.

1. Install an embedding model locally: `ollama pull nomic-embed-text`
2. Set `SAFWAN_EMBEDDING_MODEL=nomic-embed-text` in `.env` (or choose another Ollama embedding model).
3. Restart SAFWAN AI.
4. Upload documents as usual. Upload continues if the embedding model is unavailable, but those chunks use keyword search until indexed.
5. Use the Knowledge Base search UI or ask questions in chat. Search combines cosine similarity from local embeddings with keyword overlap when vectors are available.

Admin endpoint: `POST /api/knowledge/reindex` creates embeddings for older chunks that do not have them. Document listing reports `embedded_chunks`. The database stores vectors as JSON in SQLite and ranks them in Python; this is a lightweight MVP, not a dedicated vector database. If Ollama or the embedding model is unavailable, search falls back to keyword matching. Scanned PDFs still require OCR, which is not included.


## Phase 6: Local long-term memory

SAFWAN AI now has an initial single-workspace memory system stored in SQLite. It can save longer user messages from web chat and first-party API chat, retrieve related memories with local Ollama embeddings plus keyword fallback, and let the administrator add, inspect, search, and delete memories.

- `SAFWAN_MEMORY_ENABLED=true` enables automatic memory capture; set it to `false` to disable automatic capture.
- Automatic capture skips short messages and messages that appear to contain password, API-key, secret, or token assignments. This is a basic filter, not a guarantee that sensitive information will never be stored.
- Memory management endpoints require `SAFWAN_APP_TOKEN`: `GET/POST /api/memory`, `POST /api/memory/search`, `DELETE /api/memory/{id}`, and `DELETE /api/memory` to clear all.
- The Long-term Memory page lets an administrator review, add, search, and delete saved entries.
- Memory is currently shared across the entire installation. It is not multi-user or tenant-isolated; do not expose it publicly or use it for multiple customers until separate accounts and access controls are implemented.
- Memory retrieval uses the local embedding model configured by `SAFWAN_EMBEDDING_MODEL`; if embeddings are unavailable, keyword matching is used. The system does not yet perform LLM-based fact extraction or automatic summarization.


## Phase 7: SAFWAN Intelligence Engine

The web chat and first-party API now share `app/intelligence.py` to assemble a bounded context package containing the current business snapshot plus the most relevant local document and memory references.

- Retrieved references are filtered by a minimum relevance score and limited to three items per source.
- Each reference is capped at 1,800 characters to reduce irrelevant context and prompt size.
- The system prompt explicitly treats uploaded document excerpts and saved memories as untrusted data, not instructions.
- Conflicting references should be surfaced; the assistant is instructed not to claim independent verification or invent missing facts.
- The same context builder is used by `POST /api/chat` and `POST /v1/chat/completions`.

This is prompt/context orchestration, not a separate trained reasoning model, formal fact-checker, or guarantee against hallucinations and prompt injection. Search quality depends on the configured local embedding model and keyword fallback. Inference still runs on the configured Ollama model.
