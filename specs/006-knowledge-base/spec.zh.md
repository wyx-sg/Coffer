# 功能规范：Knowledge Base Manager

> English: [spec.md](./spec.md)

**Feature Branch**: `feature/kb-manager`
**Created**: 2026-05-22
**Status**: Draft
**Input**: 用户描述：「Coffer 的第五个 feature —— 管理本地知识库，编码 agent 可通过 Coffer 的 MCP 网关检索其中内容。一个 Knowledge Base 是一个 Resource（kind=knowledge_base），承载一组由用户明确加入的文档；Coffer 负责切块、embedding、建索引、提供检索。基于 001-mcp-gateway 奠定的与 kind 无关的 Resource 框架之上构建。引擎：LlamaIndex（业界主流 RAG 框架），藏在一个薄端口之后，让 Coffer 的 application 层从不直接 import 它。」

## 用户场景与测试

### User Story 1 —— 从本地文档建一个 KB（优先级 P1）

某开发者把个人文档 —— 设计笔记、ADR、内部 wiki、几篇研究论文的 PDF —— 散落在各个目录。他希望把这些文件丢进 Coffer，让自己的编码 agent 在工作中能自然地跨这些文档检索，不必把任何东西上传到第三方。

**为什么是这个优先级**：这是本规范的核心。没有它，就没有知识库。

**独立可测**：从一份全新的 Coffer 安装开始，创建一个名为 `design-notes` 的 KB，上传三份 markdown + 一份 PDF，列出文档，跑一次检索，看到结果引用了源文件。

**代表性场景**：

- 创建一个 KB
- 摄入一个文档
- 列出 KB 中的文档
- 检索返回带源信息的排名片段
- 删除单个文档
- 删除整个 KB 会清掉文件与索引

---

### User Story 2 —— 编码 agent 通过 Coffer 的 MCP 网关检索 KB（优先级 P1）

开发者的编码 agent（Claude Code、Cursor 等）接入 Coffer 的 MCP 端点。通过 Coffer 的内置工具，agent 可以列 KB、在某个 KB 内检索、按 id 取回文档全文 —— 完全不需要额外的 MCP 服务器。

**为什么是这个优先级**：没有 agent 侧的访问，KB 就只是一个个人文件查看器。Agent 集成才是它在编码现场真正有用的原因。

**独立可测**：在已经填充了文档的 KB 上，连接到 Coffer 的 MCP 客户端会在工具清单里看到 `coffer__search_knowledge_base`、`coffer__get_document`、`coffer__list_knowledge_bases`；调用 `search_knowledge_base` 返回排名片段。

**代表性场景**：

- 内置工具出现在客户端的工具清单里
- agent 检索一个 KB
- agent 按 id 取一份文档
- agent 列出可用的 KB

---

### User Story 3 —— 在桌面端管理 KB（优先级 P2）

开发者更习惯用可视化界面做日常管理 —— 建 KB、把文件拖进去、浏览文档、试搜一下。

**为什么是这个优先级**：非 CLI 用户需要，也让日常 UX 更顺。但不需要它就能跑通核心价值。

**独立可测**：启动 Coffer，从表单创建一个 KB，把文件拖到上传区，观察摄入进度，打开 KB 详情页，从搜索框查询，看到结果。

**代表性场景**：

- 桌面端创建 KB
- 桌面端上传文档
- 桌面端检索
- 桌面端删除一个文档

---

### User Story 4 —— 命令行管理 KB（优先级 P2）

开发者用脚本批量摄入（`for f in docs/*.md; do coffer kb ingest design-notes "$f"; done`），在终端里做批量操作。

**为什么是这个优先级**：Coffer 面向开发者，完整的 CLI 是基础项。

**独立可测**：在终端里创建 KB、摄入一个目录里的文件、检索、删除一个文档、删除 KB —— 全程不碰 UI。

**代表性场景**：

- CLI 覆盖每一个桌面操作
- CLI 检索能返回机器可读的 JSON

---

### User Story 5 —— 观察 KB 的运行情况（优先级 P3）

开发者想看到文档何时加入、检索过什么、每个 KB 占多少磁盘 —— 但日志不能无限增长。

**为什么是这个优先级**：信任与调试都需要它，但不阻塞基本流。默认的保留策略已经合理。

**独立可测**：在多次摄入和检索之后，打开审计视图，看到生命周期条目；打开每个 KB 的 metrics，看到文档计数与磁盘占用；改一下保留策略，等一会儿，确认老条目被清理。

