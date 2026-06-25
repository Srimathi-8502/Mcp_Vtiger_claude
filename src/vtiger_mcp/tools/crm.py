from __future__ import annotations

import json
from datetime import date
from typing import Any

from fastmcp import FastMCP

from vtiger_mcp.auth.users import (
    AccessDenied,
    AuthError,
    get_authenticated_user,
    get_user_resolver,
)
from vtiger_mcp.vtiger.client import VtigerClient, VtigerError


def register_tools(mcp: FastMCP) -> None:
    client = VtigerClient()
    resolver = get_user_resolver()

    @mcp.tool
    async def whoami() -> str:
        """
        Show which Uniware AM account is signed in and what CRM scope they have.

        Use this when you need to confirm the current user's access before briefing.
        """
        try:
            user = await get_authenticated_user()
            return _json_response(
                {
                    "email": user.email,
                    "display_name": user.display_name,
                    "owner_id": user.owner_id,
                    "is_admin": user.is_admin,
                    "scope": "all_am_data" if user.is_admin else "own_data_only",
                }
            )
        except (AuthError, AccessDenied) as exc:
            return _json_error("whoami", str(exc))

    @mcp.tool
    async def get_my_leads(am_email: str | None = None) -> str:
        """
        Fetch leads for the signed-in Account Manager.

        Do not ask the user for a Vtiger owner ID. The server uses their Claude login email.
        Regular AMs always receive only their own leads.
        Admins may pass am_email to view another AM's leads, or omit it to view all leads.
        """
        try:
            user = await get_authenticated_user()
            owner_scope = await resolver.resolve_owner_scope(
                am_email=am_email,
                current_user=user,
            )
            records = await client.get_leads_by_owner(owner_scope)
            return _json_response(
                {
                    "viewer_email": user.email,
                    "is_admin": user.is_admin,
                    "scope": "all" if owner_scope is None else owner_scope,
                    "count": len(records),
                    "leads": records,
                }
            )
        except (AuthError, AccessDenied) as exc:
            return _json_error("get_my_leads", str(exc))
        except VtigerError as exc:
            return _json_error("get_my_leads", str(exc))

    @mcp.tool
    async def get_my_deals(am_email: str | None = None) -> str:
        """
        Fetch deals for the signed-in Account Manager.

        Do not ask the user for a Vtiger owner ID. The server uses their Claude login email.
        Regular AMs always receive only their own deals.
        Admins may pass am_email to view another AM's deals, or omit it to view all deals.
        """
        try:
            user = await get_authenticated_user()
            owner_scope = await resolver.resolve_owner_scope(
                am_email=am_email,
                current_user=user,
            )
            records = await client.get_deals_by_owner(owner_scope)
            return _json_response(
                {
                    "viewer_email": user.email,
                    "is_admin": user.is_admin,
                    "scope": "all" if owner_scope is None else owner_scope,
                    "count": len(records),
                    "deals": records,
                }
            )
        except (AuthError, AccessDenied) as exc:
            return _json_error("get_my_deals", str(exc))
        except VtigerError as exc:
            return _json_error("get_my_deals", str(exc))

    @mcp.tool
    async def get_my_overdue_followups(
        as_of_date: str | None = None,
        am_email: str | None = None,
    ) -> str:
        """
        Return overdue follow-ups for the signed-in Account Manager.

        This is the primary daily briefing tool. Do not ask for a Vtiger owner ID.
        Regular AMs always receive only their own overdue items.
        Admins may pass am_email to view another AM's overdue items, or omit it for all AMs.

        Args:
            as_of_date: Optional ISO date (YYYY-MM-DD). Defaults to server local today.
            am_email: Optional AM email. Admin only.
        """
        try:
            user = await get_authenticated_user()
            owner_scope = await resolver.resolve_owner_scope(
                am_email=am_email,
                current_user=user,
            )
            as_of = date.fromisoformat(as_of_date) if as_of_date else date.today()
            result = await client.get_overdue_followups(owner_scope, as_of=as_of)
            return _json_response(
                {
                    "viewer_email": user.email,
                    "is_admin": user.is_admin,
                    "scope": "all" if owner_scope is None else owner_scope,
                    "as_of_date": as_of.isoformat(),
                    "overdue_lead_count": len(result["leads"]),
                    "overdue_deal_count": len(result["deals"]),
                    "leads": result["leads"],
                    "deals": result["deals"],
                }
            )
        except ValueError:
            return _json_error(
                "get_my_overdue_followups",
                "as_of_date must be ISO format YYYY-MM-DD",
            )
        except (AuthError, AccessDenied) as exc:
            return _json_error("get_my_overdue_followups", str(exc))
        except VtigerError as exc:
            return _json_error("get_my_overdue_followups", str(exc))


def _json_response(payload: dict[str, Any]) -> str:
    return json.dumps(payload, default=str)


def _json_error(tool: str, message: str) -> str:
    return json.dumps({"error": True, "tool": tool, "message": message})
