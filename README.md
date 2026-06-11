# Uniware Vtiger MCP Server (Phase 1)

Read-only [MCP](https://modelcontextprotocol.io/) server that connects Claude to **Vtiger CRM** for Uniware's Account Manager (AM) Copilot. Phase 1 exposes briefing tools for leads, deals, and overdue follow-ups.

**Repository:** http://192.168.1.195/genai/claude_vtiger_mcp

## MCP tools

| Tool | Description |
|------|-------------|
| `get_leads_by_owner` | Leads assigned to an AM (organisation, status, follow-up fields) |
| `get_deals_by_owner` | Open deals for an AM (stage, amount, last contacted, follow-up) |
| `get_overdue_followups` | Leads and deals with follow-up date on or before today |

All tools take an `owner` argument — the Vtiger user ID (e.g. `19x5`) agreed with your CRM admin.

## Requirements

- Python **3.12+**
- Network access to your Vtiger instance (`VTIGER_BASE_URL`)
- Vtiger API username and access key

## Quick start

```bash
# Clone
git clone http://192.168.1.195/genai/claude_vtiger_mcp.git
cd claude_vtiger_mcp

# Virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with Vtiger credentials and MCP_API_KEY

# Run
set PYTHONPATH=src          # Windows CMD
# export PYTHONPATH=src     # Linux / macOS
vtiger-mcp
# or: uvicorn vtiger_mcp.main:app --host 0.0.0.0 --port 8000
```

Server defaults to `http://0.0.0.0:8000`. MCP HTTP endpoint is served by FastMCP on the same app.

## Environment variables

Copy `.env.example` to `.env`. Key settings:

| Variable | Required | Description |
|----------|----------|-------------|
| `MCP_API_KEY` | Yes | Secret Claude sends as `X-API-Key` when calling this server |
| `MCP_AUTH_TOKEN` | No | Optional Bearer token (FastMCP native auth) |
| `VTIGER_BASE_URL` | Yes | e.g. `https://usp.od2.vtiger.com` |
| `VTIGER_USERNAME` | Yes | Vtiger API user |
| `VTIGER_ACCESS_KEY` | Yes | Vtiger webservice access key |
| `VTIGER_OPEN_DEAL_STAGES` | No | Comma-separated stages; empty = all deals for owner |
| `VTIGER_FIELD_*` | Partial | CRM field API names; at least one follow-up date field required for `/ready` |

Generate an API key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

See `.env.example` for the full list of field-mapping variables.

## Health checks

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness — always returns 200 if the process is up |
| `GET /ready` | Readiness — 200 when required config is present, 503 if degraded |

These paths do not require authentication.

## Authentication

Requests to MCP endpoints must include one of:

- `X-API-Key: <MCP_API_KEY>`
- `Authorization: Bearer <MCP_API_KEY>` (or `MCP_AUTH_TOKEN` if set for FastMCP auth)

When registering the custom connector in Claude, use the deployed base URL and `MCP_API_KEY`.

## Helper scripts

Run from the repo root with `PYTHONPATH=src` and `.env` loaded:

```bash
python scripts/connection_check.py   # Vtiger login + MCP health probe
python scripts/mcp_check.py            # MCP tool smoke test
python scripts/describe_fields.py    # Inspect Vtiger module fields
python scripts/test_tools.py         # Exercise CRM tools
```

## Docker

```bash
docker build -t uniware-vtiger-mcp .
docker run --env-file .env -p 8000:8000 uniware-vtiger-mcp
```

## Deploy (Render)

`render.yaml` defines a web service:

- **Build:** `pip install -r requirements.txt`
- **Start:** `PYTHONPATH=src uvicorn vtiger_mcp.main:app --host 0.0.0.0 --port $PORT`
- **Health:** `/health`

Set environment variables in the Render dashboard (or GitLab CI) — do not commit `.env`.

## Project layout

```
src/vtiger_mcp/
  main.py           # FastMCP app, health routes, uvicorn entry
  config.py         # Settings from environment
  middleware.py     # API key validation
  tools/crm.py      # MCP tool definitions
  vtiger/client.py  # Vtiger webservice client
scripts/            # Local verification scripts
```

## Security

- Never commit `.env` or Vtiger access keys.
- Phase 1 is **read-only** — no create/update/delete operations.
- Rotate `MCP_API_KEY` if it is exposed.

## License

Internal Uniware project.
