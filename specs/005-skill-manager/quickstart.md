# Quickstart — Coffer Skill Manager

Manage AgentSkills-standard skill folders centrally in Coffer, then deliver
them to one or more registered AI agents (spec 004).

## Prerequisites

- Coffer's daemon is running (start the desktop app or `coffer daemon`).
- At least one agent is registered (auto-detected or via `coffer agent add` —
  see spec 004 quickstart).
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
   `config_dir/skills` folder pointing back to the master.

After this, **all your agents see the skill** through their normal
`config_dir/skills` folder.

## Enable / disable per agent

After import, every registered agent is enabled by default. To
restrict a skill to one agent:

```bash
coffer skill disable my-skill --agent codex
coffer skill list --json | jq '.items[] | select(.name=="my-skill") | .bindings'
```

To re-enable:

```bash
coffer skill enable my-skill --agent codex
```

If something else already exists at the target path (a regular file or a
non-Coffer symlink), the operation refuses unless you pass `--force`. Forced
operations back up the existing target to `<path>.coffer-backup-<timestamp>`
before linking.

## Follow the master library

By default every agent **follows** the master library: every skill you import
is delivered automatically, and newly registered skills appear
without further action. Turn it off (or back on) per agent:

```bash
coffer agent follow codex --off
coffer agent follow codex --on
```

While following, disabling a single skill adds it to the agent's **exclusion
list** instead of touching bindings; set the list explicitly with repeatable
`--exclude` flags (the list is replaced as a whole):

```bash
coffer agent follow codex --on --exclude my-skill --exclude another-skill
```

Turning follow off preserves the currently delivered skills as explicit
per-skill bindings, so nothing disappears — you just switch to manual
`enable`/`disable` curation. The same switch lives on the agent's Skills tab
in the desktop app.

## Adopt skills Coffer doesn't manage yet

If an agent's skill folders contain hand-placed skills (copied by hand or
installed by another tool), Coffer can list and adopt them. The scan covers
`<config_dir>/skills` for both agent types plus `~/.agents/skills` for Codex:

```bash
coffer skill unmanaged claude-code
coffer skill unmanaged claude-code --json
```

Managed Coffer links and internal entries like Codex's `.system` never appear.
Symlinks pointing somewhere outside Coffer's master store are listed as
foreign links — they are surfaced but never adoptable (their origin is
unknown).

Adopt a valid entry into the master store (it is validated, moved to
`~/.coffer/skills/<name>/`, registered, and re-delivered to the agent as a
managed link):

```bash
coffer skill adopt claude-code my-skill --location skills
```

Or delete an unwanted entry from the agent's workspace (disk only — never
master content or bindings):

```bash
coffer skill rm-unmanaged claude-code my-skill --location skills
```

## Verify drift

If you (or another tool) tampered with files in an agent's `config_dir/skills`
folder, ask Coffer to report it:

```bash
coffer skill verify
```

The report categorizes drift and suggests a remedy per entry. Coffer does
**not** automatically fix drift — you decide whether to re-enable or disable.

## Browse a skill's files (read-only)

The desktop app shows a skill's master folder as a file tree and lets you read
individual files in a read-only viewer. To change a file, open it (or its
containing folder) in your own external editor or file manager via the viewer's
open / reveal / copy-path affordances. The same read data is available over the
REST API, and each entry carries its absolute on-disk path.

List the master folder as a recursive tree:

```bash
curl -s http://127.0.0.1:8000/api/v1/skills/my-skill/files \
  -H "X-Coffer-Token: $COFFER_TOKEN" | jq
```

```json
{
  "root": {
    "name": "my-skill",
    "path": "",
    "abs_path": "/Users/me/.coffer/skills/my-skill",
    "type": "dir",
    "size": null,
    "children": [
      {
        "name": "scripts",
        "path": "scripts",
        "abs_path": "/Users/me/.coffer/skills/my-skill/scripts",
        "type": "dir",
        "size": null,
        "children": [
          {
            "name": "run.py",
            "path": "scripts/run.py",
            "abs_path": "/Users/me/.coffer/skills/my-skill/scripts/run.py",
            "type": "file",
            "size": 42,
            "children": []
          }
        ]
      },
      {
        "name": "SKILL.md",
        "path": "SKILL.md",
        "abs_path": "/Users/me/.coffer/skills/my-skill/SKILL.md",
        "type": "file",
        "size": 87,
        "children": []
      }
    ]
  }
}
```

Read one file's contents (the `path` query parameter is relative to the
master folder root):

```bash
curl -s "http://127.0.0.1:8000/api/v1/skills/my-skill/files/content?path=SKILL.md" \
  -H "X-Coffer-Token: $COFFER_TOKEN" | jq
```

```json
{
  "path": "SKILL.md",
  "abs_path": "/Users/me/.coffer/skills/my-skill/SKILL.md",
  "folder_abs_path": "/Users/me/.coffer/skills/my-skill",
  "content": "---\nname: my-skill\n...",
  "truncated": false,
  "binary": false,
  "size": 87
}
```

Reads are contained to the master folder: a path that escapes it (`../...`, an
absolute path, or an escaping symlink) is rejected with `400`. Files larger
than 256 KiB come back with `truncated: true`; non-text files come back with
`binary: true` and empty `content`.

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
