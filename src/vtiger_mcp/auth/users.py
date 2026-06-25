from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache

from fastmcp.server.dependencies import get_access_token

from vtiger_mcp.config import Settings, get_settings
from vtiger_mcp.vtiger.client import VtigerClient, VtigerError

logger = logging.getLogger(__name__)


class AuthError(RuntimeError):
    """Raised when the caller is not authenticated."""


class AccessDenied(RuntimeError):
    """Raised when the caller is not allowed to access the requested data."""


@dataclass(frozen=True)
class AuthenticatedUser:
    email: str
    owner_id: str
    display_name: str | None
    is_admin: bool


@dataclass(frozen=True)
class VtigerUser:
    owner_id: str
    email: str
    display_name: str | None


class UserResolver:
    def __init__(
        self,
        client: VtigerClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.client = client or VtigerClient()
        self.settings = settings or get_settings()
        self._users_by_email: dict[str, VtigerUser] | None = None

    async def _load_users(self) -> dict[str, VtigerUser]:
        if self._users_by_email is not None:
            return self._users_by_email

        rows = await self.client.list_users()
        users: dict[str, VtigerUser] = {}
        for row in rows:
            owner_id = str(row.get("id") or "").strip()
            if not owner_id:
                continue

            emails = {
                str(value).strip().lower()
                for key in ("user_name", "email1")
                for value in [row.get(key)]
                if value and "@" in str(value)
            }
            display_name = " ".join(
                part
                for part in [row.get("first_name"), row.get("last_name")]
                if part
            ).strip() or None

            for email in emails:
                users[email] = VtigerUser(
                    owner_id=owner_id,
                    email=email,
                    display_name=display_name,
                )

        self._users_by_email = users
        logger.info("Loaded %s Vtiger users for access control", len(users))
        return users

    def _admin_emails(self) -> set[str]:
        return {
            email.strip().lower()
            for email in self.settings.vtiger_admin_emails.split(",")
            if email.strip()
        }

    def is_admin_email(self, email: str) -> bool:
        return email.lower() in self._admin_emails()

    async def resolve_email(self, email: str) -> VtigerUser:
        normalized = email.strip().lower()
        users = await self._load_users()
        if normalized not in users:
            raise AccessDenied(
                f"No Vtiger user found for email '{email}'. "
                "Use your Uniware Google / Vtiger login email."
            )
        return users[normalized]

    async def authenticate(self, email: str) -> AuthenticatedUser:
        vtiger_user = await self.resolve_email(email)
        is_admin = self.is_admin_email(email)
        return AuthenticatedUser(
            email=vtiger_user.email,
            owner_id=vtiger_user.owner_id,
            display_name=vtiger_user.display_name,
            is_admin=is_admin,
        )

    async def resolve_owner_scope(
        self,
        *,
        am_email: str | None,
        current_user: AuthenticatedUser,
    ) -> str | None:
        """
        Return an owner ID to filter on, or None for all owners (admin only).

        Regular AMs always receive their own owner ID.
        Admins receive None when am_email is omitted (all data), or a specific owner ID.
        """
        if am_email:
            if not current_user.is_admin:
                raise AccessDenied("Only admins can view another AM's CRM data.")
            return (await self.resolve_email(am_email)).owner_id

        if current_user.is_admin:
            return None

        return current_user.owner_id


@lru_cache
def get_user_resolver() -> UserResolver:
    return UserResolver()


async def get_authenticated_user() -> AuthenticatedUser:
    settings = get_settings()
    token = get_access_token()
    email = None

    if token and token.claims:
        for claim in ("email", "preferred_username", "upn"):
            value = token.claims.get(claim)
            if value and "@" in str(value):
                email = str(value).strip().lower()
                break

    if not email and settings.mcp_dev_user_email:
        email = settings.mcp_dev_user_email.strip().lower()
        logger.warning("Using MCP_DEV_USER_EMAIL fallback for local testing: %s", email)

    if not email:
        raise AuthError(
            "Sign in is required. Connect this MCP server in Claude with Microsoft "
            "or Google OAuth using your @uniware.net work account."
        )

    allowed_domain = settings.allowed_email_domain
    if allowed_domain and not email.endswith(f"@{allowed_domain}"):
        raise AccessDenied(f"Only @{allowed_domain} accounts can use this MCP server.")

    try:
        return await get_user_resolver().authenticate(email)
    except VtigerError as exc:
        raise AuthError(f"Unable to verify Vtiger user: {exc}") from exc
