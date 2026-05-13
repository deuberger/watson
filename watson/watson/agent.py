"""Triage agent – runs tool-use loop against GitHub Copilot API."""
import json
import os
from pathlib import Path

from openai import OpenAI

from watson.models import TriageReport

_SYSTEM_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "synthesis.txt"
_MAX_TURNS = int(os.environ.get("WATSON_MAX_AGENT_TURNS", "20"))


def _load_system_prompt() -> str:
    if _SYSTEM_PROMPT_PATH.exists():
        return _SYSTEM_PROMPT_PATH.read_text()
    # Inline fallback if file not found
    return (
        "You are Watson, an expert product triage assistant.\n"
        "You have access to tools from Jira via MCP. Given a Jira issue key, "
        "gather all relevant context then produce:\n"
        "1. A concise SUMMARY of the request and why it matters.\n"
        "2. A RECOMMENDED PATH FORWARD with specific next steps.\n"
        "3. A SOURCES list of URLs / references used.\n"
        "Be thorough but efficient. Do not fabricate information.\n"
        "Output a Markdown document with sections: ## Summary, "
        "## Recommended Path Forward, ## Sources"
    )


def _build_openai_tools(mcp_tools: list[dict]) -> list[dict]:
    """Convert MCP tool descriptors to OpenAI function-call format."""
    tools = []
    for t in mcp_tools:
        tools.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("inputSchema", {
                    "type": "object",
                    "properties": {
                        "arguments": {
                            "type": "string",
                            "description": "JSON-encoded arguments for the tool",
                        }
                    },
                }),
            },
        })
    return tools


async def run_triage_agent(
    issue_key: str,
    mcp_session,
    mcp_tools: list[dict],
) -> TriageReport:
    """Run the LLM agent loop and return a TriageReport."""
    from watson.mcp_client import call_tool

    client = OpenAI(
        base_url="https://api.githubcopilot.com",
        api_key=os.environ["GITHUB_TOKEN"],
    )
    model = os.environ.get("WATSON_LLM_MODEL", "gpt-4o")

    system_prompt = _load_system_prompt()
    openai_tools = _build_openai_tools(mcp_tools)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Please triage Jira issue: {issue_key}"},
    ]

    raw_output = ""
    turns = 0

    while turns < _MAX_TURNS:
        turns += 1
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=openai_tools if openai_tools else None,
        )

        msg = response.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        # Agent is done – no more tool calls
        if not msg.tool_calls:
            raw_output = msg.content or ""
            break

        # Execute each tool call via MCP and feed results back
        for tc in msg.tool_calls:
            fn = tc.function
            try:
                args = json.loads(fn.arguments) if fn.arguments else {}
            except json.JSONDecodeError:
                args = {}

            try:
                tool_result = await call_tool(mcp_session, fn.name, args)
            except Exception as exc:
                tool_result = f"Error calling {fn.name}: {exc}"

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": tool_result,
            })

    status = "ok" if raw_output else "incomplete"

    # Parse sections out of the Markdown response
    summary = _extract_section(raw_output, "Summary")
    path_forward = _extract_section(raw_output, "Recommended Path Forward")
    citations = _extract_sources(raw_output)

    return TriageReport(
        issue_key=issue_key,
        summary=summary or raw_output[:500],
        path_forward=path_forward,
        citations=citations,
        raw_agent_output=raw_output,
        status=status,
    )


def _extract_section(text: str, heading: str) -> str:
    """Extract text under a ## Heading until the next ## heading."""
    import re
    pattern = rf"##\s+{re.escape(heading)}\s*\n(.*?)(?=\n##\s|\Z)"
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _extract_sources(text: str) -> list[str]:
    """Pull URLs and bullet items from a ## Sources section."""
    import re
    section = _extract_section(text, "Sources")
    if not section:
        return []
    urls = re.findall(r"https?://\S+", section)
    bullets = re.findall(r"^[\-\*]\s+(.+)$", section, re.MULTILINE)
    return urls or bullets
