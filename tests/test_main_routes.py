from __future__ import annotations

from unittest.mock import patch

import pytest
from vtiger_mcp.config import Settings

from .helpers import make_settings


@pytest.mark.anyio
async def test_health_endpoint(oauth_settings: Settings) -> None:
    from httpx import ASGITransport, AsyncClient

    with patch("vtiger_mcp.main.settings", oauth_settings):
        from vtiger_mcp.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["service"] == "uniware-vtiger-mcp"


@pytest.mark.anyio
async def test_ready_endpoint_reports_oauth_enabled(oauth_settings: Settings) -> None:
    from httpx import ASGITransport, AsyncClient

    with patch("vtiger_mcp.main.settings", oauth_settings):
        from vtiger_mcp.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["oauth_enabled"] is True
    assert body["oauth_provider"] == "azure"
    assert body["missing_configuration"] == []


@pytest.mark.anyio
async def test_ready_endpoint_degraded_when_vtiger_missing() -> None:
    from httpx import ASGITransport, AsyncClient

    settings = make_settings(
        vtiger_base_url="",
        vtiger_username="",
        vtiger_access_key="",
    )

    with patch("vtiger_mcp.main.settings", settings):
        from vtiger_mcp.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert "VTIGER_BASE_URL" in body["missing_configuration"]
