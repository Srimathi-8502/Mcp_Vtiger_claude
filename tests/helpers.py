from __future__ import annotations

from vtiger_mcp.config import Settings


def make_settings(**overrides) -> Settings:
    """Build Settings without reading local .env (keeps unit tests isolated)."""
    defaults = {
        "vtiger_base_url": "https://test.vtiger.com",
        "vtiger_username": "api@uniware.net",
        "vtiger_access_key": "test-access-key",
        "vtiger_field_deal_followup_date": "cf_potentials_nextfollowupdate",
        "vtiger_field_deal_last_contacted": "last_contacted_on",
        "vtiger_field_deal_followup_desc": "nextstep",
        "vtiger_admin_emails": "nirmal@uniware.net",
        "mcp_public_base_url": "https://mcp.example.com",
        "azure_tenant_id": "tenant-id",
        "azure_client_id": "client-id",
        "azure_client_secret": "client-secret",
        "oauth_allowed_domain": "uniware.net",
    }
    defaults.update(overrides)
    return Settings.model_construct(**defaults)
