## Summary

PROJ-101 requests PDF export for dashboard reports, driven by stakeholder
sharing needs. The current CSV-only export loses chart formatting, forcing
teams to manually screenshot reports. Multiple teams report this costs ~2 hours
per quarter. A puppeteer-based approach has already been evaluated and deemed
acceptable in terms of performance overhead (~80ms/page).

## Recommended Path Forward

1. **Unblock dependency first** – PROJ-88 (chart rendering refactor) must land
   before PDF work begins to avoid broken stacked bar chart output.
2. **Implement using Puppeteer** – The team has already validated this approach.
   Spike to confirm it works with the current Chart.js version.
3. **Scope the MVP** – Single-page PDF download via an "Export as PDF" button
   on the report view. Defer multi-page reports and scheduled delivery.
4. **Define acceptance criteria with QA** – Confirm chart and table fidelity
   requirements before dev work starts.
5. **Estimate**: M (3–5 days) once PROJ-88 is merged.

## Sources

- https://yourorg.atlassian.net/browse/PROJ-101
- https://yourorg.atlassian.net/browse/PROJ-88
