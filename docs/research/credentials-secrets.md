# Credentials and secrets for agents: how other products do it

**Feature**: hold secrets (API keys, tokens, OAuth grants) for AI agents and MCP servers on the local machine, hand each one to the process that needs it without exposing plaintext elsewhere, and move them between machines · **Coffer spec**: [credentials](../../openspec/specs/credentials/spec.md) · **Related ADRs**: [envelope-encrypted-credential-store](../decisions/envelope-encrypted-credential-store.md), [credential-references](../decisions/credential-references.md), [credentials-across-machines](../decisions/credentials-across-machines.md), [provider-keys-never-land-in-native-config](../decisions/provider-keys-never-land-in-native-config.md)
**Researched**: 2026-09 · **Method**: web research, primary sources

Every product below is described along the same five axes:

- **At rest**: where the ciphertext lives and who holds the key that opens it.
- **Injection**: how a plaintext value reaches the consumer: environment variable, rendered file, named pipe, HTTP header, or a helper process the consumer calls.
- **Rotation and TTL**: whether a secret expires, and who refreshes it.
- **Audit of reads**: whether a read is recorded, and what the record contains.
- **Multi-machine**: how a second machine gets the secret.

Star counts are as of 2026-09.

---

## 1. The agents themselves

### Claude Code

