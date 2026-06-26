from __future__ import annotations

from vtiger_mcp.config import Settings

from .helpers import make_settings


def test_vtiger_base_url_strips_trailing_slash() -> None:
    assert Settings.strip_trailing_slash("https://usp.od2.vtiger.com/") == "https://usp.od2.vtiger.com"


def test_azure_oauth_enabled_when_all_vars_set(base_settings: Settings) -> None:
    assert base_settings.azure_oauth_enabled is True
    assert base_settings.oauth_enabled is True


def test_azure_oauth_disabled_without_public_url() -> None:
    settings = make_settings(
        azure_tenant_id="t",
        azure_client_id="c",
        azure_client_secret="s",
        mcp_public_base_url="",
    )
    assert settings.azure_oauth_enabled is False


def test_azure_scope_list_parses_comma_separated() -> None:
    settings = make_settings(azure_required_scopes="mcp-access, read")
    assert settings.azure_scope_list == ["mcp-access", "read"]


def test_open_deal_stage_list_empty_by_default() -> None:
    settings = make_settings()
    assert settings.open_deal_stage_list == []


def test_open_deal_stage_list_parses_stages() -> None:
    settings = make_settings(vtiger_open_deal_stages="Prospecting, Negotiation")
    assert settings.open_deal_stage_list == ["Prospecting", "Negotiation"]


def test_deal_select_fields_includes_followup_when_configured() -> None:
    settings = make_settings(
        vtiger_field_deal_followup_date="cf_potentials_nextfollowupdate",
        vtiger_field_deal_followup_desc="nextstep",
    )
    fields = settings.deal_select_fields()
    assert "cf_potentials_nextfollowupdate" in fields
    assert "nextstep" in fields


def test_vtiger_webservice_url() -> None:
    settings = make_settings(vtiger_base_url="https://usp.od2.vtiger.com")
    assert settings.vtiger_webservice_url == "https://usp.od2.vtiger.com/webservice.php"
