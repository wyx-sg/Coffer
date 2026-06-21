# Research —— 006 Knowledge Base（重新设计）

> English: [research.md](./research.md)

本次重新设计中各项技术选择的背景与理由。每节末尾给出 **决策**；并记录未选方案让后续读者知道走过哪些岔路。本次重新设计**取代**原始 006 的选择（LlamaIndex + sentence-transformers），并由一个新 ADR 承载，该 ADR 取代 ADR-010 与 ADR-011。

> **后续修订 —— [ADR-028](../../docs/decisions/ADR-028-knowledge-base-documents-co-managed.md)（2026-06-19）：** 下文记录的两项决策随后被反转。**doc id** 现在是稳定 ULID（不再是 §3 的 source-sha256 前缀），且 KB **由人与 agent 共管** —— agent 可经 MCP 写文档，而非只读（§4）—— 由 F01 审计守护。下文保留为原始记录；两者不一致处以 ADR-028 为准。

## 1. 检索栈：文件 + SQLite，无 RAG 框架

**问题**：Coffer 存储、索引、检索知识的骨干是什么？

**候选**：

| Approach                                     | Strengths                                               | Risks for Coffer                                                         |
| -------------------------------------------- | ------------------------------------------------------- | ------------------------------------------------------------------------ |
| **LlamaIndex**（原 006）                     | 业界主流、loader 多                                     | 重；重构两次；persist 目录是文件之外的第二真相源；抽象外泄；拉一大堆依赖 |
| Haystack 2.x                                 | pipeline 模型更干净                                     | 社区更小；仍是框架                                                       |
| **Markdown 文件 + SQLite FTS5 + sqlite-vec** | 无框架；文件即真相；一个 `coffer.db`；离线 keyword/grep | 我们自己写 chunker + retriever 胶水（适量 LOC），完全可控                |
| Chroma / Qdrant local                        | 流行向量库                                              | 又一个进程/库；hybrid 非内建；又一个真相源                               |

**决策**：**以 Markdown 文件为真相源 + SQLite（FTS5 做 keyword、sqlite-vec 做 vector），无 RAG 框架。** 驱动了核心重新设计原则 —— _文件是真相，SQLite 是可重建索引_。好处：

1. 消除原始的双真相源毛病（文本同时存在 persist 目录和 SQLite）。`coffer kb reindex` 从文件重建每一行 SQLite。
2. keyword + grep 零配置、零模型下载、离线可用。
3. 一切都在一个 `coffer.db` 里，紧挨 Coffer 其余控制面 —— 一次备份、一次删除。
4. 转换器与向量引擎藏在 `infrastructure/` 的端口后；未来切换只改一个文件。

LlamaIndex、mem0、chroma、手写的 keyword 词频扫描、dispatcher 全部移除。

## 2. 三种检索模式

**问题**：用户 / agent 如何从 KB 检索？

**决策**：三种模式、一个引擎、按面调优的工具：

- **`grep`** —— 对 `docs/*.md` 跑 `ripgrep`，由 `max_matches` 和超时限制。无索引、无 embedding、正则/精确。返回 `{path, line_number, line}`。文件一存在就立即可用。
- **`keyword`** —— FTS5 `MATCH(query) ORDER BY bm25() LIMIT top_k`。零配置、离线、支持 CJK（**trigram** 分词器，能匹配中文与任意子串；`unicode61` 不切分 CJK，中文查询会返空）。无 ≥3 字 token 的查询（如 2 字中文词）回退到有界子串扫描。多词查询采用 **AND 优先**：先跑隐式 AND（每个词都要命中），使包含全部词的 chunk 排在只命中某一个常见词的 chunk 前；仅当 AND 命中数不足 `top_k` 时才放宽为 OR，并把 OR 独有命中（去重、AND 优先）追加在后。**默认**。
- **`vector`** —— embedding query → sqlite-vec KNN top_k。可选；需要已配置的 embedding provider。

KB 声明 `enabled_modes` + `default_mode`；search 调用可覆盖 `mode`。**Hybrid（keyword + vector 的 RRF 融合）**是同引擎后的可选未来增强 —— 列为非阻塞增强，MVP 不内建。

**Vector 回退**：若请求 `vector` 但未配置 embedding provider，引擎跑 `keyword` 并在响应里标注 `fallback="keyword"`。检索绝不因缺 embedding 配置而阻断。

## 3. 转换器库（任意格式 → Markdown）

**问题**：任意上传如何归一化为 Markdown？

