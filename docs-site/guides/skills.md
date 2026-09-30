---
title: Skills
description: Keep one library of AgentSkills-standard skills in Coffer — added from a folder, an archive or a Git repository — and deliver each one into the skill directories of the agents you choose.
---

# Skills

Coffer keeps one master library of skills on your machine and links each skill into the skill directory of every agent that should have it. This page covers adding skills from a folder, an archive or a Git repository, updating a skill from its repository, adopting skills an agent already has, choosing which agents a skill reaches, editing skill files, the commands a skill needs, skill names, checking agents' copies, and Coffer's own built-in `coffer-guide` skill. How it works underneath is on the [Skills architecture](/architecture/skills) page.

## What skills are for

A skill is a folder an agent loads on demand: a `SKILL.md` with instructions, plus any scripts or reference files it needs. Claude Code and Codex both read skills natively from a `skills/` folder inside their config directory. Without Coffer, the same skill ends up copied into `~/.claude/skills/` and `~/.codex/skills/`, and the copies drift apart.

Coffer keeps a single master copy of each skill under `~/.coffer/vault/skills/<name>/` and places a directory link to it in each agent's skill folder. You edit the skill once and every agent reads the same bytes.

Coffer manages skills in the open [AgentSkills](https://agentskills.io) format. A folder that does not conform to it cannot be imported.

## Prerequisites

- The Coffer daemon is running (see [Running the daemon](/guides/daemon)).
- To add from a Git repository, `git` is installed on this machine.
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

Coffer also reads the optional `license` field, the experimental `allowed-tools` field (a list, or a comma- or space-separated string), and `requires:` — the command-line tools the skill drives, which Coffer checks on this machine and shows on the skill's **Requires** tab and the [CLIs page](/guides/clis). Any other frontmatter key is kept and ignored.

A folder that breaks a rule is refused with the reason, and nothing is written to the vault.

## Where skills live

| Path | What it is |
| --- | --- |
| `~/.coffer/vault/skills/<name>/` | The master folder. This is the only copy you edit. |
| `<config_dir>/skills/<name>` | The delivered link in each agent, for example `~/.claude/skills/release-checklist` or `~/.codex/skills/release-checklist`. It points at the master folder. |

Because the delivered path is a link, editing `SKILL.md` from inside `~/.claude/skills/<name>/` edits the master, and every other agent sees the change on its next read. Deleting a file there deletes it from the master too.

## The Skills page

**Skills** (under Capabilities in the sidebar) is your library beside the skill you are reading. The list on the left has a search box, an **All / On / Off** filter and **Check copies**; each row shows the skill's name and its reach, with **Built-in** or **Off** where they apply, and its description — or, in its place, the one thing that needs you: **Master missing**, **Folder in the way in Codex**, **Needs jq · not installed**, **Source unreachable** or **Update available**. Tick rows (a box appears on hover) to set the reach of several skills at once or to delete them; the selection shows as a bar under the filter and in the reading pane. Folders in `~/.coffer/vault/skills/` that no skill claims are listed apart, under **Not in your library** (see [below](#folders-not-in-your-library)).

The open skill's header carries its reach button and a **⋯** menu: **Open in editor**, **Reveal in Finder**, **Copy master path**, **Check agents' copies**, **Turn off** (removes it from every agent and keeps who you chose) and **Delete…**. Above its tabs, a banner says what needs you — a folder in the way, a missing command, an update — with the one action that answers it.

Choosing a skill opens it on the right, at its own address (`/skills/<name>`), with four tabs:

| Tab | What it shows |
| --- | --- |
| **Files** | The skill's files beside the open file, opening on `SKILL.md` rendered. **Preview / Source** switches a Markdown file between rendered and raw text, and **Edit** edits a file in place. A binary file offers **Open in default app** and **Reveal in Finder**; a very large file shows its start, read-only. A Git skill shows its source above the files. |
| **Delivery** | Every agent and the state of its copy: **Linked**, **Copied, not linked** (where links are not allowed), a folder in the way (with **Review…**), or not delivered and why. **Check again** looks at every copy afresh. |
| **Requires** | The commands the skill says it needs, each with its state and **Open in CLIs**. Installing and logging in happen on the CLIs page. |
| **History** | Every version of the skill's folder, newest first, with who wrote each (you, edited on disk, an agent, Coffer, sync), each version's changes file by file, and **Restore** to put a version back as a new one. |

The Skills page lists only the skills Coffer manages. Skills an agent has that Coffer does not manage are on that agent's **Skills** tab, where you can adopt them (see [below](#adopt-skills-an-agent-already-has)).

## Add a skill

A skill comes from one of three places. Whichever you use, Coffer first shows what it found — the skill or skills, their names and descriptions, any that cannot be added and why, and any whose name is already taken — and adds nothing until you confirm. Closing the dialog leaves nothing behind.

### From a folder

::: code-group

```sh [CLI]
coffer skill add ~/src/team-skills/release-checklist
```

```text [Web UI]
Skills → Add skill → From a folder → paste the path, or Choose… → Add skill
```

:::

Coffer reads the skill's name from its `SKILL.md` frontmatter and copies the folder to `~/.coffer/vault/skills/release-checklist/`. It records the path it came from, but does not track it afterwards: a later change to the source folder is not picked up until you add it again. In the web UI, a folder whose top has no `SKILL.md` but whose subfolders do offers those subfolders as a choice. On the command line, naming the folder is the confirmation, so it is added at once.

### From an archive

::: code-group

```sh [CLI]
coffer skill add ~/Downloads/release-notes.skill
coffer skill add ~/Downloads/team-skills.zip --skill review --skill triage
coffer skill add ~/Downloads/team-skills.zip --all --yes
```

```text [Web UI]
Skills → Add skill → From an archive → Choose file… (or drop a .zip or .skill file) → Add skill
```

:::

A `.zip` or `.skill` archive holds a skill when its `SKILL.md` is at the top of the archive or one folder down. An archive holding several skills lists them all, and you pick which to add — on the command line with `--skill <name>` (repeat it) or `--all`. The command prints what it found and asks before adding; `--yes` skips the question.

Coffer refuses the whole archive, naming the entries, before unpacking any of it when an entry has an absolute path or a `..` in its path, when an entry is a symlink, or when it would unpack to more than 50 MB. An archive with no `SKILL.md` at the top or one folder down is refused with that message.

### From a Git repository

::: code-group

```sh [CLI]
coffer skill add https://github.com/acme/agent-skills --path skills/review
coffer skill add https://github.com/acme/agent-skills --ref v1.2 --path skills/review --yes
coffer skill add https://github.com/acme/agent-skills/tree/main/terraform-plan
```

```text [Web UI]
Skills → Add skill → From Git → Repository URL, and optionally Branch or tag and Folder → Add skill
```

:::

Coffer clones the repository with this machine's own `git`, resolves the branch, tag or commit you gave (the default branch when you gave none) to one commit, and looks for skills in the folder you named by the same rule as an archive. A GitHub folder address such as `https://github.com/acme/agent-skills/tree/main/terraform-plan` is read as the repository, the branch and the folder.

The skill is **pinned** to the commit it was copied from. It does not change when the repository does; see [Update a skill from its repository](#update-a-skill-from-its-repository).

::: info Which repositories Coffer can reach
Git runs without a prompt, and Coffer gives it no credential and stores none. A public repository always works. A private one works when this machine's git can already clone it — through a credential helper such as the macOS keychain, or SSH keys — because Coffer uses your own git configuration. If git would ask for a password, the add fails with git's message instead.
:::

### When the name is taken

Adding a skill whose `name` already exists is refused with a conflict. To replace the existing skill with the new content, choose **Replace** on that row in the dialog, or pass `--force` on the command line. The master folder's content is swapped in one step, and the skill's reach and its delivered links are kept.

```sh
coffer skill add --force ~/src/team-skills/release-checklist
```

A freshly added skill is enabled and reaches every registered agent, so it is linked into each agent's skill folder straight away.

## Update a skill from its repository

A skill added from a Git repository shows its source on its page: the repository, the folder, the pinned commit and whether an update is waiting. Coffer checks the repository every six hours, and you can check at any time.

::: code-group

```sh [CLI]
coffer skill update terraform-plan --check
coffer skill update terraform-plan
```

```text [Web UI]
Skills → the skill → Check now, then Review update… on the banner when an update is available
```

:::

When the branch or tag has new commits that change the skill's folder, the skill shows **Update available** with the commits since the pin. Reviewing it lists the files the update adds, removes and changes, with a diff, and applies nothing until you confirm. Applying replaces the folder with the new commit's content, moves the pin, and keeps the skill's reach and links; every agent sees the new files at once. On the command line, `coffer skill update <name>` prints the same preview and asks before applying (`--yes` skips the question).

If you edited the skill since its pinned commit, the update is a **conflict**:

| Choice | Web UI | CLI | What happens |
| --- | --- | --- | --- |
| Keep mine | **Keep my edits** | `--keep-mine` | Nothing changes. Coffer stops offering this update and tells you again when a newer commit arrives. |
| Take theirs | **Take the update** | `--take-theirs` | The new commit is applied and your edits are replaced. |
| Compare | **Compare** | — | Each changed file side by side: your folder, the pinned commit and the new commit. |
| Merge with an agent | **Merge with an agent**, then **I merged it** | `--prompt`, then `--merged <commit>` | Your agent merges the update into your edits; recording it moves the pin and keeps the files. |

Coffer does not merge two versions of a skill itself. **Merge with an agent** gives you a prompt to copy, or **Ask an agent** starts a conversation with it filled in (nothing is sent until you press Send). The prompt names the skill's master folder as the only place to edit, the files you edited since the pin, the pinned and new commits with their messages, and the repository to read the update from. The agent keeps what your edits were for, takes the update's fixes, and shows you the diff; it does not record the merge itself. When the files look right, choose **I merged it** and confirm, or run:

```sh
coffer skill update <name> --merged <commit>
```

This moves the pin to that commit and leaves the master folder exactly as the merge left it. Your merged edits still count as local edits against the new pin, so the next update is a conflict again, listing only the edits you carried over — never one that silently replaces them. Only the update that is waiting can be recorded: the pinned commit, or a commit that is not on the branch, is refused with `SKILL_UPDATE_NOT_PENDING`. To do the merge by hand instead, edit the files in the master folder (`coffer path skill <name>`), then record it the same way.

If the repository can no longer be reached, the skill keeps working from its pinned copy. Its page shows git's message and when the last check succeeded, and nothing changes until a check succeeds again.

To move a Git skill to another repository, branch or folder, use **Change source…** in its Source block. Coffer clones the new source and shows how it differs from your current version; nothing is replaced until you take it, and the skill keeps its name.

A skill added from a folder or an archive has no source to update from: add it again with **Replace** (`--force`).

## Adopt skills an agent already has

Agents accumulate skills that Coffer does not manage — a folder you copied into `~/.claude/skills/` by hand, or one a tool installed into Codex's `~/.agents/skills/`. Coffer lists these as **unmanaged** skills so you can bring them into the library, or delete them.

Coffer scans:

- `<config_dir>/skills/` for every agent, and
- `~/.agents/skills/` for Codex, which reads that location as well.

Anything there that is not a Coffer-managed link is unmanaged. Codex's own `.system` entry is never listed.

### List unmanaged skills

::: code-group

```sh [CLI]
coffer scan --agent codex
coffer scan --agent codex --json
```

```text [Web UI]
Agents → choose the agent → Skills tab → Unmanaged skills
```

:::

On the CLI, `coffer scan` lists unmanaged skills in one table with detected agents and MCP entries that Coffer does not manage yet; skill rows have kind `skill`. Each entry shows its name, path, location and whether its `SKILL.md` is valid. An invalid entry shows the reason. The **Ref** column of a skill row is the folder's path, which is what `coffer adopt skill` and `coffer discard skill` take.

### Preview one

Read an unmanaged skill before you decide what to do with it. Nothing here changes the folder.

::: code-group

```sh [CLI]
coffer scan --agent codex --json   # each skill row's "ref" is the folder's absolute path
cat <that path>/SKILL.md           # read it with your own tools
```

```text [Web UI]
Agents → choose the agent → Skills tab → click the row
```

:::

The detail page has an **Overview** tab (the `SKILL.md` description, the folder's path and location) and a **Files** tab (the folder's tree and a read-only preview of each file). An invalid folder opens too, with the reason at the top. The page header carries **Open folder** (the folder in your file manager), **Adopt** and **Delete**, and its back link returns to the agent's Skills tab. File reads stay inside the folder, as they do for a managed skill.

### Adopt one

Adopting moves the folder into `~/.coffer/vault/skills/<name>/`, registers it as a skill, and puts a managed link where the agent expects it.

::: code-group

```sh [CLI]
# a folder in ~/.codex/skills/
coffer adopt skill ~/.codex/skills/pdf-tools

# a folder in ~/.agents/skills/
coffer adopt skill ~/.agents/skills/pdf-tools
```

```text [Web UI]
Agents → choose the agent → Skills tab → Adopt on the row, or Adopt on the skill's page
```

:::

Adopting from the skill's page takes you on to the new managed skill's page.

- A folder adopted from `<config_dir>/skills/` is replaced in place by the link.
- A folder adopted from `~/.agents/skills/` is moved out of that directory and the link is placed in `<config_dir>/skills/`. Codex reads both locations, so it keeps seeing the skill.

Adoption is refused, with nothing moved, when the folder has no valid `SKILL.md`, when its name matches a skill already in the library, or when the entry is a symlink pointing somewhere outside Coffer's store (shown as **Foreign link**). If anything fails before the skill is registered, the original folder stays exactly where it was.

After adoption the skill is an ordinary managed skill and follows the same delivery rules as any other: with the default reach it belongs to every agent, and the other agents receive their links at the next reconcile (see [When delivery happens](#when-delivery-happens)).

### Delete an unmanaged skill

To remove an unmanaged folder from disk without adopting it:

::: code-group

```sh [CLI]
coffer discard skill ~/.codex/skills/old-experiment --force
```

```text [Web UI]
Agents → choose the agent → Skills tab → Delete on the row, or Delete on the skill's page
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
# show the current reach
coffer skill scope release-checklist

# only Claude Code
coffer skill scope release-checklist --agents claude-code

# nobody, but keep it in the library
coffer skill scope release-checklist --none

# back to every agent
coffer skill scope release-checklist --all

# switch it off entirely
coffer skill disable release-checklist
coffer skill enable release-checklist
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

A copied delivery is refreshed after each edit in Coffer. The skill's **Delivery** tab shows that agent's copy as **Copied, not linked**, with the reason.

If something that is not a Coffer link already sits at `<config_dir>/skills/<name>`, Coffer reports a conflict for that skill (a folder in the way) and leaves the existing file or folder untouched. The rest of the skills are still delivered. See [Resolve a folder in the way](#resolve-a-folder-in-the-way).

## View and edit skill files

The master folder is a normal directory, so the way to edit a skill is to open `~/.coffer/vault/skills/<name>/` in your editor or shell. Changes take effect on the agent's next read, with no import step. `coffer path skill <name>` prints the folder's absolute path.

::: code-group

```sh [CLI]
# where the master folder is
coffer path skill release-checklist

# then edit it in place with your own tools
$EDITOR "$(coffer path skill release-checklist)/SKILL.md"
```

```text [Web UI]
Skills → choose the skill → Files tab → pick a file → Edit → Save
```

:::

The Files tab also offers **Open in editor** on a text file, and **Open in default app** and **Reveal in Finder** (your system's file manager) on a binary one; the skill's **⋯** menu opens or reveals the whole folder.

Saving in the Files tab is conditional. Each read returns a fingerprint of the file's bytes, and a save that carries it is refused if the file changed on disk in the meantime — for example, because you also edited it in your own editor. Your text stays in the editor, marked **Not saved**, with three ways out: **Reload** (take what is on disk), **Compare** (the disk against your text) and **Copy my text**. `⌘S` saves while you edit. Every save, and every edit you make in your editor, becomes a version on the **History** tab; `coffer vault history skills/<name>/` lists them from the terminal. See [Editing the vault by hand](/guides/vault-files). The Files tab edits existing text files only; to add a file to a skill, create it in the master folder with your editor or shell.

## Commands a skill needs

A skill can say which command-line tools it relies on with `requires` in its frontmatter:

```yaml
---
name: gh-triage
description: Label new issues, find duplicates, ask for missing details.
requires: [jq, "gh>=2.40", uv]
---
```

Each entry is a command name, optionally with a minimum version (`gh>=2.40`); `requires: {commands: [...]}` and entries like `{command: gh, version: "2.40"}` are read too. The skill's **Requires** tab lists them, each linking to its page on the CLIs page, and `coffer skill show <name> --json` carries them as `requires`. Declaring a requirement changes nothing about delivery: the skill is delivered whether or not the command is installed.

## Skill names and descriptions

A skill's name comes from the `name` line of its `SKILL.md` and is fixed once the skill is registered. It is the name of the directory an agent loads the skill from and the identifier an agent invokes it by, so instructions, other skills and permission rules that quote it would break on a rename. A request to change it is refused with `NAME_IMMUTABLE`. To use a different name, remove the skill and add it again under the new name, which resets its reach and delivered links (its bindings). The decision is recorded in the ADR "names-visible-to-agents-are-fixed".

A skill has no separate display title: Coffer's pages and the CLI show its name. Its **description** is the `description` line of its `SKILL.md`, the text agents read to decide when to use the skill, so Coffer shows that and keeps no description of its own. Nothing on the skill's record is editable. To change the description, or anything else about the skill, edit `SKILL.md` in the master folder that `coffer path skill <name>` prints, or in the skill's **Files** tab.

## Check for drift and repair it

Drift is any disagreement between what Coffer recorded as delivered and what is on disk. Coffer recognises five kinds:

| Kind | What happened | Repaired automatically |
| --- | --- | --- |
| `missing_link` | The link in the agent's skill folder was deleted. | Yes |
| `tampered_link` | The link now points somewhere other than the master folder. | Yes |
| `replaced_with_regular` | A real file or folder now occupies the link path. | No — Coffer never touches your content |
| `missing_master` | The master folder under `~/.coffer/vault/skills/` is gone. | No |
| `orphan_master` | A folder in `~/.coffer/vault/skills/` has no Coffer record. | No |

### Automatic repair at startup

Every time the daemon starts, Coffer re-creates missing links and re-points tampered ones. Each repair is recorded in the audit log with a system actor. The other three kinds are left as found and written to the daemon log with the skill, agent, path and a reason. A failure during this check never stops the daemon from starting.

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

`--fix` re-creates missing links. For a tampered link it first moves the existing link aside to `<path>.coffer-backup-<timestamp>`, then re-creates it. It prints what it repaired and what still needs you, and exits 2 if anything remains.

In the web UI, **Check copies** on the Skills page runs the same report and lists each finding with the skill, the agent (or Library), what differs and whether it needs you. A missing or repointed link has **Repair**, which puts it back; a folder in the way, a missing master and a folder not in your library have **Review…**, which opens the place to answer it. A skill's **Delivery** tab has **Check again**, which does the same for that one skill's copies.

Those three kinds need a judgement Coffer does not make for you — which of two folders to keep, what a stray folder is, where a lost master can be found — so each also offers a prompt for your agent, with **Copy prompt** and **Ask an agent** beside the finding, in the compare dialog, on the folder's pane and on the Files tab. The agent looks and tells you which button to press; it moves, deletes and edits nothing itself. The same prompts appear on the Overview's "needs you" list, and `coffer skill verify --prompt` prints them.

### Resolve a folder in the way

When an agent's copy is a real folder rather than Coffer's link — you, or the agent, replaced the link with an edited copy — the skill shows a banner and its Delivery row offers **Review…**. The dialog compares the folder with the master and offers two choices, confirmed before anything happens:

| Choice | What happens |
| --- | --- |
| **Replace it with Coffer's link** | The folder is moved to `~/.coffer/content/backup/skills/<agent>/` first, then the master is linked in its place. Nothing is lost. |
| **Adopt this folder** | Its files become the master, so every other agent gets them too; the folder is then backed up and linked the same way. |

The diff shows what happens to the side you are not keeping. Coffer never makes this choice on its own. Not sure which to keep? The dialog's prompt asks your agent to compare the folder with the master and recommend one of the two.

### Folders not in your library

A folder in `~/.coffer/vault/skills/` that no skill claims — copied in by hand, or left behind by an interrupted import — reaches no agent. It is listed under **Not in your library**, with whether its `SKILL.md` is valid and how many files it holds. **Add to library…** adds it in place, **Reveal in Finder** shows it, and **Delete folder…** moves it to `~/.coffer/content/backup/skills/orphans/` after asking. The pane's prompt asks your agent to read the folder and tell you which of the two to choose.

### When the master folder is gone

If a skill's master folder was removed outside Coffer, the skill says **Master missing**. Its Files tab offers two ways forward. **Restore it from History** puts back the newest version of `skills/<name>/` that still had files, as a new version of the vault; it cannot be chosen when the vault has no such version. **Remove the skill** removes its record and settings. From the terminal, `coffer vault history skills/<name>/` lists the folder's versions and `coffer vault restore skills/<name>/ <version>` puts one back. The tab's prompt asks your agent to look for a copy — in `~/.coffer/content/backup/skills/`, in an agent's skills folder, or at the skill's source (`coffer skill show <name> --json`) — and, once you agree, to copy it back to `~/.coffer/vault/skills/<name>/`; Coffer links it to your agents again on its next pass.

## The built-in `coffer-guide` skill

Coffer ships one skill of its own, `coffer-guide`. It is the manual an agent reads to work with Coffer well:

- Coffer's own MCP tools and when to reach for each.
- That tools hidden from the agent's tool list are still callable through `coffer__search_tools`.
- [Knowledge](/guides/knowledge): where the knowledge root is, how to read it with the agent's own file tools, how to add to it with `coffer__write`, and a catalogue of every document in every collection, with its path, title and description.
- [Memory](/guides/memory): that Coffer reads the agent's memory and never writes it, and that Coffer's notes are Markdown under the memory root, which the agent greps with its own file tools.
- That no Coffer tool waits on a human approval.

Its frontmatter description names Coffer's tools and the subjects of your collections (taken from each collection's `README.md`), so the model has something concrete to match against. The description stays within 1024 characters; if the collections do not fit, whole subjects are dropped from the end.

In every other respect it is an ordinary skill. It lives at `~/.coffer/derived/skills/coffer-guide/`, appears on the **Skills** page with a **Built-in** badge, and is delivered, reached, verified and repaired exactly like an imported skill.

### It is regenerated, so edits do not survive

Coffer rewrites `coffer-guide` from the running build at every daemon start and whenever the knowledge catalogue changes (after a curation pass, when a collection is created or deleted, and on each curation sweep so hand-added documents are picked up). A rewrite is skipped when the content is already identical. Because of this:

- Its files are read-only in the web UI.
- Any edit you make on disk is replaced at the next rewrite.

The skill is not carried by [vault sync](/guides/vault-sync). Each machine renders its own from its own collections and settings.

### It cannot be deleted, but you control its reach

Deleting `coffer-guide` is refused with `RESOURCE_PROTECTED` on every surface, because the next start would write it back. What you can change is who gets it: disable it, or narrow its reach, exactly as for any other skill.

```sh
coffer skill scope coffer-guide --agents claude-code
coffer skill disable coffer-guide
```

## Remove a skill

Removing a skill deletes every delivered link, then deletes the master folder and the skill's record. The removal is audited with a snapshot of the skill's configuration.

::: code-group

```sh [CLI]
coffer skill rm release-checklist --force
```

```text [Web UI]
Skills → the skill → ⋯ → Delete… → confirm "Delete release-checklist?"
```

:::

::: danger The master folder is the only copy
Removing a skill deletes `~/.coffer/vault/skills/<name>/`. Coffer does not keep the source folder you imported from. If you want to keep the skill but stop delivering it, disable it or set its reach to no agent instead.
:::

If an agent's copy is no longer Coffer's link, the delete is refused and nothing changes: the dialog names the folder, and you either restore it from master first or delete that folder yourself.

Removing an agent from Coffer also removes that agent's skill links. The master folders stay.

## How it works

Each skill is a `skill` resource in Coffer's registry, identified by an immutable uid. Its name is fixed once registered and its description is its `SKILL.md`'s (see [Skill names and descriptions](#skill-names-and-descriptions)).

Coffer records each delivered link in internal bookkeeping (the link path, the link mode, when it was linked). The link on disk is the live truth; the record is what `verify` compares it against. Every import, delivery, removal of a link, removal of a skill and repair is written to the audit log, which you can read on the [Activity](/guides/activity) page.

Coffer exposes no skill tools over MCP. Both supported agents read skills from disk, and a second, tool-based path would bypass each skill's reach.

For the resource model behind enable and reach, see [Resource framework](/architecture/resource-framework).

## Troubleshooting

**An agent does not see a skill.** Check that the skill is enabled and that its reach includes the agent: `coffer skill scope <name>`. Check that the agent itself is enabled. Then run `coffer skill verify` to see whether its link is missing or blocked by a foreign folder.

**Adding a skill from Git fails.** The dialog and the command show git's own message. `could not read Username` or `Permission denied (publickey)` means this machine's git has no credential for that repository: check that `git clone <url>` works in a terminal first. A ref or folder that does not exist is named in the message too.

**An archive is refused.** The message names the entries that could write outside the archive, the symlinks, or the size cap it would pass. Re-create the archive from the skill's folder itself.

**Adding a skill is refused.** The error names the rule the folder broke and, for a frontmatter problem, the field and the check it failed (for example `description: String should have at most 1024 characters`). The most common causes are a `name` with uppercase letters or dots, a missing or over-long `description`, or a symlink inside the folder that points outside it.

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
