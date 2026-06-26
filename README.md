# Uniware Vtiger MCP Server (Phase 1)

Read-only [MCP](https://modelcontextprotocol.io/) server that connects Claude to **Vtiger CRM** for Uniware's Account Manager (AM) Copilot. Phase 1 exposes briefing tools for leads, deals, and overdue follow-ups.

**Repository:** https://github.com/Srimathi-8502/Mcp_Vtiger_claude

## MCP tools

| Tool | Description |
|------|-------------|
| `get_leads_by_owner` | Leads assigned to an AM (organisation, status, follow-up fields) |
| `get_deals_by_owner` | Open deals for an AM (organisation, stage, amount, last contacted, follow-up) |
| `get_overdue_followups` | Leads and deals with follow-up date on or before today |

All tools take an `owner` argument — the Vtiger user ID (e.g. `19x5`) agreed with your CRM admin.

## Requirements

- Python **3.12+**
- Network access to your Vtiger instance (`VTIGER_BASE_URL`)
- Vtiger API username and access key

## Quick start

```bash
# Clone
git clone https://github.com/Srimathi-8502/Mcp_Vtiger_claude.git
cd Mcp_Vtiger_claude

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

### Confirmed Deals field mapping (Potentials module)

Deals use the Vtiger module **`Potentials`** (not `Deals`).

| Briefing field | Vtiger API name | Env var |
|----------------|-----------------|---------|
| Assigned AM | `assigned_user_id` | `VTIGER_FIELD_DEAL_OWNER` |
| Deal name | `potentialname` | `VTIGER_FIELD_DEAL_NAME` |
| Organization | `related_to` | `VTIGER_FIELD_DEAL_ORG` (resolved to `accountname` via Accounts) |
| Deal stage | `sales_stage` | `VTIGER_FIELD_DEAL_STAGE` |
| Amount | `amount` | `VTIGER_FIELD_DEAL_AMOUNT` |
| Last contacted | `last_contacted_on` | `VTIGER_FIELD_DEAL_LAST_CONTACTED` |
| Next follow-up date | `cf_potentials_nextfollowupdate` | `VTIGER_FIELD_DEAL_FOLLOWUP_DATE` |
| Next follow-up description | `nextstep` | `VTIGER_FIELD_DEAL_FOLLOWUP_DESC` |

Deal tool responses remap these to: `owner`, `deal_name`, `organisation_id`, `organisation_name` (resolved from Accounts), `stage`, `amount`, `last_contacted_date`, `next_followup_date`, `next_followup_description`.

**Leads follow-up:** Vtiger `Leads` has no next-follow-up date field (unlike Potentials `cf_potentials_nextfollowupdate`). `get_overdue_followups` returns **deals only** until a Leads date field exists in CRM. Use `get_leads_by_owner` for leads in the briefing.

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
python scripts/describe_raw.py       # Full describe JSON for Leads/Potentials
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
docs/               # Technical architecture and project history
```

See [docs/TECHNICAL.md](docs/TECHNICAL.md) for architecture and request flow.  
See [docs/PROJECT_JOURNEY_AND_TECHNICAL_HISTORY.md](docs/PROJECT_JOURNEY_AND_TECHNICAL_HISTORY.md) for full project journey, issues, and module reference.

## Security

- Never commit `.env` or Vtiger access keys.
- Phase 1 is **read-only** — no create/update/delete operations.
- Rotate `MCP_API_KEY` if it is exposed.

## License

Internal Uniware project.
