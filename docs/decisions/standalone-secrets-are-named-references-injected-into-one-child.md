# Standalone Secrets Are Named `coffer://secret/` References, Injected Only Into One Child Process

**Status**: Accepted
**Date**: 2026-10-04
**Deciders**: Yuxing Wu
**Related**: [Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md), [Resources Cite Secrets by Opaque Reference, Resolved Only at the Moment of Use](credential-references.md), [The Master Key Lives in a Keychain Access Group Only Coffer's Signed Binaries Can Read; Secrets Stay Envelope-Encrypted in the Vault](master-key-lives-in-the-macos-keychain.md), [Secrets Cross Machines Only as Ciphertext; the Master Key and the Push Token Never Enter the Repository](secrets-cross-machines-only-as-ciphertext.md), [Names Visible to Agents Are Fixed](names-visible-to-agents-are-fixed.md), [API-Key Providers Are Reached Through a Separate Local Model Proxy That Relays Bytes Unchanged](api-key-providers-are-reached-through-a-separate-local-model-proxy.md), [Managed Agents Run With Full Permissions; Owner Pairing Is the Gate](managed-agents-run-with-full-permissions.md), [A Per-Start Token, Handed to the Page by Whoever Hosts It, Behind a Loopback Host Guard](daemon-auth-and-origin-guard.md), [Audit Every Change With Its Actor, Log Every Invocation, Prune Per Table](audit-and-retention.md), [Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy](storage-is-five-classes-by-nature.md), [Sync Only Pulls and Pushes the Vault Repository; a Clean Merge Is Applied, Any Conflict Stops for the Person](sync-applies-clean-merges-and-stops-on-any-conflict.md), [Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](every-vault-write-is-a-validated-commit-naming-its-writer.md), [Platform Differences Live Behind One Platform Port; Only macOS Ships](platform-differences-live-behind-one-platform-port.md), [Per-Agent Resource Scope Is One Framework Allow-List, Enforced by Each Kind](per-agent-resource-scope.md), [principles](../../docs-site/architecture/principles.md) (Secrets), research note [credentials and secrets](../research/credentials-secrets.md), spec secret "Address a secret by an opaque reference", spec secret "Resolve standalone secrets into one child with coffer run", spec secret "List every stored and cited secret with what uses it", spec secret "Route every secret command through the daemon", spec secret "Release unshared references when a resource is deleted", spec secret "Hold plaintext only in memory at the moment of use"

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
| An agent that asks Coffer for a secret's value, through REST, the CLI or MCP | **Yes** for a secret without the local-process grant — no route returns its value and `coffer run` refuses it; in a build without the Keychain access group the agent can still read the master key file and decrypt the store itself |
| An agent that runs `coffer run --secret X -- env` for a secret a person has not granted to local programs | **Yes** — the resolve is refused, nothing starts, and the request waits in the desktop app |
| An agent that runs `coffer run --secret X -- env`, or reads the environment of the child it started, for a granted secret | **No** — the agent is the child's parent; the grant says so in the approval and on the Secrets page |

## Options Considered

### Option A — A minted id in the existing store, cited as `coffer://secret/<id>`, resolved by `coffer run` into one child (chosen)

- **Namespace, not a new store.** A standalone secret is one ciphertext file of the
  existing encrypted store under the ref `secret/<id>`, where `<id>` is 32
  lowercase hex characters minted by Coffer. It is cited from
  anywhere a person or a skill writes text as the URI `coffer://secret/<id>`:
  a `.env` value, a skill's `connection.md`, a resource config field (a
  resource may cite `secret/<id>` in its secret refs like any other ref).
