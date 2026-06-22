# 功能规范：Knowledge Base（重新设计）

> English: [spec.md](./spec.md)

**Feature Branch**: `feature/kb-memory-redesign`
**Created**: 2026-06-09
**Status**: Accepted (redesign — in development)
**Input**: 对 `knowledge_base` 资源 kind 的彻底重新设计。一个 Knowledge Base 是共享**知识基底（knowledge substrate）**的一张「面」：用户上传**任意格式**的文件，Coffer 清洗并归一化为**磁盘上的 Markdown**（真相源），再以三种检索模式（`grep`、`keyword`、`vector`）提供回检索。SQLite 仅是可重建的索引。文档**由人与 agent 共管**（[ADR-028](../../docs/decisions/ADR-028-knowledge-base-documents-co-managed.md)）：双方都通过 Coffer 的 MCP 网关读 _和_ 写，每次写入都被审计（F01）。基底依据见 [ADR-012](../../docs/decisions/ADR-012-files-as-truth-sqlite-retrieval.md),架构见 [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md)。

## 用户场景与测试

### User Story 1 —— 用任意格式的文件建一个 KB（优先级 P1）

某开发者手里有设计笔记、ADR、内部 wiki、论文 PDF、一个表格、若干 HTML 页面。他不管格式，把它们一股脑丢进 Coffer。Coffer 把每个文件转换为干净的 Markdown，保留原件作为溯源，并对结果建索引，让 agent 可以从中检索。

**为什么是这个优先级**：这是本规范的核心。没有它就没有知识库。

**独立可测**：从全新安装开始，创建 KB `design-notes`，上传一个 `.md`、一个 `.pdf`、一个 `.docx`、一个 `.csv`；观察每个文件都在 `~/.coffer/knowledge/design-notes/docs/` 下变成一个 Markdown 文件，原件落在 `raw/`，并在统一的 `documents` 表里产生一行。

**代表性场景**：create a knowledge base；ingest converts any format to markdown；list documents in a knowledge base；delete a single document；delete a knowledge base cleans up files and index。

---

### User Story 2 —— 三种模式检索（优先级 P1）

同一份语料在底层用多种方式检索：`grep`（对 Markdown 文件做精确/正则匹配，零索引）、`keyword`（SQLite FTS5 + BM25）、`vector`（sqlite-vec 配合已配置的 embedding provider），以及 `hybrid`（对 keyword + vector 做 reciprocal rank fusion，使精确/CJK/标识符命中与释义命中相互增强）。这些是**引擎内部细节**：外部调用方**不**选择模式——一次检索自动解析 KB 的默认策略（启用 vector 时为 `hybrid`，否则为 `keyword`）。`grep` 是一个独立的工具/端点（仅供 agent；已从人用 web 面板移除）。请求时若未配置 embedding provider，在内部回退到 keyword —— 绝不阻断，也无查询期标志（降级通过 `documents_degraded` 指标体现）。

**为什么是这个优先级**：检索就是产品。内部模式覆盖了从离线零配置到语义检索的全谱，而外部界面保持「一次查询 → 一个答案」。

**独立可测**：在已填充的 KB 上跑一次检索（无模式）和一次 grep 查询（两者都无需 embedding 配置即可工作）；配置 embedding provider，在启用 vector 的 KB 上再检索一次；移除配置，再检索一次，观察结果仍返回且无报错（降级通过 `documents_degraded` 体现，而非逐查询标志）。

**代表性场景**：keyword search returns ranked passages；grep returns file/line matches；vector search returns ranked passages；vector falls back to keyword when embedding unconfigured；hybrid search fuses keyword and vector via RRF。

---

### User Story 3 —— agent 通过 MCP 网关读*和*写（优先级 P1）

开发者的编码 agent 连到 Coffer 的 MCP 端点，拿到内置的 KB 工具：读工具（列出 KB、检索、grep、读取完整文档）_与_ 写工具（新增文档、编辑文档、删除文档）。文档由人与 agent 共管：agent 可以与人类一起贡献与策展。每次 agent 写入都以 agent 为 actor 被审计（F01），走人类写入所用的同一套幂等 re-index 例程。

**为什么是这个优先级**：agent 侧检索正是让 KB 在编码过程中有用的关键；agent 侧策展让它成为活的、共管的知识库而非静态库（ADR-028）。

**独立可测**：在已填充的 KB 上，MCP 客户端能看到 `coffer__list_knowledge_bases`、`coffer__search_knowledge`、`coffer__grep_knowledge`、`coffer__read_document`、`coffer__add_document`、`coffer__edit_document`、`coffer__delete_document`；调用 `coffer__add_document` 创建一个可检索的文档。

**代表性场景**：built-in KB tools appear in client tool list；agent searches a knowledge base；agent greps a knowledge base；agent reads a document；agent adds a document via MCP；agent edits a document via MCP；agent deletes a document via MCP。

