# Skills

A **skill** is an [AgentSkills](https://agentskills.io)-standard bundle — a folder with a `SKILL.md` carrying `name` and `description` frontmatter — that teaches an agent a repeatable task. Coffer keeps one canonical copy of each skill and **delivers** it into the agents you choose, so you manage skills once instead of copying folders between `~/.claude`, `~/.codex`, and the rest.

## Import a skill

Add a skill to your master library from a folder on disk:

```bash
coffer skill import ./my-skill      # copy a local folder in
coffer skill list                   # → my-skill | local_import
coffer skill show my-skill          # metadata + files
```

- `import` takes a copy. `local_import` is the **only** source a skill can have: there is no Git fetcher and no `update` command. If a skill originally came from a repository, the way to refresh it is to pull that repository yourself and `import` again.
- The master copy lives at `~/.coffer/skills/<name>/`, and it is the source of truth — edit it there (or on the skill's page) and every agent it reaches sees the change without re-delivery.

## Decide which agents get a skill

A skill reaches an agent iff the skill is **enabled** and that agent is in the skill's **scope**. An imported skill starts enabled and unscoped, so it goes to every agent; narrow it with the same scope commands every scoped resource uses:

```bash
coffer scope set skill:my-skill --agents claude-code   # only this agent
coffer scope clear skill:my-skill                      # back to every agent
coffer resource disable skill:my-skill                 # take it away from all of them
coffer skill verify                                    # report drift; non-zero exit if any
```

Both of those settings — the enable flag and the scope — are **this machine's**. They are never synced, so a skill that converges to your laptop and your desktop can be delivered to different agents on each, and you set that on each. See [Sync](/guide/sync).

- Delivery is a symlink from the agent's `skills/` directory to the master copy, created and reclaimed for you whenever either input changes.
- `coffer skill verify` reports missing, tampered, or orphaned links; `coffer skill repair` (also the **Repair** action in the app) is the explicit fix.
- `coffer skill rm <name>` removes a skill and tears down all of its links.
- `coffer skill unmanaged` lists skills sitting in an agent's directory that Coffer did not put there; `adopt` pulls one into the master library, and `rm-unmanaged` deletes it.

## In the app

The **Skills** page lists your master library; import via a folder picker — a path, not a URL — and open a skill to see its metadata and browse its master folder, editing any text file in place. Delivery is set on the skill itself — the list table's enable switch, and the activation-scope control on the skill's page. Each agent's **Skills** tab shows what it currently receives, read-only. See [Agents](/guide/agents).

[Knowledge →](/guide/knowledge)
