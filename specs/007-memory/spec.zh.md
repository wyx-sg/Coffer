# 功能规范：Memory Manager

> English: [spec.md](./spec.md)

**Feature Branch**: `feature/007-memory`
**Created**: 2026-05-22
**Status**: Draft
**Input**: 用户描述：「Coffer 的第七个 feature —— 管理本地 AI agent 记忆：关于用户 / 项目 / 偏好的短、派生事实，由编码 agent（以及可选地由用户）写入，再通过 Coffer 的 MCP 网关回吐给 agent。引擎：mem0（业界主流 memory 框架），藏在一个薄端口背后，让 Coffer 的 application 层从不直接 import 它。基于 001-mcp-gateway 奠定的与 kind 无关的 Resource 框架之上构建。与 knowledge_base（spec 006）有所区分 —— KB 装的是用户上传的文档，memory 装的是短的派生事实。」

## 用户场景与测试

### User Story 1 —— Agent 跨会话记住事实（优先级 P1）

开发者的编码 agent（Claude Code / Cursor / …）接到 Coffer 的 MCP 端点。某次会话里它学到这位开发者偏好 tabs 而不是 spaces、分支名用 kebab-case、避免 force-push。通过 Coffer 内置的 `coffer__add_memory` 工具，agent 把每条事实记下来。下次会话里 —— 哪怕换了 MCP 客户端 —— agent 用 `coffer__search_memory` 配一条相关 query，同一批事实重新出现，省得反复追问。

**为什么是这个优先级**：这是本规范的核心。没有跨会话召回，memory 这条 feature 相对 agent 已经能做的 in-context 记忆就什么都不剩。

**独立可测**：从一份全新的安装开始，注册一个 memory store，用 MCP 客户端调三次 `coffer__add_memory`，重启 daemon，再用客户端调 `coffer__search_memory` 配一条相关 query，看到之前写入的事实被召回。

**代表性场景**：

- 创建一个 memory store
- agent 写入一条 memory
- agent 检索 memory
- memory 在 daemon 重启后仍然存在
- agent 删除单条 memory
- 删除整个 memory store 清掉所有副本

---

### User Story 2 —— 用户审核与维护 agent 记下的东西（优先级 P1）

开发者要看得见、管得住：能查到 agent 写了哪些事实、在事实跟现实脱节时改它、能选择性地忘记、还能阻止 agent 写某些类别。

**为什么是这个优先级**：没有维护手段的 memory 让人不放心（agent 偶尔会记错）。能维护，这条 feature 才足够可信、用户才愿意一直开着它。

**独立可测**：agent 写了若干条 memory 之后，用户打开列表、选一条、改其文本、保存，看到 agent 下一次搜索返回的是改后的版本。再删另一条，确认它已经没了。

**代表性场景**：

- 在 store 内列出 memory
- 编辑一条 memory
- 用户直接写入一条 memory
- 在 UI 中删除 memory

---

### User Story 3 —— 在桌面端管理 memory（优先级 P2）

开发者更喜欢可视化的列表 —— 能搜索、能滚动、能扫读，找出过时或错误的条目。

**为什么是这个优先级**：给非 CLI 用户用。memory 的形态（可滚动列表、就地编辑）天然更适合 UI 而非 CLI。

**独立可测**：启动 Coffer，进入 memory store，看到列表，在其中搜索，就地改一条、删一条，两个动作都立刻反映在视图里。

**代表性场景**：

- 桌面端列表视图显示 memory
- 桌面端就地编辑
- 桌面端搜索框过滤

---

### User Story 4 —— 在命令行管理 memory（优先级 P2）

开发者要做批量脚本：把所有 memory 导出成 JSON、按 tag 批量删、从文件里导入。

**为什么是这个优先级**：备份 / 迁移 / 排错的支撑能力。

**独立可测**：开终端，把 memory 列成 JSON，改 JSON，按 id 批删几条，再导出到一个文件 —— 全程不开 UI。

**代表性场景**：

- CLI list / add / delete
- CLI 输出 JSON 供管道使用

---

### User Story 5 —— 观察并约束 memory 增长（优先级 P3）

开发者想要安心：memory 不会悄无声息地无限增长，必要时还能一键全清。

**为什么是这个优先级**：卫生级别；不挡核心流程。

