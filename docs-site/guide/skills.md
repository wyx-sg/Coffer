# Skills

A **skill** is an [AgentSkills](https://agentskills.io)-standard bundle — a folder with a `SKILL.md` carrying `name` and `description` frontmatter — that teaches an agent a repeatable task. Coffer keeps one canonical copy of each skill and **delivers** it into the agents you choose, so you manage skills once instead of copying folders between `~/.claude`, `~/.codex`, and the rest.

## Import a skill

Add a skill to your master library from a local folder or a public Git URL:

```bash
coffer skill import ./my-skill                                      # copy a local folder in
coffer skill fetch https://github.com/acme/skills --ref main --subpath foo
coffer skill list                                                  # → my-skill | local_import
coffer skill show my-skill                                          # metadata + files
```

- `import` takes a point-in-time copy; `fetch` records the Git source so you can refresh it later with `coffer skill update <name>`.
- The master copy lives at `~/.coffer/skills/<name>/`.

## Decide which agents get a skill

A skill reaches an agent iff the skill is **enabled** and that agent is in the skill's **scope**. An imported skill starts enabled and unscoped, so it goes to every agent; narrow it with the same scope commands every scoped resource uses:

```bash
coffer scope set skill:my-skill --agents claude-code   # only this agent
coffer scope clear skill:my-skill                      # back to every agent
coffer resource disable skill:my-skill                 # take it away from all of them
coffer skill verify                                    # report drift; non-zero exit if any
```

- Delivery is a symlink from the agent's `skills/` directory to the master copy, created and reclaimed for you whenever either input changes.
- Coffer never auto-remediates drift. `verify` reports missing, tampered, or orphaned links; you fix them explicitly (`coffer skill update`, or re-apply the scope).
- `coffer skill rm <name>` removes a skill and tears down all of its links.

## In the app

The **Skills** page lists your master library; import via a file picker or a Git URL, and open a skill to see its metadata and browse its master folder, editing any text file in place. Delivery is set on the skill itself — the list table's enable switch, and the activation-scope control on the skill's page. Each agent's **Skills** tab shows what it currently receives, read-only. See [Agents](/guide/agents).

[Knowledge →](/guide/knowledge)