**代表性场景**：

- 审计记录 KB 的生命周期变更
- KB metrics 显示文档数和磁盘占用
- 保留策略适用于 KB 摄入日志

---

### Edge Cases

- **不支持的文件类型**：摄入一个 Coffer 不知道怎么抽文本的文件（二进制 blob、没有 OCR pipeline 的图片）会快速失败、不留痕。
- **重复文档**：重复摄入一份内容哈希已经存在的文件会被明确拒绝；用户可以在 CLI 加 `--replace` 或在 UI 确认以覆盖。
- **超大文档**：超出配置大小限制（默认 25 MB）的文档在 API 边界就被拒，根本走不到抽取与 embedding。
- **空文档**：抽到 0 个字符的文件被拒 —— 没东西可索引。
- **引擎不可用**：如果 LlamaIndex（或其 embedding 模型）在 daemon 启动时初始化失败，KB 的摄入接口返回 503，错误信息指明缺哪个依赖；KB 仍可创建与列出，但摄入会被门控。
- **摄入中途磁盘满**：部分摄入会回滚 —— 原始文件清除、索引不变、`kb_documents` 不留孤儿行。
- **摄入进行中删除 KB**：拒绝删除，返回 409；让用户等摄入完成后再重试。
- **并发检索**：同一个 KB 上的多次检索互不影响；没有按 KB 加锁拖累延迟。
- **改 embedding 模型**：在 KB 已经索引文档之后改 embedding 模型会被拒 —— 一个 KB 的 embedding 模型创建后即不可变；想换模型就新建 KB。

## Acceptance Scenarios

按 `agents/sdd.md` 与 `agents/testing.md` 的约定，本节中的每一个场景都至少被一个带 `@pytest.mark.acceptance(spec="006-knowledge-base", scenario="…")` 的测试引用。

### Scenario: create a knowledge base

- **Given** coffer daemon 正在运行且没有任何 KB，
- **When** 用户用一个唯一名字 + 一个 embedding 模型选项创建一个 KB，
- **Then** KB 被持久化，磁盘上 `~/.coffer/kb/<name>/` 初始化出空索引，列出 KB 时能看到它。

### Scenario: ingest a single document

- **Given** 已经存在一个 KB，
- **When** 用户上传一个文件（markdown / 纯文本 / pdf / 源代码），
- **Then** 原始文件落到 KB 目录下，文本被抽出、切块、embedding、入索引，`kb_documents` 表里新增一行（id / 文件名 / 大小 / 内容哈希 / 摄入时间）。

### Scenario: list documents in a knowledge base

- **Given** 文档已被摄入到某个 KB 中，
- **When** 用户列出该 KB 的文档，
- **Then** 每个文档一行，含稳定 id、文件名、大小、摄入时间，并分页。

### Scenario: search returns ranked passages with sources

- **Given** 文档已被摄入，
- **When** 用户在 KB 中跑一次检索，
- **Then** 收到排名片段，每条带源文档 id、文件名、相关性分数。

### Scenario: delete a single document

- **Given** 一个 KB 有文档，
- **When** 用户按 id 删除一个文档，
- **Then** 原始文件被移除，对应 chunk 从索引中删掉，`kb_documents` 中的行删除，审计写入一行，后续检索不再返回该文档。

### Scenario: delete a knowledge base cleans up files and index

- **Given** 一个 KB 有文档、有已建好的索引，
- **When** 用户删除该 KB，
- **Then** 每个文档行被删除，磁盘目录 `~/.coffer/kb/<name>/` 被移除，内存里的引擎实例被 dispose，Resource 行被删。

### Scenario: built-in tools appear in client tool list

- **Given** 一个 MCP 客户端接入 coffer 的网关,
- **When** 客户端列出工具,
- **Then** 工具列表中含 `coffer__list_knowledge_bases`、`coffer__search_knowledge_base`、`coffer__get_document`，与上游 MCP server 工具并列。

### Scenario: agent searches a knowledge base

- **Given** 一个有索引文档的 KB 已存在，
- **When** MCP 客户端调用 `coffer__search_knowledge_base`，传入 kb 名与 query，
- **Then** coffer 返回适合 LLM 直接消费的结构化排名片段（text + 源 document id + 分数）。

### Scenario: agent fetches a document by id

