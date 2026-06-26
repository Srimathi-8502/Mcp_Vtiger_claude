# Uniware Vtiger MCP — Project Journey & Technical History

**Document purpose:** Full technical history for leadership review — how the project started, what was tried, issues faced, solutions applied, and what the current code does.

**Audience:** Technical lead, IT, GenAI team  
**Last updated:** June 2026  
**Live service:** https://mcp-vtiger-claude.onrender.com  
**Repository:** https://github.com/Srimathi-8502/Mcp_Vtiger_claude

---

## 1. Executive summary

We built a **read-only MCP (Model Context Protocol) server** that connects **Anthropic Claude** to **Uniware’s Vtiger CRM** so Account Managers (AMs) can ask for daily briefings in natural language.

The project evolved in two major phases:

| Phase | Approach | User experience |
|-------|----------|-----------------|
| **Phase 1 (initial)** | Shared MCP server + owner ID in prompt | AM had to know Vtiger ID (e.g. `19x6`) |
| **Phase 1.5 (current)** | Microsoft Entra ID OAuth + per-user access | AM signs in with `@uniware.net` email; no owner ID needed |

**Current state:** Code deployed on Render, Azure OAuth integrated, four MCP tools (`whoami` + three briefing tools), per-user data scoping enforced in server code.

---

## 2. Why we started — business goal

**Problem:** AMs spend time manually checking Vtiger for overdue follow-ups, open deals, and leads before daily standups.

**Solution:** An “AM Copilot” — AM opens Claude, asks *“Give me my morning CRM briefing”*, Claude calls our MCP server, server fetches live Vtiger data, Claude formats a prioritized action list.

**Constraints agreed early:**
- Phase 1 is **read-only** (no create/update/delete in Vtiger)
- Uniware Vtiger instance: `https://usp.od2.vtiger.com`
- Deals module API name is **Potentials** (not `Deals`)
- Deployment target: **Render.com** + **Claude custom connector**

---

## 3. Chronological timeline

### Stage 0 — Project bootstrap (commits `49b69e6` → `8396173`)

**What we built:**
- Python 3.12 + FastMCP + Uvicorn ASGI server
- Vtiger webservice client (`getchallenge` → MD5 → `login` → `query`)
- Three MCP tools requiring **`owner` parameter** (Vtiger user ID)
- `ApiKeyMiddleware` for optional `X-API-Key` auth
- `/health` and `/ready` endpoints
- Render deployment via `render.yaml`

**First tool design:**

| Tool | Input | Purpose |
|------|-------|---------|
| `get_leads_by_owner` | `owner: str` | Leads for one AM |
| `get_deals_by_owner` | `owner: str` | Deals for one AM |
| `get_overdue_followups` | `owner: str` | Overdue follow-ups |

**First auth approach:** Optional shared `MCP_API_KEY` — Claude sends same key for all users. **Could not identify individual AMs.**

---

### Stage 1 — Vtiger field mapping & data quality (commits `2bca5e4` → `f901f6e`)

**Work done:**
- Confirmed Vtiger API field names via `describe` scripts
- Mapped deal follow-up field: `cf_potentials_nextfollowupdate`
- Mapped deal org field: `related_to` (Account reference, not plain text)
- Added **Account name resolution** — deals return `organisation_name` not just ID
- Added `docs/TECHNICAL.md` architecture document

**Issue discovered:** Vtiger UI says “Deals” but API module is **`Potentials`**. Using `Deals` returns `ACCESS_DENIED`.

**Solution:** `VTIGER_DEALS_MODULE=Potentials` in config.

---

### Stage 2 — Leads follow-up limitation (commit `acb8e42`)

**Issue:** `get_overdue_followups` could not filter leads by follow-up date.

**Root cause:** Vtiger **Leads** module has **no “next follow-up date” field** (confirmed via `describe` operation). Only Potentials has `cf_potentials_nextfollowupdate`.