**候选**：

| Library                          | Strengths                                                                   | Notes                  |
| -------------------------------- | --------------------------------------------------------------------------- | ---------------------- |
| **MarkItDown**（Microsoft, MIT） | 覆盖广（PDF/docx/pptx/xlsx/html/csv/json/…）、面向 LLM 的 Markdown 输出、轻 | 默认                   |
| Docling（IBM, MIT）              | 高保真 PDF（版式、表格、可选 OCR）                                          | 更重；存在时按格式接入 |
| pandoc                           | epub/odt/rtf 及多种格式                                                     | 外部二进制；可插拔     |
| readability + custom             | 剥 HTML 样板                                                                | 用在 HTML 路径里       |

**决策**：一个 `MarkdownConverter` **端口**（`can_handle(format)` + `convert(bytes) -> (markdown, metadata)`）配按格式的**注册表**，限制在 `infrastructure/knowledge/converters/`。默认引擎 **MarkItDown**；Markdown / 纯文本 / 源码走 passthrough 转换器，csv 走专用转换器。当前不附带 Docling/pandoc 转换器 —— open item(PDF 用 MarkItDown vs Docling)由注册表在*结构层面*解决：某格式要更高保真引擎，就是在 `infrastructure/knowledge/converters/` 下新增一个转换器；切换无需改规范。

转换后 pipeline **清洗**（归一化空白、剥控制字符、合并空行、修标题层级、剥 HTML 样板；空结果拒绝）并预置 **YAML frontmatter** 让存下的 `.md` 自描述。

## 4. Embedding 配置（vector 模式）

**问题**：用哪个 embedding 模型，怎么配置？

**决策**：一个**用户可配置、OpenAI 兼容的 provider 抽象**（DevPilot 风格：一个 `AsyncOpenAI` 客户端 + 可换 `base_url`）。per-KB 的 `EmbeddingConfig`：`provider`、`model`、`base_url`、`credential_ref`（加密存储 ref，绝不明文）、`dimensions`。经同一个 `.embeddings.create` 可达的 provider：OpenAI / OpenRouter / Voyage / Jina / Gemini / Azure / DashScope 及本地 Ollama / LM Studio；外加 in-process **`local`** provider（fastembed）做零服务器离线 embedding。

- **默认检索是 `keyword`+`grep`**（零配置、离线）。vector 可选 —— 用户无需选模型或下载任何东西就能得到可用的 KB。
- **embedding 模型可变。** 改它会重新 embedding 语料（文件即真相，重导便宜）。无不可变锁 —— 修掉了原规范「想换模型就重建 KB」的摩擦。
- 对**双语**内容，推荐本地 `bge-m3`（fastembed）或云 provider；英文小模型 embedding 中文效果差。本地模型的硬 MTEB/CPU 基准是可选的定稿前步骤，非阻塞。

出站 embedding 调用走 Coffer 的 SSRF 防护 HTTP 客户端。vector 模式访问第三方 API 不违反 local-first：只有 query/chunk 文本被 embedding；用户数据留在磁盘（宪法原则 I；见 local-first memory 备注）。

## 5. 切块策略

**问题**：Markdown 在索引前如何切？

**决策**：**边界感知（结构保持）的 Markdown 切块** —— 按标题切（一个 chunk 绝不跨两个段落小节），再把**整块结构块**（散文段落、围栏代码块、表格、列表组）**贪心打包**进 `chunk_size`（默认 512）窗口，相邻 chunk 之间携带 `chunk_overlap`（默认 64）重叠。两参数均为 **per-KB 且可变**：改它们会重新切块 + 重建语料索引（便宜，文件即真相）。这消除了原规范里 chunk 参数创建即冻结的半不可变毛病。

边界感知是一项 **chunk 质量**属性（不是新的 wire 契约——FR-014 已治理可变的字符级参数）：chunk 边界即检索单元，故须尊重结构，而非在 `start + chunk_size` 处盲切。具体：

