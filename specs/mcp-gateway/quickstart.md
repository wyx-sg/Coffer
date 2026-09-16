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
- The `coffer` CLI and the `coffer-mcp-shim` binary on your `PATH`. How they
  get there — a source install, the release archive, or the desktop app — is
  spec daemon's and spec desktop-app's; either route leaves both on disk.

## First launch

Start the daemon:

```bash
coffer daemon start
```

On first launch Coffer:

1. Binds its port and publishes `~/.coffer/daemon.json` so the CLI and the shim
   can find each other (spec daemon).
2. Initialises the SQLite database under `~/.coffer/coffer.db`.
3. Seeds the default retention policies every log-writing spec registers —
   the invocation log below arrives at 30 days (spec resource-framework).

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

The daemon serves the web UI at its own loopback origin and authenticates the
page it serves, so there is no token to paste; `coffer open` reads the real port
and starts a daemon if none is running (spec daemon). People who would rather
not start in a terminal have the desktop app instead (spec desktop-app).

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

Add an HTTP MCP server (with credentials) the same way. `coffer credentials set`
is spec credentials'; it takes the **ref** as its only argument and reads the
secret from stdin, so the secret never lands in shell history:

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

(If you moved Coffer's port, `~/.coffer/daemon.json` names the actual one —
substitute it here.)

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

### See what changed and when, or how long logs are kept

`coffer audit list --kind mcp_server --name filesystem` and
`coffer retention set mcp_invocations --days 7` both work here, but they are
spec resource-framework's commands and its quickstart covers them — including
reach, deletion and the rest of what any resource can be told to do.

### Update a credential

```bash
printf '<new value>' | coffer credentials set github-token
```

No need to update the server config: it already references the credential by
ref. The command itself is spec credentials'.

## Troubleshooting

| Symptom                                           | Most likely cause             | Fix                                                                                |
| ------------------------------------------------- | ----------------------------- | ---------------------------------------------------------------------------------- |
| `Cannot connect to coffer daemon` from the client | Daemon not running            | `coffer daemon start`                                                              |
| `command not found: coffer-mcp-shim`              | PATH not updated              | Use the absolute path to the binary, or add its directory to your `PATH`.          |
| Server registered but capabilities empty          | Upstream failed to initialize | `~/.coffer/logs/upstream-<name>.log` has stderr from the upstream.                 |
| `CREDENTIAL_LOCKED` error                         | OS keychain is locked         | Unlock the keychain; the credential store's own troubleshooting is spec credentials'. |
| Disabled tool still appears in client             | Client cached the tool list   | Restart the client, or look for a "reload MCP servers" option.                     |
| The daemon will not start, or its port is held    | Another process holds the port | Spec daemon's quickstart covers the port and its diagnosis.                        |

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

**Master key.** `master.key` decrypts the credential ciphertext in `coffer.db`.
Keep it out of anything you copy off-machine — spec credentials' quickstart
explains why and what a vault without it can still do.
