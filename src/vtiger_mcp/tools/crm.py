from __future__ import annotations

import json
from datetime import date
from typing import Any

from fastmcp import FastMCP

from vtiger_mcp.vtiger.client import VtigerClient, VtigerError


def register_tools(mcp: FastMCP) -> None:
    client = VtigerClient()

    @mcp.tool
    async def get_leads_by_owner(owner: str) -> str:
        """
        Fetch all leads assigned to an Account Manager (AM).

        Args:
            owner: Vtiger user ID (e.g. '19x5') or owner identifier agreed with Natasha.

        Returns:
            JSON list of leads with organisation name, status, and follow-up fields.
        """
        try:
            records = await client.get_leads_by_owner(owner)
            return _json_response({"owner": owner, "count": len(records), "leads": records})
        except VtigerError as exc:
            return _json_error("get_leads_by_owner", str(exc))

    @mcp.tool
    async def get_deals_by_owner(owner: str) -> str:
        """
        Fetch open deals (potentials) assigned to an Account Manager (AM).

        Args:
            owner: Vtiger user ID (e.g. '19x5') or owner identifier agreed with Natasha.

        Returns:
            JSON list of deals with stage, amount, last contacted, and follow-up fields.
        """
        try:
            records = await client.get_deals_by_owner(owner)
            return _json_response({"owner": owner, "count": len(records), "deals": records})
        except VtigerError as exc:
            return _json_error("get_deals_by_owner", str(exc))

    @mcp.tool
    async def get_overdue_followups(owner: str, as_of_date: str | None = None) -> str:
        """
        Return leads and deals where next follow-up date is today or earlier.

        This is the primary briefing tool for daily AM action lists.

        Args:
            owner: Vtiger user ID (e.g. '19x5') for the Account Manager.
            as_of_date: Optional ISO date (YYYY-MM-DD). Defaults to server local today.
        """
        try:
            as_of = date.fromisoformat(as_of_date) if as_of_date else date.today()
            result = await client.get_overdue_followups(owner, as_of=as_of)
            return _json_response(
                {
                    "owner": owner,
                    "as_of_date": as_of.isoformat(),
                    "overdue_lead_count": len(result["leads"]),
                    "overdue_deal_count": len(result["deals"]),
                    "leads": result["leads"],
                    "deals": result["deals"],
                }
            )
        except ValueError:
            return _json_error(
                "get_overdue_followups",
                "as_of_date must be ISO format YYYY-MM-DD",
            )
        except VtigerError as exc:
            return _json_error("get_overdue_followups", str(exc))


def _json_response(payload: dict[str, Any]) -> str:
    return json.dumps(payload, default=str)


def _json_error(tool: str, message: str) -> str:
    return json.dumps({"error": True, "tool": tool, "message": message})
