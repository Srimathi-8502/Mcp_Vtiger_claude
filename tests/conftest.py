from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock

import pytest

from vtiger_mcp.config import Settings, get_settings
from vtiger_mcp.vtiger.client import VtigerClient

from .helpers import make_settings


@pytest.fixture
def base_settings() -> Settings:
    return make_settings()


@pytest.fixture
def oauth_settings(base_settings: Settings) -> Settings:
    return base_settings


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def sample_vtiger_users() -> list[dict]:
    return [
        {
            "id": "19x6",
            "user_name": "nirmal@uniware.net",
            "first_name": "Nirmal",
            "last_name": "Kumar",
            "email1": "nirmal@uniware.net",
        },
        {
            "id": "19x34",
            "user_name": "Divya.k@uniware.net",
            "first_name": "Divya",
            "last_name": "Karunakaran",
            "email1": "Divya.k@uniware.net",
        },
    ]


@pytest.fixture
def mock_vtiger_client(sample_vtiger_users: list[dict]) -> VtigerClient:
    client = VtigerClient()
    client.list_users = AsyncMock(return_value=sample_vtiger_users)
    client.get_leads_by_owner = AsyncMock(return_value=[])
    client.get_deals_by_owner = AsyncMock(return_value=[])
    client.get_overdue_followups = AsyncMock(return_value={"leads": [], "deals": []})
    return client
