---
title: Skill requirements
description: How Coffer reads the command-line tools a skill declares, checks them where the agent runs, and hands a missing one to the person's agent as a prompt instead of installing it.
---

# Skill requirements

A skill that drives a command-line tool fails at the step that calls it when the tool is missing, too old or not logged in. Skill requirements give that failure a place to be seen before an agent trips over it: each skill declares its commands in `SKILL.md`, Coffer checks each command once on this machine, and the CLIs page, the skill's Requires tab, the attention list and `coffer cli` report what they found. The user-facing side is the [CLIs guide](/guides/clis).

## Principles

- **The skill declares; the file is the truth.** `requires:` lives in the skill's own `SKILL.md` and is read from the master folder at every check, so it can never drift from what the user edits. Nothing is stored in the database.
- **Check where the agent runs.** The lookup uses the agent's real `PATH`: the login shell's, merged with the daemon's inherited one — the same `UserPath` agent detection uses, which is why it lives in the kind-agnostic `infrastructure/platform/user_path.py`.
- **A declaration can only name the tool it declares.** The command is a bare name, the login check's first word must be that command, and nothing runs in a shell. A skill cannot make Coffer run an arbitrary program by declaring it.
- **Nothing a check prints is kept.** A login check's stdout and stderr go to `/dev/null`; only its exit status is used, because such output may hold an account name or a token.
- **Coffer checks; the agent installs.** Installing depends on the machine — which package manager, which architecture, whether `sudo` is involved — and the person's agent can find that out. Coffer runs no installer and no login. It writes the facts it has into a prompt, the [agent hand-off](#the-agent-hand-off), and the person gives it to an agent.
- **One row per command.** A missing `gh` is one problem, however many skills need it.
- **MCP servers' launchers are requirements too.** An enabled stdio MCP server needs its launcher, so the check lists it under the command that provides it (`uv` for `uvx`, `node` for `npx`, `bun` for `bunx`) with no minimum and no login. The two kinds meet only at the composition root: `application/mcp/stdio_launchers.py` reads the servers, `agent_skill_wiring.py` hands them to the check through `McpLaunchersPort`, and the skill kind never imports the MCP kind.

## The pieces

| Piece | Where | What it does |
| --- | --- | --- |
| Declaration | `domain/skill/requirements.py` | Parses `requires:` leniently: an entry it cannot use is skipped with a warning and never fails the skill's import. |
| Versions | `domain/versions.py` | Reads a dotted version out of `--version` output and compares two, shared with agent detection. |
| Status | `domain/skill/cli_status.py` | `missing`, `outdated`, `logged_out` or `ready`, the problems-first order, and `launcher_cli` (which command a stdio launcher is checked as). |
| Aggregation and cache | `application/skill/cli_requirements.py` | One row per command across every managed skill and enabled stdio MCP server: the highest minimum, the first skill's title, login check and login command, every skill that needs it and every server started with it. Results are cached until Check again or the daemon restarts; probes run in worker threads. |
| Probe | `infrastructure/skill/command_probe.py` | Locates on `UserPath`, runs `--version` (5 s) and the login check (10 s) with `stdin` closed and output discarded. |
| Hand-off | `application/skill/cli_handoff.py`, `domain/handoff.py` | The prompt for a missing, outdated or not-logged-in command, carried as `handoff.prompt` on every command the routes return. |
| Machine | `infrastructure/platform/host.py` (`machine_label`) | The OS and CPU architecture the prompt names, e.g. `macOS 15.6, arm64`, read once per daemon. |
| Attention | `application/skill/cli_attention.py` | Kind `cli`, the command as the uid: `cli_missing`, `cli_outdated`, `cli_logged_out`, each offering `check`. A command only MCP servers need raises none: the server's `mcp_missing_launcher` item already names it. |
| Surfaces | `surfaces/http/cli_routes.py`, `surfaces/cli/cli_cmd.py` | `/api/v1/clis…` and `coffer cli list|show|check|prompt`. |

## The agent hand-off

Coffer is AI-native: a chore that depends on the machine — installing, setting up, troubleshooting — is handed to the person's agent rather than scripted by the daemon. The hand-off is a building block any feature can use:

- **`domain/handoff.py`** holds `Handoff(task, facts, steps)` and `render_handoff()`. A feature supplies what it knows; the renderer writes one task sentence, the facts as `-` lines, the steps one per line, and then the rules every hand-off ends with — check with the person before anything that needs `sudo` or changes system settings, and leave any login to the person without handling their credentials.
- **The prompt is built on the daemon** and served on the feature's own REST response as `handoff: {prompt}` (the shared `HandoffOut` schema) and by its command line, so a copied prompt and a printed one are the same words.
- **The web UI shows it with one component**, `AgentHandoff`: **Copy prompt**, and **Ask an agent**, which opens a new conversation with a Coffer-managed agent with the prompt in the composer. The person presses Send; nothing is sent for them, because a managed agent runs with full permissions. With no managed agent available — the agent that is missing is the one that would be asked, or none is added yet — only Copy prompt is offered.
- **The attention list carries it too.** An `AttentionItem` whose fix is a chore has an optional `handoff`, the same prompt its kind's page offers, and a reason sentence that names no command. The Overview's Needs you row offers it in the row's ⋯ menu, and `coffer attention --prompt <key>` prints it.

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
