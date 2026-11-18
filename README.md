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

## Phase 8: Local model router

SAFWAN can select among models already installed in the operator's Ollama instance. It classifies requests as coding, reasoning, or general work, then tries the matching configured model when available. If a preferred model is not installed, it falls back to the configured default; if an inference attempt fails, it tries the next installed candidate.

Optional environment settings (each value must exactly match a name shown by the ollama list command):
- SAFWAN_CODING_MODEL (defaults to OLLAMA_MODEL)
- SAFWAN_REASONING_MODEL (defaults to OLLAMA_MODEL)
- SAFWAN_FALLBACK_MODEL (optional; blank by default)

The router records task, model, success/failure, and duration in the local SQLite database. The authenticated GET /api/model-router/status endpoint reports installed models, routing preferences, and usage summaries. Model preferences do not download models automatically. Install any model yourself with Ollama and confirm its exact tag with ollama list.

This is lightweight keyword-based routing, not an intelligent benchmark or a guarantee that a specialist model is better. The default model remains the safe fallback. All inference stays on the configured Ollama server; SAFWAN still does not contain a newly trained foundation model.


## Phase 9: Evaluation engine

- POST /api/evaluations/score evaluates a supplied prompt and answer with transparent heuristic signals.
- POST /api/evaluations/compare runs the same prompt against 1–4 installed Ollama models and returns their answers, heuristic signals, and response times.
- GET /api/evaluations returns recent evaluation history and aggregate score/time summaries.
- All evaluation endpoints require SAFWAN_APP_TOKEN. The compare endpoint calls only models already installed in the configured Ollama server.

Scores use answer length, overlap with prompt terms, basic structure, and clarity proxies. When an expected answer is supplied, the API also reports term overlap with that reference. These are not factuality, safety, or benchmark scores; human review and a trusted test dataset are still required to measure correctness. Model comparison can consume significant local RAM/VRAM and time, so compare a small number of models.


## Phase 10: Human-reviewed training dataset

SAFWAN AI can collect question/ideal-answer pairs as a private training dataset. New examples start as drafts; only explicitly approved examples are included in the JSONL export. Editing an example automatically returns it to draft so it must be reviewed again.

