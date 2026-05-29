# Coffer

> Local-first AI agent vault. Manage all your MCP servers from one place.

Coffer is a daemon + CLI that aggregates upstream MCP servers and re-exposes them to MCP clients (Claude Code, Codex) through a unified, namespaced surface. Configure once; every client sees the same tools. All state lives on your machine — no cloud accounts, no vendor lock-in.

---

## Install

```bash
git clone https://github.com/wyx-sg/Coffer.git
cd Coffer
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ./backend[dev]
make verify          # sanity-check the install
coffer daemon start  # boots the daemon on http://127.0.0.1:<auto-port>
```

`pip install` puts both the CLI (`coffer`) and the stdio shim (`coffer-mcp-shim`) on your `PATH` as console-script entry points — no separate deploy step.

---

## Quickstart

Register your first MCP server — using `@modelcontextprotocol/server-filesystem` as the example:

```bash
coffer mcp add filesystem \
  --stdio "npx -y @modelcontextprotocol/server-filesystem /tmp"

coffer mcp list                   # → filesystem  | stdio | enabled
coffer mcp tool list filesystem   # → read_file, write_file, list_directory, …
```

Then point your MCP client at the shim — see **Connect to an MCP client** below.

---

## Connect to an MCP client

Use `coffer-mcp-shim` as the stdio MCP server command. The shim auto-discovers (and if needed, auto-spawns) the daemon — no port or token config required.

### Claude Code

```bash
claude mcp add coffer coffer-mcp-shim
```

### Codex

`~/.codex/config.toml`:

```toml
[mcp_servers.coffer]
command = "coffer-mcp-shim"
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
specs/                Speckit specs (one per feature)
docs/decisions/       Architectural Decision Records (ADRs)
agents/               Workflow, SDD, stack, and testing guides
```

Architecture deep-dive: [.specify/memory/architecture.md](.specify/memory/architecture.md).
ADRs: [docs/decisions/](docs/decisions/).

---

## Developer commands

| Command | What it does |
|---|---|
| `make verify` | Full check: lint, type, unit, integration, contract, acceptance audit |
| `make install` | Install backend deps into the project venv |

---

## Contributing

- **Conventional Commits** required — see [agents/workflow.md](agents/workflow.md)
- **Spec-driven development** — every feature starts with a spec under `specs/<id>/` — see [agents/sdd.md](agents/sdd.md)
- **Architecture contracts** — 6 importlinter contracts must stay green (defined in [backend/pyproject.toml](backend/pyproject.toml))
- **Credentials** — all secrets go through `coffer.infrastructure.credentials.keyring_adapter`; never reach the DB in plaintext

---

## License

MIT — see [LICENSE](LICENSE).
