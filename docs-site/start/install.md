---
title: Install
description: Install Coffer with the one-line installer, the macOS desktop app, a release archive or from source, then verify, start, upgrade or uninstall it.
---

# Install

This page covers every supported way to install Coffer, what each one puts on disk, and how to verify, upgrade and uninstall it. If you only want to get going, [let your agent install it](#let-your-agent-install-it) or run the one-line installer, then continue with the [Quickstart](/start/quickstart).

::: warning No tagged release yet
The one-line installer, the desktop `.dmg` and the release archive all download from a tagged GitHub release. Until the first `v*` tag is published those downloads return 404. For now, [install from source](#from-source).
:::

## Requirements

| What | Why |
| --- | --- |
| **macOS on Apple silicon (arm64)**, for a prebuilt build | The desktop app, the one-line installer and the release archive are built for it only. Any other machine installs [from source](#from-source). |
| **git 2.40 or later** — required | The vault is a git repository: every change is a commit, and history, undo and sync run on git (sync's merges need 2.40). Without it Coffer still starts, but shows [Coffer needs git](/guides/troubleshooting#coffer-needs-git) until git is there. Check with `git --version`. |
| **A coding agent to connect** — Claude Code or Codex | Coffer serves its MCP servers, skills and the rest to your agents. You can install Coffer first and connect an agent afterwards. |
| **From source:** Python 3.12 or later, and Node.js 20 | Python runs the daemon and the CLI; Node.js builds the web UI (CI builds it with Node.js 20). |

## Let your agent install it

If you already work with a coding agent — Claude Code, Codex, or any agent that can run commands on your machine — paste this prompt into it:

```text
Install Coffer on this machine by following
https://wyx-sg.github.io/Coffer/start/install — pick the install path that fits
this machine (a release build if one is published for this OS and architecture,
otherwise from source). Check its Requirements first: if `git --version` is
missing or older than 2.40, install or update git the way that fits this machine.
Ask me before running anything with sudo or editing my shell profile. When it is
installed, check it with `coffer daemon status`.
Then tell me which coding agents it found here (claude-code, codex) and which
config files each one's Connect button on the web UI's Agents page will change,
so I can connect them myself. Do not handle any credentials: if a step needs a
login, tell me what to do instead.
```

The agent reads this page, chooses the path that fits your machine and checks the result, asking before it touches anything outside Coffer's own directory. Coffer never asks an agent to handle a credential, so any login stays with you. The rest of this page is what the agent follows, and what you follow to install by hand.

## Choose an install path

| Path | Best for | Gives you |
| --- | --- | --- |
| [Desktop app](#desktop-app) | Anyone who prefers a window and a menu-bar icon | `Coffer.app`, plus the same four binaries once you first open it |
| [One-line installer](#one-line-installer) | Terminal users on a Mac | `coffer`, `coffer-daemon`, `coffer-mcp-shim`, `coffer-seatalk-bridge` in `~/.coffer/bin` |
| [Release archive](#release-archive) | Installing by hand, or on machines with no GUI | The same four binaries, extracted wherever you choose |
| [From source](#from-source) | Contributors, Linux users, and anyone tracking `main` | A Python install with `coffer` and `coffer-mcp-shim` on your `PATH` |

Prebuilt binaries target **macOS on Apple silicon (arm64)** only. Intel Macs, Linux and Windows have no release build. On those machines, install from source. Every path needs git 2.40 or later; see [Requirements](#requirements).

Every path installs the whole of Coffer. The daemon serves the web UI itself, so a CLI install also gives you the UI (at `http://127.0.0.1:38470/`), and the desktop app also gives you the CLI.

## Desktop app

::: steps

### Download the .dmg

Download the `.dmg` from [Releases](https://github.com/wyx-sg/Coffer/releases/latest). A signed and notarised release is named `Coffer-aarch64-apple-darwin.dmg`; a build without code signing says so in its name, `Coffer-unsigned-aarch64-apple-darwin.dmg`.

### Drag Coffer to Applications

Open the `.dmg` and drag **Coffer** to **Applications**.

### Open Coffer

Only for an unsigned build: macOS refuses a browser-downloaded copy with "Coffer is damaged and can't be opened". The app is not damaged. Clear the quarantine flag and open it again:

```sh
xattr -dr com.apple.quarantine /Applications/Coffer.app
```

Open Coffer. The app finds a running daemon, or starts the one bundled inside it, and shows the UI in a native window. A menu-bar icon stays after you close the window.

:::

The app bundles the same four binaries as the release archive. The first time its daemon starts, it copies them into `~/.coffer/bin`. To use the CLI as well, add that directory to your `PATH`:

```sh
export PATH="$HOME/.coffer/bin:$PATH"   # add to your shell profile
```

See [Desktop app](/guides/desktop-app) for the menu bar, updates, restarts and the offline banner.

## One-line installer

```sh
curl -fsSL --proto '=https' --tlsv1.2 https://wyx-sg.github.io/Coffer/install.sh | sh
```

The script:

1. Checks that you are on macOS arm64. Any other OS or architecture exits with an error that points to the from-source install.
2. Downloads `coffer-cli-aarch64-apple-darwin.tar.gz` and the release's `SHA256SUMS` from GitHub Releases, then verifies the archive's checksum. If the checksum does not match, the script stops.
3. Installs `coffer`, `coffer-daemon`, `coffer-mcp-shim` and `coffer-seatalk-bridge` into the install directory. Each binary is copied to a temporary name beside it, marked executable and renamed over the public name, so when that name is a symlink into a versioned directory (as it is once a daemon started from elsewhere, such as the desktop app, has deployed its build there), the link is replaced and the previous version's binaries stay intact for a rollback.
4. If that directory is not already on your `PATH`, appends a line to your shell profile. The profile depends on your shell: `~/.zshrc` for zsh (or `$ZDOTDIR/.zshrc`), `~/.bash_profile` for bash on macOS, `~/.config/fish/config.fish` for fish (as `fish_add_path`), and `~/.profile` for anything else. Running the script again does not add the line twice.
5. Warns, without failing, when `git` is missing or older than 2.40, and points to [Requirements](#requirements).

Open a new shell, or `source` the profile the script names, so that `coffer` is on your `PATH`. The script ends by pointing you to the web UI's **Agents** page, where **Connect** connects Claude Code. See the [Quickstart](/start/quickstart).

### Installer options

Set these environment variables for the `sh` process:

| Variable | Default | Effect |
| --- | --- | --- |
| `COFFER_INSTALL_DIR` | `~/.coffer/bin` | Where the four binaries are copied. |
| `COFFER_VERSION` | latest release | Install a specific tag, such as `v<version>`. A version without the leading `v` also works. |
| `COFFER_NO_MODIFY_PATH` | unset | Set to `1` to leave your shell profile alone. The script prints the line to add instead. |

```sh
curl -fsSL --proto '=https' --tlsv1.2 https://wyx-sg.github.io/Coffer/install.sh \
  | COFFER_VERSION=v<version> COFFER_NO_MODIFY_PATH=1 sh
```

A binary installed by `curl` is not quarantined, so macOS Gatekeeper does not block it.

## Release archive

Each release publishes `coffer-cli-aarch64-apple-darwin.tar.gz` and one `SHA256SUMS` file that covers every file in the release.

```sh
shasum -a 256 -c SHA256SUMS --ignore-missing   # verify what you downloaded
mkdir -p ~/.coffer/bin
tar -xzf coffer-cli-aarch64-apple-darwin.tar.gz -C ~/.coffer/bin
export PATH="$HOME/.coffer/bin:$PATH"          # add to your shell profile
```

Keep the four binaries together in one directory. `coffer` and `coffer-mcp-shim` look for `coffer-daemon` beside them when they need to start the daemon. If you downloaded the archive in a browser, clear the quarantine flag with `xattr -dr com.apple.quarantine ~/.coffer/bin`.

## From source

Besides git, a source install needs Python 3.12 or later and Node.js 20 to build the web UI; see [Requirements](#requirements).

```sh
git clone https://github.com/wyx-sg/Coffer.git
cd Coffer
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ./backend
```

`pip install` puts two console scripts on the venv's `PATH`: `coffer` and `coffer-mcp-shim`. A source install has no separate `coffer-daemon` binary. The CLI and the shim start the daemon from the same Python environment.

Build the web UI once so the daemon has something to serve. Without it, the API and the MCP endpoint still work, but the daemon has no page to serve.

```sh
cd frontend && npm install && npm run build && cd ..
```

::: tip Contributor setup
`make install` creates `.venv`, installs the backend with its development extras, and installs the frontend's npm dependencies. `make dev` then runs the daemon on port 38470 and the Vite dev server on port 5173 with hot reload. See [Development setup](/contributing/development).
:::

### Frozen binaries and the app from source

| Command | Produces |
| --- | --- |
| `make bundle-binaries` | `coffer`, `coffer-daemon`, `coffer-mcp-shim` and `coffer-seatalk-bridge` frozen with PyInstaller into `dist/`, the same layout as the release archive |
| `make desktop` | `Coffer.app` and an unsigned `.dmg`. Needs a Rust toolchain and Node.js, and takes roughly 50 minutes because it runs PyInstaller first. |

## What gets installed where

| Path | What it is |
| --- | --- |
| `~/.coffer/bin/coffer`, `coffer-daemon`, `coffer-mcp-shim`, `coffer-seatalk-bridge` | The public names. For a release build these are symlinks into a versioned directory. |
| `~/.coffer/bin/<version>/` | One directory per deployed build. The current and previous versions are kept, so you can roll back by pointing the links at the older directory. |
| `~/.coffer/vault/` | The vault: a git repository of resource files, skills, knowledge and encrypted secrets. |
| `~/.coffer/local/` | Settings true of this machine only: agents, reach, retention, the sync remote. |
| `~/.coffer/runs.db` | The history database: audit log, invocations, conversations, sync rounds, usage. |
| `~/.coffer/runs.db.pre-<revision>` | A copy taken before each schema migration. The three newest are kept. |
| `~/.coffer/daemon.json` | Runtime discovery file: PID, port and API token (mode `0600`). Written at start and removed at exit. |
| `~/.coffer/daemon-config.json` | Settings read before the daemon starts: a fixed port, the machine name, any experimental-feature switches. |
| `~/.coffer/content/`, `~/.coffer/derived/` | Media and the chat workspace; state Coffer rebuilds, such as the memory tree. |
| `~/.coffer/logs/daemon.log` | The daemon log, shared by the daemon, its child processes and the desktop app. |

A release-built daemon manages `~/.coffer/bin` itself. At every start it checks whether its build is already deployed there. If not, it copies the four binaries into `~/.coffer/bin/<version>/` and switches the public symlinks to them in one atomic step. A source install never does this. The [files and directories](/reference/filesystem) reference lists every path.

## Verify the install

```sh
coffer daemon start
coffer daemon status
```

```text
status:  ready
version: 0.2.0
port:    38470
pid:     48213
```

Your version and PID will differ. `status:  setup` means the daemon is waiting for git: the same command prints why and a prompt for your agent (see [Coffer needs git](/guides/troubleshooting#coffer-needs-git)). Then open `http://127.0.0.1:38470/` in your browser, or open the desktop app. The page the daemon serves already carries the API token, so you are signed in with no further step.

## Start and keep the daemon running

You rarely need to start the daemon yourself:

- Any `coffer` command that needs the daemon starts it if none is running.
- `coffer-mcp-shim` does the same when an agent starts a session.
- The desktop app starts it at launch.

Once started, the daemon keeps running until you stop it or another daemon replaces it. To have macOS start it at login and restart it after a crash, turn on **Start at login** in **Settings › Daemon**.

The daemon binds `127.0.0.1:38470`. If another program already holds that port, the daemon refuses to start and names the program holding it. You can move it with `coffer config set daemon.port <port>` and go back with `coffer config unset daemon.port`. See [Running the daemon](/guides/daemon).

## Upgrade

**Desktop app.** The app checks for a new release at launch and every six hours, and **Settings › About** shows it with what's new. **Download and restart** installs it: the app verifies the update's signature, replaces itself, relaunches and restarts the daemon on the new version. **Check for updates** checks now, and you can turn **Check automatically** off. From a terminal, `coffer update` does the same through the app.

**One-line installer or release archive.** Run:

```sh
coffer update
```

It downloads the newest release's archive, checks it against the release's `SHA256SUMS`, replaces the binaries in `~/.coffer/bin` and restarts the daemon on them. An archive that does not match installs nothing. `coffer update --check` only says whether a newer release exists. The daemon also checks once a day, and **Settings › About** shows a newer version with `coffer update` to copy; it never installs anything by itself. Turn the check off there, or with `coffer daemon upgrade-auto-check --set enabled=false`.

**From source.**

```sh
git pull
source .venv/bin/activate && pip install -e ./backend
(cd frontend && npm install && npm run build)
coffer daemon restart
```

**Settings › About** can also hand the upgrade to your agent as a prompt that names the version running and how this copy was installed.

Restarting matters because a daemon that is already running keeps running the old version. When the CLI or the shim finds that the daemon's version differs from its own, it prints a one-line warning on stderr that names the daemon's executable. Before a new build applies its schema migrations, it saves `runs.db.pre-<revision>`.

## Uninstall

In the desktop app, open **Settings › About** and choose **Uninstall Coffer…**. Without the app, run:

```sh
coffer uninstall
```

Either way Coffer takes back everything it wrote outside `~/.coffer`, then stops:

- Coffer's MCP entry, memory hook and model routing in each agent's config;
- the skill links it delivered into the agents' skill folders;
- start at login;
- the command-line tools in `~/.coffer/bin` and the `PATH` lines the installer added to your shell profile;
- `Coffer.app`, which moves itself to the Trash.

`~/.coffer` stays: your vault, secrets, skills, knowledge and settings are there when you install Coffer again. Connect your agents again after a reinstall. A source checkout and its `.venv` are yours to remove. Shells that are already open keep the old `PATH` until they restart.

To delete your data as well, tick **Also delete my data** in the dialog; Coffer asks for Touch ID before anything is removed. The app also deletes the master key's Keychain items once the daemon has stopped. When the daemon belongs to the desktop app, `coffer uninstall` (with or without `--delete-data`) opens this dialog instead. After an installer or source install, `coffer uninstall --delete-data` asks you to type `delete my data`, does nothing without a terminal to type it in, and deletes `~/.coffer` but not the Keychain, which only Coffer's daemon touches: delete the `coffer` items in Keychain Access yourself. A vault you moved somewhere else is left in place.

::: danger Deleting ~/.coffer is permanent
`~/.coffer` holds your database, knowledge collections, skill library and encrypted secrets. Deleting it destroys every stored secret and every document that exists only there, including skills Coffer adopted from your agents. [Back up the master key](/guides/secrets#the-master-key-and-its-backup) first if you might want them back.
:::

## Experimental features

Every build carries the same capabilities. Two of them are experimental — Knowledge and Memory — and start switched off, in a stable release and a source build alike. Sync and Model providers are regular features, always on. Switch one on from Settings → Features. See [Experimental features](/guides/experimental-features).

## Next steps

- [Quickstart](/start/quickstart): connect Claude Code and register your first MCP server.
- [Running the daemon](/guides/daemon)
- [Distribution and releases](/architecture/distribution)
- [Troubleshooting](/guides/troubleshooting)
