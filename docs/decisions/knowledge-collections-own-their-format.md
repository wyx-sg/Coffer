# Knowledge Collections Own Their Format; Coffer Checks Only Links

**Status**: Accepted
**Date**: 2026-11-11
**Deciders**: Yuxing Wu
**Related**: [Knowledge Is a Directory of Markdown Files, Not an Index](knowledge-is-plain-files.md); [Tidying Knowledge Is the Agent's Job, One Hand-Off Recorded as One Change](tidying-knowledge-is-the-agents-job.md); [Knowledge Files Stay Where Their Writer Put Them, and Every Link Is Checked](knowledge-files-stay-where-their-writer-put-them.md); [A Linked Knowledge Folder Is Shared in Place, Read-Only to Coffer, and Recorded Machine-Local](linked-knowledge-folders-are-read-only-and-machine-local.md); [Knowledge Sources Keep Their Images; Originals Stay on This Mac](knowledge-sources-keep-their-images-and-originals-stay-on-this-mac.md); [Coffer Ships Its Own Manual as a Skill Resource](coffer-ships-its-own-skill.md); research notes [knowledge curation](../research/knowledge-curation.md) and [knowledge structures](../research/knowledge-structures.md); spec knowledge "Let each collection declare its own rules", "Check every link in a collection", "Start a collection from a template", "Teach writing and tidying in the guide"; OpenSpec change `let-collections-own-their-format`

## Context

Knowledge is plain Markdown under `~/.coffer/vault/knowledge/<collection>/`,
read by agents with their own file tools at paths the `coffer-guide` skill
hands them ([Knowledge Is a Directory of Markdown Files](knowledge-is-plain-files.md)).
Until this decision Coffer also fixed **how a collection is written**: every
collection was a wiki compiled from kept sources (Karpathy's "LLM Wiki"
pattern), with `pages/` and `sources/` apart, five built-in page types, a
required frontmatter (`title`, `type`, `description`, `sources`, `verified`),
and eleven findings Coffer computed on every read — waiting, superseded and
missing sources, incomplete, unsourced, orphan and stale pages, duplicate
names, and dead, ambiguous and outside links. The README held a schema block
(`verify_after_days`, `types_without_sources`) and the guide taught the format
as Coffer's own.

Using it on real collections showed the format belonged to the collection, not
to Coffer:

- **Two collections already had their own.** The developer's `shopee-account`
  and `shopee-platform` (47 + 59 pages, 54 + 99 sources) each kept a
  `schema.md` written for agents, a `sources/catalog.yaml`, a `research/`
  folder, page types of their own (`comparison`), and both `verify_after_days`
  and `review_after_days`. Coffer's guide and the collection's schema were two
  sets of instructions an agent had to reconcile.
- **Coffer could not enforce it anyway.** Agents write with their own file
  tools; a "required" key was only ever a finding after the fact. The rules
  lived in Coffer's code, so a collection could not change them.
- **A linked folder already worked the other way.** An Obsidian vault linked
  into Coffer is read by its own `AGENTS.md`, `CLAUDE.md` or `README.md`
  ([linked folders](linked-knowledge-folders-are-read-only-and-machine-local.md)),
  so Coffer carried two models of a collection.
- **A hidden hard limit.** The path guard accepted only a narrow character set
  in file names, so a file an agent named `Login (v2).md` could not be opened
  in the web UI.
- **The project's lean rule.** What the agent can do itself, Coffer does not do
  (principles; decision of 2026-11-06). Judging whether a page is complete,
  current or well-sourced is judgement, and the agent does it by the
  collection's rules.

How comparable tools split the work (surveyed 2026-11-11):

| Tool | Who sets the format | What the tool itself does |
| --- | --- | --- |
| Obsidian | The vault: no required frontmatter; property types in the vault's own `.obsidian/types.json` | Stores files, resolves links (shows unresolved ones), backlinks, version history (Sync). Format checks only through the community Linter plugin, opted into |
| Logseq | Each graph's `logseq/config.edn`; `pages/` and `journals/` a convention | Parses links and properties; validates nothing |
| Dendron | Optional `*.schema.yml` in the vault, for completion and templates; a mismatch is a hint, never a block | Resolves hierarchy and links |
| Foam | No schema; optional templates in `.foam/templates/` | Shows dead links (placeholders) and the graph |
| Karpathy's LLM Wiki | The schema lives in the agent's instruction file (`CLAUDE.md` / `AGENTS.md`), co-written by the person and the LLM | A pattern, not a tool |
| LLM-wiki implementations (nashsu/llm_wiki, claude-obsidian, llmwiki) | Each repository's own `schema.md`; claude-obsidian requires only `title` | Deterministic lint: dead and ambiguous links, orphans, missing frontmatter — reported, never fixed |
| markdownlint, Vale, ESLint (by analogy) | The rule engine is the tool's; which rules run is the repository's config file | Runs only the rules the repository names |

Three things are common: the tool stores, links and versions; the format lives
in the vault's own files; checks are opt-in — except dead links, which nearly
every tool reports because they depend on no format.

## Options Considered

### Option A — One format for every collection, checks always on

Coffer defines the full format (page types, required keys, sources, rechecks),
every collection follows it, and every check is on and cannot be turned off.
This is the previous design tightened one step.

- **Pros.** Every collection looks the same, so an agent moving between them
  learns nothing new; the checks always mean something; the UI can do more by
  type (Contents cards, a To do list).
- **Cons.** Coffer cannot stop a write: "enforced" can only mean reported
  loudly. Which format? The two existing collections already differ, so one
  bends to the other or the shared format absorbs both sets of keys. A linked
  folder cannot follow it. And it runs against the lean rule this whole change
  answers.

### Option B — Keep the LLM wiki as Coffer's format (the previous design)

`pages/` and `sources/` apart, five page types, required keys, eleven computed
findings, the README as schema with an interval, a guide that teaches the wiki.

- **Pros.** Already built. The pattern does make knowledge compound (sources
  integrated into subjects), traceable (pages cite sources) and linked.
- **Cons.** Everything in Context: two sets of instructions for a collection
  with its own schema, rules a collection cannot change because they are code,
  a second model beside linked folders, and judgement Coffer computes on the
  agent's behalf. The pattern's value survives as a template (Option E); it
  does not need to be Coffer's rule.

### Option C — Remove every rule and every check

No page/source split, no findings, no format; the README holds a heading and a
description; the guide says only "follow the collection's own rules".

- **Pros.** The leanest.
- **Cons.** It also drops the one check that depends on no format and that
  nearly every comparable tool keeps: a link that names nothing. A new empty
  collection gets no guidance at all.

### Option D — Keep the engine, every check opt-in per collection

The eleven checks stay in Coffer, all off by default; a collection turns on the
ones it wants, with their parameters, in its README.

- **Pros.** Nothing a collection relies on is lost; ESLint-style.
- **Cons.** Coffer still owns the meaning of `type`, `sources`, `verified` and
  `superseded_by`, so a collection that opts in still writes Coffer's format;
  dead links would be off for a new collection unless it remembered to turn
  them on; and the rule engine, its UI and its configuration stay to be
  maintained for checks an agent can run by reading the collection's rules.
  Finding a collection's rules would still be a second mechanism beside the
  linked folder's.

### Option E — Collections own their format; Coffer reads four declarations and checks links (chosen)

A collection is a folder plus its own rules file, kept or linked alike. Its
README declares, all optional, what Coffer needs to know:

- its **description** — the README's first paragraph, as before;
- `rules` — the file agents follow, relative to the collection (it may point
  into another collection); without one, the first of `AGENTS.md`, `CLAUDE.md`
  and `README.md` at its root, the linked folder's order;
- `entry` — the page an agent starts reading at;
- `uploads` — the folder an upload lands in, `sources/` by default; an
  upload with pictures is a folder of its own there.

Coffer checks only links — dead, ambiguous and out of the knowledge root —
because those depend on no format. Files in the uploads folder are not checked,
since imported material keeps its exporter's text (a Confluence macro's `[[`).
The catalogue gives each collection's rules file and entry page; with an entry
page it gives a file count, without one it lists files by folder with their
titles. A new collection starts from a template copied in once — `llm-wiki`
(the previous wiki as an `AGENTS.md` and an `index.md`) by default, or `blank`
— after which the files are the collection's own.

