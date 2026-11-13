## Context

See ADR `docs/decisions/knowledge-collections-own-their-format.md` for the options (one enforced format, the previous wiki, no rules at all, an opt-in rule engine, collections own their format) and the survey of Obsidian, Logseq, Dendron, Foam, Karpathy's LLM Wiki and its implementations.

## Decisions

- **Four declarations, all optional.** The README's first paragraph (description), `rules`, `entry`, `uploads`. A declaration that does not resolve is ignored, never refused, so a typo cannot break a read. `rules` may point into another collection (bounded by the knowledge root; a linked folder by itself), which is how collections share rules without a "reuse" option in the dialog.
- **One check.** Broken links depend on no format; everything else (completeness, sources, staleness) is the collection's rules, applied by the agent at a tidy.
- **Templates copied once.** `llm-wiki` carries the previous wiki's rules as an `AGENTS.md` (reviewed and tightened) plus an empty `index.md`; `blank` is the README only. Coffer never reads a template again, so upgrades never change a collection's rules.
- **Uploads folder.** Coffer must write uploads somewhere; the collection may choose where. An upload with pictures is one folder there, the file and its pictures side by side and linked by bare name, so it moves and deletes as a whole (Hugo's page bundles); existing collections are migrated once by a script, and Coffer keeps no code for the old root `assets/`.
- **Migration.** None: existing files are untouched and their old keys become the collection's own. The developer's two collections add `rules: schema.md` and `entry: index.md` by hand.

## Risks

- A collection with poor rules gets no help beyond broken links. Mitigated by the default `llm-wiki` template.
- Collections from before are read by their README until they declare `rules`.
