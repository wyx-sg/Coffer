# Provider Keys Never Land in an Agent's Native Config

**Status**: Accepted
**Date**: 2026-06-21
**Deciders**: Yuxing Wu
**Related**: [Provider Connections Projected Into Agent Config](provider-connections-projected-into-agent-config.md), [Envelope-Encrypted Credential Store](envelope-encrypted-credential-store.md), [Credential References](credential-references.md), [Resource Identity Is an Immutable uid](resource-identity-is-an-immutable-uid.md), [Daemon Auth and Origin Guard](daemon-auth-and-origin-guard.md), spec provider-switching "Resolve a key for exactly one connection", spec provider-switching "Never return the raw secret in a connection", spec provider-switching "Require a connection or a wire for the key command", spec credentials "Hold plaintext only in memory at the moment of use", [principles](../../docs-site/architecture/principles.md) (Credentials), PR #165, PR #309

## Context

[Projecting a connection](provider-connections-projected-into-agent-config.md)
means writing into `~/.claude/settings.json` and `~/.codex/config.toml`. The
path of least resistance is to put the API key there too: Claude Code reads
`env.ANTHROPIC_API_KEY` or `env.ANTHROPIC_AUTH_TOKEN` from the `env` block of its
settings file, and that is how tools such as cc-switch configure it.

Those files are not a safe place for a secret. They are plaintext under the home
directory, copied into dotfile repos and backups, read by other tools, and
restored wholesale by the user. The principles say secret plaintext exists only
in memory, between decrypt and the injection that consumes it; everything else
holds a credential reference. MCP servers already follow that rule: their
secrets are refs resolved at spawn time.

Each agent offers a different indirection:

- **Claude Code** runs the shell command in `apiKeyHelper` and uses its stdout
  as the key, re-invoking it periodically.
- **Codex** reads the key from the environment variable named by
  `[model_providers.<id>].env_key`.

The agents are started two ways: by Coffer (chat and channel turns) and by the
user in their own terminal.

## Options Considered

### Option A — Point each agent at an indirection Coffer resolves at use time (chosen)

Claude Code's projected `apiKeyHelper` is
`coffer provider key --connection-uid <uid>` (`anthropic_api_key_helper` in
`domain/provider/projection.py`). The CLI asks the daemon's
`GET /api/v1/providers/{uid}/key` (token-guarded like every route), which
decrypts that one connection's key. It answers 404, and the CLI exits 4 with
nothing on stdout, when the connection is absent, disabled, scoped to no agent
or keyless, so a stale helper fails instead of reading a key it should not.
The helper cites the uid, not the name, so renaming the connection rewrites
nothing in the agent's file.

Codex's projected provider table sets `env_key = "COFFER_PROVIDER_KEY"`. The
name lives in the kind-agnostic `domain/connection.py` (`CODEX_ENV_KEY`) so the
provider kind that writes it and the chat kind's Codex adapter that fills it
agree without importing each other. Every Codex process Coffer spawns gets the
resolved key merged into its environment (`infrastructure/chat/codex_provider.py`).
A Codex the user starts from their own shell needs `COFFER_PROVIDER_KEY`
exported there.

The key itself stays Fernet ciphertext in the credential store, under an opaque
ref minted for the connection (`provider/<uuid4>/key`). It travels between
machines only as ciphertext.

Pros: no plaintext key in any file Coffer writes; a key rotation in Coffer
reaches Claude Code on its next helper call with no file change; the same
credential-ref pattern as MCP servers; removing the connection makes the helper
fail closed. Cons: Claude Code depends on the daemon being reachable when it
fetches a key (the CLI can spawn it, per detect-or-spawn); a Codex started from
the user's shell has an extra setup step; the helper line names a Coffer command,
so uninstalling Coffer without `use-builtin` leaves Claude Code with a helper
that fails. It wins because it is the only option that keeps both files free of
plaintext while still working for agents the user starts.

### Option B — Write the key into the native file (the cc-switch shape)

Put the raw key in `env.ANTHROPIC_AUTH_TOKEN` / the Codex provider table.

Pros: works with no daemon, no helper and no shell export; the simplest thing
that runs. Cons: the key lands in plaintext in files that are backed up, synced
by dotfile tools and committed to git by accident; a rotation means rewriting
every file on every machine; it breaks the rule every other Coffer secret
follows. It loses on the credentials principle, which admits no exception.

### Option C — A local proxy that injects the key

Agents call a Coffer endpoint with a dummy key; the proxy adds the real one.

Pros: no key anywhere outside Coffer; no per-agent indirection. Cons: all the
costs of a proxy on the request path — a resident dependency for every agent
call, visibility of every prompt, added latency — which
[Provider Connections Projected Into Agent Config](provider-connections-projected-into-agent-config.md)
rejects on their own. Adopting a proxy only for key injection would pay the
whole price for a problem the agents' own indirections already solve.

### Option D — Store the key in the OS keychain and point the agents at it

Write the key to the macOS keychain (or libsecret) and let each agent read it
through a helper such as `security find-generic-password`.

Pros: an OS-grade secret store; no daemon dependency for the read. Cons: Codex
has no keychain hook, only `env_key`, so it still needs launch-time injection;
a keychain entry is a second copy of a secret Coffer already stores and must
be kept in step on rotation and sync; macOS keychain access prompts are tied to
the reading binary's signature and recur for builds signed without a Team ID,
which Coffer has already hit with its own master key. It loses on
duplication and on Codex not supporting it.

## Decision

No raw provider key is ever written into an agent's native config file.
Claude Code reads the key through an `apiKeyHelper` that names one connection
by uid and asks the daemon for it. Codex reads it from `COFFER_PROVIDER_KEY`,
which Coffer injects into every Codex process it spawns and the user exports for
their own shell. The key exists as ciphertext in the credential store and as
plaintext only in the helper's stdout or the spawned process's environment.

A future change must keep these rules:

- Projection writers never emit `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` or
  an inline Codex token (spec provider-switching "Project into Claude Code
  settings without clobbering them").
- A helper names the connection by uid. The `--wire` form resolves whichever
  connection is active for that wire, and remains only so files written before
  the uid form keep working.
- The key route answers only for a connection that currently reaches an agent.

## Consequences

- Claude Code turns fail with a clear helper error when the daemon cannot be
  reached or the connection was removed, rather than silently using a stale key.
- A user who starts Codex from a shell must export `COFFER_PROVIDER_KEY`
  themselves; Coffer cannot reach a shell it did not spawn.
- Coffer recognises its own helper by the `coffer provider key` prefix
  (`MANAGED_API_KEY_HELPER_PREFIX`), which is how de-projection and the boot
  check tell a Coffer-managed helper from one the user wrote.
