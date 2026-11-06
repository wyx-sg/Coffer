---
title: Skill requirements
description: How Coffer reads the command-line tools a skill declares, checks them where the agent runs, and hands a missing one to the person's agent as a prompt instead of installing it.
---

# Skill requirements

A skill that drives a command-line tool fails at the step that calls it when the tool is missing. Skill requirements give that failure a place to be seen before an agent trips over it: each skill declares its commands in `SKILL.md` (and a person can add a tool by hand), Coffer checks each command once on this machine, and the CLIs page, the skill's Requires tab and the attention list report what they found. The user-facing side is the [CLIs guide](/guides/clis).

## Principles

- **The skill's file, or the person's declaration in the vault, is the truth.** `requires:` lives in the skill's own `SKILL.md` and is read from the master folder at every check, so it can never drift from what the user edits. A tool a person adds by hand, and their edits to the display name and description of a tool a skill requires, live in the vault document `state/cli-tools/tools.json`, which syncs; an edit takes the place of the skill's value. Nothing is stored in the database.
- **Only the declaration is read.** Coffer never scans a skill's body, scripts or sub-skills to guess what it runs: a guess from prose would list commands the skill only mentions and miss the ones a script calls. A skill that delegates to another skill declares only what it uses itself; the delegated skill declares its own. Whether to add a declaration, and anything about the skill's layout, is a suggestion the person's agent makes and the person may decline (the skill's review hand-off); the only hard rules a skill meets are the import limits on the [Skills](/architecture/skills) page.
- **Check where the agent runs.** The lookup uses the agent's real `PATH`: the login shell's, merged with the daemon's inherited one — the same lookup path agent detection uses, which is why it belongs to the kind-agnostic platform layer rather than to the skill kind. The Claude Code and Codex sessions Coffer starts get that same `PATH` in their environment, so a command the check finds is one the agent finds.
- **Coffer only looks the command up.** The command is a bare name looked up on `PATH`, and Coffer runs none of the commands it checks, not even `--version`. A skill cannot make Coffer run anything by declaring it. Whether the tool is new enough or logged in is the agent's to find out when it uses it ([ADR](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/agents-check-cli-logins-themselves.md)); a `min_version`, `version`, `login_check` or `login` key, or a `gh>=2.40` spelling, an older skill carries is accepted and ignored.
- **Coffer checks; the agent installs.** Installing depends on the machine — which package manager, which architecture, whether `sudo` is involved — and the person's agent can find that out. Coffer runs no installer and no login. It writes the facts it has into a prompt, the [agent hand-off](#the-agent-hand-off), and the person gives it to an agent.
- **One row per command.** A missing `gh` is one problem, however many skills need it.
- **MCP servers' launchers are requirements too.** An enabled stdio MCP server needs its launcher, so the check lists it under the command that provides it (`uv` for `uvx`, `node` for `npx`, `bun` for `bunx`). The two kinds meet only at the composition root: the MCP kind reads the enabled servers' launchers, the composition root hands them to the check through a port, and the skill kind never imports the MCP kind.

## The pieces

| Piece | What it does |
| --- | --- |
| Declaration | Parses `requires:` leniently: an entry it cannot use is skipped with a warning and never fails the skill's import. The same `requires` may name Coffer secrets (`requires: {secrets: [...]}`); one that is not set is reported by name, without reading any value. |
| Declared by hand | The tools a person adds without a skill, and their edits to required ones, read from `state/cli-tools/tools.json`. Each change is audited as `cli_tool_added`, `cli_tool_edited` or `cli_tool_removed`. Removing a hand-added tool a skill also requires drops only the declaration. |
| Coffer's own needs | The commands Coffer runs itself: `git`, for the vault's history and sync. |
| Status | `missing` or `ready`, the problems-first order, and which command a stdio launcher is checked as. |
| Aggregation and cache | One row per command across every managed skill, enabled stdio MCP server, hand-added tool and Coffer's own need: the title from the person's declaration or edit, else Coffer's need, else the first skill's; every skill that needs it and every server started with it. Results are cached until Check or the daemon restarts, and a read probes only a command nothing has checked yet; probes run in worker threads. |
| Probe | Locates the command on the agent's `PATH`, resolving symlinks; it runs nothing. |
| Hand-off | The prompt for a missing command, carried as `handoff.prompt` on every command the routes return. |
| Machine | The OS and CPU architecture the prompt names, e.g. `macOS 15.6, arm64`, read once per daemon. |
| Attention | Kind `cli`, the command as the uid: `cli_missing`, offering `check`. A command only MCP servers need raises none: the server's `mcp_missing_launcher` item already names it. |
| Surfaces | `/api/v1/clis…`. |

## The agent hand-off

Coffer is AI-native: a chore that depends on the machine — installing, setting up, troubleshooting — is handed to the person's agent rather than scripted by the daemon. The hand-off is a building block any feature can use:

- **A hand-off is a task, some facts and some steps**, and one shared renderer, in the domain layer, turns it into the prompt. A feature supplies what it knows; the renderer writes one task sentence, the facts as `-` lines, the steps one per line, and then the rules every hand-off ends with — check with the person before anything that needs `sudo` or changes system settings, and leave any login to the person without handling their credentials.
- **The prompt is built on the daemon** and served on the feature's own REST response as `handoff: {prompt}` (one schema shared by every feature) so the prompt a person copies is the one the page offers.
- **The web UI shows it with one shared component**: **Hand off to &lt;Agent&gt;**, which starts the default hand-off agent in the preferred terminal with the prompt as its first message, and its menu's **Copy prompt**. The prompt travels in a private temporary file, and the agent runs in the person's terminal under its own permission mode. With no managed agent available — the agent that is missing is the one that would be asked, or none is added yet — only Copy prompt is offered.
- **The attention list carries it too.** An attention item whose fix is a chore has an optional `handoff`, the same prompt its kind's page offers, and a reason sentence that names no command. The Overview's Needs you row offers it in the row's ⋯ menu.

For a required command the facts are:

| Status | The prompt asks the agent to | Facts it names |
| --- | --- | --- |
| `missing` | install it, choosing the method for this machine, confirm it works, then run `coffer cli check <command>` | the skills that need it; the MCP servers started with it and their launcher; the machine |

A `ready` command carries no prompt. Use a hand-off when the chore is open-ended and depends on the environment; when Coffer can do the work itself deterministically — probing again, connecting an agent — it is a plain button.

## Trade-offs

- **No version or login state on the page.** A tool that is too old or logged out is not flagged before an agent uses it; the agent sees the tool's own error when it runs it, and a check Coffer ran would be stale a minute later anyway. Coffer reading versions also failed for tools whose `--version` prints nothing it can parse (`go version`, `kubectl version --client`).
- **The prompt names no way to confirm.** Not every tool has `--version`, so the agent confirms its own way and then runs `coffer cli check`.
- **An agent installs in the person's terminal.** The prompt asks it to check with the person before anything elevated, and **Hand off to &lt;Agent&gt;** runs the agent under its own permission mode where the person can watch it and stop it with Esc or Ctrl-C.

## Related

- Spec: [skill-manager](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/skill-manager/spec.md), and the page in [web-ui](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/web-ui/spec.md)
- Pages: [Agent facets](/architecture/agent-facets) (the dependency probe this shares its `PATH` with), [Platform port](/architecture/platform), [Security model](/architecture/security), [CLIs guide](/guides/clis)
