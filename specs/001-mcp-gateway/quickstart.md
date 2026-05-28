# Quickstart — Coffer MCP Gateway

A 10-minute path from "I just installed Coffer" to "Claude Code is calling
filesystem tools through it." This document is the **user-facing** quickstart
that ships with the feature; developers wanting to set up the dev environment
should follow `CONTRIBUTING.md` instead.

This quickstart covers the **CLI + shim** install path that this spec ships
today. The full desktop-app walkthrough (installer DMG / MSI / AppImage, GUI
forms, system tray) is deferred to the planned UI spec (to be drafted as
`002-ui-shell` in a follow-up PR); see [Future (planned in the UI spec)](#future-planned-in-the-ui-spec)
at the bottom.

## Prerequisites

- A supported MCP client installed: Claude Code, Claude Desktop, or Cursor
  (any version supporting either stdio or HTTP MCP server configuration).
- One or more MCP servers you want to use. The walk-through below uses the
  public `@modelcontextprotocol/server-filesystem` server, which needs `npx`
  (Node.js 18+).
- The `coffer` CLI and the `coffer-mcp-shim` binary on your `PATH`. From a
  source checkout: `pip install -e ./backend` puts both on `PATH` as
  console-script entry points. From PyInstaller bundles
  (`make bundle-binaries` — see [ADR-007](../../docs/decisions/ADR-007-distribution-pyinstaller-tauri-sidecar.md)):
  `dist/coffer-daemon` and `dist/coffer-mcp-shim` are self-contained
  executables — drop them in any directory on your `PATH`.

You do **not** need a system Python install when using the PyInstaller
bundles.

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
coffer keychain set github-token "ghp_xxxxxxxxxxxx"
coffer mcp add github --http https://api.github.com/mcp \
  --credential "Authorization=Bearer ${github-token}"
```

(Credentials live in the OS keychain; only the keychain ref is persisted in
coffer's config.)

## Wire Coffer into your MCP client

### Claude Code / Claude Desktop / any client supporting stdio MCP

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
coffer keychain set github-token "<new value>"
```

(No need to update the server config — it already references the keychain key
by name.)

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
├── coffer.db              # SQLite — your config, audit, invocation log
├── coffer.db-wal          # WAL
├── coffer.db-shm          # WAL shared memory
├── daemon.json            # daemon discovery: pid + port + token (mode 0600)
├── logs/
│   ├── daemon.log         # structured JSON, one line per event
│   └── upstream-<name>.log
├── backups/               # produced by `coffer daemon backup`
└── upstream-pids/         # for orphan-subprocess cleanup
```

To take a clean backup, run `coffer daemon backup` (the file copy is safe
under WAL mode; the SQLite online-backup API handles consistency).

## Future (planned in the UI spec)

The following are **not** delivered by spec `001-mcp-gateway`; they are
planned in a follow-up UI spec (to be drafted as `002-ui-shell`):

- Single-installer desktop app (DMG / MSI / AppImage / deb).
- Desktop UI for adding/listing/curating MCP servers, browsing the audit
  trail, viewing invocations, configuring retention.
- System tray, close-to-tray, launch-at-login.
- macOS Gatekeeper / Notarisation handling and first-launch walkthrough.
- First-time-install discoverability flow.
