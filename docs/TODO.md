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

## Channels and conversations

### Continue a terminal session from the phone

- **Added:** 2026-11-06, from the thread "梳理对话与消息渠道的缺口和缺陷"
- **What:** pick up a session started in a terminal from a chat channel, the
  reverse of opening a channel's conversation in the terminal.
- **Why later:** reaching an agent on this machine from elsewhere is what a
  channel is for, but `/resume` only lists conversations the chat itself opened.
  Nobody needs the desk-to-phone direction yet.
- **Sketch:** a **Continue in <channel>** item in a Conversations row's ⋯ menu
  attaches the session to a new `🧵` parallel thread in the owner's direct chat,
  reusing the session takeover from #697. Comparable: Claude Code Remote Control,
  Happy.

### Let an agent notify the owner's chat

- **Added:** 2026-11-06, from the thread "梳理对话与消息渠道的缺口和缺陷"
- **What:** an agent in a terminal, or in its own scheduled task, sends the owner a
  message (optionally with a file) on their phone when it finishes.
- **Why later:** only REST `POST /channels/{uid}/notify` exists; an agent has no
  tool for it. Not needed yet.
- **Sketch:** an MCP tool `coffer__channel_notify`, owner's direct chat only,
  rate-limited, on top of the existing notify route. This is also how an agent's
  own scheduled tasks would reach the phone, instead of Coffer running schedules.
  Comparable: cc-connect `send`, Claude Code Channels `reply`.

### Show a running turn's progress in /status

- **Added:** 2026-11-06, from the thread "梳理对话与消息渠道的缺口和缺陷"
- **What:** `/status` on a running turn says how long it has run, how many steps,
  the current tool and the agent's last line.
- **Why later:** on SeaTalk a long turn shows only typing; the live-surface ADR
  rejected pushing progress into the chat, so this answers only when asked.
- **Sketch:** text only, from the turn status Coffer already tracks for
  Telegram's live preview.

### Steer a running turn

- **Added:** 2026-11-06, from the thread "梳理对话与消息渠道的缺口和缺陷"
- **What:** add a sentence to the turn that is running instead of queueing it
  behind the turn or stopping it.
- **Why later:** the agents support it natively (Codex `turn/steer`, Claude Code
  streaming input); queue plus `/stop` is enough for now.
- **Sketch:** `/steer <text>`; falls back to the queue, saying why, where the
  agent cannot take it. No queue-mode setting. Comparable: OpenClaw (steer by
  default), Hermes (`/steer`, `/queue`).

### Add more chat platforms

- **Added:** 2026-11-06, from the thread "梳理对话与消息渠道的缺口和缺陷"
- **What:** channels for Slack, Feishu/Lark and Discord beside Telegram and
  SeaTalk.
- **Why later:** most people use a different IM, but each platform is a whole
  adapter with tests, docs and canvases; build one when someone needs it.
- **Sketch:** one adapter per platform on the existing capability declarations,
  one thread each. Comparable bridges support 13 to 20 platforms (OpenClaw,
  Hermes, cc-connect).

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