**Solution:**
- Leave `VTIGER_FIELD_LEAD_FOLLOWUP_DATE` empty
- `get_overdue_followups` returns **deals only** for overdue filtering
- Leads still available via `get_leads_by_owner` / `get_my_leads` with status and description

**Status:** Documented as CRM limitation, not a code bug. Phase 2 depends on CRM adding a Leads date field.

---

### Stage 3 — Vtiger session reliability (commit `8ecfa80`)

**Issue:** Long-running server or idle periods caused Vtiger queries to fail with stale session errors.

**Symptoms:** `"session identifier"`, `"invalid session"`, `"session expired"` from Vtiger webservice.

**Solution in `vtiger/client.py`:**
- Detect stale session error messages
- Clear cached `sessionName`
- Retry query once after re-login

**File:** `src/vtiger_mcp/vtiger/client.py` — `query_all()` retry loop

---

### Stage 4 — Per-user access without owner ID (commit `48c092d`)

**User requirement:** AMs should not type Vtiger owner ID in Claude prompts. Server should know who is asking. **Nirmal** gets full access; others see only their own data.

**First approach considered:**

| Option | Verdict |
|--------|---------|
| Shared API key | **Rejected** — cannot identify individual users |
| Owner ID in Claude prompt | **Rejected** — poor UX, error-prone |
| Google OAuth | **Possible** but Uniware uses **Microsoft 365** |
| **Microsoft Entra ID OAuth** | **Selected** — matches `@uniware.net` sign-in |

**What we implemented:**

| Component | File | Role |
|-----------|------|------|
| Azure OAuth provider | `main.py` | `AzureProvider` from FastMCP |
| User identity resolver | `auth/users.py` | Email → Vtiger owner ID |
| New MCP tools | `tools/crm.py` | `whoami`, `get_my_*` |
| JWT pass-through | `middleware.py` | OAuth tokens not blocked by API key middleware |
| Azure env config | `config.py` | `AZURE_*`, `MCP_PUBLIC_BASE_URL` |
| Setup guide | `docs/CLAUDE_SETUP.md` | IT handoff for Entra ID |

**New tool design:**

| Tool | Input | Purpose |
|------|-------|---------|
| `whoami` | none | Show signed-in email, owner ID, admin flag, scope |
| `get_my_leads` | optional `am_email` (admin only) | Leads for signed-in AM |
| `get_my_deals` | optional `am_email` (admin only) | Deals for signed-in AM |
| `get_my_overdue_followups` | optional `as_of_date`, `am_email` | Daily briefing |

---

### Stage 5 — Deployment & Claude connector (June 2026)

**Actions:**
- Pushed `48c092d` to GitHub → Render auto-deploy
- IT provided Azure Tenant ID, Client ID, Client Secret
- Set Render environment variables
- Registered Claude custom connector: Name + URL only (OAuth fields left empty in Claude UI)
- UptimeRobot monitoring on `/health`

**Issue during deploy:** `MCP_PUBLIC_BASE_URL` was missing locally → `azure_oauth_enabled` stayed `false`.

**Solution:** Added `MCP_PUBLIC_BASE_URL=https://mcp-vtiger-claude.onrender.com` to `.env` and Render.

---

## 4. First approach vs current code — comparison

| Area | First approach | Current code |
|------|--------------|--------------|
| **MCP tools** | 3 tools with `owner` param | 4 tools: `whoami` + 3 `get_my_*` |
| **User identity** | AM provides Vtiger ID in prompt | Microsoft email from OAuth token |
| **Authentication** | Optional shared `MCP_API_KEY` | Microsoft Entra ID (`AzureProvider`) |
| **Authorization** | None — any caller with key sees any owner | Email mapped to Vtiger user; data scoped per AM |
| **Admin access** | Not implemented | `VTIGER_ADMIN_EMAILS` (e.g. Nirmal) |
| **Claude connector** | URL + optional API key (problematic) | URL only; Microsoft sign-in on first use |
| **Deal org display** | Raw `related_to` ID | Resolved `organisation_name` from Accounts |
| **Session handling** | Single session, fail on expiry | Auto re-login on stale session |
| **Readiness check** | Required `MCP_API_KEY` | Requires Azure OAuth vars + Vtiger config |

