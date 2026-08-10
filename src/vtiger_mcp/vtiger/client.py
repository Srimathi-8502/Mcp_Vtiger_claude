from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from datetime import date
from typing import Any, Iterable

import httpx

from vtiger_mcp.config import Settings, get_settings

logger = logging.getLogger(__name__)

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")
_SAFE_RECORD_ID = re.compile(r"^[0-9]+x[0-9]+$")
_MAX_RATE_LIMIT_RETRIES = 5
_STALE_SESSION_MARKERS = (
    "session identifier",
    "invalid session",
    "session expired",
    "sessionid",
    "authentication required",
)


def _is_stale_session_error(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in _STALE_SESSION_MARKERS)


class VtigerError(RuntimeError):
    """Raised when Vtiger webservice returns an error response."""


# Confirmed against live Vtiger, 10 Aug 2026 (scripts/test_operators.py).
# IS NULL / IS NOT NULL are NOT supported, do not add them.
_SUPPORTED_OPERATORS = {"=", "!=", "<", ">", "<=", ">=", "IN", "LIKE", "NOTLIKE"}


def _build_filter_clause(filter_: dict[str, Any]) -> str:
    field = _validate_field(str(filter_.get("field", "")))
    operator = str(filter_.get("operator", "")).upper()
    if operator not in _SUPPORTED_OPERATORS:
        raise VtigerError(
            f"Unsupported operator '{operator}'. Supported: {', '.join(sorted(_SUPPORTED_OPERATORS))}"
        )
    value = filter_.get("value")

    if operator == "IN":
        if not isinstance(value, (list, tuple)) or not value:
            raise VtigerError("IN operator requires a non-empty list value")
        quoted_values = ", ".join(_quote(str(item)) for item in value)
        return f"{field} IN ({quoted_values})"

    if value is None:
        raise VtigerError(f"Filter on '{field}' is missing a value")
    return f"{field} {operator} {_quote(str(value))}"


class VtigerClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._session_name: str | None = None

    async def _request(
        self,
        client: httpx.AsyncClient,
        *,
        method: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        delay = 1.0
        for attempt in range(_MAX_RATE_LIMIT_RETRIES + 1):
            response = await client.request(
                method,
                self.settings.vtiger_webservice_url,
                params=params,
                data=data,
            )
            if response.status_code == 429:
                if attempt == _MAX_RATE_LIMIT_RETRIES:
                    response.raise_for_status()
                retry_after = response.headers.get("Retry-After")
                wait_seconds = float(retry_after) if retry_after else delay
                logger.warning(
                    "Vtiger rate limit hit (429), retrying in %.1fs (attempt %s/%s)",
                    wait_seconds, attempt + 1, _MAX_RATE_LIMIT_RETRIES,
                )
                await asyncio.sleep(wait_seconds)
                delay = min(delay * 2, 30.0)
                continue

            response.raise_for_status()
            payload = response.json()
            if not payload.get("success"):
                error = payload.get("error", {})
                message = error.get("message") or error.get("errorMsg") or "Unknown Vtiger error"
                raise VtigerError(message)
            return payload["result"]

        raise VtigerError("Vtiger rate limit exceeded, retries exhausted")

    async def _login(self, client: httpx.AsyncClient) -> str:
        if not self.settings.vtiger_base_url:
            raise VtigerError("VTIGER_BASE_URL is not configured")
        if not self.settings.vtiger_username or not self.settings.vtiger_access_key:
            raise VtigerError("VTIGER_USERNAME and VTIGER_ACCESS_KEY are required")

        challenge = await self._request(
            client,
            method="GET",
            params={
                "operation": "getchallenge",
                "username": self.settings.vtiger_username,
            },
        )
        token = challenge["token"]
        access_key = hashlib.md5(f"{token}{self.settings.vtiger_access_key}".encode()).hexdigest()

        login_result = await self._request(
            client,
            method="POST",
            data={
                "operation": "login",
                "username": self.settings.vtiger_username,
                "accessKey": access_key,
            },
        )
        self._session_name = login_result["sessionName"]
        logger.info("Vtiger session established for user=%s", self.settings.vtiger_username)
        return self._session_name

    def _clear_session(self) -> None:
        self._session_name = None

    async def _get_session(self, client: httpx.AsyncClient) -> str:
        if self._session_name:
            return self._session_name
        return await self._login(client)

    async def _run_query(
        self,
        client: httpx.AsyncClient,
        session_name: str,
        paged_query: str,
    ) -> list[dict[str, Any]]:
        batch = await self._request(
            client,
            method="GET",
            params={
                "operation": "query",
                "sessionName": session_name,
                "query": paged_query,
            },
        )
        return batch or []

    async def query_all(self, query: str) -> list[dict[str, Any]]:
        page_size = max(1, min(self.settings.vtiger_query_page_size, 100))
        timeout = httpx.Timeout(self.settings.vtiger_request_timeout_seconds)

        for attempt in range(2):
            offset = 0
            records: list[dict[str, Any]] = []
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    session_name = await self._get_session(client)
                    while True:
                        base_query = query.rstrip().rstrip(";")
                        paged_query = f"{base_query} LIMIT {offset}, {page_size};"
                        batch = await self._run_query(client, session_name, paged_query)
                        if not batch:
                            break
                        records.extend(batch)
                        if len(batch) < page_size:
                            break
                        offset += page_size
                return records
            except VtigerError as exc:
                if attempt == 0 and _is_stale_session_error(str(exc)):
                    logger.warning("Vtiger session expired; re-authenticating and retrying query")
                    self._clear_session()
                    continue
                raise

        return records

    async def query_module(
        self,
        *,
        module: str,
        default_fields: tuple[str, ...],
        all_fields: tuple[str, ...],
        fields: list[str] | None = None,
        filters: list[dict[str, Any]] | None = None,
        order_by: str | None = None,
        order_direction: str = "asc",
        limit: int | None = None,
        owner: str | None = None,
        owner_field: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Generic, field/filter/sort-driven query against a single Vtiger
        module. No hardcoded WHERE clauses: every filter comes from the
        `filters` argument. The only fixed behaviour is:
          - default_fields is used when `fields` is omitted, to keep vague
            queries small.
          - owner scoping, when `owner` is not None, is always ANDed in and
            cannot be overridden by `filters` (access control, not a filter).

        Every field named in `fields`, `filters`, or `order_by` must be in
        `all_fields` or this raises VtigerError before any request is sent.
        """
        module = _validate_module(module)
        allowed = set(all_fields) | {"id"}

        requested = list(fields) if fields else list(default_fields)
        unknown = [f for f in requested if f not in allowed]
        if unknown:
            raise VtigerError(
                f"Unknown field(s) for {module}: {', '.join(unknown)}. "
                f"Allowed fields: {', '.join(sorted(allowed))}"
            )
        select_fields = ", ".join(
            _validate_field(f) for f in dict.fromkeys(["id", *requested])
        )

        where_parts: list[str] = []
        if owner is not None:
            if not owner_field:
                raise VtigerError(f"{module} has no owner_field configured for scoping")
            where_parts.append(f"{_validate_field(owner_field)} = {_quote(owner)}")

        for filter_ in filters or []:
            field = str(filter_.get("field", ""))
            if field not in allowed:
                raise VtigerError(f"Unknown filter field for {module}: {field}")
            where_parts.append(_build_filter_clause(filter_))

        query = f"SELECT {select_fields} FROM {module}"
        if where_parts:
            query += " WHERE " + " AND ".join(where_parts)
        if order_by:
            if order_by not in allowed:
                raise VtigerError(f"Unknown order_by field for {module}: {order_by}")
            direction = "DESC" if order_direction.lower() == "desc" else "ASC"
            query += f" ORDER BY {_validate_field(order_by)} {direction}"
        query += ";"

        records = await self.query_all(query)
        if limit is not None:
            records = records[:limit]
        return records

    async def resolve_account_ids_by_name(self, name: str) -> list[str]:
        """
        Look up Account record IDs whose name contains `name` (partial match).
        Used to translate an AM's typed organisation name into the internal
        IDs stored on reference fields like cf_vtcmsla_organizationname or
        Potentials.related_to, since those fields hold IDs, not text.
        """
        module = _validate_module(self.settings.vtiger_accounts_module)
        name_field = _validate_field(self.settings.vtiger_field_account_name)
        pattern = name if "%" in name else f"%{name}%"
        query = f"SELECT id FROM {module} WHERE {name_field} LIKE {_quote(pattern)};"
        rows = await self.query_all(query)
        return [str(row["id"]) for row in rows if row.get("id")]

    async def resolve_org_name_filters(
        self,
        filters: list[dict[str, Any]] | None,
        org_field: str | None,
    ) -> list[dict[str, Any]] | None:
        """
        Rewrite any filter on `org_field` from a typed name into an IN
        filter on the matching Account IDs. AMs and Claude should never need
        to know or guess a Vtiger internal ID.
        """
        if not filters or not org_field:
            return filters

        resolved: list[dict[str, Any]] = []
        for filter_ in filters:
            operator = str(filter_.get("operator", "")).upper()
            if filter_.get("field") == org_field and operator in {"=", "LIKE"}:
                name = str(filter_.get("value", ""))
                ids = await self.resolve_account_ids_by_name(name)
                resolved.append(
                    {"field": org_field, "operator": "IN", "value": ids or ["__no_matching_org__"]}
                )
            else:
                resolved.append(filter_)
        return resolved

    async def retrieve_record(self, record_id: str) -> dict[str, Any]:
        """
        Fetch a single record's full detail via Vtiger's `retrieve` operation,
        the only way to get line items (products, unit price, quantity, cost).
        `query` always returns 0.0% on these fields at the module level, this
        is not a data gap, it's an API distinction. One call per record, not
        viable for bulk analytics, only for a specific record the AM named.
        """
        if not _SAFE_RECORD_ID.match(record_id):
            raise VtigerError(f"Invalid record id: {record_id}")

        timeout = httpx.Timeout(self.settings.vtiger_request_timeout_seconds)
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    session_name = await self._get_session(client)
                    return await self._request(
                        client,
                        method="GET",
                        params={
                            "operation": "retrieve",
                            "sessionName": session_name,
                            "id": record_id,
                        },
                    )
            except VtigerError as exc:
                if attempt == 0 and _is_stale_session_error(str(exc)):
                    logger.warning("Vtiger session expired; re-authenticating and retrying retrieve")
                    self._clear_session()
                    continue
                raise
        raise VtigerError("retrieve failed")

    async def list_users(self) -> list[dict[str, Any]]:
        query = "SELECT id, user_name, first_name, last_name, email1, status FROM Users;"
        return await self.query_all(query)

    async def get_leads_by_owner(self, owner: str | None = None) -> list[dict[str, Any]]:
        module = _validate_module(self.settings.vtiger_leads_module)
        fields = ", ".join(_validate_field(field) for field in self.settings.lead_select_fields())
        if owner is None:
            query = f"SELECT {fields} FROM {module};"
        else:
            owner_value = _quote(owner)
            owner_field = _validate_field(self.settings.vtiger_field_lead_owner)
            query = (
                f"SELECT {fields} FROM {module} "
                f"WHERE {owner_field} = {owner_value};"
            )
        raw = await self.query_all(query)
        return [_normalize_lead(record) for record in raw]

    async def get_deals_by_owner(self, owner: str | None = None) -> list[dict[str, Any]]:
        module = _validate_module(self.settings.vtiger_deals_module)
        fields = ", ".join(_validate_field(field) for field in self.settings.deal_select_fields())

        where_parts: list[str] = []
        if owner is not None:
            owner_value = _quote(owner)
            owner_field = _validate_field(self.settings.vtiger_field_deal_owner)
            where_parts.append(f"{owner_field} = {owner_value}")

        open_stages = self.settings.open_deal_stage_list
        if open_stages:
            stage_field = _validate_field(self.settings.vtiger_field_deal_stage)
            stage_values = ", ".join(_quote(stage) for stage in open_stages)
            where_parts.append(f"{stage_field} IN ({stage_values})")

        if where_parts:
            query = f"SELECT {fields} FROM {module} WHERE {' AND '.join(where_parts)};"
        else:
            query = f"SELECT {fields} FROM {module};"
        raw = await self.query_all(query)
        return await self._normalize_deals(raw)

    async def get_overdue_followups(
        self,
        owner: str | None = None,
        *,
        as_of: date | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        as_of = as_of or date.today()
        as_of_value = _quote(as_of.isoformat())

        leads: list[dict[str, Any]] = []
        deals: list[dict[str, Any]] = []

        lead_date_field = self.settings.vtiger_field_lead_followup_date
        if lead_date_field:
            lead_module = _validate_module(self.settings.vtiger_leads_module)
            lead_fields = ", ".join(
                _validate_field(field) for field in self.settings.lead_select_fields()
            )
            lead_date = _validate_field(lead_date_field)
            lead_where = [f"{lead_date} <= {as_of_value}"]
            if owner is not None:
                lead_owner_field = _validate_field(self.settings.vtiger_field_lead_owner)
                lead_where.insert(0, f"{lead_owner_field} = {_quote(owner)}")
            lead_query = (
                f"SELECT {lead_fields} FROM {lead_module} "
                f"WHERE {' AND '.join(lead_where)};"
            )
            leads = [_normalize_lead(record) for record in await self.query_all(lead_query)]

        deal_date_field = self.settings.vtiger_field_deal_followup_date
        if deal_date_field:
            deal_module = _validate_module(self.settings.vtiger_deals_module)
            deal_fields = ", ".join(
                _validate_field(field) for field in self.settings.deal_select_fields()
            )
            deal_date = _validate_field(deal_date_field)
            deal_where = [f"{deal_date} <= {as_of_value}"]
            if owner is not None:
                deal_owner_field = _validate_field(self.settings.vtiger_field_deal_owner)
                deal_where.insert(0, f"{deal_owner_field} = {_quote(owner)}")
            deal_query = (
                f"SELECT {deal_fields} FROM {deal_module} "
                f"WHERE {' AND '.join(deal_where)};"
            )
            deals = await self._normalize_deals(await self.query_all(deal_query))

        return {"leads": leads, "deals": deals}

    async def _normalize_deals(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        account_names = await self._resolve_account_names(
            record.get(self.settings.vtiger_field_deal_org) for record in records
        )
        owner_names = await self._resolve_owner_names(
            record.get(self.settings.vtiger_field_deal_owner) for record in records
        )
        return [_normalize_deal(record, account_names, owner_names) for record in records]

    async def _resolve_owner_names(self, owner_ids: Iterable[Any]) -> dict[str, str]:
        unique: list[str] = []
        seen: set[str] = set()
        for raw_id in owner_ids:
            if not raw_id:
                continue
            owner_id = str(raw_id).strip()
            if owner_id in seen:
                continue
            seen.add(owner_id)
            unique.append(owner_id)

        if not unique:
            return {}

        users = await self.list_users()
        lookup: dict[str, str] = {}
        for row in users:
            user_id = row.get("id")
            if not user_id:
                continue
            display_name = " ".join(
                part for part in [row.get("first_name"), row.get("last_name")] if part
            ).strip()
            if display_name:
                lookup[str(user_id)] = display_name

        return lookup

    async def _resolve_account_names(self, account_ids: Iterable[Any]) -> dict[str, str]:
        unique: list[str] = []
        seen: set[str] = set()
        for raw_id in account_ids:
            if not raw_id:
                continue
            account_id = str(raw_id).strip()
            if not _validate_record_id(account_id) or account_id in seen:
                continue
            seen.add(account_id)
            unique.append(account_id)

        if not unique:
            return {}

        module = _validate_module(self.settings.vtiger_accounts_module)
        name_field = _validate_field(self.settings.vtiger_field_account_name)
        lookup: dict[str, str] = {}
        chunk_size = 50

        for offset in range(0, len(unique), chunk_size):
            chunk = unique[offset : offset + chunk_size]
            id_list = ", ".join(_quote(account_id) for account_id in chunk)
            query = f"SELECT id, {name_field} FROM {module} WHERE id IN ({id_list});"
            for row in await self.query_all(query):
                record_id = row.get("id")
                if record_id:
                    lookup[str(record_id)] = row.get(name_field)

        return lookup


def _validate_module(name: str) -> str:
    if not _SAFE_IDENTIFIER.match(name):
        raise VtigerError(f"Invalid Vtiger module name: {name}")
    return name


def _validate_field(name: str) -> str:
    if not name or not _SAFE_IDENTIFIER.match(name):
        raise VtigerError(f"Invalid Vtiger field name: {name}")
    return name


def _quote(value: str) -> str:
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def _normalize_lead(record: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    return {
        "id": record.get("id"),
        "owner": record.get(settings.vtiger_field_lead_owner),
        "organisation_name": record.get(settings.vtiger_field_lead_org),
        "status": record.get(settings.vtiger_field_lead_status),
        "next_followup_date": record.get(settings.vtiger_field_lead_followup_date),
        "next_followup_description": record.get(settings.vtiger_field_lead_followup_desc),
    }


def _validate_record_id(value: str) -> bool:
    return bool(_SAFE_RECORD_ID.match(value))


def _normalize_deal(
    record: dict[str, Any],
    account_names: dict[str, str] | None = None,
    owner_names: dict[str, str] | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    organisation_id = record.get(settings.vtiger_field_deal_org)
    organisation_name = None
    if organisation_id is not None:
        organisation_id = str(organisation_id)
        organisation_name = (account_names or {}).get(organisation_id)

    owner_id = record.get(settings.vtiger_field_deal_owner)
    owner_name = None
    if owner_id is not None:
        owner_name = (owner_names or {}).get(str(owner_id))

    return {
        # --- Phase 1 original fields ---
        "id": record.get("id"),
        "owner": owner_id,
        "owner_name": owner_name,
        "deal_name": record.get(settings.vtiger_field_deal_name),
        "organisation_id": organisation_id,
        "organisation_name": organisation_name,
        "stage": record.get(settings.vtiger_field_deal_stage),
        "amount": record.get(settings.vtiger_field_deal_amount),
        "last_contacted_date": record.get(settings.vtiger_field_deal_last_contacted),
        "next_followup_date": record.get(settings.vtiger_field_deal_followup_date),
        "next_followup_description": record.get(settings.vtiger_field_deal_followup_desc),
        # --- Phase 1 additions ---
        "expected_close_date": record.get(settings.vtiger_field_deal_close_date),
        "deal_type": record.get(settings.vtiger_field_deal_type),
        "deal_type_subcategory": record.get(settings.vtiger_field_deal_type_subcategory),
        "oem_category": record.get(settings.vtiger_field_deal_oem_category),
        "oem_subcategory": record.get(settings.vtiger_field_deal_oem_subcategory),
        "stage_changed_at": record.get(settings.vtiger_field_deal_stage_changed_at),
        "last_contacted_via": record.get(settings.vtiger_field_deal_last_contacted_via),
        "region": record.get(settings.vtiger_field_deal_region),
    }
