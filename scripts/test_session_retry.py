"""Verify Vtiger session auto-refresh on stale sessionName."""
from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv

load_dotenv()

from vtiger_mcp.vtiger.client import VtigerClient


async def main() -> int:
    client = VtigerClient()
    owner = os.environ.get("VTIGER_TEST_OWNER", "19x34")

    client._session_name = "stale-invalid-session-id"

    deals = await client.get_deals_by_owner(owner)
    overdue = await client.get_overdue_followups(owner)

    print(
        json.dumps(
            {
                "owner": owner,
                "deals_count": len(deals),
                "overdue_deals_count": len(overdue["deals"]),
                "sample_deal": deals[0] if deals else None,
            },
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
