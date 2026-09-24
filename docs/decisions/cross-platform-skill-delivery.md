# Skills Reach an Agent as a Directory Link to One Master Folder

**Status**: Accepted
**Date**: 2026-05-29
**Deciders**: Yuxing Wu
**Related**: spec skill-manager; spec agent-registry; [Coffer Ships Its Own Manual as a Skill Resource](coffer-ships-its-own-skill.md); [Per-Agent Resource Scope](per-agent-resource-scope.md); [Resource Reach Is Machine-Local](resource-reach-is-machine-local.md); [Writing Agent-Native Config Safely](writing-agent-native-config-safely.md); research note [agent skills](../research/agent-skills.md)

## Context

Coffer keeps one master folder per skill under `~/.coffer/skills/<name>/`, and
that folder is the single editable copy (spec skill-manager "Keep one master
folder per skill and carry it through a rename"). Each registered agent must
nevertheless see the skill in its own skills directory, under its own layout:
`AgentConfig.resolved_skill_dir()` is `<config_dir>/skills` for both Claude
Code and Codex (`backend/coffer/domain/agent/config.py`), so a skill named
`foo` must appear at `~/.claude/skills/foo/` and `~/.codex/skills/foo/`.

The master has more than one writer: Coffer's in-app editor, and the person's
own editor — directly, or through any agent's view of the skill. Whatever puts
the skill in the agent's directory must make an edit made through one path
visible through all of them.

Neither agent lets Coffer change where it looks for skills: the path is
fixed by the agent, and where an override exists it lives in a private config
that is not stable across versions. And the agent's skills directory is shared
territory — the person and other tools put skills there too.

## Options Considered

### Option A — A directory link per agent, with a copy only where Windows can make no link (chosen)

Place a directory symlink at the agent path pointing at the master. On Windows,
try a symlink first (it succeeds with Developer Mode or
`SeCreateSymbolicLinkPrivilege`), then a directory junction via
`cmd /c mklink /J` (no elevation needed on local NTFS), and only when both fail
— FAT32, some network shares — copy the master with `shutil.copytree`. The mode
used is recorded per binding.

- **Pros.** One copy of the bytes; an edit anywhere is an edit everywhere.
  Delivery is a metadata operation, not a content sync. Drift is a structural
  check: is the link there, and does it point at the master? The copy fallback
  keeps Coffer usable on filesystems with no reparse points instead of failing.
- **Cons.** Three link shapes mean three removal paths, one of which —
  `rmtree` — could destroy a master or a person's files if applied to the wrong
  shape. A copy is silently inferior: edits through that agent's view do not
  reach the master. Junctions differ subtly from symlinks for tools that
  resolve targets explicitly; no supported agent has been affected.
- **Why it wins.** It is the only option that keeps one editable copy while
  every agent reads through its own unchanged path.

### Option B — Copy the master into every agent

- **Pros.** Works on every filesystem; no link semantics to reason about.
- **Cons.** Immediate drift: an edit in one agent's copy does not propagate,
  every update touches N directories, and drift detection becomes a content
  diff. It breaks the "edit master, see everywhere" promise that justifies a
  central store.
- **Why it lost.** It is kept only as the Windows last resort, where it is
  recorded, marked and never mistaken for a link.

### Option C — Point each agent's configuration at `~/.coffer/skills/`

- **Pros.** No per-skill filesystem objects at all.
- **Cons.** Both agents fix their skills path; where an override exists it
  lives in a private config that moves between versions. It would also hand the
  agent every skill in the store, defeating per-skill `enabled` and scope, and
  hide the skills the person put in the agent's own directory.
- **Why it lost.** Not available, and it would remove per-skill delivery.

### Option D — Hard links

- **Pros.** Transparent to every reader.
- **Cons.** Directory hard links are not supported on APFS, NTFS or ext4.
  File-level hard links need per-file bookkeeping and break when a skill gains
  or loses a file.
- **Why it lost.** Not available for directories.

### Option E — A native filesystem helper for link creation

- **Pros.** Uniform error reporting across platforms.
- **Cons.** A native dependency the rest of the backend does not need, for a
  job `os.symlink` plus `mklink /J` already does.
- **Why it lost.** Cost without a measured problem to justify it.

## Decision

**A skill reaches an agent as a directory link from the agent's skills
directory to the skill's one master folder. A copy is made only on Windows when
neither a symlink nor a junction can be created, and is recorded as such. What
decides delivery, and what Coffer does when the target is not its own, is part
of the same rule.**

- **The link.** `backend/coffer/infrastructure/skill/sync_engine.py` makes one
  attempt per platform. POSIX: `os.symlink` → `link_mode = symlink`, with no
  fallback. Windows: symlink, else junction, else copy → `symlink`, `junction`
  or `copy_fallback`. The mode is decided per binding, not per OS, because one
  machine can mix filesystems, and it is recorded in the binding row (one row
  per delivered `(skill, agent)` in `skill_agent_bindings`) and in the
  `skill_bound` audit event.
- **Removal inspects before it removes.** A symlink is unlinked; a Windows
  junction is `rmdir`'d, which removes the link and not the target; a real
  directory is deleted only when the binding recorded it as `copy_fallback`. A
  real directory under any other mode is a person's content that replaced
  Coffer's link, and is never deleted — this is what prevents the classic
  Windows footgun of `rmtree` through a junction into the master.
- **One predicate decides delivery.** A skill is delivered to an agent exactly
  when `skill.enabled and is_active(skill.scope, agent.uid)`, and the agent is
  enabled (`application/skill/delivery_ops.py`). There is no per-`(skill,
  agent)` switch. Both inputs are machine-local reach. Delivery is reconciled
  per agent on every trigger that can change the answer.
- **Report, never overwrite.** A target that holds something Coffer did not
  put there is reported as a conflict and left byte-identical; the link helper
  refuses to create over an existing path.
- **Boot repairs only what is safe to repair unattended.** At every daemon
  start, `application/skill/boot_reconcile.py` runs the same repair a person
  can trigger on demand, restricted to `missing_link` (recreate it) and
  `tampered_link` (rename the foreign link aside to a uniquely suffixed backup,
  then recreate). `replaced_with_regular`, `missing_master` and
  `orphan_master` are reported, never auto-remediated. The repair is audited
  with the actor `system`.
- **Degraded delivery is visible.** A `copy_fallback` binding is badged on the
  Skills page and carries `mode: copy_fallback` in its audit event; `verify`
  treats a copy that carries the skill's `SKILL.md` as healthy, since a real
  directory is the expected shape of that mode.

## Consequences

- **One editable copy, seen everywhere** — the product promise of a central
  skill store.
- **No per-OS branching above infrastructure.** The skill service calls one
  port; the sync engine holds all platform behaviour.
- **Drift that accumulates while the daemon is down heals at boot.** Before the
  boot repair existed, the live audit log held zero `skill_drift_remediated`
  events: nobody ever pressed the manual repair.
- **The master has concurrent writers.** The in-app editor's write is
  conditional on a fingerprint of the bytes it read, so a person's concurrent
  edit through their own editor or an agent's link produces a 409 instead of a
  silent overwrite (spec skill-manager "Save an existing skill file
  conditionally").
- **A copy is not promoted.** Nothing converts a `copy_fallback` binding into a
  link when the filesystem later gains link support.
- **The Windows paths are tested less than the POSIX ones.** The unit tests in
  `backend/tests/unit/infrastructure/test_sync_engine.py` run on POSIX: they
  cover link creation, refusal over an existing path, preserving a directory a
  person put in place of a link, deleting a recorded copy, and every drift
  classification. The junction branch has no Windows runner behind it.
- **Enforcement.** Spec skill-manager "Deliver a skill as a directory link",
  spec skill-manager "Fall back to copying where links are unavailable",
  spec skill-manager "Deliver a skill only where it is enabled and in scope",
  spec skill-manager "Report a foreign target instead of overwriting it",
  spec skill-manager "Heal safely repairable drift at daemon boot".
