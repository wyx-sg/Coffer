# Coffer

Coffer is this machine's local vault. It stands between you and the MCP servers
this developer registered, it holds what they have written down about their
working environment, and it holds the notes distilled from what every agent on
this machine has learned. This is the manual: what Coffer will do for you, and
what it will not.

## Coffer's own tools

Coffer adds one tool of its own, `coffer__search_tools`. Everything else you can
see through Coffer belongs to an upstream server and is named `<server>__<tool>`.
Reach for it when you need a capability and nothing in your tool list offers it.

If you cannot see Coffer's tools at all, the agent you are running as is not
connected to Coffer; the developer connects it with the Connect button on the agent's page in Coffer.

## The tools you were listed are not all the tools there are

Coffer aggregates every MCP server the developer registered and re-exposes them
through one endpoint. When that catalogue is large, `tools/list` carries only a
budgeted slice of it — the ones most used on this machine, with one slot
reserved per server so no server disappears entirely. **Everything left out is
still callable.**

So a tool you cannot see is not a capability you do not have. Call
`coffer__search_tools` with a plain-language description of what you need. It
ranks the *whole* catalogue, listed or not, and anything it hands back is
callable by exactly the name it returns, immediately — there is no enabling,
loading or registering step between the search result and the call.

Coffer's own `coffer__` tools are always listed and never consume that budget,
so this only ever concerns upstream tools.

<!-- when:knowledge -->
## Knowledge is a directory of files, and you read it yourself

The developer's knowledge lives under `<KNOWLEDGE_ROOT>/<collection>/`: one
tree of Markdown documents per collection, which the developer and Coffer's own
model write together.

**There is no Coffer tool for reading, listing, searching or grepping it.** Use
your own file tools on those paths. The full catalogue of what exists is at the
bottom of this file, so you never have to guess at a filename. When the titles
do not cover what you are after, grep the directory for a literal string — an
identifier, a service name, a phrase in any language. It matches bytes, so
nothing is stemmed away.

Check it before asking the developer something they may already have written
down.

### Writing something down

When you learn something durable — a fact about a service, a convention this
developer follows, a decision and the reason behind it, a trap and how to avoid
it — write a Markdown file into `<KNOWLEDGE_ROOT>/<collection>/.inbox/`, under
any name ending in `.md`. Frontmatter is optional: `title`, `description` and
`actor` (who you are, for example `claude-code`). Coffer fills in whatever is
missing, then its model merges the file into the collection's documents,
integrating it with what is already there. Write the fact plainly; you do not
have to work out where it belongs or check whether it repeats something. The
collection must already exist: only the developer creates one, so a file under
any other directory is ignored.

To correct or extend a document you have read, edit the file itself with your
own tools, as the developer does in their editor. Coffer's model notices the
edit and carries it into the rest of the collection as a newer statement. Where
two statements disagree the newer wins unless the older is shown right by a
source, a date, a command's output or the code, whoever wrote either.

Never run git inside the vault: Coffer records every change itself, and a
commit of your own would be attributed to nobody.

<!-- end:knowledge -->
<!-- when:memory -->
## Coffer reads your memory. It never writes it.

Coffer reads the native memory of every registered agent — your own memory
files, in your own format — and modifies nothing there: not a file, not a
format, not your memory setting. What it reads it distils into its own notes
under `<MEMORY_ROOT>`, which are derived and are Coffer's to own.

<!-- when:knowledge -->
The practical consequence: **you cannot ask Coffer to write a memory for you.**
Knowledge is a different store with a different purpose. If you want something
in your own memory, write it there yourself, the way you normally would.

<!-- end:knowledge -->
### Finding a note

Coffer's notes are Markdown files under `<MEMORY_ROOT>/<partition>/notes/`, one
partition per repository plus `global`. Your session opened with the index of
this repository's partition and of `global`. For a note from another project,
search `<MEMORY_ROOT>` with your own tools — grep for a distinctive word or
phrase — and read the file you find. There is no Coffer tool for this.

<!-- end:memory -->
## Nothing here waits on a human

