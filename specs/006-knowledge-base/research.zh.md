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

## 9. 此处明确不决定 / 范围外

- 单次调用里 keyword + vector 的 hybrid RRF 融合（可选未来，同引擎）。
- 检索时的 reranking / HyDE / multi-query / LLM 综合 —— agent 综合。
- agent 编辑 KB 文档 —— KB 由用户策展；后续再议。
- 默认图像 OCR / 音频转写。
- 默认开启的文件系统 watcher。
- 按格式的最终转换库（MarkItDown vs Docling）与本地模型 MTEB/CPU 基准 —— 在 converter/embedder 端口后做运维调优；无需重新建模。
- sqlite-vec 在 macOS arm64 + Linux 的打包 —— 由 `importorskip` 守护；加载失败把 vector 降级为 keyword，绝不阻断。
