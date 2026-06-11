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

if settings.mcp_auth_token:
    from fastmcp.server.auth import StaticTokenVerifier

    auth = StaticTokenVerifier(
        tokens={settings.mcp_auth_token: {"sub": "claude-connector", "client_id": "uniware"}}
    )
    mcp = FastMCP("Uniware Vtiger MCP", version="1.0.0", auth=auth)
else:
    mcp = FastMCP("Uniware Vtiger MCP", version="1.0.0")

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
    if not settings.mcp_api_key:
        missing.append("MCP_API_KEY")

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
