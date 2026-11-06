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

## CLIs

### Bind a secret to a command-line tool

- **Added:** 2026-11-06, from the thread "梳理命令行工具管理功能还缺少什么"
- **What:** a CLI entry names a Coffer secret and the environment variable it
  goes in (for example `GH_TOKEN` for `gh`), so an agent runs the tool logged in
  without the token sitting in a dotfile.
- **Why later:** it fits "no secret sprawl", but agents already log tools in
  their own way (`gh auth login`, the tool's keychain), and since 2026-11-06
  Coffer checks no CLI login at all, so this may well never be needed. Do it only
  when a real tool can't keep its own login.
- **Sketch:** a `secrets: {ENV_VAR: <secret id>}` map on a `cli-tools` entry,
  injected only into processes Coffer starts (it can't reach an agent's own
  shell), which is the open question: most CLI runs happen in the agent's shell.
  Keep it apart from a skill's `requires.secrets`, which only reports a missing
  secret. OpenClaw's `skills.entries.<key>.env` / `apiKey` (SecretRef, injected
  per run) is the comparable design. Needs an ADR first.

### Accept any one of several commands

- **Added:** 2026-11-06, from the thread "梳理命令行工具管理功能还缺少什么"
- **What:** a skill declares "one of these is enough" (`rg` or `grep`), so the
  one it doesn't use isn't reported missing.
- **Why later:** no managed skill needs it yet; imported third-party skills may
  (OpenClaw's `anyBins`). Until then such a skill declares the one it prefers.
- **Sketch:** `requires: [{any: [rg, grep]}]`; one row per group on the CLIs page,
  ready when any member is found; the hand-off names the first. Touches the
  parser, aggregation, the wire, the CLIs page and Requires tab.

### Read a version a tool prints another way

- **Added:** 2026-11-06, from the thread "梳理命令行工具管理功能还缺少什么"
- **What:** a declaration names how its tool prints its version (`go version`,
  `kubectl version --client`), so a minimum can be compared for tools without
  `--version`.
- **Why later:** today such a tool shows "its version can't be read, so Coffer
  can't compare" and is not flagged; that is honest and enough until a skill
  really depends on a minimum for one of them.
- **Sketch:** an optional `version_command` field (argv starting with the
  command, no shell), used instead of `--version`; editable on the CLI's Edit form.

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
