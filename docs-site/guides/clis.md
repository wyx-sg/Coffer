---
title: CLIs
description: Declare the command-line tools a skill needs, see on one page which of those and of your MCP servers' launchers are missing, too old or not logged in, and hand the fix to your agent with a prompt Coffer writes for this machine.
---

# CLIs

Many skills drive a command-line tool — `gh` to triage issues, `jq` to filter JSON, `aws` to read a bucket. When the tool is missing, older than the skill expects or not logged in, the agent following the skill fails at the step that calls it. MCP servers depend on commands too: a stdio server started with `uvx` cannot start without `uv`. The **CLIs** page shows every command your skills say they need and every launcher your MCP servers start with, checked on this machine, with the problems first.

## Declare what a skill needs

A skill lists its commands in its `SKILL.md` frontmatter under `requires:`:

```yaml
---
name: gh-triage
description: Label new GitHub issues, find duplicates and ask for missing details.
requires:
  - command: gh
    title: GitHub CLI
    min_version: "2.40"
    login_check: gh auth status
    login: gh auth login
    why: Reads and labels issues.
  - command: jq
    min_version: "1.6"
    why: Filters issue JSON.
  - uv
---
```

| Field | Meaning |
| --- | --- |
| `command` | The command's bare name, as typed in a terminal. Required. |
| `title` | A display name, e.g. `GitHub CLI`. |
| `min_version` | The lowest version the skill works with, as dotted numbers. Quote it — unquoted, YAML reads `2.40` as the number `2.4`. |
| `login_check` | A subcommand **of the same command** that exits 0 when you are logged in, e.g. `gh auth status`. |
| `login` | The command that logs you in. Coffer never runs it; the [login prompt](#logging-in) names it for your agent. |
| `why` | One line on what the skill uses the command for. |

A skill that keeps per-environment profiles (`profiles/<name>.md`) may declare commands in a profile's frontmatter too, in the same shape. An agent picks one profile at run time, which Coffer cannot know, so Coffer reads the union of `SKILL.md` and every profile. **Needed by** names the profile after the skill, as `coffer-investigating-logs · shopee-account`; a command several of them declare is one entry with the highest minimum. See [Requirements a profile declares](/guides/skills#profile-declared-requirements).

A bare name (`- uv`) is a command with no conditions, and `- "node>=20.1"` a command with a minimum; `requires: [jq, "gh>=2.40"]` and `requires: {commands: [...]}` are read the same way. An entry Coffer cannot use — a path instead of a name, a login check that runs a different program — is skipped with a warning on the CLIs page, and so is a `tools:` name that matches no MCP server or custom tool group (see [Tools a skill needs](/guides/skills#tools-a-skill-needs)); it never stops the skill from being imported or delivered.

Coffer reads `requires:` from the skill's folder every time it checks, so an edit in your editor is picked up by the next **Check** without importing the skill again. This top-level `requires:` lists commands; it is unrelated to `metadata.requires`, which a skill library uses for [the skills a domain depends on](/guides/writing-skill-libraries#declared-dependencies).

## Commands Coffer runs itself

Coffer needs one command of its own: `git`, which keeps the vault's history and syncs it. It is always listed, titled Git, with **Coffer** under **Needed by** naming what it is used for (Vault history · Sync), whether or not any skill or server needs it too. If `git` is missing, its banner says what Coffer can't do without it and offers the same hand-off as any other command. Overview lists it too, as a CLI that needs you, saying what Coffer can't do without it (keep the vault's history, sync the vault); a missing `git` is an error there because the vault's history stops. The Sync page shows its own **git missing** card as well.

## Launchers your MCP servers start with

Every MCP server that is on and started as a command (stdio) needs its launcher. Coffer lists the launcher under the command that provides it — `uv` for `uvx`, `node` (Node.js) for `npx`, `bun` for `bunx`, and the launcher itself for anything else, such as `docker`. Nothing needs declaring: the server's own command is enough. A launcher has no minimum version and no login check; a server started from a path (`./run.sh`) is a file, not a command, and is not listed, and a server that is off or reached over HTTP needs nothing.

## How Coffer checks a command

One row per command, however many skills and servers need it:

1. **Found?** The command is looked up on your real `PATH` — your login shell's, merged with the one the daemon inherited — the same `PATH` an agent gets when you start it from a terminal. A command installed where only your shell looks (Homebrew, `~/.local/bin`) is found.
2. **Version.** Coffer runs `<command> --version` and compares the version with the **highest** minimum any skill asks for. A version it cannot read is shown as unknown and is not called too old.
3. **Logged in?** If a skill declared a login check, Coffer runs it only when you press **Check** (listing the page, and the attention list that polls it, never run one) — without a shell, with a 10-second limit — and looks only at whether it succeeded. **Its output is thrown away unread**: a login check can print your account name or a token, and none of it is kept, logged or shown.

Each command is then **Not found**, **Too old**, **Not logged in** or **Ready**. Results are kept until you press **Check** or the daemon restarts.

## The CLIs page

The page is a list beside one detail page for the command you choose. The list puts **Needs you** — not found, then too old, then not logged in — above **Ready**, each command with its version or its problem and how many MCP servers and skills need it. The detail page's header carries the command's description under its name, and nothing when it has none. **Edit**, on the header's right, changes it — any CLI has one, whether you added it or a skill or server requires it, so you can note what a tool is for. Under it are two sections. **On this machine** shows where the command was found, its version against the minimum, its login state and when Coffer last checked. **Needed by** lists every MCP server started with it (opening that server's page, with the launcher it starts with) and every skill that needs it with the minimum each asks for; a CLI nobody requires says so. One that needs you says what it costs in a plain sentence in a banner at the top — "duckdb can't start, and data-profiling fails at the step that calls uv." — with the [hand-off](#hand-the-install-to-your-agent) beside it. There is no command browser: what a tool's subcommands and options are is for the agent to read from `--help` when it uses the tool, so Coffer neither shows nor stores it. The page shows no install, update or login command, and nothing to run in a terminal.

**Check**, beside the list's filter (as **Check copies** sits on the Skills page), probes every command afresh; a banner's own **Check** probes just that one. **Add CLI**, the page's header action, takes a command name or the path to an executable, with an optional display name (e.g. `GitHub CLI`, shown before "needed by" in the header), minimum version, description and login check, for a tool you want checked — and your agents told about — that no skill or server declares. **Edit** opens the same form with the command locked: for a CLI you added it changes all of those; for one a skill or server requires, only the description, since the skills and servers that need it set the rest. Only a CLI you added by hand has **Remove**, in its **⋯** menu; it stops Coffer checking it and leaves the tool installed on this machine. A CLI that a skill or server requires cannot be removed here, because it is listed for as long as something needs it.

A skill's own page has a **Requires** tab listing what that skill declares, each command linking to its place here and offering the same hand-off when it needs you. And while any required command is missing, too old or not logged in, **Overview** lists it under what needs you. A launcher only MCP servers need is listed on Overview once, as the server's own "launcher isn't found on this machine" item, not a second time as a CLI.

## What your agents see

Every agent on this machine can read the same list. The [`coffer-guide` skill](/guides/skills#the-built-in-coffer-guide-skill) tells it to run `coffer cli list`, which prints every command Coffer manages — what each is for (the title you gave a CLI you added, and the description you wrote for any CLI), who needs it and whether it is ready on this machine — so an agent checks there before deciding a tool is unavailable, and learns which tool you use for a job. `coffer cli list --json` adds the hand-off prompt for any command that needs you. The command reads what Coffer found at its last check; it runs no check and no login check, so press **Check** after you install something.

## Hand the install to your agent

Coffer does not install anything itself. People install tools in many ways — Homebrew, apt, a language's own package manager, an installer from the vendor — and the right one depends on the machine. Your agent can look at the machine and choose; what it needs from Coffer are the facts. So for a command that is missing or too old, Coffer writes a short **install prompt**:

```text
Please install the command-line tool `gh` (GitHub CLI) on this machine.

- Needed by the Coffer skills: gh-triage (version 2.40 or newer).
- This machine: macOS 15.6, arm64.

Choose the right install method for this machine.
When you are done, run `gh --version` to confirm it works.
Check with me before running anything that needs sudo or changes system settings.
If a login is needed, tell me how and I will log in myself; do not handle my credentials.
```

A launcher adds the servers that start with it (`` - Needed by the MCP servers Coffer starts: duckdb (started with `uvx`). ``). A command that is too old gets the same prompt asking for an update, with the version found and where. The prompt names no install command: choosing one is the agent's job. The command's page and the skill's **Requires** tab offer one split button, **Hand off to &lt;Agent&gt; ▾**:

- **Hand off to &lt;Agent&gt;** — starts your default hand-off agent in your [preferred terminal](/guides/web-ui#settings) with the prompt as its first message. The prompt reaches the agent through a private temporary file, never the command line or shell history. Pick the agent and the terminal under **Settings › General**.
- **Hand off to the other agent**, in the ▾ menu when it is available, and **Copy prompt** — paste it into whichever agent you use, in a terminal or an IDE. A toast reads "Prompt copied".

Pressing the button asks for no confirmation. The agent runs in your own terminal under its own permission mode, with the prompt in plain view, and Esc or Ctrl-C stops it. Without a managed agent on this machine only Copy prompt is offered.

When the agent is done, press **Check**.

## Logging in

Coffer never logs in for you, and the page shows no login command. A command that is not logged in hands the login to your agent the same way: its prompt names the login check that failed and the login command the skill declared, and asks your agent only to tell you what to run; you run the login and type anything it asks for yourself. Then press **Check**.

## Related

- [Skills](/guides/skills) — importing skills and the `SKILL.md` format.
- [Writing skill libraries](/guides/writing-skill-libraries) — structuring larger skill sets.
- [Skill requirements](/architecture/skill-requirements) — how the check and the hand-off work.
