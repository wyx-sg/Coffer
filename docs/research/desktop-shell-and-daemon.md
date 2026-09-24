# Desktop shell and resident daemon: how other products do it

**Feature**: a local developer tool shipped as one download that contains a resident background daemon (localhost HTTP API on a fixed port, a discovery file, a login service), a native desktop shell (tray icon, window hosting a web UI that authenticates to the daemon) and a CLI. · **Coffer spec**: [daemon](../../openspec/specs/daemon/spec.md), [desktop-app](../../openspec/specs/desktop-app/spec.md) · **Related ADRs**: [desktop shell over a shared frontend](../decisions/desktop-shell-over-a-shared-frontend.md), [daemon detect-or-spawn](../decisions/daemon-detect-or-spawn.md), [daemon binds a fixed port](../decisions/daemon-binds-a-fixed-port.md), [daemon is a resident login service](../decisions/daemon-is-a-resident-login-service.md), [daemon auth and origin guard](../decisions/daemon-auth-and-origin-guard.md), [distribution with PyInstaller](../decisions/distribution-pyinstaller.md)

**Researched**: 2026-09 · **Method**: web research, primary sources (repository source at HEAD of the default branch, official docs, advisories). Star counts from the GitHub API, as of 2026-09-24.

---

## 1. The field at a glance

