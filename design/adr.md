# Watson – Architecture Design Record (ADR)

**Status:** Draft  
**Context:** prompts/shared-objectives.txt, prompts/architect.txt

---

## 1. Overview

Watson is a CLI tool that, given one or more Jira issue keys, uses an AI agent
to gather context from Jira, Mattermost, Google Docs, and GitHub via MCP
servers, then synthesizes everything into a triage report with a summary and
recommended path forward (Markdown, one file per issue).

All external integrations are MCP servers — the agent decides which tools to
call and in what order. Watson's job is to configure the MCP servers, invoke
the agent, and write the output.

The PoC optimises for speed-to-demo. Every design decision below favours the
simplest option that could work; nothing is irreversible at this scale.

---

## 2. Component Diagram

```
┌─────────────────────────────────────────────────────┐
│                     CLI entrypoint                  │
│   watson triage <ISSUE-KEY> [<ISSUE-KEY> ...]        │
└───────────────────────┬─────────────────────────────┘
                        │ issue keys
                        ▼
┌─────────────────────────────────────────────────────┐
│                  Triage Orchestrator                │
│  - iterates issues                                  │
│  - spins up MCP servers                             │
│  - invokes Triage Agent with tools + system prompt  │
│  - writes output                                    │
└───────────────────────┬─────────────────────────────┘
                        │ system prompt + issue key
                        ▼
┌─────────────────────────────────────────────────────┐
│                   Triage Agent (LLM)                │
│  - autonomously decides which tools to call         │
│  - iterates until sufficient context gathered       │
│  - produces: summary + recommended path forward     │
└──┬──────────┬──────────┬──────────┬─────────────────┘
   │          │          │          │  MCP tool calls
   ▼          ▼          ▼          ▼
┌──────┐ ┌────────┐ ┌────────┐ ┌────────┐
│ Jira │ │  Mat-  │ │Google  │ │ GitHub │
│ MCP  │ │termost │ │ Drive  │ │  MCP   │
│Server│ │  MCP   │ │  MCP   │ │ Server │
│      │ │ Server │ │ Server │ │        │
└──────┘ └────────┘ └────────┘ └────────┘
   │          │          │          │
   └──────────┴──────────┴──────────┘
                        │ tool results
                        ▼
            ┌───────────────────────┐
            │     Output Writer     │
            │  output/<KEY>.md      │
            │  stdout summary       │
            └───────────────────────┘
```

---

## 3. Technology Choices

| Concern | Choice | Rationale |
|---|---|---|
| Language | Python 3.11+ | Fastest path for LLM SDKs and MCP client support |
| Package manager | `uv` | Fast, single-file lockfile, easy PoC setup |
| MCP client | `mcp` Python SDK | Official SDK; spawns servers as subprocesses, handles protocol |
| Jira MCP server | `mcp-server-jira` (or equivalent) | Exposes Jira tools over MCP |
| Mattermost MCP server | `mcp-server-mattermost` (or equivalent) | Exposes Mattermost search/read tools |
| Google Drive MCP server | `mcp-server-gdrive` (or equivalent) | Exposes Drive/Docs search and read tools |
| GitHub MCP server | `github/github-mcp-server` | Official GitHub MCP server |
| Agent / LLM SDK | `anthropic` (Claude) or `openai` (GPT-4o) | Both support tool-use natively; swap via env var |
| Config | `python-dotenv` + env vars | `.env` file; no secrets in code |
| Output | Markdown files + stdout | Zero dependencies; easy to inspect |
| Testing | `pytest` + MCP server mocks | Fake MCP servers return fixture data for unit tests |

---

## 4. Data Model

The agent works directly with raw MCP tool results; there is no intermediate
collector data model. The only structured types Watson owns are:

```python
@dataclass
class TriageReport:
    issue_key: str
    summary: str           # synthesized description of the request and why it matters
    path_forward: str      # agent's recommended next steps / approach
    citations: list[str]   # source URLs referenced in the report
    raw_agent_output: str  # full agent response for debugging
```

---

## 5. MCP Server Configuration

Each MCP server is launched as a subprocess by the `mcp` Python SDK. Servers
are defined in a `mcp_servers.json` config file (path set via
`WATSON_MCP_CONFIG`):

```json
{
  "jira": {
    "command": "npx",
    "args": ["-y", "mcp-server-jira"],
    "env": {
      "JIRA_URL": "${JIRA_URL}",
      "JIRA_API_TOKEN": "${JIRA_API_TOKEN}"
    }
  },
  "mattermost": {
    "command": "npx",
    "args": ["-y", "mcp-server-mattermost"],
    "env": {
      "MM_URL": "${MM_URL}",
      "MM_TOKEN": "${MM_TOKEN}",
      "MM_CHANNEL_IDS": "${MM_CHANNEL_IDS}"
    }
  },
  "gdrive": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-gdrive"],
    "env": {
      "GOOGLE_SERVICE_ACCOUNT_FILE": "${GOOGLE_SERVICE_ACCOUNT_FILE}",
      "GOOGLE_DRIVE_FOLDER_ID": "${GOOGLE_DRIVE_FOLDER_ID}"
    }
  },
  "github": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-github"],
    "env": {
      "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"
    }
  }
}
```

Watson resolves `${VAR}` placeholders from the environment at startup.

---

## 6. Triage Agent

### Role
The agent is an LLM running in a tool-use loop. It receives a system prompt
(`prompts/synthesis.txt`) and the Jira issue key, then autonomously decides
which MCP tools to call, iterates until it has sufficient context, and produces
the final report.

