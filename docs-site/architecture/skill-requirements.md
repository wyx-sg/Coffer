---
title: Skill requirements
description: How Coffer reads the command-line tools a skill declares, checks them where the agent runs, and hands a missing one to the person's agent as a prompt instead of installing it.
---

# Skill requirements

A skill that drives a command-line tool fails at the step that calls it when the tool is missing, too old or not logged in. Skill requirements give that failure a place to be seen before an agent trips over it: each skill declares its commands in `SKILL.md`, Coffer checks each command once on this machine, and the CLIs page, the skill's Requires tab, the attention list and `coffer cli` report what they found. The user-facing side is the [CLIs guide](/guides/clis).

## Principles

- **The skill declares; the file is the truth.** `requires:` lives in the skill's own `SKILL.md` and is read from the master folder at every check, so it can never drift from what the user edits. Nothing is stored in the database.
- **Check where the agent runs.** The lookup uses the agent's real `PATH`: the login shell's, merged with the daemon's inherited one — the same lookup path agent detection uses, which is why it belongs to the kind-agnostic platform layer rather than to the skill kind.
- **A declaration can only name the tool it declares.** The command is a bare name, the login check's first word must be that command, and nothing runs in a shell. A skill cannot make Coffer run an arbitrary program by declaring it, and a declared login check runs only when someone asks: reads (the attention list polls them) find the command and its version and leave the login state unknown; the Check action runs the login check.
- **Nothing a check prints is kept.** A login check's stdout and stderr go to `/dev/null`; only its exit status is used, because such output may hold an account name or a token.
- **Coffer checks; the agent installs.** Installing depends on the machine — which package manager, which architecture, whether `sudo` is involved — and the person's agent can find that out. Coffer runs no installer and no login. It writes the facts it has into a prompt, the [agent hand-off](#the-agent-hand-off), and the person gives it to an agent.
- **One row per command.** A missing `gh` is one problem, however many skills need it.
- **MCP servers' launchers are requirements too.** An enabled stdio MCP server needs its launcher, so the check lists it under the command that provides it (`uv` for `uvx`, `node` for `npx`, `bun` for `bunx`) with no minimum and no login. The two kinds meet only at the composition root: the MCP kind reads the enabled servers' launchers, the composition root hands them to the check through a port, and the skill kind never imports the MCP kind.

## The pieces

| Piece | What it does |
| --- | --- |
| Declaration | Parses `requires:` leniently: an entry it cannot use is skipped with a warning and never fails the skill's import. |
| Versions | Reads a dotted version out of `--version` output and compares two, shared with agent detection. |
| Status | `missing`, `outdated`, `logged_out` or `ready`, the problems-first order, and which command a stdio launcher is checked as. |
| Aggregation and cache | One row per command across every managed skill and enabled stdio MCP server: the highest minimum, the first skill's title, login check and login command, every skill that needs it and every server started with it. Results are cached until Check again or the daemon restarts; probes run in worker threads. |
| Probe | Locates the command on the agent's `PATH`, runs `--version` (5 s) and the login check (10 s) with `stdin` closed and output discarded. |
| Hand-off | The prompt for a missing, outdated or not-logged-in command, carried as `handoff.prompt` on every command the routes return. |
| Machine | The OS and CPU architecture the prompt names, e.g. `macOS 15.6, arm64`, read once per daemon. |
| Attention | Kind `cli`, the command as the uid: `cli_missing`, `cli_outdated`, `cli_logged_out`, each offering `check`. A command only MCP servers need raises none: the server's `mcp_missing_launcher` item already names it. |
| Surfaces | `/api/v1/clis…` and `coffer cli list|show|check|prompt`. |

## The agent hand-off

Coffer is AI-native: a chore that depends on the machine — installing, setting up, troubleshooting — is handed to the person's agent rather than scripted by the daemon. The hand-off is a building block any feature can use:

- **A hand-off is a task, some facts and some steps**, and one shared renderer, in the domain layer, turns it into the prompt. A feature supplies what it knows; the renderer writes one task sentence, the facts as `-` lines, the steps one per line, and then the rules every hand-off ends with — check with the person before anything that needs `sudo` or changes system settings, and leave any login to the person without handling their credentials.
- **The prompt is built on the daemon** and served on the feature's own REST response as `handoff: {prompt}` (one schema shared by every feature) and by its command line, so a copied prompt and a printed one are the same words.
- **The web UI shows it with one shared component**: **Ask an agent**, which opens a new conversation with a Coffer-managed agent with the prompt in the composer, and its menu's **Copy prompt**. The person presses Send; nothing is sent for them, because a managed agent runs with full permissions. With no managed agent available — the agent that is missing is the one that would be asked, or none is added yet — only Copy prompt is offered.
- **The attention list carries it too.** An attention item whose fix is a chore has an optional `handoff`, the same prompt its kind's page offers, and a reason sentence that names no command. The Overview's Needs you row offers it in the row's ⋯ menu, and `coffer attention --prompt <key>` prints it.

For a required command the facts are:

| Status | The prompt asks the agent to | Facts it names |
| --- | --- | --- |
| `missing` | install it, choosing the method for this machine, and run `<command> --version` | the skills that need it, with each one's minimum; the MCP servers started with it and their launcher; the machine |
| `outdated` | update it the way it was installed, and run `<command> --version` | the version and path found against the minimum; the skills; the machine |
| `logged_out` | tell the person what to run to log in, and run the login check afterwards | the login check that failed; the declared login command; the skills; the machine |

A `ready` command carries no prompt. Use a hand-off when the chore is open-ended and depends on the environment; when Coffer can do the work itself deterministically — probing again, connecting an agent — it is a plain button.

## Trade-offs

- **The login check runs a declared subcommand on the user's machine.** It is the tool the skill already tells the agent to run, restricted to that tool and run without a shell; the alternative — never checking login — leaves the most common failure invisible.
- **An agent installs with full permissions.** The prompt asks it to check with the person before anything elevated, and **Ask an agent** only fills the composer, so the person reads the request before it is sent.
- **A minimum written unquoted in YAML** (`2.40`) is parsed as a number and would compare as `2.4`; Coffer refuses it with a warning instead of guessing.

## Related

- Spec: [skill-manager](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/skill-manager/spec.md), and the page in [web-ui](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/web-ui/spec.md)
- Pages: [Agent facets](/architecture/agent-facets) (the dependency probe this shares its `PATH` with), [Platform port](/architecture/platform), [Security model](/architecture/security), [CLIs guide](/guides/clis)
