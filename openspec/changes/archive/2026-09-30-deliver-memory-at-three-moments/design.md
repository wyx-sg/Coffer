# Design — deliver memory at three moments

The decision and its evidence are the ADR
[Memory Reaches a Session at Three Moments](../../../docs/decisions/memory-reaches-a-session-at-prompt-time-and-before-a-known-trap.md);
the architecture is [docs-site/architecture/memory.md](../../../docs-site/architecture/memory.md).
This records the implementation choices a reviewer would ask about.

## One command on four events

Every entry runs `coffer memory hook --agent-uid <uid> --cwd "$PWD"`. The
event arrives in the hook's own stdin JSON (`hook_event_name`), which both
agents send in the same shape (`tool_name: "Bash"`, `tool_input.command`,
`tool_response`), and both read the same `hookSpecificOutput` back. One
command means one string to judge for staleness and one hash shape per entry
for Codex. The alternative — a command per event with the event baked in —
would have multiplied the stale-command surface by four for no behaviour.

The CLI answers locally what needs no daemon: a trivial prompt, or a shell
command no armed trigger in `vault/memory-triggers/` matches. So an ordinary
command costs a process start and a directory read, not a round-trip. The
daemon still decides everything that depends on state: which partition the
session is in, whether the note is reachable, whether this session already had
it.

## The session ledger is in memory

"Once per session" and "never the same note twice" are kept per `session_id`
in the daemon, bounded to the 2,048 most recent sessions. A daemon restart
forgets them: a session may then be given a note again or have a trigger hold
one more command. That is cheaper than a table (the layer adds none) and the
harm is one repeated line or one extra deny.

## The ranking index

`domain.memory.retrieval` is the prototype's BM25 (k1 1.2, b 0.75), its
tokeniser (word tokens, CJK bigrams, a small stopword set) and its floor of 4.0,
so the eval numbers carry over. The index is built per repository partition
together with `global` and rebuilt when either `notes/` changes by name, mtime
or size.

## Triggers are vault files

`vault/memory-triggers/<id>.md`, frontmatter plus an optional body. They are
authored, so they sit in the vault and survive a rebuild of the derived memory
tree. A trigger names its note as `<partition>/<slug>`; the reason shown is the
note's current substance, so a rewritten note updates its trigger's message,
and the body is the fallback when the note is gone. Distil proposes through an
optional `trigger` field on the writing stage's answer (a command regex and an
`unless` regex); the proposal is filed unarmed and deduplicated on note, kind
and patterns.

## What "notes read" counts

Only tool-call arguments are looked at, and only for a path under the memory
root naming a note. A line of a transcript is parsed only when it mentions the
memory root at all, and each file's answer is cached by mtime and size, so a
week of large transcripts is read once.
