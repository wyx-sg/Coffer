# 功能规范：Knowledge Base（重新设计）

> English: [spec.md](./spec.md)

**Feature Branch**: `feature/kb-memory-redesign`
**Created**: 2026-06-09
**Status**: Accepted (redesign — in development)
**Input**: 对 `knowledge_base` 资源 kind 的彻底重新设计。一个 Knowledge Base 是共享**知识基底（knowledge substrate）**的一张「面」：用户上传**任意格式**的文件，Coffer 清洗并归一化为**磁盘上的 Markdown**（真相源），再以三种检索模式（`grep`、`keyword`、`vector`）提供回检索。SQLite 仅是可重建的索引。agent 通过 Coffer 的 MCP 网关读取 KB；KB **由用户策展、对 agent 只读**。完整设计依据见 [ADR-012](../../docs/decisions/ADR-012-files-as-truth-sqlite-retrieval.md),架构见 [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md)。

## 用户场景与测试

### User Story 1 —— 用任意格式的文件建一个 KB（优先级 P1）

某开发者手里有设计笔记、ADR、内部 wiki、论文 PDF、一个表格、若干 HTML 页面。他不管格式，把它们一股脑丢进 Coffer。Coffer 把每个文件转换为干净的 Markdown，保留原件作为溯源，并对结果建索引，让 agent 可以从中检索。

**为什么是这个优先级**：这是本规范的核心。没有它就没有知识库。

**独立可测**：从全新安装开始，创建 KB `design-notes`，上传一个 `.md`、一个 `.pdf`、一个 `.docx`、一个 `.csv`；观察每个文件都在 `~/.coffer/knowledge/design-notes/docs/` 下变成一个 Markdown 文件，原件落在 `raw/`，并在统一的 `documents` 表里产生一行。

**代表性场景**：create a knowledge base；ingest converts any format to markdown；list documents in a knowledge base；delete a single document；delete a knowledge base cleans up files and index。

---

### User Story 2 —— 三种模式检索（优先级 P1）

同一份语料用三种方式检索：`grep`（对 Markdown 文件做精确/正则匹配，零索引）、`keyword`（SQLite FTS5 + BM25）、`vector`（sqlite-vec 配合已配置的 embedding provider）。KB 声明一个默认模式；调用方可覆盖它。请求 `vector` 但未配置 embedding provider 时，回退到 keyword 并标注 —— 绝不阻断。

**为什么是这个优先级**：检索就是产品。三种模式覆盖了从离线零配置到语义检索的全谱。

**独立可测**：在已填充的 KB 上跑一次 keyword 检索和一次 grep 查询（两者都无需 embedding 配置即可工作）；配置 embedding provider，跑一次 vector 检索；移除配置，再次请求 vector，观察响应里被标注为 keyword 回退。

**代表性场景**：keyword search returns ranked passages；grep returns file/line matches；vector search returns ranked passages；vector falls back to keyword when embedding unconfigured。

---

### User Story 3 —— agent 通过 MCP 网关只读检索（优先级 P1）

开发者的编码 agent 连到 Coffer 的 MCP 端点，拿到内置的只读 KB 工具：列出 KB、检索、grep、读取完整文档。agent 永远不写 KB。

**为什么是这个优先级**：agent 侧检索正是让 KB 在编码过程中有用的关键。

**独立可测**：在已填充的 KB 上，MCP 客户端能看到 `coffer__list_knowledge_bases`、`coffer__search_knowledge`、`coffer__grep_knowledge`、`coffer__read_document`；调用 `coffer__search_knowledge` 返回排序后的 passage；不存在 KB 的写工具。

**代表性场景**：built-in KB tools appear in client tool list；agent searches a knowledge base；agent greps a knowledge base；agent reads a document。

---

### User Story 4 —— 策展语料：编辑、重建索引、重新 embedding（优先级 P2）

用户直接编辑 Markdown 修掉一处转换瑕疵，然后重建索引。他重新上传更新的源文件以重新转换。他改动 chunk 参数或 embedding 模型，Coffer 重新索引 / 重新 embedding 整个语料。一旦某文档被手工编辑（`source_mode = edited`），就**禁止**从原始 raw 重新转换，以免覆盖编辑。

**为什么是这个优先级**：KB 是随时间策展的；一次性 ingest 不够。但它不是展示核心价值所必需。

**独立可测**：通过 API 编辑某文档的 Markdown，重建索引，确认检索反映了编辑；尝试重新转换该文档，观察被阻止；改动 KB 的 chunk size，确认语料被重新切块并重新索引。

