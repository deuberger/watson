"""Unit tests for mcp_client helpers."""
import pytest
from watson.mcp_client import build_jql


class TestBuildJql:
    def test_project_only(self):
        jql = build_jql("PROJ", [], [])
        assert "project = PROJ" in jql
        assert "statusCategory != Done" in jql

    def test_single_priority(self):
        jql = build_jql("PROJ", [], ["High"])
        assert 'priority in ("High")' in jql

    def test_multiple_priorities(self):
        jql = build_jql("PROJ", [], ["High", "Highest"])
        assert '"High"' in jql
        assert '"Highest"' in jql

    def test_single_component(self):
        jql = build_jql("PROJ", ["Reporting"], [])
        assert 'component in ("Reporting")' in jql

    def test_multiple_components(self):
        jql = build_jql("PROJ", ["Auth", "Payments"], ["High"])
        assert '"Auth"' in jql
        assert '"Payments"' in jql

    def test_combined(self):
        jql = build_jql("PROJ", ["Auth"], ["High"])
        assert "project = PROJ" in jql
        assert 'priority in ("High")' in jql
        assert 'component in ("Auth")' in jql
        assert "ORDER BY priority ASC" in jql

    def test_issue_type_filter_not_present(self):
        """issuetype filter was removed to avoid excluding valid issue types."""
        jql = build_jql("PROJ", [], [])
        assert "issuetype" not in jql