All endpoints require the master \`SAFWAN_APP_TOKEN\`:
- \`POST /api/training-data\` — create a draft pair.
- \`GET /api/training-data?status=draft\` — list and count draft, approved, and rejected examples.
- \`PATCH /api/training-data/{id}\` — edit a pair (resets status to draft).
- \`PATCH /api/training-data/{id}/status\` — set \`draft\`, \`approved\`, or \`rejected\`.
- \`DELETE /api/training-data/{id}\` — delete an example.
- \`GET /api/training-data/export.jsonl\` — download approved examples only in chat-messages JSONL format.

This phase prepares data only; it does not fine-tune or train a model. Review every example for correctness, quality, permission, and personal or confidential information before approval. There is no automatic PII detector, so do not upload sensitive data. Fine-tuning still requires a chosen compatible base model, adequate clean examples, GPU/compute resources, and a separate training workflow.


## Phase 12: Optional LoRA fine-tuning pipeline

The optional \`scripts/train_lora.py\` pipeline converts the approved SAFWAN JSONL export into a LoRA adapter for a compatible Hugging Face instruction model. It does not train a foundation model from scratch and does not automatically replace the Ollama model used by SAFWAN chat.

**Important hardware and platform requirements**
- Run this optional workflow in a separate Linux environment with a compatible NVIDIA CUDA GPU. The script intentionally stops if CUDA is unavailable; CPU training is not attempted.
- Install a PyTorch build that matches the machine's CUDA setup first, then install \`requirements-training.txt\`. These packages are not part of the normal SAFWAN web-app requirements.
- The default base model is \`Qwen/Qwen2.5-3B-Instruct\`. Check the model's current license, access terms, and commercial-use conditions before use.
- GPU VRAM needs vary with model size, sequence length, and batch settings. Check available VRAM before attempting training; no specific GPU capacity is guaranteed by this starter script.
- The script requires at least 20 unique reviewed examples as a basic safety gate. This is not a claim that 20 examples are enough for a useful production model; quality and diversity matter much more.

**Workflow**
1. In SAFWAN AI, review and approve only accurate, permitted, non-sensitive examples.
2. Download the approved \`safwan-training-approved.jsonl\` file from Training Dataset.
3. Validate the file first: \`python scripts/train_lora.py --data safwan-training-approved.jsonl --validate-only\`
4. In a separate supported Linux CUDA environment, install PyTorch for that CUDA version and then run \`pip install -r requirements-training.txt\`.
5. Start a small experiment: \`python scripts/train_lora.py --data safwan-training-approved.jsonl --model Qwen/Qwen2.5-3B-Instruct --output ./safwan-lora-adapter\`
6. Evaluate the adapter on a separate held-out test set before considering deployment.

The output is a LoRA adapter, not a complete model. SAFWAN's Ollama runtime does not automatically load this adapter. A separate conversion/serving integration and evaluation are required before using it in chat. Do not train on private customer records, passwords, API keys, or personal information.


### Phase 13: Held-out validation split

Before fine-tuning, split the approved JSONL export into separate training and validation files:

\`\`\`bash
python scripts/split_dataset.py --data safwan-training-approved.jsonl --output-dir ./safwan-dataset --validation-ratio 0.1 --seed 42
\`\`\`

This writes \`train.jsonl\` and \`validation.jsonl\`. Exact duplicate examples are removed by the dataset loader before splitting, and the split is deterministic for a fixed seed. Use the training file for learning and pass the validation file to track validation loss:

\`\`\`bash
python scripts/train_lora.py --data ./safwan-dataset/train.jsonl --validation-data ./safwan-dataset/validation.jsonl --output ./safwan-lora-adapter
\`\`\`

Validation loss is only one signal; it does not prove factual accuracy, safety, or real-world usefulness. Keep a separate human-reviewed test set that is never used for training or model selection. With a very small dataset, a validation split can be unstable; gather more diverse examples instead of treating a small score as proof of quality.


## Phase 14: Compare a fine-tuned adapter with its base model

After training, evaluate the adapter against a held-out test file that was not used for training or model selection. Example:

\`\`\`bash
python scripts/evaluate_adapter.py --data ./safwan-dataset/validation.jsonl --adapter ./safwan-lora-adapter --model Qwen/Qwen2.5-3B-Instruct --output ./safwan-evaluation.json
\`\`\`

The script generates both base-model and adapter answers for each prompt and saves a JSON report with latency and simple token-overlap F1 against the reference answer. It requires a compatible CUDA GPU and the optional training dependencies. Review the outputs manually. Token overlap is only a rough diagnostic; it cannot determine factual correctness, safety, reasoning quality, or whether the answer is actually better. For a credible final evaluation, keep a separate untouched test set and have humans review representative Bangla, Banglish, English, and business tasks. Do not deploy an adapter based only on this score.


## Phase 15: Prepare a trained LoRA adapter for Ollama

A trained PEFT adapter is not a standalone model. The deployment-preparation script merges it into the exact original Hugging Face base model, producing a full model directory that can then be converted to GGUF and imported into Ollama. This is a manual, compute-heavy step; SAFWAN does not automatically train, merge, convert, or deploy models.

**Important:** use the exact base model (and, ideally, the same model revision) used during fine-tuning. The current training script uses QLoRA 4-bit; merging reloads the base model in FP16 and therefore needs a compatible NVIDIA CUDA environment, substantial VRAM/RAM, and several GB of free disk space. It deliberately refuses CPU-only merging. The script does not change or delete the original adapter.

1. Copy the trained adapter folder and its original model name to a Linux CUDA machine.
2. Install a PyTorch build matching that machine's CUDA setup, then install `requirements-training.txt`.
3. Check the paths without loading the model:
   `python scripts/merge_lora_adapter.py --adapter ./safwan-lora-adapter --model Qwen/Qwen2.5-3B-Instruct --output ./safwan-merged-model --validate-only`
4. Merge the adapter:
   `python scripts/merge_lora_adapter.py --adapter ./safwan-lora-adapter --model Qwen/Qwen2.5-3B-Instruct --output ./safwan-merged-model`
5. Install llama.cpp using its current official instructions. Convert the merged Hugging Face directory to an FP16 GGUF:
   `python convert_hf_to_gguf.py ./safwan-merged-model --outfile ./safwan-merged-f16.gguf --outtype f16`
   Run the converter from the llama.cpp checkout; the script path may be `./convert_hf_to_gguf.py` depending on your working directory. Check that the architecture is supported by your llama.cpp version.
6. On the machine running Ollama, create a text file named `Modelfile` containing the absolute path to the GGUF:
   ```text
   FROM /absolute/path/to/safwan-merged-f16.gguf
   PARAMETER temperature 0.35
   ```
7. Create and test the Ollama model:
   `ollama create safwan-finetuned -f Modelfile`
   `ollama run safwan-finetuned`
8. After confirming the model works, set `OLLAMA_MODEL=safwan-finetuned` in SAFWAN's `.env`. Restart SAFWAN AI. The existing model router will use this installed model as its general/default model; coding and reasoning preferences can be set to the same exact Ollama model name if desired.

GGUF conversion/import compatibility depends on the model architecture and llama.cpp/Ollama versions. Do not assume that a Qwen adapter can be loaded directly through Ollama's Safetensors ADAPTER path: the documented Safetensors adapter architecture list is limited, and adapter support may differ by Ollama release. The merged GGUF route avoids depending on direct adapter loading. Keep the base model, adapter, merged model, and GGUF until deployment and evaluation are complete. Re-run the held-out evaluation and human review after conversion; successful import does not prove the fine-tune is better. Check the base model's license before commercial use or redistribution.


## Phase 16: Model deployment and quality dashboard

The Model Deployment page in the SAFWAN web UI provides an admin-only view of models currently installed in the configured Ollama server and evaluation history grouped by model. It also lets an administrator run a prompt against up to four installed models and compare their answers, heuristic scores, and response latency.

- `GET /api/deployment/status` — reports Ollama connectivity, installed model names, evaluation averages by model, and the ten most recent evaluations. Requires `SAFWAN_APP_TOKEN`.
- The dashboard uses the same master-token connection as API Management.
- Comparison requests use the existing `POST /api/evaluations/compare` endpoint and only run models already installed in Ollama.
- The comparison endpoint evaluates each model sequentially. A slow model can take several minutes; this is not a throughput or load test.
- Average scores are heuristic indicators, not factuality, safety, or benchmark measurements. Review answers manually and use a held-out test set before choosing a model for deployment.
- Installed in Ollama means the model is available to the configured runtime; it does not prove the model is fine-tuned, correctly licensed, or production-ready.
