# Standalone Secrets Are Named `coffer://secret/` References, Injected Only Into One Child Process

**Status**: Proposed
**Date**: 2026-09-30
**Deciders**: Yuxing Wu
**Related**: [Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md), [Resources Cite Secrets by Opaque Reference, Resolved Only at the Moment of Use](credential-references.md), [Envelope-Encrypted Credential Store](envelope-encrypted-credential-store.md), [Credentials Cross Machines Only as Ciphertext; the Master Key and the Push Token Never Enter the Repository](credentials-across-machines.md), [Names Visible to Agents Are Fixed](names-visible-to-agents-are-fixed.md), [Provider Keys Never Land in an Agent's Native Config](provider-keys-never-land-in-native-config.md), [Managed Agents Run With Full Permissions; Owner Pairing Is the Gate](managed-agents-run-with-full-permissions.md), [A Per-Start Token, Handed to the Page by Whoever Hosts It, Behind a Loopback Host Guard](daemon-auth-and-origin-guard.md), [Audit Every Change With Its Actor, Log Invocations Without Payloads, Prune Per Table](audit-and-retention.md), [Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy](storage-is-five-classes-by-nature.md), [The Master Key Lives in a Keychain Access Group Only Coffer's Signed Binaries Can Read; Secrets Stay Envelope-Encrypted in the Vault](master-key-lives-in-the-macos-keychain.md), [Sync Only Pulls and Pushes the Vault Repository; a Clean Merge Is Applied, Any Conflict Stops for the Person](sync-applies-clean-merges-and-stops-on-any-conflict.md), [Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](every-vault-write-is-a-validated-commit-naming-its-writer.md), [Platform Differences Live Behind One Platform Port; Only macOS Ships](platform-differences-live-behind-one-platform-port.md), [Per-Agent Resource Scope Is One Framework Allow-List, Enforced by Each Kind](per-agent-resource-scope.md), [principles](../../docs-site/architecture/principles.md) (Credentials; "Not a firewall or security boundary"; an amendment to both is proposed separately), research note [credentials and secrets](../research/credentials-secrets.md), spec secret "Address a secret by an opaque reference", spec secret "Resolve standalone secrets into one child with coffer run", spec secret "List every stored and cited secret with what uses it", spec secret "Move plaintext secret files into the store", spec secret "Route every secret command through the daemon", spec secret "Release unshared references when a resource is deleted", spec secret "Hold plaintext only in memory at the moment of use"

## Context

The credential store was built for **resources**. Every secret in it today is
cited by a resource's config through an opaque ref minted for that resource
(`provider/<hex>/key`, `<kind>/<hex>/<key>`), resolved by
`CredentialResolver.materialize` (`application/secret/resolver.py:34`) at
an MCP spawn, a channel adapter start, a sync push or a provider key fetch
([Resources Cite Secrets by Opaque Reference](credential-references.md)).

The secrets that are **not** a resource's have nowhere to go. Skills that
call a database, an internal API or a CLI need a password or token at the
moment they run a command, and the convention the repository documents for
them is a plaintext file: `docs-site/guides/writing-skill-libraries.md:159`
says credentials live "in a credential store or a file such as
`~/.coffer/secrets/<name>.env` with mode 600". In practice that file is the
only option a skill author has, because nothing in Coffer can hand a secret to
a command. The store already accepts an arbitrary ref
(`coffer credentials set <ref>`, `POST /api/v1/credentials`), but:

- nothing resolves a ref for a command a person or an agent runs;
- `coffer credentials list` and `GET /api/v1/credentials` (`list_cited_refs`,
  `surfaces/http/secret_routes.py:76`) list only refs a resource cites, so a
  secret stored for a skill is invisible once stored. The store itself can
  only `count()` rows (`infrastructure/secret/encrypted_store.py:95`); the
  one enumeration, `list_refs`, lives in the sync adapter
  (`infrastructure/sync/secret.py:94`);
- resolution at use is not audited: `materialize` records nothing, and neither
  does the provider key route (`surfaces/http/provider_routes.py:131`). Only a
  deliberate read (`GET /api/v1/credentials/{ref}`, `get --show`) is audited as
  `credential_read` (`credential_routes.py:139-150`).

