# A Provider's and a Channel's Name Is Free Text, and Their Files Are Named by uid

**Status**: Accepted
**Date**: 2026-10-09
**Deciders**: Yuxing Wu
**Related**: [A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](identity-is-the-uid-inside-the-file.md), [Names Visible to Agents Are Fixed](names-visible-to-agents-are-fixed.md), [Kind Plug-in Contract](kind-plugin-contract.md), [Every Vault File Carries Its Format Version](every-vault-file-carries-its-format-version.md), spec resource-framework "Name a provider or a channel with free text", spec channels "Name a channel by any display name", architecture TODO O-10

## Context

Every resource had a `name` held to `^[a-zA-Z0-9_.-]+$` (at most 64
characters), and a provider, a channel or a memory could carry a second label,
an optional free-text `title` of at most 80 characters that surfaces showed in
the name's place. The slug rule exists for the kinds whose name is quoted
outside Coffer — an MCP server's name is in every tool name an agent calls, a
skill's is the directory an agent loads it from ([Names Visible to Agents Are
Fixed](names-visible-to-agents-are-fixed.md)) — and those kinds already carry no
title.

A provider and a channel are named only on Coffer's own surfaces. Nothing an
agent reads names them: the proxy token Coffer projects into an agent's config
does not, and a channel turn's origin block now hands the agent the channel's
uid for the one tool that takes a channel. For these two kinds the slug was a
rule with no reader, and the title existed only to get around it:

- **Two labels for one thing.** Every surface had to choose (`displayName` in
  the web UI), the CLI listed the slug while the app showed the title, and a
  search had to match both.
- **A name nobody chose.** Adding a channel asked for a display name, derived a
  slug from it (`My Team Bot` → `my-team-bot`, and Chinese text → nothing
  usable), and stored the typed text as the title. Renaming changed one label
  and not the other.
- **The file was named after the slug.** `resources/<kind>/<name>.json` was
  safe because the name was; a free-text name is not a safe file name
  (`/`, `:`, emoji, a case-insensitive APFS volume), and a rename moved the file.

How comparable products name a configured connection:

| Product | Identity | What a person names it | Where it is stored |
| --- | --- | --- | --- |
| Home Assistant config entries | `entry_id` (opaque) | `title`, free text, editable | One store file keyed by `entry_id` |
| Grafana data sources | `uid` (opaque, used in references) | `name`, free text, editable, unique | Database row; provisioning references by `uid` |
| 1Password items | `uuid` | `title`, free text | Keyed by `uuid` |
| n8n credentials | `id` | `name`, free text, editable | Database row by `id` |
| Kubernetes objects | `metadata.uid` | `metadata.name`, a DNS slug, immutable; display text in annotations | etcd key by name |

Where the name is a person's label and an opaque id carries the identity, the
name is free text and the storage key is the id. Kubernetes keeps a slug
because the name is the API address — the same reason Coffer fixes an MCP
server's name.

## Options Considered

### Option A — The name is free text, no title, and the file is named by uid (chosen)

`Kind.free_name` (`domain/resource.py`), set by `provider` and `channel`. The
name is whatever a person types: trimmed, NFC-normalised, 1–80 characters, no
control characters (a newline would split a log line or a chat message), no
leading `-` (the CLI would read it as an option). Two resources of the kind may
not share a name ignoring case — a person told apart by sight cannot tell
`Work` from `work`. The file is `resources/<kind>/<uid>.json`, so a rename
rewrites one field and never moves the file. No kind carries a `title`.

- **Pros.** One label, the one a person typed, everywhere: app, CLI, audit,
  attention. Any language. A rename is a one-field edit with no file move, so a
  rename on one machine and an edit on another never conflict over the path.
  The name rule lives in one function for both kinds.
- **Cons.** The file name no longer says which provider a file is; a person
  browsing the vault reads the `name` inside it. A one-time migration rewrites
  existing files (title into name, file to its uid).
