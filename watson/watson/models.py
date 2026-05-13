"""Data models for Watson triage reports."""
from dataclasses import dataclass, field


@dataclass
class TriageReport:
    issue_key: str
    summary: str
    path_forward: str
    citations: list[str] = field(default_factory=list)
    raw_agent_output: str = ""
    status: str = "ok"  # ok | incomplete | error