- **Given** 文档存在于某 KB 中，
- **When** MCP 客户端调用 `coffer__get_document`，传入 kb 名与 document id，
- **Then** coffer 返回该文档的抽取文本与 metadata；若 id 未知，返回明确错误。

### Scenario: agent lists available knowledge bases

- **Given** 注册了零个或多个 KB，
- **When** MCP 客户端调用 `coffer__list_knowledge_bases`，
- **Then** coffer 返回每个 KB 的 name、description、文档计数与 embedding 模型。

### Scenario: audit records KB lifecycle changes

- **Given** 用户创建 / 摄入 / 删除单条 / 删除 KB，
- **When** 他打开审计日志，
- **Then** 每次变更一行，含 actor、时间、描述变更的 payload。

### Scenario: KB metrics show document count and disk usage

- **Given** 一个 KB 有文档，
- **When** 用户打开它的详情视图（UI 或 `coffer kb describe`），
- **Then** 看到文档数和 `kb/<name>/` 的字节数。

> **延后到未来的测试工作里**（前端 Playwright + 完整 CLI integration）：以下场景属于用户可见契约的一部分，但其测试会与 e2e 测试设施一起落地，本 PR 不交付。在此列出以保持规范完整；`make verify-acceptance` 不门控它们。
>
> - 桌面端创建 KB
> - 桌面端上传文档
> - 桌面端检索
> - 桌面端删除一个文档
> - CLI 覆盖每一个桌面操作（端到端，带运行中的 daemon）
> - CLI 检索能返回机器可读的 JSON
> - 保留策略适用于 KB 摄入日志

## Requirements

### Functional Requirements

**Resource 生命周期**

- **FR-001**: 系统必须支持新的资源 kind `knowledge_base`；用户必须能通过既有的 kind-agnostic Resource 框架对 KB 进行创建、列出、查看、更新（仅 description 与 `max_document_bytes` —— 其余配置创建后不可变）、启用、禁用、删除。
- **FR-002**: 系统必须用 Pydantic schema 校验 KB 配置（embedding 模型 id、chunk size、chunk overlap），拒绝同 kind 内的重名，校验失败什么也不落库。
- **FR-003**: 系统必须把每个 KB 的文档落在 `~/.coffer/kb/<name>/`，原文在 `raw/`，索引在 `index/`。删除 KB 必须连这个目录和对应的 `kb_documents` 行一起删掉。

**文档生命周期**

- **FR-004**: 用户必须能把一个文档摄入 KB；系统必须抽取文本、切块、embedding、并加入索引。
- **FR-005**: 系统至少必须支持这些类型：`.md`、`.markdown`、`.txt`、`.rst`、`.pdf`，以及常见源代码文本格式（`.py`、`.js`、`.ts`、`.go`、`.java`、`.rs`、`.c`、`.h`、`.cpp`、`.hpp`、`.sh`、`.yaml`、`.yml`、`.json`）。
- **FR-006**: 系统必须默认拒绝大于 25 MB 的文件（可逐 KB 配置）、拒绝未识别的可抽文本类型、拒绝抽出空文本的文件。
- **FR-007**: 系统必须为每个摄入文档计算 SHA-256 内容哈希；同哈希已存在的文档默认拒绝，除非调用方显式传 override。
- **FR-008**: 用户必须能列出 KB 中的文档（分页）、取得单个文档的抽取文本、删除单个文档。删除必须连原始文件、对应索引条目、数据库行一起处理。

**检索**

- **FR-009**: 用户必须能用 query 检索 KB，得到排名片段，每条含源 document id、文件名、文本片段、相关性分数——通过 KB 配置的 `search_mode`（见 FR-017）。
- **FR-010**: 检索默认返回 top 5 条；调用方可传 `top_k`，范围 1–20。
- **FR-017**: 每个 KB 必须声明 `search_mode`，创建后固定：`keyword`（默认）按词频在已摄入的文档文本上排名，**不需要** embedding 模型、也不下载模型——KB 一创建即可用，就像搜索文件；`semantic` 使用每个 KB 的 embedding 模型做向量相似度（FR-015 仅适用于此模式）。两种模式都满足 FR-009。

**Agent 集成 (MCP)**

- **FR-011**: Coffer 的 MCP 网关必须把内置工具 `coffer__list_knowledge_bases`、`coffer__search_knowledge_base`、`coffer__get_document` 暴露给每个接入的 MCP 客户端，与上游 MCP server 工具并列。
- **FR-012**: 内置工具必须挂在保留前缀 `coffer__` 下，保证不与上游 `<server>__<tool>` 命名冲突。
- **FR-013**: 内置工具的调用必须像上游工具调用一样被记入既有的 `mcp_invocations` 表（时间、能力 key、耗时、状态 —— 不记参数也不记返回值），保留与审计逻辑统一适用。

