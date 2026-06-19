# 功能规范：Knowledge Base（重新设计）

> English: [spec.md](./spec.md)

**Feature Branch**: `feature/kb-memory-redesign`
**Created**: 2026-06-09
**Status**: Accepted (redesign — in development)
**Input**: 对 `knowledge_base` 资源 kind 的彻底重新设计。一个 Knowledge Base 是共享**知识基底（knowledge substrate）**的一张「面」：用户上传**任意格式**的文件，Coffer 清洗并归一化为**磁盘上的 Markdown**（真相源），再以三种检索模式（`grep`、`keyword`、`vector`）提供回检索。SQLite 仅是可重建的索引。文档**由人与 agent 共管**（[ADR-028](../../docs/decisions/ADR-028-knowledge-base-documents-co-managed.md)）：双方都通过 Coffer 的 MCP 网关读 _和_ 写，每次写入都被审计（F01），且逐文档的**锁**可让权威文档退出一切变更。文档存在于**全局或逐项目 scope**，删除是一次**可恢复软删除**（回收站 / 恢复）（[ADR-030](../../docs/decisions/ADR-030-per-project-kb-scope-and-soft-delete.md)）——二者共同完成统一的 知识 模型（知识 = 记忆 + 文档 × 全局 / 项目）。基底依据见 [ADR-012](../../docs/decisions/ADR-012-files-as-truth-sqlite-retrieval.md),架构见 [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md)。

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

### User Story 3 —— agent 通过 MCP 网关读*和*写（优先级 P1）

开发者的编码 agent 连到 Coffer 的 MCP 端点，拿到内置的 KB 工具：读工具（列出 KB、检索、grep、读取完整文档）_与_ 写工具（新增文档、编辑文档、删除文档）。文档由人与 agent 共管：agent 可以与人类一起贡献与策展。每次 agent 写入都以 agent 为 actor 被审计（F01），走人类写入所用的同一套幂等 re-index 例程，并在**被锁**的文档上被拒绝。

**为什么是这个优先级**：agent 侧检索正是让 KB 在编码过程中有用的关键；agent 侧策展让它成为活的、共管的知识库而非静态库（ADR-028）。

**独立可测**：在已填充的 KB 上，MCP 客户端能看到 `coffer__list_knowledge_bases`、`coffer__search_knowledge`、`coffer__grep_knowledge`、`coffer__read_document`、`coffer__add_document`、`coffer__edit_document`、`coffer__delete_document`；调用 `coffer__add_document` 创建一个可检索的文档；对被锁文档调用 `coffer__edit_document` 被拒绝。

**代表性场景**：built-in KB tools appear in client tool list；agent searches a knowledge base；agent greps a knowledge base；agent reads a document；agent adds a document via MCP；agent edits a document via MCP；agent deletes a document via MCP；an agent write to a locked document is refused。

---

### User Story 4 —— 策展语料：编辑、重建索引、重新 embedding（优先级 P2）

用户在自己的外部编辑器中打开文档的 Markdown（或通过编辑 API）修掉一处转换瑕疵，改动随后被拾取。他以同名重新上传某文件的更新版本，Coffer 就地更新**同一文档**（稳定 ULID id——不产生重复）。他改动 chunk 参数或 embedding 模型，Coffer 重新索引 / 重新 embedding 整个语料。他**锁定**一份权威文档，使人和 agent 都无法在解锁前对其变更。他**删除**一份文档，它进入可恢复的**回收站**；之后他可以**恢复**它（从保留的原件重新转换）或将其永久**清除**。Coffer UI 以**只读**方式渲染 Markdown——它从不提供应用内文本编辑器——而是提供在外部编辑器中打开文档（或其所在文件夹）、在文件管理器 / 访达中显示、复制其绝对路径、或切换锁状态等操作。一旦某文档被编辑（`source_mode = edited`），就**禁止**从原始 raw 重新转换，以免覆盖编辑。

**为什么是这个优先级**：KB 是随时间策展的；一次性 ingest 不够。但它不是展示核心价值所必需。

