# A Linked Knowledge Folder Is Shared in Place, Read-Only to Coffer, and Recorded Machine-Local

**Status**: Accepted
**Date**: 2026-10-12
**Deciders**: Yuxing Wu
**Related**: [Knowledge Is a Directory of Markdown Files, Not an Index](knowledge-is-plain-files.md), [Knowledge Is a Wiki of Pages Compiled From Kept Sources](knowledge-is-a-wiki-of-pages-compiled-from-kept-sources.md), [Tidying Knowledge Is the Agent's Job, One Hand-Off Recorded as One Change](tidying-knowledge-is-the-agents-job.md), [Coffer Ships Its Own Manual as a Skill Resource](coffer-ships-its-own-skill.md), [Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy](storage-is-five-classes-by-nature.md), [Channels Are Machine-Local Resources, Like Agents](channels-are-machine-local-resources.md), [A Kind Plugs In as One Frozen Record of Optional Hooks](kind-plugin-contract.md), spec knowledge "Link a folder the person keeps themselves", "Leave a linked folder to its own tools", spec vault-sync "Keep machine-local state out of the repository", OpenSpec change `link-external-knowledge-folders`

## Context

A collection Coffer keeps lives under `~/.coffer/vault/knowledge/<name>/`. Coffer
lays it out as a wiki (`README.md`, `sources/`, `pages/`, a hidden `.inbox/`),
commits every change to the vault's history, files loose Markdown into
`pages/`, checks it on every read, hands it to an agent to tidy, and syncs it
to the person's other Macs. That is the right treatment for knowledge Coffer
is meant to hold.

Many people already keep notes somewhere else, with tools they chose: an
Obsidian vault in `~/Documents`, a Logseq graph, a folder of Markdown in a
repository. They asked for that knowledge to reach their agents the way a
Coffer collection does, through the `coffer-guide` skill every agent reads,
without moving it. Two things about such a folder shape the decision:

- **It already has an owner.** The person edits it in Obsidian or another
  editor, often syncs it with that tool's own service (Obsidian Sync, iCloud,
  a git repository of their own), and lays it out by their own conventions. A
  second writer that reorganises it, or a second copy that diverges from it,
  would make it worse.
- **Its path is true of one machine.** `/Users/alice/Obsidian/Work` on one Mac
  may be `/Users/alice/Notes/Work` on another, or absent. This is the same
  property that made channels machine-local
  ([Channels Are Machine-Local Resources, Like Agents](channels-are-machine-local-resources.md)):
  a value that means something on one disk only.

When the feature was discussed, the person settled the scope: everything about
maintaining such a folder stays with the folder itself (全给那个知识集自己维护).
Coffer's part is to share it with agents. This ADR records how that is built
and why the obvious alternatives were not.

### How comparable products handle it

- **ChatGPT Projects and Claude Projects** take uploaded files into the
  project's knowledge. The upload is a copy: editing the original afterwards
  changes nothing the model sees until the person uploads it again.
- **AnythingLLM** and **Open WebUI** both ingest documents into a workspace or
  knowledge collection in their own storage, then chunk and embed them.
  AnythingLLM added a separate "watch" option that re-syncs a watched document
  on a schedule, which is the cost of the copy showing up as a feature.
- **Claude Code** reaches directories outside the working one through
  `--add-dir` and the `additionalDirectories` setting. The setting lives in a
  settings file on the machine, and the directory is read where it is; nothing
  is copied.
- **Obsidian** opens any folder as a vault ("Open folder as vault"). The folder
  stays where it is, and the list of vaults the app knows about is per
  machine.
- **Logseq** treats a graph as a folder on disk the person picks on each
  device; moving it between devices is the person's choice of sync tool.
- **The MCP filesystem server** is given its allowed directories as arguments
  in each client's configuration, on each machine. It serves them in place.
- **Cursor** indexes the open workspace where it sits; the files remain the
  person's, edited by any tool.

The products that copy are the ones whose job is to hold the knowledge. The
products that reference in place, and keep that reference per machine, are the
ones that work alongside the person's own files. Coffer's role here is the
second.

## Options Considered

