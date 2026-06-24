# OpenClaw + Carta Automation

Automated portfolio data export system for Carta via OpenClaw AI agent.

**Author:** Ankur Kumar | **Team:** Elevation AI | **Status:** Active

---

## What This Does

Per company:

1. Authenticates into Carta via a persistent Chrome session
2. Navigates to the investor portfolio dashboard
3. Searches and resolves the target company via fuzzy entity matching
4. Exports the **holdings CSV/XLSX** (primary structured export)
5. Downloads any **attached documents** (valuations, term sheets, K-1s)
6. Stores raw files in `output/exports/`
7. Returns structured metadata via FastAPI + MCP

### Export Result Format

```json
{
  "company": "OpenAI",
  "exports": [
    { "type": "holdings_csv", "path": "output/exports/<task_id>_openai_holdings.csv" },
    { "type": "document",     "path": "output/exports/<task_id>_openai_doc_1.pdf" }
  ]
}
```

---

## Architecture

```
MCP Client (Claude, etc.)
        │
        ▼ SSE + JSON-RPC
  mcp_server.py  (port 8080)
        │
        ▼ HTTP
  api/server.py  (port 8082)   ← FastAPI + SQLite WAL queue
        │
        ▼
  CartaProvider              ← singleton Playwright + CDP
        │
  Persistent Chrome  ←──────── start_persistent_browser.py
        │
  https://app.carta.com
```

### Provider Abstraction

The codebase uses a `ProviderAgent` interface:

```
services/providers/
├── base.py        ← abstract ProviderAgent
└── carta/         ← CartaProvider (active implementation)
```

To add a new provider (Crunchbase, Affinity, DealRoom…):

1. Create `services/providers/crunchbase.py` implementing `ProviderAgent`
2. Import and swap in `api/server.py`
3. MCP tools and queue are unchanged

---

## Prerequisites

| Requirement | Version |
| ----------- | ------- |
| Python      | 3.11+   |
| Playwright  | Latest  |
| Chrome      | Latest  |
| Node.js     | 18+     |

---

## Setup (One-Time)

### Step 1 — Create Environment

```bash
conda create -n carta-env python=3.11
conda activate carta-env
```

### Step 2 — Install Dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### Step 3 — Add Carta Credentials

Edit `.env` in the project root:

```env
CARTA_EMAIL=your-email@elevationai.com
CARTA_PASSWORD=your-carta-password
```

Or add them to `config/settings.json` under the `"carta"` key.

### Step 4 — Add Your Company List

Edit `config/companies.json`:

```json
{
  "companies": ["OpenAI", "Stripe", "Anthropic"]
}
```

---

## Running the System

### Step 1 — Start the Persistent Browser

```bash
python scripts/start_persistent_browser.py
```

Chrome opens to `https://app.carta.com/login/`. **Log in manually.**
Keep the terminal open — the browser must stay running.

### Step 2 — Start the API Server

```bash
uvicorn api.server:app --host 0.0.0.0 --port 8082
```

### Step 3 — Start the MCP Server (optional)

```bash
python scripts/mcp_server.py --port 8080
```

---

## API Reference

### Submit a single export task

```bash
curl -X POST http://127.0.0.1:8082/api/download-report \
  -H "Content-Type: application/json" \
  -d '{"company_name": "OpenAI"}'
```

Response:

```json
{"task_id": "uuid", "status": "pending", "company_name": "OpenAI"}
```

### Poll task status

```bash
curl http://127.0.0.1:8082/api/status/<task_id>
```

Response (completed):

```json
{
  "task_id": "uuid",
  "status": "completed",
  "export_url": "http://34.122.215.240:8082/files/<task_id>_openai_holdings.csv"
}
```

### MCP Tools

| Tool                | Description                             |
| ------------------- | --------------------------------------- |
| `download_report` | Export data for a single company        |
| `download_batch`  | Export data for a list of companies     |
| `get_status`      | Check if the Carta export service is up |

MCP authentication: `X-API-Key` header (default: `openclaw-dev-key`, set via `MCP_API_KEY` env var).

---

## Folder Structure

```
openclaw_carta/
├── legacy/
│   ├── PRD.docx                    # Product Requirements Document
│   └── pitchbook.zip               # Legacy Pitchbook automation code
├── api/
│   └── server.py                   # FastAPI + SQLite worker
├── services/
│   ├── entity_resolver.py          # Fuzzy company matching (RapidFuzz)
│   └── providers/
│       ├── base.py                 # ProviderAgent interface
│       └── carta/                  # Carta provider implementation
├── scripts/
│   ├── start_persistent_browser.py # Launch Chrome for CDP
│   └── mcp_server.py              # MCP SSE server
├── utils/
│   └── db.py                       # SQLite WAL helpers
├── config/
│   ├── companies.json.example      # Example company list template
│   └── settings.json.example       # Example credentials settings template
├── requirements.txt
└── Dockerfile
```

---

## Known Issues & Workarounds

| Issue                          | Workaround                                                        |
| ------------------------------ | ----------------------------------------------------------------- |
| Carta session expires mid-task | Re-login in persistent browser; provider detects and retries auth |
| MFA/SSO required               | Log in manually in persistent browser; session is reused          |
| Export button not found        | Verify account has investor/holdings access on Carta              |
| Company not found in portfolio | Check company name spelling; fuzzy matching has a 75% threshold   |
| CDP port conflict              | Restart Chrome or ensure only one Chrome instance uses port 9222  |

---

## Contact

- **Ankur Kumar** — project lead
- **Saumya Garg** — stakeholder
- **Hanzel Corella** — provides company lists
- **Alan Abraham** — stakeholder
