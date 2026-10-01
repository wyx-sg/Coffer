## Context

A round's push publishes more than the files as they are now: git sends every
object the remote lacks, so every version of every file in every unpushed
commit. Coffer commits each write on its own, so "a value was pasted, then
removed" is two local commits, and the first still holds the value.

## Decisions

### Read what the push publishes, not only the current files

The check lists the blobs reachable from the commit being pushed and not from
the remote's head (`git rev-list --objects --filter=object:type=blob`), and
reads each one. Reading only the tree being pushed would publish the value in
the history of any file that was fixed before the round ran, which is exactly
the file the person just fixed.

### Reuse `coffer secret scan`'s detection

The detection is the one the Secrets page's "Find plaintext keys" and
`coffer secret scan` already use for skill files: an assignment whose name
says secret (`DB_PASSWORD=…`, `api_key: …`) with a value of eight or more
characters that is not a reference, an interpolation or a placeholder, and the
well-known token shapes (GitHub, OpenAI-style `sk-`, Slack, AWS access keys).
A line that runs `coffer run` names secrets rather than holding one. No new
dependency and no second rule set to keep in step: a finding the round names
is one the Secrets page would name too. A blob that is binary or over 1 MB is
not read. `secret/<ref>.enc` is ciphertext and is skipped by path.

### Stop only on what a file still holds; fold what only history holds

- A finding whose blob is the file's version at the commit being pushed stops
  the round, `plaintext_found`, before anything is pushed. Pulling and
  applying still happened; only the push waits.
- When every finding is only in history, the fix is already made, and the
  person cannot remove a blob from unpushed history without rewriting it. The
  round does that one rewrite itself: one commit on the remote's head with the
  same tree, checked out in place of the unpushed ones under the vault's write
  lock (the tree is identical, so no file on disk changes). The round records
  how many commits it folded.

The cost of folding is the per-commit history of those unpushed edits, merged
into one entry. The pre-round snapshot and git's reflog still hold the
originals on this machine, which never leave it.

### "Push anyway" allows blobs, not files

The detection can be wrong: an example key in a document, a test value. The
person's override allows exactly the blobs the last round found, and is kept
in `local/sync/round.json` (machine-local). A file edited since is a new blob
and is read again, so the override never covers a value it was not shown. The
event is audited with the files and lines, never the values. The HTTP route
and the CLI command are the same operation (the CLI asks first unless given
`--yes`), so REST/CLI parity holds.

### The hand-off, not a button, moves the value

Moving a value into a secret depends on the file: a resource's field takes a
`coffer://secret/<name>` reference, a skill's command needs `coffer run
--secret`. The prompt names each file, line and key, tells the agent to pipe
the value into `coffer secret set` without ever printing it, and leaves Retry
and Push anyway to the person.
