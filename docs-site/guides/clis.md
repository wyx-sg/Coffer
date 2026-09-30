---
title: CLIs
description: Declare the command-line tools a skill needs, see on one page which are missing, too old or not logged in, and hand the install to your agent with a prompt Coffer writes for this machine.
---

# CLIs

Many skills drive a command-line tool — `gh` to triage issues, `jq` to filter JSON, `aws` to read a bucket. When the tool is missing, older than the skill expects or not logged in, the agent following the skill fails at the step that calls it. The **CLIs** page shows every command your skills say they need, checked on this machine, with the problems first.

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
| `login` | The command that logs you in, shown for you to copy. Coffer never runs it. |
| `why` | One line on what the skill uses the command for. |

A bare name (`- uv`) is a command with no conditions, and `- "node>=20.1"` a command with a minimum; `requires: [jq, "gh>=2.40"]` and `requires: {commands: [...]}` are read the same way. An entry Coffer cannot use — a path instead of a name, a login check that runs a different program — is skipped with a warning on the CLIs page; it never stops the skill from being imported or delivered.

Coffer reads `requires:` from the skill's folder every time it checks, so an edit in your editor is picked up by the next **Check again** without importing the skill again. This top-level `requires:` lists commands; it is unrelated to `metadata.requires`, which a skill library uses for [the skills a domain depends on](/guides/writing-skill-libraries#declared-dependencies).

## How Coffer checks a command

One row per command, however many skills need it:

1. **Found?** The command is looked up on your real `PATH` — your login shell's, merged with the one the daemon inherited — the same `PATH` an agent gets when you start it from a terminal. A command installed where only your shell looks (Homebrew, `~/.local/bin`) is found.
2. **Version.** Coffer runs `<command> --version` and compares the version with the **highest** minimum any skill asks for. A version it cannot read is shown as unknown and is not called too old.
3. **Logged in?** If a skill declared a login check, Coffer runs it — without a shell, with a 10-second limit — and looks only at whether it succeeded. **Its output is thrown away unread**: a login check can print your account name or a token, and none of it is kept, logged or shown.

Each command is then **Not found**, **Too old**, **Not logged in** or **Ready**. Results are kept until you press **Check again** or the daemon restarts.

## The CLIs page

The page is a list beside the command you choose. The list puts **Needs you** — not found, then too old, then not logged in — above **Ready**, each command with its version or its problem and how many skills need it. The command on the right shows where it was found, its version against the minimum, its login state and every skill that needs it with the minimum each asks for; one that needs you has its problem at the top and the [hand-off](#hand-the-install-to-your-agent) beside its name.

A skill's own page has a **Requires** tab listing what that skill declares, each command linking to its place here and offering the same hand-off when it needs you. And while any required command is missing, too old or not logged in, **Overview** lists it under what needs you, and the **CLIs** entry in the sidebar carries a dot.

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

A command that is too old gets the same prompt asking for an update, with the version found and where. The command's page and the skill's **Requires** tab offer two ways to use it:

- **Copy prompt** — paste it into whichever agent you use, in a terminal or an IDE.
- **Ask an agent** — choose one of the agents Coffer manages and a folder, and a new [conversation](/guides/chat) opens with the prompt already in the message box. **Nothing is sent until you press Send**: a managed agent runs with full permissions, so read what it is about to be asked first. Without a managed agent on this machine only Copy prompt is offered.

When the agent is done, press **Check again**.

## Logging in

Coffer never logs in for you. A command that is not logged in shows its login command — `gh auth login` — to copy: run it in a terminal, then press **Check again**. If you would rather have help, its prompt asks your agent only to tell you what to run; you run the login and type anything it asks for yourself.

## On the command line

```sh
coffer cli list                 # every required command, problems first
coffer cli list --json
coffer cli show gh              # one command: path, version, login, skills
coffer cli check                # probe every command again
coffer cli check gh             # probe one again
coffer cli prompt gh            # the prompt to give your agent
coffer cli prompt gh | pbcopy   # straight to the clipboard on macOS
```

`coffer cli prompt` prints the same text the page copies, and exits non-zero for a command that is ready. Every option is in the [CLI reference](/reference/cli#coffer-cli).

## Related

- [Skills](/guides/skills) — importing skills and the `SKILL.md` format.
- [Writing skill libraries](/guides/writing-skill-libraries) — structuring larger skill sets.
- [Skill requirements](/architecture/skill-requirements) — how the check and the hand-off work.