Where a secret lands once it is in an environment was measured on 2026-09-29
(Claude Code 2.1.281, Codex 0.155.1, isolated config directories, fake keys):

| Path | Codex | Claude Code |
| --- | --- | --- |
| The agent's own shell tool | `shell_environment_policy` defaults to `inherit = all` and **does not filter** names containing `KEY`, `SECRET` or `TOKEN` (the filter runs only when `ignore_default_excludes = false`; the reference gives the default as `true`, as the research note records) | — |
| A stdio MCP child | an allow-list: `HOME`, `PATH`, `SHELL`, `USER`, locale, `TMPDIR`, certificate variables, plus names listed in `env_vars` / values in `env` | **the whole parent environment**, `ANTHROPIC_API_KEY` and every `*TOKEN*` included, unless `CLAUDE_CODE_MCP_ALLOWLIST_ENV=1` |

So a secret exported into an agent's environment is readable by every shell
command that agent runs (Codex) or every MCP server it spawns (Claude Code) —
and every command's output is a transcript line. Coffer already puts one
there: its chat provider merges `COFFER_PROVIDER_KEY` into the environment of
the Codex process it drives (`infrastructure/chat/codex_provider.py:143-155`),
which Codex's default shell policy then passes on. Coffer's own upstream
spawns do the opposite and build the child environment from the MCP SDK's
minimal allow-list plus that server's own refs
(`infrastructure/mcp/subprocess.py:101-110`).

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
| A secret pasted into a skill file, `.env` or script that syncs to git | **Yes** — the file holds a reference; every vault commit is scanned |
| A secret echoed into a transcript by a command that prints its config or an error | **Mostly** — the value never enters the agent's environment, and `coffer run` masks exact matches in the child's output |
| A plaintext secrets file read by any tool that walks `~/.coffer/` | **Yes**, after migration — the file holds references |
| A secret in the agent's own environment inherited by its shell or MCP children | **Yes** for secrets resolved through `coffer run` — they never enter it |
| An agent that asks Coffer for a secret's value, through REST, the CLI, MCP or the master key | **Yes** — no route returns a value, and no binary but Coffer's signed ones can read the key |
| An agent that runs `coffer run --secret X -- env`, or reads the environment of the child it started | **No** — the agent is the child's parent; the secret is labelled "readable by local agents" and this ADR does not claim otherwise |

## Options Considered

### Option A — Named secrets in the existing store, cited as `coffer://secret/<name>`, resolved by `coffer run` into one child (chosen)

- **Namespace, not a new store.** A standalone secret is a row of the
  existing encrypted store under the ref `secret/<name>`, where `<name>` is one
  ref segment (`[A-Za-z0-9_.-]`, at most 64 characters). It is cited from
  anywhere a person or a skill writes text as the URI `coffer://secret/<name>`:
  a `.env` value, a skill's `connection.md`, a resource config field (a
  resource may cite `secret/<name>` in `credential_refs` like any other ref).
  Refs already stored under `secret/` are adopted as standalone secrets.
- **The name is fixed after creation.** The name is quoted in files Coffer
  cannot see — skills, env files, scripts on other machines — which is exactly
  the condition under which
  [Names Visible to Agents Are Fixed](names-visible-to-agents-are-fixed.md)
  fixes a name. Renaming is create-new plus delete-old; rotation re-encrypts
  under the same name, so nothing that cites it changes. This is also what
  answers the three reasons [Credential References](credential-references.md)
  retired name-derived refs (its Option F): a rename cannot move the secret
  because there is no rename; a standalone secret is never mistaken for a
  resource's minted ref because the two live in different namespaces; and a
  sync never sees a move, only an add or a delete.