- **Pros.** One model for kept and linked collections. No second set of
  instructions: the guide says "read the collection's rules file; it wins".
  Coffer keeps only what an agent cannot do as well: storage, history, sync,
  conversion, one link check. A collection changes its rules by editing a file.
  The wiki's value stays available as a template. The catalogue no longer
  duplicates a collection's own `index.md`.
- **Cons.** A collection with poor rules gets no help from Coffer beyond broken
  links. The web UI loses what depended on types and sources (the Contents
  cards, the To do list, the Waiting and Needs rechecking marks). Collections
  made from the previous design keep `type`, `sources` and `verified` keys
  Coffer no longer reads; their own rules must say what to do with them.

#### Sub-choices within Option E

- **Templates: copied, not referenced.** A template that points at Coffer's
  copy of the rules would let an upgrade change a collection's rules under it;
  a copied file is the collection's own. Sharing one collection's rules with
  another is not a template either: `rules: ../shared/rules.md` does it by
  hand, and an agent asked to can copy a file. A "reuse another collection's
  rules" option in the dialog was considered and left out as one more control
  for something a path already expresses.
- **Uploads folder declared; an upload with pictures is one folder.** Coffer
  has to write uploads somewhere; letting the collection say where costs one
  key. An upload's pictures are part of the upload, so the source and its
  pictures share a folder, `sources/deck/deck.md` beside
  `sources/deck/image-1.png`, and the source links them by bare name. An
  upload with no pictures stays a single `sources/<slug>.md`. Three layouts
  were weighed:

  | Layout | Seen in | For | Against |
  |---|---|---|---|
  | `assets/<folder>/` at the collection root | Logseq, Dendron | Uploads folder holds only Markdown | Coffer writes into two folders; a link depends on how deep the uploads folder is; moving a source strands its pictures |
  | `<uploads>/assets/<folder>/` | Obsidian's "subfolder under current folder" | One folder written into; short links | Source and pictures still apart, so a move or delete leaves pictures behind |
  | `<uploads>/<slug>/` holding both (chosen) | Hugo page bundles, Notion's Markdown export | One upload is one folder: moved, renamed or deleted whole, links stay `image-1.png` | One more level in the tree for uploads with pictures |

  The source is named after its folder (`deck-2/deck-2.md`, not
  `deck-2/deck.md`), so two imports of the same page do not share a slug.
  Collections made before were migrated once by a script run on the owner's
  Mac (root `assets/` folders merged into each upload's folder, links
  rewritten, the sidecar files an older Confluence exporter left there —
  `manifest.yaml`, `original.storage.xml`, `original.export.json` — removed);
  Coffer keeps no code for the old layout.
