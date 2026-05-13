"""End-to-end smoke test – full pipeline from CLI filters to output file."""
import json
import os
import pytest
from pathlib import Path
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from tests.conftest import (
    load_json, load_text, make_mock_session,
    make_chat_response, make_tool_call,
)


MCP_RESPONSES = load_json("mcp_responses.json")
TOOLS_DATA = load_json("mcp_tools.json")["tools"]
LLM_FINAL_RESPONSE = load_text("llm_response.md")


@pytest.mark.asyncio
async def test_e2e_filter_to_report(tmp_path, monkeypatch):
    """
    Full pipeline: filter by component+priority → search Jira → triage issue
    → write Markdown report to disk.
    No live API calls; all external I/O is mocked.
    """
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("WATSON_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("WATSON_MCP_CONFIG", str(tmp_path / "mcp_servers.json"))

    # Write a minimal mcp_servers.json so load_server_config() doesn't error
    (tmp_path / "mcp_servers.json").write_text(json.dumps({
        "jira": {"command": "npx", "args": [], "env": {}}
    }))

    session = make_mock_session(MCP_RESPONSES, TOOLS_DATA)

    # LLM: one tool call then final answer
    tool_call = make_tool_call(
        "call_1", "getJiraIssue", json.dumps({"issueKey": "PROJ-101"})
    )
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.side_effect = [
        make_chat_response(None, tool_calls=[tool_call]),
        make_chat_response(LLM_FINAL_RESPONSE, tool_calls=None),
    ]

    @asynccontextmanager
    async def _fake_jira_session(_config):
        yield session

    with patch("watson.orchestrator.jira_mcp_session", _fake_jira_session), \
         patch("watson.agent.OpenAI", return_value=mock_openai):

        from watson.orchestrator import triage_issues
        await triage_issues(
            issue_keys=[],
            components=["Reporting"],
            priorities=["High"],
            project="PROJ",
            max_results=10,
        )

    # Report file should exist for PROJ-101
    report_path = tmp_path / "PROJ-101.md"
    assert report_path.exists(), "Report file was not created"

    content = report_path.read_text()
    assert "PROJ-101" in content
    assert "Summary" in content
    assert "Recommended Path Forward" in content
    assert "Sources" in content


@pytest.mark.asyncio
async def test_e2e_explicit_keys(tmp_path, monkeypatch):
    """Full pipeline with explicit issue keys (no filter search step)."""
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("WATSON_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("WATSON_MCP_CONFIG", str(tmp_path / "mcp_servers.json"))

    (tmp_path / "mcp_servers.json").write_text(json.dumps({
        "jira": {"command": "npx", "args": [], "env": {}}
    }))

    session = make_mock_session(MCP_RESPONSES, TOOLS_DATA)

    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value = make_chat_response(
        LLM_FINAL_RESPONSE, tool_calls=None
    )

    @asynccontextmanager
    async def _fake_jira_session(_config):
        yield session

    with patch("watson.orchestrator.jira_mcp_session", _fake_jira_session), \
         patch("watson.agent.OpenAI", return_value=mock_openai):

        from watson.orchestrator import triage_issues
        await triage_issues(
            issue_keys=["PROJ-101"],
            components=[],
            priorities=[],
            project=None,
            max_results=10,
        )

    report_path = tmp_path / "PROJ-101.md"
    assert report_path.exists()
    # search_issues should NOT have been called (no filters)
    for call in session.call_tool.await_args_list:
        assert call.args[0] != "searchJiraIssuesUsingJql"


@pytest.mark.asyncio
async def test_e2e_no_results_from_filter(tmp_path, monkeypatch, capsys):
    """Pipeline exits cleanly when the filter search returns no issues."""
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("WATSON_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("WATSON_MCP_CONFIG", str(tmp_path / "mcp_servers.json"))

    (tmp_path / "mcp_servers.json").write_text(json.dumps({
        "jira": {"command": "npx", "args": [], "env": {}}
    }))

    # Return empty search results
    session = make_mock_session({}, TOOLS_DATA)

    @asynccontextmanager
    async def _fake_jira_session(_config):
        yield session

    mock_openai = MagicMock()

    with patch("watson.orchestrator.jira_mcp_session", _fake_jira_session), \
         patch("watson.agent.OpenAI", return_value=mock_openai):

        from watson.orchestrator import triage_issues
        await triage_issues(
            issue_keys=[],
            components=["Ghost"],
            priorities=["High"],
            project="PROJ",
            max_results=10,
        )

    captured = capsys.readouterr()
    assert "No issues matched" in captured.out
    # No report files should have been written
    assert list(tmp_path.glob("*.md")) == []
