# Quickstart — Coffer Skill Manager

Manage AgentSkills-standard skill folders centrally in Coffer, then deliver
them to one or more registered AI agents (spec 004).

## Prerequisites

- Coffer's daemon is running (start the desktop app or `coffer daemon`).
- At least one agent is registered (auto-detected or via `coffer agent add` —
  see spec 004 quickstart).
- For Git fetches: `git` is installed and on `PATH`.

## Import an existing skill folder

If you already have a skill in `~/.claude/skills/my-skill/`, bring it under
Coffer's management:

```bash
coffer skill import ~/.claude/skills/my-skill
```

Coffer:

1. Reads `SKILL.md`, validates frontmatter (`name`, `description` required).
2. Copies the folder to `~/.coffer/skills/my-skill/` (the canonical master).
3. Registers a Resource of kind `skill`.
4. Auto-enables the skill for every registered agent (trust mode).
5. Creates a directory symlink (POSIX) or junction (Windows) in each agent's
   skill directory pointing back to the master.

After this, **all your agents see the skill** through their normal skill
directory.

## Fetch a skill from a Git repository

```bash
coffer skill fetch https://github.com/owner/skills-repo \
  --ref main \
  --subpath skills/my-skill
```

Coffer performs a shallow clone, validates the subpath, and copies it to
`~/.coffer/skills/<name>/`. Private repos are not supported in v1.

## Enable / disable per agent

After import or fetch, every registered agent is enabled by default. To
restrict a skill to one agent:

```bash
coffer skill disable my-skill --agent cursor
coffer skill list --json | jq '.items[] | select(.name=="my-skill") | .bindings'
```

To re-enable:

```bash
coffer skill enable my-skill --agent cursor
```

If something else already exists at the target path (a regular file or a
non-Coffer symlink), the operation refuses unless you pass `--force`. Forced
operations back up the existing target to `<path>.coffer-backup-<timestamp>`
before linking.

## Update a Git-sourced skill

```bash
coffer skill update my-skill
```

Coffer re-fetches the source, replaces the master folder atomically if the
content has changed, and records the before/after content hashes in the audit
log. If SKILL.md's frontmatter `name` has changed, the update is rejected
unless you pass `--allow-rename`.

Local-imported skills cannot be updated this way — re-run `import` against
the new folder.

## Verify drift

If you (or another tool) tampered with files in an agent's skill directory,
ask Coffer to report it:

```bash
coffer skill verify
```

The report categorizes drift and suggests a remedy per entry. Coffer does
**not** automatically fix drift — you decide whether to re-enable, disable,
or update.

## Remove a skill

```bash
coffer skill rm my-skill
```

Coffer removes every per-agent symlink, deletes the bindings, then deletes the
master folder. The removal is recorded in the audit log with a snapshot of
the skill's config.

## How the on-disk layout looks

```
~/.coffer/skills/
  my-skill/
    SKILL.md
    scripts/...
    references/...
    .coffer.meta.json     # source provenance (forensic only)

~/.claude/skills/my-skill        → symlink to ~/.coffer/skills/my-skill
~/.cursor/skills/my-skill        → symlink to ~/.coffer/skills/my-skill
~/.codex/skills/my-skill         → symlink to ~/.coffer/skills/my-skill
```

Edits to any of these paths land in the master (symlinks are transparent), so
there is no copy drift.

## Troubleshooting

**"SKILL.md missing required frontmatter field"** — open the folder you tried
to import and ensure both `name` and `description` are non-empty in the
top-of-file YAML.

**"Refusing to overwrite existing target"** — there is a non-Coffer file or
directory at the link path. Either remove it yourself or pass `--force` to
have Coffer back it up and replace it.

**"Symlink creation failed; falling back to copy"** — your filesystem doesn't
support directory junctions (Windows on FAT32 or some network shares). Coffer
copied the skill content into the target and recorded the degradation in
the audit log; UI shows a warning chip on that binding.

**Drift after manual edits in `~/.coffer/skills/<name>/`** — That's fine.
Master is the editable source of truth. Other agents see the edit on next
read through their symlinks.