### System Prompt (prompts/synthesis.txt)
```
You are Watson, an expert product triage assistant.

You have access to tools from four systems: Jira, Mattermost, Google Drive,
and GitHub. Given a Jira issue key for a high-priority product improvement
request, your job is to:

1. Gather all relevant context from the available tools.
2. Synthesize a concise SUMMARY of what is being requested and why it matters.
3. Produce a clear RECOMMENDED PATH FORWARD — specific next steps the team
   should take to act on this request, including any open questions to resolve.
4. Cite every source (URL or reference) you used.

Be thorough but efficient: gather enough context to give confident
recommendations, then stop. Do not fabricate information not present in the
tools' responses.

Output your final answer as a Markdown document with the following sections:
## Summary
## Recommended Path Forward
## Sources
```

### Agent Loop
```
orchestrator
  → start MCP servers
  → for each issue key:
      → run agent(system_prompt, issue_key, tools=all_mcp_tools)
      → agent calls tools until satisfied
      → agent emits final Markdown response
      → output writer saves output/<KEY>.md
  → stop MCP servers
```

### Tool Visibility
All tools from all four MCP servers are exposed to the agent simultaneously.
The agent is responsible for choosing which to call — no pre-filtering.

---

## 7. Error Handling

| Scenario | Behaviour |
|---|---|
| MCP server fails to start | Log error; skip that server's tools; agent proceeds with remaining tools |
| MCP tool call returns error | Tool result is passed back to agent as an error message; agent decides how to proceed |
| Jira issue not found | Agent receives error from Jira MCP tool; Watson logs and skips the issue |
| LLM API error | Retry once with backoff; if still failing, write partial report with error note |
| Agent exceeds max turns | Capture partial output; mark report as `incomplete` |

---

## 8. Configuration

All configuration via environment variables (`.env` file supported):

```
# MCP server config file
WATSON_MCP_CONFIG=./mcp_servers.json

# Jira (passed to Jira MCP server)
JIRA_URL=https://yourorg.atlassian.net
JIRA_API_TOKEN=...

# Mattermost (passed to Mattermost MCP server)
MM_URL=https://mattermost.yourorg.com
MM_TOKEN=...
MM_CHANNEL_IDS=channel1id,channel2id

# Google Drive (passed to GDrive MCP server)
GOOGLE_SERVICE_ACCOUNT_FILE=./secrets/gsa.json
GOOGLE_DRIVE_FOLDER_ID=...

# GitHub (passed to GitHub MCP server)
GITHUB_TOKEN=...

# LLM
WATSON_LLM_PROVIDER=anthropic          # or: openai
WATSON_LLM_MODEL=claude-opus-4-5       # or: gpt-4o
ANTHROPIC_API_KEY=...
# OPENAI_API_KEY=...

# Agent
WATSON_MAX_AGENT_TURNS=20

# Output
WATSON_OUTPUT_DIR=./output
```

---

## 9. Project Layout

```
watson/
├── watson/
│   ├── __init__.py
│   ├── cli.py              # click CLI entrypoint: watson triage <KEY>
│   ├── orchestrator.py     # starts MCP servers, runs agent per issue, writes output
│   ├── agent.py            # wraps LLM SDK in tool-use loop; returns Markdown string
│   ├── mcp_client.py       # loads mcp_servers.json, spawns servers, exposes tools list
│   ├── models.py           # TriageReport dataclass
│   └── output.py           # Markdown writer + stdout summary
├── prompts/
│   ├── shared-objectives.txt
│   ├── architect.txt
│   ├── coder.txt
│   └── synthesis.txt       # agent system prompt
├── design/
│   └── adr.md              # this file
├── tests/
│   ├── fixtures/           # static MCP tool response payloads
│   ├── test_mcp_client.py
│   ├── test_agent.py       # uses fake MCP tools returning fixture data
│   └── test_e2e.py         # full run against fixtures; no live APIs
├── mcp_servers.json        # MCP server definitions (gitignored if contains secrets)
├── mcp_servers.example.json
├── output/                 # generated triage reports (gitignored)
├── .env.example
├── pyproject.toml
└── README.md
```

---

## 10. Risks & Assumptions

| Risk / Assumption | Mitigation |
|---|---|
| MCP servers for Mattermost / GDrive may need custom implementation | Evaluate available community servers first; build a minimal one if needed |
| Google Drive MCP auth (service account) may require admin setup | Document clearly; provide OAuth fallback option |
| Agent may make redundant or excessive tool calls | Set `WATSON_MAX_AGENT_TURNS`; review system prompt if calls seem wasteful |
| LLM context window limit if many tools return large payloads | Each MCP server should paginate / limit results; tune per-tool limits |
| "Fit with project goals" is subjective | Include a short project-goals blurb in the system prompt via config |
| API rate limits (GitHub, Jira) | MCP servers handle retries; log rate-limit warnings |

---

## 11. Next Steps for the Coder

1. Scaffold project with `uv init watson` and add dependencies (`mcp`, `anthropic`/`openai`, `click`, `python-dotenv`).
2. Implement `models.py` — just `TriageReport`.
3. Implement `mcp_client.py` — load `mcp_servers.json`, spawn servers, return tool list.
4. Implement `agent.py` — tool-use loop against the LLM using the system prompt.
5. Implement `orchestrator.py` — wire MCP client + agent together per issue key.
6. Expose via `cli.py` (`watson triage <KEY>`).
7. Implement `output.py` — write `output/<KEY>.md`.
8. Write tests using fake MCP tool fixtures.