**独立可测**：通过编辑 API（或在外部编辑器中编辑磁盘上的文件）编辑某文档的 Markdown，确认下一次读取 / 检索经由读取时惰性重建索引（lazy reindex-on-read）反映了编辑；以 `replace=true` 重新上传同一文件的变更版本，观察**同一** doc id 被就地更新；锁定该文档并观察编辑 / 删除被拒绝；删除一份文档，确认它离开活动列表但出现在回收站中，恢复它，并确认它再次可检索；改动 KB 的 chunk size，确认语料被重新切块并重新索引。

**代表性场景**：edit a document and reindex；external edit picked up by reindex-on-read；re-conversion blocked once edited；re-upload of an updated file updates the document in place；re-upload of an identical file is a no-op；a locked document rejects mutations；lock and unlock a document；restore a trashed document；reindex-on-read does not resurrect a trashed document；purge a trashed document permanently；changing chunk params re-indexes；changing embedding model re-embeds。

---

### User Story 5 —— 在桌面与 CLI 管理，并观测（优先级 P2）

用户在桌面 UI 的 `Resources` 下、以及通过 `coffer kb …` 子命令管理 KB，并查看每个 KB 的指标（文档数、chunk 数、磁盘占用、已建索引的模式）。

**为什么是这个优先级**：非 CLI 用户和脚本化都需要它；但不阻塞核心流。

**独立可测**：在 UI 里创建一个 KB，拖入文件，检索；在终端 ingest 一个目录、grep、以 JSON 读取指标。

**代表性场景**：KB metrics report counts and disk usage；（UI / CLI 流程延后到 e2e —— 见末尾说明）。

---

### User Story 6 —— 把文档划定到某个项目（优先级 P2）

某开发者把一部分文档保持为**全局**（在他所有工作中共享），另一些划定到某个具体**项目**——他正在其中工作的 git 检出。Coffer 从工作目录推导项目（git-root → 一个稳定的项目 ULID，与 memory 面所用的同一标识），并把该项目的文档存放在一个逐项目子树下。统一的 知识 UI 呈现一条 全局 / 项目 轴，并按可读名称列出每个项目；在某个 scope 内，一个项目的 notes（memory）与文档（KB）并排呈现。同一文件名在两个 scope 上传是两份独立文档。

**为什么是这个优先级**：它组织起不断增长的语料，并支撑统一 知识 的项目视图；但它不是展示单 scope 核心所必需。

**独立可测**：在全局 scope ingest `notes.md`，再把另一个 `notes.md` ingest 到某个项目 scope（由一个 git 检出路径解析得到）；观察两份独立文档分别存储在 `knowledge/<kb>/docs/` 与 `knowledge/<kb>/projects/<ulid>/docs/` 下；列出该项目 scope 只看到它的那份文档；对该项目 scope grep 与检索只得到它的匹配。

**代表性场景**：ingest a document into a project scope；global and project documents are isolated；list documents filtered by scope；search is scoped to a project。

---

### 边界情况

