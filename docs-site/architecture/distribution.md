---
title: Distribution and releases
description: How Coffer is built into frozen binaries, released as a CLI archive and a desktop .dmg, signed and notarised when the secrets exist, updated in place by the desktop app, installed into versioned directories under ~/.coffer/bin, stamped with a commit and hardened for tagged releases, and gated by experimental features.
---

# Distribution and releases

This page explains how Coffer's Python code reaches a machine with no Python on it: the four frozen binaries, the release workflow that produces them, how a release is signed and notarised, how the desktop app updates itself, the two download tiers, how a new build is installed beside the old one, and how experimental features are switched on, one machine at a time. It is for contributors who build or release Coffer and for anyone who wants to know what is actually on their disk.

## The problem

Coffer is a Python program, but its users are people running AI coding agents, not Python developers. A distribution that asks them to install the right Python, create a virtual environment and recover from a wheel build error loses most of them before the first run. At the same time:

- **Three processes have to find each other.** The MCP client launches `coffer-mcp-shim`; the shim has to find and, if needed, start `coffer-daemon`; the `coffer` CLI has to do the same.
- **Upgrades must not break the running system.** A daemon may be running, and an MCP client may be about to spawn a shim, at the moment a new build lands.
- **Unfinished features must ship without harming people who did not ask for them.** A single release line serves both the owner's daily testing and everyone else.
- **Coffer is self-distributed.** A release is signed only once the owner has an Apple Developer ID, and until then every consequence of being unsigned — Gatekeeper, a debugger attaching to the daemon — has to be designed around rather than assumed away.
- **A desktop user does not watch a releases page.** The app has to find and install its own updates, without trusting anything but a key it was built with.

## Design decisions

| Decision | Reason |
| --- | --- |
| Freeze each entry point with PyInstaller into a single-file executable | Runs on a clean machine with no Python; one build serves CLI use, MCP-client spawn and direct download. |
| Ship four binaries, always together | The shim and the CLI find `coffer-daemon` as a sibling, so co-location is the discovery mechanism. `coffer-seatalk-bridge` is the fourth: it loads the SeaTalk SDK outside the daemon and is signed without the keychain entitlement. |
| Two download tiers built in one job from the same binaries | The desktop app cannot drift from the CLI archive it wraps. |
| The daemon deploys its siblings into versioned directories under `~/.coffer/bin` and flips symlinks | A deploy never overwrites a binary that may be running, and the previous build stays for a manual rollback. |
| One build for everyone, every experimental feature off until a person switches it on | There is no release branch and no second build: the owner tests exactly what users run. |
| A build stamp: the commit, and a `stable` mark on tagged releases | A tagged release ignores the development environment switches for host and CORS checks. Nothing a person sees changes. |
| Experimental features gated at request time, per machine | Switching a feature takes effect without a restart and never deletes what it holds. |
| Sign, notarise and publish the updater feed only when the credentials are present | The same workflow builds a signed release for the owner and an unsigned one everywhere else, and stays green in both. |
| The desktop app updates from a minisign-signed manifest on GitHub Releases | The update is verified against a key compiled into the app, so neither GitHub nor the network is trusted with what gets installed. |

## The binaries

Each binary is frozen from its own PyInstaller spec in `backend/`, one per entry point: the daemon's, the shim's and the CLI's.

| Binary | What it contains |
| --- | --- |
| `coffer-daemon` | The whole backend: FastAPI and uvicorn, SQLAlchemy and aiosqlite, alembic with its migration scripts as data files, the MCP SDK, document converters, model SDKs, and the built web UI when the frontend has been built (`frontend/dist`) at build time. |
| `coffer-mcp-shim` | The stdio-to-HTTP bridge an MCP client launches. Excludes FastAPI, uvicorn, SQLAlchemy, alembic and structlog, so it starts quickly for clients that spawn it every session. |
| `coffer` | The Typer CLI, httpx, and the `keyring` backends: a thin HTTP client of the daemon. Excludes the web server, SQLAlchemy, Alembic and the MCP SDK. |

