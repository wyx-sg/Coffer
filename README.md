# Coffer

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
- **Agents** — detect and register your local AI coding agents, edit their config files in-app, and connect any of them to Coffer in one action — which installs its gateway MCP entry and, while memory is on, the memory delivery hook.
- **Providers** — one shared registry of model-provider connections (base URL, encrypted secret, curated models), so you switch provider once instead of once per agent. Switching points the agent's native config at Coffer's local model proxy on `127.0.0.1:8001` and installs a helper, `coffer proxy token --agent-uid <uid>`, that prints the agent's own local proxy token. The proxy exchanges that token for the connection's key upstream, fails over to another connection serving the same model before the first byte, and meters usage (`coffer usage`, `coffer proxy status`). No provider key is written into an agent's config; secrets stay Fernet ciphertext.
- **Skills** — keep a master library of agent skill bundles and deliver them into one or more agents' skill directories, with drift reconciliation.
- **Knowledge** — a directory of markdown files, not an index. You create a **collection**, nest folders in it however you like, and drop files in from your own editor or file manager; agents read the same bytes with their own file tools, find things by walking a generated catalogue and grepping, and add to it through `coffer__write`, with nothing chunked, embedded or reconciled in between. Every collection is served to every agent; a collection cannot be disabled. A curation pass merges new material into coherent documents, on a sweep or on request.
- **Memory** — Coffer aggregates each registered agent's own native memory read-only, normalises it into derived facts partitioned by project plus a `global` partition, and delivers it back through one hook at four moments — session start, each prompt, and before and after a shell command — naming the memory root (`coffer path memory`) that an agent greps with its own file tools for whatever the digest left out. Coffer never writes an agent's memory files, and everything under `~/.coffer/derived/memory/` is derived and rebuildable.
- **Channels** — chat with your registered coding agents (Claude Code, Codex) from Telegram or SeaTalk, and receive notifications from your phone.

Run Coffer on more than one machine? The vault is a git repository, and it syncs with one git remote you own. A background worker fetches, lets git merge outside the vault, applies a clean merge and pushes; any conflict stops the round, with nothing changed on either side, until you choose per file. A new machine joins with `coffer sync join`, which takes the union and deletes nothing. Secrets travel as ciphertext only; the master key never leaves a machine except through an explicit out-of-band transfer you perform yourself. One thing deliberately stays behind: a resource's **reach** — whether it is enabled, and which agents it is scoped to — is machine-local, so each machine answers that question for itself.

One **UI** ties them together — register and configure your agents, browse and curate every kind, and manage the vault's settings from one place. It reaches you two ways from a single build: served by the daemon at its own loopback origin for a browser, and hosted in a **macOS desktop app** with a Dock icon and a menu-bar tray that starts the daemon for you.

📖 **Documentation site:** https://wyx-sg.github.io/Coffer/

## Download & install

**Let your agent install it.** Coffer is for people who already work with a
coding agent, so the quickest install is to paste this into Claude Code, Codex
or any agent that can run commands on your machine:

```text
Install Coffer on this machine by following
https://wyx-sg.github.io/Coffer/start/install — pick the install path that fits
this machine (a release build if one is published for this OS and architecture,
otherwise from source). Ask me before running anything with sudo or editing my
shell profile. When it is installed, check it with `coffer daemon status`.
Then, for each coding agent installed here (claude-code, codex), run
`coffer agent add <type>` and `coffer agent connect <type>`, telling me which
config files connect will change before you run it. Do not handle any
credentials: if a step needs a login, tell me what to do instead.
```

The agent reads the install page, chooses the path for your machine and checks
the result. To install by hand instead, use one of the paths below.

