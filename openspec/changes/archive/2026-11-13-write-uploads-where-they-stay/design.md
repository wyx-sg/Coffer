## Context

The options behind each decision are in the ADRs: `docs/decisions/knowledge-has-no-inbox.md` and `docs/decisions/the-guide-catalogue-counts-files.md`. This file records only how the change is made.

## Decisions

- **Upload.** `infrastructure/knowledge/sources.py` `write_source` writes the source into the uploads folder (in its own folder when it has pictures). `KnowledgeService.submit` calls it inside the one vault transaction and touches one path. `inbox.py` and `application/knowledge/intake.py` are deleted.
- **Hidden paths.** `paths.is_hidden` replaces the inbox name. The change feed and undo drop hidden paths, so the `.inbox/` paths an earlier build committed are never shown or restored. The history's operation word `promote` is kept as the wire value of an upload's commit.
- **Ignore list.** The `!/knowledge/**/.inbox` exception is removed from `.git/info/exclude`.
- **Catalogue.** `guide_render._folder_counts` gives a collection's Markdown files per top-level folder, folders by name and the root last. The three detail levels and `MAX_CATALOGUE_CHARS` are deleted.

## Risks

- A tool that still drops files into `.inbox/` is silently ignored. The only installation's inboxes are empty and the guide has not named the inbox since collections own their format.
- A collection without a start page is now found by search alone. Its rules can name a start page with `entry:`.
