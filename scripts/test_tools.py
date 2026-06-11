import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from vtiger_mcp.vtiger.client import VtigerClient


async def main() -> None:
    client = VtigerClient()
    owner = os.environ.get("VTIGER_TEST_OWNER", "19x1")
    leads = await client.get_leads_by_owner(owner)
    deals = await client.get_deals_by_owner(owner)
    print(
        json.dumps(
            {
                "owner": owner,
                "leads_count": len(leads),
                "deals_count": len(deals),
                "sample_lead": leads[0] if leads else None,
                "sample_deal": deals[0] if deals else None,
            },
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