Each spec builds a single-file console executable without UPX compression, and each freezes the interpreter option `-X utf8` in. That option matters only for the shipped binary: an unfrozen interpreter in the C locale turns UTF-8 mode on by itself, but a frozen binary started from Finder or launchd with no `LANG` would otherwise fall back to ASCII.

PyInstaller finds imports by static analysis, so anything imported lazily inside a function — document converters, model SDKs — is pinned in the spec's list of hidden imports, and package data files are collected explicitly. A spec check runs in `make lint` and fails when a spec's entry script or a data-file source path no longer exists, or when a spec loses `-X utf8`. No CI job other than the release runs PyInstaller, so this check is what keeps the specs level with the tree between releases.

### Building locally

```sh
make bundle-binaries        # runs scripts/build_binaries.sh → dist/coffer, dist/coffer-daemon, dist/coffer-mcp-shim
bash scripts/smoke_test_bundle.sh dist
```

The build script runs PyInstaller from `backend/` (where the specs' relative paths resolve) with output redirected to the repository's `dist/` and `build/`. It detects the host's target triple (`aarch64-apple-darwin`, `x86_64-apple-darwin`, the Linux and Windows triples) for naming, but builds only for the host.

The smoke test starts the bundled daemon under an isolated `HOME`, with a free daemon port and proxy port and a master key of its own, so it runs beside a Coffer already on the machine and never touches that Coffer's key. It waits for `daemon.json` and `/api/v1/daemon/status`, checks that `/` serves the bundled web UI, runs the bundled `coffer daemon status` against the daemon, then sends one JSON-RPC `initialize` through the bundled shim and expects a reply within 15 seconds. On exit it stops the daemon and the model proxy the daemon started. Pointed at `Coffer.app/Contents/MacOS`, it tests the copies the desktop app carries.

## The release workflow

The release workflow (in `.github/workflows/`) runs on a pushed `v*` tag (and on manual dispatch, which builds artifacts without publishing). It has one build job on a `macos-14` runner for `aarch64-apple-darwin`, and one publish job.

```mermaid
flowchart TD
    T["push tag v*"] --> I["uv sync --frozen, npm ci"]
    I --> F["build frontend (codegen + vite build)"]
    F --> P["release plan: which secrets are present"]
    P --> S["stamp build (+ access group when signing)"]
    S --> B["build binaries (PyInstaller x3, signed when possible)"]
    B --> K["smoke test (+ verify signatures, notarise)"]
    K --> A["coffer-cli-aarch64-apple-darwin.tar.gz"]
    K --> D["stage binaries → tauri build (sign, notarise, updater archive)"]
    D --> G["Coffer[-unsigned]-aarch64-apple-darwin.dmg"]
    D --> U["Coffer_aarch64-apple-darwin.app.tar.gz + .sig + latest.json"]
    A --> H["SHA256SUMS"]
    G --> H
    U --> H
    H --> R["GitHub Release"]
```

1. Install the backend from its lockfile (`uv.lock`) with `uv sync --frozen`, so the tagged build uses exactly the locked dependency set.
2. Build the frontend (`npm run codegen`, `npm run build`). The daemon spec picks up `frontend/dist` as the served web UI.
3. Decide which signing steps can run (see [Signing, notarisation and updates](#signing-notarisation-and-updates)). When a Developer ID is present, import it into a temporary keychain and stamp the keychain access group.
4. Stamp the build: the commit always, and the `stable` mark on a tag (see [The build stamp](#the-build-stamp)).
5. Freeze the four binaries — signed with the Developer ID when there is one — and run the smoke test against `dist/`. A signed build then has its signatures verified and the binaries notarised.
6. Package `coffer`, `coffer-daemon` and `coffer-mcp-shim` into `coffer-cli-<triple>.tar.gz`.
7. Stage the same four files in the desktop crate as `<name>-<triple>` and run `tauri build`, producing the `.dmg` — `Coffer-<triple>.dmg` when signed (then notarised and stapled), `Coffer-unsigned-<triple>.dmg` otherwise — and, with the updater key, the signed updater archive and `latest.json`.
8. Write `SHA256SUMS` over every artifact, then create (or update, with `--clobber`) the GitHub Release for the tag.

Only macOS on Apple Silicon is published. The specs and build script are cross-platform, so widening the release matrix is a workflow change rather than a redesign.

Versions are kept in several files that must agree exactly — the Python package, the frontend `package.json` and lockfile, the desktop crate and its Tauri configuration among them. One version-bump script rewrites all of them in one step, and an integration test pins that they agree. The desktop app compares its own version with the `version` reported by `/api/v1/daemon/status`; when they differ, the web UI shows a **Daemon out of date** banner with a restart action.

## The desktop bundle

The desktop app is a Tauri 2 shell around the same web UI the daemon serves. Its Tauri configuration bundles `app` and `dmg` targets, loads the built frontend as local assets, and lists the four binaries as external binaries. Tauri resolves each binary name to `<name>-<target-triple>` and places it in `Coffer.app/Contents/MacOS/`, next to the app's own executable.

When the app starts, it resolves a daemon in a fixed order: an already-running daemon named by `~/.coffer/daemon.json` (attached to, never re-spawned); the binary inside the app bundle; `~/.coffer/bin/coffer-daemon`; `coffer-daemon` on `PATH`; otherwise a message telling you to install the CLI. The shell never writes to `~/.coffer/bin` itself — the daemon it starts does that (next section). Installing the app therefore installs the CLI too.

| Target | What it does |
| --- | --- |
| `make desktop` | Builds the frontend, runs `make bundle-binaries`, stages the binaries under the host triple, and runs `tauri build`. Produces an unsigned `.app` and `.dmg` under `desktop/target/release/bundle/`. Takes roughly 50 minutes, mostly PyInstaller. |
| `make desktop-stage-binaries` | Stages placeholder scripts for any missing external binary, so `cargo` can compile the crate without a frozen build. |
| `make desktop-lint` | `cargo check` and `cargo clippy -D warnings`. |
| `make desktop-test` | `cargo test`. |

The `desktop` GitHub workflow runs `desktop-lint` and `desktop-test` on Ubuntu for changes under `desktop/`; it never bundles. None of the desktop targets are part of `make verify`, because they need a Rust toolchain.

See [Desktop app](/guides/desktop-app) for using it.

## Installing into `~/.coffer/bin`

### The one-line installer

`install.sh` is served from the documentation site and is POSIX `sh`:

```sh
curl -fsSL --proto '=https' --tlsv1.2 https://wyx-sg.github.io/Coffer/install.sh | sh
```

It accepts only macOS on `arm64` and points everyone else at a source install. It downloads `coffer-cli-aarch64-apple-darwin.tar.gz` and `SHA256SUMS` from the latest release (or the tag in `COFFER_VERSION`), verifies the archive's checksum, installs the four binaries into `COFFER_INSTALL_DIR` (default `~/.coffer/bin`) by copying each to a temporary sibling and renaming it over the public name — a plain copy would write through the daemon's symlink into the previous version directory and destroy the build a rollback needs — and — unless `COFFER_NO_MODIFY_PATH=1` — appends a `PATH` line to your shell profile (`.zshrc`, `.bash_profile`, fish's `config.fish`, or `.profile`) if the directory is not already on `PATH`. A binary downloaded by `curl` is never quarantined, so this path needs no `xattr` step. See [Install](/start/install).

### Versioned directories and the symlink flip

Every frozen daemon, whichever tier it came from, deploys its sibling binaries at startup. A source install skips this, because `pip install` already put the console scripts on `PATH`.

```text
~/.coffer/bin/
├── coffer            -> 0.2.0/coffer
├── coffer-daemon     -> 0.2.0/coffer-daemon
├── coffer-mcp-shim   -> 0.2.0/coffer-mcp-shim
├── 0.2.0/
│   ├── coffer-daemon
│   ├── .coffer-daemon.version
│   └── …
└── 0.1.1/            the previous build, kept for rollback
```

```mermaid
stateDiagram-v2
    [*] --> Check: daemon starts (frozen)
    Check --> Skip: already running from ~/.coffer/bin, or copy current
    Check --> Copy: missing, size differs, no sentinel, or link elsewhere
    Copy --> Sentinel: temp file, chmod +x, rename into version dir
    Sentinel --> Flip: write .name.version
    Flip --> Prune: relative temp symlink renamed over the public name
    Prune --> [*]: keep newest 2 version dirs, never one in use
    Skip --> [*]
```

For each of `coffer`, `coffer-daemon` and `coffer-mcp-shim`:

1. **Decide.** A deploy is needed when `~/.coffer/bin/<version>/<name>` is missing, differs in size from the running build's sibling, lacks its `.<name>.version` sentinel (a copy that never completed), or the public name does not point at it. Modification time is not used: it records when a build was extracted, not what it contains.
2. **Copy.** The binary is copied to a temporary name, made executable, and renamed into the version directory. The sentinel is written last, so a sentinel means a complete copy.
3. **Flip.** A relative symlink is created under a temporary name and renamed over `~/.coffer/bin/<name>`. A concurrent `exec` sees either the old binary or the new one, never a partial file.
4. **Retire and prune.** A public symlink into a version directory under a name this build no longer ships is removed. Version directories beyond the newest two are deleted, except any directory a public symlink still points into.

Deployment is best-effort: a binary that cannot be copied is logged and skipped, and the daemon starts anyway. To roll back by hand, point the symlinks at the previous version directory.

Before running database migrations, the daemon also copies `runs.db` (and its `-wal`/`-shm` files) to `runs.db.pre-<revision>`, keeping the three most recent copies. See [Persistence](/architecture/persistence).

::: warning
`install.sh` installs plain files into `~/.coffer/bin`, each renamed over its public name, so a symlink left by an earlier deploy is replaced rather than written through and the version directories stay intact. A daemon running from `~/.coffer/bin` itself skips the deploy, so an installer-only machine has no version directories until a build from another location (such as the desktop app) starts a daemon.
:::

## The build stamp

Every build carries one internal stamp in the backend package: the commit it was built from, and a mark that says whether it is a tagged release. The repository always says `dev`; on a tag, the release workflow rewrites the mark to `stable` before PyInstaller runs. Whether the binary is frozen is not the signal: the owner's own testing build is frozen too and stays `dev`.

The mark is a security detail and nothing else. A tagged release ignores the development environment switches `COFFER_ALLOWED_HOSTS`, `COFFER_CORS_ORIGINS` and `COFFER_DEV_CORS`, so a stray variable cannot widen the Host and Origin checks of a shipped build (see [Security model](/architecture/security#the-host-and-origin-checks)). It changes no default, no screen and no report: a build from source and a release behave identically, and nothing in the daemon status, the CLI or Settings names a channel.

## Experimental features

An experimental feature is a capability that ships in every build but is off until you switch it on. The feature registry in the domain layer is the one list; anything not in it is always on. Each entry names a key, the REST prefixes the feature owns and the resource kinds it owns.

The registry holds four entries, in this order: `knowledge`, `memory`, `sync` (vault sync) and `models` (model providers, the local model proxy and Usage). Conversations and Channels are always on. An earlier design also had `run` and `context` entries; they are gone, and `context` split into `knowledge` and `memory`. Settings stored under a key the registry does not declare, and no table lists, are ignored, so a leftover one is harmless. A feature that graduates or is retired is listed in one of two small tables beside the registry instead: at startup the daemon applies them once to `daemon-config.json`, removing a graduated feature's switch and moving the settings it names to their new keys, and removing a retired feature's switch and the settings it names. Both tables are empty today.

No feature hard-depends on another. A switched-off feature simply leaves its part out of whatever else shows it: with `knowledge` off the `coffer-guide` skill has no knowledge sections; with `memory` off channel turns carry no memory; with `models` off the speech-to-text connection still resolves.

A feature's state is resolved on every read, highest precedence first:

1. a pin from the `COFFER_FEATURES` environment variable (`key=on|off`, comma-separated), fixed for the daemon's lifetime;
2. the machine's own setting, stored in `~/.coffer/daemon-config.json`;
3. the default, which is off for every feature in every build.

The status reports which of the three decided: `pin`, `setting` or `default`.

```mermaid
flowchart LR
    Q["request under a feature's prefix"] --> G{"feature gate (key)"}
    G -->|pin?| P["COFFER_FEATURES"]
    G -->|setting?| S["daemon-config.json"]
    G -->|else| C["default: off"]
    G -->|on| R["route runs"]
    G -->|off| X["404 FEATURE_DISABLED"]
```

The gates are request-time:

- Every router whose prefix falls under a feature's prefix is mounted with a feature-gate dependency that checks the feature's state. The routes stay registered, so the OpenAPI document never changes with the switch, and a switch takes effect on the next request.
- The kind-agnostic `/api/v1/resources` routes refuse a resource whose kind a switched-off feature owns, and leave such resources out of lists.
- The MCP gateway's one builtin tool, `coffer__search_tools`, belongs to no feature, so switching a feature on or off never changes the tool list.
- CLI commands reach the daemon over the gated routes and print the daemon's one line naming **Settings › Features** as where to switch it on, then exit 1.
- Background passes owned by the feature skip their rounds: the knowledge sweep while `knowledge` is off, distil and aggregate while `memory` is off, the usage ingest and price refresh while `models` is off, and the converge worker while `sync` is off.
- Whatever a feature put in front of agents is withdrawn and returns on switch-on: the memory delivery hook and the memory root named in the guide (`memory`), the knowledge sections of the `coffer-guide` skill (`knowledge`), and the provider projection into each agent's own config plus an empty model-proxy state (`models`).
- The web UI reads the state off the daemon status, and a switched-off feature looks absent: its sidebar entry, palette entries, Overview figures and page sections are gone, and a link into its page lands on the not-found page. There is no notice and no switch-on button on the page itself. **Settings → Features** is the one place to switch a feature on, and it exists in every build.

Switching a feature off never deletes, moves or rewrites what it holds; switching it back on resumes from the same state. Features change in **Settings › Features**, with `coffer settings feature set <key> --set enabled=true|false`, or with `PUT /api/v1/daemon/features/{key}`; a pinned feature refuses the change with `409 FEATURE_PINNED`. A feature joins by adding one registry entry and gating its surfaces through it; it leaves (graduates) once it is ready, by deleting its entry and every gate that names it, and by adding one entry to the graduated or retired table, which removes its stored switch (and moves or removes the settings it names) at the next daemon start. See [Experimental features](/guides/experimental-features).

## Signing, notarisation and updates

Three kinds of credential turn an unsigned release into a signed one, and each is optional. A release-plan step is handed only whether each secret is set — never its value — and answers three questions the later steps' `if:` conditions read. Every step it turns off is announced on the run page with the secret it is missing, and the unsigned release is built and published exactly as before, so a fork or a repository without the secrets stays green.

| Step | Runs when these are set | What it does |
| --- | --- | --- |
| Developer ID signing | `APPLE_CERTIFICATE`, `APPLE_CERTIFICATE_PASSWORD`, `APPLE_TEAM_ID` | Imports the certificate into a temporary keychain; stamps `<TEAM_ID>.coffer` into the backend's build identity and the shell; PyInstaller signs each frozen binary and every library it collects, and Tauri signs the app, under the hardened runtime with the `keychain-access-groups` entitlement and without `get-task-allow`; the signatures are verified before packaging. |
| Notarisation | the above, plus `APPLE_API_KEY`, `APPLE_API_KEY_ID`, `APPLE_API_ISSUER` | `notarytool` notarises the CLI binaries (as a zip; a bare binary cannot be stapled), Tauri notarises and staples the app before building the `.dmg` and the updater archive from it, and the workflow notarises and staples the `.dmg`. |
| Updater feed | `TAURI_SIGNING_PRIVATE_KEY` (and its password, if it has one), and the repository variable `COFFER_UPDATER_PUBKEY` | Tauri signs `Coffer.app.tar.gz` with the updater key; a manifest step writes `latest.json`; the public key is compiled into the shell. |

### The keychain access group

The master key lives in the data-protection Keychain in the access group `<TEAM_ID>.coffer`, which only binaries signed by that team and carrying the `keychain-access-groups` entitlement can read ([ADR: the master key lives in the macOS Keychain](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/master-key-lives-in-the-macos-keychain.md)). One Team ID sets it in three places at once: a stamping step rewrites the access-group constant in the backend's build identity before PyInstaller freezes it, the shell is compiled with `COFFER_KEYCHAIN_ACCESS_GROUP`, and the entitlements template in `desktop/` is rendered with the same ID for every signature. A build that is not stamped — every build from source and every unsigned release — reports itself as a development build. Whether a Developer ID build needs a provisioning profile for the entitlement is still to be proven; an optional `APPLE_PROVISIONING_PROFILE` secret is embedded in the app when present. `coffer-seatalk-bridge` is the one exception: it is signed with the hardened runtime but without that entitlement, and the app bundle ships it without re-signing, so the third-party SeaTalk SDK it loads can never read the master key.

### How the desktop app updates

```mermaid
sequenceDiagram
    participant App as Coffer.app (shell)
    participant GH as GitHub Releases
    participant D as daemon
    App->>GH: GET releases/latest/download/latest.json (launch + 30 s, then every 6 h)
    GH-->>App: version, notes, url, signature
    App->>App: record for Settings › About and the menu bar
    Note over App: nothing installs until the user chooses Download and restart
    App->>GH: GET Coffer_<triple>.app.tar.gz
    App->>App: verify the minisign signature and the signed version against the built-in key
    App->>App: replace Coffer.app, relaunch
    App->>D: shutdown (the previous version's daemon)
    App->>D: spawn the new version's daemon, wait for it to answer
```

The updater (Tauri's updater plugin) runs in the shell's Rust process; the webview has none of its permissions and its content policy stays loopback-only. The shell checks the manifest named as the updater endpoint in its Tauri configuration and verifies each archive against the public key it was compiled with. The updater also requires the signed version to match, rejecting an archive signed for a different version than the manifest names, so an altered manifest cannot pair a new version number with an older release. A build compiled without a key never checks. After installing, the shell relaunches with a marker in its environment, and the relaunched shell's first handshake replaces the previous version's daemon through the same restart the menu bar uses. See [Desktop app → Update](/guides/desktop-app#update).

### An unsigned release

Without a Developer ID, macOS quarantines a downloaded archive or `.dmg`. Clear it with `xattr -dr com.apple.quarantine <extracted-directory>`, or `xattr -dr com.apple.quarantine /Applications/Coffer.app` after dragging the app across. The one-line installer's download is not quarantined. The release notes and the `.dmg` file name (`Coffer-unsigned-…`) say this up front. An unsigned daemon is also ad-hoc signed without the hardened runtime, so a same-user debugger can attach to it; that is what a development build gives up.

### What the owner provides

[`RELEASING.md`](https://github.com/wyx-sg/Coffer/blob/main/RELEASING.md) is the checklist: an Apple Developer Program membership, a Developer ID Application certificate exported as a `.p12`, the Team ID, an App Store Connect API key for notarisation, and an updater key pair generated with `tauri signer generate` — the private key and its password as repository secrets, the public key as a repository variable.

## Trade-offs and alternatives

**Requiring Python.** Publishing to PyPI and asking users to `pipx install` would avoid PyInstaller entirely. It fails the "clean machine" requirement and moves dependency-resolution errors onto users. Source install stays available for contributors.

**Size and start-up.** A frozen binary is large (tens of megabytes each) and starts slower than a system interpreter. The daemon starts once and stays up, and the shim excludes the server stack to keep its start-up short, so the cost is paid rarely.

**A release branch for unfinished work.** Keeping experimental work on a branch would keep `stable` clean, but every fix would need to land twice and the owner would not be testing what users run. Per-machine switches, all off by default, give one codebase and one build.

**Overwriting binaries in place.** Simpler, but a deploy could replace a file a running process is about to `exec`, and a bad build would leave nothing to return to. Versioned directories cost one extra copy on disk.

**Per-secret keychain storage with code signing.** One Keychain item per secret would keep secrets out of `~/.coffer`, but vault sync could no longer carry ciphertext between machines. Envelope encryption keeps a single Keychain item — the master key — and reads it through the access group instead of an access list.

**Downloading updates in the background.** The update would be ready the moment the user asks, but it spends a metered connection on a version the user may never want, and a verified archive would have to be kept somewhere between runs. The app downloads only when the user chooses Download and restart.

**An update feed the app trusts by transport.** Serving the manifest over HTTPS from GitHub would be simpler than signing each archive, but it would make whoever controls the release, the account or the network path able to install code on every Mac running Coffer. The minisign key is held only as a repository secret.

## Where it lives in the code

| Directory | What it holds |
| --- | --- |
| `backend/` | the three PyInstaller specs |
| `scripts/` | building, smoke-testing, spec checking, build and build-identity stamping, release planning and signing, the update manifest, version bumping |
| `.github/workflows/` | the release workflow and the `desktop` check workflow |
| `desktop/` | the Tauri shell: bundle configuration, entitlements, daemon resolution order, the updater |
| `docs-site/public/` | the one-line installer |
| the backend's application layer | the versioned deploy and symlink flip, experimental-feature state; the HTTP surface holds the request-time gates and the pre-migration database copy |

## Related

- Guides: [Install](/start/install), [Desktop app](/guides/desktop-app), [Running the daemon](/guides/daemon), [Experimental features](/guides/experimental-features)
- Reference: [Files and directories](/reference/filesystem), [Configuration](/reference/configuration)
- Architecture: [Daemon and processes](/architecture/daemon), [Security model](/architecture/security), [Persistence](/architecture/persistence)
- Checklist: [RELEASING.md](https://github.com/wyx-sg/Coffer/blob/main/RELEASING.md)
- Decision records: [The Master Key Lives in the macOS Keychain](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/master-key-lives-in-the-macos-keychain.md), [Distribution — PyInstaller-Bundled Daemon, Shim, and CLI](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/distribution-pyinstaller.md), [Daemon Detect-or-Spawn Pattern](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/daemon-detect-or-spawn.md), [The Desktop Shell Returns, Owning Only What a Browser Cannot Do](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/desktop-shell-over-a-shared-frontend.md), [Experimental Features Instead of a Release Branch](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/experimental-features-instead-of-a-release-branch.md), [The Master Key Lives in a Keychain Access Group Only Coffer's Signed Binaries Can Read; Secrets Stay Envelope-Encrypted in the Vault](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/master-key-lives-in-the-macos-keychain.md)
- Specs: [daemon](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/daemon/spec.md), [desktop-app](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/desktop-app/spec.md), [experimental-features](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/experimental-features/spec.md)
