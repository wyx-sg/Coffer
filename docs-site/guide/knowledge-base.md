# Knowledge bases

A **knowledge base** (KB) is a document store your agents can search but never write. You add files in any format; Coffer normalizes each to Markdown on disk — the source of truth — and serves them back through three retrieval modes. The Markdown files are canonical; the SQLite index is rebuildable with `coffer kb reindex`.

## Create and fill a KB

```bash
coffer kb create handbook                            # default modes: keyword + grep
coffer kb ingest handbook ./onboarding.pdf           # any format → Markdown
coffer kb ingest handbook ./notes.docx
coffer kb list-docs handbook                         # what's inside
```

- Ingestion converts pdf, docx, pptx, xlsx, html, and more to Markdown (25 MB default cap). Re-ingesting the same source needs `--replace`.
- Originals are kept under the KB's `raw/` folder; a document you hand-edit will not be re-converted from its raw original.

## Search

```bash
coffer kb search handbook "how do I reset my password"    # ranked passages (keyword)
coffer kb grep handbook "TODO"                            # exact / regex over the Markdown
coffer kb search handbook "vacation policy" --mode vector # semantic (needs embeddings)
```

- **grep** is exact/regex with no index; **keyword** (the default) is FTS5 BM25 ranking; **vector** is semantic nearest-neighbour and is opt-in.
- Enable vector with `coffer kb set-embedding handbook --provider … --model …`. A vector search with no embedding configured falls back to keyword rather than erroring.

## For your agents

Every connected MCP client automatically gets read-only tools — `coffer__list_knowledge_bases`, `coffer__search_knowledge`, `coffer__grep_knowledge`, and `coffer__read_document`. There is no write tool: agents read your knowledge, they don't change it.

In the app, knowledge bases live under **Resources** — create a KB, drag files in, and search; the detail view shows document and chunk counts, disk usage, and which retrieval modes are indexed.

[Memory →](/guide/memory)
