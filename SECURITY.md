# Security Policy

## Current deployment status
SAFWAN AI is an early development MVP for localhost or a trusted private development network only.

Do not expose it directly to the public internet or use it with sensitive customer data yet. The optional API bearer token is not a substitute for full user authentication, tenant isolation, CSRF protection, or a production security review.

## Data handling
- Chat and business records are stored in a local SQLite database.
- Prompts are sent to the configured Ollama server.
- No paid external AI API is integrated.
- Back up the database securely and never commit .env or database files.

## Reporting
Do not publish secrets, customer records, or exploitable details in public issues. Report security concerns privately to the repository owner.
