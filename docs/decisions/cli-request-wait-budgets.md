# Each CLI Command Waits as Long as Its Route Needs, and Says Why an Answer Did Not Come

**Status**: Accepted
**Date**: 2026-11-03
**Deciders**: Yuxing (owner), Claude
**Related**: [Every Web UI and Desktop Operation Has a `coffer` Command Over the Same Route](command-line-parity-with-the-web-ui.md), [A Git Skill's Folder Is Fetched in One Request](git-source-partial-clone-prefetch.md), spec resource-framework "Wait for the daemon's answer as long as the operation needs"

## Context

On 2026-11-03 `coffer skill stage-git` for `cathrynlavery/diagram-design` exited 3 after about 19 s with `DAEMON_UNREACHABLE` — "daemon not reachable, it may have crashed". The daemon was healthy before and after, its error log was empty, and the same request over the HTTP API with a longer wait returned the daemon's real answer. Two things combined:

- Every request the CLI made used one `httpx.Client(timeout=15)`. The daemon's Git work allows 180 s per git command, and one import runs several. The web UI sets no request timeout at all, so the same operation completed on the page and failed on the command line.
- `_io.call` caught every `httpx.TransportError` — connection refused, connection dropped, and no answer in time — and reported each as the daemon being unreachable. A slow answer read as a crash.

About 230 commands are declared over one route each (`RouteCommand`). Most answer in milliseconds; a few dozen make a call out (a provider, an MCP server, a platform API, an OpenAPI document, a CLI's version probe) or run git over the network (a skill's Git source, a vault sync round). The CLI is mostly run by agents, whose shell tools carry their own limits (Claude Code's default is 2 minutes, configurable), so a command that hangs forever is as bad as one that gives up early.

How comparable command lines wait for their server:

| Tool | Client wait |
| --- | --- |
| kubectl | `--request-timeout`, default 0 (wait forever); long work uses `kubectl wait --timeout` |
| Docker CLI, gh, Ollama | no read timeout on API calls; pulls stream progress |
| AWS CLI | connect and read limits apart (`--cli-connect-timeout`, `--cli-read-timeout`, 60 s each, 0 = forever) |
| git | no overall timeout |
| `coffer sync wait` | an operation that runs on after its request, polled with `--timeout`, exit 13 when it runs out |

## Options Considered

### Option A — A wait declared per command, longer than the daemon's own deadline (chosen)

Connecting gets its own short limit (5 s): the daemon is on this machine, so a connection that takes longer is not coming. Waiting for the answer is declared by the command: 15 s by default; 90 s for a route that makes a call out (the daemon bounds those at 60 s or less: provider introspection 30 s, MCP preview 35 s, model calls 60 s, OpenAPI fetch 20 s); 330 s for a route that runs git over the network. For a skill's Git source the daemon now holds one whole operation to 300 s, so the CLI's 330 s means the daemon always answers first, with its specific `SKILL_SOURCE_UNREACHABLE`. `coffer --request-timeout <seconds>` replaces the wait for one command. The three transport failures are told apart: refused is `DAEMON_UNREACHABLE` (exit 3), dropped is `DAEMON_CONNECTION_LOST` (exit 3), and no answer in time is `CLI_REQUEST_TIMEOUT` (exit 13, the existing "a wait ran out"), naming the request and the wait and saying the operation may still finish.

- Good: a slow operation gets the daemon's real answer; a wedged daemon is still noticed in 15 s on an ordinary command; the message for each failure is true; the wait sits beside the route it is for, and a test pins the Git source commands to a wait longer than the daemon's deadline.
- Cost: each command that reaches out has to be declared. A new command that forgets falls back to 15 s; the timeout message then says what happened and how to wait longer, so the cost of forgetting is a clear message, not a false crash.

### Option B — No read timeout (kubectl, Docker, gh)

Keep only the connect limit and `--request-timeout`; wait for any answer as long as it takes.

- Good: simplest; never gives up on a slow but healthy daemon.
- Lost because a daemon that accepts a connection and never answers (a deadlock, a stuck subprocess) hangs every command forever. An agent's shell tool then kills the process with no message at all, which is worse than today. Docker and kubectl can afford it because they stream progress; Coffer's routes answer once.

### Option C — Long operations become jobs, polled until done

The route answers 202 with an operation id at once; the CLI polls a status route (as `coffer sync wait` does) and the web UI shows progress.

- Good: no request is held open; survives any client limit; progress can be shown.
- Lost on cost and scope: every slow route, its wire contract, the web UI's dialogs and the spec change shape, for a problem the waits in Option A already solve. It stays the right answer if an operation ever needs longer than an agent's shell tool allows.

### Option D — One longer wait for every command

Raise the single 15 s to, say, 300 s.

- Good: one line.
- Lost because an ordinary command against a wedged daemon would then wait five minutes before saying so, and the misreport of a timeout as a crash would remain.

## Decision

The CLI connects with a 5 s limit and waits for each answer as long as its command declares (`RouteCommand.wait`, or `timeout=` on a hand-written call): `_waits.QUICK_S` (15 s) by default, `NETWORK_S` (90 s) for a route that makes a call out, `GIT_S` (330 s) for one that runs git over the network. `coffer --request-timeout` replaces it. `_transport.classify` turns a transport failure into `DAEMON_UNREACHABLE`, `DAEMON_CONNECTION_LOST` or `CLI_REQUEST_TIMEOUT`; only the first two say the daemon may have crashed.

A command whose route reaches the network or runs git MUST declare a wait at least as long as the daemon's own deadline for that work plus a margin. A daemon deadline that grows must raise the wait with it.

## Consequences

- `coffer skill stage-git` and the other Git source commands report the daemon's own error (git's message, or "did not finish within 300 s") instead of a false crash.
- An agent can tell "start the daemon" (exit 3) from "check the result, or wait longer" (exit 13).
- A staged import the CLI stopped waiting for still completes on the daemon and expires after an hour (`STAGE_TTL_S`); no state is left that cannot be cleaned up.
- Enforced in `backend/coffer/surfaces/cli/_waits.py`, `_transport.py`, `_io.call`, and `tests/integration/surfaces/cli/test_cli_request_wait.py` (a real slow HTTP server, so no test depends on the network).