- **不支持的格式**：某文件类型没有对应转换器时，以 `IngestRejected("unsupported_type")` 拒绝；不持久化任何东西。
- **转换库缺失**：某格式的转换引擎未安装时，该格式的 ingest 返回 `EngineUnavailable` 并指明缺失的依赖；daemon 不挂，其他格式照常 ingest。
- **转换为空**：转换后得到空白 / 仅空白字符的 Markdown 时，以 `IngestRejected("empty")` 拒绝。
- **文件过大**：超过 `max_document_bytes`（默认 25 MB）的文件在 API 边界、任何转换运行之前被拒绝。
- **重新上传，字节完全相同**：字节未变（其 `source_sha256` 与该文件名下已存文档相同）的重新上传是幂等 no-op——返回既有文档，不重写也不重新审计。
- **重新上传，内容变化，同名**：以 KB 中已有的文件名重新上传更新后的文件，就地更新**同一文档**（复用 ULID id，覆盖 `docs/`+`raw/`，只保留最新一份原件，`source_mode` 重置为 `converted`）——但仅当调用方传 `replace=true`；否则以 `duplicate` 拒绝，使覆盖始终显式。
- **被锁文档**：对被锁文档的任何变更——编辑、重转换、重新上传覆盖、删除——都以 `DOCUMENT_LOCKED`（409）拒绝，对人和 agent 一视同仁，直到解锁。
- **请求 vector 但未配置 embedding**：检索回退到 keyword，并在响应里标注 `fallback="keyword"`；绝不报错。
- **编辑后重新转换**：对 `source_mode == edited` 的文档请求重新转换会被拒绝；以 `replace=true` 重新上传变更后的源会就地更新它并重置为 `converted`。
- **对未变内容重建索引**：对 Markdown 的 `content_sha256` 未变的文档重建索引是 no-op。
- **并发检索**：对同一个 KB 的多次检索各自独立运行；没有 per-KB 锁拖慢读延迟。
- **删除可恢复**：删除一份活动文档会把它移入**回收站**——它的 Markdown（`docs/<id>.md`）与索引行被移除，但原件（`raw/`）与该行（带 `deleted_at`）被保留；它离开一切活动读取。删除一份**已在回收站**的文档则**永久清除**它（移除 `raw/` + 该行）。KB 级删除仍硬移除一切，包括回收站。
- **恢复会丢失正文编辑**：恢复一份回收站中的文档会从保留的原件重新转换（`source_mode` 重置为 `converted`），所以删除前的手改**不会**被找回——没有版本历史。要保护一份策展/编辑过的文档，请**锁定**它（被锁文档根本不能被删除）。
- **reindex 永不复活回收站**：读取时惰性重建索引的扫描既不重建回收站中的文档（它的 `docs/<id>.md` 已没了），也不剪除其墓碑行（剪枝只在活动行上操作）。回收站中的文档保持在回收站，直到被恢复或被清除。
- **没有 git root 的项目 scope**：一次 ingest 若其上报的 `cwd` 解析不到 git root（或它根本没有上报 `cwd`），则回退到**全局** scope；文档存储在 `knowledge/<kb>/docs/` 下。
- **跨 scope 同名文件**：同一文件名分别在全局 scope 与某项目 scope（或跨两个项目）ingest，会产生独立文档——重新上传匹配按 `(kb, project)` 划界。

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
- **When** the user deletes one live document by id,
- **Then** it is soft-deleted: `docs/<doc-id>.md` and its chunks/FTS5/vec rows are removed, the original `raw/<doc-id>.<ext>` and the `documents` row are KEPT with `deleted_at` set, audit `KB_DOCUMENT_DELETED` is recorded, and list/search no longer return it.

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
- **Then** the document is soft-deleted (moved to the recoverable trash), audit `KB_DOCUMENT_DELETED` is recorded with the agent as actor, and search no longer returns it.

### Scenario: an agent write to a locked document is refused

- **Given** a locked document,
- **When** an MCP client calls `coffer__edit_document` or `coffer__delete_document` on it,
- **Then** Coffer refuses with `DOCUMENT_LOCKED` and the document is unchanged.

### Scenario: re-upload of an updated file updates the document in place

- **Given** a document ingested from `report.md`,
- **When** the user re-uploads a changed `report.md` with `replace=true`,
- **Then** the SAME document id is updated in place (raw + markdown overwritten, only the latest original kept, `source_mode` reset to `converted`), no second document is created, and audit `KB_DOCUMENT_UPDATED` is recorded.

### Scenario: re-upload of an identical file is a no-op

- **Given** a document ingested from `report.md`,
- **When** the user re-uploads the byte-identical `report.md`,
- **Then** it is an idempotent no-op: the existing document is returned, no second document is created, and no `KB_DOCUMENT_UPDATED` audit is recorded.

### Scenario: a locked document rejects mutations

- **Given** a document that has been locked,
- **When** any caller attempts to edit, reconvert, re-upload-replace, or delete it,
- **Then** Coffer rejects the mutation with `DOCUMENT_LOCKED` (409) and the document is unchanged.

### Scenario: lock and unlock a document