> **No tagged release yet.** The desktop app, the prebuilt binaries, the one-line
> installer and the release archive below ship with Coffer's first tagged release
> and are not yet published — those links will 404 until then. For now, **[install
> from source](#install-from-source-developers)** (below) is the working path.

Coffer runs the same UI two ways, and installing either one gives you both. Pick
whichever fits how you work.

### Desktop app (macOS) — _from the first release_

Download `Coffer-unsigned-<triple>.dmg` from
[Releases](https://github.com/wyx-sg/Coffer/releases/latest), drag Coffer to
Applications, and open it. Nothing else is required: the app carries `coffer`,
`coffer-daemon` and `coffer-mcp-shim` inside it, starts the
daemon for you, and stays in the menu-bar tray between uses.

It installs the command line too. On first launch the daemon deploys all three
binaries into `~/.coffer/bin`, so putting that directory on your `PATH` gives you
`coffer` and lets MCP clients resolve `coffer-mcp-shim`:

```sh
export PATH="$HOME/.coffer/bin:$PATH"   # add this to your shell profile
```

> **macOS (unsigned):** Coffer is not yet codesigned or notarised — that needs a
> paid Apple Developer account. macOS refuses a `.dmg` downloaded in a browser
> with _"Coffer is damaged and can't be opened"_. It is not damaged; clear the
> quarantine flag and open it again:
>
> ```sh
> xattr -dr com.apple.quarantine /Applications/Coffer.app
> ```

### One-line CLI install (macOS) — _from the first release_

Prefer to stay in the terminal, or working on a machine with no GUI:

```sh
curl -fsSL --proto '=https' --tlsv1.2 https://wyx-sg.github.io/Coffer/install.sh | sh
```

Installs three binaries — `coffer` (management CLI), `coffer-daemon` and `coffer-mcp-shim` — to
`~/.coffer/bin`, and puts that directory on your `PATH`. **Any `coffer` command, or an MCP client
launching the shim, starts the daemon on demand.** Environment overrides: `COFFER_INSTALL_DIR`,
`COFFER_VERSION`, `COFFER_NO_MODIFY_PATH`. Then `coffer open` opens the UI in your browser.
A binary installed this way is not quarantined, so there is no Gatekeeper step on this path.

### Manual download — _from the first release_

Each `v*` tag publishes two tiers from
[Releases](https://github.com/wyx-sg/Coffer/releases/latest):

| Platform            | File                           | What it is                        |
| ------------------- | ------------------------------ | --------------------------------- |
| macOS Apple silicon | `Coffer-unsigned-<triple>.dmg` | The desktop app, self-contained   |
| macOS Apple silicon | `coffer-cli-<triple>.tar.gz`   | The command line and its binaries |

Coffer currently ships macOS (Apple Silicon) only. The archive contains `coffer`,
`coffer-daemon` and `coffer-mcp-shim`. Verify either download
against the release's aggregated `SHA256SUMS` file, which covers every published artifact.

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
`PATH`. The daemon listens on port 8000 by default, so that address is stable enough to
bookmark; `coffer config set daemon.port <port>` moves it if something else on your machine wants 8000.

> **macOS (unsigned):** binaries extracted from a browser-downloaded archive are quarantined too.
> Clear the flag: `xattr -dr com.apple.quarantine ~/.coffer/bin`

### From source (developers)

See [Install from source (developers)](#install-from-source-developers) below.

---

## Install from source (developers)

**Prerequisites**: Python ≥ 3.12, git, and Node.js to build the web UI.
[ripgrep](https://github.com/BurntSushi/ripgrep) (`rg`) is recommended: knowledge curation uses it
to select candidate documents, and falls back to a slower built-in search without it.

```bash
git clone https://github.com/wyx-sg/Coffer.git
cd Coffer
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e './backend[dev]'
(cd frontend && npm install && npm run build)   # without it the daemon serves no UI
```

`pip install` puts both the CLI (`coffer`) and the stdio shim (`coffer-mcp-shim`) on your `PATH`
as console-script entry points — no separate deploy step. The daemon **auto-starts** the first
time you run any `coffer` command or connect an MCP client — `coffer daemon start` exists for
explicit control but is not a required setup step. Contributors use `make install` instead, which
installs the locked dependencies; see [Install](https://wyx-sg.github.io/Coffer/start/install).

---

## Quickstart

Register your first MCP server — using `@modelcontextprotocol/server-filesystem` as the example:

```bash
coffer mcp add filesystem \
  --stdio "npx -y @modelcontextprotocol/server-filesystem /tmp"

coffer mcp list                   # → filesystem  | stdio | enabled
coffer mcp cap list filesystem    # → tool:read_file, tool:write_file, …
```

Then point your MCP client at the shim — see **Connect to an MCP client** below.

### Agents

An **agent** is a registered local AI coding agent (supported types: `claude_code`, `codex`).
Coffer can auto-detect installed agents (it lists candidates and asks you to confirm — nothing is
registered automatically), edit each agent's curated config files in-app (format-validated,
atomic write with a `.bak` backup, plus an in-editor find/replace that scrolls to the match), and
connect an agent to Coffer (or disconnect it) in one click — its gateway MCP entry plus, while
memory is on, the memory delivery hook. The web UI has an **Agents** page (list + detail), a detect
dialog, the config-file editor, and a Connect to Coffer control.

```bash
coffer scan                       # discover installed agents (confirm before registering)
coffer agent add claude-code      # register one per type; [--config-dir <dir>] for a non-standard home
coffer agent config edit <name> <key>  # edit a curated config file in your $EDITOR
coffer agent connect <name>       # connect the agent to Coffer (MCP entry + memory hook)
```

A few more commands worth knowing:

```bash
coffer attention                  # what needs you now, across every kind
coffer drift list                 # where the agents' files differ from what Coffer wrote
coffer usage                      # metered usage through the model proxy
coffer run --secret NAME -- cmd   # hand one stored secret to one child process
```

---

## Connect to an MCP client

Use `coffer-mcp-shim` as the stdio MCP server command. The shim auto-discovers (and if needed, auto-spawns) the daemon — no port or token config required.

### Claude Code

```bash
coffer agent add claude_code
coffer agent connect claude-code
```

This writes the shim entry into Claude Code's own config, with the agent's identity on it.

### Codex

```bash
coffer agent add codex
coffer agent connect codex
```

### Any other MCP client

Point the client at `coffer-mcp-shim` as a stdio server. A session without an agent identity sees only the servers that reach every agent.

Restart the client after changing its config. Tools appear namespaced as `<server-name>__<tool-name>` (e.g. `filesystem__read_file`).

---

## Project structure

```
backend/              Python daemon + CLI + shim
  coffer/
    domain/           pure types + business rules (no I/O)
    application/      services + orchestration
    infrastructure/   DB, MCP transports, encrypted secret store, daemon discovery
    surfaces/         HTTP (FastAPI), CLI (Typer), stdio shim
frontend/             React + TypeScript + Vite web UI, served by the daemon
desktop/              Tauri (Rust) macOS shell — Dock icon, menu-bar tray, bundled binaries
e2e/                  Playwright suites — the web UI and the MCP gateway
evals/                AI eval harness — tool-search and tool-routing suites
scripts/              repo gates (file sizes, doc naming, acceptance audit) and maintenance
docs-site/            VitePress source for the published documentation site
openspec/             OpenSpec config, capability specs (`specs/<capability>/`, children nest), changes in flight, and the archive
docs/decisions/       Architectural Decision Records (ADRs)
.agents/              Guides: workflow, OpenSpec, stack, frontend, visual language, testing, harness
```

Architecture deep-dive: [docs-site/architecture/](docs-site/architecture/index.md). Principles: [docs-site/architecture/principles.md](docs-site/architecture/principles.md).
ADRs: [docs/decisions/](docs/decisions/).

---

## Developer commands

| Command           | What it does                                                            |
| ----------------- | ----------------------------------------------------------------------- |
| `make install`    | Create the venv and install backend + frontend deps                     |
| `make hooks`      | Wire the pre-commit and commit-msg git hooks                            |
| `make dev`        | Run the backend (`:8000`) and the frontend (`:5173`) together           |
| `make verify`     | `lint verify-unit verify-integration verify-contract verify-acceptance` |
| `make verify-all` | `make verify` plus the end-to-end tier                                  |
| `make desktop`    | Build `Coffer.app` and the `.dmg` (needs Rust; roughly 50 minutes)      |
| `make lock`       | Refresh `backend/uv.lock` from `backend/pyproject.toml`                 |

`make help` lists the rest, including each test tier on its own.

---

## Contributing

- **Conventional Commits** required — see [.agents/workflow.md](.agents/workflow.md)
- **[OpenSpec](https://github.com/Fission-AI/OpenSpec)** — every behaviour change starts with an OpenSpec change (`/opsx:propose`) that is archived in the same PR — see [.agents/openspec.md](.agents/openspec.md)
- **Architecture contracts** — 20 importlinter contracts must stay green (defined in [backend/pyproject.toml](backend/pyproject.toml))
- **Secrets** — secrets are stored only as Fernet ciphertext in the `secrets` table via `coffer.infrastructure.secret`; plaintext never reaches the DB, logs, or audit

---

## License

MIT — see [LICENSE](LICENSE).