Every tool Coffer exposes runs immediately. There is no approval prompt, no
suspended call, no pending state to wait on: the developer driving this session
is the trust boundary, and Coffer does not re-ask them per call.

When a call cannot proceed — a capability they disabled, a server not in scope
for you, a server whose secret is still waiting for the developer's approval —
it comes back in the same turn as an ordinary error result with the reason in
it. Read the reason and adjust. Do not retry the identical call hoping
it clears. A tool call itself never waits on an approval; the one thing in
Coffer that does is a secret going somewhere new, below.

## Secrets: you use them; Coffer never prints them

Coffer holds the developer's secrets and never prints one — not through a tool,
not through the `coffer` CLI, not through its API. There is no command or
option that shows a value, and nothing to work around. Only the developer sees
a value, in the Coffer desktop app.

When a command needs a secret, run it through `coffer run`, which sets the value
only in that command's environment and prints it as `***` in its output. The
masking guards against a value leaking into a transcript by accident; it is not
a wall between you and the value, since you are the command's parent:

```sh
coffer run --secret PGPASSWORD=orders-db -- psql -h db.internal orders
coffer run --env-file connection.env -- ./query.sh
```

A secret for `coffer run` is a standalone secret, stored as `secret/<name>` and
cited in files as `coffer://secret/<name>`. Write that reference into skills,
scripts and env files — never the value. `coffer secret list` shows what
exists; `coffer secret set <name>` stores a value read from stdin. If you find a
plaintext secret left in a file or in a skill, tell the developer to store it as
a secret and cite it by `coffer://secret/<name>`.

A secret that would go somewhere it has not gone before — a new MCP server
citing an existing token, a changed command line or URL —
waits for the developer's approval in the Coffer app (a command that hits this
prints `waiting for approval in the Coffer app` and exits `9`). That is not an
error to retry or to route around: tell the developer what is waiting.

## Command-line tools Coffer manages

Coffer keeps track of the command-line tools this developer relies on: the ones
skills require, the launchers MCP servers start with, and the ones the
developer added by hand, each with what it is for. `coffer cli list` prints
them with whether each is ready, missing, outdated or logged out on this
machine as of Coffer's last check; `coffer cli list --json` adds, for one that
needs attention, the prompt for installing, updating or logging in to it. Read
it before concluding a tool is unavailable, or to learn which tool this
developer uses for a job. Coffer installs nothing itself: a missing or
logged-out tool is one to set up as that prompt says, or to raise with the
developer.

## When Coffer itself misbehaves

Coffer keeps three records of what it did: its audit log (what changed), its
MCP invocation log (every tool call through it) and its daemon log (what
happened, including what broke). Read them with `coffer log audit`,
`coffer log mcp` and `coffer log daemon`. Each takes `--since` (an age such as
`1h`, or an ISO 8601 instant) and `--limit`; `coffer log daemon --errors` and
`coffer log mcp --status error` narrow to failures, and `coffer log audit`
narrows with `--kind`, `--name` and `--event-type`. All three take `--trace <id>`:
the trace id of one request or turn (an `X-Coffer-Trace` header, or the id a
record already shows), which returns that request's audit rows, tool calls and
log lines and nothing else. `coffer path logs` finds the daemon's log files. Reach for them when a Coffer tool fails in a way its error
text does not explain, not as a debugger for the developer's own program.

<!-- when:knowledge -->
## What not to put in

- **No secrets.** No keys, tokens, passwords or secrets — not in knowledge,
  not anywhere you write through Coffer. The developer's secrets live in an
  encrypted store Coffer keeps separately, and nothing you write reaches it.
- **Not the repository in front of you.** If the answer is in code you can
  already read, read the code. Knowledge is for what the repository cannot say.
- **Not a scratch pad.** What goes in should still be true in a month.
- Address knowledge files by collection and relative path. A path that climbs
  out of the knowledge root is refused.

<!-- end:knowledge -->
## This file

Coffer wrote it and Coffer rewrites it — at every daemon start, and whenever the
catalogue below changes. Editing it has no lasting effect. It is the same file
for every agent on this machine.
