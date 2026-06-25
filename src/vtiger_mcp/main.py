from __future__ import annotations

import os

from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.responses import JSONResponse

from vtiger_mcp.config import get_settings
from vtiger_mcp.logging_config import configure_logging
from vtiger_mcp.middleware import ApiKeyMiddleware
from vtiger_mcp.tools import register_tools

configure_logging()
settings = get_settings()


def _build_mcp() -> FastMCP:
    if settings.azure_oauth_enabled:
        from fastmcp.server.auth.providers.azure import AzureProvider

        auth = AzureProvider(
            client_id=settings.azure_client_id,
            client_secret=settings.azure_client_secret,
            tenant_id=settings.azure_tenant_id,
            base_url=settings.mcp_public_base_url,
            required_scopes=settings.azure_scope_list,
            additional_authorize_scopes=["openid", "email", "profile"],
        )
        return FastMCP("Uniware Vtiger MCP", version="1.1.0", auth=auth)

    if settings.google_oauth_enabled:
        from fastmcp.server.auth.providers.google import GoogleProvider

        auth = GoogleProvider(
            client_id=settings.google_oauth_client_id,
            client_secret=settings.google_oauth_client_secret,
            base_url=settings.mcp_public_base_url,
            required_scopes=[
                "openid",
                "https://www.googleapis.com/auth/userinfo.email",
            ],
        )
        return FastMCP("Uniware Vtiger MCP", version="1.1.0", auth=auth)

    if settings.mcp_auth_token:
        from fastmcp.server.auth import StaticTokenVerifier

        auth = StaticTokenVerifier(
            tokens={settings.mcp_auth_token: {"sub": "claude-connector", "client_id": "uniware"}}
        )
        return FastMCP("Uniware Vtiger MCP", version="1.1.0", auth=auth)

    return FastMCP("Uniware Vtiger MCP", version="1.1.0")


mcp = _build_mcp()
register_tools(mcp)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(_request):
    return JSONResponse({"status": "healthy", "service": "uniware-vtiger-mcp"})


@mcp.custom_route("/ready", methods=["GET"])
async def readiness_check(_request):
    missing: list[str] = []
    if not settings.vtiger_base_url:
        missing.append("VTIGER_BASE_URL")
    if not settings.vtiger_username:
        missing.append("VTIGER_USERNAME")
    if not settings.vtiger_access_key:
        missing.append("VTIGER_ACCESS_KEY")

    if settings.oauth_enabled:
        if not settings.vtiger_admin_emails.strip():
            missing.append("VTIGER_ADMIN_EMAILS")
    elif not settings.mcp_api_key and not settings.mcp_dev_user_email:
        missing.append(
            "AZURE_* or GOOGLE_OAUTH_* + MCP_PUBLIC_BASE_URL (recommended) or MCP_DEV_USER_EMAIL"
        )

    followup_fields = [
        settings.vtiger_field_lead_followup_date,
        settings.vtiger_field_deal_followup_date,
    ]
    if not any(followup_fields):
        missing.append("VTIGER_FIELD_*_FOLLOWUP_DATE (at least one)")

    status = "ready" if not missing else "degraded"
    code = 200 if status == "ready" else 503
    return JSONResponse(
        {
            "status": status,
            "service": "uniware-vtiger-mcp",
            "oauth_enabled": settings.oauth_enabled,
            "oauth_provider": (
                "azure"
                if settings.azure_oauth_enabled
                else "google"
                if settings.google_oauth_enabled
                else None
            ),
            "missing_configuration": missing,
        },
        status_code=code,
    )


if settings.stateless_http:
    os.environ.setdefault("FASTMCP_STATELESS_HTTP", "true")

app = mcp.http_app(middleware=[Middleware(ApiKeyMiddleware)])


def run() -> None:
    import uvicorn

    uvicorn.run(
        "vtiger_mcp.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "development",
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run()
