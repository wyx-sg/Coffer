---
title: Install
description: Install Coffer with the one-line installer, the macOS desktop app, a release archive or from source, then verify, start, upgrade or uninstall it.
---

# Install

This page covers every supported way to install Coffer, what each one puts on disk, and how to verify, upgrade and uninstall it. If you only want to get going, run the one-line installer and continue with the [Quickstart](/start/quickstart).

::: warning No tagged release yet
The one-line installer, the desktop `.dmg` and the release archive all download from a tagged GitHub release. Until the first `v*` tag is published those downloads return 404. For now, [install from source](#from-source).
:::

## Choose an install path

| Path | Best for | Gives you |
| --- | --- | --- |
| [One-line installer](#one-line-installer) | Terminal users on a Mac | `coffer`, `coffer-daemon`, `coffer-mcp-shim` in `~/.coffer/bin` |
| [Desktop app](#desktop-app) | Anyone who prefers a window and a menu-bar icon | `Coffer.app`, plus the same three binaries once you first open it |
| [Release archive](#release-archive) | Installing by hand, or on machines with no GUI | The same three binaries, extracted wherever you choose |
| [From source](#from-source) | Contributors, Linux users, and anyone tracking `main` | A Python install with `coffer` and `coffer-mcp-shim` on your `PATH` |

Prebuilt binaries target **macOS on Apple silicon (arm64)** only. Intel Macs, Linux and Windows have no release build. On those machines, install from source (Python 3.12 or later).

Every path installs the whole of Coffer. The daemon serves the web UI itself, so a CLI install also gives you the UI (`coffer open`), and the desktop app also gives you the CLI.

## One-line installer

```sh
curl -fsSL --proto '=https' --tlsv1.2 https://wyx-sg.github.io/Coffer/install.sh | sh
```

The script:

1. Checks that you are on macOS arm64. Any other OS or architecture exits with an error that points to the from-source install.
2. Downloads `coffer-cli-aarch64-apple-darwin.tar.gz` and the release's `SHA256SUMS` from GitHub Releases, then verifies the archive's checksum. If the checksum does not match, the script stops.
3. Copies `coffer`, `coffer-daemon` and `coffer-mcp-shim` into the install directory and marks them executable.
4. If that directory is not already on your `PATH`, appends a line to your shell profile. The profile depends on your shell: `~/.zshrc` for zsh (or `$ZDOTDIR/.zshrc`), `~/.bash_profile` for bash on macOS, `~/.config/fish/config.fish` for fish (as `fish_add_path`), and `~/.profile` for anything else. Running the script again does not add the line twice.

Open a new shell, or `source` the profile the script names, so that `coffer` is on your `PATH`.

### Installer options

Set these environment variables for the `sh` process:

| Variable | Default | Effect |
| --- | --- | --- |
| `COFFER_INSTALL_DIR` | `~/.coffer/bin` | Where the three binaries are copied. |
| `COFFER_VERSION` | latest release | Install a specific tag, such as `v0.1.0`. A version without the leading `v` also works. |
| `COFFER_NO_MODIFY_PATH` | unset | Set to `1` to leave your shell profile alone. The script prints the line to add instead. |

```sh
curl -fsSL --proto '=https' --tlsv1.2 https://wyx-sg.github.io/Coffer/install.sh \
  | COFFER_VERSION=v0.1.0 COFFER_NO_MODIFY_PATH=1 sh
```

A binary installed by `curl` is not quarantined, so macOS Gatekeeper does not block it.

## Desktop app

1. Download `Coffer-unsigned-aarch64-apple-darwin.dmg` from [Releases](https://github.com/wyx-sg/Coffer/releases/latest).
2. Open the `.dmg` and drag **Coffer** to **Applications**.
3. The app is not code-signed or notarised, so macOS refuses a browser-downloaded copy with "Coffer is damaged and can't be opened". The app is not damaged. Clear the quarantine flag and open it again:

   ```sh
   xattr -dr com.apple.quarantine /Applications/Coffer.app
   ```

4. Open Coffer. The app finds a running daemon, or starts the one bundled inside it, and shows the UI in a native window. A menu-bar icon stays after you close the window.

The app bundles the same three binaries as the release archive. The first time its daemon starts, it copies them into `~/.coffer/bin`. To use the CLI as well, add that directory to your `PATH`:

```sh
export PATH="$HOME/.coffer/bin:$PATH"   # add to your shell profile
```

See [Desktop app](/guides/desktop-app) for the tray menu, restarts and the offline banner.

## Release archive

Each release publishes `coffer-cli-aarch64-apple-darwin.tar.gz` and one `SHA256SUMS` file that covers every file in the release.

```sh
shasum -a 256 -c SHA256SUMS --ignore-missing   # verify what you downloaded
mkdir -p ~/.coffer/bin
tar -xzf coffer-cli-aarch64-apple-darwin.tar.gz -C ~/.coffer/bin
export PATH="$HOME/.coffer/bin:$PATH"          # add to your shell profile
```

Keep the three binaries together in one directory. `coffer` and `coffer-mcp-shim` look for `coffer-daemon` beside them when they need to start the daemon. If you downloaded the archive in a browser, clear the quarantine flag with `xattr -dr com.apple.quarantine ~/.coffer/bin`.

## From source

You need Python 3.12 or later and git. Node.js is required to build the web UI, and [ripgrep](https://github.com/BurntSushi/ripgrep) (`rg`) is recommended. Knowledge curation uses `rg` to select candidate documents, and falls back to a slower built-in search when it is missing.

```sh
git clone https://github.com/wyx-sg/Coffer.git
cd Coffer
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ./backend
```

`pip install` puts two console scripts on the venv's `PATH`: `coffer` and `coffer-mcp-shim`. A source install has no separate `coffer-daemon` binary. The CLI and the shim start the daemon from the same Python environment.

Build the web UI once so the daemon has something to serve. Without it, the API and the MCP endpoint still work, but `coffer open` has no page to open.

```sh
cd frontend && npm install && npm run build && cd ..
```

::: tip Contributor setup
`make install` creates `.venv`, installs the backend with its development extras, and installs the frontend's npm dependencies. `make dev` then runs the daemon on port 8000 and the Vite dev server on port 5173 with hot reload. See [Development setup](/contributing/development).
:::

### Frozen binaries and the app from source

| Command | Produces |
| --- | --- |
| `make bundle-binaries` | `coffer`, `coffer-daemon` and `coffer-mcp-shim` frozen with PyInstaller into `dist/`, the same layout as the release archive |
| `make desktop` | `Coffer.app` and an unsigned `.dmg`. Needs a Rust toolchain and Node.js, and takes roughly 50 minutes because it runs PyInstaller first. |

## What gets installed where

| Path | What it is |
| --- | --- |
| `~/.coffer/bin/coffer`, `coffer-daemon`, `coffer-mcp-shim` | The public names. For a release build these are symlinks into a versioned directory. |
| `~/.coffer/bin/<version>/` | One directory per deployed build. The current and previous versions are kept, so you can roll back by pointing the links at the older directory. |
| `~/.coffer/coffer.db` | The SQLite database: resources, settings, audit log, encrypted credentials. |
| `~/.coffer/coffer.db.pre-<revision>` | A copy taken before each schema migration. The three newest are kept. |
| `~/.coffer/master.key` | The credential master key (mode `0600`), unless you moved it to the keychain. |
| `~/.coffer/daemon.json` | Runtime discovery file: PID, port and API token (mode `0600`). Written at start and removed at exit. |
| `~/.coffer/daemon-config.json` | Settings read before the daemon starts: a fixed port, the machine name, experimental-feature switches. |
| `~/.coffer/skills/`, `knowledge/`, `memory/` | The file-backed kinds' trees. |
| `~/.coffer/logs/daemon.log` | The daemon log, shared by the daemon, its child processes and the desktop app. |

A release-built daemon manages `~/.coffer/bin` itself. At every start it checks whether its build is already deployed there. If not, it copies the three binaries into `~/.coffer/bin/<version>/` and switches the public symlinks to them in one atomic step. A source install never does this. The [files and directories](/reference/filesystem) reference lists every path.

## Verify the install

```sh
coffer daemon start
coffer daemon status
```

```text
status:  ready
version: 0.1.1
channel: dev
port:    8000
pid:     48213
```

Your version and PID will differ. `channel` is `stable` for a release build and `dev` for anything else. Then open the UI:

```sh
coffer open
```

`coffer open` reads `~/.coffer/daemon.json` and opens your browser at `http://127.0.0.1:8000/`. The page it loads already carries the API token, so you are signed in with no further step. Pass `--no-browser` to print the URL instead.

## Start and keep the daemon running

You rarely need to start the daemon yourself:

- Any `coffer` command that needs the daemon starts it if none is running.
- `coffer-mcp-shim` does the same when an agent starts a session.
- The desktop app starts it at launch.

Once started, the daemon keeps running until you stop it or another daemon replaces it. To have macOS start it at login and restart it after a crash, install the login service:

```sh
coffer daemon service install    # coffer daemon service status | uninstall
```

The daemon binds `127.0.0.1:8000`. If another program already holds that port, the daemon refuses to start and names the program holding it. You can move it with `coffer daemon port set <port>` and go back with `coffer daemon port clear`. See [Running the daemon](/guides/daemon).

## Upgrade

::: code-group

```sh [Installer]
curl -fsSL --proto '=https' --tlsv1.2 https://wyx-sg.github.io/Coffer/install.sh | sh
coffer daemon restart
```

```sh [Source]
git pull
source .venv/bin/activate && pip install -e ./backend
(cd frontend && npm install && npm run build)
coffer daemon restart
```

:::

For the desktop app, quit Coffer, stop the daemon with `coffer daemon stop`, replace `Coffer.app` with the new version and clear its quarantine flag again. The next launch starts the new daemon, which deploys the new binaries.

Restarting matters because a daemon that is already running keeps running the old version. When the CLI or the shim finds that the daemon's version differs from its own, it prints a one-line warning on stderr that names the daemon's executable. Before a new build applies its schema migrations, it saves `coffer.db.pre-<revision>`.

## Uninstall

1. Remove Coffer's entry from each agent, and remove the agent from Coffer. Removing the agent also removes the skill links Coffer delivered into it:

   ```sh
   coffer agent mcp uninstall claude-code
   coffer memory delivery-remove claude-code   # only if you installed memory delivery
   coffer agent rm claude-code
   ```

2. Stop the daemon and remove the login service if you installed it:

   ```sh
   coffer daemon service uninstall
   coffer daemon stop
   ```

3. Remove the binaries: `rm -r ~/.coffer/bin`. Delete the `# Added by Coffer installer` line and the `PATH` line after it from your shell profile. For the desktop app, move `Coffer.app` from **Applications** to the Bin.
4. Optionally, delete the vault itself.

::: danger Deleting ~/.coffer is permanent
`~/.coffer` holds your database, knowledge collections, skill library and credential master key. Deleting it destroys every stored secret and every document that exists only there. Copy it somewhere first if you might want it back.
:::

## Release channel

Every build has a **channel**. A tagged release is stamped `stable`. Source runs, `make desktop` and `make bundle-binaries` are `dev`. The channel sets only the default for the experimental features (Sync, Knowledge and Memory): off on `stable`, on on `dev`. You can switch any of them on each machine under **Settings → General** or with `coffer daemon features enable <key>`. See [Experimental features](/guides/experimental-features).

## Next steps

- [Quickstart](/start/quickstart): connect Claude Code and register your first MCP server.
- [Running the daemon](/guides/daemon)
- [Distribution and releases](/architecture/distribution)
- [Troubleshooting](/guides/troubleshooting)