- **Lifecycle independent of resources.** Deleting a resource releases only
  the minted refs nothing else cites; the `secret/` namespace is never released
  by `release_orphaned_credentials` (`application/resource_delete_ops.py:25`),
  because a standalone secret's citers are mostly files Coffer does not parse.
  Deleting a standalone secret is refused while a resource cites it, as today,
  and warned about while a skill in the master store mentions its URI.
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
  value so a match split across two reads is still caught. When Coffer's own
  stdout is a terminal the child runs on a pseudo-terminal (through the
  processes port of
  [Platform Differences Live Behind One Platform Port](platform-differences-live-behind-one-platform-port.md)),
  so interactive tools keep behaving. Values shorter than 8 characters are not
  masked (masking a 3-character value would shred ordinary output) and `coffer
  run` says so. `--no-masking` turns it off. The filter does not see what the
  child writes to files, and does not see a transformed value (`base64`, a
  substring); that is the line between accident and intent, and the docs say
  so.
- **Every resolve is audited.** A resolve through `coffer run` records
  `secret_resolved` with the name, the command's `argv[0]` and working
  directory — never the value, never the rest of argv, which may itself carry a
  secret. The resolver behind resource use records `credential_resolved` with
  the ref and the consumer (`mcp_spawn`, `channel_start`, `sync_push`,
  `provider_key`). Volume is bounded by the audit log's per-table retention
  ([Audit Every Change With Its Actor](audit-and-retention.md)).
- **Every stored secret is listable, with its reference count.** The store
  gains an enumeration; `coffer credentials list` and the Security page list
  every stored ref — cited or not — with `cited_by` from the kinds' extractors
  and, for `secret/` names, the skills in the master store whose files mention
  the URI (a literal search of Coffer's own skill store, and later the
  `requires.secrets` frontmatter). A row with zero citers is the cleanup
  candidate the product cannot show today. The list carries no values: a
  value is seen only in the desktop app, under a presence check, and
  `coffer credentials get --show` is removed.
- **A secret scanner gates every commit into the vault.** The vault is a
  git repository that records every accepted write as a commit
  ([Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](every-vault-write-is-a-validated-commit-naming-its-writer.md)),
  and a sync round publishes those commits. So the scan runs where a secret
  would first become durable history, not only where it would leave the
  machine: before any commit, the staged diff is scanned with gitleaks. A
  finding refuses that commit, names the path and the rule — never the
  matched text — and leaves the file uncommitted and flagged, exactly as a
  file that fails validation is left; a round cannot publish what was never
  committed. Ciphertext paths are exempt from the scan (a Fernet token is
  high-entropy by design). The scanner ships beside the other frozen
  binaries, and a missing scanner refuses the commit rather than skipping the
  gate. It is the same tool the repository's own CI runs over its full
  history (`.github/workflows/verify.yml:161`).
- **Migration of plaintext secret files.** `coffer credentials scan` reads
  `~/.coffer/secrets/*.env` (`KEY=VALUE` lines) and `*.json` (a flat map of
  strings), proposes one name per entry (`<file stem>.<key>`), and
  `coffer credentials import`, on
  confirmation stores each value — the daemon decrypts what it stored and
  compares it with what it received in the same call, returning only whether
  they match — rewrites the file with `coffer://secret/<name>` in place of each value,
  and lists the skills in the master store whose files mention the old path so
  their commands can move to `coffer run --env-file`. No plaintext backup is
  kept: the values are in the store, which is backed up with the vault. A
  `--dry-run` prints the plan and writes nothing.

Pros: the secret never enters an environment the agent or its other children
can see, which is the one exposure the measurements show is automatic; one
store, one resolver, one audit trail; a skill file, an env file and a synced
vault hold only references; and the design copies a pattern users already
know (`op run`, `doppler run`, `sops exec-env`).

Cons: every command that needs a secret must be prefixed with `coffer run`;
masking changes the child's stdio (a pipe or pty in the middle) and can
surprise a tool that checks for a real terminal; the daemon must be running
to resolve anything; a gitleaks false positive leaves a file uncommitted until
the user changes it or adds an allow rule.

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
environment (for a Coffer-driven turn, the way `COFFER_PROVIDER_KEY` reaches
Codex today), so any command the agent runs can read them.

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
  [Credential References](credential-references.md) gave for not building its
  Option D apply unchanged.
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

A secret that belongs to no resource is a row of the existing encrypted store
under `secret/<name>`, cited as `coffer://secret/<name>`, and its name cannot
change after creation. `coffer run` resolves the secrets a command names or
whose references it inherits, through the daemon, and sets them only in that
one child's environment, masking exact matches of the values in the child's
output. Every resolve — through `coffer run` or at a resource's moment of use —
is audited without the value. Every stored secret is listed with its reference
count, cited or not. Every commit into the vault is scanned for secrets
before it exists, so none reaches local history or the remote.
Plaintext secret files are migrated into the store and rewritten as
references.