**代表性场景**：edit a document and reindex；re-conversion blocked once edited；changing chunk params re-indexes；changing embedding model re-embeds。

---

### User Story 5 —— 在桌面与 CLI 管理，并观测（优先级 P2）

用户在桌面 UI 的 `Resources` 下、以及通过 `coffer kb …` 子命令管理 KB，并查看每个 KB 的指标（文档数、chunk 数、磁盘占用、已建索引的模式）。

**为什么是这个优先级**：非 CLI 用户和脚本化都需要它；但不阻塞核心流。

**独立可测**：在 UI 里创建一个 KB，拖入文件，检索；在终端 ingest 一个目录、grep、以 JSON 读取指标。

**代表性场景**：KB metrics report counts and disk usage；（UI / CLI 流程延后到 e2e —— 见末尾说明）。

---

### 边界情况

- **不支持的格式**：某文件类型没有对应转换器时，以 `IngestRejected("unsupported_type")` 拒绝；不持久化任何东西。
- **转换库缺失**：某格式的转换引擎未安装时，该格式的 ingest 返回 `EngineUnavailable` 并指明缺失的依赖；daemon 不挂，其他格式照常 ingest。
- **转换为空**：转换后得到空白 / 仅空白字符的 Markdown 时，以 `IngestRejected("empty")` 拒绝。
- **文件过大**：超过 `max_document_bytes`（默认 25 MB）的文件在 API 边界、任何转换运行之前被拒绝。
- **重复上传**：`source_sha256` 已存在的重新上传被拒绝，除非调用方传 `replace=true`。
- **请求 vector 但未配置 embedding**：检索回退到 keyword，并在响应里标注 `fallback="keyword"`；绝不报错。
- **编辑后重新转换**：对 `source_mode == edited` 的文档请求重新转换会被拒绝；重新上传新源文件会把 `source_mode` 重置为 `converted`。
- **对未变内容重建索引**：对 Markdown 的 `content_sha256` 未变的文档重建索引是 no-op。
- **并发检索**：对同一个 KB 的多次检索各自独立运行；没有 per-KB 锁拖慢读延迟。

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

### Scenario: keyword search returns ranked passages

- **Given** documents are indexed,
- **When** the user searches with `mode="keyword"` (or the KB default),
- **Then** they receive passages ranked by `bm25()`, each carrying its source doc id, title, snippet, and score.

### Scenario: grep returns file/line matches

- **Given** documents are on disk,
- **When** the user greps the KB with a pattern,
- **Then** Coffer runs ripgrep over `docs/` (bounded by max-matches and a timeout) and returns `{path, line_number, line}` hits with no index involved.

### Scenario: vector search returns ranked passages

- **Given** the KB has an embedding provider configured and documents embedded,
- **When** the user searches with `mode="vector"`,
- **Then** Coffer embeds the query, runs a sqlite-vec KNN, and returns top-k passages with similarity scores.

### Scenario: vector falls back to keyword when embedding unconfigured

- **Given** the KB has no embedding provider configured,
- **When** the user searches with `mode="vector"`,
- **Then** Coffer runs a keyword search instead and the response is flagged `fallback="keyword"`; no error is raised.

### Scenario: edit a document and reindex

- **Given** a converted document exists,
- **When** the user edits its Markdown body and triggers reindex,
- **Then** `source_mode` becomes `edited`, the single re-index routine deletes old chunks/FTS5/vec rows and re-chunks (re-embedding if vector is enabled), and subsequent search reflects the edit.

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
- **Then** `coffer__list_knowledge_bases`, `coffer__search_knowledge`, `coffer__grep_knowledge`, and `coffer__read_document` are present; no KB write tool exists.

### Scenario: agent searches a knowledge base

- **Given** a KB with indexed documents,
- **When** the client calls `coffer__search_knowledge(kb, query, top_k?, mode?)`,
- **Then** Coffer returns ranked passages structured for LLM consumption (passage + source doc id + score).

### Scenario: agent greps a knowledge base

- **Given** a KB with documents on disk,
- **When** the client calls `coffer__grep_knowledge(kb, pattern)`,
- **Then** Coffer returns file/line matches.

### Scenario: agent reads a document

- **Given** a document exists in a KB,
- **When** the client calls `coffer__read_document(kb, doc_id)`,
- **Then** Coffer returns the document's Markdown body and frontmatter, or a clear error if the id is unknown.

