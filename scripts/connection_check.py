"""One-off Vtiger + MCP connection check. Credentials via environment variables only."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys

import httpx

# Allow importing vtiger_mcp when run from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


async def vtiger_login(base_url: str, username: str, access_key: str) -> dict:
    base_url = base_url.rstrip("/")
    url = f"{base_url}/webservice.php"
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        challenge_resp = await client.get(
            url, params={"operation": "getchallenge", "username": username}
        )
        challenge_resp.raise_for_status()
        challenge = challenge_resp.json()
        if not challenge.get("success"):
            return {"ok": False, "step": "getchallenge", "error": challenge}

        token = challenge["result"]["token"]
        generated = hashlib.md5(f"{token}{access_key}".encode()).hexdigest()
        login_resp = await client.post(
            url,
            data={
                "operation": "login",
                "username": username,
                "accessKey": generated,
            },
        )
        login_resp.raise_for_status()
        login = login_resp.json()
        if not login.get("success"):
            return {"ok": False, "step": "login", "error": login}

        session = login["result"]["sessionName"]
        user_id = login["result"].get("userId")
        for module in ("Leads", "Potentials"):
            describe_resp = await client.get(
                url,
                params={
                    "operation": "describe",
                    "sessionName": session,
                    "elementType": module,
                },
            )
            describe = describe_resp.json()
            if not describe.get("success"):
                return {"ok": False, "step": f"describe_{module}", "error": describe}

        sample_resp = await client.get(
            url,
            params={
                "operation": "query",
                "sessionName": session,
                "query": "SELECT id, company, assigned_user_id FROM Leads LIMIT 1;",
            },
        )
        sample = sample_resp.json()
        if not sample.get("success"):
            return {"ok": False, "step": "query_leads", "error": sample}

        return {
            "ok": True,
            "base_url": base_url,
            "user_id": user_id,
            "session_prefix": session[:8] + "...",
            "sample_lead_count": len(sample.get("result") or []),
        }


async def mcp_health(port: int, api_key: str) -> dict:
    base = f"http://127.0.0.1:{port}"
    headers = {"X-API-Key": api_key} if api_key else {}
    async with httpx.AsyncClient(timeout=10.0) as client:
        health = await client.get(f"{base}/health")
        ready = await client.get(f"{base}/ready")
        mcp_probe = await client.get(f"{base}/mcp", headers=headers)
        return {
            "health_status": health.status_code,
            "health_body": health.json() if health.status_code == 200 else health.text[:200],
            "ready_status": ready.status_code,
            "ready_body": ready.json() if "application/json" in ready.headers.get("content-type", "") else ready.text[:200],
            "mcp_status": mcp_probe.status_code,
        }


def main() -> int:
    base_url = os.environ.get("VTIGER_BASE_URL", "").strip()
    username = os.environ.get("VTIGER_USERNAME", "").strip()
    access_key = os.environ.get("VTIGER_ACCESS_KEY", "").strip()
    candidates = os.environ.get("VTIGER_BASE_URL_CANDIDATES", "").strip()

    if not username or not access_key:
        print(json.dumps({"error": "Set VTIGER_USERNAME and VTIGER_ACCESS_KEY"}))
        return 1

    urls: list[str] = []
    if base_url:
        urls.append(base_url)
    if candidates:
        urls.extend(u.strip() for u in candidates.split(",") if u.strip())
    if not urls:
        urls = [
            "https://uniware.odx.vtiger.com",
            "https://uniware.od2.vtiger.com",
            "https://uniware.vtiger.com",
        ]

    async def run() -> dict:
        vtiger_result = None
        attempts: list[dict] = []
        for url in urls:
            try:
                result = await vtiger_login(url, username, access_key)
            except Exception as exc:  # noqa: BLE001 — diagnostic script
                result = {"ok": False, "step": "connection", "error": str(exc)}
            attempts.append({"url": url, **result})
            if result.get("ok"):
                vtiger_result = result
                break
        if not vtiger_result:
            vtiger_result = {"ok": False, "attempts": attempts}

        mcp_result = None
        if os.environ.get("MCP_CHECK", "").lower() in {"1", "true", "yes"}:
            mcp_result = await mcp_health(
                int(os.environ.get("MCP_PORT", "8000")),
                os.environ.get("MCP_API_KEY", "test-key"),
            )
        return {"vtiger": vtiger_result, "mcp": mcp_result}

    out = asyncio.run(run())
    print(json.dumps(out, indent=2))
    return 0 if (out.get("vtiger") or {}).get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
