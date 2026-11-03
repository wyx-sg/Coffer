## Why

Importing `diagram-design` from GitHub with `coffer skill stage-git` failed two ways on the owner's Mac (2026-11-03):

- The CLI waited 15 s for every request, whatever it did, while the daemon's Git work may take minutes; and it reported the wait running out as `DAEMON_UNREACHABLE` ("it may have crashed") although the daemon was healthy and went on to answer.
- The checkout of the skill's folder from the `--filter=blob:none` clone fetched each of its 290 files in a separate request (a checkout limited to a path does not prefetch). That took 96 s on git 2.43 and failed on Apple Git 2.50 with "in the commit graph file but not in the object database".

## What Changes

- The daemon fetches the files a Git skill's folder holds in one request before the checkout, and runs the temporary clones with no auto gc, maintenance or commit-graph writes. A missing object after that falls back once to a clone without the filter.
- One operation on a skill's Git source (stage, check, change source, hand-off, record a merge) is held to 300 s in all; past it every git process is killed and the operation is refused `SKILL_SOURCE_UNREACHABLE` saying so.
- Each CLI command waits as long as its route needs: 15 s by default, 90 s for a route that makes a call out, 330 s for one that runs git over the network (skill sources, sync rounds). `coffer --request-timeout <seconds>` replaces the wait.
- A request with no answer is reported by what happened: nothing listening is `DAEMON_UNREACHABLE` (exit 3); the connection closed before an answer is `DAEMON_CONNECTION_LOST` (exit 3); no answer within the wait is `CLI_REQUEST_TIMEOUT` (exit 13) naming the request and the wait, and does not say the daemon crashed.

## Impact

- Specs: resource-framework (CLI waits and transport errors), skill-manager (Git fetch and deadline).
- Code: `backend/coffer/infrastructure/skill/git_source.py`, `application/skill/source_service.py`, `update_ops.py`, `surfaces/cli/_waits.py`, `_transport.py`, `_io.py`, `_client.py`, `_route_command.py`, `main.py`, command declarations.
- ADRs: `cli-request-wait-budgets`, `git-source-partial-clone-prefetch`.
- Docs: CLI reference (generated), error codes, skills guide, troubleshooting (English and Chinese).
