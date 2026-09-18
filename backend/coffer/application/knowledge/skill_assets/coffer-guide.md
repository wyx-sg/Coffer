# Coffer

Coffer is this machine's local vault. It stands between you and the MCP servers
this developer registered, it holds what they have written down about their
working environment, and it holds the notes distilled from what every agent on
this machine has learned. This is the manual: what Coffer will do for you, and
what it will not.

## Coffer's own tools

Four, all prefixed `coffer__`. Everything else you can see through Coffer
belongs to an upstream server and is named `<server>__<tool>`.

| Tool | Reach for it when |
| --- | --- |
| `coffer__search_tools` | You need a capability and nothing in your tool list offers it. |
| `coffer__write` | You learned something durable about this environment. |
| `coffer__recall` | You want a note from a project other than this one. |
| `coffer__diagnose` | Coffer itself is misbehaving and you want its side of the story. |

If you cannot see these at all, Coffer's MCP server is not installed for the
agent you are running as; the developer installs it with
`coffer agent mcp install <agent>`.

`coffer__diagnose` answers with two correlated timelines for a window you
choose — what changed in Coffer (its audit log) and what its daemon logged —
so reach for it when a Coffer tool fails in a way its error text does not
explain, not as a general-purpose debugger for the developer's own program.

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

The developer's knowledge lives under `<KNOWLEDGE_ROOT>/<collection>/`, split
into two lanes:

- `sources/` — what a person or an agent wrote down, in the words they wrote it.
- `topics/` — what Coffer's own model folded those sources into. This is the
  lane worth reading.

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
and how to avoid it. What you write is filed as **source material** under
`sources/`, and Coffer's model later folds it into the topic documents, merging
it with what is already there.

So write the fact plainly. You do not have to work out where it belongs, and
you do not have to check whether it repeats something already filed.

Do not write into `topics/` yourself and do not edit those files — they are
generated, and the next pass overwrites them. A correction goes in as a new
source saying what is actually true.

## Coffer reads your memory. It never writes it.

Coffer reads the native memory of every registered agent — your own memory
files, in your own format — and modifies nothing there: not a file, not a
format, not your memory setting. What it reads it distils into its own notes
under `~/.coffer/memory/`, which are derived and are Coffer's to own.

The practical consequence: **you cannot ask Coffer to write a memory for you.**
`coffer__write` files knowledge, which is a different store with a different
purpose. If you want something in your own memory, write it there yourself, the
way you normally would.

`coffer__recall` locates Coffer's notes. It answers with each note's path, title
and one-line description, never the body — read the file yourself when you want
that. Its matching is literal and case-insensitive, so hand it a distinctive
word or phrase rather than a question.

## Nothing here waits on a human

Every tool Coffer exposes runs immediately. There is no approval prompt, no
suspended call, no pending state to wait on: the developer driving this session
is the trust boundary, and Coffer does not re-ask them per call.

When a call cannot proceed — a capability they disabled, a server not in scope
for you — it comes back in the same turn as an ordinary error result with the
reason in it. Read the reason and adjust. Do not retry the identical call hoping
it clears, and do not tell the developer you are waiting on an approval: there
is nothing to approve.

## What not to put in

- **No secrets.** No keys, tokens, passwords or credentials — not in knowledge,
  not anywhere you write through Coffer. The developer's credentials live in an
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