- **Given** a document exists,
- **When** the user locks it then unlocks it,
- **Then** `locked` flips `true` then `false`, each transition is audited (`KB_DOCUMENT_LOCKED` / `KB_DOCUMENT_UNLOCKED`), and mutations are refused only while locked.

### Scenario: KB metrics report counts and disk usage

- **Given** a KB has documents,
- **When** the user opens its detail view (UI or `coffer kb describe`),
- **Then** they see document count, chunk count, the indexed retrieval modes, and the on-disk byte size of `knowledge/<name>/`.

### Scenario: test an embedding model

- **Given** an embedding provider, model id, and (where required) credential ref,
- **When** the user tests the embedding model,
- **Then** Coffer requests one embedding and reports success with the returned
  vector dimension, or a humanized failure message, without persisting anything.

### Scenario: restore a trashed document

- **Given** a document that has been soft-deleted (in the trash, its original kept in `raw/`),
- **When** the user restores it,
- **Then** Coffer re-converts it from the kept original, regenerates `docs/<doc-id>.md`, re-indexes it, clears `deleted_at` (`source_mode` resets to `converted`), records audit `KB_DOCUMENT_RESTORED`, and the document is searchable again.

### Scenario: reindex-on-read does not resurrect a trashed document

- **Given** a soft-deleted document (no `docs/<doc-id>.md`, `raw/` kept, row tombstoned with `deleted_at`),
- **When** the KB is read or searched (triggering the lazy reindex-on-read scan),
- **Then** the scan neither rebuilds the document nor prunes its tombstone row; the document stays in the trash and out of every live read.

### Scenario: purge a trashed document permanently

- **Given** a document already in the trash,
- **When** the user deletes it again (purge),
- **Then** its `raw/<doc-id>.<ext>` original and its `documents` row are removed for good, audit `KB_DOCUMENT_PURGED` is recorded, and it no longer appears in the trash.

### Scenario: ingest a document into a project scope

- **Given** a knowledge base exists,
- **When** the user uploads a file under a resolved project scope (a project ULID),
- **Then** the document is stored under `knowledge/<kb>/projects/<ulid>/docs/` + `raw/`, its `documents` row carries that `project_id`, and it is searchable within that scope.

### Scenario: global and project documents are isolated

- **Given** the same filename ingested once at global scope and once into a project scope,
- **When** the documents are listed,
- **Then** they are two independent documents with distinct ids, stored under `knowledge/<kb>/docs/` and `knowledge/<kb>/projects/<ulid>/docs/` respectively (re-upload matching is scoped to `(kb, project)`).

### Scenario: list documents filtered by scope

- **Given** a KB with both global and project-scoped documents,
- **When** the user lists documents for a specific scope (global or a project ULID),
- **Then** only that scope's documents are returned.

### Scenario: search is scoped to a project

- **Given** a KB with documents in two different scopes,
- **When** the user searches (keyword/vector) or greps within one project scope,
- **Then** only that scope's passages / file matches are returned.

> **延后到未来的测试工作**（frontend Playwright + 全 CLI e2e）：通过桌面 app 创建 / 上传 / 检索 / 删除 KB；CLI 覆盖每一个桌面操作；CLI 检索 / grep 返回机器可读 JSON。此处列出仅为完整性；`make verify-acceptance` 不对其门禁。

## Requirements

### Functional Requirements

**Resource lifecycle**

- **FR-001**: System MUST support the resource kind `knowledge_base` on the shared knowledge substrate; users MUST create, list, view, update (description + retrieval config), enable, disable, and delete KBs through the kind-agnostic Resource framework.
- **FR-002**: System MUST validate each KB's config (enabled retrieval modes, chunk size/overlap, embedding provider/model/base_url/credential_ref) against a Pydantic schema by `kind`, reject duplicate names, and persist nothing on failure.
- **FR-003**: System MUST store each KB under `~/.coffer/knowledge/<name>/`. **Global** documents keep normalized Markdown at `docs/<doc-id>.md` (source of truth) and the original at `raw/<doc-id>.<ext>` (provenance); **project-scoped** documents live under a per-project subtree at `projects/<project-ulid>/docs/<doc-id>.md` + `projects/<project-ulid>/raw/<doc-id>.<ext>` (FR-022). There are NO per-corpus `index/`/`chroma/` directories — all indexing lives in `coffer.db`.

