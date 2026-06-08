# Quickstart —— Knowledge Base（重新设计）

> English: [quickstart.md](./quickstart.md)

重新设计的 006-knowledge-base 上线后，开发者如何端到端地用它。三条流程：CLI、桌面、以及通过 MCP 客户端。

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

`--json` 在每个读命令上都支持；输出是一个 JSON 文档，适合 `| jq`。stderr 承载人类可读的进度。

### 开启 vector 检索（可选）

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

如果你在未配置 embedding 的 KB 上请求 `--mode vector`，检索会回退到 keyword，响应被标注 `fallback="keyword"` —— 绝不报错。

## 桌面

1. 启动 Coffer。
2. 侧栏 → **Resources** → **Add** → 选 **Knowledge Base**。
3. 填表单：name、description、启用的检索模式（默认 keyword + grep）、chunk 参数，以及 —— 仅当你启用 vector —— 一个 embedding provider/model 与凭据。提交。
4. 点进 KB。把任意格式的文件拖入上传区；每个都变成 Markdown。
5. 用 **Search** 面板；从选择器里挑模式（grep / keyword / vector）。
6. 打开一个文档查看渲染后的 Markdown；就地编辑并 **Reindex** 生效（标记为 `edited`）。
7. 文档操作在每一行上（read、delete、copy id、re-upload source）。
8. 在详情头部的 kebab 菜单删除 KB。

## 通过 MCP 客户端（Claude Code、Codex …）

一旦 Coffer 成为你客户端的 MCP server，四个只读 KB 工具出现（KB 由用户策展 —— 没有写工具）：

- `coffer__list_knowledge_bases` —— 可用 KB 及其 description、文档数、已建索引的模式。
- `coffer__search_knowledge(kb, query, top_k=5, mode?)` —— 排序后的 passage（`text`、`document_id`、`title`、`score`、`position`）；`mode` 默认取 KB 配置。
- `coffer__grep_knowledge(kb, pattern, max_matches?)` —— 对 markdown 的 file/line 匹配。
- `coffer__read_document(kb, doc_id)` —— 文档的完整 Markdown + frontmatter。

示例流程：

> **User**: "How does our service handle backoff?"
>
> **Agent** (tool call): `coffer__search_knowledge("design-notes", "service backoff strategy")`
>
> **Agent**: "Per `design-notes` doc `architecture` (id 8a3f…), services use exponential backoff with full jitter, capped at 30 s — passages 1 & 3 below."

无需安装额外的 MCP server —— 它们内建在 Coffer 网关里。

## 文件落在哪

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

Markdown 文件是**真相源**；SQLite 是可重建索引。`coffer kb reindex <name>` 从 `docs/` 文件重建每一行 SQLite。备份一个 KB = 拷贝它的 `knowledge/<name>/` 目录；索引在 reindex 时再生成。

## 限制（默认）

- 每文档大小：25 MB（per-KB 可配）。
- 每 KB 文档数：约 500（软；超过后检索延迟上升）。
- 支持格式：转换器注册表能处理的一切 —— md / txt / 源码（passthrough），pdf / docx / pptx / xlsx / html / csv / json / yaml / xml（MarkItDown），以及安装了相应引擎时的 epub / odt / rtf（pandoc）与高保真 pdf（Docling）。不支持的类型以 `unsupported_type` 拒绝；已知类型但引擎缺失返回 `ENGINE_UNAVAILABLE` 并指明依赖。
- 检索：keyword + grep 零配置离线工作；vector 可选，需要 embedding provider。
