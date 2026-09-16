# Quickstart — Coffer MCP Gateway

A 10-minute path from "I just installed Coffer" to "Claude Code is calling
filesystem tools through it." This document is the **user-facing** quickstart
that ships with the feature; developers wanting to set up the dev environment
should follow `CONTRIBUTING.md` instead.

This quickstart covers the **CLI + shim** install path: install from a source
checkout, register an MCP server, and wire Coffer into your MCP client.

## Prerequisites

- A supported MCP client installed (e.g. Claude Code or Codex; any version
  supporting either stdio or HTTP MCP server configuration).
- One or more MCP servers you want to use. The walk-through below uses the
  public `@modelcontextprotocol/server-filesystem` server, which needs `npx`
  (Node.js 18+).
- The `coffer` CLI and the `coffer-mcp-shim` binary on your `PATH`. From a
  source checkout: `pip install ./backend` puts both on `PATH` as
  console-script entry points.

## First launch

Start the daemon:

```bash
coffer daemon start
```

On first launch Coffer:

1. Binds port 8000 and writes `~/.coffer/daemon.json` (mode `0600`) so the CLI
   and the shim can find each other. The address does not move between
   restarts, so a browser bookmark to Coffer's UI keeps working. If something
   else on your machine wants 8000, Coffer refuses to start rather than landing
   somewhere else, and names the process holding it;
   `coffer daemon port set <other>` moves Coffer instead.
2. Initialises the SQLite database under `~/.coffer/coffer.db`.
3. Seeds default retention policies (audit: 365 days, invocations: 30 days).

Verify the daemon is up:

```bash
coffer daemon status
# → status:  ready
# → version: 0.x.y
# → port:    8000
# → pid:     12345
```

Then open the UI:

```bash
coffer open
```

The daemon serves the built web UI itself, at its own loopback origin, and hands
the browser its API token in the page it serves — so landing on that origin is
all the authentication there is: no token to paste. `coffer open` exists for the
one part a human cannot do reliably, reading the real port out of
`~/.coffer/daemon.json`, and it starts a daemon if none is running.

(There is a second way in, for people who would rather not start with a
terminal: the desktop `.dmg` of the release, which is the same UI in a native
window with a tray, and which installs the `coffer` CLI on first launch.)

## Add your first MCP server

```bash
coffer mcp add filesystem \
  --stdio "npx -y @modelcontextprotocol/server-filesystem /tmp"
```

`add` registers the server and prints `registered: mcp_server:filesystem`. It
does not spawn anything — discovery happens on the first list, and you can force
it now:

```bash
coffer mcp show filesystem       # the discovered tools, resources and prompts
coffer mcp refresh filesystem    # re-discover after an upstream upgrade
```

Add an HTTP MCP server (with credentials) the same way. `credentials set` takes
the **ref** as its only argument and reads the secret from stdin, so it never
lands in shell history:

```bash
printf 'ghp_xxxxxxxxxxxx' | coffer credentials set github-token
coffer mcp add github --http https://api.github.com/mcp \
  --credential "Authorization=github-token"
```

`--credential` maps an env var or header name to a **credential ref**
(`ENV_OR_HEADER=CREDENTIAL_REF`), repeatable; the value is materialised at spawn
time. Secrets are stored as ciphertext in coffer's encrypted credential store;
only the ref is persisted in coffer's config.

## Wire Coffer into your MCP client

### Claude Code / Codex / any client supporting stdio MCP

Edit your client's MCP configuration (location is client-specific; for
Claude Code it is `~/.claude/mcp.json` or via `claude mcp add …`):

```json
{
  "mcpServers": {
    "coffer": {
      "command": "coffer-mcp-shim"
    }
  }
}
```

Replace `coffer-mcp-shim` with the absolute path if the binary is not on
your client's `PATH`.

Restart the client.

### Clients supporting HTTP MCP

