# Quickstart — Knowledge Base Manager

Once 006-knowledge-base ships, here is how a developer uses it end-to-end. Three flows: CLI, desktop, and through an MCP client.

## CLI

```bash
# Create a KB with the default embedding model.
coffer kb create design-notes --description "Internal design docs and ADRs"

# Ingest a few files.
coffer kb ingest design-notes ~/work/notes/architecture.md
coffer kb ingest design-notes ~/work/notes/adr-005.md
coffer kb ingest design-notes ~/papers/raft.pdf

# Ingest a directory (one file at a time).
for f in ~/work/notes/*.md; do
  coffer kb ingest design-notes "$f"
done

# Inspect.
coffer kb list                              # all KBs
coffer kb describe design-notes             # document count + disk usage + config
coffer kb list-docs design-notes            # document rows
coffer kb list-docs design-notes --json     # for piping

# Search.
coffer kb search design-notes "how does our retry policy work?"
coffer kb search design-notes "raft leader election" --top-k 3 --json

# Delete a single document.
coffer kb delete-doc design-notes 8a3f1c2b...     # id from list-docs
# Or by filename (resolves uniquely or fails).
coffer kb delete-doc design-notes --filename architecture.md

# Delete the whole KB.
coffer kb delete-kb design-notes              # confirms first
coffer kb delete-kb design-notes --yes        # non-interactive
```

`--json` is supported on every read command. Output is a single JSON document, suitable for `| jq` / scripting. Stderr carries human-readable progress.

## Desktop

1. Launch Coffer.
2. Sidebar → **Resources** → **Add** → pick **Knowledge Base**.
3. Fill the form (name, description, embedding model — default pre-filled). Submit.
4. The new KB shows in the list. Click into it.
5. Drag files into the upload area, or click **Upload** and pick files.
6. Progress runs; documents appear in the list.
7. Use the **Search** box at the top of the KB detail page to test retrieval.
8. Document actions live on each row (delete, copy id, view extracted text).
9. Delete the entire KB via the kebab menu on the detail header.

## Through an MCP client (Claude Code, Cursor, ...)

Once Coffer is configured as your client's MCP server, three new tools appear:

- `coffer__list_knowledge_bases` — what KBs are available, with description and document count.
- `coffer__search_knowledge_base(kb, query, top_k=5)` — ranked passages with `text`, `document_id`, `filename`, `score`, `position`.
- `coffer__get_document(kb, document_id)` — the document's extracted full text + metadata.

Example conversation flow:

> **User**: "How does our service handle backoff?"
>
> **Agent** (tool call): `coffer__search_knowledge_base("design-notes", "service backoff strategy")`
>
> **Agent** (after seeing passages): "Per `design-notes/architecture.md`, services use exponential backoff with full jitter, capped at 30 s. See passages 1 & 3 below."

No additional MCP server install is required — these are built into Coffer's own MCP gateway endpoint.

## First-time model download

The default embedding model `BAAI/bge-small-en-v1.5` is downloaded from HuggingFace Hub on first use (~130 MB), cached under `~/.cache/huggingface/` per the standard HF cache location. Subsequent KBs that use the same model reuse the cache.

If you want to pre-warm the model (e.g., during installer setup), run:

```bash
coffer kb warmup
```

This downloads the default model without ingesting anything.

## Where files live

```
~/.coffer/
├── coffer.db                  # SQLite — control plane (resources, kb_documents, audit, ...)
└── kb/
    └── design-notes/
        ├── raw/
        │   ├── 8a3f1c2b....md
        │   ├── 4e7d2901....md
        │   └── a91bcd2e....pdf
        └── index/
            └── ...             # LlamaIndex persistent index
```

Backing up a KB = copying its directory plus the SQLite rows. The `coffer daemon backup` command (already shipped) snapshots the SQLite database; the `kb/` directory should be included in your filesystem backup strategy.

## Limits (default)

- Per-document size: 25 MB.
- Per-KB documents: ~500 (soft; nothing enforces a hard cap, but search latency grows past that).
- Supported file types out of the box: `.md`, `.markdown`, `.txt`, `.rst`, `.pdf`, common source-code text extensions (`.py`, `.js`, `.ts`, `.go`, `.java`, `.rs`, `.c`, `.h`, `.cpp`, `.hpp`, `.sh`, `.yaml`, `.yml`, `.json`).
- Other text-like files: convert to text yourself and ingest.
