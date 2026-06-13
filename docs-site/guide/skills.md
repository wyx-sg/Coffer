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

## Deliver a skill to an agent

Enabling a skill for an agent creates a symlink from the agent's `skills/` directory to the master copy:

```bash
coffer skill enable my-skill --agent claude-code     # deliver it (symlink)
coffer skill disable my-skill --agent claude-code    # remove the link
coffer skill verify                                  # report drift; non-zero exit if any
```

- Coffer never auto-remediates. `verify` reports missing, tampered, or orphaned links; you fix them explicitly (re-enable, or `coffer skill update`).
- `coffer skill rm <name>` removes a skill and tears down all of its bindings.

## In the app

The **Skills** page lists your master library; import via a file picker or a Git URL, and open a skill to see its metadata and a read-only file tree. Per-agent delivery lives on each agent's **Skills** tab — toggle a skill on or off for that agent. See [Agents](/guide/agents).

[Knowledge bases →](/guide/knowledge-base)