```json
{
  "mcpServers": {
    "coffer": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

(If you moved Coffer's port with `coffer daemon port set` — see
`~/.coffer/daemon.json` for the actual one — substitute it here.)

## Verify it works

1. In your MCP client, list available tools. You should see every enabled
   upstream tool, prefixed:
   - `filesystem__read_file`
   - `filesystem__write_file`
   - `filesystem__list_directory`
   - …
2. Ask the AI to read a file. It should call `filesystem__read_file`. Coffer
   routes the call to the upstream filesystem server with the original name.
3. Run `coffer mcp invocations filesystem`. You should see the call logged
   with timestamp, duration, and outcome.

## Common tasks

### Disable a single tool

```bash
coffer mcp tool disable filesystem write_file
```

Restart the MCP client; the disabled tool no longer appears.

### Add a second MCP server

Repeat the steps above. Tool calls in the client now appear prefixed by their
respective server names — no collisions.

### See what changed and when

```bash
coffer audit list --kind mcp_server --name filesystem
```

### Change how long logs are kept

```bash
coffer retention list
coffer retention set mcp_invocations --days 7
coffer retention set audit_log --forever
```

### Update a credential

```bash
printf '<new value>' | coffer credentials set github-token
```

(`--value <secret>` is accepted too, and documented as unsafe — it lands in
shell history. No need to update the server config either way: it already
references the credential by ref.)

## Troubleshooting

| Symptom                                           | Most likely cause             | Fix                                                                                |
| ------------------------------------------------- | ----------------------------- | ---------------------------------------------------------------------------------- |
| `Cannot connect to coffer daemon` from the client | Daemon not running            | `coffer daemon start`                                                              |
| `command not found: coffer-mcp-shim`              | PATH not updated              | Use the absolute path to the binary, or add its directory to your `PATH`.          |
| Server registered but capabilities empty          | Upstream failed to initialize | `~/.coffer/logs/upstream-<name>.log` has stderr from the upstream.                 |
| `CREDENTIAL_LOCKED` error                         | OS keychain is locked         | Unlock the keychain (macOS: log in to GUI; Linux: unlock GNOME-keyring / KWallet). |
| Disabled tool still appears in client             | Client cached the tool list   | Restart the client, or look for a "reload MCP servers" option.                     |
| `port <n> is configured as Coffer's fixed daemon port` | Something else holds the port Coffer binds — 8000 by default | The message names the process. Free it, or move Coffer with `coffer daemon port set <other>`. |

## Where things live

```text
~/.coffer/
├── coffer.db              # SQLite — resources, credentials, audit, chat, sync state
├── coffer.db-wal          # WAL
├── coffer.db-shm          # WAL shared memory
├── knowledge/             # system of record: KB markdown trees
├── memory/                # system of record: memory markdown trees
├── skills/                # system of record: managed skill folders
├── master.key             # Fernet key that decrypts the credential ciphertext
├── daemon.json            # daemon discovery: pid + port + token (mode 0600)
├── daemon-config.json     # daemon settings read BEFORE the DB opens: the fixed port (mode 0600)
├── logs/
│   ├── daemon.log         # structured JSON, one line per event
│   └── upstream-<name>.log
└── upstream-pids/         # for orphan-subprocess cleanup
```

### Copying the vault

The markdown trees (`knowledge/`, `memory/`, `skills/`) are the system of record
for their own content; `coffer.db` is the system of record for everything else —
registered resources, credential ciphertext, the audit log, chat history and
sync state. There is no index to rebuild: retrieval over the trees is literal
text search, so nothing in the database derives from the files
([Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md)).
Coffer ships no backup command of its own — to keep a vault on two machines,
point spec vault-sync's bidirectional convergence at a git remote you own; for a
plain copy, `cp -r ~/.coffer/ <dest>` with the daemon stopped.

**Master key.** `master.key` decrypts the credential ciphertext in
`coffer.db`. Bundling it next to that ciphertext defeats the encryption, so
keep it out of anything you copy off-machine; a vault without it works for
everything except *reading* previously-stored credentials, which can be
re-entered with `coffer credentials set`.
