# Writing Agent-Native Config Safely

**Status**: Accepted
**Date**: 2026-09-15
**Deciders**: Yuxing Wu
**Related**: [Per-Agent Behaviour Lives in One Descriptor Record per Agent](agent-descriptor-manifest.md), [Provider Connections Projected Into Agent Config](provider-connections-projected-into-agent-config.md), [Provider Keys Never Land in an Agent's Native Config](provider-keys-never-land-in-native-config.md), [Agent Hook Installation](agent-hook-installation.md), [Aggregate Agent Memory, Never Write It](aggregate-agent-memory-never-write-it.md), [Audit and Retention](audit-and-retention.md), spec agent-registry "Address config files only by allowlisted key", spec agent-registry "Validate config-file content before saving it", spec agent-registry "Write config files atomically with a backup and an audit entry", spec agent-registry "Reject stale config-file writes by fingerprint", spec agent-registry "Degrade a facet to a parse-error state when its config file is unparseable", spec agent-registry "Uninstall a plugin by the type's own strategy", spec agent-registry/codex "Install Coffer's MCP entry into config.toml preserving its layout", spec agent-registry/codex "Never expose Codex's credential file", spec agent-registry/claude-code "Delegate Claude Code plugin uninstall to its CLI", PR #60, PR #337, PR #386

## Context

Coffer writes into files that belong to someone else: Claude Code's
`settings.json`, `settings.local.json`, `.claude.json`, `CLAUDE.md` and
`agents/*.md`, and Codex's `config.toml`, `AGENTS.md` and `hooks.json`. The
writers are the in-app and CLI config editor, the Coffer MCP install and
uninstall, adoption and removal of the agent's own MCP entries, plugin toggle
and uninstall, provider projection, and memory-delivery hook install.

Three other parties touch the same files: the user in their own editor, the
agent itself (Claude Code rewrites `.claude.json` constantly), and other tools
such as dotfile managers. A Coffer write that goes wrong destroys the user's
configuration of a tool Coffer does not own, and the user may not notice until
the agent misbehaves. So every write path needs answers to: which files may be
touched, what a write must preserve, what happens when the write fails halfway,
how a bad write is undone, and what happens when someone else changed the file
first.

## Options Considered

### Option A — Unconditional read-modify-write of whole files

Read the file, parse it, change the object, serialise it, write it back with a
plain `open(..., "w")`.

Pros: the least code. Cons: a crash mid-write truncates the user's file; a
serialiser that does not preserve layout drops TOML comments and reorders keys
the user arranged; there is no way back from a bad write; and any change the
user or the agent saved between Coffer's read and write is silently lost. It
was never shipped; it is the baseline every guard below answers.

### Option B — Layered guards on every write path (chosen)

Each write goes through the same stack, most of it in
`infrastructure/agent/config_file_store.py` (`ConfigFileStore`), which the
composition root injects into every writer:

1. **Address by key, never by path.** Files are named by an allowlist key from
   the agent's [descriptor](agent-descriptor-manifest.md);
   `domain/agent/config_files.spec_for()` raises `ConfigFileNotAllowed` (404)
   for an unknown key before any filesystem call, so a caller cannot supply a
   path. Directory entries (Claude Code's `agents/`) additionally pass
   `validate_child_relpath()` — no `..`, no absolute path, no hidden segment,
   lowercase `.md` only — and a resolved-path containment check that rejects a
   symlink pointing outside the directory. Files the agent treats as secret or
   internal are simply absent from the allowlist; Codex's `auth.json` is never
   listed, read or parsed.
2. **Validate before touching disk.** The config editor runs
   `validate_content()` — JSON and TOML must parse — and rejects malformed
   content with 422, leaving the file as it was. The structural writers parse
   the current file first, and a file that does not parse raises
   `ConfigFileFormatInvalid` or `AgentConfigParseError` instead of being
   overwritten; the affected facet shows a parse-error state until the user
   fixes the file.
3. **Change only the part Coffer owns, preserving the rest.** MCP install,
   plugin toggle and provider projection edit one entry or table. TOML goes
   through `tomlkit`, which keeps comments, ordering and unrelated keys. JSON
   keeps key order and every unrelated key, but is re-serialised with a
   two-space indent, so a JSON file's whitespace is normalised on the first
   Coffer write.
4. **Atomic replace.** The new content goes to a temp file in the same
   directory, is `fsync`ed, and replaces the target with `os.replace`. A crash
   leaves either the old file or the new one, never a truncated one.
5. **Rotating backups.** Before the replace, the existing file is copied to
   `<path>.bak`, with older copies shifted to `.bak.1` and `.bak.2`
   (`BACKUP_COPIES = 3`). Deletes of directory children back up the same way.
   A copy rather than a move, so the original stays in place until the replace
   succeeds.
6. **Audit.** Every editor write, MCP install and uninstall, plugin change and
   hook install records an audit entry with its actor.
7. **Delegate what Coffer must not write.** Where the product keeps state in a
   file it treats as internal, Coffer hands the change to the product's own
   tool: Claude Code plugin uninstall runs `claude plugin uninstall`, because
   the install inventory is Claude Code's to manage.

Pros: each guard answers one failure (arbitrary path, malformed input, lost
formatting, torn write, unrecoverable mistake, unaccountable change, corrupted
internal state), and all but the first two live in one store the writers share.
Cons: backup files accumulate beside the user's config (three per file that
Coffer has ever written); JSON reformatting is visible in a diff. It wins
because a user's agent configuration is the one thing Coffer can break that the
user did not hand to Coffer.

### Option C — Optimistic concurrency on every write

Carry a fingerprint of the content read and refuse the write if the file
changed since, on every write path.

`ConfigFileStore.fingerprint()` is the SHA-256 of the file's text (`""` for an
absent file), and `write_text_atomic(..., expected_fingerprint=...)` refuses
with `ConfigFileStale` (409) on a mismatch. Coffer applies it where a lost
update is likely, not everywhere:

