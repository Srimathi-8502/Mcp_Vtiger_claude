import asyncio
import json
import os
import sys

import httpx
from httpx import ASGITransport

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from vtiger_mcp.main import app  # noqa: E402


async def main() -> None:
    api_key = os.environ.get("MCP_API_KEY", "test-connection-key")
    transport = ASGITransport(app=app, lifespan="on")
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/health")
        ready = await client.get("/ready")
        mcp_no_key = await client.get("/mcp")
        mcp_with_key = await client.get("/mcp", headers={"X-API-Key": api_key})
        print(
            json.dumps(
                {
                    "health": {"status": health.status_code, "body": health.text[:500]},
                    "ready": {"status": ready.status_code, "body": ready.text[:500]},
                    "mcp_without_key": {"status": mcp_no_key.status_code},
                    "mcp_with_key": {"status": mcp_with_key.status_code},
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