**独立可测**：看到 per-store 的度量（条数、磁盘占用）。触发「清空本 store 全部 memory」。确认所有 memory 都没了但 store 本身保留下来，随时可以再装东西。

**代表性场景**：

- per-store 度量
- 清空一个 store 的全部 memory

> **保留说明**：每个 store ~10,000 条 memory 的上限是规划层面的软目标（见 `plan.md` Technical Context 中的「Scale / Scope」），不是一条由 FR 强制的硬上限。本规范的任何 FR 都没有在执行层强制它；未来若有真实使用需求，可能会再起一份规范追加执行策略（rolling eviction、硬上限拒绝、或操作侧告警）。

---

### Edge Cases

- **mem0 的 LLM 依赖没配置**：mem0 在写入时要调一个 LLM（做事实抽取）。如果没配 LLM provider，`add_memory` 接口返回 503，并明确指向配置文档。读路径（`search_memory`、`list`）依旧可用 —— 它们不需要 LLM。
- **LLM 端点在写入时不可达**：单次写入失败不会让 store 坏掉；操作返回错误，用户重试即可。
- **过长的输入文本**：API 边界把 memory 文本约束在 8 KB；超长会在到达 mem0 之前被拒。
- **空 memory 文本**：在 API 边界被拒。
- **重复 memory**：mem0 自带 dedup / merge 逻辑；我们透传它的结果，不静默吞结果。审计行会记录 `created` 还是 `merged`。
- **写入仍在飞、用户想删 store**：返回 409；用户等写入结束后重试。
- **embedding 模型在 store 中途换**：拒绝 —— 跟 knowledge_base 一样（创建后不可变）。

## Acceptance Scenarios

每条场景至少对应一个被 `@pytest.mark.acceptance(spec="007-memory", scenario="…")` 打了标记的测试。

### Scenario: create a memory store

- **Given** coffer daemon 已运行，当前没有任何 memory store，
- **When** 用户用一个唯一的名字 + embedding 模型 + LLM provider 选项创建 memory store，
- **Then** store 被持久化，一个空的 mem0 实例在 `~/.coffer/memory/<name>/` 下初始化好，列出 stores 时能看到它。

### Scenario: agent adds a memory

- **Given** 一个 memory store 已经存在且 LLM provider 已配置，
- **When** 某个 MCP 客户端用 store 名 + 一条事实（例如「the user uses tabs」）调 `coffer__add_memory`，
- **Then** memory 通过 mem0 被持久化、`memory_records` 表里多一行带 id / store_name / text / created_at、并写入一条审计。

### Scenario: agent searches memories

- **Given** 一个 memory store 内已经有 memory，
- **When** 某个 MCP 客户端用 store 名 + 一条 query 调 `coffer__search_memory`，
- **Then** 返回按相关性排序的 memory 列表，每条带 id、text、score、created_at。

### Scenario: memories persist across daemon restarts

- **Given** 一些 memory 已经写入了某个 store，
- **When** daemon 被停止再重启，
- **Then** 之后的搜索仍能返回先前写入的 memory，无需重新摄入。

### Scenario: agent deletes a single memory

- **Given** 一个 memory store 内已经有 memory，
- **When** 某个 MCP 客户端用一个 memory id 调 `coffer__delete_memory`，
- **Then** memory 从 mem0 中被删除、`memory_records` 中对应行被删掉、写入一条审计、之后的搜索不再返回它。

### Scenario: delete a memory store cleans up everything

- **Given** 一个 memory store 内有 memory + 落盘的 mem0 状态，
- **When** 用户删除该 memory store，
- **Then** 所有 memory 行被清除、`~/.coffer/memory/<name>/` 目录被删除、内存中的任何 mem0 客户端被回收、Resource 行被删除。

### Scenario: list memories in a store

- **Given** 某个 memory store 内有 memory，
- **When** 用户在该 store 中列出 memory（分页），
- **Then** 每条 memory 一行，带 id、text、created_at。

### Scenario: edit a memory

- **Given** 一条 memory 已经存在，
- **When** 用户改它的 text 并保存，
- **Then** 新文本被持久化（重新计算 embedding），审计记录该变更，之后搜索反映新的文本。

### Scenario: clear all memories in a store

