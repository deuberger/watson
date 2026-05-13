"""Watson CLI entrypoint."""
import logging
import click
from dotenv import load_dotenv

_PRIORITIES = ["Highest", "High", "Medium", "Low", "Lowest"]


@click.group()
def cli() -> None:
    """Watson – product feedback triage assistant."""
    load_dotenv()


@cli.command()
@click.argument("issue_keys", nargs=-1, required=False)
@click.option(
    "--component", "-c",
    multiple=True,
    metavar="COMPONENT",
    help="Filter by Jira component name. Repeatable.",
)
@click.option(
    "--priority", "-p",
    multiple=True,
    type=click.Choice(_PRIORITIES, case_sensitive=False),
    help="Filter by priority. Repeatable.",
)
@click.option(
    "--project", "-j",
    default=None,
    metavar="PROJECT_KEY",
    envvar="JIRA_PROJECT",
    help="Jira project key to search within (required when using filters).",
)
@click.option(
    "--max-results", "-n",
    default=10,
    show_default=True,
    help="Maximum issues to triage when using filters.",
)
@click.option(
    "--debug", is_flag=True,
    help="Print JQL, raw MCP responses, and LLM tool calls.",
)
def triage(
    issue_keys: tuple[str, ...],
    component: tuple[str, ...],
    priority: tuple[str, ...],
    project: str | None,
    max_results: int,
    debug: bool,
) -> None:
    """Triage Jira issues and produce Markdown reports.

    Accepts explicit ISSUE_KEYS or a filter combination of --component /
    --priority. When filtering, --project is required.

    \b
    Examples:
      watson triage PROJ-123 PROJ-456
      watson triage --project PROJ --priority High --priority Highest
      watson triage --project PROJ --component "Auth" --priority High --debug
    """
    from watson.orchestrator import run

    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s: %(message)s",
        force=True,
    )

    if not issue_keys and not (component or priority):
        raise click.UsageError(
            "Provide ISSUE_KEYS or at least one --component / --priority filter."
        )

    if (component or priority) and not project:
        raise click.UsageError(
            "--project is required when using --component or --priority filters."
        )

    run(
        issue_keys=list(issue_keys),
        components=list(component),
        priorities=list(priority),
        project=project,
        max_results=max_results,
    )


@cli.command("tools")
def list_tools_cmd() -> None:
    """List all MCP tools available from the configured servers."""
    import asyncio
    from watson.mcp_client import load_server_config, jira_mcp_session, list_tools

    async def _run():
        config = load_server_config()
        async with jira_mcp_session(config) as session:
            tools = await list_tools(session)
            print(f"\n{len(tools)} tools available:\n")
            for t in tools:
                print(f"  {t['name']}")
                if t.get("description"):
                    print(f"    {t['description'][:80]}")
            print()

    asyncio.run(_run())


def main() -> None:
    cli()
