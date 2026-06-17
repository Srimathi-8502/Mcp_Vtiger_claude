from __future__ import annotations

import asyncio
import hashlib
import json
import os

import httpx


async def main() -> None:
    base = os.environ["VTIGER_BASE_URL"].rstrip("/")
    username = os.environ["VTIGER_USERNAME"]
    access_key = os.environ["VTIGER_ACCESS_KEY"]
    url = f"{base}/webservice.php"

    async with httpx.AsyncClient(timeout=60.0) as client:
        ch = (await client.get(url, params={"operation": "getchallenge", "username": username})).json()
        token = ch["result"]["token"]
        key = hashlib.md5(f"{token}{access_key}".encode()).hexdigest()
        login = (
            await client.post(
                url, data={"operation": "login", "username": username, "accessKey": key}
            )
        ).json()
        session = login["result"]["sessionName"]

        out: dict = {"module_check": {}, "raw": {}}
        for module in ("Potentials", "Deals", "Leads"):
            resp = (
                await client.get(
                    url,
                    params={
                        "operation": "describe",
                        "sessionName": session,
                        "elementType": module,
                    },
                )
            ).json()
            out["module_check"][module] = {
                "success": bool(resp.get("success")),
                "error": resp.get("error"),
            }
            if resp.get("success"):
                out["raw"][module] = resp["result"]

        print(json.dumps(out, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