- **The config editor** (REST, the in-app editor, `coffer agent config edit`)
  returns a fingerprint with each read and accepts `expected_fingerprint` on
  each write, for single files and directory children. The CLI and the in-app
  editor always send it, because they hold the file open for as long as the
  user edits. A REST call without it is applied unconditionally. The comparison
  is made in `AgentConfigFileService`, which then calls the store without the
  fingerprint.
- **Provider projection** (`application/provider/projector.py`) always passes
  the fingerprint of the text it read to the store, so a projection refuses to
  overwrite an edit the user saved in between. It also skips the write when
  the new text equals the old.
- **Every other structural writer** — Coffer MCP install and uninstall
  (`mcp_service.py`), direct MCP entry removal and adoption
  (`mcp_entry_service.py`), the MCP home migration, plugin toggle and Codex
  plugin uninstall, and memory-delivery hook install (`memory/delivery.py`) —
  reads, transforms and writes with no fingerprint.

Pros of applying it everywhere: no Coffer write could discard a concurrent
edit. Cons: a check is a read-compare-replace without a lock, so it narrows the
window rather than closing it — the agents take no lock Coffer could share, and
the check in the store and the one in the service both leave a gap between the
compare and `os.replace`; the structural writers finish in milliseconds after
their own read, so the window they leave is far smaller than an editor session
measured in minutes; and a 409 on a one-click action such as MCP install would
only make the user click again. Full coverage lost for that reason: the
fingerprint is required where a person holds a read open or where Coffer
rewrites a file the user actively edits (the provider block in
`settings.json`), and the rotating backups cover the rest.

### Option D — Own a separate file and ask the agent to include it

Write Coffer's settings into a file Coffer owns and have the agent's config
reference it, so Coffer never edits the user's file.

Pros: no concurrent-edit problem at all. Cons: neither Claude Code's settings
files nor Codex's `config.toml` has an include mechanism for the parts Coffer
needs (MCP servers, plugin flags, the model provider), so the agent would never
read the file. It lost on that platform limit.

## Decision

Every write into an agent's native config addresses the file by allowlist key,
refuses malformed input and unparseable targets, edits only the entry Coffer
owns while preserving the rest, replaces the file atomically, keeps three
rotating backups, and records an audit entry. Files the product treats as
internal are left to its own CLI. The content fingerprint is required on
config-editor writes from the CLI and the in-app editor and on every provider
projection, optional on raw REST editor writes, and absent from the other
structural writers.

## Consequences

- A bad Coffer write is recoverable from `<path>.bak`, and a run of three is
  recoverable from `.bak.1` and `.bak.2`. A fourth consecutive write drops the
  oldest copy.
- An MCP install, MCP entry change, plugin change or hook install that lands
  between the user's save and the agent's next read can overwrite that save;
  the prior content survives only in `.bak`. Extending the fingerprint to those
  writers means passing the fingerprint of the text each one already reads to
  `write_text_atomic`, as the projector does.
- Because the config-editor check runs in the service rather than in the store,
  a second writer can land between the comparison and the replace. Moving the
  comparison into the store call would put the editor on the same footing as
  the projector.
- The first Coffer write to a JSON file normalises its indentation. TOML files
  keep their layout.
- A new agent's safety depends on its allowlist builder: a file left off the
  list cannot be touched by any Coffer surface, and a file put on it can be
  edited from the UI, the CLI and REST.