- **The id is minted and fixed; the name is a note.** The id is quoted in files
  Coffer cannot see — skills, env files, scripts on other machines — which is
  exactly the condition under which
  [Names Visible to Agents Are Fixed](names-visible-to-agents-are-fixed.md)
  fixes a name, so it never changes and a person never picks it. What a person
  sees and edits is a **name** (label, at most 64 characters) and a
  **description** (at most 200), kept in one vault notes document keyed by id
  and synced with the vault, so editing them touches no ciphertext and nothing
  that cites the secret. `coffer secret set --name "<name>"` mints a secret;
  `coffer secret set <existing ref>` only replaces its value; a client cannot
  store a value under an id it chose. Rotation re-encrypts under the same id.
  This also answers the three reasons
  [Resources Cite Secrets by Opaque Reference](credential-references.md)
  retired name-derived refs: an id is never derived from a mutable name, so
  nothing moves on rename; a sync never sees a move, only an add or a delete;
  and one shape serves every secret, so there is no namespace to confuse.
- **Lifecycle independent of resources.** Deleting a resource releases a
  secret only if it was created for that resource (the notes record
  `created_for`, the uid of the resource it was minted for) and nothing else —
  no other resource, no skill file — cites it
  (`release_orphaned_secrets`, `application/resource_delete_ops.py`). Every
  other secret is kept and shows as Not used, because a standalone secret's
  citers are mostly files Coffer does not parse. Deleting a secret is refused
  with `SECRET_IN_USE` while a resource cites it, and likewise while a skill in
  the master store cites its URI, naming the skill.
- **`coffer run [--secret ID|ENV=ID]… [--env-file FILE] [--no-masking] -- cmd args…`.** The
  CLI asks the daemon to resolve every `--secret`, every `coffer://secret/`
  value in `--env-file`, and every `coffer://secret/` value already present in
  its own environment (the pattern `op run` uses). It then starts `cmd` with
  those values set **only in the child's environment**; the calling shell, the
  agent that typed the command and its other children never hold them. The bare
  `--secret <id>` form derives the variable name from the id, which is a hex
  string and rarely what a program reads, so `--secret ENV=<id>` is the useful
  form. Exit status and signals pass through.
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
- **Every use is audited.** The resolve route
  (`POST /api/v1/secrets/resolve`) answers `secret/<id>` refs only and records
  one `secret_resolved` row per secret with the id, the command's `argv[0]` and
  working directory — never the value, never the rest of argv, which may itself
  carry a secret. A use at a resource's moment of use (an MCP spawn, a channel
  start, a provider key fetch, a sync push) is audited the same way, naming
  the destination and slot. Volume is bounded by a one-minute window per
  destination and the audit log's per-table retention
  ([Audit Every Change With Its Actor](audit-and-retention.md)).
