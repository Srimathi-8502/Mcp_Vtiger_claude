from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from vtiger_mcp.config import get_settings


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Validates X-API-Key (briefing spec) and optional Authorization: Bearer."""

    PUBLIC_PATHS = {"/health", "/ready"}

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path.rstrip("/") or "/"
        if path in self.PUBLIC_PATHS:
            return await call_next(request)

        settings = get_settings()
        if not settings.mcp_api_key:
            return await call_next(request)

        provided = request.headers.get("x-api-key", "")
        if not provided:
            auth_header = request.headers.get("authorization", "")
            if auth_header.lower().startswith("bearer "):
                provided = auth_header[7:].strip()

        if provided != settings.mcp_api_key:
            return JSONResponse({"detail": "Invalid or missing API key"}, status_code=401)

        return await call_next(request)
