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
from vtiger_mcp.modules import ACCOUNTS, CASES, POTENTIALS, QUOTES, SALESORDER, VTCMSLA
from vtiger_mcp.vtiger.client import VtigerClient, VtigerError, extract_line_items


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
                # Vtiger internal IDs are "<module_number>x<record_number>",
                # e.g. "15x90674". Vtiger's own web UI links use only the
                # numeric record_number after the "x", module is already
                # given as a query param. Confirmed against a real record's
                # own self-reported "url" field during SalesOrder testing:
                # id "15x90674" -> url "...?module=SalesOrder&id=90674".
                # Using the full composite ID here was the deep link bug
                # Ilakkiya hit, "Error from deep link on opening".
                numeric_id = str(record_id).split("x", 1)[-1]
                record["deep_link"] = f"{base_url}/view/detail?module={module_api_name}&id={numeric_id}"

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

        Every record includes a deep_link field. Always show it in your
        reply, for every deal listed, not just a summary or the first one.

        For a vague request like "show my deals" with no further
        qualifier, default to open pipeline (filter sales_stage NOT IN
        ["Closed Won", "Closed Lost", "Dormant", "Dropped"]) rather than
        returning the full historical set, which can run into the hundreds
        of rows. Only return full history if the AM asks for it, or asks
        about a specific past deal or customer.

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

        Every response also includes two plain-language aliases, always
        highlight these two over amount/hdnGrandTotal-style totals, they
        are what actually matters to an AM:
          margin           = forecast_amount, Weighted Revenue, actual profit
          top_line_value    = cf_potentials_toplinevalue, purchase cost set
                               at closure (often null on open deals, that's
                               normal, not missing data)

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

            for record in records:
                if "forecast_amount" in record:
                    record["margin"] = record["forecast_amount"]
                if "cf_potentials_toplinevalue" in record:
                    record["top_line_value"] = record["cf_potentials_toplinevalue"]

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
    async def get_my_orders(
        fields: list[str] | None = None,
        filters: list[dict[str, Any]] | None = None,
        order_by: str | None = None,
        order_direction: str = "asc",
        limit: int | None = None,
        am_email: str | None = None,
    ) -> str:
        """
        Query sales orders (SalesOrder module) for the signed-in Account
        Manager. Order-level data only, no line items, use
        get_order_line_items for a specific order's products/pricing.

        Every record includes a deep_link field. Always show it in your
        reply, for every order listed, not just a summary or the first one.

        Do not ask the user for a Vtiger owner ID. Regular AMs always see
        only their own orders. Admins may pass am_email to view another
        AM's orders, or omit it to view all.

        Default fields, used when `fields` is omitted: order number,
        organisation, sales order date, customer PO date, vendor, final
        margin (the authoritative margin figure, use this not margin_total,
        which is only 33% filled), order total, purchase cost total, linked
        quote, linked deal, status, customer type, owner.

        Every response also includes three plain-language aliases so you
        never have to explain raw Vtiger field names to the AM:
          order_total_customer_pays  = hdnGrandTotal, what the customer is billed
          purchase_cost_from_vendor  = purchase_cost_total, what Uniware paid
                                        the vendor (only ~33% of orders have
                                        this filled, expect nulls, that is
                                        normal, not missing data)
          margin                     = cf_salesorder_finalmargin, the
                                        authoritative bottom line
        purchase cost minus a stated example: bought for 5, sold for 10,
        margin is 5. That is purchase_cost_from_vendor vs
        order_total_customer_pays vs margin, in that order.

        There is no stored total for margin by month/quarter/year, Vtiger
        only stores it per order. Sum cf_salesorder_finalmargin yourself
        after fetching the relevant orders, this is a presentation gap in
        Vtiger, not a missing field.

        filters: list of {"field": ..., "operator": ..., "value": ...},
        combined with AND. Supported operators: =, !=, <, >, <=, >=, IN,
        LIKE, NOTLIKE. To filter by organisation, use field "account_id"
        with your best guess at the name and operator "=" or "LIKE", do NOT
        guess an internal ID, the tool resolves the name for you. Example,
        one customer's order history across years, oldest first:
          filters=[{"field": "account_id", "operator": "LIKE", "value": "Acme"}]
          order_by="cf_salesorder_salesorderdate", order_direction="asc"

        cf_salesorder_vendor is a string, not a lookup, vendor grouping
        needs LIKE/text matching, not exact IDs.

        order_by: field name to sort on. order_direction: "asc" or "desc".
        limit: optional cap on rows returned, applied after sorting.

        Fields available beyond the default set: customer PO number,
        subtotal, credit days (customer and vendor), tax type, created/
        modified by and time, currency, pre-tax total, target dates (SO and
        PO), OEM, is closed, billing/shipping address, order date, customer
        PO to SO delay, PO status, support category, margin_total and
        purchase_cost_total (only ~33% filled, treat as supplementary not
        authoritative), remarks, remarks technical, parking amount
        (mostly historical, largely stopped being used ~2 years ago),
        contact, terms and conditions.
        """
        try:
            user = await get_authenticated_user()
            owner_scope = await resolver.resolve_owner_scope(
                am_email=am_email,
                current_user=user,
            )
            resolved_filters = await client.resolve_org_name_filters(filters, SALESORDER.org_field)
            records = await client.query_module(
                module=SALESORDER.api_name,
                default_fields=SALESORDER.default_fields,
                all_fields=SALESORDER.all_fields,
                fields=fields,
                filters=resolved_filters,
                order_by=order_by,
                order_direction=order_direction,
                limit=limit,
                owner=owner_scope,
                owner_field=SALESORDER.owner_field,
            )
            base_url = get_settings().vtiger_base_url
            requested = set(fields) if fields else set(SALESORDER.default_fields)
            if SALESORDER.org_field in requested:
                await _enrich_org_names(records, SALESORDER.org_field)
            for record in records:
                if "hdnGrandTotal" in record:
                    record["order_total_customer_pays"] = record["hdnGrandTotal"]
                if "purchase_cost_total" in record:
                    record["purchase_cost_from_vendor"] = record["purchase_cost_total"]
                if "cf_salesorder_finalmargin" in record:
                    record["margin"] = record["cf_salesorder_finalmargin"]
            _enrich_deep_links(records, base_url, SALESORDER.api_name)
            return _json_response(
                {
                    "viewer_email": user.email,
                    "is_admin": user.is_admin,
                    "scope": "all" if owner_scope is None else owner_scope,
                    "fields_returned": fields or list(SALESORDER.default_fields),
                    "count": len(records),
                    "orders": records,
                }
            )
        except (AuthError, AccessDenied) as exc:
            return _json_error("get_my_orders", str(exc))
        except VtigerError as exc:
            return _json_error("get_my_orders", str(exc))

    @mcp.tool
    async def get_order_line_items(order_id: str, am_email: str | None = None) -> str:
        """
        Fetch line-item detail (products, quantity, unit price, unit
        purchase cost) for ONE specific sales order, by its Vtiger record
        id (e.g. "11x12345", the `id` field from get_my_orders).

        Use this only after get_my_orders has identified the specific order,
        this cannot be used for bulk/across-many-orders analysis, it is one
        API call per order. Regular AMs can only retrieve an order assigned
        to them, checked before fetching. Admins may pass am_email to
        retrieve on another AM's behalf, or omit it to retrieve any order.

        Returns order header totals plus a clean line-item list: product,
        quantity, unit list price, unit purchase cost, line total purchase
        cost, line margin, margin/markup percentage, section, description.
        unit_purchase_cost is confirmed present directly on each line, do
        not compute it by dividing purchase_cost by quantity.
        """
        try:
            user = await get_authenticated_user()
            owner_scope = await resolver.resolve_owner_scope(
                am_email=am_email,
                current_user=user,
            )
            if owner_scope is not None:
                owned = await client.query_module(
                    module=SALESORDER.api_name,
                    default_fields=("id",),
                    all_fields=SALESORDER.all_fields,
                    fields=["id"],
                    filters=[{"field": "id", "operator": "=", "value": order_id}],
                    owner=owner_scope,
                    owner_field=SALESORDER.owner_field,
                )
                if not owned:
                    raise AccessDenied(
                        f"Order {order_id} was not found or is not assigned to you."
                    )

            raw = await client.retrieve_record(order_id)
            line_items = extract_line_items(raw)
            return _json_response(
                {
                    "viewer_email": user.email,
                    "order_id": order_id,
                    "order_number": raw.get("salesorder_no"),
                    "vendor": raw.get("cf_salesorder_vendor"),
                    "order_total": raw.get("hdnGrandTotal"),
                    "order_margin_total": raw.get("cf_salesorder_finalmargin"),
                    "order_purchase_cost_total": raw.get("purchase_cost_total"),
                    "line_item_count": len(line_items),
                    "line_items": line_items,
                }
            )
        except (AuthError, AccessDenied) as exc:
            return _json_error("get_order_line_items", str(exc))
        except VtigerError as exc:
            return _json_error("get_order_line_items", str(exc))

    @mcp.tool
    async def get_my_quotes(
        fields: list[str] | None = None,
        filters: list[dict[str, Any]] | None = None,
        order_by: str | None = None,
        order_direction: str = "asc",
        limit: int | None = None,
        am_email: str | None = None,
    ) -> str:
        """
        Query quotes (Quotes module) for the signed-in Account Manager.
        Order-level data only, no line items, use get_quote_line_items for
        a specific quote's products/pricing.

        Every record includes a deep_link field. Always show it in your
        reply, for every quote listed, not just a summary or the first one.

        Do not ask the user for a Vtiger owner ID. Regular AMs always see
        only their own quotes. Admins may pass am_email to view another
        AM's quotes, or omit it to view all.

        IMPORTANT on quotestage: AMs never change this manually, Vtiger
        sets it to Accepted automatically when a quote converts to a Sales
        Order. "New" does not mean pending, it means it never converted.
        Do not tell an AM their quote "needs review" based on stage alone.
        Quote win rate = count where quotestage = 'Accepted' divided by
        total quotes for the same filter set, computed client-side, there
        is no stored win-rate field.

        Default fields, used when `fields` is omitted: quote number,
        organisation, linked deal, quote stage, quote date, valid until,
        total, purchase cost total, final margin (proposed margin, compare
        against SalesOrder.cf_salesorder_finalmargin for actual margin
        erosion), margin_total, payment terms, owner.

        Every response also includes three plain-language aliases so you
        never have to explain raw Vtiger field names to the AM:
          order_total_customer_pays  = hdnGrandTotal, what the customer is quoted
          purchase_cost_from_vendor  = purchase_cost_total, what Uniware
                                        would pay the vendor
          margin                     = cf_quotes_finalmargin, the proposed margin

        filters: list of {"field": ..., "operator": ..., "value": ...},
        combined with AND. Supported operators: =, !=, <, >, <=, >=, IN,
        LIKE, NOTLIKE. To filter by organisation, use field "account_id"
        with your best guess at the name and operator "=" or "LIKE", do NOT
        guess an internal ID, the tool resolves the name for you.

        order_by: field name to sort on. order_direction: "asc" or "desc".
        limit: optional cap on rows returned, applied after sorting.

        Fields available beyond the default set: subject, sub total, tax
        type, created/modified by and time, currency, pre-tax total,
        support terms, is closed, billing/shipping address, terms and
        conditions, tax region, purchase_cost_total, margin_percentage_total,
        markup_percentage_total, sync-to-deals flag, contact, annexure,
        parking amount (sparse), descriptions.
        """
        try:
            user = await get_authenticated_user()
            owner_scope = await resolver.resolve_owner_scope(
                am_email=am_email,
                current_user=user,
            )
            resolved_filters = await client.resolve_org_name_filters(filters, QUOTES.org_field)
            records = await client.query_module(
                module=QUOTES.api_name,
                default_fields=QUOTES.default_fields,
                all_fields=QUOTES.all_fields,
                fields=fields,
                filters=resolved_filters,
                order_by=order_by,
                order_direction=order_direction,
                limit=limit,
                owner=owner_scope,
                owner_field=QUOTES.owner_field,
            )
            base_url = get_settings().vtiger_base_url
            requested = set(fields) if fields else set(QUOTES.default_fields)
            if QUOTES.org_field in requested:
                await _enrich_org_names(records, QUOTES.org_field)
            for record in records:
                if "hdnGrandTotal" in record:
                    record["order_total_customer_pays"] = record["hdnGrandTotal"]
                if "purchase_cost_total" in record:
                    record["purchase_cost_from_vendor"] = record["purchase_cost_total"]
                if "cf_quotes_finalmargin" in record:
                    record["margin"] = record["cf_quotes_finalmargin"]
            _enrich_deep_links(records, base_url, QUOTES.api_name)
            return _json_response(
                {
                    "viewer_email": user.email,
                    "is_admin": user.is_admin,
                    "scope": "all" if owner_scope is None else owner_scope,
                    "fields_returned": fields or list(QUOTES.default_fields),
                    "count": len(records),
                    "quotes": records,
                }
            )
        except (AuthError, AccessDenied) as exc:
            return _json_error("get_my_quotes", str(exc))
        except VtigerError as exc:
            return _json_error("get_my_quotes", str(exc))

    @mcp.tool
    async def get_quote_line_items(quote_id: str, am_email: str | None = None) -> str:
        """
        Fetch line-item detail (products, quantity, unit price, unit
        purchase cost) for ONE specific quote, by its Vtiger record id
        (e.g. "13x12345", the `id` field from get_my_quotes).

        Use this only after get_my_quotes has identified the specific
        quote, this cannot be used for bulk/across-many-quotes analysis,
        it is one API call per quote. "What products did we quote this
        customer" is always a per-record lookup, not a list query, set
        that expectation. Regular AMs can only retrieve a quote assigned to
        them, checked before fetching. Admins may pass am_email to retrieve
        on another AM's behalf, or omit it to retrieve any quote.

        Returns quote header totals plus a clean line-item list: product,
        quantity, unit list price, unit purchase cost, line total purchase
        cost, line margin, margin/markup percentage, section, description.
        """
        try:
            user = await get_authenticated_user()
            owner_scope = await resolver.resolve_owner_scope(
                am_email=am_email,
                current_user=user,
            )
            if owner_scope is not None:
                owned = await client.query_module(
                    module=QUOTES.api_name,
                    default_fields=("id",),
                    all_fields=QUOTES.all_fields,
                    fields=["id"],
                    filters=[{"field": "id", "operator": "=", "value": quote_id}],
                    owner=owner_scope,
                    owner_field=QUOTES.owner_field,
                )
                if not owned:
                    raise AccessDenied(
                        f"Quote {quote_id} was not found or is not assigned to you."
                    )

            raw = await client.retrieve_record(quote_id)
            line_items = extract_line_items(raw)
            return _json_response(
                {
                    "viewer_email": user.email,
                    "quote_id": quote_id,
                    "quote_number": raw.get("quote_no"),
                    "quote_stage": raw.get("quotestage"),
                    "quote_total": raw.get("hdnGrandTotal"),
                    "quote_margin_total": raw.get("cf_quotes_finalmargin"),
                    "quote_purchase_cost_total": raw.get("purchase_cost_total"),
                    "line_item_count": len(line_items),
                    "line_items": line_items,
                }
            )
        except (AuthError, AccessDenied) as exc:
            return _json_error("get_quote_line_items", str(exc))
        except VtigerError as exc:
            return _json_error("get_quote_line_items", str(exc))

    @mcp.tool
    async def get_my_accounts(
        fields: list[str] | None = None,
        filters: list[dict[str, Any]] | None = None,
        order_by: str | None = None,
        order_direction: str = "asc",
        limit: int | None = None,
        am_email: str | None = None,
    ) -> str:
        """
        Query organisations (Accounts module, UI label "Organizations") for
        the signed-in Account Manager.

        Every record includes a deep_link field. Always show it in your
        reply, for every organisation listed, not just a summary or the
        first one.

        Do not ask the user for a Vtiger owner ID. Regular AMs always see
        only organisations assigned to them. Admins may pass am_email to
        view another AM's organisations, or omit it to view all.

        CRITICAL, read before answering any "how many customers" question:
        an Accounts record is NOT necessarily a customer. accounttype has
        11 values, only "Customer", "Branch Customer", "Billing Unit
        Customer" are unambiguously customers, "Partner - Customer" is
        partial, everything else (Lead, Sales Qualified Lead, Vendor -
        Supplier, Vendor - OEM, Competitor, Analyst, Unmapped) is NOT a
        customer. Any count, list, or analysis the AM frames around
        "customers" must filter accounttype to the customer values first,
        do not just count all records. This is not optional, get this
        wrong and every number you give the AM is wrong.

        accountstatus is unreliable for "active customer" questions, it
        conflates three unrelated concepts in one field: sales funnel
        (Cold/Warm/Hot/Qualified/Ready to close), lifecycle
        (Active/Inactive), and sentiment (Positive/Neutral/Negative). A
        record marked "Hot" tells you nothing about whether it is active.
        Filtering accountstatus = "Active" is the closest available signal,
        but tell the AM this field is noisy, not filter silently and
        present the result as clean.

        GSTIN (gst_in) is entirely empty, 0.0% across every record, do not
        suggest looking it up here, it does not exist in this data.

        Default fields, used when `fields` is omitted: organisation name,
        type (see customer-type warning above), status (see warning
        above), industry, employee count, billing state, billing postal
        code, owner, profile_score (Vtiger's own account scoring, 91% real
        value, worth surfacing when relevant, nobody has been using it).

        filters: list of {"field": ..., "operator": ..., "value": ...},
        combined with AND. Supported operators: =, !=, <, >, <=, >=, IN,
        LIKE, NOTLIKE. Example, active customers in an industry:
          filters=[{"field": "accounttype", "operator": "IN",
                     "value": ["Customer", "Branch Customer", "Billing Unit Customer"]},
                   {"field": "accountstatus", "operator": "=", "value": "Active"},
                   {"field": "industry", "operator": "=", "value": "Manufacturing"}]

        order_by: field name to sort on. order_direction: "asc" or "desc".
        limit: optional cap on rows returned, applied after sorting.

        Fields available beyond the default set: organisation ID (Vtiger's
        own, not the record id), created/modified by and time, source, is
        converted from lead, profile_rating, is closed, SMS/email/WhatsApp
        opt-in, opt-out, billing GPS coordinates, currency, last contacted
        (via and on, only ~20% filled, declining, do not treat absence as
        meaningful).

        Address fields (city, street, country) and website are excluded
        entirely, all near-zero or zero fill. Do not offer to look up an
        organisation's address or website from this data, it is not there.
        """
        try:
            user = await get_authenticated_user()
            owner_scope = await resolver.resolve_owner_scope(
                am_email=am_email,
                current_user=user,
            )
            records = await client.query_module(
                module=ACCOUNTS.api_name,
                default_fields=ACCOUNTS.default_fields,
                all_fields=ACCOUNTS.all_fields,
                fields=fields,
                filters=filters,
                order_by=order_by,
                order_direction=order_direction,
                limit=limit,
                owner=owner_scope,
                owner_field=ACCOUNTS.owner_field,
            )
            base_url = get_settings().vtiger_base_url
            _enrich_deep_links(records, base_url, ACCOUNTS.api_name)
            return _json_response(
                {
                    "viewer_email": user.email,
                    "is_admin": user.is_admin,
                    "scope": "all" if owner_scope is None else owner_scope,
                    "fields_returned": fields or list(ACCOUNTS.default_fields),
                    "count": len(records),
                    "accounts": records,
                }
            )
        except (AuthError, AccessDenied) as exc:
            return _json_error("get_my_accounts", str(exc))
        except VtigerError as exc:
            return _json_error("get_my_accounts", str(exc))

    @mcp.tool
    async def get_my_cases(
        fields: list[str] | None = None,
        filters: list[dict[str, Any]] | None = None,
        order_by: str | None = None,
        order_direction: str = "asc",
        limit: int | None = None,
        am_email: str | None = None,
    ) -> str:
        """
        Query support tickets (Cases module, UI label "Tickets" / "Support")
        for the signed-in Account Manager. This is the largest module,
        19,000+ records total, always query Cases, never InternalTickets,
        that is a different, unused module.

        Every record includes a deep_link field. Always show it in your
        reply, for every ticket listed, not just a summary or the first one.

        This module is much larger than the others. For a vague request
        like "show my tickets" with no qualifier, default to
        casestatus != 'Closed' rather than pulling the full history, which
        can run into the thousands of rows for an active AM. Do NOT assume
        a specific list of "open" status labels (e.g. "In Progress",
        "Escalated"), those were guessed once and were wrong, confirmed
        casestatus values so far are only 'Closed' and 'Assigned', more may
        exist. "Not Closed" is the safe default regardless of what the
        actual open-state labels turn out to be.

        Do not ask the user for a Vtiger owner ID. Regular AMs always see
        only tickets assigned to them. Admins may pass am_email to view
        another AM's tickets, or omit it to view all.

        THREE TRAPS, do not use the wrong field:
        1. total_time and billable_time are 100% filled and entirely
           ZEROS on every record. They look like "time spent" fields and
           carry nothing. Use time_spent (real, 93% filled) or
           resolution_time (real, 92% filled) instead.
        2. age is 93% filled and entirely zeros. Compute age yourself from
           createdtime if the AM asks how old a ticket is.
        3. cf_cases_actualtimetaken is a STRING, not numeric, despite
           holding time-like values. Do not sum or average it. time_spent
           is the numeric field for aggregation.

        reopen_count and reassign_count are real on only ~3-9% of tickets.
        Meaningful as exception reports ("which tickets were reopened"),
        useless as averages across all tickets, most are genuinely zero.

        Default fields, used when `fields` is omitted: title, case number,
        status, priority, organisation, contact, product, ticket type,
        created time, SLA time elapsed, SLA status, time in current state,
        owner.

        filters: list of {"field": ..., "operator": ..., "value": ...},
        combined with AND. Supported operators: =, !=, <, >, <=, >=, IN,
        LIKE, NOTLIKE. To filter by organisation, use field "parent_id"
        with your best guess at the name and operator "=" or "LIKE", do NOT
        guess an internal ID, the tool resolves the name for you.

        cf_cases_products and cf_cases_type are only populated on tickets
        from roughly the last 2 years (100% recent, 0.0% older), by-product
        volume/time analysis only works on recent tickets, that matches
        what a renewal conversation needs anyway.

        order_by: field name to sort on. order_direction: "asc" or "desc".
        limit: optional cap on rows returned, applied after sorting.

        Fields available beyond the default set: group, created/modified
        by and time, reopen/reassign counts, customer reply flag, from
        portal flag, source, first response target/actual/status,
        resolution due/actual, SLA reference, billable/billed flags,
        category (impact_type), last responded on, description, wait
        count, satisfaction rating (46% filled) and feedback (19%
        filled, treat as supplementary), currency (only ~40% filled,
        declining).
        """
        try:
            user = await get_authenticated_user()
            owner_scope = await resolver.resolve_owner_scope(
                am_email=am_email,
                current_user=user,
            )
            resolved_filters = await client.resolve_org_name_filters(filters, CASES.org_field)
            records = await client.query_module(
                module=CASES.api_name,
                default_fields=CASES.default_fields,
                all_fields=CASES.all_fields,
                fields=fields,
                filters=resolved_filters,
                order_by=order_by,
                order_direction=order_direction,
                limit=limit,
                owner=owner_scope,
                owner_field=CASES.owner_field,
            )
            base_url = get_settings().vtiger_base_url
            requested = set(fields) if fields else set(CASES.default_fields)
            if CASES.org_field in requested:
                await _enrich_org_names(records, CASES.org_field)
            _enrich_deep_links(records, base_url, CASES.api_name)
            return _json_response(
                {
                    "viewer_email": user.email,
                    "is_admin": user.is_admin,
                    "scope": "all" if owner_scope is None else owner_scope,
                    "fields_returned": fields or list(CASES.default_fields),
                    "count": len(records),
                    "cases": records,
                }
            )
        except (AuthError, AccessDenied) as exc:
            return _json_error("get_my_cases", str(exc))
        except VtigerError as exc:
            return _json_error("get_my_cases", str(exc))

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

        Every record includes a deep_link field. Always show it in your
        reply, for every renewal listed, not just a summary or the first one.

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
