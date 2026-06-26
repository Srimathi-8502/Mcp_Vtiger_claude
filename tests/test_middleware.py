from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from vtiger_mcp.config import Settings, get_settings
from vtiger_mcp.middleware import ApiKeyMiddleware, _looks_like_jwt


async def _ok(_request):
    return PlainTextResponse("ok")


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MCP_API_KEY", "secret-key")
    get_settings.cache_clear()

    application = Starlette(
        routes=[Route("/mcp", _ok), Route("/health", _ok)],
        middleware=[Middleware(ApiKeyMiddleware)],
    )
    yield application
    get_settings.cache_clear()


@pytest.mark.anyio
async def test_health_is_public(app: Starlette) -> None:
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200


@pytest.mark.anyio
async def test_mcp_requires_api_key(app: Starlette) -> None:
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/mcp")
    assert response.status_code == 401


@pytest.mark.anyio
async def test_mcp_accepts_valid_api_key(app: Starlette) -> None:
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/mcp", headers={"X-API-Key": "secret-key"})
    assert response.status_code == 200


@pytest.mark.anyio
async def test_mcp_passes_jwt_bearer_through(app: Starlette) -> None:
    from httpx import ASGITransport, AsyncClient

    jwt_token = "header.payload.signature"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/mcp", headers={"Authorization": f"Bearer {jwt_token}"})
    assert response.status_code == 200


@pytest.mark.anyio
async def test_well_known_path_is_public(app: Starlette) -> None:
    from httpx import ASGITransport, AsyncClient

    application = Starlette(
        routes=[Route("/.well-known/oauth-protected-resource", _ok)],
        middleware=[Middleware(ApiKeyMiddleware)],
    )
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/.well-known/oauth-protected-resource")
    assert response.status_code == 200


def test_looks_like_jwt() -> None:
    assert _looks_like_jwt("aaa.bbb.ccc") is True
    assert _looks_like_jwt("not-a-jwt") is False
    assert _looks_like_jwt("only.two") is False


@pytest.mark.anyio
async def test_no_api_key_configured_allows_all(monkeypatch: pytest.MonkeyPatch) -> None:
    from httpx import ASGITransport, AsyncClient

    monkeypatch.setenv("MCP_API_KEY", "")
    get_settings.cache_clear()

    application = Starlette(
        routes=[Route("/mcp", _ok)],
        middleware=[Middleware(ApiKeyMiddleware)],
    )
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/mcp")
    assert response.status_code == 200
    get_settings.cache_clear()
