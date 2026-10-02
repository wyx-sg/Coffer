# Standalone Secrets Are Named `coffer://secret/` References, Injected Only Into One Child Process

**Status**: Accepted
**Date**: 2026-09-30
**Deciders**: Yuxing Wu
**Related**: [Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md), [Resources Cite Secrets by Opaque Reference, Resolved Only at the Moment of Use](credential-references.md), [The Master Key Lives in a Keychain Access Group Only Coffer's Signed Binaries Can Read; Secrets Stay Envelope-Encrypted in the Vault](master-key-lives-in-the-macos-keychain.md), [Secrets Cross Machines Only as Ciphertext; the Master Key and the Push Token Never Enter the Repository](secrets-cross-machines-only-as-ciphertext.md), [Names Visible to Agents Are Fixed](names-visible-to-agents-are-fixed.md), [API-Key Providers Are Reached Through a Separate Local Model Proxy That Relays Bytes Unchanged](api-key-providers-are-reached-through-a-separate-local-model-proxy.md), [Managed Agents Run With Full Permissions; Owner Pairing Is the Gate](managed-agents-run-with-full-permissions.md), [A Per-Start Token, Handed to the Page by Whoever Hosts It, Behind a Loopback Host Guard](daemon-auth-and-origin-guard.md), [Audit Every Change With Its Actor, Log Invocations Without Payloads, Prune Per Table](audit-and-retention.md), [Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy](storage-is-five-classes-by-nature.md), [Sync Only Pulls and Pushes the Vault Repository; a Clean Merge Is Applied, Any Conflict Stops for the Person](sync-applies-clean-merges-and-stops-on-any-conflict.md), [Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](every-vault-write-is-a-validated-commit-naming-its-writer.md), [Platform Differences Live Behind One Platform Port; Only macOS Ships](platform-differences-live-behind-one-platform-port.md), [Per-Agent Resource Scope Is One Framework Allow-List, Enforced by Each Kind](per-agent-resource-scope.md), [principles](../../docs-site/architecture/principles.md) (Secrets), research note [credentials and secrets](../research/credentials-secrets.md), spec secret "Address a secret by an opaque reference", spec secret "Resolve standalone secrets into one child with coffer run", spec secret "List every stored and cited secret with what uses it", spec secret "Move plaintext secret files into the store", spec secret "Route every secret command through the daemon", spec secret "Release unshared references when a resource is deleted", spec secret "Hold plaintext only in memory at the moment of use"

## Context

Secrets are cited by **resources**. A resource's config holds an opaque ref
minted for that resource (`provider/<hex>/key`, `<kind>/<hex>/<key>`), which
`SecretResolver.materialize` (`application/secret/resolver.py`) turns into a
value at an MCP spawn, a channel adapter start, a sync push or a provider key
fetch ([Resources Cite Secrets by Opaque Reference](credential-references.md)).

The secrets that are **not** a resource's need a home of their own. Skills that
call a database, an internal API or a CLI need a password or token at the
moment they run a command, and the convention a skill author would otherwise
fall back on is a plaintext file such as `~/.coffer/secrets/<name>.env` with
mode 600, because nothing else can hand a secret to a command. The store
accepts an arbitrary ref (`coffer secret set <ref>`, `POST /api/v1/secrets`),
but a ref alone solves little:

- a command a person or an agent runs has no way to resolve a ref;
- a listing that shows only refs a resource cites makes a secret stored for a
  skill invisible once stored, so the store has to enumerate what it holds;
- resolving a secret for a command is a use of the secret that belongs in the
  audit log, without the value.

Where a secret lands once it is in an environment was measured on 2026-09-29
(Claude Code 2.1.281, Codex 0.155.1, isolated config directories, fake keys):

| Path | Codex | Claude Code |
| --- | --- | --- |
| The agent's own shell tool | `shell_environment_policy` defaults to `inherit = all` and **does not filter** names containing `KEY`, `SECRET` or `TOKEN` (the filter runs only when `ignore_default_excludes = false`; the reference gives the default as `true`, as the research note records) | — |
| A stdio MCP child | an allow-list: `HOME`, `PATH`, `SHELL`, `USER`, locale, `TMPDIR`, certificate variables, plus names listed in `env_vars` / values in `env` | **the whole parent environment**, `ANTHROPIC_API_KEY` and every `*TOKEN*` included, unless `CLAUDE_CODE_MCP_ALLOWLIST_ENV=1` |

So a secret exported into an agent's environment is readable by every shell
command that agent runs (Codex) or every MCP server it spawns (Claude Code) —
and every command's output is a transcript line. Coffer's own upstream spawns
do the opposite and build the child environment from the MCP SDK's minimal
allow-list plus that server's own refs (`infrastructure/mcp/subprocess.py`),
and a provider key reaches an agent only as the agent's local model-proxy token
([API-Key Providers Are Reached Through a Separate Local Model Proxy](api-key-providers-are-reached-through-a-separate-local-model-proxy.md)).

The threat model has to be stated before the options, because it decides
them. It is set by
[Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md):
the adversary is a prompt-injected agent running as the user, and Coffer's
boundary against it is the secret itself — plaintext reaches only a present
human in the desktop app, and a secret is sent to a new destination only with
that human's approval. There is no route that returns a value, the master key
is readable only by Coffer's signed binaries
([The Master Key Lives in a Keychain Access Group Only Coffer's Signed Binaries Can Read; Secrets Stay Envelope-Encrypted in the Vault](master-key-lives-in-the-macos-keychain.md)),
and the daemon's per-start token therefore no longer buys a secret. What a
standalone secret still has to survive is the process it is handed to: a
managed agent runs with full permissions
([Managed Agents Run With Full Permissions](managed-agents-run-with-full-permissions.md)),
and the initial environment of any same-user process is readable with `ps eww`
— measured on 2026-09-30 from inside Claude Code's sandbox too.

| Threat | Protected? |
| --- | --- |
| A secret pasted into a skill file, `.env` or script that syncs to git | **Mostly** — a file holds a reference once migrated (`coffer secret scan` finds the plaintext, `import` rewrites it), and a round refuses to push a file that still holds a value; a commit itself is not scanned |
| A secret echoed into a transcript by a command that prints its config or an error | **Mostly** — the value never enters the agent's environment, and `coffer run` masks exact matches in the child's output |
| A plaintext secrets file read by any tool that walks `~/.coffer/` | **Yes**, after migration — the file holds references |
| A secret in the agent's own environment inherited by its shell or MCP children | **Yes** for secrets resolved through `coffer run` — they never enter it |
| An agent that asks Coffer for a secret's value, through REST, the CLI, MCP or the master key | **Yes** — no route returns a value, and no binary but Coffer's signed ones can read the key |
| An agent that runs `coffer run --secret X -- env`, or reads the environment of the child it started | **No** — the agent is the child's parent; the secret is labelled "Readable by local processes" and this ADR does not claim otherwise |

## Options Considered

### Option A — Named secrets in the existing store, cited as `coffer://secret/<name>`, resolved by `coffer run` into one child (chosen)

- **Namespace, not a new store.** A standalone secret is one ciphertext file of the
  existing encrypted store under the ref `secret/<name>`, where `<name>` is one
  ref segment (`[A-Za-z0-9_.-]`, at most 64 characters). It is cited from
  anywhere a person or a skill writes text as the URI `coffer://secret/<name>`:
  a `.env` value, a skill's `connection.md`, a resource config field (a
  resource may cite `secret/<name>` in its secret refs like any other ref).
- **The name is fixed after creation.** The name is quoted in files Coffer
  cannot see — skills, env files, scripts on other machines — which is exactly
  the condition under which
  [Names Visible to Agents Are Fixed](names-visible-to-agents-are-fixed.md)
  fixes a name. Renaming is create-new plus delete-old; rotation re-encrypts
  under the same name, so nothing that cites it changes. This is also what
  answers the three reasons [Resources Cite Secrets by Opaque Reference](credential-references.md)
  retired name-derived refs: a rename cannot move the secret
  because there is no rename; a standalone secret is never mistaken for a
  resource's minted ref because the two live in different namespaces; and a
  sync never sees a move, only an add or a delete.
- **Lifecycle independent of resources.** Deleting a resource releases only
  the minted refs nothing else cites; the `secret/` namespace is never released
  by `release_orphaned_secrets` (`application/resource_delete_ops.py`),
  because a standalone secret's citers are mostly files Coffer does not parse.
  Deleting a standalone secret is refused with `SECRET_IN_USE` while a resource
  cites it, and likewise while a skill in the master store cites its URI, naming
  the skill.
- **`coffer run [--secret NAME|ENV=NAME]… [--env-file FILE] [--no-masking] -- cmd args…`.** The
  CLI asks the daemon to resolve every `--secret`, every `coffer://secret/`
  value in `--env-file`, and every `coffer://secret/` value already present in
  its own environment (the pattern `op run` uses). It then starts `cmd` with
  those values set **only in the child's environment**; the calling shell, the
  agent that typed the command and its other children never hold them. `ENV`
  defaults to the name upper-cased with `-` and `.` as `_`. Exit status and
  signals pass through.
- **Output masking — accidental-leak defence only.** The child's stdout and
  stderr pass through a filter that replaces every exact occurrence of a
  resolved value with `***`, holding back a tail the length of the longest
  value so a match split across two reads is still caught. The child's output is piped
  through the filter, so a tool that needs a real terminal runs with
  `--no-masking`. Values shorter than 8 characters are not
  masked (masking a 3-character value would shred ordinary output) and `coffer
  run` says so. `--no-masking` turns it off. The filter does not see what the
  child writes to files, and does not see a transformed value (`base64`, a
  substring); that is the line between accident and intent, and the docs say
  so.
- **A `coffer run` resolve is audited.** The resolve route
  (`POST /api/v1/secrets/resolve`) answers `secret/<name>` refs only, so a
  resource's minted ref is never answerable there, and records one
  `secret_resolved` row per name with the name, the command's `argv[0]` and
  working directory — never the value, never the rest of argv, which may itself
  carry a secret. Volume is bounded by the audit log's per-table retention
  ([Audit Every Change With Its Actor](audit-and-retention.md)). A resolve at a
  resource's moment of use is not an audit row; it stamps the secret's
  last-used time, shown in the listing.
- **Every stored secret is listable, with what uses it.** `coffer secret list`
  and the Secrets page list every stored ref — cited or not — with the
  resources that cite it from the kinds' extractors and, for `secret/` names,
  the skills in the master store whose files mention the URI (a literal search
  of Coffer's own skill store). A row nothing references is the cleanup
  candidate. The list carries no values: a value is seen only in the desktop
  app, under a presence check.
- **Migration of plaintext secret files.** `coffer secret scan` reads
  `~/.coffer/secrets/*.env` (`KEY=VALUE` lines) and `*.json` (a flat map of
  strings) and every text file of the skill master store (assignments whose
  name says password, secret, token or key, and well-known token shapes),
  proposes one name per entry (`<file stem>.<key>`) and reports findings, never
  values. `coffer secret import [--id]… [--dry-run]` stores each chosen value,
  confirms the store reads back the same value, and only then rewrites the file
  with `coffer://secret/<name>` in place of the value, atomically and keeping
  its mode; it lists the skills whose files mention the old path so their
  commands can move to `coffer run --env-file`, and hands that rewrite to the
  person's agent as a prompt that carries no value. No plaintext backup is kept:
  the values are in the store, which is backed up with the vault. A new
  standalone secret, and the replacement of a value already in use, wait for an
  approval in the desktop app
  ([Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md)),
  so an import of a new name is applied once that approval is.

Pros: the secret never enters an environment the agent or its other children
can see, which is the one exposure the measurements show is automatic; one
store, one resolver, one audit trail; a skill file, an env file and a synced
vault hold only references; and the design copies a pattern users already
know (`op run`, `doppler run`, `sops exec-env`).

Cons: every command that needs a secret must be prefixed with `coffer run`;
masking changes the child's stdio (a pipe in the middle) and can surprise a
tool that checks for a real terminal; the daemon must be running to resolve
anything.

It wins because it removes the accidental paths — files, git, the agent's own
environment — without pretending to stop the agent that runs the command, and because it
is almost entirely reuse: the store, the resolver, the daemon-routed CLI and
the audit log already exist.

### Option B — Make `secret` an eighth resource kind

A secret would be a resource with a uid, a fixed name, a title and a
description; its value in the store under the resource's minted ref.

- **Pros.** It inherits listing, audit of lifecycle, `title`, the uniform
  REST and CLI verbs, and would show in the same tables as everything else.
- **Cons.** A resource document converges through the vault, so each secret
  would publish a metadata file (name, title, description) even on a remote
  that does not carry ciphertext — the name of every secret the user holds, in
  the clear. Reach and per-agent scope have no meaning for a value handed to a
  command. And the resource framework's delete cascade, rename path and
  kind-plugin hooks would all need a "not for this kind" answer.
- **Why it loses.** It buys table rows at the cost of publishing secret
  names and bending the framework; a namespace in the store gives the same
  addressability with none of that.

### Option C — Inject secrets into the agent's environment

Resolve the skill's secrets once and export them into the agent process's
environment (for a Coffer-driven turn, the way a provider key once reached
Codex), so any command the agent runs can read them.

- **Pros.** Zero change to skills: a command reading `$DB_PASSWORD` just
  works; no wrapper, no masking.
- **Cons.** The measurements are the argument: Codex's default shell policy
  passes the whole environment to every command, unfiltered, and Claude Code
  passes it to every MCP child. Every secret would be readable by every
  command and every server the agent starts, for the whole session, and one
  `env` or one verbose error prints it into the transcript. It also only works
  for turns Coffer drives, not for the agent a user runs in a terminal.
- **Why it loses.** It is the leak this ADR exists to close.

### Option D — Keep plaintext files, harden them

Leave `~/.coffer/secrets/*.env` as the convention; enforce mode `0600`, keep
the directory out of the vault's synced trees, and scan for it.

- **Pros.** No new command; skills keep working unchanged.
- **Cons.** A plaintext file is read by anything that walks the home
  directory — backup tools, dotfile managers, an agent's file search, a
  cloud-drive client — and mode bits do not stop the same user's processes,
  which is who reads it. It gives no audit trail, no rotation in one place,
  and no way for a second machine to receive the secret except by copying the
  plaintext.
- **Why it loses.** It keeps the failure and adds checks around it.

### Option E — Delegate to an external secret manager (`op://`, `bws`, Vault)

Cite `op://vault/item/field` and resolve with that tool's own `run`.

- **Pros.** The manager is audited, rotatable, and may already be trusted by
  the user; its `run` command already masks output.
- **Cons.** A hard dependency on a third-party CLI, its login session and its
  prompts at every command; nothing for a user who does not run one; and the
  skill library would need one citation form per manager. The reasons
  [Resources Cite Secrets by Opaque Reference](credential-references.md) gave
  for not delegating to an external manager apply unchanged.
- **Why it loses** as the mechanism. It stays open as a resolver: a ref is
  opaque, so a future scheme prefix could route to an external manager
  without changing any citation form this ADR introduces.

### Option F — A real boundary for `coffer run` too: a broker the agent cannot bypass

Keep every secret out of the agent's reach, including the ones a command needs:
run the daemon as a separate OS user, or never hand a command a value at all
and inject it into the command's outbound requests through a TLS-terminating
proxy with a placeholder in the environment (the pattern of Claude Code's
`sandbox.credentials` `mask` mode and 1Password with OpenShell).

- **Pros.** It would close the one row of the threat table this ADR leaves
  open.
- **Cons.** The parts of this that hold at user level are adopted elsewhere:
  no route returns a value and only Coffer's signed binaries can read the master key
  ([Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md)).
  What remains costs far more than it buys here. A separate OS user means an
  installer, privilege separation and a second home for a single-user tool,
  and the command still runs as the user. A placeholder proxy needs a local CA
  every client must trust (`NODE_EXTRA_CA_CERTS`, `SSL_CERT_FILE`), fails
  against SDKs that validate a token's format (OpenShell #894), is bypassed by
  an `HTTPS_PROXY` override, and cannot serve the database passwords and
  non-HTTP protocols most skills need a secret for.
- **Why it loses** for `coffer run`. The command a person or an agent runs is
  the agent's own child; handing it a value is handing the agent the value, and
  the design says so instead of pretending otherwise.

## Decision

A secret that belongs to no resource is one ciphertext file of the existing
encrypted store under `secret/<name>`, cited as `coffer://secret/<name>`, and
its name cannot change after creation. `coffer run` resolves the secrets a
command names or whose references it inherits, through the daemon, and sets
them only in that one child's environment, masking exact matches of the values
in the child's output. Every `coffer run` resolve is audited without the value.
Every stored secret is listed with what uses it, cited or not. Plaintext secret
files are migrated into the store and rewritten as references.

The threat model is part of the decision: this protects against secrets
landing in transcripts, git and plaintext files by accident, and — with no
route that returns a value — against an agent asking Coffer for one. It does
not protect a secret from the agent that runs the command it is resolved into:
that agent is the child's parent. Every secret usable through `coffer run` is
labelled "Readable by local processes", and nothing in Coffer claims otherwise.

Rules a future change must respect:

- No code path exports a resolved secret into an agent's environment; a
  secret reaches a process only as the direct child of `coffer run` or of a
  Coffer spawn that builds the child's environment from an allow-list.
- A `coffer run` resolve that is not audited is a defect.
- The masking filter is described everywhere as an accident guard, never as
  protection.
- The `secret/` namespace is never released by a resource deletion.

## Consequences

- Minted opaque refs remain the rule for resource-owned secrets
  ([Resources Cite Secrets by Opaque Reference](credential-references.md));
  this adds a second, named namespace for secrets owned by people and skills.
- The skill-library guide cites secrets as `coffer://secret/<name>` and runs
  commands under `coffer run`, the `coffer-guide` skill teaches `coffer run`,
  and `SECURITY.md` states the threat model above.
- The provider key Coffer once injected into the Codex process it drives is
  gone: the local model proxy hands an agent only its local proxy token
  ([API-Key Providers Are Reached Through a Separate Local Model Proxy](api-key-providers-are-reached-through-a-separate-local-model-proxy.md)).
- Not built yet: a gitleaks scan of the staged diff before every vault commit,
  with the scanner shipped beside the frozen binaries. What exists is narrower:
  before a sync round pushes, it reads every file version the push would publish
  with the detection `coffer secret scan` uses and pushes nothing while one
  still holds a value (spec vault-sync "Refuse to push a plaintext secret"). A
  secret typed into a skill file after the migration therefore reaches local
  history, and is stopped at the remote.
- Not built yet: an audit row for a resolve at a resource's moment of use (an
  MCP spawn, a channel start, a sync push, a provider key fetch); only
  `coffer run`'s resolves are audited, and the others stamp last-used time.
- Not built yet: a pseudo-terminal for the child; a tool that needs a real
  terminal runs with `--no-masking`.
- Not built yet: a skill's `requires.secrets` frontmatter as a source of
  citations. It is read to say when a required secret is not set, but the
  listing and the delete refusal see only skills that mention the URI.