**Ingestion & conversion**

- **FR-004**: Users MUST be able to upload a file of any supported format; the system MUST detect format, convert to Markdown via a pluggable `MarkdownConverter` port, clean the output, prepend YAML frontmatter, write `docs/`+`raw/`, and index it.
- **FR-005**: Conversion MUST dispatch through a per-format converter registry confined to `infrastructure/`: Markdown/text/source files pass through unchanged, `csv` has a dedicated converter, and everything else (pdf / docx / pptx / xlsx / html / epub / odt / rtf / …) goes through the default MarkItDown engine. A higher-fidelity engine for a format is a new converter in the registry, not a substrate change.
- **FR-006**: System MUST reject files over `max_document_bytes` (default 25 MB, configurable), files of unsupported type, and files whose conversion yields empty Markdown.
- **FR-007**: Each document MUST be identified by a **stable ULID** minted at first ingest (not a content hash). The system MUST compute `source_sha256` of the original (kept in `metadata` as provenance) and match a re-upload to an existing document by `original_filename` within the store's resolved scope `(kb, project_id)`: a **byte-identical** re-upload is an idempotent no-op; a **changed** re-upload of a filename already present updates the **same document in place** (reuse the id) only when `replace=true`, otherwise it is rejected (`duplicate`); a **new** filename is a new document. The same filename across two scopes (global vs a project, or two projects), or into two different KBs, yields independent documents — KB documents are not deduplicated across stores or scopes.

**Storage as source of truth**

- **FR-008**: Markdown files MUST be the sole source of truth; SQLite (`documents`, `chunks`, FTS5, sqlite-vec) is a derived, rebuildable index. A reindex routine MUST be able to reconstruct all SQLite state from the files.
- **FR-008a**: The KB MUST use **lazy reindex-on-read**: a read or search first detects on-disk drift by `content_sha256` and reconciles the index through the single idempotent re-index routine (FR-016) before serving, so out-of-band edits — including edits made in the user's external editor — are visible immediately with no filesystem watcher running.
- **FR-009**: System MUST use one unified `documents` table shared with the `memory` kind, discriminated by `kind` and a per-face JSON `metadata` column. There is no `kb_documents` table.

**Retrieval**

- **FR-010**: Users MUST be able to search a KB and receive ranked passages (passage text + source doc id + title + score) via the requested or default mode. Default `top_k` is 5; callers MAY set `top_k` in 1–20.
- **FR-011**: System MUST support three retrieval modes: `grep` (ripgrep over `docs/`, bounded by max-matches + timeout, no index), `keyword` (FTS5 `MATCH` ordered by `bm25()`), and `vector` (sqlite-vec KNN over embeddings). Default enabled modes are `keyword`+`grep`; `vector` is opt-in. Grep responses carry a `truncated` flag that is true when matches beyond `max_matches` exist OR the server-side timeout cut the scan short (a timed-out grep returns no hits with `truncated=true`, and the `rg` process is killed).
- **FR-011a**: An EXPLICIT `mode=grep` on the search endpoint — or any explicit mode not in the KB's `enabled_modes` — MUST be rejected with `400 SEARCH_MODE_INVALID` (grep is served by its own endpoint, never silently rewritten). `vector` is the one exception: it always reaches the retrieval facade so the keyword fallback is FLAGGED per FR-012. An implicit search (no `mode`) on a KB whose `default_mode` is `grep` serves `keyword` (grep is not a passage mode).
- **FR-012**: When `vector` is requested but no embedding provider is configured, the system MUST fall back to `keyword` and flag the fallback in the response — it MUST NOT error or block.

**Embedding configuration**