### Option A — Copy or import the folder into the vault

"Link" runs an import: every Markdown file in the folder is copied into a new
collection under `vault/knowledge/`, as sources or pages, and from then on it
is an ordinary Coffer collection.

Pros: one kind of collection, so nothing in the knowledge layer branches; the
copy syncs, has history and can be tidied; the guide needs no new section.

Cons: two copies drift from the first edit. The person keeps writing in
Obsidian, which never sees what an agent wrote into the copy, and the agents
never see what the person wrote into the original until someone imports again.
A re-import has to decide which side wins for every file, which is a merge
problem Coffer would own for a folder it does not own. The import also changes
the files' layout (into `sources/` or `pages/`), so the copy is not even the
same tree.

Loses because it breaks the one thing the person wanted: their own tools and
their agents looking at the same notes.

### Option B — Reference the folder in place, read-only, with a machine-local row (chosen)

Linking records one `knowledge` resource whose config names the folder,
`{"folder": "<absolute path>"}`. The kind's storage hook files that row in the
machine-local class, `~/.coffer/local/resources/knowledge/`, because the path
is true of this disk only; a collection Coffer keeps stays in the vault. The
folder is read where it is:

- The collection list, the tree and the file routes read it through their own
  module (`infrastructure/knowledge/linked.py`) with its own path guard, since
  it lies outside the knowledge root. Hidden entries and `node_modules` are
  skipped, a walk stops at 5000 Markdown files, and a file over 2 MB is listed
  but not read into the page.
- The `coffer-guide` catalogue gives it a section of its own: its path, its
  rules file, its notes by title.
- Every action that would change it or needs its history (upload, delete,
  description edit, check, tidy, undo) is refused with
  `409 KNOWLEDGE_COLLECTION_LINKED`. The sweep, the tidy-all hand-off and the
  changes feed leave it out.
- Renaming changes only the label. Disconnecting deletes the row and leaves
  every file where it is.

Pros: the folder stays the single copy, edited by the tools that already own
it, and an agent sees each edit on its next read; Coffer cannot damage it,
because nothing in Coffer writes there; the row never reaches another machine,
so no other Mac ever holds a path that is wrong for it; it matches how Claude
Code, Obsidian, Logseq and the MCP filesystem server treat folders outside
their own store.

Cons: the folder gets none of what a Coffer collection gets: no sync through
Coffer, no history or undo, no mechanical check, no Tidy. A person with two
Macs links the folder on each one. The knowledge layer now has two sorts of
collection, so every write path asks which sort it holds.

Wins because every one of those costs is something the folder's own tools
already provide or the person explicitly left to them, while every benefit is
something only a reference in place can give.

### Option C — Reference in place, but keep the row in the vault so it syncs

As B, but the resource file stays under `vault/resources/knowledge/` and
travels to the person's other Macs.

Pros: linking once covers every machine when the folder happens to sit at the
same path everywhere.

Cons: the row carries an absolute path, which dangles on any machine where the
folder is elsewhere or absent. Every surface then needs a state for "linked on
another machine, missing here", and the guide on that machine either names a
path that does not exist or silently drops the section. This is the reasoning
the channels ADR went through: a synced document holding values true of one
machine needs a gate, extra states and a takeover story, and still cannot make
the value right on the second machine.

Loses because it ships a path to machines where it means nothing, to save one
action on machines where it happens to be right.

### Option D — A symlink inside the knowledge root

Linking creates `vault/knowledge/<name>` as a symlink to the folder, and the
rest of the layer treats it as any collection.

Pros: almost no new code: the catalogue, tree and file routes already walk the
knowledge root.

Cons: the vault is a git repository. Git either commits the symlink itself,
which syncs a dangling link to the other Macs, or, through anything that
follows links, commits the folder's content, which is Option A by accident.
Worse, every mechanism that writes a collection Coffer keeps would write
through the link into the person's own folder: the sweep would move their
loose notes into a `pages/` folder they never made, adopt `.inbox/` files, and
a tidy would reorganise their vault by Coffer's rules. Making each of those
skip symlinked collections is the same branching as Option B, with the
symlink still in the repository.

