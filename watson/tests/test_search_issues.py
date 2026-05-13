"""Unit tests for search_issues – mocked MCP session."""
import json
import pytest
from unittest.mock import AsyncMock

from tests.conftest import load_json, load_text, make_mock_session
from watson.mcp_client import search_issues


MCP_RESPONSES = load_json("mcp_responses.json")
TOOLS_DATA = load_json("mcp_tools.json")["tools"]


@pytest.mark.asyncio
async def test_search_issues_returns_keys():
    session = make_mock_session(MCP_RESPONSES, TOOLS_DATA)
    keys, raw = await search_issues(
        session,
        project="PROJ",
        components=["Reporting"],
        priorities=["High", "Highest"],
        max_results=10,
    )
    assert "PROJ-101" in keys
    assert "PROJ-102" in keys
    assert raw  # raw response should be non-empty


@pytest.mark.asyncio
async def test_search_issues_respects_max_results():
    session = make_mock_session(MCP_RESPONSES, TOOLS_DATA)
    keys, _ = await search_issues(
        session,
        project="PROJ",
        components=[],
        priorities=["High"],
        max_results=1,
    )
    assert len(keys) <= 1


@pytest.mark.asyncio
async def test_search_issues_empty_response():
    session = make_mock_session({}, TOOLS_DATA)
    keys, raw = await search_issues(
        session,
        project="PROJ",
        components=["NonExistentComponent"],
        priorities=["High"],
    )
    assert keys == []
    assert raw == ""
