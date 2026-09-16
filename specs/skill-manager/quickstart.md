# Quickstart — Coffer Skill Manager

Manage AgentSkills-standard skill folders centrally in Coffer, then deliver
them to one or more registered AI agents (spec agent-registry).

## Prerequisites

- Coffer's daemon is running (`coffer daemon start`, or `coffer open`, which
  starts one if none is running and opens the web UI).
- At least one agent is registered (auto-detected or via `coffer agent add` —
  see spec agent-registry quickstart).
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
4. Registers it unscoped and enabled, so it is active for every agent.
5. Creates a directory symlink (POSIX) or junction (Windows) in each agent's
   `config_dir/skills` folder pointing back to the master.

After this, **all your agents see the skill** through their normal
`config_dir/skills` folder.

## Decide which agents get a skill

A skill reaches an agent iff the skill is **enabled** and that agent is in the
skill's **scope**. Those two are the only controls; there is no per-agent
follow flag and no per-binding switch.

Scope is the framework's own per-agent activation axis ([ADR per-agent-resource-scope](../../docs/decisions/per-agent-resource-scope.md)),
so a skill uses the same commands every scoped kind does — unscoped means every
agent:

```bash
coffer scope show skill:my-skill
coffer scope set skill:my-skill --agents codex        # only codex
coffer scope set skill:my-skill --no-agents           # dormant: no agent
coffer scope clear skill:my-skill                     # back to every agent
```

Disabling the skill itself takes it away from every agent at once, and
re-enabling gives it back to whatever its scope grants:

```bash
coffer resource disable skill:my-skill
coffer resource enable skill:my-skill
coffer skill list --json | jq '.items[] | select(.name=="my-skill") | {enabled, scope, bindings}'
```

Either change reconciles immediately: a delivered copy that falls out of scope,
or belongs to a skill you just disabled, is reclaimed. In the web UI the same
two controls are the Skill list table's enable switch and the skill detail
page's activation-scope control.

If something else already exists at the target path (a regular file or a
non-Coffer symlink), delivery **reports and moves on**: that one skill comes
back as a conflict, the existing target is left exactly as it was, and the rest
of the delivery still happens. Delivery never overwrites and has no `--force`.
The one place Coffer backs a target up before relinking is the opt-in drift
repair below, and only for a link it put there itself.

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

The report categorizes drift and suggests a remedy per entry; asking for it
never repairs anything.

Repair is a separate, explicit operation — and it also runs **once at every
daemon boot**, because boot is the moment nothing else reconciles an
already-delivered link's health:

```bash
coffer skill verify --fix        # or: POST /skills/repair
```

Repair re-delivers only the two drift kinds that are safe to fix without
asking: a **missing link** is recreated, and a **tampered link** is renamed
aside to `<path>.coffer-backup-<timestamp>` before being recreated — never
deleted, never overwritten in place. The kinds that would clobber someone
else's content or have nothing left to re-deliver from (replaced with a regular
file, missing master, orphan master) are left exactly as they are and reported
for a human. The boot pass is audited with an actor that says it was automatic,
and a failure there never blocks startup.

## Browse and edit a skill's files

The web UI shows a skill's master folder as a file tree and opens an individual
file in a viewer you can **edit in place**. A save is conditional: every read
returns a content fingerprint, and a write that carries a stale one is rejected
with `409` and the file left byte-identical, so an edit made in your own editor
meanwhile is never silently lost (a write that omits the fingerprint stays
unconditional, which is what a script that never read the file needs). The
write overwrites an existing text file only — it will not create files, write
outside the folder, or replace a binary. The viewer also offers open / reveal
for the file and its containing folder, for anything bigger than a small edit.
The same reads and the same write are available over the REST API, and each
entry carries its absolute on-disk path.

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

## Let an agent read the library itself

An agent connected to Coffer's MCP endpoint sees two built-in tools beside the
management surfaces above:

- `coffer__list_skills` — no arguments; returns every registered skill as a
  `name` and a `description`, so the agent can see what is available without
  the user pasting a list.
- `coffer__load_skill` — takes a skill `name`; returns the verbatim text of
  that skill's `SKILL.md`. It reads that one file in that one master folder and
  nothing else, and it delivers nothing: a skill an agent loads this way is not
  linked into its config directory.

Both are reads, recorded in the MCP invocation log rather than the audit log.
Both are also **global**: the catalogue they answer with is the whole library,
including skills that are disabled or scoped away from the calling agent. That
is what ships and it is recorded as a known defect in
[`spec.md`](./spec.md) `## Assumptions` — a skill's `enabled` flag and scope
decide **delivery**, not what these two tools will read out.

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

**A skill reported as a conflict instead of delivered** — there is a non-Coffer
file or directory at the link path. Coffer will not overwrite it and offers no
flag that would: move or remove it yourself, then let the next reconcile (or
`coffer skill verify --fix`) deliver the link.

**"Symlink creation failed; falling back to copy"** — your filesystem doesn't
support directory junctions (Windows on FAT32 or some network shares). Coffer
copied the skill content into the target and recorded the degradation in
the audit log; UI shows a warning chip on that binding.

**Drift after manual edits in `~/.coffer/skills/<name>/`** — That's fine.
Master is the editable source of truth. Other agents see the edit on next
read through their symlinks.
