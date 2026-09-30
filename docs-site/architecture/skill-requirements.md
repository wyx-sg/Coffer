---
title: Skill requirements
description: How Coffer reads the command-line tools a skill declares, checks them where the agent runs, and installs a missing one through Homebrew only when a person confirms.
---

# Skill requirements

A skill that drives a command-line tool fails at the step that calls it when the tool is missing, too old or not logged in. Skill requirements give that failure a place to be seen before an agent trips over it: each skill declares its commands in `SKILL.md`, Coffer checks each command once on this machine, and the CLIs page, the skill's Requires tab, the attention list and `coffer cli` report what they found. The user-facing side is the [CLIs guide](/guides/clis).

## Principles

- **The skill declares; the file is the truth.** `requires:` lives in the skill's own `SKILL.md` and is read from the master folder at every check, so it can never drift from what the user edits. Nothing is stored in the database.
- **Check where the agent runs.** The lookup uses the agent's real `PATH`: the login shell's, merged with the daemon's inherited one — the same `UserPath` agent detection uses, which is why it lives in the kind-agnostic `infrastructure/platform/user_path.py`.
- **A declaration can only name the tool it declares.** The command is a bare name, the login check's first word must be that command, and nothing runs in a shell. A skill cannot make Coffer run an arbitrary program by declaring it.
- **Nothing a check prints is kept.** A login check's stdout and stderr go to `/dev/null`; only its exit status is used, because such output may hold an account name or a token.
- **Install only through Homebrew, only when asked.** Coffer never guesses a package manager, never installs on its own initiative, never elevates, and never logs in.
- **One row per command.** A missing `gh` is one problem, however many skills need it.

## The pieces

| Piece | Where | What it does |
| --- | --- | --- |
| Declaration | `domain/skill/requirements.py` | Parses `requires:` leniently: an entry it cannot use is skipped with a warning and never fails the skill's import. |
| Versions | `domain/versions.py` | Reads a dotted version out of `--version` output and compares two, shared with agent detection. |
| Status | `domain/skill/cli_status.py` | `missing`, `outdated`, `logged_out` or `ready`, and the problems-first order. |
| Aggregation and cache | `application/skill/cli_requirements.py` | One row per command across every managed skill: the highest minimum, the first skill's title, login check, login command and formula, and every skill that needs it. Results are cached until Check again, an install ends or the daemon restarts; probes run in worker threads. |
| Probe | `infrastructure/skill/command_probe.py` | Locates on `UserPath`, runs `--version` (5 s) and the login check (10 s) with `stdin` closed and output discarded. |
| Installer | `application/skill/cli_install.py`, `infrastructure/skill/homebrew.py` | One job per command: `brew install|upgrade <formula>` as argv, `HOMEBREW_NO_AUTO_UPDATE=1`, `NONINTERACTIVE=1`, a 15-minute ceiling, the merged output buffered (2 000 lines) for the page to poll, and `cli_install_started` / `cli_install_finished` audited with the argv, the exit code and the last 40 lines. |
| Attention | `application/skill/cli_attention.py` | Kind `cli`, the command as the uid: `cli_missing`, `cli_outdated`, `cli_logged_out`, each offering `check`. |
| Surfaces | `surfaces/http/cli_routes.py`, `surfaces/cli/cli_cmd.py` | `/api/v1/clis…` and `coffer cli list|show|check|install`. |

## Installing

An install request must name the formula the confirmation showed — `POST /api/v1/clis/{command}/install {formula}` — so a confirmation given for one command cannot run another. It is refused for a command that is ready, that declares no formula, while a job for it is running, or while Homebrew is not on the agent's `PATH`. The page polls `GET /api/v1/clis/{command}/install?since=<line>` for the output while the job runs; when it ends the command is probed again before the job reads as finished, so whoever sees it end also sees the new status.

## Trade-offs

- **The login check runs a declared subcommand on the user's machine.** It is the tool the skill already tells the agent to run, restricted to that tool and run without a shell; the alternative — never checking login — leaves the most common failure invisible.
- **Homebrew runs third-party code.** It runs only after the person confirmed the exact command, never elevated, and with its full record in Activity.
- **A minimum written unquoted in YAML** (`2.40`) is parsed as a number and would compare as `2.4`; Coffer refuses it with a warning instead of guessing.

## Related

- Spec: [skill-manager](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/skill-manager/spec.md), and the page in [web-ui](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/web-ui/spec.md)
- Pages: [Agent facets](/architecture/agent-facets) (the dependency probe this shares its `PATH` with), [Platform port](/architecture/platform), [Security model](/architecture/security), [CLIs guide](/guides/clis)
