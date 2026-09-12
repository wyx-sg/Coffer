# Coffer

<p align="center">
  <b>English</b> · <a href="./README.zh.md">简体中文</a>
</p>

<p align="center">
  <a href="https://wyx-sg.github.io/Coffer/"><img alt="Docs" src="https://img.shields.io/badge/docs-coffer-C96442"></a>
  <a href="./LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue"></a>
  <img alt="Python ≥3.12" src="https://img.shields.io/badge/python-%E2%89%A53.12-3776AB?logo=python&logoColor=white">
  <img alt="Claude Code compatible" src="https://img.shields.io/badge/Claude%20Code-compatible-C96442">
  <img alt="Platforms" src="https://img.shields.io/badge/platform-macOS-555">
</p>

> Local-first AI agent vault, one vault across your machines. One place to manage everything your AI agents touch.

Coffer is a daemon + CLI + web UI that gives every AI agent on your machine one safe, shared surface. All state lives on your machine — no cloud accounts, no vendor lock-in. Everything Coffer manages is a **resource kind**:

- **MCP servers** — aggregate upstream MCP servers and re-expose them to MCP clients (Claude Code, Codex) through a unified, namespaced surface. Configure once; every client sees the same tools.
- **Agents** — detect and register your local AI coding agents, edit their config files in-app, and one-click install Coffer's own MCP server into any of them.
- **Skills** — keep a master library of agent skill bundles and deliver them into one or more agents' skill directories, with drift reconciliation.
- **Knowledge** — a directory of markdown files, not an index. You create a **collection**, nest folders in it however you like, and drop files in from your own editor or file manager; agents read and write the same bytes over MCP and find things by walking a generated catalogue and grepping, with nothing chunked, embedded or reconciled in between. Each collection is a resource, so you decide which agents may see it. A tidy pass merges duplicates into coherent documents on request, archiving every revision it replaces.
- **Channels** — chat with your registered coding agents (Claude Code, Codex) from Telegram or SeaTalk, and receive notifications from your phone.

Run Coffer on more than one machine? **Vault export & import** writes the whole vault to a directory you pick and reads one back on the other machine — knowledge, resources, and ciphertext-only credentials travel; the encryption key never leaves your machines.

A **web UI** — served by the daemon itself at its own loopback origin — ties them together: register and configure your agents, browse and curate every kind, and manage the vault's settings from one place.

📖 **Documentation site:** https://wyx-sg.github.io/Coffer/

## Download & install

> **No tagged release yet.** The prebuilt binaries, the one-line installer, and
> the release archive below ship with Coffer's first tagged release and are not
> yet published — those links will 404 until then. For now, **[install from
> source](#install-from-source-developers)** (below) is the working path.

### One-line CLI install (macOS) — _from the first release_

```sh
curl -fsSL --proto '=https' --tlsv1.2 https://wyx-sg.github.io/Coffer/install.sh | sh
```

Installs `coffer` (management CLI), `coffer-daemon`, `coffer-mcp-shim` and the runtime helper
binaries to `~/.coffer/bin`, and puts that directory on your `PATH`. **The daemon auto-starts on
first use — no manual start step.** Environment overrides: `COFFER_INSTALL_DIR`,
`COFFER_VERSION`, `COFFER_NO_MODIFY_PATH`.

### Manual download — _from the first release_

Each `v*` tag publishes a single archive from
[Releases](https://github.com/wyx-sg/Coffer/releases/latest):

| Platform            | File                          |
| ------------------- | ----------------------------- |
| macOS Apple silicon | `coffer-cli-<triple>.tar.gz`  |

Coffer currently ships macOS (Apple Silicon) only. The archive contains `coffer`,
`coffer-daemon`, `coffer-mcp-shim` and the runtime helper binaries. Verify the download against
the release's aggregated `SHA256SUMS` file, which covers every published artifact.

```sh
mkdir -p ~/.coffer/bin
tar -xzf coffer-cli-<triple>.tar.gz -C ~/.coffer/bin
export PATH="$HOME/.coffer/bin:$PATH"   # add this to your shell profile
coffer daemon start
coffer open                             # opens an authenticated browser session
```

`coffer open` reads `~/.coffer/daemon.json` and opens your browser at the daemon's loopback
origin, where the daemon serves the web UI itself. The frozen daemon deploys its sibling
binaries into `~/.coffer/bin` on first start, so MCP clients can resolve `coffer-mcp-shim` from
`PATH`.

> **macOS (unsigned):** the binaries ship unsigned (codesigning and notarisation are pending), so
> Gatekeeper quarantines them on download and macOS may refuse to run them. Clear the quarantine
> flag on the extracted binaries: `xattr -dr com.apple.quarantine ~/.coffer/bin`

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

### Agents

An **agent** is a registered local AI coding agent (supported types: `claude_code`, `codex`).
Coffer can auto-detect installed agents (it lists candidates and asks you to confirm — nothing is
registered automatically), edit each agent's curated config files in-app (format-validated,
atomic write with a `.bak` backup, plus an in-editor find/replace that scrolls to the match), and
one-click install or uninstall Coffer's own MCP server into an agent. The web UI has an
**Agents** page (list + detail), a detect dialog, the config-file editor, and an MCP-install toggle.

```bash
coffer agent detect               # discover installed agents (confirm before registering)
coffer agent add claude_code      # register one (--name optional; defaults to claude-code)
coffer agent config edit <name> <key>  # edit a curated config file in your $EDITOR
coffer agent mcp install <name>   # install Coffer's MCP server into the agent
```

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
    infrastructure/   DB, MCP transports, encrypted credential store, daemon discovery
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
- **Credentials** — secrets are stored only as Fernet ciphertext in the `credentials` table via `coffer.infrastructure.credentials`; plaintext never reaches the DB, logs, or audit

---

## License

MIT — see [LICENSE](LICENSE).