Loses because it puts the person's folder inside the one directory Coffer
treats as its own to write and commit.

### Option E — A linked folder as a full Coffer collection, with tidy, check and history

As B for storage, but the linked folder gets the rest of the collection
treatment: the mechanical check, the Tidy hand-off, history and undo through a
second git view, and uploads into it.

Pros: one experience on the collection page whatever the sort.

Cons: each of those assumes Coffer's wiki layout and Coffer's rules, which the
folder does not follow; a check would report half an Obsidian vault as orphan
pages without sources. History would need a repository Coffer does not own, or
a shadow one. And it contradicts the scope the person set: maintenance belongs
to the folder and its own tools, and Coffer only shares it.

Loses on the person's decision, and because every part of it would be Coffer
imposing its layout on a folder that has its own.

### Sub-decision — whose rules an agent follows in a linked folder

An agent that reads the guide is taught Coffer's wiki rules: write into
`pages/`, never edit `sources/`, give every page frontmatter with a type and
sources, drop material into `.inbox/`. In a linked folder those rules would be
wrong.

- **Coffer's rules everywhere.** Simple to state, and every collection reads
  the same. But an agent following them would create `pages/` and `sources/`
  inside an Obsidian vault and add frontmatter the person never asked for.
- **No rules: read only.** Safe, but it forbids what the person may want, such
  as an agent adding a note to their vault in the vault's own style.
- **The folder's own rules file (chosen).** The guide names the folder's rules
  file, the first of `AGENTS.md`, `CLAUDE.md` and `README.md` present at its
  root, and tells the agent to follow it before writing anything there. With
  none, the agent writes only the way the folder's existing notes are written.
  The guide says plainly that Coffer's `pages/`, `sources/`, inbox and tidy do
  not apply. These are the files agents already read for a folder's
  conventions, so the person states the rules once, in the folder, for every
  agent and tool.

## Decision

A linked folder is a `knowledge` resource whose config is
`{"folder": "<absolute path>"}`. Its row is filed in the machine-local class,
`~/.coffer/local/resources/knowledge/`, through the kind's storage hook, and is
never committed or synced. The folder is the only copy: Coffer reads it in
place and writes nothing into it. It is shared with every agent through the
`coffer-guide` catalogue, under its own path and with its own rules file,
which is what an agent follows when it writes there.

Rules a later change must respect:

- Nothing Coffer runs writes into a linked folder: no upload, delete,
  description edit, sweep, tidy, undo or restore. A route that would do so
  answers `409 KNOWLEDGE_COLLECTION_LINKED`.
- A linked folder's row never enters the vault, and no vault document refers
  to one by uid.
- Coffer's own home, and any folder holding it (the home directory and the
  disk root), cannot be linked: `400 KNOWLEDGE_FOLDER_REFUSED`. So can a path
  that is not absolute or does not exist.
- Renaming changes the label only; Disconnect removes the row only.
- Coffer's wiki rules do not apply in a linked folder; the guide points the
  agent at the folder's own rules file.

## Consequences

- The knowledge service distinguishes the two sorts at its edges:
  `collection_rows()` (what the sweep and the writers walk) holds only the
  collections Coffer keeps, `owned_collection()` refuses a linked folder for
  every write, tidy, check and history action, and `find_collection()` serves
  reads of either.
- The guide renderer has a linked-folder section, and the guide's manual says
  what a linked folder is and that its own rules govern it.
- The Sync page's areas line says linked knowledge folders are not synced, and
  the docs say what to do on a second Mac: link that Mac's copy of the folder.
- A large vault is shared by linking a subfolder of it; the walk cap of 5000
  Markdown files keeps one huge folder from swamping the catalogue, which then
  shortens itself as for any collection.
- Enforced by: the `knowledge` kind's `storage_row` hook in
  `application/knowledge/kind.py`, `KnowledgeService.owned_collection` and
  `collection_rows` in `application/knowledge/service.py`, the read-only module
  `infrastructure/knowledge/linked.py`, and the acceptance scenarios under the
  two linked-folder requirements of the knowledge spec.
