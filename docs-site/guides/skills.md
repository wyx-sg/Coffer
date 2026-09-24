---
title: Skills
description: Keep one library of AgentSkills-standard skills in Coffer and deliver each one into the skill directories of the agents you choose.
---

# Skills

Coffer keeps one master library of skills on your machine and links each skill into the skill directory of every agent that should have it. This page covers importing and adopting skills, choosing which agents a skill reaches, editing skill files, repairing drift, and Coffer's own built-in `coffer-guide` skill.

## What skills are for

A skill is a folder an agent loads on demand: a `SKILL.md` with instructions, plus any scripts or reference files it needs. Claude Code and Codex both read skills natively from a `skills/` folder inside their config directory. Without Coffer, the same skill ends up copied into `~/.claude/skills/` and `~/.codex/skills/`, and the copies drift apart.

Coffer keeps a single master copy of each skill under `~/.coffer/skills/<name>/` and places a directory link to it in each agent's skill folder. You edit the skill once and every agent reads the same bytes.

Coffer manages skills in the open [AgentSkills](https://agentskills.io) format. A folder that does not conform to it cannot be imported.

## Prerequisites

- The Coffer daemon is running (see [Running the daemon](/guides/daemon)).
- At least one agent is registered (see [Agents](/guides/agents)). Coffer delivers skills to Claude Code and Codex.

## The skill format

A skill folder must contain a `SKILL.md` whose YAML frontmatter carries at least `name` and `description`:

```markdown
---
name: release-checklist
description: Walks through this team's release checklist — version bump, changelog, tag, and the smoke tests to run before announcing.
license: MIT
allowed-tools: Bash, Read
---

# Release checklist

1. Bump the version in `pyproject.toml` ...
```

Coffer validates every folder before it accepts it:

| Rule | Limit |
| --- | --- |
| `SKILL.md` present | required |
| `name` | lowercase letters, digits, `-` and `_`; starts with a letter or digit; at most 64 characters |
| `description` | non-empty, at most 1024 characters |
| Symlinks inside the folder | none may point outside the folder |
| Total folder size | at most 50 MB |

Coffer also reads the optional `license` field and the experimental `allowed-tools` field (a list, or a comma- or space-separated string). Any other frontmatter key is kept and ignored.

A folder that breaks a rule is refused with the reason, and nothing is written to `~/.coffer/skills/` or the database.

## Where skills live

| Path | What it is |
| --- | --- |
| `~/.coffer/skills/<name>/` | The master folder. This is the only copy you edit. |
| `<config_dir>/skills/<name>` | The delivered link in each agent, for example `~/.claude/skills/release-checklist` or `~/.codex/skills/release-checklist`. It points at the master folder. |

Because the delivered path is a link, editing `SKILL.md` from inside `~/.claude/skills/<name>/` edits the master, and every other agent sees the change on its next read. Deleting a file there deletes it from the master too.

## Import a skill

Import copies a local skill folder into the master library. Coffer records the path it came from, but does not track it afterwards: a later change to the source folder is not picked up until you import again.

::: code-group

```sh [CLI]
coffer skill import ~/src/team-skills/release-checklist
```

```text [Web UI]
Skills → Add skill → choose the folder under "Local path" → Import
```

:::

Coffer reads the skill's name from its `SKILL.md` frontmatter and creates `~/.coffer/skills/release-checklist/`. A freshly imported skill is enabled and reaches every registered agent, so it is linked into each agent's skill folder straight away.

Importing a folder whose `name` already exists is refused with a conflict. To replace the existing skill with the new content, re-import with `--force` (in the web UI, confirm **Replace** in the dialog that asks). The master folder's content is swapped in one step, and the skill's reach and its delivered links are kept.

```sh
coffer skill import --force ~/src/team-skills/release-checklist
```

Re-importing is the only way to update a skill from an outside source. Coffer does not import from a URL or a git repository; clone it first, then import the folder.

## Adopt skills an agent already has

Agents accumulate skills that Coffer does not manage — a folder you copied into `~/.claude/skills/` by hand, or one a tool installed into Codex's `~/.agents/skills/`. Coffer lists these as **unmanaged** skills so you can bring them into the library.

Coffer scans:

- `<config_dir>/skills/` for every agent, and
- `~/.agents/skills/` for Codex, which reads that location as well.

Anything there that is not a Coffer-managed link is unmanaged. Codex's own `.system` entry is never listed.

### List unmanaged skills

::: code-group

```sh [CLI]
coffer skill unmanaged codex
coffer skill unmanaged codex --json
```

```text [Web UI]
Agents → choose the agent → Skills tab → Unmanaged skills
```

:::

Each entry shows its name, path, location and whether its `SKILL.md` is valid. An invalid entry shows the reason.

### Adopt one

Adopting moves the folder into `~/.coffer/skills/<name>/`, registers it as a skill, and puts a managed link where the agent expects it.

::: code-group

```sh [CLI]
# a folder in ~/.codex/skills/
coffer skill adopt codex pdf-tools

# a folder in ~/.agents/skills/
coffer skill adopt codex pdf-tools --location agents_dir
```

```text [Web UI]
Agents → choose the agent → Skills tab → Adopt on the row
```

:::

- A folder adopted from `<config_dir>/skills/` is replaced in place by the link.
- A folder adopted from `~/.agents/skills/` is moved out of that directory and the link is placed in `<config_dir>/skills/`. Codex reads both locations, so it keeps seeing the skill.

Adoption is refused, with nothing moved, when the folder has no valid `SKILL.md`, when its name matches a skill already in the library, or when the entry is a symlink pointing somewhere outside Coffer's store (shown as **Foreign link**). If anything fails before the skill is registered, the original folder stays exactly where it was.

After adoption the skill is an ordinary managed skill and follows the same delivery rules as any other: with the default reach it belongs to every agent, and the other agents receive their links at the next reconcile (see [When delivery happens](#when-delivery-happens)).

### Delete an unmanaged skill

To remove an unmanaged folder from disk without adopting it:

::: code-group

```sh [CLI]
coffer skill rm-unmanaged codex old-experiment --force
```

```text [Web UI]
Agents → choose the agent → Skills tab → select the row → Delete
```

:::

This deletes only that folder. It never touches the master library. Coffer never deletes an unmanaged folder on its own.

## Choose which agents get a skill

Two settings on the skill decide where it is delivered, and nothing else does:

- **Enabled** — a disabled skill is delivered nowhere.
- **Reach** (the skill's scope) — which agents it is for.

| Reach | Effect |
| --- | --- |
| Every agent (no scope) | Delivered to every registered agent, including agents you register later. This is the default. |
| Only selected agents | Delivered only to the agents you pick. |
| No agent selected | Delivered to nobody. The skill stays in the library, listed and synced. |

A skill is delivered to an agent if and only if the skill is enabled **and** its reach includes that agent. There is no per-agent switch for "this agent gets no skills"; to keep an agent away from a skill, leave it out of that skill's reach.

::: code-group

```sh [CLI]
# only Claude Code
coffer scope set skill release-checklist --agents claude-code

# nobody, but keep it in the library
coffer scope set skill release-checklist --no-agents

# back to every agent
coffer scope clear skill release-checklist

# switch it off entirely
coffer resource disable skill release-checklist
coffer resource enable skill release-checklist
```

```text [Web UI]
Skills → the Reach button on the skill's row (or on its detail page)
       → Disabled | Every agent | Only selected agents
```

:::

The reach button is labelled with the current answer, for example **Every agent**, **2 agents** or **Disabled**. Choices made under **Only selected agents** are saved once when the panel closes. To change several skills at once, select their rows and use **Reach for the selected**.

::: info Reach is set per machine
Reach and the enabled flag apply to the machine you set them on. [Vault sync](/guides/vault-sync) carries the skill itself — its files and metadata — to your other machines, but each machine keeps its own reach.
:::

### When delivery happens

Coffer reconciles an agent's skills whenever something that affects delivery changes: a skill is imported, removed, enabled, disabled or has its reach edited; an agent is registered, enabled, disabled or has its config directory changed; or a sync round imports new skills. Each reconcile creates the links the agent should have and removes the ones it should no longer have. Removing a link never touches the master folder.

A disabled agent receives nothing. Its links are removed, and they come back when you enable the agent again.

### Link, junction or copy

| Platform | How the skill is delivered |
| --- | --- |
| macOS, Linux | A directory symlink. |
| Windows | A directory symlink; if that is not permitted, a directory junction; if the filesystem supports neither (FAT32, some network shares), a full copy. |

A copied delivery does not follow later edits to the master. The **Skills** page marks such a skill with a **Copied** badge.

If something that is not a Coffer link already sits at `<config_dir>/skills/<name>`, Coffer reports a conflict for that skill and leaves the existing file or folder untouched. The rest of the skills are still delivered.

## View and edit skill files

The master folder is a normal directory, so the simplest way to edit a skill is to open `~/.coffer/skills/<name>/` in your editor. Changes take effect on the agent's next read, with no import step.

Coffer also shows the folder in the web UI and on the CLI.

::: code-group

```sh [CLI]
# the folder as a tree
coffer skill files release-checklist

# one file
coffer skill cat release-checklist SKILL.md

# overwrite an existing file from a local file, or from stdin
coffer skill write release-checklist SKILL.md --from-file ./SKILL.md
cat ./SKILL.md | coffer skill write release-checklist SKILL.md
```

```text [Web UI]
Skills → choose the skill → Files tab → pick a file → Edit → Save
```

:::

The Files tab also offers **Open in editor** and **Reveal in Finder** (your system's file manager) on every file and folder.

Saving is conditional. Each read returns a fingerprint of the file's bytes, and a save that carries it is refused if the file changed on disk in the meantime — for example, because you also edited it in your own editor. Re-read the file and apply your change again. On the CLI, `coffer skill write` takes a fresh fingerprint just before writing unless you pass the one your edit started from with `--fingerprint` (from `coffer skill cat --json`).

`coffer skill write` edits existing text files only. It cannot create new files or folders, and it refuses binary files. To add a file to a skill, create it in the master folder with your editor or shell.

::: warning Guards on `coffer skill write`
`skill write` refuses to save empty content unless you pass `--allow-empty`, so an empty stdin (cron, CI, an agent's shell) cannot silently blank a file. With stdin attached to a terminal and no `--from-file`, it refuses immediately instead of waiting for input. Both refusals exit with code 2 and change nothing. A stale fingerprint exits with code 5.
:::

`coffer skill cat` prints at most the read cap. For a larger file it prints the first part, reports the true size on stderr and exits with code 1, so a script never mistakes the part for the whole file. With `--json` it exits 0 and sets `truncated: true`.

## Check for drift and repair it

Drift is any disagreement between what Coffer recorded as delivered and what is on disk. Coffer recognises five kinds:

| Kind | What happened | Repaired automatically |
| --- | --- | --- |
| `missing_link` | The link in the agent's skill folder was deleted. | Yes |
| `tampered_link` | The link now points somewhere other than the master folder. | Yes |
| `replaced_with_regular` | A real file or folder now occupies the link path. | No — Coffer never touches your content |
| `missing_master` | The master folder under `~/.coffer/skills/` is gone. | No |
| `orphan_master` | A folder in `~/.coffer/skills/` has no Coffer record. | No |

### Automatic repair at startup

Every time the daemon starts, Coffer re-creates missing links and re-points tampered ones. Each repair is recorded in the audit log with a system actor. The other three kinds are left as found and written to the daemon log with the skill, agent, path and a suggested remedy. A failure during this check never stops the daemon from starting.

### Check by hand

```sh
coffer skill verify
```

```text
                                   Skill drift
┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┓
┃ Skill             ┃ Agent       ┃ Kind         ┃ Target                                          ┃ Remedy          ┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━┩
│ release-checklist │ claude-code │ missing_link │ /Users/you/.claude/skills/release-checklist     │ Run `coffer ... │
└───────────────────┴─────────────┴──────────────┴─────────────────────────────────────────────────┴─────────────────┘
```

`verify` only reports; it never changes anything. It prints `no drift` and exits 0 when everything matches, and exits 2 when it finds drift. Add `--json` for machine-readable output.

To repair the repairable kinds now instead of at the next start:

```sh
coffer skill verify --fix
```

`--fix` re-creates missing links. For a tampered link it first moves the existing link aside to `<path>.coffer-backup-<timestamp>`, then re-creates it. It prints what it repaired and what still needs you, and exits 2 if anything remains. Drift checking has no web UI.

## The built-in `coffer-guide` skill

Coffer ships one skill of its own, `coffer-guide`. It is the manual an agent reads to work with Coffer well:

- Coffer's own MCP tools and when to reach for each.
- That tools hidden from the agent's tool list are still callable through `coffer__search_tools`.
- When [Knowledge](/guides/knowledge) is switched on: where the knowledge root is, how to read it with the agent's own file tools, how to add to it with `coffer__write`, and a catalogue of every document in every enabled collection, with its path, title and description.
- When [Memory](/guides/memory) is switched on: that Coffer reads the agent's memory and never writes it, and how `coffer__recall` locates Coffer's notes.
- That no Coffer tool waits on a human approval.

Its frontmatter description names Coffer's tools and the subjects of your enabled collections (taken from each collection's `README.md`), so the model has something concrete to match against. The description stays within 1024 characters; if the collections do not fit, whole subjects are dropped from the end.

In every other respect it is an ordinary skill. It lives at `~/.coffer/skills/coffer-guide/`, appears on the **Skills** page with a **Built-in** badge, and is delivered, reached, verified and repaired exactly like an imported skill.

### It is regenerated, so edits do not survive

Coffer rewrites `coffer-guide` from the running build at every daemon start and whenever the knowledge catalogue changes (after a curation pass, when a collection is created, deleted, enabled or disabled, and on each curation sweep so hand-added documents are picked up). A rewrite is skipped when the content is already identical. Because of this:

- Its files are read-only in the web UI, and `coffer skill write` refuses it.
- Any edit you make on disk is replaced at the next rewrite.

The skill is not carried by [vault sync](/guides/vault-sync). Each machine renders its own from its own collections and settings.

### It cannot be deleted, but you control its reach

Deleting `coffer-guide` is refused with `RESOURCE_PROTECTED` on every surface, because the next start would write it back. What you can change is who gets it: disable it, or narrow its reach, exactly as for any other skill.

```sh
coffer scope set skill coffer-guide --agents claude-code
coffer resource disable skill coffer-guide
```

## Remove a skill

Removing a skill deletes every delivered link, then deletes the master folder and the skill's record. The removal is audited with a snapshot of the skill's configuration.

::: code-group

```sh [CLI]
coffer skill rm release-checklist --force
```

```text [Web UI]
Skills → the delete action on the row (or Delete on the skill's page)
       → confirm "Remove skill release-checklist?"
```

:::

::: danger The master folder is the only copy
Removing a skill deletes `~/.coffer/skills/<name>/`. Coffer does not keep the source folder you imported from. If you want to keep the skill but stop delivering it, disable it or set its reach to no agent instead.
:::

Removing an agent from Coffer also removes that agent's skill links. The master folders stay.

## How it works

Each skill is a `skill` resource in Coffer's registry, identified by an immutable uid. Its name is a label you can change; renaming a skill moves its master folder, re-points every link and rewrites the `name` line in `SKILL.md`, leaving the rest of the file byte-for-byte unchanged.

Coffer records each delivered link in internal bookkeeping (the link path, the link mode, when it was linked). The link on disk is the live truth; the record is what `verify` compares it against. Every import, delivery, removal of a link, removal of a skill and repair is written to the audit log, which you can read on the [Activity](/guides/activity) page.

Coffer exposes no skill tools over MCP. Both supported agents read skills from disk, and a second, tool-based path would bypass each skill's reach.

For the resource model behind enable and reach, see [Resource framework](/architecture/resource-framework).

## Troubleshooting

**An agent does not see a skill.** Check that the skill is enabled and that its reach includes the agent: `coffer scope show skill <name>`. Check that the agent itself is enabled. Then run `coffer skill verify` to see whether its link is missing or blocked by a foreign folder.

**Import is refused.** The error names the rule the folder broke. The most common causes are a `name` with uppercase letters or dots, a missing `description`, or a symlink inside the folder that points outside it.

**A skill shows the Copied badge.** The agent's filesystem does not support links (this happens only on Windows). The copy does not follow edits to the master. After editing, trigger a new delivery, for example by disabling and re-enabling the skill.

**`verify` reports `replaced_with_regular`.** Something other than Coffer put a real folder at the link path. Move it away yourself (adopt it first if you want to keep it), then run `coffer skill verify --fix`.

## Related

- [Knowledge](/guides/knowledge) — the catalogue that `coffer-guide` carries
- [Memory](/guides/memory)
- [Agents](/guides/agents)
- [Vault sync](/guides/vault-sync)
- [CLI reference](/reference/cli)
- [Skill Manager spec](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/skill-manager/spec.md)
- [Cross-Platform Skill Delivery](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/cross-platform-skill-delivery.md) and [Coffer Ships Its Own Manual as a Skill Resource](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/coffer-ships-its-own-skill.md)
