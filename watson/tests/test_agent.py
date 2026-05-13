"""Unit tests for the triage agent – mocked MCP session and LLM."""
import json
import pytest
from unittest.mock import MagicMock, patch

from tests.conftest import (
    load_json, load_text, make_mock_session,
    make_chat_response, make_tool_call,
)
from watson.agent import run_triage_agent


MCP_RESPONSES = load_json("mcp_responses.json")
TOOLS_DATA = load_json("mcp_tools.json")["tools"]
LLM_FINAL_RESPONSE = load_text("llm_response.md")


def _make_openai_client(responses: list):
    """Return a mock OpenAI client that yields responses in sequence."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = responses
    return mock_client


@pytest.mark.asyncio
async def test_agent_direct_response(tmp_path, monkeypatch):
    """Agent produces a report when the LLM responds immediately (no tool calls)."""
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("WATSON_OUTPUT_DIR", str(tmp_path))

    session = make_mock_session(MCP_RESPONSES, TOOLS_DATA)
    tools = [{"name": t["name"], "description": t["description"]} for t in TOOLS_DATA]

    mock_client = _make_openai_client([
        make_chat_response(LLM_FINAL_RESPONSE, tool_calls=None),
    ])

    with patch("watson.agent.OpenAI", return_value=mock_client):
        report = await run_triage_agent("PROJ-101", session, tools)

    assert report.issue_key == "PROJ-101"
    assert report.status == "ok"
    assert "PDF" in report.summary
    assert report.path_forward != ""
    assert any("PROJ-101" in c for c in report.citations)


@pytest.mark.asyncio
async def test_agent_tool_call_then_response(tmp_path, monkeypatch):
    """Agent calls a tool first, then produces the final report."""
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("WATSON_OUTPUT_DIR", str(tmp_path))

    session = make_mock_session(MCP_RESPONSES, TOOLS_DATA)
    tools = [{"name": t["name"], "description": t["description"]} for t in TOOLS_DATA]

    tool_call = make_tool_call(
        id_="call_1",
        name="getJiraIssue",
        arguments=json.dumps({"issueKey": "PROJ-101"}),
    )

    mock_client = _make_openai_client([
        # Turn 1: agent calls a tool
        make_chat_response(None, tool_calls=[tool_call]),
        # Turn 2: agent produces final answer
        make_chat_response(LLM_FINAL_RESPONSE, tool_calls=None),
    ])

    with patch("watson.agent.OpenAI", return_value=mock_client):
        report = await run_triage_agent("PROJ-101", session, tools)

    assert report.status == "ok"
    assert "PDF" in report.summary
    # Verify the MCP tool was actually called
    session.call_tool.assert_awaited_once_with(
        "getJiraIssue", arguments={"issueKey": "PROJ-101"}
    )


@pytest.mark.asyncio
async def test_agent_handles_mcp_tool_error(tmp_path, monkeypatch):
    """Agent continues gracefully when an MCP tool call raises an exception."""
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("WATSON_OUTPUT_DIR", str(tmp_path))

    session = make_mock_session(MCP_RESPONSES, TOOLS_DATA)
    session.call_tool.side_effect = RuntimeError("MCP tool unavailable")
    tools = [{"name": t["name"], "description": t["description"]} for t in TOOLS_DATA]

    tool_call = make_tool_call("call_err", "getJiraIssue", json.dumps({"issueKey": "PROJ-101"}))

    mock_client = _make_openai_client([
        make_chat_response(None, tool_calls=[tool_call]),
        make_chat_response(LLM_FINAL_RESPONSE, tool_calls=None),
    ])

    with patch("watson.agent.OpenAI", return_value=mock_client):
        report = await run_triage_agent("PROJ-101", session, tools)

    # Should still produce a report despite the tool error
    assert report.status == "ok"
    assert report.summary != ""


@pytest.mark.asyncio
async def test_agent_incomplete_on_empty_response(tmp_path, monkeypatch):
    """Report is marked incomplete when LLM returns no content."""
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("WATSON_OUTPUT_DIR", str(tmp_path))

    session = make_mock_session(MCP_RESPONSES, TOOLS_DATA)
    tools = []

    mock_client = _make_openai_client([
        make_chat_response("", tool_calls=None),
    ])

    with patch("watson.agent.OpenAI", return_value=mock_client):
        report = await run_triage_agent("PROJ-999", session, tools)

    assert report.status == "incomplete"