---

### User Story 4 —— 策展语料：编辑、重建索引、重新 embedding（优先级 P2）

用户在自己的外部编辑器中打开文档的 Markdown（或通过编辑 API）修掉一处转换瑕疵，改动随后被拾取。他以同名重新上传某文件的更新版本，Coffer 就地更新**同一文档**（稳定 ULID id——不产生重复）。他改动 chunk 参数或 embedding 模型，Coffer 重新索引 / 重新 embedding 整个语料。全局唯一的 embedding 模型在「设置 → 向量模型」中通过添加 / 编辑弹窗配置（只能有一个模型，弹窗内含拉取模型与测试连接）；由于更换模型会重新 embedding 所有库，UI 会先弹确认，而启用开关则放在分块默认值旁边。Coffer UI 以**只读**方式渲染 Markdown——它从不提供应用内文本编辑器——而是提供在外部编辑器中打开文档（或其所在文件夹）、在文件管理器 / 访达中显示等操作（Web 上经 daemon,桌面上为原生）。一旦某文档被编辑（`source_mode = edited`），就**禁止**从原始 raw 重新转换，以免覆盖编辑。

**为什么是这个优先级**：KB 是随时间策展的；一次性 ingest 不够。但它不是展示核心价值所必需。

**独立可测**：通过编辑 API（或在外部编辑器中编辑磁盘上的文件）编辑某文档的 Markdown，确认下一次读取 / 检索经由读取时惰性重建索引（lazy reindex-on-read）反映了编辑；以 `replace=true` 重新上传同一文件的变更版本，观察**同一** doc id 被就地更新；改动 KB 的 chunk size，确认语料被重新切块并重新索引。

**代表性场景**：edit a document and reindex；external edit picked up by reindex-on-read；re-conversion blocked once edited；re-upload of an updated file updates the document in place；re-upload of an identical file is a no-op；changing chunk params re-indexes；changing embedding model re-embeds。

---

### User Story 5 —— 在桌面与 CLI 管理，并观测（优先级 P2）

用户在桌面 UI 的 `Resources` 下、以及通过 `coffer kb …` 子命令管理 KB，并查看每个 KB 的指标（文档数、chunk 数、磁盘占用、已建索引的模式，以及因 embedding 服务暂不可用而向量嵌入待重试的文档数）。

**为什么是这个优先级**：非 CLI 用户和脚本化都需要它；但不阻塞核心流。

**独立可测**：在 UI 里创建一个 KB，拖入文件，检索；在终端 ingest 一个目录、grep、以 JSON 读取指标。

**代表性场景**：KB metrics report counts and disk usage；degraded embed surfaces documents_degraded and retries without re-chunking；（UI / CLI 流程延后到 e2e —— 见末尾说明）。

---

### 边界情况

- **不支持的格式**：某文件类型没有对应转换器时，以 `IngestRejected("unsupported_type")` 拒绝；不持久化任何东西。
- **转换库缺失**：某格式的转换引擎未安装时，该格式的 ingest 返回 `EngineUnavailable` 并指明缺失的依赖；daemon 不挂，其他格式照常 ingest。
- **转换为空**：转换后得到空白 / 仅空白字符的 Markdown 时，以 `IngestRejected("empty")` 拒绝。若是 **PDF** 转换为空，则以更具体的 `IngestRejected("scanned_pdf")`（同为 415 状态）拒绝，以便 UI 呈现可操作的「看起来是扫描件 / 纯图片——请运行 OCR」消息，而非通用消息。
- **文件过大**：超过 `max_document_bytes`（默认 25 MB）的文件在 API 边界、任何转换运行之前被拒绝。
- **重新上传，字节完全相同**：字节未变（其 `source_sha256` 与该文件名下已存文档相同）的重新上传是幂等 no-op——返回既有文档，不重写也不重新审计。
- **重新上传，内容变化，同名**：以 KB 中已有的文件名重新上传更新后的文件，就地更新**同一文档**（复用 ULID id，覆盖 `docs/`+`raw/`，只保留最新一份原件，`source_mode` 重置为 `converted`）——但仅当调用方传 `replace=true`；否则以 `duplicate` 拒绝，使覆盖始终显式。
- **vector 不可用、未配置 embedding**：检索在内部回退到 keyword 并正常返回结果、不报错；降级**不**作为查询期标志暴露（通过 `documents_degraded` 指标体现）。
- **编辑后重新转换**：对 `source_mode == edited` 的文档请求重新转换会被拒绝；以 `replace=true` 重新上传变更后的源会就地更新它并重置为 `converted`。
- **对未变内容重建索引**：对 Markdown 的 `content_sha256` 未变的文档重建索引是 no-op。
- **并发检索**：对同一个 KB 的多次检索各自独立运行；没有 per-KB 锁拖慢读延迟。
- **被跟踪的源被移动 / 删除**：当某文档被跟踪的外部 `source_path` 被移动或删除时，`check_sources` 把它报告为 `missing` 且绝不崩溃；`source_path` 是机器本地的，因此（同步到）另一台机器上得到 `missing` 是预期且无害的。

