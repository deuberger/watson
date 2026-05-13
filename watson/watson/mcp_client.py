"""MCP client – connects to the Atlassian Rovo MCP server via mcp-remote."""
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

log = logging.getLogger(__name__)


def _resolve_env(value: str) -> str:
    """Expand ${VAR} placeholders using the current environment."""
    import re
    return re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), ""), value)


def load_server_config(config_path: str | None = None) -> dict:
    """Load mcp_servers.json, resolving env var placeholders."""
    path = Path(config_path or os.environ.get("WATSON_MCP_CONFIG", "mcp_servers.json"))
    if not path.exists():
        raise FileNotFoundError(f"MCP server config not found: {path}")
    raw = json.loads(path.read_text())
    resolved = {}
    for name, cfg in raw.items():
        resolved[name] = {
            "command": cfg["command"],
            "args": [_resolve_env(a) for a in cfg.get("args", [])],
            "env": {k: _resolve_env(v) for k, v in cfg.get("env", {}).items()},
        }
    return resolved


@asynccontextmanager
async def jira_mcp_session(config: dict):
    """Async context manager yielding a live MCP ClientSession for Jira."""
    jira_cfg = config["jira"]
    server_params = StdioServerParameters(
        command=jira_cfg["command"],
        args=jira_cfg["args"],
        env={**os.environ, **jira_cfg["env"]},
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def list_tools(session: "ClientSession") -> list[dict]:
    """Return all tools available on the given MCP session."""
    result = await session.list_tools()
    return [{"name": t.name, "description": t.description} for t in result.tools]


async def call_tool(session: "ClientSession", tool_name: str, arguments: dict) -> str:
    """Call a named MCP tool and return its text content."""
    result = await session.call_tool(tool_name, arguments=arguments)
    parts = []
    for content in result.content:
        if hasattr(content, "text"):
            parts.append(content.text)
    return "\n".join(parts)


def build_jql(
    project: str,
    components: list[str],
    priorities: list[str],
) -> str:
    """Build a JQL query string from filter parameters."""
    clauses = [f"project = {project}"]

    if priorities:
        plist = ", ".join(f'"{p}"' for p in priorities)
        clauses.append(f"priority in ({plist})")

    if components:
        clist = ", ".join(f'"{c}"' for c in components)
        clauses.append(f"component in ({clist})")

    clauses.append("statusCategory != Done")

    return " AND ".join(clauses) + " ORDER BY priority ASC, created DESC"


def _find_search_tool(tools: list[dict]) -> str | None:
    """Return the name of the JQL/search tool from the available MCP tools."""
    for candidate in ("searchJiraIssuesUsingJql", "search_jira_issues", "jira_search",
                      "searchIssues", "search_issues"):
        if any(t["name"] == candidate for t in tools):
            return candidate
    # Fall back: first tool whose name contains "search" (case-insensitive)
    for t in tools:
        if "search" in t["name"].lower():
            return t["name"]
    return None


async def search_issues(
    session: "ClientSession",
    project: str,
    components: list[str],
    priorities: list[str],
    max_results: int = 10,
    available_tools: list[dict] | None = None,
) -> tuple[list[str], str]:
    """Search Jira via MCP and return (issue_keys, raw_response)."""
    import re

    tool_name = _find_search_tool(available_tools or []) or "searchJiraIssuesUsingJql"
    jql = build_jql(project, components, priorities)

    log.debug("Search tool: %s", tool_name)
    log.debug("JQL: %s", jql)

    result = await call_tool(session, tool_name, {
        "jql": jql,
        "maxResults": max_results,
    })

    log.debug("Raw MCP search response:\n%s", result)

    # Parse issue keys from the returned text (e.g. "PROJ-123", "PROJ-456")
    keys = re.findall(r"\b[A-Z][A-Z0-9]+-\d+\b", result)
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique = [k for k in keys if not (k in seen or seen.add(k))]  # type: ignore[func-returns-value]
    return unique[:max_results], result

