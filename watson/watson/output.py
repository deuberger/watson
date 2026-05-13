"""Output writer – saves TriageReport to Markdown and prints a stdout summary."""
import os
from pathlib import Path

from watson.models import TriageReport


def write_report(report: TriageReport) -> Path:
    """Write a full Markdown report to output/<KEY>.md and return the path."""
    output_dir = Path(os.environ.get("WATSON_OUTPUT_DIR", "output"))
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{report.issue_key}.md"

    lines = [
        f"# Watson Triage – {report.issue_key}",
        "",
    ]

    if report.status != "ok":
        lines += [f"> ⚠️  Status: `{report.status}`", ""]

    if report.raw_agent_output:
        lines.append(report.raw_agent_output)
    else:
        lines += [
            "## Summary",
            report.summary,
            "",
            "## Recommended Path Forward",
            report.path_forward,
            "",
        ]
        if report.citations:
            lines += ["## Sources", ""]
            for c in report.citations:
                lines.append(f"- {c}")

    out_path.write_text("\n".join(lines))
    return out_path


def print_summary(report: TriageReport) -> None:
    """Print a brief human-readable summary to stdout."""
    status_icon = "✅" if report.status == "ok" else "⚠️"
    print(f"\n{status_icon}  {report.issue_key}")
    print("─" * 60)
    # Print first 3 lines of summary
    summary_lines = report.summary.strip().splitlines()
    for line in summary_lines[:3]:
        print(f"  {line}")
    if len(summary_lines) > 3:
        print("  …")
    print()
