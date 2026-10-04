# Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New

**Status**: Accepted
**Date**: 2026-09-30
**Deciders**: Yuxing Wu
**Related**: [The Master Key Lives in a Keychain Access Group Only Coffer's Signed Binaries Can Read; Secrets Stay Envelope-Encrypted in the Vault](master-key-lives-in-the-macos-keychain.md), [Standalone Secrets Are Named `coffer://secret/` References, Injected Only Into One Child Process](standalone-secrets-are-named-references-injected-into-one-child.md), [API-Key Providers Are Reached Through a Separate Local Model Proxy That Relays Bytes Unchanged](api-key-providers-are-reached-through-a-separate-local-model-proxy.md), [A Per-Start Token, Handed to the Page by Whoever Hosts It, Behind a Loopback Host Guard](daemon-auth-and-origin-guard.md), [Resources Cite Secrets by Opaque Reference, Resolved Only at the Moment of Use](credential-references.md), [Managed Agents Run With Full Permissions; Owner Pairing Is the Gate](managed-agents-run-with-full-permissions.md), [Per-Agent Resource Scope Is One Framework Allow-List, Enforced by Each Kind](per-agent-resource-scope.md), [The Desktop Shell Hosts the Shared Frontend and Owns Only What a Browser Cannot Do](desktop-shell-over-a-shared-frontend.md), [Knowledge Is a Directory of Markdown Files, Not an Index](knowledge-is-plain-files.md), [Distribution — Three PyInstaller Binaries, Shipped as a CLI Archive and a Desktop App](distribution-pyinstaller.md), [Audit Every Change With Its Actor, Log Invocations Without Payloads, Prune Per Table](audit-and-retention.md), [principles](../../docs-site/architecture/principles.md) (Secrets; Network defaults), research note [credentials and secrets](../research/credentials-secrets.md), spec secret "Return no plaintext on any route, command or tool", spec secret "Release plaintext only to a present human in the desktop app", spec secret "Hold a secret for a new destination until a person approves it", spec secret "Hold plaintext only in memory at the moment of use", spec daemon "Require a token on every management call", spec daemon "Refuse a request whose Host or Origin is not the daemon's own", spec desktop-app "Reimplement no daemon route in the shell", PR #464

## Context

Coffer holds the user's secrets and hands them to the things that consume
them: MCP servers, channel adapters, the sync remote, model providers. The
agents it serves — Claude Code and Codex — run as the same OS user, and a
managed agent runs with full permissions
([Managed Agents Run With Full Permissions](managed-agents-run-with-full-permissions.md)).
This ADR decides where Coffer draws its security boundary against those
agents, and what it stops claiming.

**The threat.** The case that matters is a **prompt-injected agent running as
the user**: a coding agent that read a hostile web page, issue, README or tool
result and now follows the attacker's instructions with the user's shell. It is
not a malicious binary the user installed (nothing at user level stops that),
and not another OS user (loopback binding and file modes already keep that one
out). Second in line is a **web page in the user's browser**, which can send
requests to `127.0.0.1` and, through DNS rebinding, read the answers.

**What such an agent could do before the boundary** (measured 2026-09-30 on
macOS 15.7.7, SIP on, against the design this decision replaced):

| Path | Result |
| --- | --- |
| Read `~/.coffer/daemon.json`, then call the route that returned a secret's value, or run the command's `--show` form | the plaintext of any secret — audited as a read, not refused |
| `coffer provider key --connection-uid <uid>` | a real provider key |
| `coffer sync key export <file>` | the master key, which opens every ciphertext |
| Read `~/.coffer/master.key` | the master key (the file default) |
| `lldb -p <daemon pid>` | decrypted secrets from the daemon's memory: the shipped binaries are ad-hoc signed with no hardened runtime. Against the same binary signed with `codesign -o runtime`, the attach is refused |
| `ps eww <pid>` / `KERN_PROCARGS2` on an MCP stdio server Coffer spawned | the secret in that server's initial environment — **also from inside Claude Code's Seatbelt sandbox**, and also against a hardened-runtime binary |
| `security find-generic-password -w` on an item another signed app owns | an Allow / Always Allow / Deny dialog; one "Always Allow" opens the item to every process for good |
| Register an MCP server whose `env` cites an existing secret and whose command is the attacker's script | the secret, delivered to the attacker by Coffer |

The last row matters most and is the one most designs miss: a secret does not
have to be *read* to be stolen. Coffer can be asked to **send** it somewhere
new.

**What such an agent can do anyway**, whatever Coffer does: run any command the
user can; write its own configuration (`~/.claude.json`, `~/.codex/config.toml`
— it can add an MCP server there directly when unsandboxed); read any file its
sandbox allows; read the initial environment of any same-user process.

Every vendor that shipped an "agent-safe" secret feature in 2026 settled on the
same two moves against this: **a human-presence gate the agent cannot
satisfy** — Touch ID or a password drawn by a separate signed process, as in
1Password's per-request SSH approval and Secretive's Secure Enclave keys — and
**a broker that injects the credential so the agent never holds it** —
1Password with NVIDIA OpenShell placeholders, Infisical Agent Proxy, Claude
Code's `sandbox.credentials` `mask` mode, Smithery's write-only credentials.
Every design that hands plaintext to a process — `op run`, `aws-vault exec`,
`BW_SESSION` — leaves it readable by the agent that started the process.

The browser case has CVEs in exactly this product class: Ollama
(CVE-2024-28224, DNS rebinding against the loopback API), Tailscale's LocalAPI
(TS-2022-004/005, no `Host` check), and the MCP Inspector (CVE-2025-49596, CVSS
9.4: an unauthenticated local proxy that spawned stdio commands, fixed by
`Origin` validation plus a session token). The MCP transport spec makes
`Origin` validation a MUST for every HTTP server. Coffer refuses a non-loopback
`Host` and a foreign `Origin` on every listener
([A Per-Start Token … Behind a Loopback Host Guard](daemon-auth-and-origin-guard.md)).

## Options Considered

### Option A — The boundary is the secret: plaintext only to a present human, new destinations only with a human's approval, capabilities instead of keys (chosen)

Agents keep full use of Coffer — they may read and change its configuration
through the CLI, REST and MCP, exactly as a person can — and the boundary moves
to the two things an agent cannot already do by itself: **learn a secret's
plaintext**, and **make Coffer deliver a secret somewhere it did not deliver it
before**.

1. **Plaintext reaches only a present human, in the desktop app.** Reveal,
   copy and export of any secret, and export of the master key, exist only in
   the desktop app. Each is released by its own LocalAuthentication check in
   the desktop app (Touch ID or the login password), with no reuse window: the
   next reveal asks again. The master key itself carries no presence flag
   ([The Master Key Lives in a Keychain Access Group Only Coffer's Signed Binaries Can Read](master-key-lives-in-the-macos-keychain.md)),
   so the daemon starts and restarts unattended; presence gates the
   operation, not the key. The grant is a one-time challenge bound to one
   operation (`reveal`, `approve`, `approve_batch`, `export_master_key`) and one
   target (the ref, the approval, the folder, or, for several approvals at once,
   a digest of exactly the approvals and targets the person was shown, so one
   check approves that list and nothing else), valid for two minutes and consumed by its first
   redeem whether or not the signature verifies. The desktop app runs the
   LocalAuthentication check first — a fresh context per operation, the prompt
   naming the operation and its target — and only then fetches the challenge and
   signs it with HMAC-SHA256 under a grant key that is itself an HMAC of the
   master key with a fixed label, derived when needed and never stored. The
   daemon releases the one value to the app only against a signature that
   verifies (`POST /api/v1/secrets/presence/reveal`). That keeps a single
   decryption path and gives the shell no access to the store; the protection is
   the same, because the route acts only on a grant that only a holder of the
   master key can sign. Apart from that route the daemon has **no route that
   returns plaintext** to anyone — not REST, not the CLI, not MCP; no command
   prints a value or exports the master key; the browser UI offers none of
   these actions and names the desktop app instead. Writing a secret stays open
   to every surface: a caller that supplies a value already has it.
2. **A secret goes to a new destination only with the human's approval.** A
   *destination* is a place Coffer sends a secret's plaintext: an MCP server's
   environment variable or HTTP header, a
   channel adapter's credential, the sync remote's push token, and the base URL
   of a provider connection that carries a key. The target of a provider
   connection is its base URL: the local model proxy and the internal engine
   receive a key only for an approved URL. Telegram and SeaTalk channels are the
   channel destinations wired today. Citing an existing secret from
   a destination that did not cite it before, or changing where a resource that
   already cites one sends it (the command of a stdio server, the URL of an HTTP
   server or a provider), saves the change with the binding **pending**: Coffer
   injects nothing into the new destination until the human approves it in the
   desktop app, under the same presence check. The approval is proven, not
   asserted: after the presence check passes, the desktop app signs the pending
   change with a key derived from the master key, and the daemon applies a
   binding only with a valid signature. Only Coffer's signed binaries can read
   the master key, and only the desktop app's approval path signs, so a process
   an agent controls cannot produce one. A binding whose secret value was supplied for it needs
   no approval: the destination was just registered or changed, and the ref has
   never been bound anywhere, is not a standalone `secret/` name and was written
   on this machine within the last five minutes, which is how every surface that registers a resource with a
   pasted secret behaves. That is decided inside the registration call, by one
   post-register seam every resource kind goes through, and the binding is
   recorded there, so a second destination citing the same ref is not a first
   one and waits, so the five minutes only bound how old an unused value may be and are no longer a race to the first use. A ref already in use elsewhere, or
   a target that moved, records its pending approval in the same call. Bindings
   are also evaluated at the moment of use (spawn, adapter start, push), which
   catches changes that reach the vault behind Coffer's back; a binding met only
   there is never counted as supplied. Switching the protection off waits for
   an approval the same way; writing a value does not, whether it is a new
   standalone secret or a replacement of one in use (rule 1: writing stays
   open). Rejecting needs no grant. A command whose change leaves a binding
   waiting prints "waiting for approval in the Coffer app" and exits `9`.
   Pending bindings are attention items on the Overview.
3. **Turning these protections off takes the human.** Any setting that would
   weaken rule 1 or rule 2 (`secrets.require_approval`) switches off only
   through an approval applied in the desktop app, signed the same way. No
   environment variable, config key or CLI flag does it.
4. **`Host` and `Origin` are checked on every listener.** The daemon's REST
   API, `/mcp`, the event stream, the served web UI and the model proxy all
   refuse a `Host` that is not the loopback address and port, and refuse a
   request whose `Origin` is not one of Coffer's own: the daemon's
   `http://127.0.0.1:<port>` and `http://localhost:<port>`, the desktop shell's
   `tauri://localhost` / `http://tauri.localhost`, and the Vite dev origin when
   a source checkout enables it; the model proxy, which no page has business with, refuses any
   `Origin` at all. A request with no `Origin` — the CLI, the shim, an agent —
   passes. The mechanism is the daemon-auth ADR's; this rule is the boundary's
   reliance on it. The browser UI stays: it is served from the daemon's own origin and
   lacks only the actions of rules 1–3.
5. **Agents get capabilities, not keys.** The MCP gateway injects an HTTP
   upstream's headers itself, so the agent sees tool results and never the
   token. The local model proxy injects the provider key, and the agent holds
   only its per-agent local proxy token
   ([API-Key Providers Are Reached Through a Separate Local Model Proxy](api-key-providers-are-reached-through-a-separate-local-model-proxy.md)).
   That token is kept although an agent can read it: it attributes usage per
   agent, keeps browser pages and other users' processes off the user's quota,
   and fills the key field both agents insist on. No command returns a
   provider's real key.
6. **Per-agent tokens for attribution are a SHOULD, not a MUST.** When the
   gateway and the REST API can tell which agent is calling from a token Coffer
   minted for it, audit rows, reach and usage would key on that identity instead
   of the self-reported `clientInfo.name`. It would make the trail trustworthy
   against accidents; it is not part of the boundary, because a same-user agent
   can read another agent's token. Only the model proxy has such tokens today.
7. **The processes that hold secrets cannot be inspected.** Every shipped
   binary is signed with the Developer ID under the hardened runtime, without
   `get-task-allow`, and notarised (`scripts/release_signing.sh`), so a
   same-user debugger cannot attach to the daemon, the proxy or the desktop
   app. The master key lives in a
   data-protection Keychain item in an access group limited to Coffer's Team
   ID: the signed daemon reads it silently, and any other binary — an agent's
   own program, `/usr/bin/security` — gets no access and no "Always Allow"
   dialog to click.

**What stays exposed, stated as part of the decision:**

- **A third-party stdio MCP server that takes its token from its environment.**
  The token sits in the server's initial environment, which any same-user
  process reads with `ps eww`, from inside Claude Code's sandbox too. Coffer
  cannot fix a server it did not write. The UI labels such a binding "Readable by local
  processes" and prefers an HTTP server with gateway-injected headers
  wherever the upstream offers one.
- **`coffer run` children.** A secret resolved into a child's environment is
  readable by the agent that started the child: it is the parent, and `ps eww`
  works regardless. `coffer run` stays as the accident guard it was designed as
  ([Standalone Secrets Are Named `coffer://secret/` References](standalone-secrets-are-named-references-injected-into-one-child.md)),
  labelled the same way ("Readable by local processes"). A per-secret opt-in for
  `coffer run` is the lever if this proves too wide; it is not decided here.
- **Computer-use agents.** An agent granted Accessibility or screen control can
  click an approval dialog or type a password. The presence gate holds against
  an agent with a shell, not one with the mouse.
- **The signed CLI shares the key's access group.** The `coffer` CLI could
  read the master key. That is acceptable because no CLI or REST path returns
  plaintext or the key, and the hardened runtime keeps another process from
  attaching to or injecting into Coffer's signed binaries.
- **Bypass modes.** An agent in `bypassPermissions`, `--yolo` or
  `danger-full-access` has no sandbox of its own. Nothing above depends on one;
  nothing above protects what such an agent reaches outside Coffer either.

Pros: it protects the one thing that is Coffer's to protect — the secret — on
the two paths an agent actually uses to get it: asking for it, and having it
sent. It keeps "the agent sets Coffer up for you", which the `coffer-guide`
skill and the CLI are built around. It matches what the password managers and
agent vendors converged on, and every rule is enforceable at user level on
macOS with a Developer ID. It closes the browser vector.

Cons: every reveal and every new binding costs a Touch ID; nothing sensitive
can be done from a terminal or a browser, so an SSH-only session cannot reveal
or approve anything. It requires the signed desktop app and a paid Developer
Program membership. The residual risks are real, and the UI has to say so
wherever they apply.

It wins because it is the only option whose protections hold against the
stated threat without forbidding something the agent could do without Coffer's
help.

### Option B — Token scopes as the boundary: an admin token for mutations, per-agent tokens for the gateway

Split the daemon's single token in two. An admin token, held by the UI, the
desktop shell and the `coffer` CLI, alone may change state: add or edit MCP
servers, providers, channels, settings. A token per agent reaches only the
gateway, a few read routes and its own proxy traffic. The admin token moves out
of `daemon.json`, and read-deny rules for it are written into the agents' own
configs. This is the permissions research's first MUST, modelled on LM Studio,
1Password Connect, Docker profiles and the MCP spec's warning that a proxy able
to spawn stdio servers is "a critical escalation path".

- **Pros.** Least privilege in the textbook sense; a stolen agent token cannot
  register a server; each agent has a real identity.
- **Cons.** The `coffer` CLI runs as the user, so the admin token must be
  somewhere the user's processes can read, and an agent that can run `coffer`
  holds it. The read-deny rules hold only while the agent is sandboxed, and a
  managed agent runs in bypass mode by design. More fundamentally, it guards the
  wrong thing. Registering an MCP server is running a command, which the agent
  does directly with its own shell, or by adding the server to its own config
  file, which no Coffer token governs. Denying it through Coffer protects
  nothing and breaks the supported workflow of an agent configuring Coffer for
  its user. And it does not stop the attack that matters: a mutation the admin
  token allows — "add a server that cites secret X" — is the exfiltration,
  whoever holds the token.
- **Why it loses.** It spends its whole cost on "who may change config", which
  is not a boundary against a same-user agent, and leaves "where may a secret
  go" open. Option A gates that question directly, and keeps per-agent tokens
  for what they are good at: attribution (rule 6).

### Option C — Read-deny `~/.coffer` in every agent's configuration

Write `Read(~/.coffer/**)` deny rules and `sandbox.filesystem.denyRead` into
Claude Code's config (and Codex's equivalent) wherever Coffer manages it, so a
sandboxed agent cannot read `daemon.json`, the master key file or the vault.

- **Pros.** Cheap. Both agents protect their own config directories from
  sandboxed writes, so a sandboxed agent cannot lift the rule.
- **Cons.** Agents are *meant* to read `~/.coffer`: knowledge documents and
  memory notes are files there, read with the agent's own file tools
  ([Knowledge Is a Directory of Markdown Files, Not an Index](knowledge-is-plain-files.md)).
  Once the master key is in the Keychain and the plaintext routes are gone,
  nothing under `~/.coffer` is plaintext and `daemon.json`'s token no longer
  yields a secret, so there is nothing left for the rule to protect. It does
  nothing in bypass mode.
- **Why it loses.** It would break knowledge and memory to guard files that no
  longer hold anything secret.

### Option D — Remove browser access; the desktop app is the only UI

- **Pros.** One fewer origin to trust; no served page carries the token.
- **Cons.** The user keeps the browser UI (decided 2026-09-30): it is how the UI
  is reached on a machine without the app, over a remote desktop, and during
  development. What makes the browser dangerous — rebinding and cross-site
  requests — is closed by the `Host` and `Origin` checks, which the MCP spec
  requires anyway.
- **Why it loses.** Rule 4 removes the browser's risk at a fraction of the
  cost, and rules 1–3 keep the sensitive actions out of the browser.

### Option E — Keep plaintext on the CLI and REST, audited (the design this replaced)

A `get --show` command and a REST read route return the value and record an
audit row for the read.

- **Pros.** Scriptable; works over SSH; every read leaves a trail.
- **Cons.** An audit is not a refusal: the injected agent runs the command, and
  the log records the theft afterwards.
- **Why it loses.** It is the hole this ADR exists to close.

### Option F — Presence-gated plaintext on the CLI, with a reuse window

Keep `get --show`, make it wait for Touch ID, and let one approval cover a
terminal session for a few minutes — the 1Password CLI model.

- **Pros.** Usable from a terminal; one touch per burst of work.
- **Cons.** 1Password documents that its authorisation "extends to
  subprocesses" and lasts ten minutes of inactivity: an agent started from that
  terminal, or running `op` in it after the human did, inherits the session.
  The value is also printed into a terminal the agent may be reading.
- **Why it loses.** A window is a gift to whoever acts next. No window, and no
  plaintext outside the app's own window, are what make the gate hold.

### Option G — A real OS boundary: the daemon as a separate user

Run the daemon under its own OS account so the agent cannot read its files,
attach to it or read its children's environments.

- **Pros.** It would also narrow the stdio-environment gap.
- **Cons.** An installer with privilege separation and a second home for a
  single-user tool, plus cross-user access to the user's agents' configs and
  memory. The upstream servers still have to run as the user to use the user's
  tools, which puts their environments back in reach.
- **Why it loses.** Most of its cost buys nothing the stdio case does not undo;
  the argument in [Standalone Secrets Are Named `coffer://secret/` References](standalone-secrets-are-named-references-injected-into-one-child.md)
  (its Option F) stands.

## Decision

**Agents may use and configure Coffer through every surface. Coffer's boundary
against them is the secret: its plaintext reaches only a present human, in the
desktop app, released by a presence check on each use; and it is
delivered to a destination it did not go to before only after that human
approves, with the approval signed by a key an agent cannot obtain.** Agents
use secrets through capabilities — the gateway and the model proxy inject them
— and never hold the keys. Every listener checks `Host` and `Origin`. Shipped
binaries are signed with the Developer ID under the hardened runtime.

Rules a future change must respect:

- No route, command, tool or file returns or writes a secret's plaintext or the
  master key, except the desktop app's presence-gated reveal, copy and export.
  A new path that does is a defect, however it is audited.
- Every path that makes Coffer inject a secret into a new destination goes
  through the pending-binding approval. A new destination type is added to that
  list in the change that introduces it.
- No setting that weakens either rule changes outside the desktop app's signed
  path.
- Every listener refuses a foreign `Host` and a foreign `Origin`.
- The UI labels every binding a residual risk covers — a stdio server's
  environment, a `coffer run` secret — as readable by local processes, and nothing
  describes Coffer as protecting it.

## Consequences

- The secret spec states each rule as operable behaviour: no plaintext on any
  route, command or tool, the presence-gated reveal, key backup and approval, the
  pending binding with its signed approval.
  The desktop shell gains reveal, key export and approval signing — each
  something a browser cannot do, since each needs a LocalAuthentication
  presence check ([The Desktop Shell Hosts the Shared Frontend](desktop-shell-over-a-shared-frontend.md)).
- The principles' Secrets clause carries the invariant that secret plaintext
  reaches only a present human and agents get capabilities, never keys, and
  states that Coffer holds this one narrow boundary while confining nothing an
  agent does with its own shell.
- **Costs accepted.** No reveal, export or approval over SSH or from a browser;
  a machine without the signed app can use secrets but never see one; a Touch ID
  per reveal and per new binding.
- **Development builds do not hold the boundary.** Their master key is a
  `0600` file (or the login keychain), and the shell derives the grant key from
  it, so any same-user process can forge a grant. The daemon reports
  `development: true`, the shell titles every presence prompt "Development
  build", and on a Mac without LocalAuthentication a development build falls
  back to a modal confirmation in the app window. The boundary holds only in a
  signed release ([The Master Key Lives in a Keychain Access Group](master-key-lives-in-the-macos-keychain.md)).
- The security architecture page's threat table and `SECURITY.md` state the
  residual risks listed in Option A.
- Not built yet: per-agent tokens on the gateway and the REST API (rule 6);
  attribution still uses the self-reported agent name there.
- Not built yet: any destination beyond MCP servers, channels, the sync push
  token and provider connections; a new destination type is added to the
  pending-binding list in the change that introduces it.
- Not decided: whether `coffer run` needs a per-secret opt-in.
