## Why

A review of the knowledge design on 2026-11-13 found two things Coffer did that an agent does itself. Every collection kept a hidden `.inbox/`: an upload was staged there before being promoted in the same call, and a file dropped there was adopted by the sweep, though nothing told agents to use it since collections own their format. And the `coffer-guide` catalogue listed every file of a collection without a start page: on the maintainer's Mac the skill was 48 KB, 21 KB of it one collection's file list, paid for on every open.

## What Changes

- **BREAKING** A collection has no `.inbox/`. An upload or import is written once, straight into the uploads folder. The sweep adopts nothing: it commits edits on disk, closes idle tidies and re-renders the guide. A file left in a `.inbox/` folder is no longer picked up, and the vault ignores `.inbox` like every hidden knowledge entry.
- The guide's catalogue lists no file by name. A collection with a start page gets its file count; one without gets the count for each top-level folder and is told to search. The 60,000-character budget and the shortened forms are removed.
- The main spec `openspec/specs/knowledge/spec.md` and `data-model.md` were edited directly (requirement "Adopt a file dropped into the inbox" removed, "Promote submitted material at once" renamed "Store an upload the moment it arrives", scenarios removed and renamed), so this change carries no delta.

## Capabilities

### Modified Capabilities

- `knowledge`: no inbox entrance; uploads written in place; the catalogue counts files.
- `vault-storage`, `vault-sync`: the ignore list has no inbox exception.

## Impact

Backend knowledge (submission, sweep, paths, history feed, guide renderer, vault ignore list), the guide skill's text, docs-site (en and zh), ADRs `knowledge-has-no-inbox` and `the-guide-catalogue-counts-files` (new), `knowledge-is-plain-files` and `tidying-knowledge-is-the-agents-job` (partly superseded). No HTTP or CLI contract changes.
