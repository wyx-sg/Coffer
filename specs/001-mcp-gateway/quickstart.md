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

1. Allocates a free port in the 8000–8009 range and writes
   `~/.coffer/daemon.json` (mode `0600`) so the CLI and the shim can find
   each other.
2. Initialises the SQLite database under `~/.coffer/coffer.db`.
3. Seeds default retention policies (audit: 365 days, invocations: 30 days).

Verify the daemon is up:

```bash
coffer daemon status
# → status: ready
# → port:   8001
```

## Add your first MCP server

```bash
coffer mcp add filesystem \
  --stdio "npx -y @modelcontextprotocol/server-filesystem /tmp"
```

Coffer registers the server, spawns it once to discover capabilities, then
prints the discovered tools (e.g. `read_file`, `write_file`,
`list_directory`).

Add an HTTP MCP server (with credentials) the same way:

```bash
coffer credentials set github-token "ghp_xxxxxxxxxxxx"
coffer mcp add github --http https://api.github.com/mcp \
  --credential "Authorization=Bearer ${github-token}"
```

(Secrets are stored as ciphertext in coffer's encrypted credential store; only
the credential ref is persisted in coffer's config.)

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

(If Coffer chose a different port — see `~/.coffer/daemon.json` for the
actual one — substitute it here.)

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
coffer credentials set github-token "<new value>"
```

(No need to update the server config — it already references the credential
by ref.)

## Troubleshooting

| Symptom                                           | Most likely cause             | Fix                                                                                |
| ------------------------------------------------- | ----------------------------- | ---------------------------------------------------------------------------------- |
| `Cannot connect to coffer daemon` from the client | Daemon not running            | `coffer daemon start`                                                              |
| `command not found: coffer-mcp-shim`              | PATH not updated              | Use the absolute path to the binary, or add its directory to your `PATH`.          |
| Server registered but capabilities empty          | Upstream failed to initialize | `~/.coffer/logs/upstream-<name>.log` has stderr from the upstream.                 |
| `CREDENTIAL_LOCKED` error                         | OS keychain is locked         | Unlock the keychain (macOS: log in to GUI; Linux: unlock GNOME-keyring / KWallet). |
| Disabled tool still appears in client             | Client cached the tool list   | Restart the client, or look for a "reload MCP servers" option.                     |
| `no free port in 8000-8009 range`                 | Ten ports busy                | Kill the other process and restart `coffer daemon`.                                |

## Where things live

```text
~/.coffer/
├── coffer.db              # SQLite — the rebuildable INDEX over the file trees
├── coffer.db-wal          # WAL
├── coffer.db-shm          # WAL shared memory
├── knowledge/             # system of record: KB markdown trees
├── memory/                # system of record: memory markdown trees
├── skills/                # system of record: managed skill folders
├── master.key             # Fernet key that decrypts the credential ciphertext
├── daemon.json            # daemon discovery: pid + port + token (mode 0600)
├── logs/
│   ├── daemon.log         # structured JSON, one line per event
│   └── upstream-<name>.log
├── backups/               # produced by `coffer daemon backup`
└── upstream-pids/         # for orphan-subprocess cleanup
```

### Backup & restore

The markdown trees (`knowledge/`, `memory/`, `skills/`) are the system of
record; `coffer.db` is a rebuildable index over them. Two backup levels:

- `coffer daemon backup` writes a self-consistent SQLite copy of `coffer.db`
  alone under `backups/` while the daemon runs — handy for snapshotting the
  index, but it does NOT capture the file trees.
- `coffer backup <dest>` is the full **vault** backup: it copies `coffer.db`
  AND every file tree into `<dest>`. `coffer restore <dest>` verifies the
  backup and re-places the db + trees into `~/.coffer/`, so a fresh machine
  comes back to life. The restored `coffer.db` is already a consistent index;
  pass `coffer restore <dest> --reindex` to rebuild it from the trees anyway.

**Master-key policy.** `coffer backup` EXCLUDES `master.key` by default, so the
backup is safe to copy off-machine — bundling the Fernet key next to the
ciphertext it unlocks would defeat the encryption. A restored vault works for
everything except *reading* previously-stored credentials; re-place
`master.key` at `~/.coffer/master.key` or re-enter the secrets with
`coffer credentials set`. Pass `coffer backup <dest> --include-master-key` to
bundle the key (after a printed warning) — only into storage you trust as much
as the live key.