### Scenario: KB metrics report counts and disk usage

- **Given** a KB has documents,
- **When** the user opens its detail view (UI or `coffer kb describe`),
- **Then** they see document count, chunk count, the indexed retrieval modes, and the on-disk byte size of `knowledge/<name>/`.

> **延后到未来的测试工作**（frontend Playwright + 全 CLI e2e）：通过桌面 app 创建 / 上传 / 检索 / 删除 KB；CLI 覆盖每一个桌面操作；CLI 检索 / grep 返回机器可读 JSON。此处列出仅为完整性；`make verify-acceptance` 不对其门禁。

## Requirements

### Functional Requirements

**Resource lifecycle**

- **FR-001**: System MUST support the resource kind `knowledge_base` on the shared knowledge substrate; users MUST create, list, view, update (description + retrieval config), enable, disable, and delete KBs through the kind-agnostic Resource framework.
- **FR-002**: System MUST validate each KB's config (enabled retrieval modes, chunk size/overlap, embedding provider/model/base_url/credential_ref) against a Pydantic schema by `kind`, reject duplicate names, and persist nothing on failure.
- **FR-003**: System MUST store each KB under `~/.coffer/knowledge/<name>/` with normalized Markdown at `docs/<doc-id>.md` (source of truth) and the original at `raw/<doc-id>.<ext>` (provenance). There are NO per-corpus `index/`/`chroma/` directories — all indexing lives in `coffer.db`.

**Ingestion & conversion**

- **FR-004**: Users MUST be able to upload a file of any supported format; the system MUST detect format, convert to Markdown via a pluggable `MarkdownConverter` port, clean the output, prepend YAML frontmatter, write `docs/`+`raw/`, and index it.
- **FR-005**: Conversion MUST dispatch through a per-format converter registry confined to `infrastructure/`: Markdown/text/source files pass through unchanged, `csv` has a dedicated converter, and everything else (pdf / docx / pptx / xlsx / html / epub / odt / rtf / …) goes through the default MarkItDown engine. A higher-fidelity engine for a format is a new converter in the registry, not a substrate change.
- **FR-006**: System MUST reject files over `max_document_bytes` (default 25 MB, configurable), files of unsupported type, and files whose conversion yields empty Markdown.
- **FR-007**: System MUST compute `source_sha256` of the original and reject re-upload of an existing source unless `replace=true`.

**Storage as source of truth**

- **FR-008**: Markdown files MUST be the sole source of truth; SQLite (`documents`, `chunks`, FTS5, sqlite-vec) is a derived, rebuildable index. A reindex routine MUST be able to reconstruct all SQLite state from the files.
- **FR-009**: System MUST use one unified `documents` table shared with the `memory` kind, discriminated by `kind` and a per-face JSON `metadata` column. There is no `kb_documents` table.

**Retrieval**

- **FR-010**: Users MUST be able to search a KB and receive ranked passages (passage text + source doc id + title + score) via the requested or default mode. Default `top_k` is 5; callers MAY set `top_k` in 1–20.
- **FR-011**: System MUST support three retrieval modes: `grep` (ripgrep over `docs/`, bounded by max-matches + timeout, no index), `keyword` (FTS5 `MATCH` ordered by `bm25()`), and `vector` (sqlite-vec KNN over embeddings). Default enabled modes are `keyword`+`grep`; `vector` is opt-in. Grep responses carry a `truncated` flag that is true when matches beyond `max_matches` exist OR the server-side timeout cut the scan short (a timed-out grep returns no hits with `truncated=true`, and the `rg` process is killed).
- **FR-011a**: An EXPLICIT `mode=grep` on the search endpoint — or any explicit mode not in the KB's `enabled_modes` — MUST be rejected with `400 SEARCH_MODE_INVALID` (grep is served by its own endpoint, never silently rewritten). `vector` is the one exception: it always reaches the retrieval facade so the keyword fallback is FLAGGED per FR-012. An implicit search (no `mode`) on a KB whose `default_mode` is `grep` serves `keyword` (grep is not a passage mode).
- **FR-012**: When `vector` is requested but no embedding provider is configured, the system MUST fall back to `keyword` and flag the fallback in the response — it MUST NOT error or block.

**Embedding configuration**

