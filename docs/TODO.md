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

## Vault sync

All four come from the thread "梳理多机器同步的缺口和缺陷" (2026-11-06), whose
discussion draft is `sync-review/讨论稿.md` in the project files. They matter
once a second Mac syncs; on 2026-11-06 only one did (every round pulled 0 files).

### Sync soon after a change, and when a Mac wakes

- **Added:** 2026-11-06, from the thread "梳理多机器同步的缺口和缺陷"
- **What:** a change reaches the remote a minute or two after it is made, and a
  Mac that wakes or gets its network back pulls at once, instead of waiting up
  to the hourly round.
- **Why later:** with two Macs used in turn, an hour-old edit can be missing on
  the other one and conflicts get likelier; with one Mac it changes nothing.
- **Sketch:** per ADR background-workers-wake-on-events: a vault commit pokes
  the sync worker, debounced 1–2 minutes; a wake/network-up event pulls; the
  hourly round stays as the fallback. Not real-time. Syncthing aggregates
  file events for 10 s and rescans hourly; Obsidian Sync and 1Password are
  near-instant.

### Keep secrets readable when two Macs hold different master keys

- **Added:** 2026-11-06, from the thread "梳理多机器同步的缺口和缺陷"
- **What:** a Mac never replaces a secret it can decrypt with a newer ciphertext
  it cannot, and joining a remote that carries secrets asks for the master key
  before secrets come down.
- **Why later:** today "the fresher encryption wins" (`settle_secrets` in
  `application/sync/round_trees.py`) does not check this Mac's key; the
  Machines tab only flags the mismatch. It needs two Macs with secrets synced.
- **Sketch:** open questions: two Macs that keep their own values would
  ping-pong; perhaps stop the round on such a secret instead. Needs an ADR.

### Help when a Mac is lost or retired

- **Added:** 2026-11-06, from the thread "梳理多机器同步的缺口和缺陷"
- **What:** retiring a Mac walks through revoking its access: revoke and replace
  the push token at the Git host (with a link), and optionally rotate the
  master key (re-encrypt every secret) so the old Mac's key opens nothing new.
- **Why later:** retiring only removes the descriptor; the token and key stay
  on that Mac. Matters only once there is a second Mac to lose.
- **Sketch:** 1Password and Bitwarden deauthorise the device and rotate keys.
  Key rotation needs its own ADR (every machine must import the new key).

### Set up another Mac from one file

- **Added:** 2026-11-06, from the thread "梳理多机器同步的缺口和缺陷"
- **What:** the passphrase-protected `.cfk` backup can also carry the remote's
  URL, branch, options and push token, so a new Mac joins by importing one file
  and typing one passphrase.
- **Why later:** today a second Mac needs a token, a secret, the URL and the key
  file, each by hand; worth it the first time the owner adds a Mac.
- **Sketch:** 1Password adds a device by QR code; Syncthing devices introduce
  each other. The token must stay inside the passphrase-encrypted bundle.
