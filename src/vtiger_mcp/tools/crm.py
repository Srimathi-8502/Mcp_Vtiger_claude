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
from vtiger_mcp.config import get_settings
from vtiger_mcp.modules import POTENTIALS, VTCMSLA
from vtiger_mcp.vtiger.client import VtigerClient, VtigerError


def register_tools(mcp: FastMCP) -> None:
    client = VtigerClient()
    resolver = get_user_resolver()

    async def _enrich_org_names(records: list[dict[str, Any]], org_field: str) -> None:
        account_names = await client._resolve_account_names(
            record.get(org_field) for record in records
        )
        for record in records:
            org_id = record.get(org_field)
            if org_id:
                record[f"{org_field}_name"] = account_names.get(str(org_id))

    def _enrich_deep_links(records: list[dict[str, Any]], base_url: str, module_api_name: str) -> None:
        if not base_url:
            return
        for record in records:
            record_id = record.get("id")
            if record_id:
                record["deep_link"] = f"{base_url}/view/detail?module={module_api_name}&id={record_id}"

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
    async def get_my_deals(
        fields: list[str] | None = None,
        filters: list[dict[str, Any]] | None = None,
        order_by: str | None = None,
        order_direction: str = "asc",
        limit: int | None = None,
        am_email: str | None = None,
    ) -> str:
        """
        Query deals (Potentials module) for the signed-in Account Manager.
        No stage or status is filtered by default, this returns every deal
        assigned to the AM unless `filters` narrows it. Ask for open deals,
        closed deals, a stage, a date range, etc. by filtering explicitly.

        Do not ask the user for a Vtiger owner ID. Regular AMs always see
        only their own deals (by assigned_user_id). Admins may pass am_email
        to view another AM's deals, or omit it to view all.

        Note: deals can have co-owners (cf_potentials_coowners,
        cf_potentials_coowners2) separate from assigned_user_id. This tool
        does not currently scope on co-owner fields, an AM who is a
        co-owner but not the assigned owner will not see that deal here.

        Default fields, used when `fields` is omitted (keep vague or small
        queries small): deal name, Weighted Revenue (forecast_amount, the
        actual profit figure, use this not `amount` unless asked for the
        tax-inclusive figure), amount, top line value, sales stage, time in
        current stage, opportunity type, organisation, contact, owner,
        co-owners, expected close date, probability, created time, next
        follow-up date, next step, lost reason, lead source, OEM category,
        region, last contacted.

        filters: list of {"field": ..., "operator": ..., "value": ...},
        combined with AND. Supported operators: =, !=, <, >, <=, >=, IN,
        LIKE, NOTLIKE. To filter by organisation, use field "related_to"
        with your best guess at the name and operator "=" or "LIKE", do NOT
        try to guess or ask for an internal ID, the tool resolves the name
        to the right record(s) for you and matches partially. Example, open
        pipeline stuck before Value Proposition:
          filters=[{"field": "sales_stage", "operator": "IN",
                     "value": ["New", "Qualifying", "Requirements Gathering",
                               "Demo POC", "To Quote"]}]

        lost_reason is only ~4% filled, do not filter on it, most deals
        simply have none recorded.

        order_by: field name to sort on. order_direction: "asc" or "desc".
        limit: optional cap on rows returned, applied after sorting.

        current_stage_entry_time gives time in the CURRENT stage only,
        Vtiger does not retain full stage history. "Days in Requirements
        Gathering right now" is answerable, "average days New to Value
        Proposition historically" is not.

        Fields available beyond the default set: pipeline, lead source
        subcategory, opportunity type subcategory, campaign source,
        created/modified by and time, last contacted via, OEM subcategory,
        is closed, sub total, grand total, adjusted amount, journey/playbook,
        linked quote, week, forecast category, points, description, lost
        remarks.
        """
        try:
            user = await get_authenticated_user()
            owner_scope = await resolver.resolve_owner_scope(
                am_email=am_email,
                current_user=user,
            )
            resolved_filters = await client.resolve_org_name_filters(filters, POTENTIALS.org_field)
            records = await client.query_module(
                module=POTENTIALS.api_name,
                default_fields=POTENTIALS.default_fields,
                all_fields=POTENTIALS.all_fields,
                fields=fields,
                filters=resolved_filters,
                order_by=order_by,
                order_direction=order_direction,
                limit=limit,
                owner=owner_scope,
                owner_field=POTENTIALS.owner_field,
            )
            settings = get_settings()
            base_url = settings.vtiger_base_url
            requested = set(fields) if fields else set(POTENTIALS.default_fields)

            if POTENTIALS.org_field in requested:
                await _enrich_org_names(records, POTENTIALS.org_field)

            if "assigned_user_id" in requested:
                owner_names = await client._resolve_owner_names(
                    record.get("assigned_user_id") for record in records
                )
                for record in records:
                    owner_id = record.get("assigned_user_id")
                    if owner_id:
                        record["assigned_user_id_name"] = owner_names.get(str(owner_id))

            _enrich_deep_links(records, base_url, POTENTIALS.api_name)

            return _json_response(
                {
                    "viewer_email": user.email,
                    "is_admin": user.is_admin,
                    "scope": "all" if owner_scope is None else owner_scope,
                    "fields_returned": fields or list(POTENTIALS.default_fields),
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

    @mcp.tool
    async def get_my_renewals(
        fields: list[str] | None = None,
        filters: list[dict[str, Any]] | None = None,
        order_by: str | None = None,
        order_direction: str = "asc",
        limit: int | None = None,
        am_email: str | None = None,
    ) -> str:
        """
        Query SLA / warranty / renewal records (vtcmsla module) for the
        signed-in Account Manager. Use this for anything about warranty end
        dates, renewals due, serial numbers, or OEM support status.

        Do not ask the user for a Vtiger owner ID. Regular AMs always see
        only their own records. Admins may pass am_email to view another
        AM's records, or omit it to view all.

        Default fields, used when `fields` is omitted (keep vague or small
        queries small): end date, organisation, linked sales order, status,
        product description, serial number, OEM support, start date.
        Name specific `fields` to get more, or to narrow a wide question.

        filters: list of {"field": ..., "operator": ..., "value": ...},
        combined with AND. Supported operators: =, !=, <, >, <=, >=, IN,
        LIKE, NOTLIKE. To filter by organisation, use field
        "cf_vtcmsla_organizationname" with your best guess at the name and
        operator "=" or "LIKE", do NOT try to guess or ask for an internal
        ID, the tool resolves the name to the right record(s) for you and
        matches partially. Example, renewals due in the next 30 days for a
        named organisation, soonest first:
          filters=[{"field": "cf_vtcmsla_enddate", "operator": ">=", "value": "<today>"},
                   {"field": "cf_vtcmsla_enddate", "operator": "<=", "value": "<today+30>"},
                   {"field": "cf_vtcmsla_organizationname", "operator": "LIKE", "value": "Acme"}]
          order_by="cf_vtcmsla_enddate", order_direction="asc"

        order_by: field name to sort on. order_direction: "asc" or "desc".
        limit: optional cap on rows returned, applied after sorting.

        Fields available beyond the default set: SLA name, SLA number,
        SLA date, assigned owner, created/modified by and time, source,
        Invoice reference, support category, scope of work.
        """
        try:
            user = await get_authenticated_user()
            owner_scope = await resolver.resolve_owner_scope(
                am_email=am_email,
                current_user=user,
            )
            resolved_filters = await client.resolve_org_name_filters(filters, VTCMSLA.org_field)
            records = await client.query_module(
                module=VTCMSLA.api_name,
                default_fields=VTCMSLA.default_fields,
                all_fields=VTCMSLA.all_fields,
                fields=fields,
                filters=resolved_filters,
                order_by=order_by,
                order_direction=order_direction,
                limit=limit,
                owner=owner_scope,
                owner_field=VTCMSLA.owner_field,
            )
            base_url = get_settings().vtiger_base_url
            requested = set(fields) if fields else set(VTCMSLA.default_fields)
            if VTCMSLA.org_field in requested:
                await _enrich_org_names(records, VTCMSLA.org_field)
            _enrich_deep_links(records, base_url, VTCMSLA.api_name)
            return _json_response(
                {
                    "viewer_email": user.email,
                    "is_admin": user.is_admin,
                    "scope": "all" if owner_scope is None else owner_scope,
                    "fields_returned": fields or list(VTCMSLA.default_fields),
                    "count": len(records),
                    "renewals": records,
                }
            )
        except (AuthError, AccessDenied) as exc:
            return _json_error("get_my_renewals", str(exc))
        except VtigerError as exc:
            return _json_error("get_my_renewals", str(exc))


def _json_response(payload: dict[str, Any]) -> str:
    return json.dumps(payload, default=str)


def _json_error(tool: str, message: str) -> str:
    return json.dumps({"error": True, "tool": tool, "message": message})
