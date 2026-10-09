# Coffer

Coffer is this machine's local vault. It stands between you and the MCP servers
this developer registered, it holds what they have written down about their
working environment, and it copies what each of their agents has learned into
the others' own memory. This is the manual: what Coffer will do for you, and
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
tree of Markdown documents per collection, which the developer and agents like
you write together.

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
it — put it into the collection's documents yourself, with your own file tools.
Coffer does not rewrite what you write: where a fact ends up is your decision,
so make it the right one.

1. **Find its home.** Read the catalogue at the bottom of this file and grep the
   collection for the subject. If a document already answers the question this
   fact belongs to, read that document in full and fold the fact into the
   section it belongs in. Only when no document owns the subject, create a new
   file at a slug of its title (`session-ownership.md`).
2. **Lose nothing.** Integrate; never regenerate. Every fact already in a
   document you rewrite must survive your edit.
3. **Organise by subject, never by provenance.** A reader wants the document to
   be about the thing. Never add sections like "Added today" or "From the
   ticket" — put the fact where a reader would look for it.
4. **Where two statements disagree, the newer wins unless the older one is
   shown to be right** — by a source, a date, a command's output or the code.
   Whoever wrote either, the developer included. Keep the superseded statement
   legible where the corrected fact is: "(previously recorded as X; corrected
   YYYY-MM-DD)".
5. **Never name another knowledge file.** Paths move as the collection is
   reorganised; name the subject in prose. The catalogue is how a reader finds
   the file.
6. **Give every document frontmatter**: a `title`, a one-line `description`
   saying what *question* the document answers (it is the only thing a future
   reader chooses by), and `actor: agent`. Leave any other key a person added
   alone.

The collection must already exist: only the developer creates one. Coffer
commits every change it finds on disk to the vault's git history, so a bad edit
can be brought back from it; never run git inside the vault on your own
initiative, because a commit of your own would be attributed to nobody. The
developer reads a document's versions and restores an earlier one from its
History tab in Coffer.

### Tidying a collection

When the developer asks you to tidy, organise or clean up knowledge (整理知识),
work through one collection at a time:

1. Read its README and every document's title and description, then read the
   documents in full before changing them.
2. **Merge** documents that answer the same question into one, keeping every
   fact; delete the ones you merged away.
3. **Split** a document that answers several unrelated questions, one subject
   per file.
4. **Fix** what is wrong or contradictory by rule 4 above, and rewrite a
   description that does not say what question its document answers.
5. Move a document into a subfolder only if that makes the tree easier for a
   person to browse; folders carry no meaning to Coffer.
6. Report what you merged, split, corrected and deleted, so the developer can
   check it against the vault's git history.

Change nothing that does not need changing.

<!-- end:knowledge -->
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
only in that command's environment and prints it as `***` in its output. It
works only for a secret the developer granted to local programs in the Coffer
app (once per secret). Without the grant it starts nothing, prints no value,
exits non-zero, and the request waits in the app's approvals
(`SECRET_BINDING_PENDING`; `SECRET_BINDING_REJECTED` if refused): tell the
developer which secret you need rather than retrying. The masking guards against
a value leaking into a transcript by accident; it is not a wall between you and
the value, since you are the command's parent. A secret you should only use
stays ungranted and reaches its service through Coffer (an MCP server or a
custom HTTP tool). For example:

```sh
coffer run --secret PGPASSWORD=coffer://secret/orders-db -- psql -h db.internal orders
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

## Where a skill's scripts keep their files

A skill's scripts write the logs, operation journals and temp files they
generate under `~/.coffer/skill-data/<skill-name>/`; `coffer path skill-data`
prints the directory. Never write them inside the skill's own folder (that is
the synced vault) and never elsewhere in `~/.coffer`. Coffer deletes files
there after the Skill working files retention window (30 days by default,
set in Settings › Data), so durable data does not belong there.

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