- **File names.** The guard now refuses only `/`, `\`, control characters,
  dot-only and hidden segments, so any name an agent's own tools can write is
  readable.
- **An ambiguous `[[slug]]` prefers the linking file's own folder.** Two
  folders may each hold a `design.md`; a reader in one means its neighbour.

## Decision

A knowledge collection's format is its own. Coffer gives no folder, page type
or frontmatter key a meaning beyond the uploads folder it writes into, requires no key of any file, and reads only what the README declares:
its description, `rules`, `entry` and `uploads`. A linked folder is read by the
same declarations. Coffer reports broken links and nothing else; the rest of a
tidy is the collection's rules, carried out by the agent. A new collection is
copied from the `llm-wiki` template or the `blank` one.

Rules a future change must respect:

- Do not add a check that depends on a collection's format. A check worth
  having for every collection depends on no key, folder or type.
- Do not teach a format in the guide. The guide names each collection's rules
  file and says it wins.
- A template is copied once and never read again by Coffer.

## Consequences

- `infrastructure/knowledge/collection_settings.py` reads the declarations;
  `link_graph.py` resolves links and reports the three link findings;
  `application/knowledge/templates.py` and `skill_assets/templates/` hold the
  templates. The previous `wiki.py`, `wiki_findings.py` and `wiki_rules.py`
  are gone, with the page/source kinds, waiting and stale marks and the wire
  fields that carried them.
- The `coffer-guide` knowledge sections, the tidy hand-off and the catalogue
  are written in terms of a collection's rules file and entry page.
- The web UI shows a collection's Markdown file count, its rules file and start
  page, its Broken links and its Change log; its tree shows folders by their
  own names.
- Existing collections keep working unchanged: their files are not touched,
  their old keys stay as written, and they are read by `AGENTS.md`/`CLAUDE.md`/
  `README.md` until their README names a `rules` file. The developer's two
  collections each add `rules: schema.md` and `entry: index.md`.
