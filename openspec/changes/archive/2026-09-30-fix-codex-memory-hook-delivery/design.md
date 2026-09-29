## Context

Codex's hook trust lives in `config.toml` as `[hooks.state."<hooks.json path>:<event>:<group>:<handler>"]` with `enabled` and `trusted_hash`. The hash is `sha256:` plus the SHA-256 of a normalised identity serialised as sorted, compact JSON (`codex-rs/hooks/src/engine/discovery.rs` `hook_hash`, `codex-rs/config/src/fingerprint.rs` `version_for_toml`). The identity holds:

- the event's snake-case label;
- the matcher, for events that read one;
- the one handler, with `timeout` defaulted to 600, `async` to false, and unset options left out.

## Decisions

**Read trust; never write it.** The hash is fully reproducible: Coffer's implementation matches Codex 0.155.1's own `hooks/list` `currentHash` on all 12 hooks of a real `hooks.json` and on a new `SessionStart` entry with a matcher. Coffer could therefore write `trusted_hash` itself. It does not, for three reasons:

- Approval is Codex's review gate, and its docs make the user the one who reviews and trusts a hook. A tool that installs a hook and then approves it removes the only point where the user looks at it.
- The codex child spec already requires `[hooks.state.*]` to stay byte-identical across every write Coffer makes ("Leave Codex's internal-state tables untouched").
- The algorithm is internal to Codex and undocumented. If Coffer wrote a hash from a stale copy of it, Coffer would report `trusted` while Codex skipped the hook. That is exactly the "installed but never runs" failure this change fixes.

Reading the record with a stale algorithm fails the visible way instead: Coffer reports `modified` while Codex runs the hook.

Alternative considered: spawning `codex app-server` and writing through `config/value/write`, the path Codex Desktop uses. That still bypasses the user's review, and it adds a Codex process start to every reconcile pass.

**One byte ceiling for both agents.** Claude Code's limit is about 10,000 characters and Codex's is 2,500 × 4 = 10,000 UTF-8 bytes. A text's UTF-8 byte count is never smaller than its character count, so one ceiling of 9,500 bytes satisfies both and leaves margin for the agent's own wrapper. It is applied at `POST /memory/context`, the route both hooks reach. A channel turn's system-prompt append is not a hook output and keeps the token ceiling alone.

**Migration by comparison, not by version.** The reconcile target already compares whole parameters. Adding `event`, read from where the entry actually sits, turns an older build's `UserPromptSubmit` entry into a MODIFY of `command` and `event`, repaired on any pass. `install_entry` drops Coffer-marked entries from every event, so the old entry does not survive beside the new one. `trust` is also a parameter (desired `trusted`). When `trust` is the only difference, the result is a REPORT, never a write.

**`HookTrust` lives in the kind-agnostic domain.** The memory kind's adapters produce it and the agent kind's listing reports it. Neither kind may import the other, so the enum sits in `domain/hook_trust.py`, the way `domain/connection.py` holds the one string the provider and chat kinds share.

## Risks

- A Codex release that changes the hash algorithm makes a trusted hook read `modified`. The adapter's unit tests pin the hash against values Codex itself reported, so a re-check against a new Codex is one run of `hooks/list`.
- A user who never runs `/hooks` still gets nothing in Codex. The hooks listing, the Hooks tab and the attention list now all say so, with the fix, instead of `installed: true`.
