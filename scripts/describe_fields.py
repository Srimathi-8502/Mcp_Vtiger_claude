"""List Vtiger field names relevant to Phase 1 MCP tools."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

KEYWORDS = ("follow", "contact", "owner", "assign", "stage", "amount", "company", "status", "potential")


async def main() -> None:
    base = os.environ["VTIGER_BASE_URL"].rstrip("/")
    username = os.environ["VTIGER_USERNAME"]
    access_key = os.environ["VTIGER_ACCESS_KEY"]
    url = f"{base}/webservice.php"

    async with httpx.AsyncClient(timeout=30.0) as client:
        ch = (await client.get(url, params={"operation": "getchallenge", "username": username})).json()
        token = ch["result"]["token"]
        key = hashlib.md5(f"{token}{access_key}".encode()).hexdigest()
        login = (
            await client.post(
                url, data={"operation": "login", "username": username, "accessKey": key}
            )
        ).json()
        session = login["result"]["sessionName"]

        out: dict = {"user_id": login["result"].get("userId")}
        for module in ("Leads", "Potentials"):
            desc = (
                await client.get(
                    url,
                    params={
                        "operation": "describe",
                        "sessionName": session,
                        "elementType": module,
                    },
                )
            ).json()["result"]
            fields = []
            for field in desc.get("fields", []):
                name = field.get("name", "")
                label = field.get("label", "")
                blob = f"{name} {label}".lower()
                if any(k in blob for k in KEYWORDS):
                    fields.append({"name": name, "label": label, "type": field.get("type", {}).get("name")})
            out[module] = fields

        print(json.dumps(out, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