- **Why it wins.** The file name is read by almost no one, and the label is read
  on every screen. It is how the products above do it.

### Option B — Keep the slug name and the optional title (the design this replaced)

- **Pros.** No migration. The file name stays readable.
- **Cons.** Everything in the Context: two labels, a derived slug nobody chose
  and that fails for non-Latin text, a rename that changes one of them.
- **Why it loses.** The slug has no reader for these two kinds; it only made
  the title necessary.

### Option C — Free-text name, file named after the name where it is a safe file name

`My Bot` → `My Bot.json`; an unsafe name falls back to a sanitised stem or the
uid, and a rename moves the file, as fixed-name kinds do.

- **Pros.** A readable file name in the common case.
- **Cons.** Two naming rules for one directory, decided by the characters a
  person typed. A rename moves the file, so a rename on one machine and an edit
  on another meet as a rename/modify conflict in the merge. Case-only renames
  are a no-op on a case-insensitive volume.
- **Why it loses.** It pays in merge conflicts and special cases for a file
  name that nearly no one reads.

### Option D — Free-text name, file named by a slug taken once at creation

- **Pros.** Readable at first; no move on rename.
- **Cons.** After a rename the file name says something else; a stale name is
  worse than an opaque one. Non-Latin names still have no slug.
- **Why it loses.** It looks readable and then misleads.

### Option E — Make every kind's name free text

- **Pros.** One rule for all kinds.
- **Cons.** An MCP server's name is part of every tool name an agent calls and
  a skill's is a directory an agent loads; agents' names are their types.
- **Why it loses.** [Names Visible to Agents Are Fixed](names-visible-to-agents-are-fixed.md)
  still holds for those kinds.

Uniqueness was weighed the same way: exact match lets `Work` and `work` both
exist, which nobody can tell apart in a list; no uniqueness at all (n8n) makes
`coffer provider show <name>` ambiguous. Ignoring case is the rule that keeps
a name a usable handle.

## Decision

`provider` and `channel` declare `free_name`. Their name is free text (trimmed,
NFC, 1–80 characters, no control characters, no leading `-`), unique within
the kind ignoring case, and editable through the ordinary rename. Their files
are `resources/<kind>/<uid>.json` and stay there on rename. Every other kind
keeps its slug name and its name-derived file. No kind carries a `title`; the
key is gone from the resource document.

## Consequences

- A one-time migration (`infrastructure/vault/free_name_migration.py`, run
  before the resource store first reads) rewrites every provider and channel
  file with the old shape: a non-blank title becomes the name (`` (2)``,
  `` (3)``… on a clash ignoring case, a kept name winning over a title), the
  `title` key is dropped, and the file moves to `<uid>.json`. Its plan is a pure
  function of the files, so two machines migrating the same vault commit the
  same change; it is delete-able once every machine runs this build.
- The vault layout version is not raised. A machine still on the previous
  build judges a migrated provider file invalid, so its sync round stops with
  that file named on the attention list until the machine is updated; nothing
  is lost or overwritten meanwhile. Raising the layout instead would have the
  first updated machine replace the remote with its own vault, dropping from
  the tip whatever another machine pushed and it had not yet pulled — a
  bigger cost than a paused sync on a machine that updates itself.
- A channel turn's origin block reads `channel: "<name>" (id: <uid>)` and
  `coffer__channel_read_thread` takes the uid, so a rename never breaks a call
  an agent is about to make.
- `PATCH /api/v1/resources/{uid}` and every create route take no `title`; the
  generic routes accept up to 80 characters for a name and leave the kind's
  rule to the service.
- Enforced in `domain/resource.py` (`normalise_free_name`, `same_free_name`),
  `application/resource_kind_ops.check_name`, the store's naming and collision
  checks (`infrastructure/vault/resource_store.py`) and the vault validator
  (`application/vault/resource_rules.py`).