- **原子块** —— 围栏代码块（```` ``` ```` / `~~~`，含语言标签）或 Markdown 表格（一串管道符分隔的行——表头、分隔行、数据行）**绝不被内部切开**。旧的字符窗口会在围栏/表格中间切断，产生孤立的半截围栏和无表头的表格碎片，embedding 与阅读都很差。
- **贪心块打包** —— 整块依次塞入 chunk，直到下一块会超出 `chunk_size` 才开新 chunk；切点优先落在空行 / 块边界。超大散文段落在最近的**句子**边界（`. ` / `。` / 换行）处切，而非切在词中间；仅对完全没有断句的段落才退而硬切。
- **超大原子块** —— 单个大于 `chunk_size` 的围栏或表格保持**整块**作为自己的（超大）chunk；半截围栏对检索比一个大 chunk 更糟。
- **重叠** —— 相邻 chunk 通过把上一 chunk 的尾部句子/块（约 `chunk_overlap` 字符，对齐到边界）重新纳入来共享上下文；整块打包后，字符级精确重叠必然是近似的。

尺寸仍按**字符**计（确定、无依赖）；token 级尺寸延后（不引入分词器）。语义 / 层次 / 源码感知切块器 MVP 范围外；它们带来与预期语料规模不成比例的模型调用成本，可在同一切块接口后再加。

## 6. 文档存储布局与标识

**决策**：`~/.coffer/knowledge/<kb-name>/docs/<doc-id>.md`（归一化 Markdown = 真相）+ `raw/<doc-id>.<ext>`（原始上传 = 溯源，可重新转换）。**没有** per-corpus 的 `index/` 或 `chroma/` 目录 —— 所有索引都在 `coffer.db`。

`doc-id` = 原件 `source_sha256` 的前 16 个 hex 字符（同一值用于重复上传闸门）。内容寻址、派生而非分配、在预期 KB 规模（≤ 500 文档）下不碰撞。留着 `raw/` 意味着以后能用更好的引擎重新转换某文档。

## 7. 编辑与单一 re-index 例程

**问题**：用户的编辑与重新上传如何保持一致？

**决策**：KB **由用户策展、对 agent 只读**（设计 option A）。两条编辑路径：重新上传新源（重新转换 → 新 Markdown）或直接编辑 Markdown——经编辑 API（REST/CLI）或在用户自己的外部编辑器中打开磁盘文件。Coffer UI 查看器为**只读**；它提供在编辑器中打开 / 显示 / 复制路径等操作，而非应用内文本编辑器。`source_mode` 为 `converted`（Markdown 由 raw 派生；可重新转换）或 `edited`（禁止重新转换以免覆盖；重新上传重置为 `converted`）。一个幂等 re-index 例程服务 ingest、re-upload、edit 与 reindex scan：`content_sha256` 未变 ⇒ no-op；变 ⇒ 删旧 chunks/FTS5/vec、重新切块、重新 embedding（若 vector）、upsert `documents` 行、audit。一致性触发：API 编辑 + 显式 `coffer kb reindex`（重扫增量）+ **读取时惰性重建索引**（读取 / 检索检测到 `content_sha256` 漂移并在服务前先对齐）——无文件系统 watcher，因此外部编辑器的编辑在下次读取时浮现。

## 8. 内置 MCP 工具表面（只读）

**决策**：reserved `coffer__` 前缀下的四个只读工具，由网关提供给每个客户端：

- `coffer__list_knowledge_bases() -> [{name, description, document_count, modes}, ...]`
- `coffer__search_knowledge(kb, query, top_k=5, mode?) -> {mode, fallback?, passages:[{text, document_id, title, score, position}, ...]}`
- `coffer__grep_knowledge(kb, pattern, max_matches?) -> [{path, line_number, line}, ...]`
- `coffer__read_document(kb, doc_id) -> {document_id, title, markdown, metadata}`

不存在 KB 写工具 —— KB 由用户策展。调用记入 `mcp_invocations`（仅 tool 名 + who/when/duration/outcome；无参数或返回内容），与既有隐私立场一致。`coffer__` 前缀保留（名为 `coffer` 的 server 在注册时被拒）；上游工具前缀是 `<server>__`，绝不碰撞。

## 9. 降级 embed：与 sha 闸门解耦 + 暴露计数（KB8）

**问题**：当 embedding provider 不可用时，例程如何让 embed 保持可重试而不破坏 no-op 闸门？降级又如何在读取时变得可见？

**决策**：用一个专用的持久化 **`embed_pending`** 标志，与 `content_sha256`（始终是真实正文哈希）解耦，再配上一个基于持久计数的暴露方式。

- **为什么解耦。** 旧设计用空字符串哨兵覆盖 `content_sha256`，使下一次对账失配而重试 embed。但 `"" == previous_sha` 永不成立，于是**每次**扫描都重新切块降级文档 + 重写其 FTS 行 + 重试 embed —— 一个无关编辑就会重建整个降级语料。空 sha 还破坏了 files-as-truth 推导。把重试状态拆到独立列，让 sha 闸门保持诚实（正文不变 ⇒ 无 churn），同时 embed 仍可重试。
- **为什么走只重试 embed 的路径。** 正文未变但 `embed_pending` 时，chunks + FTS 已经是最新 —— 只缺向量。例程在**内存**里重新切块（位置确定），embed，并调用新的索引方法 `upsert_vectors` 只写 vec 行。不重写 FTS / chunk ⇒ 降级语料的 churn 消失，且向量按位置与已存 chunks 对齐。
- **为什么从持久标志暴露，而非临时扫描计数。** 降级计数原本在 `reindex_scan` 内计算，只由显式 `POST /reindex` 返回；读取时惰性重建（list / get / search / grep）期间的降级被悄悄丢弃（`_reconcile_on_read -> None`）。在 `metrics()` 里查询持久的 `embed_pending`（`count_pending_embeds`），让 `documents_degraded` 在任意读取上都正确，无需把扫描计数穿过每条读路径。
- **边界。** `embed_pending` 只跟踪 embedding **provider** 调用失败（`EngineUnavailable`）。它与 sqlite-vec 扩展是否可用正交：provider 成功但 vec 表不可用属于 `embedded=True`（非 pending），在查询时由 `SearchResponse.fallback` 处理 —— 与既有 `embedded` 标志同构。

## 10. 标题作为 embedding 上下文（KB5）

**问题**：取自文档中部的 chunk 被孤立地 embedding，向量丢失了文档主题 —— 如何恢复主题上下文以提升 vector 召回？

**决策**：仅把文档**标题**（`"{title}\n\n{chunk}"`）前置到**被 EMBEDDING** 的文本 —— 一种标准 RAG 技术。写入 FTS（`documents_fts`）与 chunk 行的仍是**原始** chunk，因此返回的 `Passage.text` 永不被污染（标题已由 `documents` JOIN 经 `Passage.title` 单独呈现）。前缀只存在于 `Reindexer._maybe_embed` 内部；调用方仍把原始 `chunks` 传给 `upsert_chunks`。memory 复用此机制：fact name 即标题。

- **不触发大规模重 embed。** `content_sha256` 仍是**原始正文**的哈希（标题不折入），因此既有文档不会被判为「changed」—— 它们保留（无标题的）旧向量，直到真正的内容变更或 `force` 对账以带标题重新 embedding。这种渐进 rollout 是有意且可接受的：带/不带标题的向量共享同一空间，无正确性问题。
- **无迁移 / 无 schema 变更。** 无新 FR（既有检索模式下的检索质量改动，与 KB4 chunker、KB2 同类）。无 FTS schema 变更，无 `upsert_chunks`/`upsert_vectors` 签名变更。
- **延后。** keyword 侧的索引化 `title` FTS 列被延后 —— 它需要 FTS 重建迁移且存在短 CJK 标题的 trigram 缺口 —— 直到 keyword 标题匹配确有需要。

## 11. Embedding 请求分批（KB9）

**问题**：重嵌在 per-store 锁内串行——每文档一次 provider 调用——且单次 `embed()` 把一个文档的全部 chunk 放进一个无上限请求。应批量到什么程度？

**决策**：**限制请求大小**，**不**引入跨文档并发。

- **限制请求大小（已交付）。** `OpenAICompatibleEmbedder.embed` 把输入切成至多 `_MAX_EMBED_BATCH`（128）条文本的串行子请求，并按输入顺序拼接结果。这避免块数多的文档（或未来的批量调用方）发出一个无上限请求被 OpenAI 兼容端点按 inputs-per-call / token 上限拒绝（一个潜在 bug，KB5 给每条嵌入文本加 title 前缀后更突出）。每个子请求的 `index` 重对齐 + 宽度校验保留；任一子请求失败抛 `EngineUnavailable`，文档整体降级并经 KB8 的 `embed_pending` 整体重试（per-doc all-or-nothing，不变）。本地（fastembed）嵌入在进程内、无需上限。
- **跨文档并发/批量重嵌：刻意推迟（未构建）。** 把串行 per-document 循环改成并发或跨文档批量已评估、判定为单用户工具上的过度工程：调用内批量本就存在；全量重嵌只发生在 `force` reconcile（配置变更）或 provider 恢复扫描——都罕见——且 `CooldownEmbedder` 已化解 provider-down（无 O(N×timeout) 卡顿）。跨文档重构会破坏 KB8 per-doc `embed_pending` 隔离所依赖的 per-document `embed → upsert_chunks` 原子性，而有界并发的收益仅限云 provider 的罕见操作。仅在出现真实批量重嵌延迟抱怨时再做。
- **无迁移 / 无 schema 改动。无新 FR**（既有检索模式下的可靠性/健壮性改动）。

## 12. 资源列表计数走索引计数，而非 `metrics()`（KB14）

**问题**：资源 LIST 端点（`GET /knowledge_bases`、`GET /memory_stores`）为了显示一个计数，对每个资源调用完整的 `metrics()`。`metrics()` 做了列表输出会丢弃的昂贵磁盘 I/O：KB 的 `metrics()` 每个 KB 跑一次递归 `du_bytes` 磁盘遍历；memory 的 `store_metrics()` 每个 store 同时跑 `scan_store_dir`（读/解析每个 fact 文件）和 `du_bytes` 遍历。列出 N 个资源就触发 N 次磁盘遍历（KB）/ N 次文件扫描 + N 次遍历（memory），只为一个列表会显示、却从不显示其计算出的 `disk_bytes` 的数字。

**决策**：给每条列表路径一个只命中索引 DB `count_documents`、绝不走 `du_bytes` / `scan_store_dir` 的廉价计数。

- **KB 列表**用一个薄方法 `KnowledgeBaseService.document_count(kb_name)` → `count_documents(KIND_KNOWLEDGE_BASE, kb_name)`（即 `metrics()` 本就作为 `document_count` 返回的同一索引计数）。列表路径上无 `du_bytes` 遍历。
- **Memory 列表**用一个薄方法 `MemoryService.fact_count(store_name)` → `count_documents(KIND_MEMORY, store_name)`。计数来源从磁盘文件数（`len(scan_store_dir().files)`）改为 DB 索引——与 KB 现有计数方式一致。索引-vs-磁盘的小幅过期窗口会在下一次 recall/reconcile（惰性 reindex-on-read）时关闭，对一个列表显示数字而言是可接受的取舍。
- **`metrics()` / `store_metrics()` 不变**：每个资源的 DETAIL 端点（`GET /{name}/metrics`）仍遍历磁盘并报告 `disk_bytes`。只有 LIST 路径改了。
- **无迁移 / 无 schema 改动。无新 FR**（既有端点下的性能改动）。

## 13. 持久化"真相之源"文件的原子写入（KB19）

**问题**：Coffer 的不变量是"文件即真相，SQLite 是可重建索引"，但持久化的 Markdown / raw 文件此前通过裸 `path.write_text` / `path.write_bytes` 非原子写入。写入中途崩溃或断电会留下被**截断**的文件 —— 一个损坏的真相之源，而下一次 reindex 会原样把它吃进索引。

**决策**：把每个持久化真相写入都走同一个共享辅助函数 `coffer.infrastructure.knowledge.fs.atomic_write_text` / `atomic_write_bytes`：先写到**同一目录**下的临时文件，fsync，再 `os.replace` 就位。`os.replace` 在同一文件系统上是原子重命名，因此并发读者只会看到**完整的旧文件**或**完整的新文件**，绝不会是残缺的混合；任意失败都会删除临时文件并保持原文件不变。

- **已转换的写入点**：KB 文档写入（ingest 经 `mkparent_write`、edit、reconvert）与 KB raw 上传字节；memory fact 文件、organizer 主题文档 + `INDEX.md`、以及按分支的 handoff 文件。辅助函数仅依赖标准库（无导入环），放在共享的 `infrastructure.knowledge` substrate —— 那里本就是 application 可组合的 kind-agnostic 辅助函数之家（chunking、frontmatter、ids、paths），import-linter 契约允许 `application/knowledge_base/*` 导入 —— 故 `application/knowledge_base/*` 与 `infrastructure/memory/*` 复用同一个，且不改动任何架构边界。原本就在事件循环外的写入保留其 `asyncio.to_thread` 包装（辅助函数是同步的）。
- **追加型日志刻意不转换**：`consolidation-log.md` 以追加模式（`"a"`）打开；它是审计追踪，原子替换会摧毁既有历史，且一次被打断的追加也无法损坏先前的行。
- **目录 fsync（断电下的重命名持久性）刻意推迟**：单次文件 fsync + `os.replace` 已提供**原子性**（无残缺/损坏文件），这正是 KB19 的目标。要保证重命名**本身**在断电后存活，还需对父目录再做一次 fsync；这是更强的持久性保证，可在出现真实需求时后续叠加到同一辅助函数上，且无需改动任何调用点。
- **无迁移 / 无 schema 改动。无新 FR**（既有行为下的健壮性/质量改动）。memory 的真相之源文件（spec 007）共享该辅助函数；这是原子性保证的唯一归处。

## 14. 代码卫生清理（死代码 + 过时注释）

**问题**：若干产物早于 spec-006 重设计与 ADR-028 的 ULID 标识切换，遗留了死代码、误描述 doc-id 标识的注释、未使用的 i18n key，以及一个未记录的扫描上界。一次删除安全性审计已逐项确认它们确实死/过时，可安全移除或更正。

**决策**：一次无行为变更的清理：

- **移除死的 `kb_doc_id` / `DOC_ID_LEN`** 辅助（旧的"`source_sha256` 前 16 位十六进制"内容寻址 doc id）。doc id 现已是 ULID（ADR-028：重新上传会**铸造新 id**），该辅助零调用点；已从 `domain/knowledge_base/document.py` 删除，并从两处 `__all__` 中剪除。
- **改写过时的"content-addressed"doc-id 注释**：位于 `infrastructure/knowledge/models.py`、`infrastructure/knowledge/sqlite_index.py` 及对应的集成测试 docstring。store 作用域的 chunk-id 理由**仍成立** —— ULID 只在单个 store 内唯一，故同一 doc id 仍可能跨 store 出现且不能碰撞 —— 仅更正了"内容寻址 / 同一文件重复其 id"这一错误前提。`memory/scope_fs.py` 中真正内容寻址的路径哈希、不可变的迁移历史、以及 ADR-028 对**旧**方案的描述均保持不动。
- **删除 14 个未使用的 KB i18n key**（旧的每 KB embedding 表单 `dialog.{vectorHint,provider,embeddingModel,dimensions,baseUrl,credential}`，现已全局；以及被 `common.*` 取代的 `detail.{metrics,reindexResult,chunks,editAria,loadFailed,edit,save,cancel}`），从 `en.json` + `zh.json` 双语同删，保持两份 locale 结构一致。
- **把 100k 每次扫描的文档上界记录为单个命名常量** `DOCUMENT_SCAN_LIMIT`，定义在 `domain/knowledge/document.py`，在全部三个 `list_documents(limit=…)` 对账点（KB reindex 扫描、KB source-tracking、memory sync）使用。它是一个**安全上界** —— 单次扫描/对账每个 store 的最大文档数，**而非**强制的 ingest 限制；语料预期远低于它。取值不变（100_000）。
- **每 KB 的 `embedding` 配置字段经评审予以保留** —— 运行期惰性的遗留物，但**契约仍活**：它仍支撑注册期"凭据缺失"保证、一个验收测试，以及 CLI/前端表面。故**刻意不**移除。

**无迁移 / 无 schema 改动 / 无新 FR**（既有行为下的纯清理）。

## 15. 文档时间戳写入 frontmatter（KB18）

**问题**：Coffer 的不变量是"文件是真相，SQLite 是可重建的索引"，但 KB 文档的磁盘 `.md` frontmatter 此前**未**记录 `created_at` / `updated_at`。于是数据库丢失、从文件重建行（`document_from_frontmatter`）时，两个时间戳都会被重置为 `now()` —— 原始的 ingest/编辑时间被悄无声息地丢失。记忆面（spec 007）已在每个 fact 文件里记录并回读这两个字段，故该缺口仅在 KB 侧。

**决策**：在每条写入路径把 `created_at` / `updated_at`（ISO 字符串）写入 KB 文档 frontmatter —— ingest（`render_ingest_markdown`）与 编辑/重转换（`render_doc_markdown`），并保持两处字段集合**完全一致**，使 ingest→编辑→重建的往返稳定。首次 ingest 两者都等于 `now`；重新上传时 `created_at` 从既有文档保留、`updated_at` 顶进；编辑/重转换保留 `created_at`、顶进 `updated_at`。数据库丢失重建（`document_from_frontmatter`）现会回读它们，使重建行恢复**真实**时间戳，而非 `now()`。

- **文件 mtime 兜底以向后兼容**：缺失这些 key（或值为空/无法解析）的既有 / 手写文件，降级到文件的 `mtime` —— 而非 `now()` —— 与记忆面 `parse_fact_markdown` 一致。故既有语料以合理时间重建，**无需迁移 / 无需回填**。
- **本地 `_parse_dt` 辅助，不跨 kind import**：ISO→aware-UTC 解析辅助是 `application/knowledge_base/pipeline_helpers.py` 内的本地副本；import-linter 禁止从 `infrastructure/memory/*` import（memory↔knowledge_base 是不同 kind），而每个 kind 各持一份副本是既定模式（记忆面的 topic_files / handoff 各自一份）。
- **`converted_at` 不变** —— 它跟踪一次转换引擎运行，而非文档年龄，故重建时仍为 `now`。
- **无新 FR** —— 这是在既有 FR-008 / SC-005 重建保证下补上一个"文件即真相"的缺口。无 schema/DB 改动（`documents` 表已有这两列）；仅改变磁盘文件内容与重建读取路径。

## 16. 源文件更新检测——前端（FR-021..024）

**问题**：PR #140 交付了外部源文件跟踪的后端——`check-sources` 扫描会按文档（仅限带有跟踪 `source_path` 的文档）报告其原始磁盘文件是 `unchanged`（未变更）/ `changed`（已变更）/ `missing`（文件已删除）/ `edited`（源文件已变但文档曾本地编辑，故跳过重新摄入）/ `updated`（曾变更并因该知识库的 `auto_update_sources` 开启而自动重新摄入）；外加按文档的 `update-source` 重新摄入与按知识库的 `auto_update_sources` 配置开关。这些此前都无法从 UI 触达。

**决策**：在知识库详情页以纯增量 UI 暴露（不改后端）：

- 在标题栏（紧邻 设置 / 重建索引 / 上传）新增 **「检查源文件」** 动作，POST `check-sources` 并打开 **报告对话框**。每行显示文档标题、其源文件路径，以及对应五种状态之一的状态徽标。只有 **`changed`** 行提供按行的 **「从源文件更新」** 按钮（POST `update-source`，原地重新摄入）；`missing` 行注明文件已不存在，`edited` 行注明文档已本地编辑、为避免覆盖而禁止更新（后端会以一个带类型的错误拒绝 `edited` 文档，以 toast 形式呈现）。当扫描返回零行时，对话框会说明 **网页上传不会被跟踪**——只有基于路径的摄入（CLI / 桌面）才带有源文件。

- 按知识库的 **`auto_update_sources`** 开关在设置对话框中新增一个 `<Switch>` 行。由于配置 PATCH 会 **替换** 整个配置对象（FR-014/FR-019），该开关的值会被串进提交时构建的合并配置中，并且该字段已加入 `KnowledgeBaseConfigOut`，从而保证保存设置不会悄悄把它重置为 false。

- **无新增 FR**——这交付的是既有 FR-021..024 的前端；覆盖由新的 `SourceCheckDialog` vitest 套件与扩展后的详情页测试（断言「检查源文件」会打开对话框、且设置 PATCH 携带 `auto_update_sources`）保证。

## 17. 文档列表筛选 + 多选批量删除——前端（KB12）

**问题**：知识库详情页的文档列表（`KnowledgeBaseDocTree`，左侧栏的可点击行 `<ul>`）此前无法收窄一个很长的列表，也无法一次删除多个文档——单条删除是由查看器驱动的（选中文档 → 右侧 Trash2 → 确认 → 删一条）。策展一个大知识库只能滚动并逐条删除。

**决策**：就地增强既有侧栏——纯增量前端，不改后端：

- 在文档树顶部（在 `<aside role="complementary">` 内、`<ul>` 之上）放一个小的客户端 **筛选 `<Input>`**。它按 **大小写不敏感的标题子串** 过滤已渲染的文档；空筛选显示全部文档，若筛选把一切都隐藏，则显示一行灰色的「无匹配」提示。

- 每行新增一个 **作为可点击标题「兄弟」的 `<Checkbox>`**（绝不嵌套互动元素）。标题仍是可按其文本选中的 `<button>`——从而保留 e2e（`shell_knowledge_base.spec.ts` 按文本点击 "Deploys"）与详情页测试（`getByRole("complementary")` + 按文本点击）的选择器。表头的「全选」复选框覆盖 **筛选后** 的集合（沿用 `useTableSelection` 的 selected ∩ visible）。

- 当选中 ≥1 行时，共享的 **`BulkBar`**（来自 `DataTableSelection`）显示计数 + 删除 + 清除。删除打开 `ConfirmDialog`；确认后，页面 hook 的 `bulkDelete` 经 `useBulkMutate` 把 `deleteDocument(name, id)` 在所选 id 上扇出（一条汇总 toast + 一次 `["kb-documents"]`/`["kb-metrics"]` 失效），随后清空选择。若当前正在 **查看** 的文档也在删除之列，则重置查看器的 `selectedId`，使右侧面板不再显示已删除的文档。

- 我们 **保留了双栏布局**（侧栏树 + 右侧查看器），而非换成全宽 `DataTable`：DataTable 不适配窄侧栏，且会破坏查看器流程与 e2e/详情页选择器。单条删除路径（查看器 Trash2 → 确认 → `del`）保持不变。

- **无新增 FR**——这是对既有 FR-013/FR-020 文档管理表面的一个 UX 增益；覆盖由扩展后的详情页测试保证（筛选会收窄/恢复/无匹配；选中两行 → 批量栏 → 确认 → 每个 id 调用一次 `deleteDocument` → 选择清空；点击标题仍能在查看器中加载）。

## 18. 摄入拒绝错误的可读性——扫描 PDF + 由 reason 驱动的消息（KB11/KB15）

**问题**：摄入拒绝（`IngestRejected`）把所有原因——空转换、上传过大、重复、不支持的类型——都坍缩成同一句通用的前端文案（`translateApiError` 只按信封 `code` 取键，于是所有 `INGEST_REJECTED` 的 reason 都映射到「文档在摄入过程中被拒绝」）。最糟糕的是：**扫描件 / 纯图片 PDF** 会转换成空 markdown，抛出通用的 `"empty"` reason，用户既不知道为什么，也没有下一步可做。

**决策**——让机器 `reason` 端到端可读，且为增量、向后兼容：

- **后端（KB11）**：当清洗后的 markdown 为空 **且格式是 PDF**（`fmt.lower().lstrip(".") == "pdf"`，同时处理 `"pdf"` 与 `".pdf"`）时，转换器注册表抛出一个独立的 `IngestRejected("scanned_pdf", <可操作消息>)`（「该 PDF 无可提取文本——看起来是扫描件或纯图片。请运行 OCR…」）。检测保持 **严格判空**（不加长度阈值——较低阈值会对确实很短的 PDF 误报）。其他所有格式保留通用的 `"empty"` reason。reason→HTTP 映射新增 `"scanned_pdf": 415`（与 `"empty"` 同状态码）。错误信封已经通过 `_details_for` 携带 `details.reason`。
- **前端（KB15）**：`translateApiError` 现在先尝试一个 **由 reason 限定的扁平键** `errors.${code}_${reason}`（如 `errors.INGEST_REJECTED_scanned_pdf`）——之所以扁平，是因为 `errors.INGEST_REJECTED` 本身是字符串，因此嵌套的 `errors.INGEST_REJECTED.scanned_pdf` 不可能存在。该键命中则采用；否则原样回退到既有的 `errors.${code}` → 信封消息链。`throwApiError` 现在把信封的 `details` 透传到所抛出的 `ApiError` 上（此前会丢弃），使 reason 能在各处到达翻译器。`details` 被防御式读取（从 `unknown` 收窄）；缺失或非字符串的 reason 行为与此前完全一致。
- **无新增 FR**：这是错误质量（与此前的 KB 项目一致）——由一个后端注册表测试（PDF 空转换 → `scanned_pdf`；`.pdf` 归一化；非 PDF 空转换仍为 `empty`）与一个前端 `translateApiError`/`throwApiError` 测试覆盖。仅新增必需的 `INGEST_REJECTED_scanned_pdf` i18n 键（en+zh）；通用键仍作回退。

## 19. 此处明确不决定 / 范围外

- 单次调用里 keyword + vector 的 hybrid RRF 融合（可选未来，同引擎）。
- 检索时的 reranking / HyDE / multi-query / LLM 综合 —— agent 综合。
- agent 编辑 KB 文档 —— KB 由用户策展；后续再议。
- 默认图像 OCR / 音频转写。
- 默认开启的文件系统 watcher。
- 按格式的最终转换库（MarkItDown vs Docling）与本地模型 MTEB/CPU 基准 —— 在 converter/embedder 端口后做运维调优；无需重新建模。
- sqlite-vec 在 macOS arm64 + Linux 的打包 —— 由 `importorskip` 守护；加载失败把 vector 降级为 keyword，绝不阻断。