- **FR-013**: The embedding provider MUST be user-configurable per KB via the nested `embedding` config object (DevPilot-style OpenAI-compatible: `provider`, `model`, `base_url`, `credential_ref`, `dimensions`), with an optional in-process `local` provider (fastembed). Credentials MUST be referenced via the keychain, never stored in plaintext.
- **FR-014**: Chunk parameters and the embedding model MUST be mutable; changing chunk params re-chunks+re-indexes and changing the embedding model re-embeds the corpus. There is NO immutability lock on these fields.

**Curation & consistency**

- **FR-015**: Each document MUST carry a `source_mode` of `converted` (Markdown derived from raw, re-convertible) or `edited` (hand-edited; re-conversion blocked). Document ids are content-addressed (the first 16 hex chars of the source's sha256), so re-uploading the **identical** source with `replace=true` resets `source_mode` to `converted`; uploading a different source creates a new document and the edited one remains `edited`. Users MUST be able to edit a document's Markdown, re-upload its source, delete it, and reindex.
- **FR-016**: All write paths (re-upload, edit, reindex scan) MUST funnel through one idempotent re-index routine: if `content_sha256` is unchanged it is a no-op; if changed it deletes old chunks/FTS5/vec rows, re-chunks, re-embeds (if vector enabled), updates the `documents` row, and audits `KB_DOCUMENT_UPDATED`. The KB is **agent-read-only**; agents MUST NOT write KB documents.

**Agent integration via MCP**

- **FR-017**: Coffer's MCP gateway MUST expose read-only built-in tools `coffer__list_knowledge_bases`, `coffer__search_knowledge`, `coffer__grep_knowledge`, and `coffer__read_document` to every connected client, namespaced under the reserved `coffer__` prefix.
- **FR-018**: Built-in KB tool invocations MUST be recorded in `mcp_invocations` exactly as upstream calls (tool name, who/when/duration/outcome — no arguments or returned content).

**Surfaces**

- **FR-019**: Users MUST be able to perform every KB operation through (a) a REST API under `/api/v1/knowledge_bases/`, (b) `coffer kb …` subcommands, and (c) a desktop UI under the existing `Resources` navigation.

### Key Entities

- **Knowledge Base**（kind 为 `knowledge_base` 的 resource）：config = 启用的检索模式、chunk size/overlap、embedding provider/model/base_url/credential_ref、max document bytes、description。
- **Document**（统一 `documents` 行，`kind="knowledge_base"`）：doc id、KB resource 名、磁盘 path、title、description、`content_sha256`、`source_mode`、per-face `metadata`（`original_filename`、`original_format`、`source_sha256`、`converted_at`、`conversion_engine`）、时间戳。
- **Chunk**（`chunks` 行）：在文档内的 position。chunk 文本在常规 FTS5 索引（`documents_fts`）内部存一份，不再重复存进基础 SQLite 表；它始终可由 Markdown 文件重建，文件仍是真相源。
- **Passage**（检索结果，不持久化）：passage 文本、源 doc id、title、score、position。
- **Grep hit**（检索结果，不持久化）：path、行号、行内容。

## Success Criteria

### Measurable Outcomes

- **SC-001**: From a fresh install, a user creates a KB and ingests their first non-Markdown file (e.g. a PDF) within 60 seconds by following the quickstart alone.
- **SC-002**: With a 50-document KB (≤ 50 MB), keyword search latency for a typical query is ≤ 200 ms and grep ≤ 500 ms wall-clock at the REST surface on a developer laptop.
- **SC-003**: Deleting a KB removes 100% of its on-disk footprint and 100% of its SQLite rows; verified by a test that walks `~/.coffer/knowledge/` and queries `documents`/`chunks` before and after.
- **SC-004**: An agent connected through the MCP gateway can list KBs, search, grep, and read a document — all via read-only built-in tools — in one MCP session, with no separate MCP server installed.
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

- **共享基底**：`documents`/`chunks`/FTS5/sqlite-vec 以及转换器端口与 spec 007（memory）共享。本规范拥有 KB 面（任意格式→Markdown、三模式读、agent 只读）；007 拥有 memory 面。两份规范里对基底的描述要保持同步；架构在宪法与重新设计 ADR 里，此处不复述。
- **embedding 默认值**：vector 是可选项；零配置默认是 `keyword`+`grep`（离线、语言无关）。双语语料推荐本地 `bge-m3` 或云 provider（英文小模型 embedding 中文效果差）。
- **延后项**：检索时的 reranking / HyDE / multi-query / LLM 综合；agent 编辑 KB 文档；默认图像 OCR；默认开启的文件系统 watcher。
