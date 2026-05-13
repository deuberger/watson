"""Watson CLI entrypoint."""
import logging
import click
from dotenv import load_dotenv

_PRIORITIES = ["Highest", "High", "Medium", "Low", "Lowest"]


@click.group()
@click.option("--debug", is_flag=True, help="Enable debug logging.")
def cli(debug: bool) -> None:
    """Watson – product feedback triage assistant."""
    load_dotenv()
    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


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
    help="Filter by priority. Repeatable. Defaults to High+Highest when filtering.",
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
def triage(
    issue_keys: tuple[str, ...],
    component: tuple[str, ...],
    priority: tuple[str, ...],
    project: str | None,
    max_results: int,
) -> None:
    """Triage Jira issues and produce Markdown reports.

    Accepts explicit ISSUE_KEYS or a filter combination of --component /
    --priority. When filtering, --project is required.

    \b
    Examples:
      watson triage PROJ-123 PROJ-456
      watson triage --project PROJ --priority High --priority Highest
      watson triage --project PROJ --component "Auth" --priority High
    """
    from watson.orchestrator import run

    if not issue_keys and not (component or priority):
        raise click.UsageError(
            "Provide ISSUE_KEYS or at least one --component / --priority filter."
        )

    if (component or priority) and not project:
        raise click.UsageError(
            "--project is required when using --component or --priority filters."
        )

    # Default priorities when only component is given
    effective_priorities = list(priority) or (["High", "Highest"] if component else [])

    run(
        issue_keys=list(issue_keys),
        components=list(component),
        priorities=effective_priorities,
        project=project,
        max_results=max_results,
    )


def main() -> None:
    cli()
