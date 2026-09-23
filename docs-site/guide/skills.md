# Skills

A **skill** is an [AgentSkills](https://agentskills.io)-standard bundle — a folder with a `SKILL.md` carrying `name` and `description` frontmatter — that teaches an agent a repeatable task. Coffer keeps one canonical copy of each skill and **delivers** it into the agents you choose, so you manage skills once instead of copying folders between `~/.claude`, `~/.codex`, and the rest.

## Import a skill

Add a skill to your master library from a folder on disk:

```bash
coffer skill import ./my-skill      # copy a local folder in
coffer skill list                   # → my-skill | local_import
coffer skill show my-skill          # metadata + where it is delivered
```

- `import` takes a copy. `local_import` is the only source **you** can create: there is no Git fetcher and no `update` command. If a skill originally came from a repository, the way to refresh it is to pull that repository yourself and `import` again. The one other source is `builtin`, which only Coffer itself creates — see "Coffer's own skill" below.
- The master copy lives at `~/.coffer/skills/<name>/`, and it is the source of truth — edit it there (or on the skill's page) and every agent it reaches sees the change without re-delivery.
- An import is refused if `SKILL.md` lacks a non-empty `name` or `description`, if the folder is over 50 MB, or if a skill of that name already exists — `--force` replaces the existing one.

On disk, delivery is a directory link from each agent's skills folder back to the master, so an edit through either path lands in the one copy:

```
~/.coffer/skills/my-skill/
  SKILL.md
  scripts/…
  .coffer.meta.json            # where the folder was imported from

~/.claude/skills/my-skill  →  ~/.coffer/skills/my-skill
~/.codex/skills/my-skill   →  ~/.coffer/skills/my-skill
```

On Windows the link is a junction; on a filesystem that supports neither, Coffer copies the folder instead and records the degradation in the audit log.

## Decide which agents get a skill

A skill reaches an agent iff the skill is **enabled** and that agent is in the skill's **scope**. An imported skill starts enabled and unscoped, so it goes to every agent; narrow it with the same scope commands every scoped resource uses:

```bash
coffer scope set skill my-skill --agents claude-code   # only this agent
coffer scope clear skill my-skill                      # back to every agent
coffer resource disable skill my-skill                 # take it away from all of them
```

Both of those settings — the enable flag and the scope — are **this machine's**. They are never synced, so a skill that converges to your laptop and your desktop can be delivered to different agents on each, and you set that on each. See [Sync](/guide/sync).

- Links are created and reclaimed for you whenever either input changes.
- If something Coffer did not put there already sits at the link path — a regular file, or a symlink pointing elsewhere — that skill is reported as a **conflict** and the existing entry is left exactly as it was; the rest of the delivery still happens. There is no flag that overwrites it: move it yourself and the next reconcile delivers the link.
- `coffer skill rm <name>` removes a skill: every link first, then its bindings, then the master folder, with a snapshot of its config in the audit log. Coffer's own skill is refused.

## Drift and repair

```bash
coffer skill verify            # report drift; non-zero exit if any
coffer skill verify --fix      # repair what is safe to repair (the app's Repair action)
```

`verify` only reports. `--fix` re-delivers the two kinds of drift that are safe to fix without asking: a **missing** link is recreated, and a **tampered** link is renamed aside to `<path>.coffer-backup-<timestamp>` before being recreated — never deleted or overwritten in place. Anything that would clobber someone else's content or has nothing left to deliver from — a link replaced by a real folder, a missing master, a master folder Coffer has no record of — is left as it is and reported for you to decide. The same safe repair also runs **once at every daemon start**, audited as automatic, and never blocks startup if it fails.

## Skills Coffer doesn't manage

Skills copied into an agent's folder by hand or by another tool can be listed, adopted into the master library, or deleted. The scan covers each agent's `skills/` folder, plus `~/.agents/skills` for Codex (`--location agents_dir`):

```bash
coffer skill unmanaged claude-code                       # --json for scripts
coffer skill adopt claude-code my-skill                  # move into ~/.coffer/skills/, register, relink
coffer skill rm-unmanaged claude-code my-skill           # delete from the agent's folder only
```

Coffer's own links and internal entries such as Codex's `.system` never appear. A symlink pointing somewhere outside Coffer's master store is listed as a **foreign link** and cannot be adopted, because its origin is unknown.

## Coffer's own skill

One skill in your library is not yours: `coffer-guide`, the manual Coffer writes for the agents it serves. Its description names Coffer's tools and the subjects of your knowledge collections; its body is the manual and the full catalogue of what you have written down. See [Knowledge](/guide/knowledge).

It is an ordinary skill in every way that matters — listed beside yours, delivered by the same links, verified and repaired by the same commands — with two differences:

- **Coffer rewrites it** at every start and whenever your knowledge catalogue moves, so an edit to its master folder does not survive. A correction belongs in Coffer, not in the folder.
- **It cannot be deleted.** The next start would write it straight back, so the delete is refused rather than quietly undone. `coffer resource disable skill coffer-guide` and the usual scope commands still work — which agents it reaches is yours to decide; whether it exists is not.

## In the app

The **Skills** page lists your master library; import via a folder picker — a path, not a URL — and open a skill to see its metadata and browse its master folder, editing any text file in place. Reach is set on the skill itself — one reach button in the list's **Reach** column and on the skill's page (Disabled / Every agent / Only selected agents). Each agent's **Skills** tab points back here and lists the unmanaged skills found on that agent's disk. See [Agents](/guide/agents).

Editing in place is guarded against losing an edit you made elsewhere: every read returns a fingerprint of the file, and a save carrying a stale one is refused (`409`) with the file left untouched, so reload and redo the change. The editor overwrites an existing text file only — it does not create files, write outside the skill's folder, or replace a binary — and a file over 256 KiB opens truncated. For anything bigger, the viewer opens the file or reveals its folder in your own tools.

[Knowledge →](/guide/knowledge)