The threat model is part of the decision: this protects against secrets
landing in transcripts, git and plaintext files by accident, and — with no
route that returns a value — against an agent asking Coffer for one. It does
not protect a secret from the agent that runs the command it is resolved into:
that agent is the child's parent. Every secret usable through `coffer run` is
labelled "readable by local agents", and nothing in Coffer claims otherwise.

Rules a future change must respect:

- No code path exports a resolved secret into an agent's environment; a
  secret reaches a process only as the direct child of `coffer run` or of a
  Coffer spawn that builds the child's environment from an allow-list.
- A resolve that is not audited is a defect, whatever the consumer.
- The masking filter is described everywhere as an accident guard, never as
  protection.
- The `secret/` namespace is never released by a resource deletion.

## Consequences

- **Extends** [Resources Cite Secrets by Opaque Reference](credential-references.md):
  minted opaque refs remain the rule for resource-owned secrets; this adds a
  second, named namespace for secrets owned by people and skills, and extends
  its audit rule from deliberate reads to every resolve.
- The skill-library guide's plaintext-file advice
  (`docs-site/guides/writing-skill-libraries.md:159`) is rewritten to
  `coffer://secret/` plus `coffer run`; the `coffer-guide` skill learns
  `coffer run`; `SECURITY.md` states the threat model above.
- The `COFFER_PROVIDER_KEY` Coffer injected into the Codex process it drives
  is excluded from Codex's shell commands (PR #464), and goes away with the
  local model proxy, which hands an agent only its local proxy token
  ([API-Key Providers Are Reached Through a Separate Local Model Proxy](api-key-providers-are-reached-through-a-separate-local-model-proxy.md)).
- **Obligations.** Spec deltas in credentials (the namespace, `coffer run`,
  audit on resolve, listing every stored ref) and vault-sync (the scan before
  every vault commit); a store enumeration method in `infrastructure/secret/`; the
  gitleaks binary in the distribution; tests for masking across a chunk
  boundary, for a value never appearing in the parent's environment, and for
  a commit refusing when the scanner is missing.

## Implementation notes (2026-09-30)

What shipped with the change that built the secret boundary (OpenSpec change
`add-secret-boundary`), where it differs from the text above, and what is not
built yet:

- **Spellings.** The command is `coffer run [--secret NAME|ENV=NAME]…
  [--env-file FILE] [--no-masking] -- cmd args…`: the variable comes first in
  `ENV=NAME`, as in an env file. The migration is two commands of the
  existing group, `coffer credentials scan` (report findings, never values) and
  `coffer credentials import [--id]… [--dry-run]`, rather than a new
  `coffer secret` group. The scan also reads every text file of the skill
  master store (assignments whose name says password, secret, token or key,
  and well-known token shapes), not only `~/.coffer/secrets/`.
- **The resolve route answers standalone names only.** `coffer run` asks
  `POST /api/v1/credentials/secrets/resolve`, which returns values for
  `secret/<name>` refs and refuses everything else, so a resource's minted ref
  is never answerable there. It records one `secret_resolved` row per name.
- **Deleting a cited standalone secret is refused**, not warned about, while a
  skill in the master store cites its URI (`CREDENTIAL_IN_USE`, naming the
  skill), as it is while a resource cites it.
- **Replacing a standalone secret's value** waits for an approval in the
  desktop app, as replacing any value in use does
  ([Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md)).
- **Not built yet:**
  - the gitleaks scan before every vault commit, and shipping the scanner with
    the frozen binaries;
  - the pseudo-terminal: the child's output is piped through the masking filter,
    and a tool that needs a real terminal is run with `--no-masking`;
  - `credential_resolved` audit rows for resolves at a resource's moment of use
    (`mcp_spawn`, `channel_start`, `sync_push`, `provider_key`); only
    `coffer run`'s resolves are audited today;
  - the `requires.secrets` frontmatter as a second source of skill citations.
