# Coffer quickstart

A 5-minute walkthrough: from `git clone` to Claude Code calling tools through Coffer.

---

## 1. Install

```bash
git clone https://github.com/wyx-sg/Coffer.git
cd Coffer
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ./backend[dev]
```

That installs the `coffer` CLI and the `coffer-mcp-shim` entry-point into the venv.

---

## 2. Start the daemon

```bash
coffer daemon start
```

The daemon binds to `127.0.0.1` on an auto-selected port and writes its address + auth token to `~/.coffer/daemon.json`. Every subsequent `coffer` command reads that file automatically.

```bash
coffer daemon status
# → status: running  port: 8000  version: 0.1.0
```

---

## 3. Register an MCP server

Let's use the official filesystem server as a concrete example:

```bash
coffer mcp add filesystem \
  --stdio "npx -y @modelcontextprotocol/server-filesystem /tmp"
```

Coffer spawns the subprocess, runs capability discovery, and stores the result.

```bash
coffer mcp list
# → filesystem  | stdio | enabled

coffer mcp test filesystem
# → OK (87 ms)

coffer mcp tool list filesystem
# → filesystem__read_file
# → filesystem__write_file
# → filesystem__list_directory
# → …
```

Tools are namespaced as `<server-name>__<tool-name>` so multiple upstream servers never collide.

---

## 4. Deploy the shim

The `coffer-mcp-shim` binary is what MCP clients talk to. Deploy it to a directory on your `PATH`:

```bash
coffer shim deploy
# → Deployed to /Users/you/.coffer/bin/coffer-mcp-shim

# One-time PATH setup (add to ~/.zshrc or ~/.bashrc):
export PATH="$HOME/.coffer/bin:$PATH"
```

If you're using the Tauri desktop app, the shim is deployed automatically on first launch.

---

## 5. Connect a client

### Claude Code (simplest)

```bash
claude mcp add coffer coffer-mcp-shim
```

Restart Claude Code, then ask: _"List files in /tmp."_ It calls `filesystem__list_directory` through Coffer.

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "coffer": {
      "command": "coffer-mcp-shim"
    }
  }
}
```

Quit and reopen Claude Desktop.

### Cursor

Edit `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "coffer": {
      "command": "coffer-mcp-shim"
    }
  }
}
```

---

## 6. (Optional) Open the desktop UI

```bash
cd frontend && npm ci && npm run dev
```

Visit http://localhost:5173 to see the same registered servers with toggles, capability detail, invocation log, and audit log.

Or run the full Tauri app in dev mode:

```bash
cd desktop && cargo tauri dev
```

---

## 7. (Optional) Knowledge base in 30 seconds

Coffer's `knowledge_base` kind turns local files into a searchable RAG corpus your coding agent can hit through the same MCP gateway:

```bash
coffer kb create design-notes
coffer kb ingest design-notes ~/work/notes/architecture.md
coffer kb search design-notes "how does our retry policy work?"
```

Through any connected MCP client, three built-in tools appear: `coffer__list_knowledge_bases`, `coffer__search_knowledge_base`, `coffer__get_document`. No extra MCP server install.

The default embedding model `BAAI/bge-small-en-v1.5` is downloaded from HuggingFace Hub on first `coffer kb ingest` (~130 MB, cached under `~/.cache/huggingface/`). Run `coffer kb warmup` ahead of time if you want the download to happen during installer setup rather than on the first ingest.

Full walkthrough: [`specs/006-knowledge-base/quickstart.md`](../specs/006-knowledge-base/quickstart.md).

---

## Troubleshooting

**Daemon won't start**
Check `coffer daemon status`. If the port is taken, set `COFFER_PORT_RANGE_START=8001` and retry.

**Tool not appearing in client**
Run `coffer mcp refresh <name>` to re-run capability discovery, then reconnect the client (a new MCP session picks up changes immediately).

**Credentials for a private server**
Store secrets in the OS keychain, then reference them when registering:

```bash
coffer keychain set MY_API_KEY "sk-..."
coffer mcp add myserver \
  --stdio "npx -y @my/mcp-server" \
  --credential "MY_API_KEY=MY_API_KEY"
```

**Shim not found**
Run `coffer shim deploy` and confirm `~/.coffer/bin` is on your `PATH`. The shim auto-spawns the daemon if it isn't running.