- **Every stored secret is listable, with what uses it.** `coffer secret list`
  and the Secrets page list every stored ref — cited or not — with its name,
  its description, the resources that cite it from the kinds' extractors and
  the skills in the master store whose files mention the URI (a literal search
  of Coffer's own skill store, kept in a rebuildable index). A row nothing
  references shows as Not used and is the cleanup candidate. The list carries
  no values: a value is seen only in the desktop app, under a presence check.
- **No migration of plaintext secret files.** Coffer does not scan
  `~/.coffer/secrets/` or the skill store for plaintext values and does not
  rewrite files. A person or their agent stores a value as a standalone secret
  and cites `coffer://secret/<id>`. A new standalone secret, and the
  replacement of a value already in use, are stored at once: writing stays open
  ([Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md)).

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

### Option G — A person-chosen, fixed name: `secret/<name>` (the earlier design)

A standalone secret's id was the name its author typed, fixed after creation,
cited as `coffer://secret/<name>`. `coffer run --secret NAME` derived the
variable name from it.

- **Pros.** A citation reads at a glance in a skill file or a `.env`; no
  minting step; `coffer run --secret github` was short.
- **Cons.** The name was both the label and the identity, so it could not be
  fixed and also be good. A person wrote it before they knew what the secret
  would be used for, and could not correct it: renaming meant rewriting every
  config, skill file and script that cites it, including files on other
  machines Coffer cannot see, so a rename was create-new plus delete-old and a
  typo or a vague name stayed for good. Names also leaked structure:
  `postman.AUTHORIZATION` and `team.TOKEN` shapes grew inside the namespace,
  and the Secrets page showed whatever the author typed, or a hex segment for a
  resource's own secret.
- **Why it lost.** Readable and unrenamable is the wrong trade for a value that
  outlives the labels around it. Splitting the two keeps the one property the
  fixed name bought (a citation that never goes stale) and gives the person a
  name and description they can change at any time.

## Decision

A secret that belongs to no resource is one ciphertext file of the existing
encrypted store under `secret/<uuid4 hex>`, minted by Coffer and fixed for
life, cited as `coffer://secret/<id>`. A person gives it only a name (a label of
up to 64 characters) and a description (up to 200), kept in a synced vault
notes document, so changing them touches nothing that cites the secret.
`coffer run` resolves the secrets a command names or whose references it
inherits, through the daemon, and sets them only in that one child's
environment, masking exact matches of the values in the child's output. It
resolves only a secret a person granted to local programs: a `local_process`
destination approved in the desktop app with a presence grant, never by the
build's default, the approval switch or a just-supplied value, and withdrawn
at once by a revoke that needs nobody (amended 2026-10-05: before, every
standalone secret resolved for any caller holding the daemon token, which let
an agent run its own script with any of them). Every `coffer run` resolve is
audited without the value. Every stored secret is listed
with what uses it, cited or not. Plaintext secret files are migrated into the
store and rewritten as references.

The threat model is part of the decision: this protects against secrets
landing in transcripts, git and plaintext files by accident, and — with no
route that returns a value — against an agent asking Coffer for one. It does
not protect a secret from the agent that runs the command it is resolved into:
that agent is the child's parent. That is why the grant is a person's decision
per secret: a secret an agent should only use stays without it and reaches its
service through Coffer (an MCP server or custom tool), and every granted secret
is labelled "Readable by local processes", and nothing in Coffer claims otherwise.

Rules a future change must respect:

- No code path exports a resolved secret into an agent's environment; a
  secret reaches a process only as the direct child of `coffer run` or of a
  Coffer spawn that builds the child's environment from an allow-list.
- A `coffer run` resolve that is not audited is a defect.
- A `coffer run` resolve of a secret without a person's local-process grant is
  a defect, whatever the build, the approval switch or the caller says it is.
- The masking filter is described everywhere as an accident guard, never as
  protection.
- A secret's id never changes and a person never chooses one; what a person
  can change, freely, is its name and description.
- Deleting a resource never deletes a standalone secret: a secret is released
  only when it was created for that resource and nothing else cites it.

## Consequences

- One shape serves every secret: `secret/<uuid4 hex>`, for a standalone secret
  and for the ones a resource owns alike
  ([Resources Cite Secrets by Opaque Reference](credential-references.md)).
  What differs is only who the secret was minted for, which the notes record.
- The skill-library guide cites secrets as `coffer://secret/<id>` and runs
  commands under `coffer run`, the `coffer-guide` skill teaches `coffer run`,
  and `SECURITY.md` states the threat model above.
- A one-time start-up migration moved every older standalone `secret/<name>`
  to a minted id, keeping the old name as its label and rewriting
  `coffer://secret/<name>` in the skill store's files.
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
- A resolve at a resource's moment of use (an MCP spawn, a channel start, a
  sync push, a provider key fetch) is audited too, as `secret_resolved` naming
  the destination and slot, at most once a minute per destination.
- Not built yet: a pseudo-terminal for the child; a tool that needs a real
  terminal runs with `--no-masking`.
- Not built yet: a skill's `requires.secrets` frontmatter as a source of
  citations. It is read to say when a required secret is not set, but the
  listing and the delete refusal see only skills that mention the URI.
