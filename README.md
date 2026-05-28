# Coffer

> Local-first AI agent vault. One place to manage your MCP servers, skills, memories, and agents.

Coffer is a daemon + desktop app that aggregates upstream MCP servers and re-exposes them to MCP clients (Claude Desktop, Cursor, Claude Code) through a unified, namespaced surface. Configure once; every client sees the same tools. All state lives on your machine — no cloud accounts, no vendor lock-in.

**Status**: v0.1 in active development. First feature implemented (merging in PR #14): **MCP gateway** (aggregates stdio and HTTP upstream MCP servers). Additional resource kinds (skills, memory, agents, channels) are planned for future specs.

---

## Install

### Option 1 — Pre-built bundle (when releases land)

Download the latest `.dmg` (macOS), `.msi` (Windows), or `.deb` / `.AppImage` (Linux) from [Releases](https://github.com/wyx-sg/Coffer/releases). Double-click to install. The shim binary is deployed to `~/.coffer/bin/` on first launch.

### Option 2 — From source (developer install)

```bash
git clone https://github.com/wyx-sg/Coffer.git
cd Coffer
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ./backend[dev]
cd frontend && npm ci && npm run build && cd ..
make verify          # sanity-check the install
coffer daemon start  # boots the daemon on http://127.0.0.1:<auto-port>
```

### Option 3 — CLI only (no desktop UI)

Same as Option 2 but skip the frontend build. `pip install` puts both the CLI (`coffer`) and the stdio shim (`coffer-mcp-shim`) on your `PATH` as console-script entry points — they work without the Tauri app and need no separate deploy step.

---

## Quickstart

Register your first MCP server — using `@modelcontextprotocol/server-filesystem` as the example:

```bash
coffer mcp add filesystem \
  --stdio "npx -y @modelcontextprotocol/server-filesystem /tmp"

coffer mcp list                   # → filesystem  | stdio | enabled
coffer mcp tool list filesystem   # → read_file, write_file, list_directory, …
```

Then point your MCP client at the shim. See **[docs/quickstart.md](docs/quickstart.md)** for a complete 5-minute walkthrough.

---

## Connect to an MCP client

Use `coffer-mcp-shim` as the stdio MCP server command in any of these clients. The shim auto-discovers (and if needed, auto-spawns) the daemon — no port or token config required.

### Claude Desktop

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) / `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "coffer": {
      "command": "coffer-mcp-shim"
    }
  }
}
```

### Cursor

`~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "coffer": {
      "command": "coffer-mcp-shim"
    }
  }
}
```

### Claude Code

```bash
claude mcp add coffer coffer-mcp-shim
```

Restart the client after editing its config. Tools appear namespaced as `<server-name>__<tool-name>` (e.g. `filesystem__read_file`).

---

## Project structure

```
backend/              Python daemon + CLI + shim
  coffer/
    domain/           pure types + business rules (no I/O)
    application/      services + orchestration
    infrastructure/   DB, MCP transports, keychain, daemon discovery
    surfaces/         HTTP (FastAPI) + CLI (Typer) + stdio shim
frontend/             React + Vite + Tailwind + shadcn desktop UI
desktop/              Tauri 2 shell (Rust)
specs/                Speckit specs (one per feature)
docs/decisions/       Architectural Decision Records (ADRs)
agents/               Workflow, SDD, stack, and testing guides
```

Architecture deep-dive: [.specify/memory/architecture.md](.specify/memory/architecture.md).
ADRs: [docs/decisions/](docs/decisions/).

---

## Developer commands

| Command                         | What it does                                                          |
| ------------------------------- | --------------------------------------------------------------------- |
| `make verify`                   | Full check: lint, type, unit, integration, contract, acceptance audit |
| `make install`                  | Install all deps into the project venv + node_modules                 |
| `make bundle-binaries`          | Build `coffer-daemon` + `coffer-mcp-shim` with PyInstaller            |
| `cd frontend && npm run dev`    | Vite dev server at http://localhost:5173                              |
| `cd desktop && cargo tauri dev` | Tauri app in dev mode (connects to Vite)                              |
| `cd e2e && npm test`            | Playwright e2e suite (spawns a real daemon)                           |

---

## Contributing

- **Conventional Commits** required — see [agents/workflow.md](agents/workflow.md)
- **Spec-driven development** — every feature starts with a spec under `specs/<id>/` — see [agents/sdd.md](agents/sdd.md)
- **Architecture contracts** — 6 importlinter contracts must stay green (defined in [backend/pyproject.toml](backend/pyproject.toml))
- **Credentials** — all secrets go through `coffer.infrastructure.credentials.keyring_adapter`; never reach the DB in plaintext

---

## License

MIT — see [LICENSE](LICENSE).