## Acceptance Scenarios

依据 [`agents/sdd.md`](../../agents/sdd.md) 与 [`agents/testing.md`](../../agents/testing.md)，本节每个场景都被至少一个带 `@pytest.mark.acceptance(spec="006-knowledge-base", scenario="…")` 标记的测试引用。

### Scenario: create a knowledge base

- **Given** the daemon is running and no knowledge bases are registered,
- **When** the user creates a KB with a unique name and a retrieval config,
- **Then** the KB is persisted, `~/.coffer/knowledge/<name>/docs/` and `raw/` are created, and listing KBs shows it.

### Scenario: ingest converts any format to markdown

- **Given** a knowledge base exists,
- **When** the user uploads a non-Markdown file (e.g. `.pdf`, `.docx`, `.csv`, `.html`),
- **Then** Coffer converts it to Markdown at `docs/<doc-id>.md` (with YAML frontmatter), preserves the original at `raw/<doc-id>.<ext>`, inserts a `documents` row (`kind="knowledge_base"`, `source_mode="converted"`), chunks it into FTS5, and records audit `KB_DOCUMENT_INGESTED`.

### Scenario: list documents in a knowledge base

- **Given** documents have been ingested,
- **When** the user lists documents,
- **Then** they see one row per document with stable doc ids, titles, original filenames, and timestamps, paginated.

### Scenario: filter documents by title

- **Given** a KB with multiple documents,
- **When** the user lists documents with a title query `q`,
- **Then** only documents whose title contains `q` (case-insensitive) are returned, `total` reflects the filtered count, and results stay paginated by `limit`/`offset`.

### Scenario: keyword search returns ranked passages