- **FR-013**: The embedding provider MUST be user-configurable per KB via the nested `embedding` config object (DevPilot-style OpenAI-compatible: `provider`, `model`, `base_url`, `credential_ref`, `dimensions`), with an optional in-process `local` provider (fastembed). Credentials MUST be referenced into the encrypted credential store, never stored in plaintext.
- **FR-014**: Chunk parameters and the embedding model MUST be mutable; changing chunk params re-chunks+re-indexes and changing the embedding model re-embeds the corpus. There is NO immutability lock on these fields.

**Curation & consistency**

- **FR-015**: Each document MUST carry a `source_mode` of `converted` (Markdown derived from raw, re-convertible) or `edited` (re-conversion blocked). Document ids are stable ULIDs (FR-007), so re-uploading a changed source under the same filename with `replace=true` updates the same document in place and resets `source_mode` to `converted`; uploading a different filename creates a new document and the edited one is untouched. Document edits arrive through the edit API, the agent MCP `edit_document` tool, or by editing the on-disk Markdown in the user's external editor — the Coffer UI does NOT provide an in-app text editor. An edit through the edit API or MCP sets `source_mode=edited`; an external edit is picked up by lazy reindex-on-read (FR-008a). Users and agents MUST be able to edit a document's Markdown, re-upload/replace its source, delete it, and reindex (all subject to the per-document lock, FR-021).
- **FR-016**: All write paths (re-upload, edit API, agent MCP write, external edit, reindex scan) MUST funnel through one idempotent re-index routine, invoked lazily on read when the on-disk `content_sha256` has drifted: if `content_sha256` is unchanged it is a no-op; if changed it deletes old chunks/FTS5/vec rows, re-chunks, re-embeds (if vector enabled), updates the `documents` row, and audits `KB_DOCUMENT_UPDATED`. Documents are **co-managed** (ADR-028): both humans and agents may add, edit, and delete documents; every agent write is audited (FR-018) with the agent as actor and is refused on a locked document (FR-021).

**Agent integration via MCP**

- **FR-017**: Coffer's MCP gateway MUST expose built-in KB tools to every connected client, namespaced under the reserved `coffer__` prefix: the read tools `coffer__list_knowledge_bases`, `coffer__search_knowledge`, `coffer__grep_knowledge`, `coffer__read_document`, AND the write tools `coffer__add_document` (ingest Markdown content under a filename), `coffer__edit_document` (replace a document's body), and `coffer__delete_document`. The write tools share the same service paths as the REST surface, so they honour the per-document lock (FR-021) and the F01 audit (FR-018).
- **FR-018**: Built-in KB tool invocations MUST be recorded in `mcp_invocations` exactly as upstream calls (tool name, who/when/duration/outcome — no arguments or returned content); the document-level effect of a write tool is additionally recorded in the F01 audit trail (`KB_DOCUMENT_INGESTED` / `_UPDATED` / `_DELETED`) with the agent as actor.

**Surfaces**

- **FR-019**: Users MUST be able to perform every KB operation through (a) a REST API under `/api/v1/knowledge_bases/`, (b) `coffer kb …` subcommands (including `coffer kb trash` to list the trash and `coffer kb restore` to recover a document), and (c) a desktop UI. In the UI, KB documents are presented through the unified **知识** navigation — the 全局 / 项目 scope axis with notes (memory) and documents (KB) intermixed (see 007) — rather than a standalone Knowledge Base page; the trash (list / restore / purge) and per-project scope are reachable from that surface.
- **FR-020**: The UI document viewer MUST render the Markdown **read-only** — it MUST NOT offer an in-app text editor for document content (humans edit via the external editor or the edit API; agents via MCP). Instead, at both file and containing-folder granularity, the viewer MUST offer affordances to **open in external editor**, **reveal in file manager / Finder**, and **copy the absolute path**, plus a **lock / unlock toggle** (FR-021) and a `locked` badge. On desktop (Tauri) open/reveal perform the real OS action (open/reveal honouring the global preferred-editor preference specced in `002-ui-shell`); on the web client, where the daemon cannot act on the user's machine, the open/reveal affordance falls back to copy-path. To support these affordances, read API responses (FR/§Wire) MUST surface the document's absolute on-disk path, its containing folder's absolute path, and its `locked` flag.
- **FR-021**: Each document MUST carry a `locked` flag (default `false`). While a document is locked, every mutation — edit (API or MCP), reconvert, re-upload replace, and delete (API or MCP) — MUST be refused with `DOCUMENT_LOCKED` (409) for human and agent callers alike; only locking/unlocking and reads are permitted. The lock is the per-document opt-out from co-management (ADR-028). Lock and unlock transitions MUST be audited (`KB_DOCUMENT_LOCKED` / `KB_DOCUMENT_UNLOCKED`).

