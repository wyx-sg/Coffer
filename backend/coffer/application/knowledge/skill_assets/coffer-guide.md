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
## Knowledge is files, and each collection sets its own rules

The developer's knowledge lives under `<KNOWLEDGE_ROOT>/<collection>/`, one
folder of Markdown files per collection, which the developer and agents like
you write together. **Coffer sets no format for it.** Each collection decides
its own layout, page types, frontmatter and upkeep, and writes them in its
**rules file**; the catalogue at the bottom of this file names each one's rules
file and, where it has one, the page to start reading at.

- **Before you write in a collection, read its rules file** and follow it. It
  wins over anything you would do by default. A collection that names none is
  written the way its existing files are written.
- **Read from its start page** (an `index.md`, say) when it names one; otherwise
  the catalogue lists its files with their titles.
- Its `README.md` says what it is about: its first paragraph is the description
  you see below. The keys at the top of the README are what it declares to
  Coffer: `rules`, `entry` and `uploads`.

**There is no Coffer tool for reading, listing, searching or grepping it.** Use
your own file tools on those paths, and grep for a literal string (an
identifier, a service name, a phrase in any language) when the start page does
not lead you there; follow the collection's rules on what to read first.

Check it before asking the developer something they may already have written
down. When you work out an answer the collection does not already give, by
reading the code, a system or a document, write it back where its rules say,
and tell the developer in one line what you added. Do not write back a guess,
an opinion, or something true only of this conversation.

What Coffer does with a collection, whatever its format:

- It keeps every change in the vault's git history, so the developer can read
  a file's versions and restore one. Never run git inside the vault on your own
  initiative: a commit of your own would be attributed to nobody.
- It reports every **broken link**: a `[[slug]]` (a file's name without `.md`,
  or one of its frontmatter `aliases`) that names no file or more than one, a
  relative link to a file that is not there, and one that climbs out of the
  knowledge root. Links in the uploads folder are not checked: that material is
  kept as it arrived.
- It writes uploads into the collection's **uploads folder** (`sources/` unless
  the README's `uploads` names another), converted to Markdown; an upload with
  pictures is a folder holding the source and its pictures side by side. Coffer writes `title`, `description`, `actor`, the
  timestamps, `original` and `original_sha256` on what it writes there; leave
  those keys as they are.
- Nothing else: it never moves, renames or rewrites a file you write, and it
  never asks a file for a key.

The collection must already exist: only the developer creates one.

Some collections are **linked folders**: folders the developer keeps with their
own tools, an Obsidian vault say, which Coffer shares with you but does not
keep. Each one's section in the catalogue names its own path and rules file.
Read it the same way; write in it only by its rules, and do not tidy, upload
into or drop files for the inbox of one.

### Memory, knowledge or a skill

Your own memory is for the developer: who they are, how they want you to work
(preferences, corrections, what they approve), and a project's current state
that the repository does not record. Knowledge is for the world: how an
outside system, team or process works, its pitfalls, anything that needs a
source, goes stale or is worth sharing. A fixed sequence of steps they repeat
is a skill. Ask in that order: would it still hold for someone else (no:
memory); is it about an outside system or does it need a source (yes:
knowledge); is it a procedure (yes: skill). What the repository already says,
and a one-off request, belong nowhere. Coffer keeps a memory you filed as task
notes away from the developer's other agents until it is sorted, so write such
a fact into knowledge instead.

### Bringing in a Confluence page

Export it with the developer's Confluence tool as JSON, with its attachments,
and run `coffer knowledge upload <collection> <page>.json` (`--attachments
<dir>` adds attachments downloaded beside it). Coffer converts its macros,
keeps its attachments, and names what it could not keep in the source's
`import_report`; `--preview` shows all of that and writes nothing. A page
imported before is refused until you add `--replace`, which keeps the older
file and marks it `superseded_by` the new one. The file's `origin` says where
it came from and when it was fetched. What to do with it next is the
collection's rules.

### Tidying a collection

When the developer asks you to tidy, organise or clean up knowledge (整理知识),
work through one collection at a time:

