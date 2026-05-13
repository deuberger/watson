"""Shared test helpers and fixtures."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

FIXTURES = Path(__file__).parent / "fixtures"


def load_json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def load_text(name: str) -> str:
    return (FIXTURES / name).read_text()


# ---------------------------------------------------------------------------
# Fake MCP types (mirror the real mcp SDK shapes without importing them)
# ---------------------------------------------------------------------------

def make_tool(name: str, description: str):
    return SimpleNamespace(name=name, description=description)


def make_list_tools_result(tools_data: list[dict]):
    tools = [make_tool(t["name"], t["description"]) for t in tools_data]
    return SimpleNamespace(tools=tools)


def make_call_tool_result(text: str):
    content = [SimpleNamespace(text=text)]
    return SimpleNamespace(content=content)


# ---------------------------------------------------------------------------
# Fake MCP session
# ---------------------------------------------------------------------------

def make_mock_session(mcp_responses: dict, tools_data: list[dict]) -> MagicMock:
    """Return a mock MCP ClientSession backed by fixture data."""
    session = MagicMock()

    session.initialize = AsyncMock()
    session.list_tools = AsyncMock(return_value=make_list_tools_result(tools_data))

    async def _call_tool(tool_name: str, arguments: dict):
        # Route by tool name; fall back to empty string
        key = tool_name
        # For issue-specific tools, try key+issue_key variant first
        issue_key = arguments.get("issueKey") or arguments.get("issue_key", "")
        specific = f"{tool_name}_{issue_key}"
        text = mcp_responses.get(specific) or mcp_responses.get(key, "")
        return make_call_tool_result(text)

    session.call_tool = AsyncMock(side_effect=_call_tool)
    return session


# ---------------------------------------------------------------------------
# Fake OpenAI response helpers
# ---------------------------------------------------------------------------

def make_tool_call(id_: str, name: str, arguments: str):
    fn = SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(id=id_, function=fn)


def make_chat_response(content: str | None, tool_calls=None):
    """Build a minimal mock openai ChatCompletion response."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    msg.model_dump.return_value = {
        "role": "assistant",
        "content": content,
        **({"tool_calls": tool_calls} if tool_calls else {}),
    }
    choice = SimpleNamespace(message=msg)
    return SimpleNamespace(choices=[choice])