- **Given** 某个 memory store 内有 memory，
- **When** 用户跑 `coffer memory clear <store> --yes`，或在 UI 中点「Clear all」，
- **Then** 该 store 内所有 memory 被清掉（行 + mem0 状态），但 store 这个 Resource 本身保留下来。

### Scenario: built-in memory tools appear in client tool list

- **Given** 一个 MCP 客户端接入 coffer 网关，
- **When** 客户端列出 tools，
- **Then** `coffer__list_memory_stores`、`coffer__add_memory`、`coffer__search_memory`、`coffer__delete_memory` 与其它内置工具和上游工具一起出现在清单中。

### Scenario: add_memory returns 503 when LLM provider is none

- **Given** 一个 `llm_provider = "none"` 的 memory store 已经存在，
- **When** 某个 MCP 客户端（或任何外部 surface）对该 store 调 `add_memory`，
- **Then** 调用被拒，返回 503（或对等错误），带 `LLM_NOT_CONFIGURED` 错误码与一条指向配置文档的信息，
- **And** 该 store 的读路径（`list`、`get`、`search`）继续成功，行为不变。

### Scenario: memory text exceeding bound is rejected

- **Given** 一个 `max_memory_chars` 取默认值 8192 的 memory store，
- **When** 调用方对其调 `add_memory`（或 `update`）传入超过 8192 字符的文本，
- **Then** 调用在 API 边界被拒，返回 `MEMORY_REJECTED` 错误（`reason = "too_long"`），任何状态都不被持久化（mem0 不写、`memory_records` 不多行、除了拒绝本身的审计没有别的审计）。

### Scenario: empty memory text is rejected

- **Given** 任意 memory store，
- **When** 调用方对其调 `add_memory`（或 `update`）传入空字符串或纯空白文本，
- **Then** 调用在 API 边界被拒，返回 `MEMORY_REJECTED` 错误（`reason = "empty"`），任何状态都不被持久化。

### Scenario: add_memory surfaces upstream LLM error without corrupting store

- **Given** 一个 memory store 配了 LLM provider，但其 LLM 端点在写入时不可达（或返回错误），
- **When** 调用方对其调 `add_memory`，
- **Then** 调用返回结构化错误（没有部分写、`memory_records` 不留孤儿行、mem0 不留孤儿向量条目），
- **And** 之后对同一 store 再发一次正常的 `add_memory` 仍然成功 —— store 不会停留在退化状态。

> **Deferred to future test work**：以下场景属于用户可见契约的一部分，但它们的测试会跟 e2e 基础设施一起落地，不在本 PR 内。`make verify-acceptance` 不对它们做门禁。
>
> - user adds a memory directly（功能上由 `add_memory` actor="user" 路径覆盖）
> - delete a memory through the UI
> - desktop list view shows memories
> - desktop edit-in-place
> - desktop search box filters
> - CLI list / add / delete（端到端配带 daemon）
> - CLI JSON output for piping
> - per-store metrics（HTTP 路由 —— KB 已有 metrics() service 测试覆盖；以后再 mirror 给 memory）
> - audit records memory lifecycle changes

## Requirements

### Functional Requirements

**Resource lifecycle**

- **FR-001**：系统 MUST 支持新资源 kind `memory`；用户 MUST 能通过既有的 kind-agnostic Resource 框架创建、列出、查看、更新（仅 description 与 `max_memory_chars` —— `llm_provider`、`llm_model`、`llm_endpoint`、`llm_credential_ref`、`embedding_model` 在创建后不可变）、启用、禁用、删除 memory store。
- **FR-002**：系统 MUST 用 Pydantic schema 校验每个 memory store 的配置（embedding 模型、LLM provider 配置、最大 memory 文本长度），拒绝重名，失败时不持久化任何状态。
- **FR-003**：系统 MUST 把每个 memory store 的状态放到 per-store 目录 `~/.coffer/memory/<name>/`。删除时 MUST 同时删掉该目录与对应的 `memory_records` 行。

**Memory lifecycle**

- **FR-004**：用户 / agent MUST 能写入一条 memory（自由文本）。系统 MUST 通过 mem0 持久化它、为它建立检索 embedding，并在 `memory_records` 中记录一行。
- **FR-005**：memory 文本长度 MUST 至少 1 个字符、至多 8192 个字符；非文本内容在 API 边界被拒。
- **FR-006**：用户 / agent MUST 能列出 memory（分页）、按 id 取单条、改一条 memory 的文本、删除单条 memory 或一次清掉某 store 内全部 memory。

