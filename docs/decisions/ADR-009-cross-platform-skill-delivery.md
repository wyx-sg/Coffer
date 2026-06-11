# ADR-009: Cross-Platform Skill Delivery — Symlink / Junction / Copy-Fallback

**Status**: Accepted
**Date**: 2026-05-29
**Deciders**: Yuxing Wu
**Related**: spec `005-skill-manager` (FR-009, FR-012, SC-007), spec `004-agent-registry` (`AgentConfig.skill_dir`), [ADR-007](ADR-007-everything-is-a-resource-kind.md)

## Context

Spec `005-skill-manager` introduces a canonical store at
`~/.coffer/skills/<name>/` and requires each registered agent's skill
directory to "see" the managed skills under its own normal layout — i.e.
`~/.claude/skills/<name>/`, `~/.cursor/skills/<name>/`, etc. The store must
be the **single editable source of truth** (FR-003) while every agent reads
through its own pre-existing path conventions.

Three obvious mechanisms were on the table:

1. **Copy** the master folder into each agent's skill dir.
2. **Configuration pointer**: tell each agent "your skill dir is now
   `~/.coffer/skills/`".
3. **Directory link**: place a directory symlink (POSIX) / junction
   (Windows) at the agent path pointing back to the master.

Copy creates immediate drift: a user edit inside one agent's skill dir does
not propagate, every update must touch N agents, and `verify` becomes a
content-diff rather than a structural check. Configuration pointer is
rejected because most agents (Claude Code, Cursor, Claude Desktop) hard-code
their skill directory; even the ones that allow overriding store it in a
client-private config we cannot reliably touch.

Directory links work everywhere we ship except for filesystems that don't
support them. The remaining decision is **which kind of link on which OS,
and what to do when neither is available** — Windows FAT32 partitions,
some Windows network shares, and a handful of legacy NAS targets can
reject both `os.symlink` (WinError 1314: privilege not held) and
`mklink /J` (junctions disallowed on the target filesystem).

## Decision

**A single `SyncEngine` in `infrastructure/skill/sync_engine.py` makes one
attempt per platform and falls back to a content copy when the link
cannot be created. The link mode used for each binding is persisted to the
DB so the UI can surface degraded bindings.**

Concrete behaviour, per OS:

- **POSIX (macOS, Linux)**: `os.symlink(master, link, target_is_directory=True)`.
  Records `link_mode = symlink`. No fallback is expected to be needed.
- **Windows**: try `os.symlink(...)` first — this succeeds when the user has
  Developer Mode enabled or `SeCreateSymbolicLinkPrivilege`. On
  `OSError(WinError 1314)` (or equivalent), fall back to
  `subprocess.run(["cmd", "/c", "mklink", "/J", link, master])` to create a
  directory **junction**. Records `link_mode = symlink` or
  `link_mode = junction` accordingly. Junctions work without privilege
  elevation on NTFS for any local volume.
- **Any OS, when both fail** (FAT32, certain network shares, locked-down
  CI runners): copy the master folder content into the agent target with
  `shutil.copytree(...)`. Records `link_mode = copy_fallback` and emits an
  audit event with `degraded=true`. The UI surfaces a warning on degraded
  bindings; `verify` treats these as a separate drift category because
  edits to the agent-side copy will not propagate.

The mode is determined per binding (not per OS) because a single user
machine can mix filesystems (e.g. NTFS C: drive plus a SMB-mounted skill
dir). `SyncEngine.classify_target` re-reads the on-disk shape on `verify`
and is the basis for drift categorisation — see
`specs/005-skill-manager/data-model.md` `DriftKind` table.

Removal mirrors creation: `SyncEngine.remove_directory_link` inspects the
on-disk type before removing (`os.unlink` for symlinks, `os.rmdir` for
junctions, `shutil.rmtree` for copy-fallback). This avoids the classic
Windows footgun where `shutil.rmtree` on a junction recursively deletes
the master.

## Consequences

**Positive**

- One canonical master folder, edits everywhere stay in sync — the core
  product promise.
- No per-OS branching in the application layer: `SkillService` calls a
  single port; the `SyncEngine` adapter encapsulates all platform-specific
  behaviour.
- Degraded bindings are observable: `link_mode = copy_fallback` shows up
  in `SkillBindingOut`, in the desktop UI, and in audit events. The user
  knows their FAT32 share is not getting live updates.
- The copy fallback keeps Coffer usable on filesystems where neither
  symlinks nor junctions work, instead of failing outright (which would
  leave those users with no path forward in v1).

**Negative**

- The copy fallback is silently inferior: edits made through the agent's
  view of the skill do **not** land in master. This is mitigated by (a)
  the audit `degraded=true` flag, (b) the UI warning, and (c) `verify`
  reporting these bindings on every run. We do not auto-promote a
  copy-fallback to a real link when the filesystem regains support
  (v0.6+).
- Windows users without Developer Mode get junctions, which behave
  slightly differently from symlinks for tools that resolve targets
  explicitly. So far no agent we ship for treats this as an issue, but
  the divergence is real.
- Three removal code paths multiply the surface area where "delete the
  user's master folder by accident" is possible. Mitigated by a unit-test
  matrix in `tests/infrastructure/skill/test_sync_engine.py` covering
  every (create, remove) × (symlink, junction, copy_fallback) cell on
  both POSIX and a mocked Windows shim.

## Alternatives Considered

**Copy-only (no links).** Rejected.

- Forces a content-sync engine for every update on every agent; turns
  what should be a metadata change into N filesystem walks.
- Breaks the "edit master, see everywhere" workflow that justifies a
  central store in the first place.

**Configuration-pointer (rewrite each agent's `skillsPath` setting).**
Rejected.

- Most agents we target store their skill path in a private config that
  is not stable across versions; touching it is brittle.
- Some agents do not allow overriding the path at all.
- Even when feasible, mutating a third-party tool's config is a
  trust-boundary violation we explicitly avoid in the constitution.

**Hard links instead of symlinks/junctions.** Rejected.

- Hard links to directories are not supported on the filesystems we
  target (NTFS, APFS, ext4).
- File-level hard links would force per-file bookkeeping for every file
  inside a skill folder, ballooning binding state and breaking on adds /
  removes within an updated skill.

**libgit2 / Tauri filesystem APIs for cross-platform link creation.**
Considered, deferred.

- Adding `libgit2` or a Rust shim would buy uniform error reporting but
  pulls a native dependency into the backend that the rest of Coffer
  does not need. `os.symlink` + `cmd /c mklink /J` is a well-trodden
  pairing and keeps the dependency footprint minimal.
- Revisit if Windows junction edge cases force us to embed a richer
  filesystem helper.
