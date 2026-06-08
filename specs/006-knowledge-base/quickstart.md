# Quickstart — Knowledge Base (redesign)

> 中文版: [quickstart.zh.md](./quickstart.zh.md)

Once the redesigned 006-knowledge-base ships, here is how a developer uses it end-to-end. Three flows: CLI, desktop, and through an MCP client.

## CLI

```bash
# Create a KB. Default retrieval is keyword + grep — zero config, offline, no model download.
coffer kb create design-notes --description "Internal design docs and ADRs"

# Ingest files of ANY format — each is converted to Markdown on disk.
coffer kb ingest design-notes ~/work/notes/architecture.md      # passthrough
coffer kb ingest design-notes ~/papers/raft.pdf                 # MarkItDown → markdown
coffer kb ingest design-notes ~/work/spec.docx                  # MarkItDown → markdown
coffer kb ingest design-notes ~/data/metrics.csv               # → markdown table
coffer kb ingest design-notes ~/page.html                      # → cleaned markdown

# Ingest a directory (one file at a time).
for f in ~/work/notes/*; do coffer kb ingest design-notes "$f"; done

# Inspect.
coffer kb list                              # all KBs
coffer kb describe design-notes             # doc count + chunk count + indexed modes + disk usage
coffer kb list-docs design-notes            # document rows (id, title, source_mode, original_filename)
coffer kb list-docs design-notes --json     # for piping

# Read a document's normalized markdown.
coffer kb read design-notes 8a3f1c2b...

# Retrieve. Default mode = the KB's default_mode (keyword).
coffer kb search design-notes "how does our retry policy work?"
coffer kb search design-notes "raft leader election" --top-k 3 --json
coffer kb search design-notes "exponential backoff" --mode keyword

# grep: exact / regex over the markdown files, no index, no embedding.
coffer kb grep design-notes "TODO|FIXME"
coffer kb grep design-notes "backoff" --max-matches 20 --json

# Curate: edit the markdown directly, then reindex (sets source_mode=edited).
coffer kb edit design-notes 8a3f1c2b...                  # opens $EDITOR on the markdown
coffer kb reindex design-notes                           # rescan files → rebuild index from disk

# Delete a single document, then the whole KB.
coffer kb delete-doc design-notes 8a3f1c2b...
coffer kb delete-kb design-notes --yes
```

`--json` is supported on every read command; output is one JSON document, suitable for `| jq`. Stderr carries human-readable progress.

### Turning on vector search (opt-in)

```bash
# Local, offline embeddings via fastembed (no API key, no server).
coffer kb set-embedding design-notes --provider local --model bge-m3 --enable-vector

# Or a cloud / OpenAI-compatible provider; the credential is a keychain ref, never plaintext.
coffer credential set openai-embed                       # stores the key in the OS keychain
coffer kb set-embedding design-notes \
  --provider openai --model text-embedding-3-small \
  --credential-ref openai-embed --enable-vector

# Changing the embedding model re-embeds the corpus (files are the truth).
coffer kb search design-notes "service backoff strategy" --mode vector
```

If you request `--mode vector` on a KB with no embedding configured, the search falls back to keyword and the response is flagged `fallback="keyword"` — it never errors.

## Desktop

1. Launch Coffer.
2. Sidebar → **Resources** → **Add** → pick **Knowledge Base**.
3. Fill the form: name, description, enabled retrieval modes (keyword + grep by default), chunk params, and — only if you enable vector — an embedding provider/model and credential. Submit.
4. Click into the KB. Drag files of any format into the upload area; each becomes Markdown.
5. Use the **Search** panel; pick a mode (grep / keyword / vector) from the selector.
6. Open a document to view its rendered Markdown; edit it inline and **Reindex** to apply (marks it `edited`).
7. Document actions live on each row (read, delete, copy id, re-upload source).
8. Delete the KB via the kebab menu on the detail header.

## Through an MCP client (Claude Code, Codex, ...)

Once Coffer is your client's MCP server, four read-only KB tools appear (the KB is user-curated — there is no write tool):

- `coffer__list_knowledge_bases` — available KBs with description, document count, and indexed modes.
- `coffer__search_knowledge(kb, query, top_k=5, mode?)` — ranked passages (`text`, `document_id`, `title`, `score`, `position`); `mode` defaults to the KB config.
- `coffer__grep_knowledge(kb, pattern, max_matches?)` — file/line matches over the markdown.
- `coffer__read_document(kb, doc_id)` — the document's full Markdown + frontmatter.

Example flow:

> **User**: "How does our service handle backoff?"
>
> **Agent** (tool call): `coffer__search_knowledge("design-notes", "service backoff strategy")`
>
> **Agent**: "Per `design-notes` doc `architecture` (id 8a3f…), services use exponential backoff with full jitter, capped at 30 s — passages 1 & 3 below."

No additional MCP server install is required — these are built into Coffer's gateway.

## Where files live

```
~/.coffer/
├── coffer.db                       # SQLite — resources / documents / chunks / FTS5 / sqlite-vec / audit
└── knowledge/
    └── design-notes/
        ├── docs/
        │   ├── 8a3f1c2b....md      # normalized markdown = truth (frontmatter + body)
        │   └── a91bcd2e....md
        └── raw/
            ├── 8a3f1c2b....pdf     # original upload (provenance / re-convert)
            └── a91bcd2e....docx
```

Markdown files are the **source of truth**; SQLite is a rebuildable index. `coffer kb reindex <name>` reconstructs every SQLite row from the `docs/` files. Backing up a KB = copying its `knowledge/<name>/` directory; the index regenerates on reindex.

## Limits (default)

- Per-document size: 25 MB (configurable per KB).
- Per-KB documents: ~500 (soft; search latency grows past that).
- Supported formats: anything the converter registry handles — md / txt / source code (passthrough), pdf / docx / pptx / xlsx / html / csv / json / yaml / xml (MarkItDown), plus epub / odt / rtf (pandoc) and high-fidelity pdf (Docling) when those engines are installed. An unsupported type is rejected with `unsupported_type`; a missing engine for a known type returns `ENGINE_UNAVAILABLE` naming the dependency.
- Retrieval: keyword + grep work offline with zero config; vector is opt-in and needs an embedding provider.