**At rest.** On macOS the login goes into the Keychain as a generic-password item named `Claude Code-credentials` ([issue #62213](https://github.com/anthropics/claude-code/issues/62213)). When the Keychain refuses the write, for example when it is locked in an SSH session, Claude Code falls back to `~/.claude/.credentials.json` with mode `0600`. That file is the only store on Linux. On Windows it is `%USERPROFILE%\.claude\.credentials.json`, protected only by the profile directory's ACL. With `CLAUDE_CONFIG_DIR` set, both the file and the Keychain entry are keyed to that directory, so two config directories hold two independent logins ([authentication docs](https://code.claude.com/docs/en/authentication#credential-management)).

**Precedence.** Claude Code reads credentials in a fixed order:

1. cloud-provider flags
2. `ANTHROPIC_AUTH_TOKEN`, sent as `Authorization: Bearer`
3. `ANTHROPIC_API_KEY`, sent as `X-Api-Key`, approved once per key in interactive mode
4. `apiKeyHelper` output
5. `CLAUDE_CODE_OAUTH_TOKEN`, a one-year token printed by `claude setup-token` and never saved by Claude Code
6. Anthropic profiles and federation (WIF) credentials
7. the `/login` subscription OAuth

`/status` shows which source won ([precedence](https://code.claude.com/docs/en/authentication#authentication-precedence)).

**Injection through a helper.** `apiKeyHelper` is a shell command whose stdout becomes the key:

- It is re-run after 5 minutes by default. `CLAUDE_CODE_API_KEY_HELPER_TTL_MS` changes the interval.
- A slow helper, over 10 s, shows a notice in the prompt bar.
- A failing helper (non-zero exit, timeout, or empty output) surfaces a named error within three attempts.

Sibling helpers follow the same pattern: `awsAuthRefresh`, `awsCredentialExport`, and `otelHeadersHelper` ([settings reference](https://code.claude.com/docs/en/settings-reference)).

**MCP credentials** ([MCP docs](https://code.claude.com/docs/en/mcp)):

- **Variable expansion.** `.mcp.json` expands `${VAR}` and `${VAR:-default}` in `command`, `args`, `env`, `url` and `headers`. An unset variable leaves the literal text in place and prints a warning in `claude mcp list`.
- **Credential-shaped variables are blanked.** In a *remote* server's `url` and `headers`, variables such as `ANTHROPIC_API_KEY`, `AWS_BEARER_TOKEN_BEDROCK` and `NPM_TOKEN` expand to empty, so a checked-in project config cannot send your keys to its own server. The documented workaround is to copy the value into a variable with a different name.
- **`headersHelper`.** A per-server command prints a JSON map of headers at connect time.
  - It is killed after 10 s.
  - It receives `CLAUDE_CODE_MCP_SERVER_NAME` and `CLAUDE_CODE_MCP_SERVER_URL`.
  - For project or plugin servers it runs only after the workspace trust dialog, and with every environment variable whose name contains `TOKEN`, `SECRET`, `PASSWORD`, `KEY` or `AUTH` removed.
  - A common use is `op read` inside the helper, so the committed config carries only an `op://` reference ([example](https://davidwinter.dev/2026/07/08/1password-claude-code-mcp-credentials/)).
- **OAuth tokens.** Remote-server OAuth tokens and client secrets go into the Keychain on macOS, or the credentials file elsewhere. On a `401`, Claude Code refreshes once and retries. If the refresh token is rejected it tells the user to run `/mcp` and choose Re-authenticate.

**Rotation.** A subscription login warns three days before it expires. Once refresh fails, every request returns `Login expired`.

**Audit.** None of reads. `/status` only shows which credential is active.

**Multi-machine.** None built in. The two routes are `claude setup-token` to mint a portable OAuth token, or re-running `/login` on each machine.

**macOS lesson.** Issue #62213 shows how easy it is to degrade Keychain access control by accident. The desktop app rotated the item with `SecItemDelete` + `SecItemAdd` instead of `SecItemUpdate`. The new item's partition list lost `apple-tool:`, and every later `/usr/bin/security` read raised a prompt.

### Codex CLI

**At rest.** `cli_auth_credentials_store` takes one of four values ([auth docs](https://learn.chatgpt.com/docs/auth)):

- `file` stores `~/.codex/auth.json` under `CODEX_HOME`.
- `keyring` uses the OS credential store and fails if none is available.
- `auto` prefers the keyring and falls back to the file.
- `ephemeral` keeps credentials in memory only.

The docs say to "treat `~/.codex/auth.json` like a password". ChatGPT logins refresh automatically during use. `codex login --device-auth` handles headless machines, and `printenv OPENAI_API_KEY | codex login --with-api-key` stores an API key.

**Multi-machine.** The documented recipe is to copy the file: `ssh … 'cat > ~/.codex/auth.json' < ~/.codex/auth.json`, or `docker cp` into a container.

**Provider keys are never stored by Codex** ([config reference](https://learn.chatgpt.com/docs/config-file/config-reference)). Each `model_providers.<id>` names where its key comes from:

- `env_key` names an environment variable, with `env_key_instructions` as setup text.
- `env_http_headers` fills headers from environment variables.
- `experimental_bearer_token` holds an inline token. The docs mark it "discouraged".
- `[model_providers.<id>.auth]` sets a `command` that prints a bearer token. It gets no stdin and has `timeout_ms` (default 5000). `refresh_interval_ms` (default 300000) re-runs it proactively. An empty token is an error ([advanced config](https://learn.chatgpt.com/docs/config-file/config-advanced)).

**MCP.**

- `mcp_servers.<id>.env` holds literal values. `env_vars` allowlists variables to pass through. `bearer_token_env_var` names the variable that holds a remote server's token.
- MCP OAuth tokens follow `mcp_oauth_credentials_store` (`auto | file | keyring`). The keyring service is `Codex MCP Credentials`, and each entry's key is a SHA-256 of server name and URL. The file fallback is `CODEX_HOME/.credentials.json`. Tokens refresh 30 s before expiry ([`oauth.rs`](https://github.com/openai/codex/blob/main/codex-rs/rmcp-client/src/oauth.rs)).
- The dual store has produced bugs: logout left stale tokens in the fallback file ([#25002](https://github.com/openai/codex/issues/25002)), and OAuth login hung on Linux keyrings ([#31722](https://github.com/openai/codex/issues/31722)).

**Leakage to tool subprocesses.** `shell_environment_policy` decides what spawned shell commands inherit: `inherit = all | core | none`, plus include and exclude filters. A built-in filter removes names containing `KEY`, `SECRET` or `TOKEN`, but it runs only when `ignore_default_excludes = false`. The reference gives the default as `true`, so by default the filter is off.

**Audit.** None.

---

## 2. Password-manager-backed injectors

### 1Password (CLI, Environments, SSH agent, SDKs)

**Secret references.** A reference has the form `op://<vault>/<item>/[<section>/]<field>`, optionally followed by `?attribute=otp|type|id…` or `?ssh-format=openssh` ([syntax](https://www.1password.dev/cli/secret-reference-syntax/)).

- References are case-insensitive.
- Names may contain alphanumerics, `-`, `_`, `.` and whitespace. Any other character forces the use of the item's ID instead of its name.
- A reference is safe to commit. It only works for someone whose account can open that vault.

**Injection verbs:**

- **`op run -- cmd`** ([docs](https://www.1password.dev/cli/secrets-environment-variables/)) scans the environment and any `--env-file` for `op://` values and resolves them. It then starts `cmd` as a subprocess with the plaintext set in *its* environment only. Resolved values that appear in the subprocess's stdout are **masked** by default (`--no-masking` turns this off). `--environment <id>` pulls a whole 1Password Environment, and it can be combined with an env file.
- **`op inject -i tpl -o out`** ([docs](https://www.1password.dev/cli/secrets-config-files/)) renders a template containing `op://` references, which may contain `$VAR`, into a plaintext file. The docs tell users to delete the output when done. This is the one verb that writes plaintext to disk.
- **`op read`** prints a single value. This is what shell helpers such as `headersHelper` and `apiKeyHelper` call.

**Environments** ([overview](https://www.1password.dev/environments/)) are a newer object: a named set of environment variables, separate from vault items. They can be delivered four ways:

- **A mounted local `.env`** ([docs](https://www.1password.dev/environments/local-env-file)). The file is a UNIX named pipe (FIFO). Its contents are "passed directly to the reader process on demand" and "never stored on disk".
  - The first read triggers an authorization prompt. After that "every process can read it until you lock 1Password or disable the `.env` file".
  - It works on Mac and Linux only, not Windows.
  - It is "not designed for concurrent access".
- AWS Secrets Manager sync (beta).
- The SDKs (Go, JavaScript, Python).
- An **agent hook** ([docs](https://www.1password.dev/environments/agent-hook-validate)) for Claude Code, Cursor, GitHub Copilot and Windsurf.
  - It runs at `beforeShellExecution` in Cursor and `preToolUse` in Copilot.
  - It checks that each required `.env` mount is enabled, exists, and really is a FIFO, and blocks the agent with remediation text if not.
  - It **fails open** when the 1Password database cannot be read.

**SSH agent** ([docs](https://www.1password.dev/ssh/agent/), [security model](https://www.1password.dev/ssh/agent/security/)). This is the purest form of "use without exposure": the private key "never leaves the 1Password app", and clients only get signatures over `SSH_AUTH_SOCK`.

- Each *application* must be approved. An application is a process tree, except that each tab of a terminal or IDE counts separately.
- An approval can last until 1Password locks or quits, for a fixed period such as 4 hours, or for a single request.
- `~/.config/1Password/ssh/agent.toml` restricts which keys are offered.

**CLI authentication.** The CLI unlocks through the desktop app with biometrics. The app records CLI activity: the command, the time, the calling application and the account ([app integration](https://www.1password.dev/cli/app-integration/)). Headless use relies on service accounts (`OP_SERVICE_ACCOUNT_TOKEN`).

**Header injection at an MCP gateway.** In the Runlayer integration (March 2026) the gateway stores only a reference such as `Bearer op://MCP/GitHub/token` ([1Password blog](https://1password.com/blog/secure-mcp-credentials-1password-runlayer)).

- On each tool call it resolves the `op://` part of the header through the SDK and injects the result into the upstream request.
- The value leaves memory once the request finishes, with "no caching to disk, no storage in the database".
- Each fetch emits a `secret_provider.fetched` audit event.
- **Rotation is detected by comparing SHA-256 hashes** of successive fetches, which emits `secret_provider.rotated`. Only hashes are ever logged.

**Stance on MCP.** "We will not use MCP to expose raw credentials or secrets" ([July 2025](https://1password.com/blog/where-mcp-fits-and-where-it-doesnt)). The stated reason is that agent behaviour is non-deterministic and open to prompt injection. The recommended pattern is to put `op://` references in `.env` and launch servers as `op run --env-file=.env -- server`, so `mcp.json` can be committed ([Nov 2025](https://1password.com/blog/securing-mcp-servers-with-1password-stop-credential-exposure-in-your-agent)).

**Multi-machine.** Sync is end-to-end encrypted. Keys come from two-secret key derivation: the account password (about 40 bits, memorized) plus a 128-bit Secret Key that never reaches 1Password's servers. A new device needs the Secret Key, usually from the Emergency Kit ([Secret Key](https://support.1password.com/secret-key-security/)).

### Bitwarden Secrets Manager (`bws`)

**Access tokens.** A machine account gets an **access token** that carries its own decryption key (end-to-end encrypted) ([docs](https://bitwarden.com/help/access-tokens/)).

- Tokens are "never stored in Bitwarden databases and cannot be retrieved", so the user must store them somewhere else as soon as they are created.
- A token can have an expiry or none.
- A revoked token can keep an existing session alive for up to an hour.

**Injection** ([CLI](https://bitwarden.com/help/secrets-manager-cli/)). `bws secret get <UUID>` addresses secrets by UUID, not path. `bws run -- cmd` injects every secret the machine account can see.

- `--project-id` narrows the set to one project.
- `--no-inherit-env` gives the child a minimal environment.
- `--uuids-as-keynames` uses the UUIDs as variable names for POSIX safety.

**Scoping and multi-machine.** Scoping is per project and per machine account. A second machine gets secrets by being handed a token.

---

## 3. Secret servers

### HashiCorp Vault (36.3k stars, BUSL) / OpenBao (7.5k, MPL-2.0 fork)

**At rest and key custody** ([seal](https://developer.hashicorp.com/vault/docs/concepts/seal)). Keys form a chain: data is encrypted with a keyring, the keyring with the root key, and the root key with the unseal key.

- By default the unseal key is split with Shamir's secret sharing into 5 shares, any 3 of which reconstruct it.
- Auto-unseal hands custody to a cloud KMS or HSM instead.
- A restarted node comes up *sealed* and can decrypt nothing until it is unsealed. If the seal's KMS key is lost, the cluster "becomes unrecoverable, even from backups".

**Dynamic secrets and leases** ([leases](https://developer.hashicorp.com/vault/docs/concepts/lease)). A read from a dynamic engine (database, AWS and others) *creates* a credential with a `lease_id` and a TTL.

- The consumer must renew the lease before the TTL runs out. On expiry Vault revokes it and deletes the backing credential.
- Lease IDs begin with the path they were issued from, so `vault lease revoke -prefix aws/` kills a whole family of credentials during an incident.
- Revoking a token revokes every lease it created.

**Injection: Vault Agent** ([process supervisor](https://developer.hashicorp.com/vault/docs/agent-and-proxy/agent/process-supervisor)):

- auto-auth, which logs in and keeps a token fresh
- templates, which render files
- **exec mode**, where `env_template` blocks render into a child process's environment and the agent waits until every template has rendered before starting the child
- On a secret change the agent can restart the child (`restart_on_secret_changes = always|never`, `restart_stop_signal`, 30 s grace). It passes stdio through and exits with the child's exit code.

**Audit of reads** ([audit devices](https://developer.hashicorp.com/vault/docs/audit)). Every request and response is logged. Most string values appear only as **HMAC-SHA256** hashes, and an operator can hash a candidate value with `/sys/audit-hash` to check whether it appeared. The log is **fail-closed**: if no audit device can write, Vault refuses the request.

### Infisical (29.4k stars, MIT core)

**References and injection.**

- Secrets can reference each other: `${KEY}`, `${env.KEY}`, `${env.folder.KEY}` and `${@project.env.KEY}`. A reference resolves only if the reader can read every secret it points to; otherwise it stays unexpanded ([references](https://infisical.com/docs/documentation/platform/secret-reference)).
- `infisical run --env --path [--recursive] -- cmd` injects environment variables. `--watch` restarts the command when secrets change and is meant for development only. Headless use authenticates with a machine identity via `INFISICAL_TOKEN` ([run](https://infisical.com/docs/cli/commands/run)).

**Infisical Agent** ([docs](https://infisical.com/docs/integrations/platforms/infisical-agent)) mirrors Vault Agent:

- It auto-authenticates and writes renewed access tokens to file **sinks**.
- It renders Go templates using `listSecrets`, `getSecretByName` and `dynamicSecret`.
- It polls every 5 minutes by default, runs a command when a secret changes, and renews dynamic-secret leases.

**Platform.** The platform adds rotation, dynamic secrets, audit logs with streaming, and secret scanning ([repo](https://github.com/Infisical/infisical)).

### Doppler (CLI 396 stars, Apache-2.0; service is SaaS)

**Injection.** `doppler run` injects environment variables ([CLI](https://docs.doppler.com/docs/cli)). Two details go beyond the other servers ([accessing secrets](https://docs.doppler.com/docs/accessing-secrets)):

- **`--mount <file>`** exposes secrets as a named pipe that is removed when Doppler exits. Doppler calls this "the **only** secure method for supplying secrets via the file system".
  - `--mount-format` and `--mount-template` shape the output.
  - `--mount-max-reads` caps reads, for example so a dynamic SSH key disappears after one connection.
  - A mount inside an iCloud-synced directory fails.
- **Encrypted fallback snapshots.** Each `doppler run` saves the secrets it fetched to `~/.doppler/fallback`, encrypted with AES-256-GCM under a PBKDF2 key derived from the service token or a `--passphrase`, so an outage does not stop the app ([fallback files](https://docs.doppler.com/docs/enclave-automatic-fallbacks)).

**Rotation.** Service tokens are scoped to one project config. `--max-age` creates ephemeral tokens.

---

## 4. Encrypted in the repository

### SOPS + age (sops 23.2k stars, CNCF sandbox; age 23.7k)

**Mechanism.** SOPS encrypts *values* and leaves keys readable, so diffs stay meaningful ([docs](https://getsops.io/docs/)).

- Each file gets a data key. Every value is encrypted separately with AES-256-GCM.
- The data key is wrapped once per master key (age, PGP, AWS/GCP/Azure/HuaweiCloud KMS).
- A MAC over all values detects tampering.
- `.sops.yaml` `creation_rules` choose recipients by path. `encrypted_regex` and `unencrypted_suffix` choose which fields get encrypted.
- **Key groups** with a Shamir threshold require several master keys to decrypt.
- `sops updatekeys` re-wraps the data key for a changed recipient list. `-r` rotates the data key itself.

**Injection.** `sops exec-env` puts decrypted values in a child's environment. `exec-file` passes a FIFO path in place of `{}`, and `--no-fifo` switches to a temporary file for consumers that need to re-read it.

**Key custody.** The age key sits in `keys.txt`: `~/.config/sops/age/keys.txt` on Linux and `~/Library/Application Support/sops/age/keys.txt` on macOS, or wherever `SOPS_AGE_KEY_FILE` points.

**age itself** ([repo](https://github.com/FiloSottile/age)):

- keys are short text strings (`age1…` public, `AGE-SECRET-KEY-1…` secret)
- a file can have many recipients
- `ssh-ed25519` and `ssh-rsa` keys work as recipients
- scrypt passphrase mode
- a post-quantum hybrid (`-pq`)
- plugins for hardware keys, such as age-plugin-yubikey

**Multi-machine.** Transfer is just `git pull`. The only thing that must travel out-of-band is the private key.

### git-crypt (9.9k stars)

**Mechanism.** git-crypt encrypts whole files transparently through `.gitattributes` clean/smudge filters ([repo](https://github.com/AGWA/git-crypt)).

- The cipher is AES-256-CTR with a synthetic IV taken from an HMAC-SHA1 of the file. Encryption is therefore deterministic, so git can deduplicate, and the only leak is whether two files are identical.
- Keys are shared either by encrypting the repo key to GPG users (`add-gpg-user`) or by exporting a symmetric key.

**Limits it documents.** It has **no revocation and no key rotation**. File names and commit messages stay unencrypted. It is "not the best tool for encrypting most or all of the files in a repository".

---

## 5. OS keychains (the usual "local" anchor)

**macOS Keychain.** Each item has two gates:

- A legacy **ACL** lists trusted applications.
- A **partition list** holds entries of the form `apple:`, `apple-tool:`, `teamid:<ID>` or `cdhash:<hash>`. An app outside the partition list gets a prompt.

A developer-signed app lands in `teamid:`, so its updates stay trusted. An ad-hoc or unsigned build (Nix, a local PyInstaller build) only gets `cdhash:`, which **changes on every build**, so every upgrade re-prompts. There is no upgrade-stable workaround through `security(1)`, and changing the partition list needs the keychain password ([secretspec #438](https://github.com/cachix/secretspec/issues/438), [partition IDs](https://mostlikelee.com/blog-1/2017/9/16/scripting-the-macos-keychain-partition-ids)). Items sync through iCloud only when they are flagged `kSecAttrSynchronizable` *and* live in the data-protection keychain ([Apple](https://developer.apple.com/documentation/security/ksecattrsynchronizable)). The ordinary login keychain does not roam.

**Linux Secret Service (libsecret, gnome-keyring, KWallet).**

- **Data model.** Collections hold items. Items are found by lookup attributes and carry a label. Values travel over D-Bus encrypted per session with `dh-ietf1024-sha256-aes128-cbc-pkcs7` ([spec](https://specifications.freedesktop.org/secret-service/latest/)).
- **Threat model.** Once the login collection is unlocked, "any application can easily read any secret". GNOME's answer is that untrusted apps must be sandboxed away from the session bus, as Flatpak does ([CVE-2018-19358](https://nvd.nist.gov/vuln/detail/CVE-2018-19358)).
- **Headless machines** have no unlocked collection unless a daemon is started with `--unlock`.

**Windows Credential Manager.**

- A `CRED_TYPE_GENERIC` blob is capped at `CRED_MAX_CREDENTIAL_BLOB_SIZE` = 5×512 bytes. Long OAuth tokens and JWTs overflow it.
- Persistence can be `SESSION`, `LOCAL_MACHINE`, or `ENTERPRISE`, which roams with a roaming profile ([CREDENTIAL](https://learn.microsoft.com/en-us/windows/win32/api/wincred/ns-wincred-credentiala)).

**Python `keyring`** (1.5k stars, [repo](https://github.com/jaraco/keyring)) wraps all three OS stores plus KWallet. Its own README warns that on macOS "any Python script or application can access secrets created by keyring from that same Python executable without the operating system prompting". It also notes that no security analysis exists for the other backends.

**secretspec** (1.5k stars, [site](https://secretspec.dev/)) separates *declaration* from *storage*.

- `secretspec.toml` lists the secrets a project needs, per profile.
- Each secret resolves through a provider chain such as `["vault", "keyring", "env"]` across 35+ backends.
- `secretspec run` injects the result.
- It logs access "with reasons", aimed explicitly at AI agents.

---

## 6. MCP-specific runtimes and the MCP authorization spec

### ToolHive (Stacklok, 2.2k stars)

**Providers.** One secrets provider is active at a time ([secrets guide](https://docs.stacklok.com/toolhive/guides-cli/secrets-management)):

- **Encrypted** (the default) keeps a local file, `secrets_encrypted` under the app-support or config directory. It is encrypted with a password that lives in the OS keyring.
- **1Password** is read-only and uses `OP_SERVICE_ACCOUNT_TOKEN` with `op://` URIs.
- **Environment** is read-only and reads `TOOLHIVE_SECRET_<NAME>`, for CI.

**Injection.** `thv run --secret <name>,target=<ENV_VAR> <server>` injects the value into the server's container environment.

**Remote servers.** Remote servers take `--remote-auth-*` flags ([remote guide](https://docs.stacklok.com/toolhive/guides-cli/run-remote-mcp-servers)):

- bearer token, or bearer token from a file
- OIDC issuer, or OAuth2 authorize/token URLs
- client secret, or client secret from a file
- scopes, and an RFC 8707 `--remote-auth-resource`
- `--remote-auth-skip-browser` for headless use

ToolHive stores the access and refresh tokens and refreshes them automatically. The docs do not name the storage location.

### Docker MCP Toolkit / MCP Gateway (gateway 1.6k stars)

**At rest.** `docker mcp secret set key[=value]`, which also accepts a piped value, writes to the OS keychain through **Docker Pass**, the Docker Secrets Engine ([reference](https://docs.docker.com/reference/cli/docker/mcp/secret/set/)). Without Docker Desktop, a Linux engine needs the `docker-secrets-engine` packages. An ordinary `credsStore: osxkeychain` does not satisfy it ([discussion #490](https://github.com/docker/mcp-gateway/discussions/490)). A reported bug made every update after the first insert fail with "item already exists in the keychain" ([#551](https://github.com/docker/mcp-gateway/issues/551)).

**Injection and isolation** ([security.md](https://raw.githubusercontent.com/docker/mcp-gateway/main/docs/security.md)):

- Secrets are **scoped to the server that declares them**. Names are validated, so one server cannot obtain another's secret by guessing or with glob characters.
- Containers do *not* inherit the host environment. They get only their declared env, config and secrets.
- `--block-secrets`, on by default, scans tool-call arguments and text responses for secret-shaped values in both directions.

**Remote OAuth** is authorized through a browser flow inside Docker Desktop.

### MCP authorization spec (2025-11-25)

[Spec](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization) scope:

- **STDIO servers** "SHOULD NOT" use the flow and should "retrieve credentials from the environment". That is the rule every env-injection design above follows.
- **HTTP servers** use OAuth 2.1 with PKCE (S256 required, and the client must refuse if metadata does not advertise PKCE).
  - Discovery goes through protected-resource metadata (RFC 9728).
  - The client registers in this order of preference: pre-registration, Client ID Metadata Documents, then dynamic registration.
  - The client **must** send an RFC 8707 `resource` parameter so the token is bound to one server.

Token rules:

- The client sends the token as `Authorization: Bearer` on every request and never in the query string.
- Servers must reject tokens issued for another audience and must not pass tokens through to upstream services.
- For public clients, refresh tokens **must** rotate.
- Clients "MUST implement secure token storage".
- A `403 insufficient_scope` triggers step-up re-authorization, with a retry limit.

### mcp-remote (1.6k stars) and mcp-auth-proxy (173 stars)

**mcp-remote** ([repo](https://github.com/geelen/mcp-remote)) bridges a stdio client to a remote OAuth server.

- It stores client registrations and tokens as files under `~/.mcp-auth/mcp-remote-v1/`, or `MCP_REMOTE_CONFIG_DIR`. The version is the storage layout's, not the package's, so upgrades do not force a new login.
- Each combination of URL, resource, headers and parameters gets its own session.
- `--header` supports `${ENV}` substitution, so a secret can stay out of `argv`.

**mcp-auth-proxy** ([repo](https://github.com/sigbit/mcp-auth-proxy)) works in the opposite direction. It puts OAuth 2.1/OIDC (Google, GitHub, any OIDC provider, or a password) *in front of* an MCP server, including a stdio server it wraps as `/mcp`. It guards who can reach a server; it does not store credentials for the server.

---

## 7. Provider switchers (Chinese ecosystem)

**cc-switch** (136k stars, [repo](https://github.com/farion1231/cc-switch)) is the most-used provider switcher for Claude Code, Codex and Gemini CLI.

- **At rest.** Its own store is SQLite at `~/.cc-switch/cc-switch.db`, with ten rolling backups.
- **Injection.** Switching a provider **writes the key into each agent's native config** ([config files](https://github.com/farion1231/cc-switch/blob/main/docs/user-manual/zh/5-faq/5.1-config-files.md)):
  - `env.ANTHROPIC_AUTH_TOKEN` / `env.ANTHROPIC_API_KEY` in `~/.claude/settings.json`
  - `OPENAI_API_KEY` in `~/.codex/auth.json`
  - `GEMINI_API_KEY` in `~/.gemini/.env`
- **Multi-machine.** It syncs through Dropbox, OneDrive, iCloud or WebDAV.
- **Encryption.** The docs describe no encryption for the database, the written files, or the synced copy.
- Its issue tracker shows the side effect of owning another tool's config file: overwrites clobber user settings ([#1570](https://github.com/farion1231/cc-switch/issues/1570)), and preset writes fill the wrong field ([#2525](https://github.com/farion1231/cc-switch/issues/2525)).

---

## Comparison (summary)

| Product | At rest / key custody | Injection | Rotation / TTL | Audit of reads | Multi-machine |
|---|---|---|---|---|---|
| Claude Code | Keychain; else 0600 JSON | env, `apiKeyHelper`, `headersHelper` | helper TTL 5 min; OAuth refresh on 401 | — | re-login / `setup-token` |
| Codex | keyring / `auth.json` / ephemeral | `env_key`, `auth.command`, `bearer_token_env_var` | ChatGPT auto-refresh; helper 5 min | — | copy `auth.json` |
| 1Password | E2E vault, 2-secret KDF | `op run`, `op inject`, FIFO `.env`, SSH agent, SDK header resolve | vault-side; hash-diff rotation detection (Runlayer) | app logs CLI use; gateway fetch events | E2E sync + Secret Key |
| Bitwarden SM | E2E, key inside access token | `bws run` | token expiry | server-side | hand out token |
| Vault / OpenBao | seal chain, Shamir or KMS | Agent exec/env, templates, sinks | leases, dynamic creds, prefix revoke | HMAC'd, fail-closed | server |
| Infisical | server | `run`, Agent templates/sinks | rotation, dynamic secrets | audit logs + streaming | server |
| Doppler | server + encrypted local fallback | env, FIFO `--mount` with max reads | ephemeral tokens | server | server |
| SOPS + age | per-file data key wrapped per recipient | `exec-env`, `exec-file` (FIFO) | `updatekeys`, `-r` | git history | git + out-of-band private key |
| git-crypt | repo key, GPG-wrapped | checkout decrypts | none | git history | git + key export |
| ToolHive | keyring-password-encrypted file / 1P / env | `--secret name,target=ENV` into container | OAuth refresh | — | per machine |
| Docker MCP | OS keychain via Docker Pass | declared per server into container; outbound scan | OAuth via Desktop | — | per machine |
| cc-switch | plaintext SQLite | writes native agent config | — | — | cloud-folder sync |

---

## Patterns and trade-offs

**Where the field agrees:**

- **References in config, values elsewhere.** `op://…`, `${VAR}`, `env_key`, `bearer_token_env_var`, `--secret name,target=` and Infisical `${env.KEY}` all do the same job: the file that gets committed, shared or read by the agent names a secret without containing it. Tools differ only in whether the reference addresses a path (1Password, Vault), a name in a local store (ToolHive, Docker), or an environment variable (Claude Code, Codex).
- **Resolve at spawn, scoped to one child.** `op run`, `bws run`, `infisical run`, `doppler run`, `sops exec-env`, Vault Agent exec and `thv run` all resolve at the last moment and set the value only in the child's environment. MCP's own spec pushes stdio servers toward exactly this.
- **Helpers for anything that expires.** Claude Code (`apiKeyHelper`, `headersHelper`) and Codex (`auth.command`) each converged on "run a command, read stdout, cache for about 5 minutes, re-run on expiry or 401". This is the seam external vaults plug into, and it keeps refresh logic out of the agent.
- **OS keychain as the root of local trust, with a file fallback.** Claude Code, Codex, ToolHive and Docker all anchor in the keychain and quietly fall back to a mode-0600 file on headless Linux or locked sessions. The fallback is where the bugs cluster: stale tokens left behind, hangs, items duplicated across two stores.

**Where the field splits, and why:**

- **Env vs pipe vs header.** Environment variables are universal but readable by anything the child spawns, and they turn up in crash dumps. Codex's default-excludes filter and Claude Code's credential-name stripping are both patches for that. Named pipes (1Password Environments, Doppler `--mount`, SOPS `exec-file`) give a file interface with no disk plaintext and optional read limits, but they are not available on Windows and break with concurrent readers. Header injection at a proxy (Runlayer, Docker's gateway) keeps the secret out of the child entirely, but it only works for HTTP transports.
- **Who holds the root key.** A server behind a seal (Vault), a memorized password plus a device-held key (1Password), a keyring password (ToolHive), or a file key moved out-of-band (SOPS/age, git-crypt). Local-first tools choose between two failure modes: a keychain item that re-prompts after every unsigned rebuild, or a key file that is only as safe as its permissions.
- **Static vs dynamic.** Only the server products (Vault, Infisical) mint credentials per consumer with a lease. Everyone else stores long-lived keys and at best refreshes OAuth. Local tools that want rotation detect it (the Runlayer hash diff) rather than drive it.
- **Audit of reads.** Server products log every read, hashing the value (Vault's HMAC, Runlayer's SHA-256). Local agents and MCP runtimes record nothing about reads. Vault's fail-closed audit is the strongest guarantee and the most operationally expensive.
- **Moving secrets between machines** takes one of three shapes:
  - a hosted E2E vault (1Password, Bitwarden)
  - ciphertext in git with keys moved out-of-band (SOPS, git-crypt)
  - "copy the file" (Codex `auth.json`, cc-switch's cloud folder)

  Only the first two keep plaintext off the transport.

## Worth borrowing / worth avoiding

**Borrow:**

- **One resolvable reference syntax that also accepts external schemes.** An `op://`-style URI that can point either at the local store or at an existing vault means users never copy a secret they already keep in 1Password or Bitwarden. ToolHive's pluggable providers and secretspec's provider chain show the shape.
- **Hash-based rotation detection and read audit.** Hashing the value on each resolve (Runlayer's SHA-256, Vault's HMAC) gives "was it read, did it change" records without logging the value.
- **Per-server secret scoping with validated names.** Docker's rule that a server receives only the secrets it declared, checked by exact name, stops a compromised or confused server from asking for another's key.
- **Blank credential-shaped variables in shareable config.** Claude Code refuses to expand `*_TOKEN`/`*_KEY` into a remote server's URL or headers, and strips them from helpers' environments. It is a cheap defence against a hostile project file.
- **Helper commands with a TTL and a named error.** A 5-minute cache, a hard timeout, and a specific "your helper is failing" message within three attempts (Claude Code) beat silent 401s.
- **Wrap per recipient, not per secret, for multi-machine.** The SOPS/age model encrypts the data once and wraps its key once per machine or person. `updatekeys` adds or removes a machine without re-encrypting every value.
- **FIFO delivery with a read limit** for consumers that insist on a file (Doppler `--mount-max-reads`, 1Password Environments), instead of rendering plaintext `.env` files.
- **Per-application approval with a bounded lifetime** (the 1Password SSH agent) as the model for any interactive "may this process use this key?" prompt.

**Avoid:**

- **Writing keys into another tool's native config.** cc-switch puts plaintext keys in `settings.json`, `auth.json` and `.env`, then syncs them through consumer cloud folders. The key ends up in files the agent reads and prints, backs up, and hands to its own subprocesses.
- **Rendering plaintext files as the default path.** `op inject` needs a "delete it afterwards" warning for a reason.
- **Silent dual stores.** The keyring-or-file fallback in Codex and Claude Code is where logout leaks, hangs and stale-token bugs live. Whichever store is in use should be visible, and deleting a credential should clear both.
- **Replacing keychain items by delete + add.** It resets the partition list (Claude Code #62213). Update items in place.
- **Relying on keychain ACLs for unsigned or ad-hoc builds.** A `cdhash:` partition changes on every build, so users learn to click through prompts. Without a stable signing identity, a key file with strict permissions plus an explicit unlock is more honest.
- **Failing open on the security path.** The 1Password agent hook fails open when its database is unreadable. That is acceptable for a convenience check and wrong for anything that gates a secret.
- **Irrevocable sharing.** git-crypt has no revocation or rotation. Any multi-machine scheme needs a way to remove a machine and re-wrap the keys.
