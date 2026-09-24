# Provider switching: how other products do it

**Feature**: switching which model provider, endpoint and key a coding agent (Claude Code, Codex) uses, and switching back to the agent's own login. · **Coffer spec**: [provider-switching](../../openspec/specs/provider-switching/spec.md) · **Related ADRs**: [provider connections projected into agent config](../decisions/provider-connections-projected-into-agent-config.md), [provider keys never land in native config](../decisions/provider-keys-never-land-in-native-config.md), [model catalogue read from the agent](../decisions/model-catalogue-read-from-the-agent.md), [internal engine settings](../decisions/internal-engine-settings.md)

**Researched**: 2026-09 · **Method**: web research, primary sources (official docs, repository source at HEAD, release notes). Star counts are from the GitHub API, as of 2026-09-24.

---

## 1. The field at a glance

Everything in this space is built on a small set of knobs the agents themselves
expose. The tools differ in which knob they turn, where they keep the key, and
whether they put a process in the request path.

| Product | ~Stars | Kind | Knob it turns | Key lives in |
| --- | --- | --- | --- | --- |
| [cc-switch](https://github.com/farion1231/cc-switch) | 136k | Tauri desktop app, CN-first | Rewrites the agent's live config file per switch; optional local proxy "takeover" | Its own SQLite DB, then copied into the agent's config |
| [LiteLLM](https://github.com/BerriAI/litellm) | 59.5k | Self-hosted gateway | Agent points once at the gateway; switching happens server-side | Gateway config / DB; client holds a virtual key |
| [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) | 53.1k | Local proxy, CN-first | Exposes subscription OAuth logins as API endpoints | Its own auth directory |
| [claude-code-router](https://github.com/musistudio/claude-code-router) (CCR) | 37.4k | Local gateway + Electron app, CN-first | Agent points at `127.0.0.1:3456`; routing and fallback in the gateway | Its own SQLite DB; the agent gets a local client credential only |
| [claude-relay-service](https://github.com/Wei-Shaw/claude-relay-service) (CRS) | 12.6k | Self-hosted relay, CN | Pools subscription accounts server-side; clients get `cr_` keys | Server |
| [zcf](https://github.com/UfoMiao/zcf) | 6.1k | npx CLI, CN | Edits `env` keys in `~/.claude/settings.json` and Codex `config.toml` | Its own TOML file, then copied into the agent's config |
| [ccs](https://github.com/kaitranntt/ccs) | 2.9k | CLI launcher | Launches `claude --settings <profile file>` with a per-account `CLAUDE_CONFIG_DIR`; never edits `~/.claude/settings.json` | Per-profile settings files and `~/.ccs/cliproxy/auth/` |
| Claude Code (native) | — | Agent | `env` block, `apiKeyHelper`, `CLAUDE_CODE_USE_*`, `CLAUDE_CONFIG_DIR` | Keychain / `.credentials.json` for its own login; wherever the user puts the rest |
| Codex (native) | — | Agent | `model_provider` + `[model_providers.<id>]`, `--profile` layers | `auth.json` or OS keyring for its own login; `env_key` variables for custom providers |

Two families emerge: **config writers** (cc-switch, zcf, ccs, and CCR's
"system default" mode) that change what the agent reads at startup, and
**gateways** (LiteLLM, CCR, CLIProxyAPI, CRS, cc-switch's proxy mode) that let
the agent point at one stable local or remote URL and switch behind it. The
largest products do both.

---

## 2. What the agents themselves offer

Every switcher is ultimately constrained by these mechanisms, so they come first.

### 2.1 Claude Code

**Endpoint and credential variables.** Claude Code reads `ANTHROPIC_BASE_URL`
to choose the endpoint, and one of several credential sources. The documented
precedence is
([Authentication](https://code.claude.com/docs/en/authentication), checked 2026-09-24):

1. Cloud provider credentials when `CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_VERTEX` or `CLAUDE_CODE_USE_FOUNDRY` is set.
2. `ANTHROPIC_AUTH_TOKEN`, sent as `Authorization: Bearer` — the one to use for gateways.
3. `ANTHROPIC_API_KEY`, sent as `X-Api-Key`. In interactive mode the user is prompted once to approve the key and the choice is remembered.
4. `apiKeyHelper` script output.
5. `CLAUDE_CODE_OAUTH_TOKEN` (a long-lived token from `claude setup-token`).
6. Anthropic profiles / Workload Identity Federation credentials.
7. The subscription OAuth login from `/login`.

The consequence every switcher relies on: **the subscription login is never
deleted by switching — it is only outranked.** Removing the higher-ranked
variables is enough to fall back to `/login`. Setting only `ANTHROPIC_BASE_URL`
without a credential variable does not replace the subscription: requests go to
the new URL but still carry the claude.ai login
([LLM gateways](https://code.claude.com/docs/en/llm-gateway)).

**Where these live.** Any of them can go in the `env` block of a settings file
(`~/.claude/settings.json`, project or managed settings). A value in `env`
overwrites the same exported shell variable, and setting it to `""` cancels a
shell export ([settings reference, `env`](https://code.claude.com/docs/en/settings-reference)).
The docs warn that `env` values are plain text in the file and reach every
subprocess, and point at `apiKeyHelper` for API credentials instead.

**Running sessions pick up changes.** From user, `--settings` and managed
settings, `env` values apply "at startup, and again in the running session when
a saved change alters the merged `env`"; project/local values apply after
workspace trust ([settings reference, "When Claude Code applies `env` values"](https://code.claude.com/docs/en/settings-reference)).
This is why cc-switch can advertise that a Claude switch "takes effect
immediately" while a Codex switch needs a restart.

**`apiKeyHelper`.** A shell command whose stdout is the credential, sent as both
`X-Api-Key` and `Authorization: Bearer`. Claude Code caches the value and re-runs
the helper after the cache lifetime (5 minutes default, `CLAUDE_CODE_API_KEY_HELPER_TTL_MS`),
on a `401`/`403`, and before a request when the cached value is an expired JWT.
Helpers from project or local settings do not run until the workspace is
trusted. Since v2.1.227, any extra output (a banner, a log line) makes the helper
fail ([settings reference, `apiKeyHelper`](https://code.claude.com/docs/en/settings-reference);
[connect to a gateway](https://code.claude.com/docs/en/llm-gateway-connect)).
The helper is the officially sanctioned way to keep a key out of `settings.json`.

**Login storage.** macOS Keychain, falling back to `~/.claude/.credentials.json`
(mode `0600`) when the Keychain is locked; `.credentials.json` on Linux/Windows.
`CLAUDE_CONFIG_DIR` relocates the whole config directory *and* keys the Keychain
entry to that directory, so two config dirs hold two independent logins
([Authentication](https://code.claude.com/docs/en/authentication)). This is the
mechanism ccs and CCR use for isolated side-by-side instances.

**Other API formats.** A gateway may instead speak Bedrock InvokeModel
(`ANTHROPIC_BEDROCK_BASE_URL` + `CLAUDE_CODE_USE_BEDROCK=1`) or Vertex rawPredict
(`ANTHROPIC_VERTEX_BASE_URL` + `CLAUDE_CODE_USE_VERTEX=1`). For the Anthropic
Messages format the gateway must forward `anthropic-beta` and `anthropic-version`
unchanged ([gateway compatibility guide](https://code.claude.com/docs/en/llm-gateway-protocol)).

**Model names.** `ANTHROPIC_MODEL` sets the model; `ANTHROPIC_DEFAULT_OPUS_MODEL`,
`..._SONNET_MODEL`, `..._HAIKU_MODEL` and `..._FABLE_MODEL` control what each
alias resolves to; `modelOverrides`, custom model options, `availableModels` and
`modelPicker` shape the picker ([model configuration](https://code.claude.com/docs/en/model-config)).
The third-party presets in cc-switch, zcf and CCR set the tier variables to the
provider's model id, because otherwise background tasks and aliases still ask
for Claude model names the provider does not serve. For unrecognised model ids
Claude Code applies a default context window; `CLAUDE_CODE_AUTO_COMPACT_WINDOW`
and the `..._SUPPORTED_CAPABILITIES` variables exist to correct that
([connect to a gateway, troubleshooting](https://code.claude.com/docs/en/llm-gateway-connect)).

**Model discovery.** With `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1` and an
Anthropic-format `ANTHROPIC_BASE_URL` that is not `api.anthropic.com`, Claude Code
calls `GET /v1/models?limit=1000` at startup (3 s timeout, any redirect treated
as failure "so the credential can't leak to a redirect target"), reads
`id`/`display_name`/`description`, and **keeps only ids containing `claude` or
`anthropic`** (case-insensitive). Discovery is off by default "so that gateways
backed by a shared API key don't surface every model the key can access to every
user" ([gateway compatibility guide, model discovery](https://code.claude.com/docs/en/llm-gateway-protocol)).
LiteLLM's docs accordingly tell users to give non-Claude models names such as
`kimi-k3-claude-compatible` ([LiteLLM tutorial](https://docs.litellm.ai/docs/tutorials/claude_non_anthropic_models)).

**Side effects of leaving the subscription.** While `ANTHROPIC_API_KEY`,
`ANTHROPIC_AUTH_TOKEN` or `apiKeyHelper` is active, Remote Control and voice
dictation are unavailable, and Remote Control is also disabled while
`ANTHROPIC_BASE_URL` points at a non-Anthropic host. Managed `forceLoginMethod`
/ `forceLoginOrgUUID` block env credentials at startup
([connect to a gateway](https://code.claude.com/docs/en/llm-gateway-connect)).

### 2.2 Codex

**Provider table.** Codex selects a provider with top-level `model_provider` and
defines custom ones as `[model_providers.<id>]`. Source at HEAD
([`model-provider-info/src/lib.rs`](https://github.com/openai/codex/blob/main/codex-rs/model-provider-info/src/lib.rs))
lists the fields: `name`, `base_url`, `model_catalog_url`, `env_key`,
`env_key_instructions`, `experimental_bearer_token` ("discouraged in favor of
`env_key` for security reasons"), `auth` (a command-backed bearer token with
`command`, `args`, `timeout_ms`, `refresh_interval_ms`), `gateway_oauth`, `aws`
(SigV4 with a credential-export and an auth-refresh command), `wire_api`,
`query_params`, `http_headers`, `env_http_headers`, retry/timeout knobs, and
`requires_openai_auth`.

- `wire_api` now accepts only `"responses"`; `"chat"` is rejected with a
  "no longer supported" error ([same file](https://github.com/openai/codex/blob/main/codex-rs/model-provider-info/src/lib.rs)).
  Any provider that only speaks Chat Completions needs a translating proxy in
  front — which is what cc-switch's and CCR's Codex bridges do.
- `requires_openai_auth = true` means the "user is presented with login screen on
  first run, and login preference and token/key are stored in auth.json"; when
  false (the default) the key comes from the `env_key` variable (doc comment in
  the same file).
- Reserved ids `openai`, `ollama`, `lmstudio` cannot be overridden; the built-in
  OpenAI provider is redirected with `openai_base_url` instead
  ([advanced config](https://learn.chatgpt.com/docs/config-file/config-advanced)).

**Profiles.** Current Codex layers `${CODEX_HOME}/<name>.config.toml` over
`config.toml` when started with `--profile <name>`. The legacy
`profile = "<name>"` key now fails with "legacy `profile = ...` config is no
longer supported; use `--profile ...` with `....config.toml` instead"
([`core/src/config/mod.rs`](https://github.com/openai/codex/blob/main/codex-rs/core/src/config/mod.rs);
layer order documented in [`config/src/loader/mod.rs`](https://github.com/openai/codex/blob/main/codex-rs/config/src/loader/mod.rs)).
Older guides that describe `[profiles.<name>]` tables inside one file are stale.

**Login storage.** `cli_auth_credentials_store` = `file` (`~/.codex/auth.json`,
plaintext), `keyring`, `auto`, or `ephemeral`. API keys are logged in with
`printenv OPENAI_API_KEY | codex login --with-api-key`
([Codex auth](https://learn.chatgpt.com/docs/auth)). A ChatGPT login and an API
key share `auth.json`, so a switcher that writes an API key there overwrites the
ChatGPT tokens — the central hazard cc-switch engineers around (§3.1).

**Running sessions do not follow.** Config changes "generally apply on next
invocation; running sessions retain prior settings"
([advanced config](https://learn.chatgpt.com/docs/config-file/config-advanced)).
The app-server binds a "startup provider"; if the provider configuration changes
underneath it, `model/list` returns JSON-RPC `-32600` asking the client to
restart Codex ([app-server README](https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md)).

**Model list.** The app-server's `model/list` returns the catalog for the startup
provider; `model_catalog_url` on a provider points discovery at a Codex-native
catalog, and top-level `model_catalog_json` "replaces the bundled catalog for the
current process" ([`core/src/config/mod.rs`](https://github.com/openai/codex/blob/main/codex-rs/core/src/config/mod.rs)).
cc-switch generates such a catalog file per provider (§3.1).

---

## 3. Config writers

### 3.1 cc-switch (farion1231/cc-switch) — 136k stars, v3.20.4 (2026-09-22)

A Tauri (Rust + React) desktop app that manages providers for Claude Code,
Claude Desktop, Codex, Gemini CLI, OpenCode, OpenClaw, Hermes, Grok Build and
others, plus MCP servers, prompts, skills, sessions, usage and a local proxy
([README](https://github.com/farion1231/cc-switch)). It is by far the most
adopted tool in this space and the one whose source repays reading.

**Data model.** `~/.cc-switch/cc-switch.db` is the single source of truth
(SQLite since v3.7.0; tables include `providers`, `provider_endpoints`,
`mcp_servers`, `prompts`, `skills`, `proxy_config`, `proxy_request_logs`,
`provider_health`, `model_pricing`). A separate device-level
`~/.cc-switch/settings.json` holds per-machine state such as the current
provider per app and config-dir overrides, and is not synced
([user manual 5.1](https://github.com/farion1231/cc-switch/blob/main/docs/user-manual/en/5-faq/5.1-config-files.md)).
Each provider row stores a `settings_config` that *is* the agent's config in
native shape: for Claude, a full `settings.json` object whose `env` carries
`ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN` (or `ANTHROPIC_API_KEY`, chosen per
preset) and the `ANTHROPIC_MODEL` / `ANTHROPIC_DEFAULT_*_MODEL` values; for
Codex, an `auth` object plus a `config` TOML string
([`claudeProviderPresets.ts`](https://github.com/farion1231/cc-switch/blob/main/src/config/claudeProviderPresets.ts),
[`codexTemplates.ts`](https://github.com/farion1231/cc-switch/blob/main/src/config/codexTemplates.ts)).
The Cargo manifest carries no keyring or encryption crate: keys sit in the DB
row in plaintext.

**Two app modes.** "Exclusive" apps (Claude, Codex, Gemini) have exactly one
current provider and the switch replaces the live file. "Additive" apps
(OpenCode, OpenClaw, Hermes) keep every provider in the same file and a switch
only changes which one is selected
([`live.rs`](https://github.com/farion1231/cc-switch/blob/main/src-tauri/src/services/provider/live.rs)).

**The switch transaction** (`ProviderService::switch` in
[`services/provider/mod.rs`](https://github.com/farion1231/cc-switch/blob/main/src-tauri/src/services/provider/mod.rs)):

1. Take a per-app switch lock (shared with proxy takeover toggles).
2. If the proxy owns the live file, *hot-switch* the proxy's target and return
   without touching the file (see "Proxy takeover" below).
3. **Backfill**: read the live file and write it back into the *outgoing*
   provider's DB row, so manual edits made in the agent's file while that
   provider was active are not lost.
4. Before backfilling, re-extract the shareable part of the live file into the
   per-app **common config snippet** (the extractor strips auth, model,
   endpoint, `model_providers`, `mcp_servers` and injected keys). This carries
   plugins, hooks, permissions and preferences the user added in the agent
   itself across to the next provider; re-extracting "whole and replace"
   rather than "merge additions" means deletions also propagate.
5. For Codex, **preflight** the target's live projection through the same write
   path without writing, so a refusal cannot leave `current` pointing at a
   provider whose file was never written (otherwise the next backfill would copy
   the old live config into the wrong row).
6. Set the current provider in device settings and the DB.
7. Write the live file: the target's `settings_config` deep-merged with the
   common snippet, with internal-only fields stripped. JSON is written with keys
   sorted, via temp-file-then-rename; credential files are written `0600`
   ([`config.rs`](https://github.com/farion1231/cc-switch/blob/main/src-tauri/src/config.rs)).
8. Re-sync MCP servers into the agent's config.

Note what this implies about ownership: in exclusive mode **the whole
`settings.json` belongs to the current provider row** (plus the shared snippet).
Unrelated keys survive only because backfill and the snippet round-trip them.

**Restoring the original login.** The "Claude Official" preset is simply
`settings_config: { env: {} }` with `category: "official"`. Switching to it
writes a `settings.json` with no endpoint or credential variables, so Claude
Code falls back to the Keychain login, which cc-switch never touched. For Codex
the story is harder because the ChatGPT login and API keys share `auth.json`:

- A third-party switch writes `config.toml` and by default deletes `auth.json`;
  a device setting `preserve_codex_official_auth_on_switch` (default off) keeps
  it instead.
- After switching to an official card, a stale third-party key left in
  `auth.json` is removed — but only after a successful backfill, because "the DB
  copy made above is what keeps that key recoverable".
- Since v3.20.0 an "Auth Center" holds several ChatGPT OAuth sign-ins; a card
  bound to one writes that account's full refreshable token bundle into
  `auth.json`, and before each write adopts any refresh token the Codex CLI has
  rotated on disk, "so re-switching never overwrites a newer login with a stale
  one". Auth, config, catalog and a marker file form one logical commit with a
  four-file snapshot restored on failure
  ([CHANGELOG 3.20.0](https://github.com/farion1231/cc-switch/blob/main/CHANGELOG.md);
  `switch_normal` in `mod.rs`).

**Codex specifics.** Every third-party provider is written under one fixed
`model_provider` id, `custom`, and a migration re-buckets older third-party
history, so Codex's per-provider session history stays in one bucket across
switches ([`codex_config.rs`](https://github.com/farion1231/cc-switch/blob/main/src-tauri/src/codex_config.rs),
[`codex_history_migration.rs`](https://github.com/farion1231/cc-switch/blob/main/src-tauri/src/codex_history_migration.rs)).
When the official Codex provider is routed through the proxy it uses a
dedicated id, `cc-switch-official`, as an ownership marker that "can be detected
and cleaned up without mistaking a user's own local provider for takeover". It
also writes a generated `cc-switch-model-catalog.json` and points
`model_catalog_json` at it, to declare context windows and suppress Codex's
freeform `apply_patch` tool for gateways that reject custom tools.

**Model lists.** A backend fetch of `GET {base}/v1/models` (then `/models` and
variants with known compatibility sub-paths stripped), 15 s timeout, parsing
either OpenAI-style `data[].id` or Codex-catalog `models[].slug`; a preset can
override the URL with `modelsUrl`
([`model_fetch.rs`](https://github.com/farion1231/cc-switch/blob/main/src-tauri/src/services/model_fetch.rs)).
Presets also hard-code model ids (on the order of ninety Claude and ninety Codex
presets at HEAD).

**Proxy takeover.** An optional local proxy (default `127.0.0.1:15721`). Enabling
takeover for an app saves the original live config to a `live_backup` DB row and
rewrites the live file to point at the proxy with the placeholder token
`PROXY_MANAGED`; stopping the proxy restores the original
([user manual 4.1](https://github.com/farion1231/cc-switch/blob/main/docs/user-manual/en/4-proxy/4.1-service.md);
[`services/proxy.rs`](https://github.com/farion1231/cc-switch/blob/main/src-tauri/src/services/proxy.rs)).
While taken over, switching is a proxy-side hot switch — it applies to running
Codex sessions too, which a file switch cannot. The proxy adds per-app failover
queues with a circuit breaker (healthy / degraded at 1–2 consecutive failures /
unhealthy at 3+), request logging and usage/cost tracking, and converts
Anthropic Messages to OpenAI Chat Completions or Responses for providers that
speak those ([user manual 4.3](https://github.com/farion1231/cc-switch/blob/main/docs/user-manual/en/4-proxy/4.3-failover.md)).
Switching to an official provider is refused while takeover is active, because
"using proxy with official APIs may cause account bans". Ownership is decided
from corroborating evidence (a backup row *and* a placeholder in the live file),
not a flag alone, because "stale rows survive crashes and failed restores".

**Conflicts.** A startup scan detects `ANTHROPIC_*`, `OPENAI_API_KEY`,
`GEMINI_API_KEY` in shell rc files and (on Windows) the registry, shows a
banner, and can remove them after writing a JSON backup to
`~/.cc-switch/env-backups/` ([user manual 5.4](https://github.com/farion1231/cc-switch/blob/main/docs/user-manual/en/5-faq/5.4-env-conflict.md)).
Manual edits to the agent's file are recovered by backfill (above); the manual
tells users not to edit `cc-switch.db` directly.

**Backups and sync.** Automatic DB backups before each import, keeping the
latest 10 (configurable); export/import of providers, MCP, prompts and settings;
WebDAV and S3 sync of the DB, excluding usage logs and device settings
([user manual 5.1](https://github.com/farion1231/cc-switch/blob/main/docs/user-manual/en/5-faq/5.1-config-files.md)).

**MCP and prompts.** MCP servers are DB rows with a per-app enabled flag,
written into `~/.claude.json` `mcpServers`, Codex `config.toml` `[mcp_servers]`
and each other app's native table; nothing is written for an app that is not
installed ([user manual 3.1](https://github.com/farion1231/cc-switch/blob/main/docs/user-manual/en/3-extensions/3.1-mcp.md)).
Prompt presets are written to `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`,
`~/.gemini/GEMINI.md`; one preset is active per app, and the same backfill idea
applies — a hand-edited file is saved into the current preset before another is
activated ([user manual 3.2](https://github.com/farion1231/cc-switch/blob/main/docs/user-manual/en/3-extensions/3.2-prompts.md)).
A CLI sibling, [cc-switch-cli](https://github.com/SaladDay/cc-switch-cli)
(5.2k), reimplements the same model for terminals.

**Activation.** Claude and Gemini take effect immediately (Claude reloads `env`;
Gemini re-reads `.env` per request); Codex "requires a terminal restart"
([user manual 2.2](https://github.com/farion1231/cc-switch/blob/main/docs/user-manual/en/2-providers/2.2-switch.md)).

### 3.2 zcf (UfoMiao/zcf) — 6.1k stars

An `npx zcf` setup wizard for Claude Code and Codex (workflows, MCP, API config,
CCR) with a `zcf config-switch` (`zcf cs`) command
([docs](https://zcf.ufomiao.com/en/cli/config-switch.html)).

- **Profiles** live in `~/.ufomiao/zcf/config.toml` (migrated from an older
  `claude-code-configs.json`), each with `authType` (`api_key`, `auth_token`,
  `ccr_proxy`), `apiKey`, `baseUrl` and optional primary/Haiku/Sonnet/Opus model
  ids ([`claude-code-config-manager.ts`](https://github.com/UfoMiao/zcf/blob/main/src/utils/claude-code-config-manager.ts)).
- **Applying a profile** is a targeted edit of `settings.json`'s `env`: clear
  the model variables, set `ANTHROPIC_API_KEY` *or* `ANTHROPIC_AUTH_TOKEN` and
  delete the other, set or delete `ANTHROPIC_BASE_URL`, set the model variables.
  Other keys are left alone — the opposite of cc-switch's whole-file ownership.
- **Official login** is a null profile that calls `switchToOfficialLogin()`,
  removing the overrides.
- **Undocumented side writes**: it sets `hasCompletedOnboarding` in
  `~/.claude.json`, can pre-approve a key by adding its first 20 characters to
  `customApiKeyResponses.approved` there, and writes `primaryApiKey: "zcf"` into
  `~/.claude/config.json` "to prevent redirecting to official login page"
  ([`claude-config.ts`](https://github.com/UfoMiao/zcf/blob/main/src/utils/claude-config.ts)).
  These depend on Claude Code internals that are not a documented contract.
- **Backups**: timestamped copies under `~/.claude/backup/`, `~/.codex/backup/`,
  `~/.ufomiao/zcf/backup/` ([docs](https://zcf.ufomiao.com/en/features/multi-config.html)).

### 3.3 ccs (kaitranntt/ccs) — 2.9k stars

A launcher that avoids editing the agent's user config at all
([architecture reference](https://docs.ccs.kaitran.ca/reference/architecture)):

- Settings-based profiles are files such as `~/.ccs/glm.settings.json`; the
  launch is `claude --settings <path> [args]`. `~/.claude/settings.json` is
  "never modified".
- Account profiles get their own `CLAUDE_CONFIG_DIR` under
  `~/.ccs/instances/<profile>/`, which (per §2.1) isolates the Keychain entry and
  `.credentials.json`, so several subscriptions can run side by side.
- OAuth providers (Codex, Gemini, Grok, Kiro, …) go through an embedded
  CLIProxyAPI whose tokens live in `~/.ccs/cliproxy/auth/`; sessions sharing the
  proxy are reference-counted in `~/.ccs/cliproxy/sessions.json`.
- An OpenAI-compatible bridge (`ccs proxy start`, `eval "$(ccs proxy activate)"`)
  whose SSE transformation was "directly informed by CCR's transformer
  architecture" ([README](https://github.com/kaitranntt/ccs)).

Because the switch is per launch, concurrent sessions on different providers
never conflict, and there is nothing to restore.

---

## 4. Gateways

### 4.1 claude-code-router (musistudio) — 37.4k stars, v3.1.x

**v2 (the widely copied design).** A local server on `127.0.0.1:3456` configured
by `~/.claude-code-router/config.json`: a `Providers` array (name, base URL, key,
models, `transformer`) and a `Router` object mapping *scenarios* to
`provider,model` — `default`, `background`, `think`, `longContext` (with
`longContextThreshold`, e.g. 60000 tokens), `webSearch`, `image`. Transformers
adapt request/response payloads per provider or per model (`openrouter`,
`deepseek`, `gemini`, `tooluse`, `maxtoken` with options, custom plugins). Keys
could be `$VAR` / `${VAR}` interpolated from the environment. Claude Code was
launched with `ccr code`, or the shell was pointed at the router with
`eval "$(ccr activate)"`, which exports `ANTHROPIC_AUTH_TOKEN`,
`ANTHROPIC_BASE_URL=http://127.0.0.1:3456`, `NO_PROXY`, `DISABLE_TELEMETRY` and
`API_TIMEOUT_MS`. In-session switching used `/model provider,model`. Config
changes required `ccr restart`
([v2.0.0 README](https://github.com/musistudio/claude-code-router/blob/v2.0.0/README.md)).

**v3 (2026-06 onward).** Now an Electron app plus a `ccr ui` CLI, "one local
control plane for every AI agent" covering Claude Code, Codex, OpenCode, Grok
CLI, Kimi CLI and others ([README](https://github.com/musistudio/claude-code-router)).
Configuration moved to `~/.claude-code-router/config.sqlite`; the old
`config.json` is read once as a migration source
([configuration file](https://github.com/musistudio/claude-code-router/blob/main/docs/src/content/docs/en/configuration/configuration-file.md)).

- **Agent profiles** have an *effect scope*: **Only opened from CCR** (a
  generated `settings.json` under a CCR-managed directory, launched via
  `ccr "<profile>"` with `CLAUDE_CONFIG_DIR` pointing at it) or **System default**
  (edits the user's `~/.claude/settings.json`; only one per agent). The docs
  recommend the first "to avoid changing the system default agent"
  ([agent config](https://github.com/musistudio/claude-code-router/blob/main/docs/src/content/docs/en/configuration/profiles.md)).
- **What it writes for Claude Code**
  ([`profiles/service.ts`](https://github.com/musistudio/claude-code-router/blob/main/packages/core/src/profiles/service.ts)):
  `ANTHROPIC_BASE_URL` (and two alias variables) to the gateway, `NO_PROXY`,
  and the model tier variables; it *removes* `ANTHROPIC_AUTH_TOKEN`,
  `ANTHROPIC_API_KEY`, `CLAUDE_CODE_USE_*` and federation variables, then
  authenticates Claude Code to the gateway either with a generated
  `apiKeyHelper` script or with Claude Code's Workload Identity Federation
  variables pointing at a local token file (rule id `ccr-local`). It tracks which
  settings paths and env keys it manages and writes only when those changed,
  copying the previous file to a `.ccr-backup-` sibling first.
- **Model list** comes from Claude Code's own gateway discovery against CCR;
  CCR invalidates Claude Code's cached discovery when a profile's model set
  changes. Provider models are discovered from the upstream `/models`, with
  manual "custom models" for providers without that endpoint
  ([providers](https://github.com/musistudio/claude-code-router/blob/main/docs/src/content/docs/en/configuration/providers.md)).
- **Routing**: built-in Claude Code and Codex routes; ordered custom rules
  matching request headers/body with rewrites; Node.js script rules; subagent
  routing by injecting a `<CCR-SUBAGENT-MODEL>provider/model</CCR-SUBAGENT-MODEL>`
  tag into the Agent/Task tool descriptions and stripping it on the way back; a
  Codex bridge that rewrites the freeform `apply_patch` tool into a function tool
  for non-GPT models ([routing](https://github.com/musistudio/claude-code-router/blob/main/docs/src/content/docs/en/configuration/routing.md)).
- **Failure handling**: per-rule or global *Retry* or ordered *Fallback targets*
  (fallback also triggers on `4xx`, since auth or model-not-found errors may be
  target-specific), honouring `Retry-After`, else exponential backoff 1–30 s;
  `x-ccr-fallback-*` response headers expose what happened. Upstream credential
  pools rotate keys per provider.

Because the agent always talks to the same URL, provider and model changes take
effect for running sessions on the next request.

### 4.2 LiteLLM proxy — 59.5k stars

The general-purpose gateway most often recommended for teams.

- **Server**: a `model_list` in `config.yaml` maps public `model_name`s to
  `litellm_params` (`model: openai/...`, `api_key: os.environ/OPENAI_API_KEY`);
  a master key plus per-user **virtual keys** limit models and budgets. It serves
  Anthropic Messages at `/v1/messages` and the Responses API at `/v1/responses`
  ([Claude Code with non-Anthropic models](https://docs.litellm.ai/docs/tutorials/claude_non_anthropic_models)).
- **Claude Code side**: `ANTHROPIC_BASE_URL=http://0.0.0.0:4000`,
  `ANTHROPIC_AUTH_TOKEN=$LITELLM_MASTER_KEY` (or a virtual key),
  `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1`; non-Claude models must carry
  `claude` in their public name to survive the picker filter, with
  `model_info.display_name` for a friendly label.
- **Codex side**: `[model_providers.litellm]` with
  `base_url = "http://localhost:4000/v1"`, `env_key = "LITELLM_API_KEY"`,
  `wire_api = "responses"` — "so no secret is stored in the file"
  ([Codex CLI setup](https://docs.litellm.ai/docs/proxy/client_setup/codex_cli)).
- **Keeping the subscription**: with
  `general_settings.forward_client_headers_to_llm_api: true`, Claude Code keeps
  sending its Max-plan OAuth token as `Authorization`, and the LiteLLM key rides
  in `ANTHROPIC_CUSTOM_HEADERS="x-litellm-api-key: Bearer ..."`, so the gateway
  adds logging and budgets without replacing the login
  ([Claude Code Max subscription](https://docs.litellm.ai/docs/tutorials/claude_code_max_subscription)).

Anthropic's own gateway docs frame this pattern: credentials stay server-side,
and "provider switching: change the provider in gateway configuration, without
touching developer machines" — at the cost that "the gateway becomes
infrastructure your organization operates" and must keep forwarding new Claude
Code features ([LLM gateways](https://code.claude.com/docs/en/llm-gateway)).

### 4.3 Subscription relays: CLIProxyAPI (53.1k) and claude-relay-service (12.6k)

These turn subscription logins into API endpoints rather than switching API keys.

- **CLIProxyAPI** wraps OAuth logins for Codex/ChatGPT, Claude Code, Gemini and
  Grok and exposes OpenAI-, Gemini-, Claude- and Codex-compatible endpoints, with
  round-robin across multiple accounts ([README](https://github.com/router-for-me/CLIProxyAPI)).
  ccs embeds it; CCR and cc-switch offer similar "Codex OAuth reverse proxy"
  providers.
- **claude-relay-service** is a self-hosted server that pools Claude, OpenAI and
  Gemini subscription accounts added through an OAuth code-paste flow and issues
  `cr_`-prefixed keys with per-key model, client (User-Agent), rate and
  concurrency limits, sticky sessions and cooldown on 5xx. Clients set
  `ANTHROPIC_BASE_URL=http://host:3000/api/` + `ANTHROPIC_AUTH_TOKEN=cr_...`, or
  `model_provider = "crs"` with `base_url = .../openai` for Codex. The README
  warns that use may violate Anthropic's terms of service
  ([README](https://github.com/Wei-Shaw/claude-relay-service)).

### 4.4 OpenRouter (hosted, no local process)

OpenRouter's "Anthropic Skin" speaks the Anthropic API directly, so the whole
integration is a handful of variables: `ANTHROPIC_BASE_URL=https://openrouter.ai/api`,
`ANTHROPIC_AUTH_TOKEN=$OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY=""` (explicitly
blank, because a set API key "is treated as a direct-Anthropic credential"), and
the `ANTHROPIC_DEFAULT_*_MODEL` / `CLAUDE_CODE_SUBAGENT_MODEL` tier variables. Its
troubleshooting advice for a cached Anthropic login is `/logout` and relaunch
([OpenRouter guide](https://openrouter.ai/docs/guides/guides/claude-code-integration)).

---

## 5. Cross-cutting questions

**Where keys live.**

| Approach | Examples | Key at rest |
| --- | --- | --- |
| Plain text in the agent's config | cc-switch, zcf, OpenRouter guide, Codex `experimental_bearer_token` | `settings.json` `env` / `config.toml` / `auth.json`, plus the tool's own store in plaintext |
| Tool store + per-launch file | ccs | Per-profile settings file / auth dir outside the agent's user config |
| Indirection the agent calls | `apiKeyHelper`, Codex `auth.command`, `env_key` | Anywhere: vault, keychain, a tool's store |
| Gateway-held upstream key | LiteLLM, CCR, CRS, cc-switch proxy | Gateway; the agent holds only a local/virtual key |

Only the indirection and gateway rows keep upstream keys out of files the agent
(and every subprocess it spawns) can read.

**How the original login is restored.** Uniformly by *removing overrides*, never
by logging in again: Claude Code's `/login` credential sits at the bottom of the
precedence list and survives untouched in the Keychain. Codex is the exception,
because its login and API keys share `auth.json`; tools either delete and
restore that file (cc-switch, with a DB copy as the safety net and on-disk
refresh-token adoption) or avoid it entirely with `env_key` and
`requires_openai_auth = false`.

**How model lists are obtained.** Four sources: hard-coded preset ids (cc-switch,
zcf); the provider's `/v1/models` or `/models` (cc-switch, CCR); the agent's own
discovery against a gateway (Claude Code's `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY`,
used by CCR and LiteLLM); and the agent's catalog (Codex `model/list`,
`model_catalog_json`). Claude Code's `claude`/`anthropic` substring filter shapes
model naming in every gateway.

**How switching reaches running sessions.**

| Mechanism | Claude Code | Codex |
| --- | --- | --- |
| Edit user `settings.json` `env` | Applied mid-session when the merged `env` changes | — |
| Edit `config.toml` / `auth.json` | — | Next launch only; app-server asks for a restart |
| Per-launch flags/dirs (ccs, CCR "opened from CCR") | New sessions only; running ones keep theirs | New sessions only |
| Gateway-side switch (CCR, LiteLLM, cc-switch takeover) | Next request | Next request |

**Conflict with manual edits.** Three strategies appear. *Whole-file ownership
with backfill* (cc-switch): the live file is copied back into the outgoing
provider before each switch, and a shared snippet carries non-provider keys.
*Managed-key tracking* (CCR, zcf): only the keys the tool set are rewritten, and
CCR writes only when a managed key changed, with a backup. *Never touch the
file* (ccs, CCR's default scope): the user's config is left alone and the tool's
config is passed at launch. Separately, cc-switch scans shell rc files and the
Windows registry for exported variables that would silently outrank the file.

---

## 6. Patterns and trade-offs

- **The field converges on `ANTHROPIC_BASE_URL` + a bearer credential + the tier
  model variables** for Claude Code, and on a custom `[model_providers.<id>]`
  with `wire_api = "responses"` for Codex. Other formats (Bedrock/Vertex, WIF)
  are niche.
- **Writers versus gateways is a trade between simplicity and control.** Writing
  the agent's config needs no running process and has no single point of
  failure, but keys end up in files, Codex needs a restart, and there is no
  failover. A local gateway gives mid-session switching, failover, protocol
  conversion and logs, but it must stay running and must track every new header
  and field the agent sends (Anthropic's docs call this out explicitly). cc-switch
  offers both and makes the proxy opt-in.
- **Whole-file versus key-level ownership.** cc-switch's per-provider snapshot of
  the entire `settings.json` needs an elaborate backfill-plus-snippet dance, with
  its own failure modes (for example, injected defaults turn into "user values"
  unless they are stripped symmetrically on backfill). Tools that own only named
  keys (zcf, CCR) are simpler and leave the rest of the file to the user and to
  other tools.
- **Codex's shared `auth.json` is the hardest problem in the field.** cc-switch's
  most intricate code — preflight, four-file snapshot, adopting rotated refresh
  tokens, deleting stale keys only after a backup exists — exists because a
  switch can destroy a ChatGPT login.
- **Launch-scoped isolation is growing.** `CLAUDE_CONFIG_DIR`/`--settings` (ccs,
  CCR) and Codex `--profile` layers let different sessions use different
  providers at once, which a single global "active provider" cannot.
- **Subscription pooling is a separate, riskier market** (CLIProxyAPI, CRS) that
  the switchers now integrate; its own maintainers flag terms-of-service risk.

## 7. Worth borrowing / worth avoiding

**Worth borrowing**

- Restore the agent's own login by removing the override keys and relying on the
  agent's precedence list, rather than by storing or re-creating the login.
- Keep upstream keys behind an indirection the agent calls (`apiKeyHelper`,
  Codex `auth.command` / `env_key`) — the mechanism both agents document for
  this purpose, and one that also supports rotation.
- Track exactly which keys a tool wrote and write only when those changed, with
  a timestamped backup (CCR); write atomically with sorted keys and `0600` for
  credential files (cc-switch).
- Validate the full projection before committing the "active" pointer, and
  snapshot every file of a multi-file commit so a failure restores all of them
  (cc-switch's Codex preflight and snapshot).
- Before overwriting a token file, adopt any newer credential the agent itself
  rotated on disk (cc-switch's refresh-token adoption).
- Decide ownership from evidence in the file (a placeholder token, a dedicated
  provider id) rather than from a flag that can outlive a crash.
- Warn about shell-exported variables that silently outrank a written config.
- Use one stable provider id for all third-party Codex providers so history does
  not fragment across switches.
- Read models from the agent's own discovery or catalog where one exists, and
  respect Claude Code's picker filter when naming gateway models.

**Worth avoiding**

- Plaintext keys in the agent's `settings.json` `env` — the agent's own docs
  point away from it, and every subprocess inherits the values.
- Writing undocumented agent internals (`customApiKeyResponses`,
  `hasCompletedOnboarding`, `primaryApiKey` in `~/.claude/config.json`) to
  suppress prompts; they break silently when the agent changes.
- Assuming a Codex switch reaches a running session; it does not.
- Routing official subscription traffic through a switcher's proxy; cc-switch
  refuses it and the relay projects carry terms-of-service warnings.
- Treating the whole native config file as belonging to one provider, which
  forces backfill machinery to avoid losing the user's other settings.
