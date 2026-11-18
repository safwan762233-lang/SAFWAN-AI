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
