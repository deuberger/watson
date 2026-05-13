"""Triage orchestrator – loads MCP config, runs agent per issue, writes output."""
import asyncio
import logging

from watson.mcp_client import jira_mcp_session, list_tools, load_server_config, search_issues, build_jql, _find_search_tool
from watson.agent import run_triage_agent
from watson.output import print_summary, write_report

log = logging.getLogger(__name__)


async def triage_issues(
    issue_keys: list[str],
    components: list[str],
    priorities: list[str],
    project: str | None,
    max_results: int,
) -> None:
    config = load_server_config()

    try:
        async with jira_mcp_session(config) as session:
            tools = await list_tools(session)
            log.debug("Loaded %d Jira MCP tools", len(tools))

            # Resolve issue keys from filters if none provided explicitly
            keys = list(issue_keys)
            if not keys and project:
                jql = build_jql(project, components, priorities)
                tool_name = _find_search_tool(tools) or "searchJiraIssuesUsingJql"
                print(f"🔍  Searching Jira ({project}) with filters…")
                print(f"    Tool : {tool_name}")
                print(f"    JQL  : {jql}")
                keys, raw = await search_issues(
                    session,
                    project=project,
                    components=components,
                    priorities=priorities,
                    max_results=max_results,
                    available_tools=tools,
                )
                if not keys:
                    print("ℹ️   No issues matched the filters.")
                    print("\n── Raw MCP response ──────────────────────────────")
                    print(raw or "(empty response)")
                    print("──────────────────────────────────────────────────")
                    print("\nTip: run `watson tools` to see available tool names.")
                    return
                print(f"    Found {len(keys)} issue(s): {', '.join(keys)}\n")

            for key in keys:
                print(f"⏳  Triaging {key}…")
                try:
                    report = await run_triage_agent(key, session, tools)
                except Exception as exc:
                    log.error("Failed to triage %s: %s", key, exc)
                    print(f"❌  {key} failed: {exc}")
                    continue

                path = write_report(report)
                print_summary(report)
                print(f"📄  Report saved → {path}")

    except FileNotFoundError as exc:
        print(f"❌  {exc}")
        raise SystemExit(1)
    except Exception as exc:
        log.error("MCP session error: %s", exc)
        print(f"❌  MCP error: {exc}")
        raise SystemExit(1)


def run(
    issue_keys: list[str],
    components: list[str] | None = None,
    priorities: list[str] | None = None,
    project: str | None = None,
    max_results: int = 10,
) -> None:
    asyncio.run(triage_issues(
        issue_keys=issue_keys,
        components=components or [],
        priorities=priorities or [],
        project=project,
        max_results=max_results,
    ))