**Scope & recoverable delete** ([ADR-030](../../docs/decisions/ADR-030-per-project-kb-scope-and-soft-delete.md))

- **FR-022**: Each document MUST be scoped to either **global** (the `WORKSPACE_GLOBAL` sentinel `project_id`) or a **project** (a stable project ULID derived from a git-root path — the same `project_ulid` the memory face uses), carried in the `documents.project_id` column. Project-scoped documents MUST be stored under `knowledge/<name>/projects/<project-ulid>/{docs,raw}/`; global documents under `knowledge/<name>/{docs,raw}/`. Ingest MUST resolve scope from an explicit `project_id` (REST / UI) or from the caller's reported `cwd` (agent MCP: git-root → ULID), defaulting to **global** when unresolvable. List, read, grep, and keyword / vector search MUST be scoped to a resolved `project_id`; re-upload identity (FR-007) is scoped to `(kb, project_id)`.
- **FR-023**: Deleting a **live** document MUST be a recoverable **soft-delete**: remove `docs/<doc-id>.md` and its index rows (chunks / FTS5 / vec) but KEEP `raw/<doc-id>.<ext>` and the `documents` row with a non-null `deleted_at`; the document leaves every live read (list / get / search / grep / metrics / re-upload match — all filtering `deleted_at IS NULL`) and audits `KB_DOCUMENT_DELETED`. **Restore** MUST re-convert the document from the kept original, regenerate `docs/`, re-index, clear `deleted_at` (resetting `source_mode` to `converted`), and audit `KB_DOCUMENT_RESTORED`. Deleting an **already-trashed** document MUST **purge** it (remove `raw/` + the row, audit `KB_DOCUMENT_PURGED`). A **locked** document (FR-021) cannot be soft-deleted, purged, or restored. The lazy reindex-on-read scan (FR-008a) MUST NOT resurrect a tombstone nor prune its row. (A KB-level delete remains a hard cleanup of all documents, including the trash.)

### Key Entities

- **Knowledge Base**（kind 为 `knowledge_base` 的 resource）：config = 启用的检索模式、chunk size/overlap、embedding provider/model/base_url/credential_ref、max document bytes、description。
- **Document**（统一 `documents` 行，`kind="knowledge_base"`）：doc id（稳定 ULID）、KB resource 名、磁盘 path、title、description、`content_sha256`、`source_mode`、`locked` 标志、`project_id`（全局哨兵或一个项目 ULID —— FR-022）、`deleted_at`（除非在回收站否则为 null —— FR-023）、per-face `metadata`（`original_filename`、`original_format`、`source_sha256`、`converted_at`、`conversion_engine`）、时间戳。
- **Chunk**（`chunks` 行）：在文档内的 position。chunk 文本在常规 FTS5 索引（`documents_fts`）内部存一份，不再重复存进基础 SQLite 表；它始终可由 Markdown 文件重建，文件仍是真相源。
- **Passage**（检索结果，不持久化）：passage 文本、源 doc id、title、score、position。
- **Grep hit**（检索结果，不持久化）：path、行号、行内容。

## Success Criteria

### Measurable Outcomes

