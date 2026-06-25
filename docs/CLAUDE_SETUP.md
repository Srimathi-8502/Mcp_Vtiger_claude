# Claude connector setup (per-user access)

This server identifies each Account Manager by their **work email** when they connect Claude. Users do **not** need to type a Vtiger owner ID in the prompt.

**Recommended for Uniware:** **Microsoft Entra ID** (Azure AD), since your team uses **Microsoft 365** (`@uniware.net`).

---

## Access rules

| User | Email example | CRM scope |
|------|---------------|-----------|
| Regular AM | `divya@uniware.net` | Own leads, deals, overdue follow-ups only |
| Admin (Nirmal) | `nirmal@uniware.net` | All AM data; can optionally filter by `am_email` |

Configured via `VTIGER_ADMIN_EMAILS=nirmal@uniware.net`.

---

## MCP tools (no owner ID needed)

| Tool | What it does |
|------|----------------|
| `whoami` | Shows signed-in email and whether user is admin |
| `get_my_leads` | Leads for the signed-in AM |
| `get_my_deals` | Deals for the signed-in AM |
| `get_my_overdue_followups` | Daily briefing for the signed-in AM |

Example Claude prompt:

```
Give me my morning CRM briefing — overdue follow-ups, open deals, and leads.
```

---

## Option A — Microsoft Entra ID (recommended)

Give this section to your **IT / Microsoft 365 admin**.

### 1. Create an App Registration

Azure Portal → **Microsoft Entra ID** → **App registrations** → **New registration**

| Field | Value |
|-------|-------|
| Name | `Uniware Vtiger MCP` |
| Supported account types | **Single tenant** (Uniware only) |
| Redirect URI | Web → `https://mcp-vtiger-claude.onrender.com/auth/callback` |

### 2. Expose an API scope

1. App registration → **Expose an API**
2. Application ID URI: keep default `api://{client-id}`
3. **Add a scope:**
   - Scope name: `mcp-access`
   - Who can consent: Admins and users (or Admins only)
   - Display name: `Access Uniware Vtiger MCP`

### 3. Set access token version 2

App registration → **Manifest** → set:

```json
"api": {
  "requestedAccessTokenVersion": 2
}
```

Save.

### 4. Create a client secret

App registration → **Certificates & secrets** → **New client secret** → copy the value immediately.

### 5. Note these values for Render

From **Overview**:

| Azure value | Render env var |
|-------------|----------------|
| Application (client) ID | `AZURE_CLIENT_ID` |
| Directory (tenant) ID | `AZURE_TENANT_ID` |
| Client secret | `AZURE_CLIENT_SECRET` |

### 6. Control who can use it (IT)

**Option 1 — Entire org (simplest)**  
Enterprise Application → **Properties** → **User assignment required?** = **No**  
→ Any `@uniware.net` user who can sign in to Claude can connect.

**Option 2 — Specific AMs only (recommended)**  
Enterprise Application → **Properties** → **User assignment required?** = **Yes**  
→ **Users and groups** → assign only the Account Managers who should use Claude.

Also grant **admin consent** once:  
Enterprise Application → **Permissions** → **Grant admin consent for Uniware**.

### 7. Server environment variables (Render)

```env
MCP_PUBLIC_BASE_URL=https://mcp-vtiger-claude.onrender.com
AZURE_TENANT_ID=<Directory tenant ID>
AZURE_CLIENT_ID=<Application client ID>
AZURE_CLIENT_SECRET=<client secret>
AZURE_REQUIRED_SCOPES=mcp-access
OAUTH_ALLOWED_DOMAIN=uniware.net
VTIGER_ADMIN_EMAILS=nirmal@uniware.net
MCP_API_KEY=
```

`MCP_PUBLIC_BASE_URL` must match your public HTTPS URL exactly (no trailing slash).

### 8. Register in Claude

1. Claude → **Settings** → **Connectors** → **Add custom connector**
2. **URL:** `https://mcp-vtiger-claude.onrender.com/mcp`
3. **Authentication:** OAuth (Microsoft / work account)
4. Each AM signs in with their **@uniware.net** Microsoft account
5. Enable the connector in a new chat

---

## Option B — Google OAuth (only if Uniware uses Google login)

Use this only if your `@uniware.net` mail actually signs in via Google Workspace.

```env
MCP_PUBLIC_BASE_URL=https://mcp-vtiger-claude.onrender.com
GOOGLE_OAUTH_CLIENT_ID=...
GOOGLE_OAUTH_CLIENT_SECRET=...
GOOGLE_OAUTH_ALLOWED_DOMAIN=uniware.net
```

Redirect URI in Google Cloud: `https://mcp-vtiger-claude.onrender.com/auth/callback`

---

## Claude project instructions

```
You have access to the Uniware Vtiger MCP connector.

- Never ask the user for a Vtiger owner ID.
- Call whoami once if you need to confirm who is signed in.
- For daily briefings, call get_my_overdue_followups, then get_my_deals and get_my_leads.
- The server enforces access: each AM only sees their own CRM data unless they are an admin.
```

---

## How identity maps to Vtiger

1. AM signs in to Claude with Microsoft (`nirmal@uniware.net`)
2. MCP server reads email from the OAuth token (`email`, `preferred_username`, or `upn`)
3. Email is matched to a Vtiger `Users` record
4. That user's owner ID (e.g. `19x6`) is used automatically
5. If email is in `VTIGER_ADMIN_EMAILS`, full CRM access is granted

---

## Local testing (without Claude)

```env
MCP_DEV_USER_EMAIL=dhana@uniware.net
```

```bash
set PYTHONPATH=src
python scripts/test_user_access.py
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "Sign in is required" | Set Azure env vars on Render; reconnect Claude connector |
| Microsoft login works but Claude fails | Redirect URI must be exactly `.../auth/callback`; use FastMCP ≥ 2.13.3 |
| "No Vtiger user found for email" | Vtiger `Users.user_name` must match Microsoft email |
| User denied at login | IT must assign user to Enterprise App (if assignment required) |
| Dhana sees everyone's data | Check `VTIGER_ADMIN_EMAILS` — only Nirmal should be listed |
| `code: Field required` in Claude | Known Claude + Entra edge case; retry connect; verify admin consent |

---

## IT handoff checklist

- [ ] App registration created (single tenant)
- [ ] Redirect URI: `https://mcp-vtiger-claude.onrender.com/auth/callback`
- [ ] Scope `mcp-access` exposed under **Expose an API**
- [ ] `requestedAccessTokenVersion` = `2` in manifest
- [ ] Client secret created and shared securely with dev team
- [ ] Admin consent granted
- [ ] User/group assignment configured (all AMs or selected AMs)
- [ ] Render env vars set (`AZURE_*`, `MCP_PUBLIC_BASE_URL`)
- [ ] `/ready` returns `"oauth_provider": "azure"`
