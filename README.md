# Coffer

<p align="center">
  <b>English</b> · <a href="./README.zh.md">简体中文</a>
</p>

<p align="center">
  <a href="https://wyx-sg.github.io/Coffer/"><img alt="Docs" src="https://img.shields.io/badge/docs-coffer-C96442"></a>
  <a href="./LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue"></a>
  <img alt="Python ≥3.12" src="https://img.shields.io/badge/python-%E2%89%A53.12-3776AB?logo=python&logoColor=white">
  <img alt="Claude Code compatible" src="https://img.shields.io/badge/Claude%20Code-compatible-C96442">
  <img alt="Platforms" src="https://img.shields.io/badge/platform-macOS%20%C2%B7%20Linux%20%C2%B7%20Windows-555">
</p>

> Local-first AI agent vault. Manage all your MCP servers from one place.

Coffer is a daemon + CLI that aggregates upstream MCP servers and re-exposes them to MCP clients (Claude Code, Codex) through a unified, namespaced surface. Configure once; every client sees the same tools. All state lives on your machine — no cloud accounts, no vendor lock-in.

📖 **Documentation site:** https://wyx-sg.github.io/Coffer/

## Screenshots

<p align="center">
  <img src="docs-site/public/screenshots/resources.png" alt="Coffer — manage all your MCP servers from one place" width="820">
</p>

<p align="center">
  <img src="docs-site/public/screenshots/server-detail.png" alt="Per-server detail — health, transport, and discovered capabilities" width="405">
  <img src="docs-site/public/screenshots/observability.png" alt="Audit log — every lifecycle change to any resource or capability" width="405">
</p>

<p align="center">
  <sub>One vault for every MCP server · live health & capabilities · a full audit trail — all local.</sub>
</p>

---

## Download & install

### One-line CLI install (macOS / Linux / Windows)

**macOS / Linux:**

```sh
curl -fsSL --proto '=https' --tlsv1.2 https://wyx-sg.github.io/Coffer/install.sh | sh
```

**Windows PowerShell:**

```powershell
irm https://wyx-sg.github.io/Coffer/install.ps1 | iex
```

Installs three binaries — `coffer` (management CLI), `coffer-daemon`, `coffer-mcp-shim` — to
`~/.coffer/bin`. **The daemon auto-starts on first use — no manual start step.** Environment
overrides: `COFFER_INSTALL_DIR`, `COFFER_VERSION`, `COFFER_NO_MODIFY_PATH`.

### Desktop app (most users)

Download the installer from [Releases](https://github.com/wyx-sg/Coffer/releases/latest):

| Platform             | File                                                                |
| -------------------- | ------------------------------------------------------------------- |
| macOS Apple silicon  | `Coffer_<version>_aarch64.dmg`                                      |
| macOS Intel          | `Coffer_<version>_x64.dmg`                                          |
| Linux x64 (AppImage) | `Coffer_<version>_amd64.AppImage`                                   |
| Linux x64 (deb)      | `coffer_<version>_amd64.deb`                                        |
| Windows 10+ x64      | `Coffer_<version>_x64_en-US.msi` / `Coffer_<version>_x64-setup.exe` |

Each file has a `.sha256` sibling for verification.

> **macOS Gatekeeper:** the DMG ships unsigned (notarisation pending). On first open run:
> `xattr -d com.apple.quarantine /Applications/Coffer.app`

### From source (developers)

See [Install from source (developers)](#install-from-source-developers) below.

---

## Install from source (developers)

```bash
git clone https://github.com/wyx-sg/Coffer.git
cd Coffer
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ./backend[dev]
make verify          # sanity-check the install
```

`pip install` puts both the CLI (`coffer`) and the stdio shim (`coffer-mcp-shim`) on your `PATH`
as console-script entry points — no separate deploy step. The daemon **auto-starts** the first
time you run any `coffer` command or connect an MCP client — `coffer daemon start` exists for
explicit control but is not a required setup step.

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

| Command        | What it does                                                          |
| -------------- | --------------------------------------------------------------------- |
| `make verify`  | Full check: lint, type, unit, integration, contract, acceptance audit |
| `make install` | Install backend deps into the project venv                            |

---

## Contributing

- **Conventional Commits** required — see [agents/workflow.md](agents/workflow.md)
- **Spec-driven development** — every feature starts with a spec under `specs/<id>/` — see [agents/sdd.md](agents/sdd.md)
- **Architecture contracts** — 6 importlinter contracts must stay green (defined in [backend/pyproject.toml](backend/pyproject.toml))
- **Credentials** — all secrets go through `coffer.infrastructure.credentials.keyring_adapter`; never reach the DB in plaintext

---

## License

MIT — see [LICENSE](LICENSE).
