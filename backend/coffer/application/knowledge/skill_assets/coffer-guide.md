# Coffer

Coffer is this machine's local vault. It stands between you and the MCP servers
this developer registered, it holds what they have written down about their
working environment, and it holds the notes distilled from what every agent on
this machine has learned. This is the manual: what Coffer will do for you, and
what it will not.

## Coffer's own tools

Coffer adds two tools of its own, prefixed `coffer__`. Everything else you can
see through Coffer belongs to an upstream server and is named `<server>__<tool>`.

| Tool | Reach for it when |
| --- | --- |
| `coffer__search_tools` | You need a capability and nothing in your tool list offers it. |
| `coffer__write` | You learned something durable about this environment. |

If you cannot see Coffer's tools at all, the agent you are running as is not
connected to Coffer; the developer connects it with `coffer agent connect <agent>`.

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

Use `coffer__write` when you learn something durable: a fact about a service, a
convention this developer follows, a decision and the reason behind it, a trap
and how to avoid it. What you write is **new material**: Coffer's model merges
it into the collection's documents, integrating it with what is already there.
With no internal model configured, it is filed as a document of its own, and
the result names that document.

So write the fact plainly. You do not have to work out where it belongs, and
you do not have to check whether it repeats something already filed.

To correct or extend a document you have read, you may also edit the file
itself with your own tools, as the developer does in their editor. Coffer's
model notices the edit and carries it into the rest of the collection.

## Coffer reads your memory. It never writes it.

Coffer reads the native memory of every registered agent — your own memory
files, in your own format — and modifies nothing there: not a file, not a
format, not your memory setting. What it reads it distils into its own notes
under `<MEMORY_ROOT>`, which are derived and are Coffer's to own.

The practical consequence: **you cannot ask Coffer to write a memory for you.**
`coffer__write` files knowledge, which is a different store with a different
purpose. If you want something in your own memory, write it there yourself, the
way you normally would.

### Finding a note

Coffer's notes are Markdown files under `<MEMORY_ROOT>/<partition>/notes/`, one
partition per repository plus `global`. Your session opened with the index of
this repository's partition and of `global`. For a note from another project,
search `<MEMORY_ROOT>` with your own tools — grep for a distinctive word or
phrase — and read the file you find. There is no Coffer tool for this.

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
not through the `coffer` CLI, not through its API. `coffer secret get
<ref>` only says `[redacted]` or exits `4`; there is no option that shows the
value, and nothing to work around. Only the developer sees a value, in the
Coffer desktop app.

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
exists; `coffer secret scan` finds plaintext secrets left in `~/.coffer/secrets/`
and in skills.

You may configure Coffer freely, but a secret that would go somewhere it has not
gone before — a new MCP server citing an existing token, a changed command line
or URL, a replaced value — waits for the developer. The command prints `waiting
for approval in the Coffer app` and exits `9`. That is not an error to retry or
to route around: tell the developer what you set up and that it is waiting for
their approval in the Coffer app.

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

## What not to put in

- **No secrets.** No keys, tokens, passwords or secrets — not in knowledge,
  not anywhere you write through Coffer. The developer's secrets live in an
  encrypted store Coffer keeps separately, and nothing you write reaches it.
- **Not the repository in front of you.** If the answer is in code you can
  already read, read the code. Knowledge is for what the repository cannot say.
- **Not a scratch pad.** What goes in should still be true in a month.
- Address knowledge files by collection and relative path. A path that climbs
  out of the knowledge root is refused.

## This file

Coffer wrote it and Coffer rewrites it — at every daemon start, and whenever the
catalogue below changes. Editing it has no lasting effect. It is the same file
for every agent on this machine.
