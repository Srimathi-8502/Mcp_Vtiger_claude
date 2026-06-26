from __future__ import annotations

import json

from vtiger_mcp.tools.crm import _json_error, _json_response


def test_json_response_serializes_payload() -> None:
    payload = {"count": 2, "items": [{"id": "1"}]}
    result = json.loads(_json_response(payload))
    assert result["count"] == 2
    assert result["items"][0]["id"] == "1"


def test_json_error_shape() -> None:
    result = json.loads(_json_error("whoami", "Sign in is required"))
    assert result == {
        "error": True,
        "tool": "whoami",
        "message": "Sign in is required",
    }


def test_json_response_handles_dates() -> None:
    from datetime import date

    payload = {"as_of_date": date(2026, 6, 25)}
    result = json.loads(_json_response(payload))
    assert result["as_of_date"] == "2026-06-25"