1. Run `coffer knowledge tidy-start <collection>` before you change anything.
   Until you finish, Coffer keeps your edits in that collection together, so
   the developer sees the whole tidy as one change and can undo it at once.
2. Read the collection's rules file and tidy it by those rules: what they say
   a tidy checks and fixes is the tidy. Fix every broken link Coffer reports
   (`coffer knowledge check <collection>` prints them).
3. Leave alone what you are not sure about (two files that disagree with
   nothing to tell which is right, a deletion of much text, a change to the
   rules file) and put it in your report for the developer to decide.
4. Run `coffer knowledge tidy-finish <collection> --set summary="<report>"`.
   The report says what you changed and what you left for the developer, and
   ends with **Gaps**: questions the collection cannot answer and sources worth
   finding. It is shown with the tidy in the collection's change log.

Change nothing that does not need changing. When the developer asks only for a
check or a review, report what you would do and change nothing.

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

Call a tool whatever its response may hold. A response that carries a login
token, a password or personal data is no reason to refuse, disable or postpone
a tool, or to wait for Coffer to filter it: Coffer hands back what the upstream
answers, and the developer who gave you the tool decided that. Use what you
need from it, and do not repeat a credential in a reply, a file or a memory.

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
coffer run --secret PGPASSWORD=coffer://secret/<id> -- psql -h db.internal orders
coffer run --env-file connection.env -- ./query.sh
```

Always name the variable (`ENV=coffer://secret/<id>`). A tool that wants a
file rather than a variable (a service-account JSON, a kubeconfig) gets one
from inside the child, so the value never leaves it:

```sh
coffer run --secret SA_JSON=coffer://secret/<id> -- sh -c \
  'f=$(mktemp) && trap "rm -f $f" EXIT && printf %s "$SA_JSON" > "$f" &&
   GOOGLE_APPLICATION_CREDENTIALS="$f" gcloud …'
```

A secret for `coffer run` is a standalone secret, stored as `secret/<id>` (Coffer
mints the id) and cited in files as `coffer://secret/<id>`. Write that reference
into skills, scripts and env files — never the value. `coffer secret list` shows
what exists and each secret's name; the developer adds one on the Secrets page
or with `coffer secret set --name "<name>"`, which prints the reference. If you
find a plaintext secret left in a file or in a skill, tell the developer to move
it with Find plaintext keys on the Secrets page.

A secret that would go somewhere it has not gone before — a new MCP server
citing an existing token, a changed command line or URL —
waits for the developer's approval in the Coffer app (a command that hits this
prints `waiting for approval in the Coffer app` and exits `9`). That is not an
error to retry or to route around: tell the developer what is waiting, and
leave the request for them to answer. Refusing it is theirs, in the app.

## Command-line tools the developer uses

`coffer cli list` lists the command-line tools this developer added to Coffer
and the ones skills and MCP servers require, each with what it is for. When
choosing a tool for a job, prefer the one listed for it. Whether a tool is
installed, new enough or logged in, check yourself (`command -v`, its
`--version`, its own status command);
if one a skill needs is missing, `coffer cli list --json` carries Coffer's
install prompt for it.

## Adding MCP servers and HTTP APIs

When you add an MCP server that starts with `npx` or `uvx`, write the
package's version into its arguments (`npx -y @acme/server@1.4.2`,
`uvx acme-server==1.4.2`): an unpinned package can change under the developer
between two starts. To turn an API document (an OpenAPI spec, a page of
examples) into tools, create a group with `coffer custom-tool group create`
and add each request you need with `coffer custom-tool tool add`; test one with
`coffer custom-tool tool test`. `coffer custom-tool --help` lists the rest.

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
- Address knowledge files by collection and relative path. A link that climbs
  out of the knowledge root is reported.

<!-- end:knowledge -->
## This file

Coffer wrote it and Coffer rewrites it — at every daemon start, and whenever the
catalogue below changes. Editing it has no lasting effect. It is the same file
for every agent on this machine.