---

## 5. Issues faced & solutions (complete log)

| # | Issue | Symptom | Root cause | Solution | Code / config |
|---|-------|---------|------------|----------|---------------|
| 1 | Wrong Vtiger module name | `ACCESS_DENIED` on describe | UI says “Deals”, API uses `Potentials` | `VTIGER_DEALS_MODULE=Potentials` | `config.py` |
| 2 | Deal shows ID not customer name | `organisation_id` only in JSON | `related_to` is Account reference | Batch lookup in Accounts module | `client.py` → `_resolve_account_names()` |
| 3 | No lead overdue follow-ups | Empty leads in overdue tool | No date field on Leads module | Skip lead date filter; document limitation | `.env` + docs |
| 4 | Vtiger session expires | Random query failures | Cached `sessionName` goes stale | Clear session + retry once | `client.py` → `query_all()` |
| 5 | AM must know owner ID | Bad UX, wrong data risk | No user identity in MCP layer | Azure OAuth + email mapping | `auth/users.py` |
| 6 | Shared API key insecure | All users same access | API key cannot identify user | Entra ID per-user sign-in | `main.py` AzureProvider |
| 7 | `MCP_PUBLIC_BASE_URL` missing | OAuth not enabled | `azure_oauth_enabled` needs 4 vars | Set public URL in env | Render + `.env` |
| 8 | Claude API key UI limited | 401 or OAuth confusion | Claude connector doesn’t use X-API-Key well | Use OAuth; leave `MCP_API_KEY` empty | `CLAUDE_SETUP.md` |
| 9 | Render cold start | 502, slow first call | Free tier sleeps after ~15 min idle | UptimeRobot ping `/health` every 5 min | Ops config |
| 10 | `/ready` 503 before Azure | `missing MCP_API_KEY` | Old code expected API key | Deploy new code; OAuth-aware `/ready` | `main.py` |
| 11 | Copilot vs Claude confusion | “MCP not possible” claim | Different Microsoft products | Copilot Studio supports MCP; we chose **Claude** | Documented in chat |
| 12 | Email ≠ Entra “ID” | IT confusion | Entra uses GUIDs + email login | Email is login identity; GUIDs are app config | `CLAUDE_SETUP.md` |
| 13 | Non-admin tries `am_email` | Access denied | Only admins can query other AMs | `AccessDenied` in `resolve_owner_scope()` | `auth/users.py` |
| 14 | Microsoft vs Google OAuth | Wrong IdP | Uniware uses Microsoft 365 | `AzureProvider` not `GoogleProvider` | `main.py` |

---

## 6. Module-by-module code reference

### 6.1 `src/vtiger_mcp/main.py` — Application entry point

**Purpose:** Bootstraps the MCP server, wires auth, registers tools and health routes.

**Key logic:**
```
configure_logging()
  → get_settings()
  → _build_mcp()          # AzureProvider if AZURE_* + MCP_PUBLIC_BASE_URL set
  → register_tools(mcp)   # binds whoami + get_my_* tools
  → /health, /ready routes
  → app = mcp.http_app(middleware=[ApiKeyMiddleware])
```

**Auth priority (first match wins):**
1. Azure Entra ID (`azure_oauth_enabled`)
2. Google OAuth (`google_oauth_enabled`) — optional fallback
3. Static token (`MCP_AUTH_TOKEN`)
4. No auth (development only)

**Production:** Azure Entra ID is active when all of these are set:
- `AZURE_TENANT_ID`
- `AZURE_CLIENT_ID`
- `AZURE_CLIENT_SECRET`
- `MCP_PUBLIC_BASE_URL`

---

### 6.2 `src/vtiger_mcp/config.py` — Configuration