**引擎隔离**

- **FR-014**: 系统必须把 RAG 引擎（LlamaIndex）严格限定在 `coffer/infrastructure/knowledge_base/`。`domain/` 与 `application/` 层不得直接 import LlamaIndex 类型；只能通过 `KnowledgeBaseStore` 端口交互。
- **FR-015**: 如果引擎或其 embedding 模型初始化失败，daemon 仍必须能起；只有摄入与检索接口返回 503，错误信息指明缺哪个依赖。

**接口面**

- **FR-016**: 用户必须能通过 (a) `/api/v1/knowledge_bases/` 下的 REST API、(b) `coffer kb …` 子命令、(c) 既有 `Resources` 导航下的桌面 UI 完成每个操作。

### Key Entities

- **Knowledge Base**（kind 为 `knowledge_base` 的资源）：承载一个 KB 的配置 —— embedding 模型、chunk size、chunk overlap、max 文档大小、description。创建后除 description 外不可变。
- **Document**：KB 中一个被摄入的文件。以 (kb_name, document_id) 标识。存文件名、大小、sha256、mime 提示、摄入时间、chunk 数。抽取出的正文按需从 `kb/<name>/raw/<document_id><ext>` 计算。
- **Passage**（检索结果，不落库）：检索产出的一个 chunk —— 文本片段、document id、文件名、分数、在源文档中的序号位置。

## Success Criteria

### Measurable Outcomes

- **SC-001**: 从零安装起步，用户在 60 秒内能建出第一个 KB 并摄入第一个文档，查文档不超过一次。
- **SC-002**: 一个 50 篇文档的 KB（markdown + PDF，合计 ≤ 50 MB）上，典型 query 的检索墙钟延迟在开发者笔记本上 ≤ 500 ms，量在 REST 接口上。
- **SC-003**: 删除一个 KB 会清掉 100% 磁盘占用和 100% 数据库行；由自动化测试在删除前后 walk `~/.coffer/kb/` 与查 `kb_documents` 验证。
- **SC-004**: 一个接入 Coffer MCP 网关的编码 agent 能在一次 MCP session 内列 KB、检索 KB、取文档 —— 全部通过内置工具，无需额外安装 MCP server。
- **SC-005**: 本文件中的每一条 Acceptance Scenario 都至少被一个带 `acceptance(spec="006-knowledge-base", scenario="…")` 的测试覆盖；`make verify-acceptance` 报零个未覆盖场景。
- **SC-006**: 引擎隔离由 importlinter 强制：`coffer.application.*` 与 `coffer.domain.*` 下任何模块都不得 import `llama_index`（由 `backend/pyproject.toml` 中的一条契约校验）。
- **SC-007**: `make verify`（lint + 单元 + 集成 + 契约 + acceptance 审计）本地与 CI 都通过。

## Assumptions

- 用户在自己的机器上跑 Coffer。无多租户或远程访问需求。
- Embedding 模型在本地跑（默认模型在 CPU 上足够）。摄入与检索均无出网调用。
- LlamaIndex 仍是活跃维护的 Python 包。若未来版本破坏 API 兼容性，影响范围仅限 `infrastructure/knowledge_base/llamaindex_store.py`。
- 单用户并发量小（一个用户偶尔的并发摄入与检索）。本系统不为车队级 RAG 设计。
- KB **不是** memory store：它存的是用户明确加入的文档。`memory` kind（spec 007）存的是简短的派生事实。两者不共享 schema。

## Notes for reviewers

- **KB 专属表的保留策略种子**：US5 最后一条（「保留策略适用于 KB 摄入日志」）部分延后 —— 既有 `audit_log` 与 `mcp_invocations` 的保留策略已分别覆盖 KB 生命周期与内置工具调用行；KB 专属审计 / 日志表的保留策略种子延后到后续 PR。
- **CLI 测试层级**：US4 中的 CLI 命令通过 e2e 测试层（运行中的 daemon + 子进程 `coffer kb …`）覆盖。本 PR 不为 CLI 模块本身添加 unit / integration 测试；CLI 是 HTTP 接口的薄壳，而 HTTP 已有完整 integration 覆盖。
