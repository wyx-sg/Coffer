# Quickstart — Coffer Agent Registry

Once Coffer has finished its first-run setup, the Agent Registry lets you tell
Coffer which AI agents are installed on your machine so later features
(skills, memory, knowledge bases) know where to deliver assets.

## Auto-detect on first launch

Nothing to do — Coffer scans for known agent install paths the first time the
daemon starts and registers any it finds:

| Agent type       | Detection marker                                                                                         |
| ---------------- | -------------------------------------------------------------------------------------------------------- |
| Claude Code      | `~/.claude/`                                                                                             |
| Claude Desktop   | macOS: `~/Library/Application Support/Claude/`; Linux: `~/.config/Claude/`; Windows: `%APPDATA%/Claude/` |
| Cursor           | `~/.cursor/`                                                                                             |
| OpenAI Codex CLI | `~/.codex/`                                                                                              |

Each detected agent is registered with `auto_detected=true` using its default
skill directory. Open the Agents page (or run `coffer agent list`) to see them.

## List your agents

```bash
coffer agent list
```

JSON for scripts:

```bash
coffer agent list --json
```

## Manually add an agent (custom path)

If your agent is installed somewhere non-standard, add it with an explicit
skill directory:

```bash
coffer agent add cursor --name cursor-work --skill-dir /opt/cursor-work/skills
```

Coffer validates that the path exists, is a directory, is writable by your
user, and is not a privileged system location. Failures are reported with the
specific reason.

## Update an agent

```bash
coffer agent edit cursor-work --skill-dir /opt/cursor-work/skills-v2
```

## Remove an agent

```bash
coffer agent rm cursor-work
```

Removing an auto-detected agent records a "suppression" so subsequent daemon
restarts do not re-add it automatically. You can always re-add it manually
later (which lifts the suppression).

## Re-run auto-detect

If you install a new agent type after Coffer has already started, ask Coffer
to scan again:

```bash
coffer agent detect
```

This is also exposed in the desktop app on the Agents page.

## What happens behind the scenes

- Each agent is stored as a Resource of kind `agent` in Coffer's SQLite
  database, identified by `agent:<name>`. The kind-agnostic Resource framework
  (introduced in spec 001) provides CRUD, validation, and audit.
- Audit events are recorded for every add / edit / remove and queryable from
  `coffer audit list`.
- The agent's `skill_dir` becomes the target directory used by future skill
  delivery (spec 005).

## Troubleshooting

**"Default skill_dir is not writable"** — your install lives somewhere your
user can't write to. Either fix permissions on the path or pass
`--skill-dir <writable-path>` when adding the agent.

**Auto-detected an agent I don't want** — `coffer agent rm <name>`. Coffer
will not re-add it on the next launch.

**Auto-detect missed an installed agent** — your install is in a non-standard
location. `coffer agent add <type> --skill-dir <your-path>`.
