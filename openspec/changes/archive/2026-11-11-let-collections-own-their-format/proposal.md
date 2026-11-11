## Why

Coffer fixed one format for every knowledge collection: a wiki with `pages/` and `sources/`, five page types, required frontmatter (`title`, `type`, `description`, `sources`, `verified`), eleven computed findings and a README schema block. Real collections already had their own schemas (their own page types, a source catalogue, two review intervals), so agents had two sets of instructions to reconcile, the rules lived in Coffer's code where a collection could not change them, and a linked folder was already read by its own `AGENTS.md`. Coffer could not enforce the format anyway, and judging completeness and staleness is the agent's work under the lean principle.

## What Changes

- A collection's format is its own. Its README frontmatter may declare `rules` (the file agents follow; else the first of `AGENTS.md`, `CLAUDE.md`, `README.md`), `entry` (the start page) and `uploads` (where uploads land, `sources/` by default). A linked folder is read the same way.
- Coffer checks only links: dead, ambiguous and outside. Files in the uploads folder are not checked. An ambiguous `[[slug]]` prefers the linking file's own folder.
- New collections start from a template copied in once: `llm-wiki` (default; `AGENTS.md` + `index.md`) or `blank`. `POST /knowledge/collections` and `coffer knowledge create` take `template`.
- File names may hold any character but `/`, `\`, control characters and a leading dot.
- The guide teaches no format: it names each collection's rules file and start page, and the tidy steps defer to the rules file.
- **BREAKING** Removed: page/source kinds, waiting and stale marks, the eight format findings, `verify_after_days`/`types_without_sources`, the wire fields `page_count`, `source_count`, `waiting_source_count` and the per-file kind, type, sources, verified and cited fields; the web UI's To do and Contents sections. Added: `note_count`, `rules_file`, `entry_file`, `uploads_dir`; the Broken links section and the Rules/Start line.
- The main spec `openspec/specs/knowledge/spec.md` and `data-model.md` were edited directly, so this change carries no delta.

## Capabilities

### Modified Capabilities

- `knowledge`: collections own their format; Coffer reads four declarations, checks only links, and offers starter templates.

## Impact

Backend knowledge infrastructure and application layers, HTTP schemas and CLI, generated contracts, the coffer-guide skill and tidy hand-off, the frontend Knowledge page, docs-site (en and zh), ADR `docs/decisions/knowledge-collections-own-their-format.md` replacing two earlier knowledge ADRs. Existing collections keep working: no file is moved or rewritten.
