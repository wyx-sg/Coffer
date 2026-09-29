# Design — the command-line tools skills require

## Decisions

### 1. The declaration lives in SKILL.md

```yaml
requires:
  - command: gh                 # required; a bare name, no path
    title: GitHub CLI           # optional display name
    min_version: "2.40"         # optional; dotted numbers
    login_check: gh auth status # optional; argv of the SAME command, exit 0 = logged in
    login: gh auth login        # optional; shown to copy, never run
    brew: gh                    # optional; the Homebrew formula
    why: Opens and labels issues.  # optional; one line
  - jq                          # shorthand: a command with no conditions
```

`domain/skill/requirements.py` parses it leniently — an entry that is not
understood is reported as a warning on the skill and skipped, never fails the
skill's import — because it is third-party frontmatter, like `allowed-tools`.
The command must match `^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$`; the login check's
first word must be the command itself, so a skill can make Coffer run only the
tool it declares, never an arbitrary program; the formula must match
`^[A-Za-z0-9][A-Za-z0-9@._+/-]{0,127}$`. The file is read at check time, so an
edit in the user's editor is picked up by the next check. *Rejected:* storing
the list in the skill's config at import, which would go stale the moment the
file is edited.

### 2. One row per command

Rows aggregate every managed skill that declares the command. The minimum is
the highest any skill asks for; title, login check, login command and formula
come from the first skill (by name) that declares each. `needed_by` lists every
skill with the minimum and reason it gave.

Status, in problem-first order: `missing` (not on the agent's `PATH`),
`outdated` (version found below the minimum), `logged_out` (the login check
exited non-zero or timed out), `ready`. A version that cannot be parsed is
reported as unknown and not treated as outdated.

### 3. Probing

`application/skill/cli_requirements.py` (`CliRequirementService`) owns the
aggregation, the cache and the install jobs; it reaches the machine through a
`CommandProbePort` (`locate(command) -> path | None`,
`version(path) -> str | None`, `login_ok(argv) -> bool | None`) and an
`InstallerPort`. The adapter `infrastructure/skill/command_probe.py` uses
`UserPath` — the login-shell `PATH` merged with the inherited one — which moves
from `infrastructure/agent/program_probe.py` to the kind-agnostic
`infrastructure/platform/user_path.py` so agent detection and this share one
lookup; `parse_version` moves from `domain/agent/detection.py` to the
kind-agnostic `domain/versions.py` with the comparison.

- `--version` and the login check run with `stdin` closed, the user's `PATH`,
  a 5 s and 10 s timeout, and no shell. The login check's stdout and stderr are
  discarded unread — a login check may print a token or an account name, and
  none of it is captured, logged or returned. Only its exit status is used.
- Results are cached per command until **Check again** (`POST /clis/check`,
  `POST /clis/{command}/check`, `coffer cli check`), the first read after the
  daemon starts, or an install finishes. Probes run in worker threads.

### 4. Installing

`POST /clis/{command}/install {formula}` starts a job when the command is
`missing` or `outdated`, its formula is declared, the body's formula equals it
(so a confirmation shown for one command cannot run another) and Homebrew is on
the agent's `PATH`. The job runs `brew install <formula>` for a missing command
and `brew upgrade <formula>` for an outdated one — argv, no shell, never
`sudo`, as the daemon's user, with `HOMEBREW_NO_AUTO_UPDATE=1` and
`NONINTERACTIVE=1`, `stdin` closed and a 15-minute ceiling. Its merged output
is kept (last 2 000 lines) and served by `GET /clis/{command}/install` while
the page polls; the job's start and end are audited as `cli_install_started`
and `cli_install_finished` with the command, the formula, the argv, the exit
code and the last 40 lines, which is how Activity keeps it. One job per
command at a time. When it ends, the command is probed again. There is no
other installer: Coffer never guesses a package manager.

### 5. Surfaces

| Route | Does |
| --- | --- |
| `GET /api/v1/clis` | every required command, problems first, with when they were checked |
| `POST /api/v1/clis/check` | probe every command again |
| `GET /api/v1/clis/{command}` | one command (404 when no skill requires it) |
| `POST /api/v1/clis/{command}/check` | probe it again |
| `POST /api/v1/clis/{command}/install` | `{formula}` — start the Homebrew job (202) |
| `GET /api/v1/clis/{command}/install` | the latest job for it: state, exit code, output |

CLI: `coffer cli list [--json]`, `coffer cli show <command> [--json]`,
`coffer cli check [<command>]`, `coffer cli install <command> [--yes]` — which
prints the exact Homebrew command and asks before running it, then follows the
output.

The attention source (`application/skill/cli_attention.py`, kind `cli`, the
command as the uid) reports `cli_missing`, `cli_outdated` and
`cli_logged_out`, each a warning whose action is `check` through
`POST /api/v1/clis/{command}/check`; it reads the cache, probing only when
nothing was checked yet.

## Risks

- **A skill's declared login check runs on the user's machine.** It can only
  be the declared command itself, it never runs in a shell, and its output is
  discarded; the command is already one the skill tells the agent to run.
- **Homebrew runs third-party code.** Only after the person confirmed the exact
  command, never elevated.
