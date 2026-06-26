from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vtiger_mcp.auth.users import (
    AccessDenied,
    AuthError,
    AuthenticatedUser,
    UserResolver,
    get_authenticated_user,
)
from vtiger_mcp.config import Settings
from vtiger_mcp.vtiger.client import VtigerError


@pytest.mark.anyio
async def test_resolve_email_maps_vtiger_user(
    mock_vtiger_client,
    oauth_settings: Settings,
) -> None:
    resolver = UserResolver(client=mock_vtiger_client, settings=oauth_settings)
    user = await resolver.resolve_email("nirmal@uniware.net")
    assert user.owner_id == "19x6"
    assert user.email == "nirmal@uniware.net"


@pytest.mark.anyio
async def test_resolve_email_unknown_user_raises(
    mock_vtiger_client,
    oauth_settings: Settings,
) -> None:
    resolver = UserResolver(client=mock_vtiger_client, settings=oauth_settings)
    with pytest.raises(AccessDenied, match="No Vtiger user found"):
        await resolver.resolve_email("unknown@uniware.net")


@pytest.mark.anyio
async def test_authenticate_marks_admin(
    mock_vtiger_client,
    oauth_settings: Settings,
) -> None:
    resolver = UserResolver(client=mock_vtiger_client, settings=oauth_settings)
    user = await resolver.authenticate("nirmal@uniware.net")
    assert user.is_admin is True
    assert user.owner_id == "19x6"


@pytest.mark.anyio
async def test_authenticate_regular_am_not_admin(
    mock_vtiger_client,
    oauth_settings: Settings,
) -> None:
    resolver = UserResolver(client=mock_vtiger_client, settings=oauth_settings)
    user = await resolver.authenticate("divya.k@uniware.net")
    assert user.is_admin is False
    assert user.owner_id == "19x34"


@pytest.mark.anyio
async def test_resolve_owner_scope_regular_user_own_data(
    mock_vtiger_client,
    oauth_settings: Settings,
) -> None:
    resolver = UserResolver(client=mock_vtiger_client, settings=oauth_settings)
    current = AuthenticatedUser(
        email="divya.k@uniware.net",
        owner_id="19x34",
        display_name="Divya",
        is_admin=False,
    )
    scope = await resolver.resolve_owner_scope(am_email=None, current_user=current)
    assert scope == "19x34"


@pytest.mark.anyio
async def test_resolve_owner_scope_admin_all_data(
    mock_vtiger_client,
    oauth_settings: Settings,
) -> None:
    resolver = UserResolver(client=mock_vtiger_client, settings=oauth_settings)
    current = AuthenticatedUser(
        email="nirmal@uniware.net",
        owner_id="19x6",
        display_name="Nirmal",
        is_admin=True,
    )
    scope = await resolver.resolve_owner_scope(am_email=None, current_user=current)
    assert scope is None


@pytest.mark.anyio
async def test_resolve_owner_scope_admin_filter_by_email(
    mock_vtiger_client,
    oauth_settings: Settings,
) -> None:
    resolver = UserResolver(client=mock_vtiger_client, settings=oauth_settings)
    current = AuthenticatedUser(
        email="nirmal@uniware.net",
        owner_id="19x6",
        display_name="Nirmal",
        is_admin=True,
    )
    scope = await resolver.resolve_owner_scope(
        am_email="divya.k@uniware.net",
        current_user=current,
    )
    assert scope == "19x34"


@pytest.mark.anyio
async def test_resolve_owner_scope_non_admin_cannot_filter_others(
    mock_vtiger_client,
    oauth_settings: Settings,
) -> None:
    resolver = UserResolver(client=mock_vtiger_client, settings=oauth_settings)
    current = AuthenticatedUser(
        email="divya.k@uniware.net",
        owner_id="19x34",
        display_name="Divya",
        is_admin=False,
    )
    with pytest.raises(AccessDenied, match="Only admins"):
        await resolver.resolve_owner_scope(am_email="nirmal@uniware.net", current_user=current)


@pytest.mark.anyio
async def test_get_authenticated_user_uses_dev_email_fallback(
    mock_vtiger_client,
    oauth_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = oauth_settings.model_copy(update={"mcp_dev_user_email": "divya.k@uniware.net"})
    resolver = UserResolver(client=mock_vtiger_client, settings=settings)

    with patch("vtiger_mcp.auth.users.get_access_token", return_value=None), patch(
        "vtiger_mcp.auth.users.get_user_resolver",
        return_value=resolver,
    ), patch("vtiger_mcp.auth.users.get_settings", return_value=settings):
        user = await get_authenticated_user()

    assert user.email == "divya.k@uniware.net"
    assert user.owner_id == "19x34"


@pytest.mark.anyio
async def test_get_authenticated_user_rejects_wrong_domain(
    mock_vtiger_client,
    oauth_settings: Settings,
) -> None:
    settings = oauth_settings.model_copy(update={"mcp_dev_user_email": "user@gmail.com"})
    resolver = UserResolver(client=mock_vtiger_client, settings=settings)

    with patch("vtiger_mcp.auth.users.get_access_token", return_value=None), patch(
        "vtiger_mcp.auth.users.get_user_resolver",
        return_value=resolver,
    ), patch("vtiger_mcp.auth.users.get_settings", return_value=settings):
        with pytest.raises(AccessDenied, match="uniware.net"):
            await get_authenticated_user()


@pytest.mark.anyio
async def test_get_authenticated_user_requires_sign_in(oauth_settings: Settings) -> None:
    settings = oauth_settings.model_copy(update={"mcp_dev_user_email": ""})

    with patch("vtiger_mcp.auth.users.get_access_token", return_value=None), patch(
        "vtiger_mcp.auth.users.get_settings",
        return_value=settings,
    ):
        with pytest.raises(AuthError, match="Sign in is required"):
            await get_authenticated_user()


@pytest.mark.anyio
async def test_get_authenticated_user_reads_email_from_token_claims(
    mock_vtiger_client,
    oauth_settings: Settings,
) -> None:
    token = MagicMock()
    token.claims = {"preferred_username": "nirmal@uniware.net"}
    resolver = UserResolver(client=mock_vtiger_client, settings=oauth_settings)

    with patch("vtiger_mcp.auth.users.get_access_token", return_value=token), patch(
        "vtiger_mcp.auth.users.get_user_resolver",
        return_value=resolver,
    ), patch("vtiger_mcp.auth.users.get_settings", return_value=oauth_settings):
        user = await get_authenticated_user()

    assert user.email == "nirmal@uniware.net"
    assert user.is_admin is True


@pytest.mark.anyio
async def test_get_authenticated_user_wraps_vtiger_error(
    mock_vtiger_client,
    oauth_settings: Settings,
) -> None:
    mock_vtiger_client.list_users = AsyncMock(side_effect=VtigerError("login failed"))
    resolver = UserResolver(client=mock_vtiger_client, settings=oauth_settings)
    settings = oauth_settings.model_copy(update={"mcp_dev_user_email": "nirmal@uniware.net"})

    with patch("vtiger_mcp.auth.users.get_access_token", return_value=None), patch(
        "vtiger_mcp.auth.users.get_user_resolver",
        return_value=resolver,
    ), patch("vtiger_mcp.auth.users.get_settings", return_value=settings):
        with pytest.raises(AuthError, match="Unable to verify Vtiger user"):
            await get_authenticated_user()