**Purpose:** Loads all environment variables into typed `Settings` (Pydantic).

**Important groups:**

| Group | Variables | Purpose |
|-------|-----------|---------|
| Runtime | `HOST`, `PORT`, `LOG_LEVEL`, `FASTMCP_STATELESS_HTTP` | Server behaviour |
| Azure OAuth | `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `MCP_PUBLIC_BASE_URL` | Claude user sign-in |
| Access control | `VTIGER_ADMIN_EMAILS`, `OAUTH_ALLOWED_DOMAIN` | Who sees all data vs own data |
| Vtiger connection | `VTIGER_BASE_URL`, `VTIGER_USERNAME`, `VTIGER_ACCESS_KEY` | CRM API login |
| Field mapping | `VTIGER_FIELD_*` | Maps env names to Vtiger API field names |

**Helper properties:**
- `azure_oauth_enabled` — true when Azure + public URL configured
- `lead_select_fields()` / `deal_select_fields()` — dynamic SQL SELECT columns
- `open_deal_stage_list` — optional stage filter for deals

---

### 6.3 `src/vtiger_mcp/middleware.py` — HTTP security layer

**Purpose:** Runs before every HTTP request (except public paths).

**Public paths (no auth):** `/health`, `/ready`, `/.well-known/*`

**Logic:**
- If `MCP_API_KEY` is empty → allow all (OAuth handled by FastMCP)
- If `Authorization: Bearer <JWT>` (3 dot-separated parts) → pass through to FastMCP OAuth
- Otherwise validate `X-API-Key` or Bearer against `MCP_API_KEY`

**Why JWT pass-through:** Claude sends Microsoft OAuth tokens as Bearer JWTs. Middleware must not treat them as API keys.

---

### 6.4 `src/vtiger_mcp/auth/users.py` — User identity & access control

**Purpose:** Core of per-user access — maps Microsoft login email to Vtiger user.

**Classes:**

| Class | Role |
|-------|------|
| `UserResolver` | Loads Vtiger Users, maps email → owner ID |
| `AuthenticatedUser` | Signed-in user: email, owner_id, is_admin |
| `AuthError` | Not signed in |
| `AccessDenied` | Not allowed (wrong domain, not in Vtiger, not admin) |

**Flow:**
```
get_access_token()                    # from FastMCP OAuth
  → read email from token claims      # email, preferred_username, or upn
  → check @uniware.net domain
  → load Vtiger Users table
  → match email to user_name / email1
  → check VTIGER_ADMIN_EMAILS
  → return AuthenticatedUser
```

**`resolve_owner_scope(am_email, current_user)`:**
- Regular AM → always their own `owner_id`
- Admin + no `am_email` → `None` (all data)
- Admin + `am_email` → that AM’s `owner_id`

---

### 6.5 `src/vtiger_mcp/tools/crm.py` — MCP tools (Claude interface)

**Purpose:** Defines what Claude can call. Returns JSON strings.

| Tool | Auth required | Returns |
|------|---------------|---------|
| `whoami` | Yes | email, display_name, owner_id, is_admin, scope |
| `get_my_leads` | Yes | leads list scoped to user |
| `get_my_deals` | Yes | deals list scoped to user |
| `get_my_overdue_followups` | Yes | overdue leads + deals scoped to user |

**Error handling:** Never raises to Claude — returns `{"error": true, "tool": "...", "message": "..."}`

---

### 6.6 `src/vtiger_mcp/vtiger/client.py` — Vtiger CRM integration

**Purpose:** Only module that talks to Vtiger `webservice.php`.

**Authentication handshake:**
```
1. GET  ?operation=getchallenge&username=...
2. MD5(token + access_key)
3. POST operation=login
4. Receive sessionName
5. GET  ?operation=query&sessionName=...&query=SELECT ...
```

**Key methods:**

| Method | Purpose |
|--------|---------|
| `list_users()` | Load all Vtiger users for email mapping |
| `get_leads_by_owner(owner)` | `owner=None` → all leads (admin) |
| `get_deals_by_owner(owner)` | `owner=None` → all deals (admin) |
| `get_overdue_followups(owner, as_of)` | Date filter on follow-up fields |
| `query_all(query)` | Paginated LIMIT queries + session retry |
| `_resolve_account_names()` | `related_to` ID → `accountname` |

**Security in queries:**
- User values → `_quote()` (SQL string escape)
- Field/module names → `_validate_field()` (alphanumeric only)

---

### 6.7 `src/vtiger_mcp/logging_config.py` — Observability

**Purpose:** Configures stdout logging from `LOG_LEVEL` env var.

---

## 7. End-to-end MCP connection flow (current)

```
1. AM opens Claude → enables "Uniware Vtiger MCP" connector
2. AM asks: "Give me my morning CRM briefing"
3. Claude → POST https://mcp-vtiger-claude.onrender.com/mcp
4. If first time: Claude redirects AM to Microsoft sign-in (@uniware.net)
5. Microsoft Entra ID returns OAuth token to Claude
6. Claude sends tool call: get_my_overdue_followups
7. FastMCP validates JWT (AzureProvider)
8. tools/crm.py → get_authenticated_user()
   → email nirmal@uniware.net → Vtiger owner 19x6
9. VtigerClient queries Potentials WHERE follow-up date <= today
10. Account names resolved for related_to fields
11. JSON returned to Claude
12. Claude formats natural-language briefing for AM
```

**Optional first step:** Claude can call `whoami` to confirm identity before briefing.

---

## 8. Claude connector setup (actual steps used)

| Field in Claude UI | Value |
|--------------------|-------|
| Name | `Uniware Vtiger MCP` |
| Remote MCP server URL | `https://mcp-vtiger-claude.onrender.com/mcp` |
| OAuth Client ID | **Leave empty** |
| OAuth Client Secret | **Leave empty** |

OAuth is handled by the MCP server (Azure credentials on Render), not in Claude’s form.

---

## 9. Azure Entra ID setup (IT requirements)

| Step | Action |
|------|--------|
| 1 | App registration: `Uniware Vtiger MCP` (single tenant) |
| 2 | Redirect URI: `https://mcp-vtiger-claude.onrender.com/auth/callback` |
| 3 | Expose API scope: `mcp-access` |
| 4 | Manifest: `"requestedAccessTokenVersion": 2` |
| 5 | Client secret (recommend 12-month expiry) |
| 6 | Admin consent granted |
| 7 | User assignment (all org or selected AMs) |

---

## 10. Render deployment configuration

| Variable | Purpose |
|----------|---------|
| `MCP_PUBLIC_BASE_URL` | OAuth callback base URL |
| `AZURE_TENANT_ID` | Uniware Entra tenant |
| `AZURE_CLIENT_ID` | App registration ID |
| `AZURE_CLIENT_SECRET` | App secret |
| `AZURE_REQUIRED_SCOPES` | `mcp-access` |
| `OAUTH_ALLOWED_DOMAIN` | `uniware.net` |
| `VTIGER_ADMIN_EMAILS` | `nirmal@uniware.net` |
| `VTIGER_BASE_URL` | `https://usp.od2.vtiger.com` |
| `VTIGER_USERNAME` | API user |
| `VTIGER_ACCESS_KEY` | API key (secret) |
| `VTIGER_FIELD_*` | CRM field mapping |
| `MCP_API_KEY` | **Empty** when using OAuth |

**Start command:** `PYTHONPATH=src uvicorn vtiger_mcp.main:app --host 0.0.0.0 --port $PORT`

---

## 11. Helper scripts & what they test

| Script | Purpose |
|--------|---------|
| `scripts/connection_check.py` | Vtiger login + optional MCP health |
| `scripts/mcp_check.py` | In-process ASGI test of `/health`, `/ready`, `/mcp` |
| `scripts/describe_fields.py` | Discover Vtiger field names |
| `scripts/describe_raw.py` | Full describe JSON for Leads/Potentials |
| `scripts/test_tools.py` | Direct VtigerClient exercise |
| `scripts/test_user_access.py` | Per-user scope with `MCP_DEV_USER_EMAIL` |
| `scripts/test_session_retry.py` | Stale session auto-recovery |
| `scripts/test_live_mcp.py` | Live MCP JSON-RPC smoke test (needs update for new tools) |
| `scripts/generate_complete_docx.py` | Generates `Complete_MCP_Implementation.docx` |

---

## 12. Git commit milestones

| Commit | Description |
|--------|-------------|
| `49b69e6` | Initial Vtiger MCP server for Claude |
| `8396173` | README, setup, deployment docs |
| `2bca5e4` | Deal org mapping, field config, technical docs |
| `f901f6e` | Resolve `related_to` → Account name |
| `acb8e42` | Document Leads follow-up limits |
| `8ecfa80` | Vtiger session expiry retry |
| `48c092d` | **Azure OAuth + per-user access + whoami** |

---

## 13. What is still pending / known limitations

| Item | Status | Notes |
|------|--------|-------|
| Lead overdue follow-ups | Blocked by CRM | No date field on Leads module |
| Server-side stage filter | Optional | `VTIGER_OPEN_DEAL_STAGES` empty = all stages |
| Terminal stage exclusion | Prompt-side | Claude filters Closed Won/Lost in summary |
| Write-back to Vtiger | Phase 2 | No create/update/delete |
| `test_live_mcp.py` | Outdated | Still references old `get_deals_by_owner` |
| Render free tier cold start | Ops issue | 30–60s first request after idle |
| Claude OAuth + Entra edge cases | Monitor | Rare `code: Field required` — retry connect |

---

## 14. Phase 2 roadmap (not implemented)

- `create_activity` — log call/meeting to Vtiger
- `update_followup` — set next follow-up from Claude
- Server-side terminal stage and recency filters
- Lead follow-up when CRM adds date field
- Render paid tier for always-on
- Scheduled 9 AM briefing automation

---

## 15. Related documentation files

| File | Contents |
|------|----------|
| `docs/TECHNICAL.md` | Architecture and request flow (note: partially pre-OAuth) |
| `docs/CLAUDE_SETUP.md` | Claude + Entra ID connector setup for IT |
| `docs/PROJECT_JOURNEY_AND_TECHNICAL_HISTORY.md` | This document |
| `Complete_MCP_Implementation.docx` | Full project doc for stakeholders |
| `README.md` | Quick start and env reference |
| `.env.example` | All environment variables with comments |

---

## 16. Summary for leadership

**What we set out to do:** Connect Claude to Vtiger for AM daily briefings.

**What we learned along the way:**
- Vtiger API naming differs from UI (Potentials vs Deals)
- Leads module lacks follow-up date field
- Shared API keys cannot secure per-user CRM access
- Microsoft Entra ID is the right auth for `@uniware.net` users
- Claude connector OAuth is server-side, not in Claude’s OAuth form fields

**What works today:**
- AM signs into Claude with Microsoft work account
- Server identifies AM by email — **no owner ID in prompt**
- Each AM sees only their CRM data (Nirmal sees all)
- Deals show customer names, not raw IDs
- Service deployed, monitored, documented

**Repository structure (current):**
```
src/vtiger_mcp/
  main.py              ← Entry point, Azure OAuth, health routes
  config.py            ← All environment settings
  middleware.py        ← API key + JWT pass-through
  auth/users.py        ← Email → Vtiger user, admin scope
  tools/crm.py         ← whoami + get_my_* MCP tools
  vtiger/client.py     ← Vtiger login, queries, normalization
  logging_config.py    ← Logging setup
docs/                  ← Technical and setup documentation
scripts/               ← Testing and doc generation
render.yaml            ← Render deploy blueprint
```

---

*End of document*
