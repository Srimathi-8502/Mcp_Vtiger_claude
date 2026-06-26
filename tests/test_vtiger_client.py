from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from vtiger_mcp.config import Settings
from vtiger_mcp.vtiger.client import (
    VtigerClient,
    VtigerError,
    _normalize_deal,
    _normalize_lead,
    _quote,
    _validate_field,
    _validate_module,
    _validate_record_id,
)


def test_quote_escapes_single_quotes() -> None:
    assert _quote("19x6") == "'19x6'"
    assert _quote("O'Brien") == "'O''Brien'"


def test_validate_field_rejects_invalid_names() -> None:
    assert _validate_field("assigned_user_id") == "assigned_user_id"
    with pytest.raises(VtigerError, match="Invalid Vtiger field"):
        _validate_field("field; DROP TABLE")


def test_validate_module_rejects_invalid_names() -> None:
    assert _validate_module("Potentials") == "Potentials"
    with pytest.raises(VtigerError, match="Invalid Vtiger module"):
        _validate_module("Potentials;--")


def test_validate_record_id() -> None:
    assert _validate_record_id("19x6") is True
    assert _validate_record_id("invalid") is False


def test_normalize_lead_maps_configured_fields(base_settings: Settings) -> None:
    settings = base_settings.model_copy(
        update={"vtiger_field_lead_followup_desc": "description"}
    )
    with patch("vtiger_mcp.vtiger.client.get_settings", return_value=settings):
        result = _normalize_lead(
            {
                "id": "10x1",
                "assigned_user_id": "19x34",
                "company": "Acme Corp",
                "leadstatus": "Open",
                "description": "Call back next week",
            }
        )
    assert result["owner"] == "19x34"
    assert result["organisation_name"] == "Acme Corp"
    assert result["status"] == "Open"
    assert result["next_followup_description"] == "Call back next week"


def test_normalize_deal_resolves_organisation_name(base_settings: Settings) -> None:
    with patch("vtiger_mcp.vtiger.client.get_settings", return_value=base_settings):
        result = _normalize_deal(
            {
                "id": "5x1",
                "assigned_user_id": "19x6",
                "potentialname": "Big Deal",
                "related_to": "3x99",
                "sales_stage": "Negotiation",
                "amount": "50000",
            },
            account_names={"3x99": "Uniware Customer"},
        )
    assert result["deal_name"] == "Big Deal"
    assert result["organisation_id"] == "3x99"
    assert result["organisation_name"] == "Uniware Customer"


@pytest.mark.anyio
async def test_get_leads_by_owner_builds_owner_filter(base_settings: Settings) -> None:
    client = VtigerClient(settings=base_settings)
    client.query_all = AsyncMock(return_value=[])

    await client.get_leads_by_owner("19x34")

    query = client.query_all.await_args.args[0]
    assert "FROM Leads" in query
    assert "assigned_user_id = '19x34'" in query


@pytest.mark.anyio
async def test_get_leads_by_owner_admin_scope_no_where_clause(
    base_settings: Settings,
) -> None:
    client = VtigerClient(settings=base_settings)
    client.query_all = AsyncMock(return_value=[])

    await client.get_leads_by_owner(None)

    query = client.query_all.await_args.args[0]
    assert "FROM Leads" in query
    assert "WHERE" not in query


@pytest.mark.anyio
async def test_get_deals_by_owner_applies_open_stage_filter() -> None:
    from .helpers import make_settings

    settings = make_settings(
        vtiger_open_deal_stages="Prospecting, Negotiation",
        vtiger_field_deal_followup_date="cf_potentials_nextfollowupdate",
    )
    client = VtigerClient(settings=settings)
    client.query_all = AsyncMock(return_value=[])

    await client.get_deals_by_owner("19x6")

    query = client.query_all.await_args.args[0]
    assert "sales_stage IN ('Prospecting', 'Negotiation')" in query
    assert "assigned_user_id = '19x6'" in query


@pytest.mark.anyio
async def test_query_all_retries_on_stale_session(base_settings: Settings) -> None:
    client = VtigerClient(settings=base_settings)
    client._session_name = "stale-session"

    first_batch = VtigerError("Invalid session identifier")
    second_batch = [{"id": "5x1"}]

    with patch.object(client, "_run_query", new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = [first_batch, second_batch]
        with patch.object(client, "_get_session", new_callable=AsyncMock) as mock_session:
            mock_session.return_value = "fresh-session"
            records = await client.query_all("SELECT id FROM Potentials;")

    assert records == [{"id": "5x1"}]
    assert client._session_name is None or client._session_name == "fresh-session"
