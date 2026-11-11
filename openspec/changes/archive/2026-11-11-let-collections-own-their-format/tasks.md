## 1. Backend

- [x] 1.1 `collection_settings.py`: read `rules`, `entry`, `uploads`; titles from frontmatter, heading or file name
- [x] 1.2 `link_graph.py`, `file_links.py`: resolve links over every Markdown file; report dead, ambiguous and outside links; skip the uploads folder; prefer the linking file's folder
- [x] 1.3 Remove the wiki model (`wiki.py`, `wiki_findings.py`, `wiki_rules.py`), page/source kinds and the format findings
- [x] 1.4 Templates `llm-wiki` and `blank`; `template` on create (REST and CLI)
- [x] 1.5 Widen the path guard's character set
- [x] 1.6 Guide, catalogue and tidy hand-off in terms of each collection's rules file and start page

## 2. Surfaces

- [x] 2.1 Knowledge page: Broken links, Rules/Start line, file count, template choice, tree by folder name; remove To do, Contents and the Waiting/Needs rechecking marks
- [x] 2.2 Regenerate contracts and the CLI reference

## 3. Docs

- [x] 3.1 Spec and data model, ADR (replacing two earlier ones), docs-site guides, architecture, glossary and concepts (en and zh)