- **SC-001**: From a fresh install, a user creates a KB and ingests their first non-Markdown file (e.g. a PDF) within 60 seconds by following the quickstart alone.
- **SC-002**: With a 50-document KB (≤ 50 MB), keyword search latency for a typical query is ≤ 200 ms and grep ≤ 500 ms wall-clock at the REST surface on a developer laptop.
- **SC-003**: Deleting a KB removes 100% of its on-disk footprint and 100% of its SQLite rows; verified by a test that walks `~/.coffer/knowledge/` and queries `documents`/`chunks` before and after.
- **SC-004**: An agent connected through the MCP gateway can list KBs, search, grep, read a document, AND add / edit / delete a document — all via built-in tools — in one MCP session, with no separate MCP server installed; a write to a locked document is refused.
- **SC-005**: `coffer kb reindex <name>` rebuilds all SQLite index state for the KB purely from the Markdown files (drop the rows, reindex, search returns identical results).
- **SC-006**: Every Acceptance Scenario is covered by at least one `acceptance(spec="006-knowledge-base", scenario="…")` test; `make verify-acceptance` reports zero uncovered scenarios.
- **SC-007**: Engine isolation holds: no module under `coffer.application.*` or `coffer.domain.*` imports `markitdown`, `docling`, `sqlite_vec`, or an embedding-provider SDK (importlinter contract).
- **SC-008**: A deleted document is recoverable: after delete → restore, the document is searchable again with its original content; a reindex-on-read performed while the document is in the trash does NOT resurrect it (verified by a test that deletes, reindexes, asserts absence, then restores and asserts presence).
- **SC-009**: Scopes are isolated: a document ingested into one scope (global or a specific project ULID) never appears in another scope's list, search, or grep; the same filename ingested at two scopes is two independent documents.

## Assumptions

- 用户在自己的机器上运行 Coffer；没有多租户或远程访问需求。多机同步在范围之外（宪法层面）。
- keyword + grep 零配置且离线；vector 检索会访问一个已配置的 embedding provider，它**可以**是第三方 API（宪法允许 —— 只有用户**数据**留在本地）。
- 本分支**未发布**；**没有数据迁移**。一个迁移删除 `kb_documents`、删掉旧的 per-corpus 目录、创建统一 schema。
- `ripgrep` 在受支持平台（macOS arm64、Linux）可用；sqlite-vec 在这些平台上作为 SQLite 扩展加载。
- KB **不是** memory 存储：它承载用户策展的文档。`memory` kind（spec 007）是同一基底的可写面；两者共享 `documents` 表但靠 `kind` 区分。

## Notes for reviewers

- **共享基底**：`documents`/`chunks`/FTS5/sqlite-vec 以及转换器端口与 spec 007（memory）共享。本规范拥有 KB 面（任意格式→Markdown、三模式读、人与 agent 共管写入 —— ADR-028）；007 拥有 memory 面。两份规范里对基底的描述要保持同步；架构在宪法与重新设计 ADR 里，此处不复述。
- **embedding 默认值**：vector 是可选项；零配置默认是 `keyword`+`grep`（离线、语言无关）。双语语料推荐本地 `bge-m3` 或云 provider（英文小模型 embedding 中文效果差）。
- **共管（ADR-028 + ADR-030）**：文档由人与 agent 共管。共管**核心**（稳定 ULID 标识 + 重新上传就地更新（FR-007）、agent MCP 写工具（FR-017）、逐文档锁（FR-021））已在 ADR-028 下以全局 scope 交付。本统一知识切片在 [ADR-030](../../docs/decisions/ADR-030-per-project-kb-scope-and-soft-delete.md) 下完成它：**逐项目文档 scope**（全局/项目 轴 —— FR-022）与**可恢复软删除**（回收站 / 恢复 / 清除 —— FR-023），二者都通过统一 知识 UI 呈现（FR-019）。逐项目 scope 复用 memory 面的 `project_ulid`；软删除的 `deleted_at IS NULL` 过滤与 memory 面共享，但对 memory 行是 no-op（memory 从不打墓碑）。
- **延后项**：检索时的 reranking / HyDE / multi-query / LLM 综合；应用内 Markdown 编辑器（查看器保持只读 + 外部编辑器入口 —— FR-020）；默认图像 OCR；默认开启的文件系统 watcher；回收站自动过期（清除是显式的；删除 KB 会清空回收站）。
