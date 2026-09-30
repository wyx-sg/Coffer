---
title: CLIs
description: Declare the command-line tools a skill needs, see on one page which are missing, too old or not logged in, and install a missing one through Homebrew after you confirm.
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
    brew: gh
    why: Reads and labels issues.
  - command: jq
    min_version: "1.6"
    brew: jq
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
| `brew` | The Homebrew formula that installs the command. Without it Coffer offers no install. |
| `why` | One line on what the skill uses the command for. |

A bare name (`- uv`) is a command with no conditions. An entry Coffer cannot use — a path instead of a name, a login check that runs a different program — is skipped with a warning on the CLIs page; it never stops the skill from being imported or delivered.

Coffer reads `requires:` from the skill's folder every time it checks, so an edit in your editor is picked up by the next **Check again** without importing the skill again. This top-level `requires:` lists commands; it is unrelated to `metadata.requires`, which a skill library uses for [the skills a domain depends on](/guides/writing-skill-libraries#declared-dependencies).

## How Coffer checks a command

One row per command, however many skills need it:

1. **Found?** The command is looked up on your real `PATH` — your login shell's, merged with the one the daemon inherited — the same `PATH` an agent gets when you start it from a terminal. A command installed where only your shell looks (Homebrew, `~/.local/bin`) is found.
2. **Version.** Coffer runs `<command> --version` and compares the version with the **highest** minimum any skill asks for. A version it cannot read is shown as unknown and is not called too old.
3. **Logged in?** If a skill declared a login check, Coffer runs it — without a shell, with a 10-second limit — and looks only at whether it succeeded. **Its output is thrown away unread**: a login check can print your account name or a token, and none of it is kept, logged or shown.

Each command is then **Not found**, **Too old**, **Not logged in** or **Ready**. Results are kept until you press **Check again**, an install finishes, or the daemon restarts.

## The CLIs page

The list shows each command with where it was found, its version against the minimum, its login state, how many skills need it and its status — problems first. From a row you can **Install…** a missing command, **Update…** one that is too old, or **Copy login command** for one that is not logged in. Choosing a command opens its page: where it was found, the version, how to log in, and every skill that needs it with the minimum each asks for.

A skill's own page has a **Requires** tab listing what that skill declares, each command linking to its page here. And while any required command is missing, too old or not logged in, **Overview** lists it under what needs you, and the **CLIs** entry in the sidebar carries a dot.

## Install through Homebrew

**Install…** is offered only for a command that is missing or too old and whose skill names a Homebrew formula. Coffer asks first, showing the exact command it will run — `brew install jq`, or `brew upgrade docker` for one that is too old — and runs nothing until you confirm. Then the daemon runs it **as you, never with `sudo`**, the output streams onto the page, and the start and the end (with the exit code and the last lines of output) are recorded in [Activity](/guides/activity). When it finishes, the command is checked again.

Homebrew is the only installer Coffer uses: it never guesses a package manager. If Homebrew itself is not on your `PATH`, install it yourself first, or install the command however you prefer and press **Check again**.

## Logging in

Coffer never logs in for you. A command that is not logged in shows its login command — `gh auth login` — to copy: run it in a terminal, then press **Check again**.

## On the command line

```sh
coffer cli list                 # every required command, problems first
coffer cli list --json
coffer cli show gh              # one command: path, version, login, skills
coffer cli check                # probe every command again
coffer cli check gh             # probe one again
coffer cli install jq           # shows `brew install jq`, asks, then streams the output
coffer cli install jq --yes     # no question
```

`coffer cli install` exits non-zero when the install fails, and does nothing for a command that has nothing to install. Every option is in the [CLI reference](/reference/cli#coffer-cli).

## Related

- [Skills](/guides/skills) — importing skills and the `SKILL.md` format.
- [Writing skill libraries](/guides/writing-skill-libraries) — structuring larger skill sets.
- [Skill requirements](/architecture/skill-requirements) — how the check and the install work.
