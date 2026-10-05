---
title: Skills
description: Keep one library of AgentSkills-standard skills in Coffer — added from a folder, an archive or a Git repository — and deliver each one into the skill directories of the agents you choose.
---

# Skills

Coffer keeps one master library of skills on your machine and links each skill into the skill directory of every agent that should have it. This page covers adding skills from a folder, an archive or a Git repository, updating a skill from its repository, adopting skills an agent already has, choosing which agents a skill reaches, viewing and editing skill files, the commands a skill needs, skill names, checking agents' copies, and Coffer's own built-in `coffer-guide` skill. How it works underneath is on the [Skills architecture](/architecture/skills) page.

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
| `name` | lowercase letters, digits and `-`; starts with a letter or digit; at most 64 characters |
| `description` | non-empty, at most 1024 characters |
| Symlinks inside the folder | none may point outside the folder or at a folder (a link to a file counts as that file's bytes) |
| Total folder size | at most 50 MB |

Coffer also reads the optional `license` field, the experimental `allowed-tools` field (a list, or a comma- or space-separated string), and `requires:` — the command-line tools the skill drives, which Coffer checks on this machine and shows on the skill's **Requires** tab and the [CLIs page](/guides/clis), the Coffer secrets it needs (see [Secrets a skill needs](#secrets-a-skill-needs)) and the MCP servers and custom tools it calls (see [Tools a skill needs](#tools-a-skill-needs)). Any other frontmatter key is kept and ignored.

A folder that breaks a rule is refused with the reason, and nothing is written to the vault.

## Where skills live

| Path | What it is |
| --- | --- |
| `~/.coffer/vault/skills/<name>/` | The master folder. This is the only copy you edit. |
| `<config_dir>/skills/<name>` | The delivered link in each agent, for example `~/.claude/skills/release-checklist` or `~/.codex/skills/release-checklist`. It points at the master folder. |

Because the delivered path is a link, editing `SKILL.md` from inside `~/.claude/skills/<name>/` edits the master, and every other agent sees the change on its next read. Deleting a file there deletes it from the master too.

## The Skills page

**Skills** (under Capabilities in the sidebar) is your library beside the skill you are reading. The list on the left has a search box and **Check copies**, and groups skills by what needs you: **Needs attention**, **In use**, **Unused**, **Off** and **Built-in**. A row shows the skill's name and its reach as a badge — its description is on the skill's page — and, under the name, only the one thing that needs you: **Master missing**, **Folder in the way in Codex**, **Needs jq · not installed**, **Tool off**, **Secret missing**, **Source unreachable** or **Update available**. The **Reach** filter under the search box narrows the list to the skills that reach one agent (an agent's Skills tab links here with that agent chosen, `/skills?agent=<uid>`). Tick rows (a box appears on hover) to set the reach of several skills at once or to delete them; the selection shows as a bar under the search box and in the reading pane. Folders in `~/.coffer/vault/skills/` that no skill claims are listed apart, under **Not in your library** (see [below](#folders-not-in-your-library)).

The open skill's header carries its name, a state pill (**In use**, **Off**, **Master missing**, **Folder in the way**, **Command missing**, **Tool off**, **Secret missing**, **Source unreachable**), and two fixed buttons: **Reach** and a **⋯** menu with **Open in editor**, **Reveal in Finder**, **Copy master path**, **Check agents' copies**, **Turn off** (removes it from every agent and keeps who you chose) and **Delete…**. Above its tabs, a banner says what needs you — a folder in the way, a missing command, a tool that is off, an update — with the one action that answers it.

Choosing a skill opens it on the right, at its own address (`/skills/<name>`), with four tabs:

| Tab | What it shows |
| --- | --- |
| **Files** | The skill's files beside the open file, opening on `SKILL.md` rendered. **Preview / Source** switches a Markdown file between rendered and raw text, and **Open in editor** opens it in your editor. A binary file offers **Open in default app** and **Reveal in Finder**; a very large file shows its start, read-only. A Git skill shows its source above the files. |
| **Delivery** | Every agent and the state of its copy: **Linked**, **Copied, not linked** (where links are not allowed), a folder in the way (with **Review…**), or not delivered and why. **Check again** looks at every copy afresh. |
| **Requires** | What the skill says it needs, in four lists: **Commands** (each with its state and a link to the CLIs page), **Secrets** (set or not, with **Open Secrets**), **Tools** (the MCP servers and custom tool groups it calls, each on or off and linking to its page) and **Skills** (the other skills it loads). Installing and logging in happen on the CLIs page. A skill that never declared anything reads as unknown instead; see [Declared or not](#declared-or-not). |
| **History** | The skill folder's versions, newest first, each with what it did, who wrote it and when, and the diff of the chosen one, with **Restore this version…**. See [Look back at an earlier version](#look-back-at-an-earlier-version). Coffer's built-in skill has this tab too, and it says the skill has no history: it is rebuilt from the running build at every start and is not stored in the vault. |

The Skills page lists only the skills Coffer manages. Skills an agent has that Coffer does not manage are on that agent's **Skills** tab, where you can adopt them (see [below](#adopt-skills-an-agent-already-has)).

## Add a skill

A skill comes from one of three places. Whichever you use, Coffer first shows what it found — the skill or skills, their names and descriptions, any that cannot be added and why, and any whose name is already taken — and adds nothing until you confirm. Closing the dialog leaves nothing behind.

### From a folder

```text
Skills → Add skill → From a folder → paste the path, or Choose… → Add skill
```

Coffer reads the skill's name from its `SKILL.md` frontmatter and copies the folder to `~/.coffer/vault/skills/release-checklist/`. It records the path it came from, but does not track it afterwards: a later change to the source folder is not picked up until you add it again. In the web UI, a folder whose top has no `SKILL.md` but whose subfolders do offers those subfolders as a choice.

### From an archive

```text
Skills → Add skill → From an archive → Choose file… (or drop a .zip or .skill file) → Add skill
```

A `.zip` or `.skill` archive holds a skill when its `SKILL.md` is at the top of the archive or one folder down. An archive holding several skills lists them all, and you pick which to add.

Coffer refuses the whole archive, naming the entries, before unpacking any of it when an entry has an absolute path or a `..` in its path, when an entry is a symlink, or when it would unpack to more than 50 MB. An archive with no `SKILL.md` at the top or one folder down is refused with that message.

### From a Git repository

```text
Skills → Add skill → From Git → Repository URL, and optionally Branch or tag and Folder → Add skill
```

Coffer clones the repository with this machine's own `git`, resolves the branch, tag or commit you gave (the default branch when you gave none) to one commit, and looks for skills in the folder you named by the same rule as an archive. A GitHub folder address such as `https://github.com/acme/agent-skills/tree/main/terraform-plan` is read as the repository, the branch and the folder.

The skill is **pinned** to the commit it was copied from. It does not change when the repository does; see [Update a skill from its repository](#update-a-skill-from-its-repository).

::: info Which repositories Coffer can reach
Git runs without a prompt, and Coffer gives it no credential and stores none. A public repository always works. A private one works when this machine's git can already clone it — through a credential helper such as the macOS keychain, or SSH keys — because Coffer uses your own git configuration. If git would ask for a password, the add fails with git's message instead. A repository URL that carries a user name or password (`https://user:token@…`) is refused, because the URL is stored in the vault and shown on the skill's page; let the credential helper or an SSH key supply it. An archive's scripts keep the executable bit the archive recorded.
:::

### When the name is taken

Adding a skill whose `name` already exists is refused with a conflict. To replace the existing skill with the new content, choose **Replace** on that row in the dialog. The master folder's content is swapped in one step, and the skill's reach and its delivered links are kept.

A freshly added skill is enabled and reaches every registered agent, so it is linked into each agent's skill folder straight away.

## Update a skill from its repository

A skill added from a Git repository shows its source on its page: the repository, the folder, the pinned commit and whether an update is waiting. Coffer checks the repository in the background on a schedule you choose in **Settings › General › Check skills for updates** — **Every 6 hours** (the default), **Every day**, **Every week** or **Only when I ask** — and you can check at any time with **Check for updates**, in every setting. The choice is kept on this machine only (in `~/.coffer/daemon-config.json`), is not synced, and takes effect at once.

```text
Skills → the skill → Check for updates, then Hand off to <Agent> to update when an update is available
```

When the branch or tag has new commits that change the skill's folder, the skill shows **Update available** with the commit range from the pinned commit to the new one, on the Skills page and on the skill's page. **Coffer does not apply an update itself.** There is no update preview, no **Keep mine**, **Take theirs** or **Compare**, and no merge of its own: bringing new upstream content into a folder that may carry your edits is a job for your agent.

While an update is waiting, the skill also offers **Open in editor** (the master folder) and **View upstream changes**: for a GitHub or GitLab repository a link to the host's compare page from the pinned commit to the new one, and for any other host the copyable commit range and the commit subjects instead. Coffer draws no diff of its own. The skill offers one main button, **Hand off to &lt;Agent&gt; to update** (its menu holds the other installed agent and **Copy prompt**), whether or not you edited the skill. Coffer builds the prompt when you press it, so it is never stale. It names the skill's master folder as the only place to edit, the pinned and new commits with their subjects, the repository, branch and folder to read the update from (read-only, with no credential in the URL), and the files you edited since the pin, or says there are none. The agent brings the new commit's content into the master folder, keeps what your edits were for, asks you where the two really disagree, and shows you the diff; it does not record the merge itself.

When the files look right, choose **I merged it** beside the button and confirm. That moves the pin to the new commit and leaves the master folder exactly as the agent left it. Your edits still count as local edits against the new pin, so the next update's prompt lists exactly the edits you carried over. Only the update that is waiting can be recorded: the pinned commit, or a commit that is not on the branch, is refused with `SKILL_UPDATE_NOT_PENDING`.

**API:** `POST /skills/{uid}/source/check` checks, `POST /skills/{uid}/source/handoff` answers the newest commit and the prompt (refused with `SKILL_UPDATE_NOT_PENDING` when nothing newer changes the folder), and `POST /skills/{uid}/source/merged` records the merge.

If the repository can no longer be reached, the skill keeps working from its pinned copy. Its page shows git's message and when the last check succeeded, and nothing changes until a check succeeds again.

To move a Git skill to another repository, branch or folder, use **Change source…** in its Source block. Coffer clones the new source and lists the names of the files that would be added, removed or changed against your current folder (names only, no diff); nothing is replaced until you confirm, and then the folder is swapped in at once, keeping the skill's name, reach and links. Cancelling leaves everything as it was. (`POST /skills/{uid}/source/change`, then `…/source/change/apply`.)

A skill added from a folder or an archive has no source to update from: add it again with **Replace**.

## Adopt skills an agent already has

Agents accumulate skills that Coffer does not manage — a folder you copied into `~/.claude/skills/` by hand, or one a tool installed into Codex's `~/.agents/skills/`. Coffer lists these as **unmanaged** skills so you can bring them into the library, or delete them.

Coffer scans:

- `<config_dir>/skills/` for every agent, and
- `~/.agents/skills/` for Codex, which reads that location as well.

Anything there that is not a Coffer-managed link is unmanaged. Codex's own `.system` entry is never listed.

### List unmanaged skills

```text
Agents → choose the agent → Skills tab → the agent's own skills
```

Each entry shows its name, path, location and whether its `SKILL.md` is valid. An invalid entry shows the reason.

### Preview one

Read an unmanaged skill before you decide what to do with it. Nothing here changes the folder.

```text
Agents → choose the agent → Skills tab → click the row
```

The detail page has an **Overview** tab (the `SKILL.md` description, the folder's path and location) and a **Files** tab (the folder's tree and a read-only preview of each file). An invalid folder opens too, with the reason at the top. The page header carries **Adopt** and a **⋯** menu with **Delete…**; the title bar's back arrow returns to the agent's Skills tab. Files are shown in the same tree and viewer as everywhere else, so opening one in your editor or revealing it is on the viewer. File reads stay inside the folder, as they do for a managed skill.

### Adopt one

Adopting moves the folder into `~/.coffer/vault/skills/<name>/`, registers it as a skill, and puts a managed link where the agent expects it.

```text
Agents → choose the agent → Skills tab → Adopt on the row, or Adopt on the skill's page
```

Adopt opens a small form with the **name in Coffer** (checked against the library as you type; it defaults to the folder's own) and the **reach** the skill starts with — every agent, only the agents you choose, or off. An error stays inside the form.

- A folder adopted from `<config_dir>/skills/` is replaced in place by the link.
- A folder adopted from `~/.agents/skills/` is moved out of that directory and the link is placed in `<config_dir>/skills/`. Codex reads both locations, so it keeps seeing the skill.

Adoption is refused, with nothing moved, when the folder has no valid `SKILL.md`, when its name matches a skill already in the library, or when the entry is a symlink pointing somewhere outside Coffer's store (shown as **Foreign link**). If anything fails before the skill is registered, the original folder stays exactly where it was.

After adoption the skill is an ordinary managed skill and follows the same delivery rules as any other: with the default reach it belongs to every agent (over REST the adopt call takes the same `name` and `reach`), and the other agents receive their links at the next reconcile (see [When delivery happens](#when-delivery-happens)).

### Delete an unmanaged skill

To remove an unmanaged folder from disk without adopting it:

```text
Agents → choose the agent → Skills tab → ⋯ › Delete… on the row, or ⋯ › Delete… on the skill's page
```

This deletes only that folder. It never touches the master library. Coffer never deletes an unmanaged folder on its own.

## Choose which agents get a skill

Two settings on the skill decide where it is delivered, and nothing else does:

- **Enabled** — a disabled skill is delivered nowhere.
- **Reach** (the skill's scope) — which agents it is for.

| Reach | Effect |
| --- | --- |
| All agents (no scope) | Delivered to every registered agent, including agents you register later. This is the default. |
| Chosen agents | Delivered only to the agents you pick. |
| No agent selected (Chosen agents with nothing ticked) | Delivered to nobody. The skill stays in the library, listed and synced. |

A skill is delivered to an agent if and only if the skill is enabled **and** its reach includes that agent. There is no per-agent switch for "this agent gets no skills"; to keep an agent away from a skill, leave it out of that skill's reach.

```text
Skills → the Reach button on the skill's row (or on its detail page)
       → Off | All agents | Chosen agents
```

The Reach button shows a badge for the current answer — the marks of its agents, **All agents** or **Off**, never a count. The panel saves every change as you make it ("Applying…", then "✓ Saved"); **All agents** includes agents you register later. Saving a change delivers it agent by agent: if one agent's copy can't be placed, its row says why and offers **Retry** or **Untick**. To change several skills at once, select their rows and use the selection bar's reach control.

::: info Reach is set per machine
Reach and the enabled flag apply to the machine you set them on. [Vault sync](/guides/vault-sync) carries the skill itself — its files and metadata — to your other machines, but each machine keeps its own reach.
:::

### When delivery happens

Coffer reconciles an agent's skills whenever something that affects delivery changes: a skill is imported, removed, enabled, disabled or has its reach edited; an agent is registered or has its config directory changed; or a sync round imports new skills. Each reconcile creates the links the agent should have and removes the ones it should no longer have. Removing a link never touches the master folder.

An agent whose config does not parse is left alone until it reads again: its links are neither added nor removed.

### Link, junction or copy

| Platform | How the skill is delivered |
| --- | --- |
| macOS, Linux | A directory symlink. |
| Windows | A directory symlink; if that is not permitted, a directory junction; if the filesystem supports neither (FAT32, some network shares), a full copy. |

A copied delivery follows the master folder at the next repair pass. The skill's **Delivery** tab shows that agent's copy as **Copied, not linked**, with the reason.

If something that is not a Coffer link already sits at `<config_dir>/skills/<name>`, Coffer reports a conflict for that skill (a folder in the way) and leaves the existing file or folder untouched. The rest of the skills are still delivered. See [Resolve a folder in the way](#resolve-a-folder-in-the-way).

## View and edit skill files

The master folder is a normal directory, so the way to edit a skill is to open `~/.coffer/vault/skills/<name>/` in your editor or shell. Changes take effect on the agent's next read, with no import step. The skill's **⋯** menu has **Copy master path**.

```text
Skills → choose the skill → Files tab → pick a file → Open in editor
```

The Files tab is read-only. It offers **Open in editor** and **Reveal in Finder** on a text file, and **Open in default app** and **Reveal in Finder** (your system's file manager) on a binary one; the skill's **⋯** menu opens or reveals the whole folder. Open in editor uses the editor chosen in **Settings › General**.

Coffer writes no file inside a skill's folder on your behalf, so there is no save to conflict with your editor or an agent: what they save is what the tab shows next, and every such edit becomes a version in the vault's history. See [Editing the vault by hand](/guides/vault-files). To add a file to a skill, create it in the master folder with your editor or shell.

### Look back at an earlier version

To look back at an earlier version of a skill, open its **History** tab. It is one card split by a divider you can drag. On the left are the versions of the skill's folder, newest first, under **Versions** with their count. Each row says what the version did (*Added &lt;file&gt;*, *Removed &lt;file&gt;*, *Changed &lt;file&gt;*, *Changed N files*, or *Restored the version of &lt;date&gt;*), who wrote it, when, and the lines it moved (+N −M). The writer reads **You**, **Edited on disk** (your editor, a shell, or an agent's own file tools), an agent by product name, **Coffer** or **Sync**. The newest is marked **Current** and is chosen when the tab opens. On the right are the chosen version's short id, writer and time, and the diff of every file it changed; for any other version a switch shows **Changes in this version** or **Compare with current**.

**Restore this version…** asks first: every file of the folder goes back to that version, and files added since are removed, all **as a new version**, so nothing in the history is lost. It is recorded in [Activity](/guides/activity). If the folder changed since you opened the tab, the restore is refused with `VAULT_FILE_STALE`; reopen the tab and try again. You can read the same versions with git: `git -C ~/.coffer/vault log -p -- skills/<name>/`. See [Bring back an earlier version](/guides/knowledge#bring-back-an-earlier-version).

## Commands a skill needs

A skill can say which command-line tools it relies on with `requires` in its frontmatter:

```yaml
---
name: gh-triage
description: Label new issues, find duplicates, ask for missing details.
requires: [jq, "gh>=2.40", uv]
---
```

Each entry is a command name, optionally with a minimum version (`gh>=2.40`); `requires: {commands: [...]}` and entries like `{command: gh, version: "2.40"}` are read too. The skill's **Requires** tab lists them, each linking to its page on the CLIs page. Declaring a requirement changes nothing about delivery: the skill is delivered whether or not the command is installed.

## Secrets a skill needs

A skill whose commands need a token or key names the Coffer secret under `secrets:` in the mapping form of `requires`:

```yaml
---
name: gh-triage
description: Label new issues, find duplicates, ask for missing details.
requires:
  commands: [jq, "gh>=2.40"]
  secrets: [GITHUB_TOKEN]
---
```

Each entry is a secret's name in Coffer's secret store, never its value. Only the mapping form carries `secrets:`; the list form (`requires: [jq, gh]`) names commands only. A name the secret store would not accept, or one given twice, is skipped with a warning, and a key other than `commands`, `secrets` and `tools` is refused: Coffer reports it as a warning and reads nothing under it.

You set the value yourself on the [Secrets page](/guides/secrets), and allow `coffer run` to use that secret there once ([Secrets → Allow `coffer run` to use it](/guides/secrets#allow-coffer-run-to-use-it)). The skill's commands then receive it when they run under `coffer run --secret`, which sets it only in that command's environment:

```sh
coffer run --secret GITHUB_TOKEN -- gh issue list
```

The skill's **Requires** tab lists each declared secret below its commands, as **Set** or "secret GITHUB_TOKEN is not set" with **Open Secrets**. Coffer answers that from the secret store by name alone and never reads the value. A skill with a secret that is not set also says so in its row and in a banner above its tabs, and appears on the Overview's **Needs you** list, whose action opens the Secrets page. As with commands, the skill is delivered whether or not its secrets are set.

## Tools a skill needs

A skill that calls an MCP server or a custom tool names it under `tools:`, next to `commands:` and `secrets:`, in the mapping form of `requires`:

```yaml
---
name: invoice-chaser
description: Find overdue invoices and draft reminders.
requires:
  commands: [jq]
  secrets: [BILLING_TOKEN]
  tools: [github, {name: billing-api, why: Reads invoices.}]
---
```

Each entry is the name the MCP server or the custom tool group has in Coffer, either bare or as a mapping with a `why` line. Only the mapping form carries `tools:`. A name Coffer does not know (no MCP server or tool group by that name) is skipped with a warning, shown on the [CLIs page](/guides/clis); it never stops the skill from being imported or delivered.

The skill's **Requires** tab lists each tool under **Tools** as on, off or failing, linking to its page. A required tool that is off puts the skill under **Needs attention** with the banner **Tool off**, whose action turns it on. As with commands and secrets, the skill is delivered whether or not its tools are on.

## Requirements a profile declares {#profile-declared-requirements}

A skill library may keep per-skill profiles at `<skill folder>/profiles/<name>.md`: a `default.md` plus one file per environment, each with YAML frontmatter ([Writing skill libraries](/guides/writing-skill-libraries) explains why). A profile's frontmatter may carry the same `requires:` as `SKILL.md`, with commands, secrets and tools:

```yaml
---
carrier: Skill(example-log-search)
requires:
  commands:
    - command: gh
      login_check: gh auth status
  secrets: [EXAMPLE_TOKEN]
---
```

An agent picks one profile when it runs, and Coffer cannot know which. So Coffer reads the union of `SKILL.md`'s `requires:` and that of every `profiles/*.md`, each time, and says which profile declared each entry: the **Requires** tab shows "in profile example-org" on the row, and [CLIs](/guides/clis) shows `skill-name · example-org` under **Needed by**. An entry `SKILL.md` itself declares carries no profile. A command, secret or tool declared in several places is one requirement; for a command Coffer keeps the highest minimum version and the first title, `why` and login check. A warning from a profile names its file, `profiles/<name>.md`. Coffer reads only what the files declare and never scans them to guess.

## Declared or not, and checking with an agent {#declared-or-not}

Coffer tells a skill that declares nothing from one that has not declared. A skill whose `SKILL.md` and every `profiles/*.md` carry no `requires:` key is **undeclared**: its **Requires** tab reads that what it needs is unknown, because it doesn't say, and offers **Add requires with an agent**. A skill with a `requires:` key anywhere, even an empty `requires: []`, is declared; an empty one means it needs nothing, and the tab reads **Nothing required**. Unknown shows on the **Requires** tab only: the Skills list, the attention items and the Overview don't mention it, and delivery is unchanged.

A declared skill's tab carries **Check with an agent** at the top, and the Skills list's selection bar has the same button for the ticked skills, one prompt for all of them. The button is the usual hand-off split button, labelled with the agent it starts (**Check with Claude Code**, or **Add requires with Claude Code** for a skill that never declared), with **Copy prompt** and the other agent in its menu; picking the other agent makes it the hand-off agent, and the label follows. On the skill's tab a one-line note beside the button says what the agent will do. Coffer builds the prompt when you press it, naming each skill's master folder, whether it declares anything and where it came from; for a Git-imported skill it says edits are kept as local edits across updates and suggests proposing them upstream too.

Everything the agent says is a suggestion you can decline. It reads the whole skill folder, proposes what it would change and why, asks which to apply, edits only the master folder and only what you agree to, shows you the diff and commits nothing. It doesn't restructure a skill, add a profiles folder or rename files, and a secret value or personal detail already in a file stays there if you prefer; it may only point it out and suggest Coffer's secret store. Coffer reads only the `requires:` declaration; see [Writing skill libraries](/guides/writing-skill-libraries) for the optional conventions, which Coffer never requires.

## Where a skill's scripts keep their files

A skill's scripts write the logs, operation journals and temporary files they generate under `~/.coffer/skill-data/<skill-name>/`, one folder per skill; `coffer path skill-data` prints the directory. It is outside the vault, so none of it syncs, and a skill must not write inside its own folder (that is the vault) or elsewhere in `~/.coffer`. Coffer deletes files there once they are older than the **Skill working files** retention window (30 days by default, **Settings → Data → History**), so anything that has to last does not belong there. The `coffer-guide` skill tells agents the same.

## Skill names and descriptions

A skill's name comes from the `name` line of its `SKILL.md` and is fixed once the skill is registered. It is the name of the directory an agent loads the skill from and the identifier an agent invokes it by, so instructions, other skills and permission rules that quote it would break on a rename. A request to change it is refused with `NAME_IMMUTABLE`. To use a different name, remove the skill and add it again under the new name, which resets its reach and delivered links (its bindings). The decision is recorded in the ADR "names-visible-to-agents-are-fixed".

A skill has no separate display title: Coffer's pages show its name. Its **description** is the `description` line of its `SKILL.md`, the text agents read to decide when to use the skill, so Coffer shows that and keeps no description of its own. Nothing on the skill's record is editable. To change the description, or anything else about the skill, edit `SKILL.md` in the master folder (`~/.coffer/vault/skills/<name>/`); the skill's **Files** tab opens it in your editor.

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

**Check copies** on the Skills page runs the report and lists each finding with the skill, the agent (or Library), what differs and whether it needs you. A missing or repointed link has **Repair**, which puts it back (a tampered link is first moved aside to `~/.coffer/content/backup/skills/<agent>/<name>.coffer-backup-<timestamp>`, outside the agent's skills directory, so the agent never loads it); a folder in the way, a missing master and a folder not in your library have **Review…**, which opens the place to answer it. A skill's **Delivery** tab has **Check again**, which does the same for that one skill's copies.

Those three kinds need a judgement Coffer does not make for you — which of two folders to keep, what a stray folder is, where a lost master can be found — so each also offers a prompt for your agent, with **Hand off to &lt;Agent&gt;** (and **Copy prompt** in its menu) beside the finding, in the compare dialog, on the folder's pane and in the banner of a skill whose master is gone. The agent looks and tells you which button to press; it moves, deletes and edits nothing itself. The same prompts appear on the Overview's "needs you" list.

### Resolve a folder in the way

When an agent's copy is a real folder rather than Coffer's link — you, or the agent, replaced the link with an edited copy — the skill shows a banner and its Delivery row offers **Review…**. The dialog compares the folder with the master and offers two choices, confirmed before anything happens:

| Choice | What happens |
| --- | --- |
| **Replace it with Coffer's link** | The folder is moved to `~/.coffer/content/backup/skills/<agent>/` first, then the master is linked in its place. Nothing is lost. |
| **Adopt this folder** | Its files become the master, so every other agent gets them too; the folder is then backed up and linked the same way. |

The diff shows what happens to the side you are not keeping. Coffer never makes this choice on its own. Not sure which to keep? The dialog's prompt asks your agent to compare the folder with the master and recommend one of the two.

### Folders not in your library

A folder in `~/.coffer/vault/skills/` that no skill claims — copied in by hand, or left behind by an interrupted import — reaches no agent. It is listed under **Not in your library**, with whether its `SKILL.md` is valid, how many files it holds and when Coffer found it. Its files open in the same locked file tree and viewer as a skill's **Files** tab, read-only. **Add to library…** adds it in place, **Reveal in Finder** shows it, and **Delete folder…** moves it to `~/.coffer/content/backup/skills/orphans/` after asking. The pane's prompt asks your agent to read the folder and tell you which of the two to choose.

### When the master folder is gone

If a skill's master folder was removed outside Coffer, the skill says **Master missing**. The banner on its page offers two ways forward. **Hand off to &lt;Agent&gt;** (and **Copy prompt**) gives your agent a prompt that asks it to look for a copy — in `~/.coffer/content/backup/skills/`, in an agent's skills folder, in the vault's git history, or at the skill's source — and, once you agree, to copy it back to `~/.coffer/vault/skills/<name>/`; Coffer links it to your agents again on its next pass. **Delete skill…** removes the skill's record and settings instead.

## The built-in `coffer-guide` skill

Coffer ships one skill of its own, `coffer-guide`. It is the manual an agent reads to work with Coffer well:

- Coffer's own MCP tools and when to reach for each.
- That tools hidden from the agent's tool list are still callable through `coffer__search_tools`.
- [Knowledge](/guides/knowledge): where the knowledge root is, how to read it with the agent's own file tools, how to write into it and tidy it, and a catalogue of every document in every collection, with its path, title and description.
- [Memory](/guides/memory): that Coffer reads the agent's memory and never writes it, and that Coffer's notes are Markdown under the memory root, which the agent greps with its own file tools.
- [CLIs](/guides/clis#what-your-agents-see): that `coffer cli list` prints the command-line tools Coffer manages — what each is for, who needs it and whether it is ready here.
- That no Coffer tool waits on a human approval.

Its frontmatter description names Coffer's tools and the subjects of your collections (taken from each collection's `README.md`), so the model has something concrete to match against. The description stays within 1024 characters; if the collections do not fit, whole subjects are dropped from the end.

In every other respect it is an ordinary skill. It lives at `~/.coffer/derived/skills/coffer-guide/`, appears on the **Skills** page with a **Built-in** badge, and is delivered, reached, verified and repaired exactly like an imported skill.

### It is regenerated, so edits do not survive

Coffer rewrites `coffer-guide` from the running build at every daemon start and whenever the knowledge catalogue changes (when a collection is created or deleted, and on each knowledge sweep so hand-added documents are picked up). A rewrite is skipped when the content is already identical. Because of this:

- Its files are read-only in the web UI.
- Any edit you make on disk is replaced at the next rewrite.

The skill is not carried by [vault sync](/guides/vault-sync). Each machine renders its own from its own collections and settings.

### It cannot be deleted, but you control its reach

Deleting `coffer-guide` is refused with `RESOURCE_PROTECTED` on every surface, because the next start would write it back. What you can change is who gets it: disable it, or narrow its reach, exactly as for any other skill.

## Remove a skill

Removing a skill deletes every delivered link, then deletes the master folder and the skill's record. The removal is audited with a snapshot of the skill's configuration.

```text
Skills → the skill → ⋯ → Delete… → confirm "Delete release-checklist?"
```

::: danger The master folder is the only copy
Removing a skill deletes `~/.coffer/vault/skills/<name>/`. Coffer does not keep the source folder you imported from. If you want to keep the skill but stop delivering it, disable it or set its reach to no agent instead.
:::

If an agent's copy is no longer Coffer's link (it is a regular folder now), Coffer will not remove it. The delete stops with "Nothing was deleted" and names the folder; the dialog then offers **Delete, keep &lt;agent&gt;'s folder**, which deletes the skill and leaves that folder to the agent, or you cancel and review the edit first (see [Resolve a folder in the way](#resolve-a-folder-in-the-way)). Selecting several skills and choosing **Delete…** reports each one: the dialog says "Deleted N of M" and names those it refused, with **Delete N skills, keep their folders** for the rest.

Removing an agent from Coffer also removes that agent's skill links. The master folders stay.

## How it works

Each skill is a `skill` resource in Coffer's registry, identified by an immutable uid. Its name is fixed once registered and its description is its `SKILL.md`'s (see [Skill names and descriptions](#skill-names-and-descriptions)).

Coffer records each delivered link in internal bookkeeping (the link path, the link mode, when it was linked). The link on disk is the live truth; the record is what **Check copies** compares it against. Every import, delivery, removal of a link, removal of a skill and repair is written to the audit log, which you can read on the [Activity](/guides/activity) page.

Coffer exposes no skill tools over MCP. Both supported agents read skills from disk, and a second, tool-based path would bypass each skill's reach.

For the resource model behind enable and reach, see [Resource framework](/architecture/resource-framework).

## Troubleshooting

**An agent does not see a skill.** Check that the skill is enabled and that its reach includes the agent (the skill's **Reach** button). Then use **Check copies** to see whether its link is missing or blocked by a foreign folder.

**Adding a skill from Git fails.** The dialog shows git's own message. `could not read Username` or `Permission denied (publickey)` means this machine's git has no credential for that repository: check that `git clone <url>` works in a terminal first. A ref or folder that does not exist is named in the message too.

**An archive is refused.** The message names the entries that could write outside the archive, the symlinks, or the size cap it would pass. Re-create the archive from the skill's folder itself.

**Adding a skill is refused.** The error names the rule the folder broke and, for a frontmatter problem, the field and the check it failed (for example `description: String should have at most 1024 characters`). The most common causes are a `name` with uppercase letters or dots, a missing or over-long `description`, or a symlink inside the folder that points outside it.

**A skill shows the Copied badge.** The agent's filesystem does not support links (this happens only on Windows). The copy does not follow edits to the master. After editing, trigger a new delivery, for example by disabling and re-enabling the skill.

**Check copies reports `replaced_with_regular`.** Something other than Coffer put a real folder at the link path. Move it away yourself (adopt it first if you want to keep it), then choose **Check again** on the skill's **Delivery** tab.

## Related

- [Knowledge](/guides/knowledge) — the catalogue that `coffer-guide` carries
- [Memory](/guides/memory)
- [Agents](/guides/agents)
- [Vault sync](/guides/vault-sync)
- [CLI reference](/reference/cli)
- [Skill Manager spec](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/skill-manager/spec.md)
- [Cross-Platform Skill Delivery](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/cross-platform-skill-delivery.md) and [Coffer Ships Its Own Manual as a Skill Resource](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/coffer-ships-its-own-skill.md)