| Product | ~Stars | Shell | Daemon / server | Where it listens | How clients find it | How the UI / CLI authenticates |
| --- | --- | --- | --- | --- | --- | --- |
| [Ollama](https://github.com/ollama/ollama) | 182k | Native Cocoa menubar + WKWebView (Go host) | `ollama serve` child of the app | `127.0.0.1:11434` fixed | Fixed port / `OLLAMA_HOST` | API: none (Host allowlist + CORS allowlist). App UI: per-launch token cookie |
| [cc-switch](https://github.com/farion1231/cc-switch) | 136k | Tauri 2 (tray, single instance) | In-process axum proxy | `127.0.0.1:15721` default | Stored in its own DB | None (the proxy is loopback-only) |
| [Syncthing](https://github.com/syncthing/syncthing) | 89k | Separate tray wrappers ([syncthing-macos](https://github.com/syncthing/syncthing-macos) 3.9k) | `syncthing` with its own monitor process | `127.0.0.1:8384` | `config.xml` | API key header, or session + CSRF token; Host check |
| [code-server](https://github.com/coder/code-server) | 79k | None (browser) | Node server | `127.0.0.1:8080` | `~/.config/code-server/config.yaml` | Password cookie; Origin must equal Host |
| [AnythingLLM](https://github.com/Mintplex-Labs/anything-llm) | 66k | Electron (desktop build is closed) | Embedded copy of the Docker server | `localhost:3001` fixed, not configurable | Fixed port | Bearer API key for the developer API |
| [Jan](https://github.com/janhq/jan) | 45k | Tauri 2 | Optional OpenAI-compatible server | `127.0.0.1:1337` | Fixed default, user-set | Bearer API key; trusted-hosts list |
| [Tailscale](https://github.com/tailscale/tailscale) (macOS) | 37k | Native app + system/network extension | `tailscaled` inside the extension | Random `127.0.0.1` port (GUI variants), Unix socket (open-source) | `sameuserproof` file in `/Library/Tailscale` | Token in Basic auth; rejects any request with `Origin` or `Referer` |
| [JupyterLab](https://github.com/jupyterlab/jupyterlab) / [jupyter_server](https://github.com/jupyter-server/jupyter_server) | 15k | None (browser) | Python server | `localhost:8888`, tries up to 50 more | `jpserver-<pid>.json` in runtime dir | Per-start token in URL/header, then cookie; XSRF; Host check |
| [LM Studio](https://lmstudio.ai) (`lms` CLI [5.3k](https://github.com/lmstudio-ai/lms)) | closed app | Electron | App backend, or headless `llmster` daemon | OpenAI server `1234`; internal API on a published port | `~/.lmstudio/.internal/http-server.json`, then a 5-port scan | CLI: build-time key + per-install key file |
| Docker Desktop | closed | Electron dashboard + menubar | Engine in a Linux VM | Unix socket `~/.docker/run/docker.sock` | `DOCKER_HOST` / optional `/var/run/docker.sock` symlink | Socket file permissions |
| 1Password 8 | closed | Native/Electron app | The app itself | No network port: XPC / named pipe / Unix socket | OS IPC name | OS verifies code signature of both ends + biometric prompt per terminal session |
| [Datasette Desktop](https://github.com/simonw/datasette-app) | 137 | Electron | Python `datasette` child | Free port from 8001 up | Held in memory by the shell | Per-launch bearer token → signed cookie |

Three architectural families show up:

1. **Shell owns the daemon as a child** (Ollama, syncthing-macos, Datasette Desktop, Tauri sidecars). The shell restarts it, passes it configuration via environment, and its lifecycle ends when the shell quits. Auto-start is the shell's login item.
2. **Daemon is independent of the shell** (Tailscale, Docker Desktop's backend, LM Studio's `llmster`, Jupyter, code-server). The shell and the CLI are peers, both clients of the daemon. They find it through a file or a well-known socket.
3. **Everything in one process** (cc-switch, 1Password). There is no separate daemon; the API or proxy exists only while the GUI app runs.

---

## 2. Per-product mechanisms

### 2.1 Ollama (macOS / Windows app)

**Process layout.** The desktop app is Go with a native Cocoa layer and a WKWebView ([`app/`](https://github.com/ollama/ollama/tree/main/app)). The `.app` bundle carries the CLI binary at `Ollama.app/Contents/Resources/ollama`. The app runs it as `ollama serve` in a supervisor loop ([`app/server/server.go`](https://github.com/ollama/ollama/blob/main/app/server/server.go)):

- Before the first spawn it reads a pid file. If a previous `ollama` process is still alive, it stops it gracefully and kills it after 5 s (`cleanup`, `stop`).
- The loop waits `restartDelay = 1s`, starts the child, writes the pid file and `Wait()`s. Every exit is followed by a restart until the app's context is cancelled.
- **Port conflict handling.** If the child exits with code 1, the supervisor assumes another `ollama serve` holds the port. It runs `reapServers()` once to kill those processes and retries. The `reaped` flag stops this from looping.
- App settings are turned into environment variables for the child. "Expose" sets `OLLAMA_HOST=0.0.0.0`, "browser" access sets `OLLAMA_ORIGINS=*`, and there are models dir, context length and `OLLAMA_NO_CLOUD`. The app does not write a config file. The FAQ tells users of the GUI app to use `launchctl setenv OLLAMA_HOST ...` and restart the app ([faq](https://github.com/ollama/ollama/blob/main/docs/faq.mdx)).

**Port.** Fixed `127.0.0.1:11434`, overridable only by `OLLAMA_HOST` ([`envconfig/config.go`](https://github.com/ollama/ollama/blob/main/envconfig/config.go)). Clients find the server by knowing the port. There is no discovery file.

**Server-side access control** ([`server/routes.go`](https://github.com/ollama/ollama/blob/main/server/routes.go)). The public API has **no authentication**. It has two guards instead:

- `allowedHostsMiddleware` runs only when the listener is loopback. It accepts a `Host` that is empty, `localhost`, the machine hostname, an IP that is loopback/private/unspecified, or a name ending in `.localhost`, `.local` or `.internal`. Anything else gets 403. This is the fix for **DNS rebinding** [CVE-2024-28224](https://www.nccgroup.com/research/technical-advisory-ollama-dns-rebinding-attack-cve-2024-28224/). Before 0.1.29 a web page could rebind its own domain to 127.0.0.1 and drive the whole API.
- The CORS allowlist (`AllowedOrigins`) is `OLLAMA_ORIGINS` plus `http(s)://localhost|127.0.0.1|0.0.0.0` on any port, plus `app://*`, `file://*`, `tauri://*`, `vscode-webview://*` and similar. Other desktop shells are allowed in by default. Browser extensions must be added explicitly ([faq](https://github.com/ollama/ollama/blob/main/docs/faq.mdx)).

**The app's own UI server** ([`app/cmd/app/app.go`](https://github.com/ollama/ollama/blob/main/app/cmd/app/app.go), [`app/ui/ui.go`](https://github.com/ollama/ollama/blob/main/app/ui/ui.go)) is a second HTTP server on `127.0.0.1:0` (random port; fixed `3001` only in `-dev`). Every launch generates `token := uuid.NewString()`. The webview injects `document.cookie = "token=…"` before loading the page ([`webview.go`](https://github.com/ollama/ollama/blob/main/app/cmd/app/webview.go)). The UI server rejects requests without a matching `token` cookie ("Token is required"). Requests to the model API are reverse-proxied to 11434. The result is split: the chat UI's private API is token-gated, while the public model API stays open.

**Auto-start.** `registerSelfAsLoginItem` uses **`SMAppService agentServiceWithPlistName:@"com.ollama.ollama.plist"`**, a LaunchAgent plist embedded at `Ollama.app/Contents/Library/LaunchAgents/` ([`app_darwin.m`](https://github.com/ollama/ollama/blob/main/app/cmd/app/app_darwin.m)). The plist has `RunAtLoad`, `LimitLoadToSessionType=Aqua`, `POSIXSpawnType=Interactive` and **no `KeepAlive`** ([plist](https://github.com/ollama/ollama/blob/main/app/darwin/Ollama.app/Contents/Library/LaunchAgents/com.ollama.ollama.plist)). Crash recovery is the app's own supervisor loop, not launchd. If the service status is `RequiresApproval` (the user disabled it in System Settings), the app does not re-register it. The app also removes the legacy `LSSharedFileList` login item that older versions created.

**Single instance.** `handleExistingInstance` kills other running app instances. A newer "handoff" path sends `SIGUSR1` so an old instance quits during an update. It escalates from handoff to graceful to forced stop, with deadlines. Only a newer instance winning the election blocks launch ([`app_darwin.go`](https://github.com/ollama/ollama/blob/main/app/cmd/app/app_darwin.go)).

**CLI install from the app.** On start, `installSymlink` checks whether `ollama` on `PATH` already resolves to the bundle's binary. If not, it asks for admin authorization and creates `/usr/local/bin/ollama` → `…/Resources/ollama`, creating `/usr/local/bin` if needed ([`app_darwin.m`](https://github.com/ollama/ollama/blob/main/app/cmd/app/app_darwin.m), [macOS docs](https://github.com/ollama/ollama/blob/main/docs/macos.mdx)). The app also offers "Move to Applications?" on first run.

**CLI → app (detect-or-spawn and skew).** If the CLI's heartbeat gets "connection refused", `startApp` resolves its own symlink. If the target matches `…/Ollama.app`, it runs `open -j -a Ollama.app --args --fast-startup` and polls until the server answers ([`cmd/start_darwin.go`](https://github.com/ollama/ollama/blob/main/cmd/start_darwin.go), [`cmd/cmd.go`](https://github.com/ollama/ollama/blob/main/cmd/cmd.go)). `ollama -v` prints the server version and adds `Warning: client version is X` when they differ. Individual commands fail with messages like "the ollama server must be updated to use `ollama create` with this client".

**Updates.** Hourly check against `https://ollama.com/api/update`, signed with the local Ollama key when one exists. The download is verified (bundle extracted and checked in a temp dir) and staged, and the menubar shows "Restart to update" ([`app/updater`](https://github.com/ollama/ollama/tree/main/app/updater)). The bundle's LaunchAgent plist launches a bundled `Squirrel.framework` binary with `background`, which is part of the update and relaunch path.

### 2.2 LM Studio (Electron app, `lms` CLI, `llmster` daemon)

**Two servers, two ports.** The user-facing OpenAI-compatible server defaults to port **1234**. `lms server start --port` uses "the last used port" if none is given, binds `127.0.0.1` unless `--bind 0.0.0.0`, and has CORS **off** unless `--cors`. The docs warn that both CORS and network binding should come with auth ([server start](https://lmstudio.ai/docs/cli/serve/server-start)). Settings add an opt-in "Require API token" (`Authorization` header) ([settings](https://lmstudio.ai/docs/developer/core/server/settings)).

The SDK and CLI talk to a separate internal websocket API. Its port is published in **`~/.lmstudio/.internal/http-server.json`**. If that file is missing or stale, clients probe a fixed list of five ports `[41343, 52993, 16141, 39414, 22931]` in parallel with `GET /lms-status`. The endpoint must return `{package, version}` before a port counts as found ([`apiServerPorts.ts`](https://github.com/lmstudio-ai/lmstudio-js/blob/main/packages/lms-common/src/apiServerPorts.ts), [`findOrStartLlmster.ts`](https://github.com/lmstudio-ai/lmstudio-js/blob/main/packages/lms-common-server/src/findOrStartLlmster.ts), [`localAPIServer.ts`](https://github.com/lmstudio-ai/lms/blob/main/src/localAPIServer.ts)). The discovery file is only a hint, and the status probe is the authority. An env var `LMS_API_SERVER_INFO_PATH` pins one exact instance and disables the fallback scan. This keeps development wrappers from silently attaching to a different app.

**Detect-or-spawn.** `findOrStartLlmster`:
1. probes the running daemon;
2. reads `app-install-location.json` / `llmster-install-location.json` (written by the app or daemon at install/run, containing `{path, argv, cwd}`);
3. prefers the headless `llmster` daemon; otherwise launches the GUI app with `--run-as-service` (on Linux it sets `DISPLAY=:0`; on Windows it uses `Start-Process -WindowStyle Hidden`);
4. polls for up to 60 × 1 s.

**CLI auth to the local daemon** ([`createClient.ts`](https://github.com/lmstudio-ai/lms/blob/main/src/createClient.ts)). The CLI presents `clientIdentifier: "lms-cli"` and `clientPasskey = lmsKey + lmsKey2`. `lmsKey` is injected at build time. `lmsKey2` is read from `~/.lmstudio/.internal/lms-key-2`, which the app writes. After waking the service the CLI re-reads the file "due to the possibility of a new key being generated". Dev builds get a restricted `lms-cli-dev` identity. Remote hosts get a random identifier.

**CLI install.** `lms` "ships with LM Studio" and "you need to run LM Studio at least once". The first run bootstraps it onto `PATH`; `lms bootstrap` / `npx lmstudio install-cli` repairs it ([docs](https://lmstudio.ai/docs/cli), [lms README](https://github.com/lmstudio-ai/lms)). **Headless:** `llmster` is "the core of the LM Studio desktop app, packaged to be server-native, without reliance on the GUI". It is installed by a curl script and started with `lms daemon up`. The app's "run on login" setting makes quitting minimize to the tray, and "last server state will be saved and restored on app or service launch" ([headless](https://lmstudio.ai/docs/developer/core/headless)).

### 2.3 Docker Desktop (macOS)

**Layout.** The engine runs inside a Linux VM. The host-side endpoint is a Unix socket at `~/.docker/run/docker.sock`, protected by file permissions. There is no TCP port or token. The optional setting "Allow the default Docker socket to be used" creates `/var/run/docker.sock`. Because `/var/run` is wiped on reboot, Docker installs a launchd task that re-runs `ln -s -f ~/.docker/run/docker.sock /var/run/docker.sock`. Without it, users set `DOCKER_HOST` ([permission requirements](https://docs.docker.com/desktop/setup/install/mac-permission-requirements/)).

**Privileged helper.** Up to 4.88, `com.docker.vmnetd` was a launchd daemon listening on `/var/run/com.docker.vmnetd.sock`. It existed only to bind ports <1024, cache the Registry Access Management policy, and uninstall itself. Root is needed only for `/usr/local/bin` symlinks, `/etc/hosts` entries and privileged ports. A `--user` install applies these once without a prompt, at the cost of supporting one user per machine ([same page](https://docs.docker.com/desktop/setup/install/mac-permission-requirements/)).

**CLI install from the app.** Binaries live in `Docker.app/Contents/Resources/bin`. "User" mode symlinks them into `$HOME/.docker/bin` and adds that to `PATH`; this has been the default since 4.89. "System" mode symlinks into `/usr/local/bin` and needs authorization ([settings](https://docs.docker.com/desktop/settings-and-maintenance/settings/)).

**Lifecycle.** Settings include "Start Docker Desktop when you sign in", "Open Docker Dashboard when Docker Desktop starts", and **Resource Saver**, which turns off the Linux VM when idle while the app stays resident ([settings](https://docs.docker.com/desktop/settings-and-maintenance/settings/)). `docker desktop start|stop|restart|status|update|logs|diagnose` lets the CLI drive the app ([desktop CLI](https://docs.docker.com/desktop/features/desktop-cli/)).

**Version skew.** Handled by API version negotiation. The daemon and client "don't necessarily need to be the same version". A newer client "negotiates the highest version of the API supported by both" and downgrades. `DOCKER_API_VERSION` pins a version and disables negotiation ([engine API](https://docs.docker.com/reference/api/engine/)). **Updates.** "Automatically check for updates" and "Always download updates" (background download), applied from the menu or `docker desktop update`.

### 2.4 Tailscale (macOS)

**Three variants** ([macOS variants](https://tailscale.com/kb/1065/macos-variants)):
- **App Store**: a sandboxed Network Extension running as the user, updated by the App Store.
- **Standalone**: a System Extension running as root in a sandbox, updated in-app with Sparkle. This is the recommended variant.
- **Open-source `tailscaled`**: a launchd daemon on `utun`. It can run before login and has no auto-update.

In all three, `tailscaled` is the daemon and the GUI and CLI are clients of its **LocalAPI**.

**Discovery and auth: "sameuserproof"** ([`safesocket/safesocket_darwin.go`](https://github.com/tailscale/tailscale/blob/main/safesocket/safesocket_darwin.go)). The GUI variants cannot expose a Unix socket from the sandbox. Instead the extension listens on **`127.0.0.1:0`** and generates a 10-byte random hex token once per process. It then writes a credential file into `/Library/Tailscale`, removing all earlier `sameuserproof-*` files first:
- **Standalone** (root): the symlink `ipnport` → `"<port>"` and the file `sameuserproof-<port>` containing the token. The file is mode `0640`, owned root:**admin**, so only admin-group users can read it.
- **App Store**: an empty file named `sameuserproof-<port>-<token>`. The process keeps it **open** so a CLI can find it through `lsof`.

The CLI reads port and token and sends the token as the HTTP Basic-auth password. When the CLI runs from inside `Tailscale.app`, the GUI hands the credentials over directly (`SetCredentials`) over XPC. If none of this works, the CLI falls back to the classic Unix socket.

**Browser guard** ([`ipn/localapi/localapi.go`](https://github.com/tailscale/tailscale/blob/main/ipn/localapi/localapi.go)). Every LocalAPI request with a **`Referer` or `Origin` header is rejected** with 403. `Host` must be the sentinel `local-tailscaled.sock`, or loopback when a password is required. Responses carry `Content-Security-Policy: default-src 'none'`, `X-Frame-Options: DENY` and `nosniff`. The LocalAPI is meant for non-browser clients only.

**Version skew.** Responses carry `Tailscale-Version` and `Tailscale-Cap` headers. The CLI prints `Warning: client version "X" != tailscaled server version "Y"` ([`cmd/tailscale/cli/cli.go`](https://github.com/tailscale/tailscale/blob/main/cmd/tailscale/cli/cli.go)).

**CLI install from the app.** The binary is the app itself: `Tailscale.app/Contents/MacOS/Tailscale` acts as the CLI when invoked from a terminal, and `TAILSCALE_BE_CLI=1` forces CLI mode. Standalone has Settings → "CLI integration" → "Install Now", which asks for the admin password and writes a launcher to `/usr/local/bin/tailscale`. The App Store variant documents a shell alias instead ([CLI](https://tailscale.com/kb/1080/cli)).

### 2.5 1Password 8 (desktop app + `op` CLI)

There is no network port. The CLI connects to the running desktop app over OS IPC ([app integration security](https://www.1password.dev/cli/app-integration-security/)):
- **macOS**: XPC, relayed through the "1Password Browser Helper". Both sides verify the other's **code signature**.
- **Windows**: named pipes with mutual Authenticode verification.
- **Linux**: a Unix socket. The app checks that the connecting process's group is `onepassword-cli`.

**Authorization.** Authorization is scoped to the **terminal session**: TTY plus its start time on Unix, PID plus start time on Windows. Sub-shells inherit it on macOS and Linux. Each authorization needs a biometric or system prompt that names the account and the process. It lasts 10 minutes, refreshes on use, and has a 12-hour hard limit.

The CLI is **installed separately** (Homebrew, pkg, winget). The integration is switched on in the app under Settings → Developer → "Integrate with 1Password CLI", and the app must be running and unlocked ([get started](https://www.1password.dev/cli/get-started/)).

### 2.6 Syncthing and its tray wrappers

**Server** ([`lib/api/api.go`](https://github.com/syncthing/syncthing/blob/main/lib/api/api.go), [`api_csrf.go`](https://github.com/syncthing/syncthing/blob/main/lib/api/api_csrf.go)). The GUI and REST API are served at `127.0.0.1:8384` by default ([config](https://docs.syncthing.net/users/config.html)). The middleware stack, from outside in:
- **Host check.** When the listener is localhost, `Host` must look like localhost; `insecureSkipHostcheck` turns this off.
- **CORS.** OPTIONS gets `Access-Control-Allow-Origin: *` but may only use `Content-Type, X-API-Key` headers.
- **Optional basic or session auth.**
- **CSRF manager.** Requests carrying a valid `X-API-Key` (or `Authorization: Bearer`) pass. Non-`/rest` requests get a cookie `CSRF-Token-<deviceIDprefix>`. `/rest` calls without an API key must echo that cookie in the header `X-CSRF-Token-<prefix>`. Tokens live 1 h and at most 25 are active.

So the served page authenticates through the cookie plus header pair, and external tools use the API key from `config.xml`.

**Supervision.** `syncthing` runs itself under a **monitor process**. Exit code 3 means "restart". `--no-restart` / `STNORESTART` disables restart-on-exit, but the monitor "will still run to handle crashes" ([CLI reference](https://docs.syncthing.net/users/syncthing.html)).

**syncthing-macos** ([`DaemonProcess.swift`](https://github.com/syncthing/syncthing-macos/blob/v2/syncthing/DaemonProcess.swift), [`STApplication.m`](https://github.com/syncthing/syncthing-macos/blob/v2/syncthing/STApplication.m)) bundles the binary in `Resources/syncthing/`. It launches it with `--no-browser --no-restart` and `STNOUPGRADE=true`, so the wrapper's Sparkle feed owns updates. It restarts the binary itself: immediately on exit 0 or 3, and after `RestartInterval` on any other code "to not get caught in a tight loop". It gets the URI and API key by parsing Syncthing's `config.xml` on first run and caching them in user defaults, retrying up to 3 times at 5 s if the file is not there yet.

### 2.7 Jupyter Server (token-in-URL, discovery file)

- **Token.** A random token is generated per start and printed as `http://localhost:8888/?token=…`. It is accepted in the URL query, as `Authorization: token …`, or in the login form, and a cookie is set after first use ([security](https://jupyter-server.readthedocs.io/en/latest/operators/security.html)).
- **Discovery file.** `jpserver-<pid>.json` in the Jupyter runtime dir is written with `secure_write` (owner-only). It holds `{url, hostname, port, sock, secure, base_url, token, root_dir, password, pid, version}` and is removed on shutdown. `jupyter server list` reads these files ([`serverapp.py`](https://github.com/jupyter-server/jupyter_server/blob/main/jupyter_server/serverapp.py)).
- **Browser open file.** `jpserver-<pid>-open.html` is a local redirect page that contains the tokenized URL. The launcher opens this file so the token never appears on a browser command line.
- **Port conflicts.** The requested port is tried first, then up to `port_retries = 50` others (`JUPYTER_PORT_RETRIES`). Clients must read the discovery file to know which port was used.
- **DNS rebinding.** `allow_remote_access` defaults to False when bound to loopback. Requests whose `Host` is not local get 403, and `local_hostnames` extends the list. XSRF protection (`_xsrf`) applies to cookie-authenticated requests. `allow_origin` controls CORS.

### 2.8 code-server

Binds `127.0.0.1:8080`. The first run writes `~/.config/code-server/config.yaml` with a random password. `hashed-password` (argon2) takes precedence, and logins are rate-limited to 2/min + 12/h ([FAQ](https://coder.com/docs/code-server/FAQ)). WebSocket and state-changing routes call `ensureOrigin`. A request with no `Origin` passes as non-browser. Otherwise the `Origin` host must equal the `Host` (or `X-Forwarded-Host`) or match `--trusted-origins`, which accepts `*.example.com` patterns ([`src/node/http.ts`](https://github.com/coder/code-server/blob/main/src/node/http.ts)). This is the standard defence against cross-site WebSocket hijacking.

### 2.9 Jan (Tauri 2)

The desktop app is Tauri 2 with `tauri-plugin-single-instance` (with deep-link forwarding), `tauri-plugin-updater` and a store plugin ([`Cargo.toml`](https://github.com/janhq/jan/blob/main/src-tauri/Cargo.toml)). Inference runs in-process through custom Tauri plugins (llama.cpp, MLX), not a separate daemon.

The webview's CSP explicitly allows `http://127.0.0.1:*` and `ws://localhost:*`. Font sources list both `tauri://localhost` and `http://tauri.localhost`, the two webview origins Tauri uses on macOS/Linux and Windows ([`tauri.conf.json`](https://github.com/janhq/jan/blob/main/src-tauri/tauri.conf.json)). The updater reads two endpoints: its own `apps.jan.ai/update-check` first, then GitHub `latest.json`, with a minisign public key.

The optional **Local API Server** defaults to `127.0.0.1:1337` with prefix `/v1`. It requires `Authorization: Bearer <key>` (a user-chosen string, which can be empty but that is discouraged on `0.0.0.0`), has a **Trusted Hosts** list, and has CORS on by default. It is started from a button in Settings ([docs](https://www.jan.ai/docs/desktop/api-server)).

### 2.10 AnythingLLM Desktop (Electron)

The desktop build wraps the same server as the Docker image. It listens on **`localhost:3001`**, and the port is not configurable. A maintainer described the `SERVER_PORT` env as "an artifact of how we build desktop *around* the dockerized version" ([#3144](https://github.com/Mintplex-Labs/anything-llm/issues/3144)). Settings → Security → "Discoverable on network" rebinds to `0.0.0.0:3001` after a restart ([#2472](https://github.com/Mintplex-Labs/anything-llm/issues/2472)). The developer API uses a bearer key created in Settings → Developer API ([docs](https://docs.useanything.com/features/api)). This shows the cost of reusing a server image in a desktop app: users lose control of the port and cannot run two copies side by side.

### 2.11 cc-switch (Tauri 2, CN ecosystem)

cc-switch is a Tauri 2 app with a tray (`tray-icon` feature) and plugins for single-instance, updater, deep-link, window-state and process ([`Cargo.toml`](https://github.com/farion1231/cc-switch/blob/main/src-tauri/Cargo.toml)).

- **No separate daemon.** Its local provider proxy is an axum/hyper server inside the app process. It binds `127.0.0.1:15721` by default ("a less-used high port") and fails with `BindFailed` rather than picking another port ([`proxy/types.rs`](https://github.com/farion1231/cc-switch/blob/main/src-tauri/src/proxy/types.rs), [`proxy/server.rs`](https://github.com/farion1231/cc-switch/blob/main/src-tauri/src/proxy/server.rs)).
- **Auto-start** uses the `auto-launch` crate in its **AppleScript** login-item mode. The code comments that it must be given the `.app` bundle path, because pointing at the inner executable makes the login item open a Terminal window ([`auto_launch.rs`](https://github.com/farion1231/cc-switch/blob/main/src-tauri/src/auto_launch.rs)).
- **Updates** come from the Tauri updater with a minisign key and two endpoints (own CDN, then GitHub) ([`tauri.conf.json`](https://github.com/farion1231/cc-switch/blob/main/src-tauri/tauri.conf.json)).

### 2.12 Datasette Desktop (Electron + Python backend)

This is a small project, but it is the clearest public example of an Electron shell driving a Python server ([`main.js`](https://github.com/simonw/datasette-app/blob/main/main.js)):

- **Packaging.** It bundles a standalone CPython in `Resources/python`. On first run it creates `~/.datasette-app/venv` and pip-installs pinned packages, recreating the venv if the bundled Python version changed. There is no PyInstaller freeze, so plugins can be installed at runtime.
- **Port.** `portfinder` picks the first free port from 8001.
- **Auth.** Each launch generates `apiToken = randomBytes(32)`, passed to the child as `DATASETTE_API_TOKEN`, along with a random `DATASETTE_SECRET` for cookie signing. Windows open `/-/auth-app-user` with `loadURL(..., {extraHeaders: "authorization: Bearer <token>", method: "POST"})`. The server answers with a signed actor cookie and redirects. The token never appears in a URL, and a plain browser pointed at the port gets no session.

---

## 3. Framework notes: Tauri sidecar vs Electron + Python, and freezing

- **Tauri sidecar.** `bundle.externalBin` lists binaries, each with a target-triple suffix (`my-sidecar-aarch64-apple-darwin`). They are spawned with `app.shell().sidecar("my-sidecar")`, and the frontend needs an explicit `shell:allow-execute` capability with `"sidecar": true` ([sidecar docs](https://v2.tauri.app/develop/sidecar/)). For Node, the guide recommends a `pkg`-style single executable over shipping a runtime ([Node sidecar](https://v2.tauri.app/learn/sidecar-nodejs/)).
- **Sidecar lifecycle has been a recurring bug source.** Reports include sidecars left alive after the app exits ([#1896](https://github.com/tauri-apps/tauri/issues/1896), 2021) and "not killed on app exit on Windows" while macOS kills it ([#10377](https://github.com/tauri-apps/tauri/issues/10377)). For a **PyInstaller onefile** sidecar, the bootloader forks the real app as a grandchild, so killing the child leaves the grandchild running ([#14360](https://github.com/tauri-apps/tauri/issues/14360), 2025, "kill tree for sidecar"). Products that want a daemon to *outlive* the shell avoid the sidecar API and register a launchd job instead.
- **Tauri webview origin.** Pages load from `tauri://localhost` (macOS/Linux) or `http://tauri.localhost` (Windows), so a localhost daemon must allow those origins in CORS. Ollama's default allowlist includes `tauri://*`.
- **Tauri updater.** Signatures are mandatory ("cannot be disabled"), using a minisign key via `TAURI_SIGNING_PRIVATE_KEY`. It reads a static or dynamic `latest.json` with `version/url/signature`, and on macOS replaces the whole `.app` from `app.tar.gz` ([updater](https://v2.tauri.app/plugin/updater/)). Losing the private key strands existing installs. **Autostart plugin** offers `MacosLauncher::LaunchAgent` ([autostart](https://v2.tauri.app/plugin/autostart/)). **Single instance** comes from `tauri-plugin-single-instance`; Electron's equivalent is `app.requestSingleInstanceLock()`.
- **PyInstaller on macOS.** It ad-hoc signs every collected binary by default. With `--codesign-identity` it also enables the hardened runtime, which "will not work with self-signed certificates" ([feature notes](https://pyinstaller.org/en/stable/feature-notes.html)). `--onefile --windowed` app bundles are "not recommended … they require unpacking on each run (and the unpacked content might be scanned by the OS each time)" and do not work sandboxed ([usage](https://pyinstaller.org/en/stable/usage.html)). `--target-arch universal2` builds fat binaries. Notarizing a frozen binary outside an `.app` has hit problems such as "mapped file has no cdhash" ([pyinstaller#4333](https://github.com/pyinstaller/pyinstaller/issues/4333)) and PySide6 `--onedir` notarization failures ([#8927](https://github.com/pyinstaller/pyinstaller/issues/8927)).
- **Nuitka** compiles to C and offers `--mode=standalone|onefile|app`, with `--macos-create-app-bundle` and `--macos-create-installer` (DMG) ([user manual](https://nuitka.net/user-documentation/user-manual.html)). It still produces native code that needs a real Developer ID to notarize.

---

## 4. Cross-cutting topics

### 4.1 Port choice and conflicts

| Strategy | Who | On conflict |
| --- | --- | --- |
| Fixed well-known port, env override | Ollama 11434, AnythingLLM 3001, Jan 1337, Syncthing 8384, code-server 8080, cc-switch 15721 | Ollama's app kills competing `ollama serve` once and retries. cc-switch fails with an error. AnythingLLM cannot move |
| Requested port plus N retries | Jupyter (+50) | Silently moves; clients must read the discovery file |
| Last-used port, remembered | LM Studio `lms server start` | Asks the user to pick another |
| Random port plus published file | Tailscale LocalAPI, Ollama's private UI server, LM Studio internal API | Cannot collide; discovery is required |
| Short list of fallback ports probed | LM Studio internal API (5 ports) | Any one wins; an identity probe (`/lms-status`) confirms it |
| No TCP at all | Docker (Unix socket), 1Password (XPC/pipe) | Not applicable |

Fixed ports are chosen when **third parties** must connect without reading a file. Examples are OpenAI-compatible clients pointing at `:11434/v1`, or a browser tab the user bookmarks. Random ports are chosen when every client is first-party and can read a file.

### 4.2 Discovery

The field uses one of three mechanisms:
- **A per-instance JSON file** in a user-private runtime dir: Jupyter `jpserver-<pid>.json` (url, port, token, pid, version); LM Studio `http-server.json` (port) plus `*-install-location.json` (how to spawn).
- **A fixed path in a shared dir with a filesystem-enforced reader set**: Tailscale's `sameuserproof`, where root:admin 0640 decides who can read it.
- **Nothing**: a fixed port or socket.

LM Studio treats the file as a hint and confirms identity with a status probe that returns package and version. Jupyter's file carries the pid so stale files can be detected.

### 4.3 Authenticating a webview or browser to a localhost daemon

Threats in order of how often they have been exploited: DNS rebinding (Ollama CVE-2024-28224), cross-site requests from any web page (CSRF / "simple" POSTs that skip CORS preflight), cross-site WebSocket hijacking, and other local users.

Chrome 142 (Oct 2025) added a **Local Network Access** permission prompt when a *public* origin requests a loopback or private address. Loopback-to-loopback requests are exempt ([Chrome blog](https://developer.chrome.com/blog/local-network-access)). This helps, but it is browser-specific and the user can allow it.

| Defence | Examples |
| --- | --- |
| `Host` header allowlist (anti-rebinding) | Ollama, Syncthing, Jupyter, Tailscale (sentinel host `local-tailscaled.sock`) |
| Reject anything that looks like a browser (`Origin`/`Referer` present) | Tailscale LocalAPI |
| `Origin` must equal `Host`, or be in trusted list | code-server |
| CORS allowlist incl. `tauri://`, `app://`, `file://` | Ollama |
| Per-start token, delivered by the shell as a cookie | Ollama UI (`document.cookie` injection), Datasette Desktop (bearer on first POST, then signed cookie) |
| Per-start token in URL, swapped for cookie | Jupyter, with an HTML redirect file to keep it off `argv` |
| Cookie-plus-header CSRF token | Syncthing (`X-CSRF-Token-<id>`), Jupyter (`_xsrf`) |
| Long-lived API key for non-browser clients | Syncthing `X-API-Key`, Jan, AnythingLLM, LM Studio opt-in |
| OS IPC with code-signature check, no port | 1Password, Tailscale GUI↔extension (XPC) |
| Filesystem permission on socket or credential file | Docker socket, Tailscale `sameuserproof`, Jupyter `secure_write` |

### 4.4 Auto-start and crash restart

- **macOS mechanisms.**
  - **SMAppService** (macOS 13+): an agent plist embedded in the bundle's `Contents/Library/LaunchAgents/`. It shows up in System Settings → Login Items and can be `RequiresApproval`. Used by Ollama.
  - **Legacy `LSSharedFileList` / AppleScript login items**: used by cc-switch through `auto-launch`. Ollama removes these on upgrade.
  - **A hand-written `~/Library/LaunchAgents` plist**.
  - **Root `LaunchDaemons`** for pre-login operation (open-source `tailscaled`, Docker's socket-symlink task).
- **launchd semantics** ([launchd.plist(5)](https://keith.github.io/xcode-man-pages/launchd.plist.5.html)). `KeepAlive` can be a bool or a dictionary. `SuccessfulExit=true` restarts after exit 0. `Crashed=true` restarts after a crash signal. `ThrottleInterval` defaults to **10 s** between spawns. `RunAtLoad` starts at load, and `LimitLoadToSessionType=Aqua` limits the job to GUI logins. `KeepAlive={SuccessfulExit=false}` means "restart unless it exited cleanly", so a user's explicit stop is respected and crashes are restarted.
- **Supervisor in the shell instead of launchd.** Ollama restarts on every exit after 1 s. syncthing-macos restarts immediately on 0 or 3 and after a delay on error. Syncthing's own monitor handles crashes even with `--no-restart`. The shell-supervisor model ties the daemon's life to the shell's.
- **Respect the user's off switch.** Ollama does not re-register when the service is `RequiresApproval`. LM Studio's "run on login" is a user setting. Docker's "Start when you sign in" is a checkbox.

### 4.5 Single instance and version skew

- **Single instance of the shell.** Tauri and Electron use a lock (plugin or `requestSingleInstanceLock`) and forward the second launch's argv or deep link to the first. Ollama goes further and actively terminates older instances, with handoff by `SIGUSR1` during updates.
- **Single instance of the daemon.** Usually enforced by the port bind itself. Ollama adds a pid file plus a kill of stray `ollama serve` processes. Jupyter deliberately allows many instances, each with its own file.
- **Version skew between CLI, shell and daemon.**
  - Report it: Ollama `-v` warning, Tailscale per-call warning plus `Tailscale-Version` header.
  - Negotiate it: Docker API versions.
  - Fail on the specific feature: Ollama "server must be updated to use … with this client".
  - Avoid it by shipping every piece in one bundle and pointing the CLI symlink into the bundle: Ollama, Docker, Tailscale, LM Studio. The remaining skew case is an old daemon still running after the app bundle was replaced. Ollama's update handoff and pid-file cleanup exist for exactly that case.

### 4.6 Updates

| Product | Mechanism | Verification | Apply |
| --- | --- | --- | --- |
| Ollama | Hourly poll of own endpoint, background download | Bundle extracted and verified in temp dir | "Restart to update"; Squirrel swaps the bundle; handoff kills old instances |
| Tauri apps (Jan, cc-switch) | `latest.json` on own CDN, GitHub fallback | Mandatory minisign signature | Replace `.app` from `app.tar.gz` |
| Tailscale Standalone, syncthing-macos | Sparkle appcast | Sparkle signature | In-app; syncthing-macos disables Syncthing's own upgrader (`STNOUPGRADE`) so there is one updater |
| Docker Desktop | In-app check, optional background download | Vendor-signed | Menu or `docker desktop update` |
| Tailscale App Store | App Store | Apple | App Store |

The consistent rule is **one updater per bundle**. When a wrapped daemon has its own updater (Syncthing), the wrapper turns it off.

### 4.7 Installing the CLI from the app

| Product | Target | Privilege | Idempotence |
| --- | --- | --- | --- |
| Ollama | `/usr/local/bin/ollama` → bundle binary | Admin prompt (Authorization Services) | Skips if `PATH`'s `ollama` already resolves to the bundle |
| Docker Desktop | `$HOME/.docker/bin` (default since 4.89) or `/usr/local/bin` | None / admin | Settings toggle; `PATH` edited for the user dir |
| Tailscale Standalone | Launcher at `/usr/local/bin/tailscale` | Admin password | Settings button; the app binary doubles as the CLI |
| LM Studio | Bootstrapped onto `PATH` on first run | None | `lms bootstrap` repairs |
| 1Password | Separate package | Package installer | App toggle enables IPC only |

The field is moving away from root-owned `/usr/local/bin` toward a **user-owned bin dir plus a `PATH` edit** (Docker's 4.89 default change), because the admin prompt is a common place for installs to fail.

---

## 5. Patterns and trade-offs

- **The field agrees on:**
  - a localhost-only default bind with an explicit, warned opt-in for LAN exposure (Ollama, LM Studio, Jan, AnythingLLM, Syncthing);
  - a `Host` check whenever an HTTP API is on loopback;
  - the CLI shipped inside the app bundle and linked onto `PATH`;
  - one signed updater per bundle.
- **Where they split: who owns the daemon.**
  - When the shell owns it (Ollama, syncthing-macos, Datasette Desktop, Tauri sidecars), the shell supplies config, restart and log capture. The cost is that quitting the tray quits the service, and a crash in the shell takes the daemon with it.
  - When the daemon is independent (Tailscale, LM Studio's `llmster`, Docker's backend), headless use and CLI-first flows work, but the product needs discovery, detect-or-spawn in the CLI, and version-skew handling.
  - LM Studio supports both and prefers the headless daemon when both are installed.
- **Where they split: fixed vs random port.** Fixed ports serve third-party clients and bookmarks but need conflict handling. Ollama kills the competitor, cc-switch refuses, AnythingLLM breaks. Random ports need a discovery file and cannot serve external clients without one.
- **Where they split: auth on the public API.** Inference servers (Ollama, LM Studio by default) leave the model API unauthenticated and rely on loopback plus a Host check. Anything that controls the machine (Tailscale, 1Password, Syncthing, Jupyter, code-server) requires a secret or OS identity. Ollama runs both models in one product: open model API, token-gated app UI.
- **Webview auth.** When the shell and daemon are separate processes, the shell must deliver a secret to the page. Three ways appear: inject it as a cookie before load (Ollama), send it in a header on the first navigation and swap it for a cookie (Datasette Desktop), or put it in the URL and swap it for a cookie (Jupyter). Putting the secret in the served HTML works only if the Host and Origin guards stop other origins from reading that HTML.

## 6. Worth borrowing / worth avoiding

**Worth borrowing**
- **Tailscale's "reject any request that carries `Origin` or `Referer`"** for endpoints that only non-browser clients (CLI, shim) should call. It is a one-line, zero-configuration CSRF and rebinding barrier.
- **LM Studio's discovery-file-as-hint plus identity probe.** Read the port from a file, then confirm with an endpoint that returns product name and version before trusting it. Keep an env override that makes discovery strict for development instances.
- **Jupyter's discovery file content** (url, port, pid, version, owner-only perms, removed on exit). Keeping the version in the file lets a CLI detect skew before connecting.
- **Ollama's CLI-side detect-or-spawn.** If the connection is refused and the CLI is a symlink into the app bundle, launch the app hidden (`open -j -a <App> --args …`), then poll. The CLI never needs to know how to start the daemon itself.
- **Ollama's idempotent CLI symlink** (skip if `PATH` already resolves to the bundle) and **Docker's user-owned bin dir** instead of an admin prompt.
- **`SMAppService` with a bundle-embedded plist**, honouring `RequiresApproval` as the user's decision, and removing legacy login items on upgrade.
- **Syncthing's graded restart policy**: an immediate restart for "requested restart" exit codes and a back-off for errors. Also its rule of disabling the wrapped daemon's own updater so only one updater exists.
- **Datasette Desktop's header-to-cookie handshake.** The shell sends a per-launch bearer on the first navigation and the server answers with a signed cookie. The token never appears in a URL, the page source, or `argv`.

**Worth avoiding**
- **An unauthenticated localhost API without a Host check.** Ollama's CVE-2024-28224 shows DNS rebinding turns "loopback only" into "remote".
- **CORS `*` as a convenience toggle** (Ollama's "browser" setting sets `OLLAMA_ORIGINS=*`) on anything state-changing.
- **Reusing a server image unchanged as the desktop backend** (AnythingLLM): the port becomes unconfigurable and users cannot run two instances or resolve conflicts.
- **PyInstaller `--onefile` for a long-running daemon inside an `.app`.** It unpacks on every start, may be re-scanned by the OS, and the bootloader parent/child split breaks kill-on-exit (tauri#14360). Prefer onedir inside the bundle.
- **Relying on a framework's sidecar kill-on-exit for cleanup.** Behaviour has differed between platforms. Use an explicit pid file plus a stop step, as Ollama does.
- **Two updaters for one product** (the wrapper's plus the wrapped daemon's).
- **Pointing a login item at the inner executable instead of the `.app`** (cc-switch's documented Terminal-window pitfall).

---

## Sources

Repository files are cited inline at their default branch, checked 2026-09-24. Docs: [Ollama FAQ](https://github.com/ollama/ollama/blob/main/docs/faq.mdx), [Ollama macOS](https://github.com/ollama/ollama/blob/main/docs/macos.mdx), [NCC Group CVE-2024-28224](https://www.nccgroup.com/research/technical-advisory-ollama-dns-rebinding-attack-cve-2024-28224/), [LM Studio headless](https://lmstudio.ai/docs/developer/core/headless), [LM Studio server start](https://lmstudio.ai/docs/cli/serve/server-start), [Docker Desktop permissions](https://docs.docker.com/desktop/setup/install/mac-permission-requirements/), [Docker Desktop settings](https://docs.docker.com/desktop/settings-and-maintenance/settings/), [Docker engine API versioning](https://docs.docker.com/reference/api/engine/), [Tailscale macOS variants](https://tailscale.com/kb/1065/macos-variants), [Tailscale CLI](https://tailscale.com/kb/1080/cli), [1Password app integration security](https://www.1password.dev/cli/app-integration-security/), [Syncthing CLI](https://docs.syncthing.net/users/syncthing.html), [Syncthing config](https://docs.syncthing.net/users/config.html), [Jupyter Server security](https://jupyter-server.readthedocs.io/en/latest/operators/security.html), [code-server FAQ](https://coder.com/docs/code-server/FAQ), [Jan API server](https://www.jan.ai/docs/desktop/api-server), [Tauri sidecar](https://v2.tauri.app/develop/sidecar/), [Tauri updater](https://v2.tauri.app/plugin/updater/), [Tauri autostart](https://v2.tauri.app/plugin/autostart/), [PyInstaller feature notes](https://pyinstaller.org/en/stable/feature-notes.html), [PyInstaller usage](https://pyinstaller.org/en/stable/usage.html), [Nuitka manual](https://nuitka.net/user-documentation/user-manual.html), [launchd.plist(5)](https://keith.github.io/xcode-man-pages/launchd.plist.5.html), [Chrome Local Network Access](https://developer.chrome.com/blog/local-network-access).