- **Given** documents are indexed,
- **When** the user searches (no mode; Coffer uses the KB's resolved default strategy),
- **Then** they receive passages ranked by `bm25()`, each carrying its source doc id, title, snippet, and score.

### Scenario: keyword search matches CJK (Chinese) content

- **Given** a knowledge base with a document whose Markdown body is Chinese (no word-boundary spaces),
- **When** the user runs a keyword search with a CJK query,
- **Then** a multi-character query (e.g. `向量检索`) matches via the FTS5 trigram index, and a short `< 3`-character query (e.g. `向量`) matches via the substring fallback — neither returns empty as the old `unicode61` tokenizer did.

### Scenario: grep returns file/line matches

- **Given** documents are on disk,
- **When** the user greps the KB with a pattern,
- **Then** Coffer runs ripgrep over `docs/` (bounded by max-matches and a timeout) and returns `{path, line_number, line}` hits with no index involved.

### Scenario: vector search returns ranked passages

- **Given** the KB has an embedding provider configured and documents embedded,
- **When** the engine runs a vector search (a vector-enabled KB's resolved default),
- **Then** Coffer embeds the query, runs a sqlite-vec KNN, and returns top-k passages with similarity scores.

### Scenario: vector falls back to keyword when embedding unconfigured

- **Given** the KB has no embedding provider configured,
- **When** the engine resolves to a vector strategy but no embedder is available,
- **Then** Coffer runs a keyword search instead and returns results with no error; the degradation is NOT surfaced as a query-time flag (it is reported via `documents_degraded`).

### Scenario: hybrid search fuses keyword and vector via RRF

- **Given** a KB with vector enabled and documents embedded,
- **When** the engine fuses keyword+vector for a vector-enabled KB (its resolved default),
- **Then** Coffer runs BOTH keyword and vector searches and fuses them by reciprocal rank fusion (`K = 60`, deduped by `(document_id, position)`), so a passage ranked by both lists outranks single-list hits, and returns the fused top-k.

### Scenario: edit a document and reindex

- **Given** a converted document exists,
- **When** the user replaces its Markdown body through the edit API,
- **Then** `source_mode` becomes `edited`, the single re-index routine deletes old chunks/FTS5/vec rows and re-chunks (re-embedding if vector is enabled), and subsequent search reflects the edit.

### Scenario: external edit picked up by reindex-on-read

- **Given** a document whose Markdown file is edited out-of-band in the user's external editor (no API call),
- **When** the user next reads or searches that document,
- **Then** the lazy reindex-on-read scan detects the drifted `content_sha256`, re-indexes through the single idempotent routine, and the read/search reflects the edit — with no filesystem watcher running.

### Scenario: re-conversion blocked once edited

- **Given** a document whose `source_mode == edited`,
- **When** the user requests re-conversion from the raw original,
- **Then** Coffer rejects it with a clear error; re-uploading a new source file resets `source_mode` to `converted`.

### Scenario: changing chunk params re-indexes

- **Given** a KB with indexed documents,
- **When** the user changes `chunk_size` or `chunk_overlap`,
- **Then** Coffer re-chunks and re-indexes the corpus (and re-embeds if vector is enabled) — chunk params are mutable, not locked.

### Scenario: changing embedding model re-embeds

- **Given** a KB with vector indexing enabled and an embedding model set,
- **When** the user changes the embedding model,
- **Then** Coffer re-embeds the corpus into sqlite-vec — the embedding model is mutable, not locked.

### Scenario: delete a single document

- **Given** a KB has documents,
- **When** the user deletes one document by id,
- **Then** the `docs/<doc-id>.md` and `raw/<doc-id>.<ext>` files are removed, its chunks/FTS5/vec rows are deleted, the `documents` row is removed, audit `KB_DOCUMENT_DELETED` is recorded, and search no longer returns it.

### Scenario: delete a knowledge base cleans up files and index

- **Given** a KB has documents and an index,
- **When** the user deletes the KB,
- **Then** all of its `documents`/`chunks`/FTS5/vec rows are removed, `~/.coffer/knowledge/<name>/` is removed, and the Resource row is deleted.

### Scenario: built-in KB tools appear in client tool list

- **Given** an MCP client connects to Coffer's gateway,
- **When** it lists tools,
- **Then** the read tools `coffer__list_knowledge_bases`, `coffer__search_knowledge`, `coffer__grep_knowledge`, `coffer__read_document` AND the write tools `coffer__add_document`, `coffer__edit_document`, `coffer__delete_document` are present (documents are co-managed — ADR-028).

### Scenario: agent searches a knowledge base

- **Given** a KB with indexed documents,
- **When** the client calls `coffer__search_knowledge(kb, query, top_k?)`,
- **Then** Coffer returns ranked passages structured for LLM consumption (passage + source doc id + score).

### Scenario: agent greps a knowledge base

- **Given** a KB with documents on disk,
- **When** the client calls `coffer__grep_knowledge(kb, pattern)`,
- **Then** Coffer returns file/line matches.

### Scenario: agent reads a document

- **Given** a document exists in a KB,
- **When** the client calls `coffer__read_document(kb, doc_id)`,
- **Then** Coffer returns the document's Markdown body and frontmatter, or a clear error if the id is unknown.

### Scenario: agent adds a document via MCP

- **Given** a knowledge base exists,
- **When** the client calls `coffer__add_document(kb, filename, content)` with Markdown content,
- **Then** Coffer ingests it like a human upload (a new ULID-id document, `docs/`+`raw/` written, indexed), records audit `KB_DOCUMENT_INGESTED` with the agent as actor, and the document is searchable.

### Scenario: agent edits a document via MCP

- **Given** a converted document exists,
- **When** the client calls `coffer__edit_document(kb, doc_id, content)`,
- **Then** the body is replaced, `source_mode` becomes `edited`, the corpus is reindexed, and audit `KB_DOCUMENT_UPDATED` is recorded with the agent as actor.

### Scenario: agent deletes a document via MCP

- **Given** a document exists in a KB,
- **When** the client calls `coffer__delete_document(kb, doc_id)`,
- **Then** the document's files and index rows are removed, audit `KB_DOCUMENT_DELETED` is recorded with the agent as actor, and search no longer returns it.

### Scenario: re-upload of an updated file updates the document in place

- **Given** a document ingested from `report.md`,
- **When** the user re-uploads a changed `report.md` with `replace=true`,
- **Then** the SAME document id is updated in place (raw + markdown overwritten, only the latest original kept, `source_mode` reset to `converted`), no second document is created, and audit `KB_DOCUMENT_UPDATED` is recorded.

### Scenario: re-upload of an identical file is a no-op

- **Given** a document ingested from `report.md`,
- **When** the user re-uploads the byte-identical `report.md`,
- **Then** it is an idempotent no-op: the existing document is returned, no second document is created, and no `KB_DOCUMENT_UPDATED` audit is recorded.

### Scenario: KB metrics report counts and disk usage

- **Given** a KB has documents,
- **When** the user opens its detail view (UI or `coffer kb describe`),
- **Then** they see document count, chunk count, the indexed retrieval modes, the count of documents with a pending vector embed (`documents_degraded`), and the on-disk byte size of `knowledge/<name>/`.

### Scenario: degraded embed surfaces documents_degraded and retries without re-chunking

- **Given** a vector-enabled KB whose embedding provider is unavailable when a document is ingested,
- **When** the document is indexed keyword-only and the user later reads the KB (list / search / metrics) with the provider still down, then again once it is restored,
- **Then** the document carries its real `content_sha256` and a persisted `embed_pending` flag, `documents_degraded` reports `1` on the degraded read, and the next reconcile retries **only** the embed (no re-chunk / FTS rewrite — the chunk rows are unchanged), clearing `embed_pending` so `documents_degraded` returns to `0`.

### Scenario: check sources detects changed, unchanged, and missing originals

- **Given** documents ingested from external files (their absolute `source_path` recorded in metadata),
- **When** the user runs `check_sources` after one original is edited on disk, one is left untouched, and one is deleted,
- **Then** the report classifies them as `changed`, `unchanged`, and `missing` respectively (by re-hashing each external file against the stored `source_sha256`), and nothing is re-indexed or audited by the detection itself.

### Scenario: update from source refreshes a changed document in place

- **Given** a converted document whose external `source_path` original has changed on disk,
- **When** the user runs `update_from_source` for that document,
- **Then** Coffer re-ingests it from the tracked file in place (same ULID id, `source_mode` stays `converted`), the new content is searchable and the old content is gone, and `KB_DOCUMENT_UPDATED` is audited.

### Scenario: update from source refuses an edited document

- **Given** a document whose `source_mode == edited`,
- **When** the user runs `update_from_source` for it,
- **Then** Coffer refuses with the re-conversion-blocked error (hand edits are never clobbered), and `check_sources` reports that document as `edited` rather than overwriting it.

### Scenario: auto_update_sources refreshes changed sources on check

- **Given** a KB with `auto_update_sources` enabled and a document whose external original has changed,
- **When** the user runs `check_sources`,
- **Then** the changed document is auto-refreshed in place (reported `updated`) and `KB_DOCUMENT_UPDATED` is audited, while a hand-edited changed document would be skipped (reported `edited`).

### Scenario: test an embedding model

- **Given** an embedding provider, model id, and (where required) credential ref,
- **When** the user tests the embedding model,
- **Then** Coffer requests one embedding and reports success with the returned
  vector dimension, or a humanized failure message, without persisting anything.

> **延后到未来的测试工作**（frontend Playwright + 全 CLI e2e）：通过桌面 app 创建 / 上传 / 检索 / 删除 KB；CLI 覆盖每一个桌面操作；CLI 检索 / grep 返回机器可读 JSON。此处列出仅为完整性；`make verify-acceptance` 不对其门禁。

## Requirements

### Functional Requirements

**Resource lifecycle**

- **FR-001**: System MUST support the resource kind `knowledge_base` on the shared knowledge substrate; users MUST create, list, view, update (description + retrieval config), enable, disable, and delete KBs through the kind-agnostic Resource framework.
- **FR-002**: System MUST validate each KB's config (enabled retrieval modes, chunk size/overlap, embedding provider/model/base_url/credential_ref) against a Pydantic schema by `kind`, reject duplicate names, and persist nothing on failure.
- **FR-003**: System MUST store each KB under `~/.coffer/knowledge/<name>/` with normalized Markdown at `docs/<doc-id>.md` (source of truth) and the original at `raw/<doc-id>.<ext>` (provenance). There are NO per-corpus `index/`/`chroma/` directories — all indexing lives in `coffer.db`.

**Ingestion & conversion**

- **FR-004**: Users MUST be able to upload a file of any supported format; the system MUST detect format, convert to Markdown via a pluggable `MarkdownConverter` port, clean the output, prepend YAML frontmatter, write `docs/`+`raw/`, and index it.
- **FR-005**: Conversion MUST dispatch through a per-format converter registry confined to `infrastructure/`: Markdown/text/source files pass through unchanged, `csv` has a dedicated converter, and everything else (pdf / docx / pptx / xlsx / xls / html / epub / …) goes through the default MarkItDown engine. Formats MarkItDown has no converter for (legacy binary `.doc`/`.ppt`, `.rtf`, `.odt`) are rejected as `unsupported_type`, not advertised. A higher-fidelity engine for a format is a new converter in the registry, not a substrate change.
- **FR-006**: System MUST reject files over `max_document_bytes` (default 25 MB, configurable), files of unsupported type, and files whose conversion yields empty Markdown.
- **FR-007**: Each document MUST be identified by a **stable ULID** minted at first ingest (not a content hash). The system MUST compute `source_sha256` of the original (kept in `metadata` as provenance) and match a re-upload to an existing document by `original_filename` within the store: a **byte-identical** re-upload is an idempotent no-op; a **changed** re-upload of a filename already present updates the **same document in place** (reuse the id) only when `replace=true`, otherwise it is rejected (`duplicate`); a **new** filename is a new document. Re-uploading the SAME file (same name) into two different KBs yields two independent documents (KB documents are not deduplicated across stores).

**Storage as source of truth**

- **FR-008**: Markdown files MUST be the sole source of truth; SQLite (`documents`, `chunks`, FTS5, sqlite-vec) is a derived, rebuildable index. A reindex routine MUST be able to reconstruct all SQLite state from the files.
- **FR-008a**: The KB MUST use **lazy reindex-on-read**: a read or search first detects on-disk drift by `content_sha256` and reconciles the index through the single idempotent re-index routine (FR-016) before serving, so out-of-band edits — including edits made in the user's external editor — are visible immediately with no filesystem watcher running.
- **FR-009**: System MUST use one unified `documents` table shared with the `memory` kind, discriminated by `kind` and a per-face JSON `metadata` column. There is no `kb_documents` table.

**Retrieval**

- **FR-010**: Users MUST be able to search a KB and receive ranked passages (passage text + source doc id + title + score). Retrieval is **automatic**: the caller does NOT choose a mode; Coffer resolves the strategy internally (`hybrid` when `vector` is enabled, else `keyword`). Default `top_k` is 5; callers MAY set `top_k` in 1–20.
- **FR-010a**: Listing documents MUST support an optional **case-insensitive title filter `q`**, applied server-side BEFORE pagination; `total` reflects the filtered count.
- **FR-011**: System MUST support four retrieval modes: `grep` (ripgrep over `docs/`, bounded by max-matches + timeout, no index), `keyword` (FTS5 `MATCH` ordered by `bm25()`), `vector` (sqlite-vec KNN over embeddings), and `hybrid` (reciprocal rank fusion of `keyword` + `vector`, ADR-012). Default enabled modes are `keyword`+`grep`; `vector` is opt-in, and enabling `vector` also enables `hybrid` (which fuses both lists). Grep responses carry a `truncated` flag that is true when matches beyond `max_matches` exist OR the server-side timeout cut the scan short (a timed-out grep returns no hits with `truncated=true`, and the `rg` process is killed). The keyword index uses an FTS5 **trigram** tokenizer so CJK and substring queries match — `unicode61` does not segment CJK text (no word-boundary spaces), so a query like `向量检索` returned nothing; a query with no token of ≥ 3 characters (e.g. a 2-character CJK term) falls back to a bounded substring (LIKE) scan rather than returning empty. These four modes are an **INTERNAL engine detail** — external surfaces (REST / MCP / CLI / UI) do NOT expose mode selection; a search always uses the KB's resolved default strategy, and `grep` is a separate tool/endpoint (removed from the human web panel, still available to agents).
- **FR-011b**: `hybrid` mode MUST run BOTH `keyword` and `vector` searches and fuse them by **reciprocal rank fusion** (RRF): each passage's fused score is `Σ_over_lists 1/(K + rank)` with `K = 60` and `rank` the 0-based position in that list; passages are deduped by chunk identity `(document_id, position)` so a passage in both lists sums both contributions and outranks single-list hits. The top-k by fused score are returned. This delivers the "optional hybrid via reciprocal rank fusion" promised by ADR-012. (Internal — `hybrid` is the resolved default when `vector` is enabled, never an external mode parameter.)
- **FR-012**: When `vector` (or `hybrid`) is the resolved strategy but no embedding provider is configured, the system MUST fall back to `keyword` internally — it MUST NOT error or block. This degradation is NOT surfaced as a query-time response flag anymore (the `fallback` field is removed from the search response); vector-unavailable documents are reported via the `documents_degraded` metric (FR-025).

**Embedding configuration**

- **FR-013**: The embedding provider MUST be user-configurable per KB via the nested `embedding` config object (DevPilot-style OpenAI-compatible: `provider`, `model`, `base_url`, `credential_ref`, `dimensions`), with an optional in-process `local` provider (fastembed). Credentials MUST be referenced into the encrypted credential store, never stored in plaintext.
- **FR-014**: Chunk parameters and the embedding model MUST be mutable; changing chunk params re-chunks+re-indexes and changing the embedding model re-embeds the corpus. There is NO immutability lock on these fields.

**Curation & consistency**

- **FR-015**: Each document MUST carry a `source_mode` of `converted` (Markdown derived from raw, re-convertible) or `edited` (re-conversion blocked). Document ids are stable ULIDs (FR-007), so re-uploading a changed source under the same filename with `replace=true` updates the same document in place and resets `source_mode` to `converted`; uploading a different filename creates a new document and the edited one is untouched. Document edits arrive through the edit API, the agent MCP `edit_document` tool, or by editing the on-disk Markdown in the user's external editor — the Coffer UI does NOT provide an in-app text editor. An edit through the edit API or MCP sets `source_mode=edited`; an external edit is picked up by lazy reindex-on-read (FR-008a). Users and agents MUST be able to edit a document's Markdown, re-upload/replace its source, delete it, and reindex.
- **FR-016**: All write paths (re-upload, edit API, agent MCP write, external edit, reindex scan) MUST funnel through one idempotent re-index routine, invoked lazily on read when the on-disk `content_sha256` has drifted: if `content_sha256` is unchanged it is a no-op; if changed it deletes old chunks/FTS5/vec rows, re-chunks, re-embeds (if vector enabled), updates the `documents` row, and audits `KB_DOCUMENT_UPDATED`. Documents are **co-managed** (ADR-028): both humans and agents may add, edit, and delete documents; every agent write is audited (FR-018) with the agent as actor.

**Agent integration via MCP**

- **FR-017**: Coffer's MCP gateway MUST expose built-in KB tools to every connected client, namespaced under the reserved `coffer__` prefix: the read tools `coffer__list_knowledge_bases`, `coffer__search_knowledge(kb, query, top_k?)` (no `mode?` parameter — retrieval mode is internal), `coffer__grep_knowledge`, `coffer__read_document`, AND the write tools `coffer__add_document` (ingest Markdown content under a filename), `coffer__edit_document` (replace a document's body), and `coffer__delete_document`. The write tools share the same service paths as the REST surface, so they honour the F01 audit (FR-018).
- **FR-018**: Built-in KB tool invocations MUST be recorded in `mcp_invocations` exactly as upstream calls (tool name, who/when/duration/outcome — no arguments or returned content); the document-level effect of a write tool is additionally recorded in the F01 audit trail (`KB_DOCUMENT_INGESTED` / `_UPDATED` / `_DELETED`) with the agent as actor.

**Surfaces**

- **FR-019**: Users MUST be able to perform every KB operation through (a) a REST API under `/api/v1/knowledge_bases/`, (b) `coffer kb …` subcommands, and (c) a desktop UI under the existing `Resources` navigation.
- **FR-020**: The UI document viewer MUST render the Markdown **read-only** — it MUST NOT offer an in-app text editor for document content (humans edit via the external editor or the edit API; agents via MCP). Instead, at both file and containing-folder granularity, the viewer MUST offer affordances to **open in external editor** and **reveal in file manager / Finder**. Open/reveal perform the real OS action on **both** surfaces (honouring the global preferred-editor preference specced in `002-ui-shell`): desktop (Tauri) via the OS opener, the web client via the loopback daemon's filesystem-action endpoints (spec 004 FR-039) — the daemon is always on the user's own machine, so it acts on the user's behalf (ADR-033). There is no copy-path fallback. To support these affordances, read API responses (FR/§Wire) MUST surface the document's absolute on-disk path and its containing folder's absolute path. The viewer MUST render the Markdown body at a comfortable reading **max-width** (centered) so long lines do not stretch edge-to-edge on wide screens. The detail-page document **list** MUST be a single **scrollable** list (the UI fetches one page at the max `limit`) with **no in-UI page-based pager** — the documents **API** stays paginated by `limit`/`offset` (FR-010a) for programmatic/external callers.

**Source-file tracking（源文件跟踪）**

- **FR-021**: A **path-based** ingest (the `coffer kb ingest` CLI, and a future desktop file picker) MUST record the external original's **absolute path** in the document's free-form `metadata` as `source_path` — there is no schema/DB migration; it rides in the existing JSON `metadata`. A web byte-upload and the agent `add_document` MCP tool MUST NOT set or infer `source_path` (an untrusted surface must never populate an arbitrary server path). `source_path` is machine-local: it is meaningful only on the machine that ingested the file.
- **FR-022**: `check_sources` MUST classify each path-tracked document (those with a `source_path`) by re-hashing the external file with sha256 — streamed in chunks so a multi-GB original is never read fully into memory — and comparing to the stored `source_sha256`: `unchanged` (digests match), `changed` (they differ), or `missing` (the file is gone). Detection is **on-demand only** (no filesystem watcher), and detect-only changes nothing and audits nothing.
- **FR-023**: `update_from_source` MUST re-ingest a document from its `source_path` in place — reading the tracked file's bytes and replaying the existing `replace=true` re-ingest path, so the document's stable ULID id is preserved and the corpus is re-chunked/re-indexed (audited via the existing `KB_DOCUMENT_UPDATED`). A document whose `source_mode == edited` MUST be refused (the existing `ReconversionBlocked` error) so hand edits are never clobbered; a vanished or untracked source is reported via the existing `IngestRejected`.
- **FR-024**: A per-KB `auto_update_sources` flag (default **false**) governs `check_sources`: when false, detection only classifies; when true, each `changed` document whose `source_mode != edited` is auto-refreshed in place via `update_from_source` (reported `updated`), while a `changed` hand-edited document is skipped (reported `edited`). Toggling `auto_update_sources` MUST NOT re-chunk or re-embed the corpus (it is not a reindex-triggering field).
- **FR-025**: When an embed degrades because the embedding provider is unavailable (`EngineUnavailable`), the document MUST be indexed keyword-only and its retry state MUST be tracked on a dedicated persisted `embed_pending` flag — decoupled from `content_sha256`, which MUST always carry the real Markdown body hash (so a degraded document is no longer re-chunked + re-FTS'd on every scan, and the files-as-truth sha stays correct). The KB MUST surface the count of such documents as `documents_degraded` in its metrics, computed from the persisted `embed_pending` flag so the count reflects a degrade observed during **any** read (list / get / search / grep), not only an explicit `POST /reindex`. The next reconcile MUST retry **only** the embed for a still-pending document whose body is unchanged — re-chunking it in memory and upserting only the vectors (no FTS / chunk rewrite), clearing `embed_pending` on success.

### Key Entities

- **Knowledge Base**（kind 为 `knowledge_base` 的 resource）：config = 启用的检索模式、chunk size/overlap、embedding provider/model/base_url/credential_ref、max document bytes、description。
- **Document**（统一 `documents` 行，`kind="knowledge_base"`）：doc id（稳定 ULID）、KB resource 名、磁盘 path、title、description、`content_sha256`（始终是真实正文哈希）、`embed_pending`（索引派生的重试标志 —— embed 降级时为真；非文件真相）、`source_mode`、per-face `metadata`（`original_filename`、`original_format`、`source_sha256`、`converted_at`、`conversion_engine`）、时间戳。
- **Chunk**（`chunks` 行）：在文档内的 position。chunk 文本在常规 FTS5 索引（`documents_fts`）内部存一份，不再重复存进基础 SQLite 表；它始终可由 Markdown 文件重建，文件仍是真相源。
- **Passage**（检索结果，不持久化）：passage 文本、源 doc id、title、score、position。
- **Grep hit**（检索结果，不持久化）：path、行号、行内容。

## Success Criteria

### Measurable Outcomes

- **SC-001**: From a fresh install, a user creates a KB and ingests their first non-Markdown file (e.g. a PDF) within 60 seconds by following the quickstart alone.
- **SC-002**: With a 50-document KB (≤ 50 MB), keyword search latency for a typical query is ≤ 200 ms and grep ≤ 500 ms wall-clock at the REST surface on a developer laptop.
- **SC-003**: Deleting a KB removes 100% of its on-disk footprint and 100% of its SQLite rows; verified by a test that walks `~/.coffer/knowledge/` and queries `documents`/`chunks` before and after.
- **SC-004**: An agent connected through the MCP gateway can list KBs, search, grep, read a document, AND add / edit / delete a document — all via built-in tools — in one MCP session, with no separate MCP server installed.
- **SC-005**: `coffer kb reindex <name>` rebuilds all SQLite index state for the KB purely from the Markdown files (drop the rows, reindex, search returns identical results).
- **SC-006**: Every Acceptance Scenario is covered by at least one `acceptance(spec="006-knowledge-base", scenario="…")` test; `make verify-acceptance` reports zero uncovered scenarios.
- **SC-007**: Engine isolation holds: no module under `coffer.application.*` or `coffer.domain.*` imports `markitdown`, `docling`, `sqlite_vec`, or an embedding-provider SDK (importlinter contract).

## Assumptions

- 用户在自己的机器上运行 Coffer；没有多租户或远程访问需求。多机同步在范围之外（宪法层面）。
- keyword + grep 零配置且离线；vector 检索会访问一个已配置的 embedding provider，它**可以**是第三方 API（宪法允许 —— 只有用户**数据**留在本地）。
- 本分支**未发布**；**没有数据迁移**。一个迁移删除 `kb_documents`、删掉旧的 per-corpus 目录、创建统一 schema。
- `ripgrep` 在受支持平台（macOS arm64、Linux）可用；sqlite-vec 在这些平台上作为 SQLite 扩展加载。
- KB **不是** memory 存储：它承载用户策展的文档。`memory` kind（spec 007）是同一基底的可写面；两者共享 `documents` 表但靠 `kind` 区分。

## Notes for reviewers

- **共享基底**：`documents`/`chunks`/FTS5/sqlite-vec 以及转换器端口与 spec 007（memory）共享。本规范拥有 KB 面（任意格式→Markdown、三模式读、人与 agent 共管写入 —— ADR-028）；007 拥有 memory 面。两份规范里对基底的描述要保持同步；架构在宪法与重新设计 ADR 里，此处不复述。
- **embedding 默认值**：vector 是可选项；零配置默认是 `keyword`+`grep`（离线、语言无关）。双语语料推荐本地 `bge-m3` 或云 provider（英文小模型 embedding 中文效果差）。
- **共管（ADR-028）**：文档由人与 agent 共管。本切片交付全局 scope 下的共管核心——稳定 ULID 标识 + 重新上传就地更新（FR-007）、agent MCP 写工具（FR-017）。两块相关内容随后续统一知识 UI 切片一起落地：**逐项目文档 scope**（全局/项目 轴，与该 UI 相互依赖）与**可恢复软删除**（回收站/恢复，需要自己的 UI——目前删除是硬删除但留下 F01 审计痕迹）。
- **延后项**：检索时的 reranking / HyDE / multi-query / LLM 综合；逐项目 KB 文档 scope 与可恢复软删除（见上，下一切片）；应用内 Markdown 编辑器（查看器保持只读 + 外部编辑器入口）；默认图像 OCR；默认开启的文件系统 watcher。
