# TODO: larger work we may do later

Large features and changes the owner agreed are worth doing **some day but not now**.
It is a parking lot, not a plan: nothing here is scheduled, and an entry is not a
commitment to build it the way it is sketched.

- Small bugs and polish do not belong here; fix them, or track them where the
  current work is tracked.
- Work that has started moves out: delete the entry in the PR that opens the
  OpenSpec change (`openspec/changes/<name>/`) or the PR that ships it.
- An entry that was rejected is deleted too; if the reason matters later, it goes
  into the relevant spec's Purpose or an ADR, not here.

## How to add an entry

Append under the area's heading (add the heading if the area has none yet, keeping
the areas in alphabetical order). Copy this block; one `###` per entry, so two
threads appending at once rarely conflict:

```markdown
### <Verb-first title, a few words>

- **Added:** YYYY-MM-DD, from <thread name or PR link>
- **What:** one or two sentences on the capability, in the user's terms.
- **Why later:** why it is worth doing, and why not now.
- **Sketch:** the approach agreed so far, open questions, and comparable products
  looked at (link the discussion draft or research note when there is one).
```

## Agents and model providers

### Support a third coding agent

- **Added:** 2026-11-06, from the thread "梳理智能体与模型提供商的缺口和缺陷"
- **What:** register, connect and deliver to a third coding agent such as Gemini
  CLI or OpenCode, the way Claude Code and Codex are today (MCP entry, skills,
  memory, provider projection, sessions).
- **Why later:** serving every agent through one Coffer is what the project is
  for, but only Claude Code and Codex are used now. The code is already shaped
  for it: one enum value, one `AGENT_DESCRIPTORS` record and one child spec under
  `openspec/specs/agent-registry/`.
- **Sketch:** start from the agent's own config format and session API. CC
  Switch manages Gemini CLI and OpenCode next to Claude Code and Codex, so it is
  a reference for their config files. Discussion:
  `agents-providers-gaps/讨论稿.md` in the project files.

### Keep Codex's model capabilities on a provider

- **Added:** 2026-11-06, from the thread "梳理智能体与模型提供商的缺口和缺陷"
- **What:** when Codex runs on a provider, its model picker keeps reasoning effort
  and parallel tool calls for models that support them. Today Coffer's
  `coffer-model-catalog.json` writes `supported_reasoning_levels: []` and
  `supports_parallel_tool_calls: false` for every model
  (`backend/coffer/domain/provider/codex_projection.py`), so Codex on a GPT
  relay is weaker than on its own login.
- **Why later:** Codex currently runs on its own login, so nothing is lost yet;
  it matters the first time Codex is put on an OpenAI-compatible relay.
- **Sketch:** first check how Codex parses `model_catalog_json` (whether the
  fields may be omitted so Codex uses its own defaults), then write what the
  provider reports and leave the rest to Codex.

## MCP servers and custom tools

### Limit MCP servers to a project

- **Added:** 2026-11-06, from the thread "梳理 MCP 和自定义工具还缺什么"
- **What:** a server or custom tool group shows up only in the projects that need
  it (for example a production database only in the billing repo), the way a
  server configured in Claude Code's project `.mcp.json` or a project
  `.codex/config.toml` does today.
- **Why later:** once servers move into Coffer they lose the agents' native
  project scoping, since every agent reaches Coffer through one global `coffer`
  entry, so Coffer is a step back from configuring the agent directly. Nobody
  needs it yet.
- **Sketch:** named **profiles** (a set of servers and custom tool groups). The
  `coffer` entry takes a profile argument (`--profile billing`) and the gateway
  lists only that profile's servers, intersected with the agent's existing reach
  (a profile only narrows). Coffer writes a profile's entry into a project's
  `.mcp.json` / `.codex/config.toml` on request ("use in a project"), so the
  agent's own project mechanism decides which entry applies and Coffer never
  matches paths. UI: profiles on the MCP servers page, "use in a project" and
  "used in these projects" on a profile, "in profiles" on a server's Overview,
  per-project `coffer` entries on the agent's MCP servers tab. Comparable
  products all use one endpoint per subset: 1MCP (tags in the URL), MetaMCP
  (namespace endpoints), IBM ContextForge (virtual servers), Docker MCP Gateway
  (profiles), mcpm (profiles written into each client), see
  [MCP gateways research](research/mcp-gateways.md). Alternative to weigh in the
  ADR: the gateway infers the project from MCP `roots`. That needs no project
  files but needs path rules per server, and Codex's roots support is unverified.

### Upload files from custom tools

- **Added:** 2026-11-06, from the thread "梳理 MCP 和自定义工具还缺什么"
- **What:** a custom tool can send a `multipart/form-data` request with a file,
  for APIs that take attachments, images or packages (Jira or Confluence
  attachments, chat file messages, OCR, artifact stores).
- **Why later:** it is part of turning an HTTP API into tools, but no current
  API needs it, and it needs its own security design.
- **Sketch:** the hard part is where the file comes from. Inline base64 in the
  arguments is simple but floods the agent's context and suits small files only;
  a local path that Coffer reads and uploads means Coffer reads arbitrary files
  for an agent and sends them out, so it needs rules on which directories are
  allowed and whether the person confirms.
