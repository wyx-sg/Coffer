# Memory

**Memory** is one shared set of facts across all your agents. A fact written by any agent (or by you) is stored as a Markdown file under `~/.coffer/memory/`, recalled by every other agent through Coffer's gateway, and **projected** natively into each agent's own memory location so no per-agent copy drifts.

Memory shares the knowledge substrate: files are the source of truth, the SQLite index is rebuildable, and the same three retrieval modes apply.

## Two scopes

- **global** — applies everywhere (`~/.coffer/memory/global/`).
- **per-project** — scoped to one project, resolved from the git root of the agent's working directory.

Stores are auto-provisioned per scope; you never "create" one. `recall` returns both scopes by default.

## Add and recall

```bash
coffer memory add global "Prefer pnpm over npm in all repos" --name pkg-manager
coffer memory recall global "which package manager?"     # spans project + global
coffer memory facts global                               # list facts
coffer memory edit global <fact-id> "…"                  # curate
coffer memory delete global <fact-id>
```

- Facts are stored verbatim — there is no LLM at write time.
- `recall` rescans the fact directory for out-of-band edits before searching, and uses the same grep / keyword / vector modes as a knowledge base.

## Native projection

Binding a store to an agent projects its facts into that agent's own memory:

```bash
coffer memory bind <store> claude-code --project-root /path/to/repo
coffer memory unbind <store> claude-code
```

- **Claude Code** — the project memory directory is symlinked into `~/.claude/projects/<slug>/memory/`, and the auto-generated `MEMORY.md` index follows Claude Code's own memory format.
- **Codex** — facts render into a managed block in `AGENTS.md`; Codex's native memory is disabled so there is never a second copy.

Agents also get MCP tools: `coffer__remember`, `coffer__recall`, `coffer__update_memory`, `coffer__forget`, and `coffer__list_memory`. A desktop UI lets you browse and curate facts per scope.

[Channels →](/guide/channels)
