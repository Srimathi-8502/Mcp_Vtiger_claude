"""Exercise user-scoped CRM access with MCP_DEV_USER_EMAIL."""
from __future__ import annotations

import asyncio
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from vtiger_mcp.auth.users import get_authenticated_user, get_user_resolver
from vtiger_mcp.vtiger.client import VtigerClient


async def main() -> None:
    user = await get_authenticated_user()
    resolver = get_user_resolver()
    client = VtigerClient()

    owner_scope = await resolver.resolve_owner_scope(am_email=None, current_user=user)
    leads = await client.get_leads_by_owner(owner_scope)
    deals = await client.get_deals_by_owner(owner_scope)

    print(
        json.dumps(
            {
                "viewer": {
                    "email": user.email,
                    "owner_id": user.owner_id,
                    "is_admin": user.is_admin,
                    "scope": "all" if owner_scope is None else owner_scope,
                },
                "leads_count": len(leads),
                "deals_count": len(deals),
            },
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