**Retrieval**

- **FR-007**：用户 / agent MUST 能用自然语言 query 搜索 memory store，返回排序后的 memory，每条带 id、text、score、created_at。
- **FR-008**：搜索默认返回 top 5；调用方 MAY 指定 1–20 范围内的 `top_k`。

**通过 MCP 集成 agent**

- **FR-009**：Coffer 的 MCP 网关 MUST 暴露内置工具 `coffer__list_memory_stores`、`coffer__add_memory`、`coffer__search_memory`、`coffer__delete_memory`，挂在保留前缀 `coffer__` 下。
- **FR-010**：这些内置 memory 工具 MUST 与 KB 的内置工具及上游 MCP 工具共用同一套调用日志面（`mcp_invocations` 一行，不记参数也不记返回内容，除工具名外）。

**引擎隔离**

- **FR-011**：系统 MUST 把 mem0 关在 `coffer/infrastructure/memory/` 内。Domain 与 application 层 MUST NOT 直接 import mem0 的类型；交互一律通过 `MemoryStore` 端口。
- **FR-012**：如果 mem0 或其 embedding 模型初始化失败，daemon MUST 仍然能起；只有 memory 的读写接口返回 503，错误信息指明缺哪一项依赖。

**LLM provider 配置**

- **FR-013**：系统 MUST 默认不配置 LLM provider；用户 MUST 显式选择在某 memory store 上配本地 Ollama 端点或某个云端 provider key（OpenAI）。（Anthropic 支持推迟到后续规范；加它需要同时改枚举与对应的 mem0 provider 配置。）
- **FR-014**：未配 LLM provider 时，系统 MUST 允许 create / list / search / delete / edit，但 `add_memory` 必须返回 503，并指向配置文档。

**Observability**

- **FR-015**：系统 MUST 围绕 add / search / edit / delete 操作经由 `Tracer` 端口（spec 006「knowledge_base」引入、本规范作为第二个消费者把它提升为共享模块的形态，落在 `application/observability/tracer.py`）发射 trace。

**Surfaces**

- **FR-016**：用户 MUST 能通过 (a) `/api/v1/memory_stores/` 下的 REST API、(b) `coffer memory …` 子命令、(c) 桌面 UI，完成每一项操作。

### Key Entities

- **Memory Store**（kind 为 `memory` 的 resource）：持有一个 store 的配置 —— embedding 模型 id、LLM provider 配置、最大文本长度、description。创建后除 description 外不可变。
- **Memory Record**：一条 memory。由 (store_name, memory_id) 标识。持有 id、text、created_at、updated_at、actor（`agent` / `user`）。
- **Memory Hit**（搜索结果，不持久化）：id、text、score、created_at。

## Success Criteria

### Measurable Outcomes

- **SC-001**：从全新安装开始，用户能在 90 秒内创建首个 memory store 并写入第一条 memory（比 KB 多出来的时间用在 LLM provider 配置）。
- **SC-002**：单个 store 在 200 条 memory 下，典型查询的搜索 wall-clock 延迟 ≤ 500 ms（开发者笔记本）。
- **SC-003**：删除一个 memory store 把其落盘占用与数据库行清得一干二净（100%）。
- **SC-004**：接入 Coffer MCP 网关的编码 agent 能在一次 MCP 会话内通过内置工具完成 add、search、delete。
- **SC-005**：每条 Acceptance Scenario 至少有一个 `acceptance(spec="007-memory", scenario="…")` 标记的测试覆盖。
- **SC-006**：引擎隔离由 importlinter 强制：`coffer.application.*` 与 `coffer.domain.*` 下任何模块都不 import `mem0`。
- **SC-007**：`make verify` 本地与 CI 都过。

## Assumptions

- 用户在自己的机器上跑 Coffer。
- mem0 仍然是一个活跃维护的 Python 包。API 抖动只在 `infrastructure/memory/mem0_store.py` 吸收。
- 若想用本地 LLM（Ollama），用户自己安装并启动 Ollama。Coffer 在文档里给指路，但不打包 Ollama。
- memory store **不是** knowledge base。它装的是短的派生事实；文本最大长度 8 KB。
- 单用户并发量很小。
