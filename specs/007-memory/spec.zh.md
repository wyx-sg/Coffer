# 功能规范：Memory（跨 agent 共享记忆）

> English: [spec.md](./spec.md)

**Feature Branch**: `feature/kb-memory-redesign`
**Created**: 2026-05-22
**Status**: Accepted (redesign — in development)
**Input**: Coffer memory feature 的重设计 —— 与 knowledge base（spec 006）共用同一套统一底座（unified substrate）的 **memory 面**。memory 不再是「写入时调 LLM 的 mem0 向量库」；它变成 **跨 agent 的单一真相源**（没有各 agent 间互相漂移的副本），在格式匹配处做到 agent 原生。规范化存储 = 每条事实一个 markdown 文件，加上一个 `MEMORY.md` 索引 —— 即 Claude Code 的 auto-memory 格式 —— 放在 `~/.coffer/memory/` 下，并带两层作用域（global + per-project）。agent 通过 Coffer 的 MCP 网关读写；规范化文件还会 **投影（projection）** 进各 agent 的原生位置（Claude Code 用目录 symlink，Codex 用 `AGENTS.md` 中带标记栅栏的 managed block）。用户在 Coffer UI 里做完整 CRUD。检索复用与 knowledge base 相同的引擎（grep / keyword FTS5+BM25 / vector sqlite-vec）。完整设计依据见 [ADR-012](../../docs/decisions/ADR-012-files-as-truth-sqlite-retrieval.md) 与 [ADR-013](../../docs/decisions/ADR-013-agent-native-shared-memory.md)。

## 用户场景与测试

### User Story 1 —— 一份记忆，所有 agent 共享（优先级 P1）

开发者上午用 Claude Code、下午用 Codex 在同一个项目上工作。用 Claude Code 时 agent 学到「这个 repo 通过 `make release` 发版，绝不直接 `git push --tags`」，并通过 Coffer 的 `coffer__remember` 工具记下来。下午 Codex —— 另一个 agent —— 召回了同一条事实，因为两个 agent 读写的是 **同一个共享 store**，而且这条事实还被投影进各 agent 的原生记忆位置。没有任何副本漂移。

**为什么是这个优先级**：这是本次重设计的核心。各 agent 之间互相漂移的私有 silo 正是要解决的问题；没有单一真相源就没有这条 feature。

**独立可测**：从全新安装开始，在一个 git 项目里跑 MCP 客户端，调 `coffer__remember` 写一条项目事实，再用第二个 MCP 客户端（不同 agent 身份）在同一项目里调 `coffer__recall`，看到该事实被召回。确认该事实也出现在项目的规范化 `MEMORY.md` 中。

**代表性场景**：

- agent 记住一条项目事实
- agent 召回一条项目事实
- recall 跨 project 与 global 两个作用域
- agent 更新一条事实
- agent 遗忘一条事实
- 内置记忆工具出现在客户端工具列表
- embedding 未配置时 vector recall 回退

---

### User Story 2 —— 全局与每项目记忆（优先级 P1）

有些事实是关于开发者本人、到处都成立的（「偏好 tabs 而非 spaces」）；有些只关乎某个 repo（「这个服务的 API base path 是 `/api/v2`」）。开发者希望全局事实在每个项目都可用、项目事实只限本项目，而 `recall` 默认两者都返回。

**为什么是这个优先级**：把个人偏好和项目专属事实混在一起会污染 recall，还会把 repo 细节泄露到别的项目。两层作用域是这个共享 store 可信的前提。

**独立可测**：用 `scope=global` 记一条、用 `scope=project` 记一条。从另一个项目 recall 只返回全局那条；在原项目 recall 两条都返回。

**代表性场景**：

- 在 global 作用域 remember
- agent 记住一条项目事实
- project 作用域由 agent 的工作目录解析得到
- recall 跨 project 与 global 两个作用域

---

### User Story 3 —— 投影进各 agent 的原生位置（优先级 P1）

开发者保持 Claude Code 的 auto-memory 开启。Coffer 让项目的规范化记忆目录 **就是** Claude 的项目记忆（一个目录 symlink），于是 Claude 自己的编辑就是规范化内容、并对所有其它 agent 即时可见。对 Codex，Coffer 把同一批事实渲染进 `AGENTS.md` 里带标记栅栏的 managed block，并禁用 Codex 原生 `memories`，使第二份副本不会累积。

**为什么是这个优先级**：投影是让记忆「agent 原生」而非「又一个需要叮嘱 agent 去用的 MCP store」的关键。没有它，这个共享 store 其实并没有真正共享进 agent 自己的界面。

**独立可测**：把一个项目绑到 Claude Code；确认 `~/.claude/projects/<slug>/memory/` 是指向规范化目录的 symlink，且经由 symlink 编辑一条事实能被 `coffer__recall` 返回。再绑到 Codex；确认 `AGENTS.md` 多出一个含这些事实的 `<!-- coffer:memory:start -->…<!-- coffer:memory:end -->` block，且 Codex `memories` 被禁用。

**代表性场景**：

- 项目记忆以 symlink 投影进 Claude
- 全局记忆向 Codex AGENTS.md 渲染 managed block
- 经由 Claude symlink 的编辑在 recall 中可见
- 重新渲染 managed block 是幂等的
- 已存在的原生记忆文件被合并、绝不覆盖

---

### User Story 4 —— 用户在 Coffer 里维护记忆（优先级 P2）

开发者要看见并纠正 agent 记下的东西：按作用域浏览事实、改一条漂移的、手动加一条、删掉一条错的 —— 全在 Coffer UI 或 CLI 里完成。

**为什么是这个优先级**：没有人工维护的记忆让人不放心；agent 偶尔会记错。能维护，这条 feature 才足够安全到可以一直开着。

**独立可测**：agent 写了若干事实后，打开记忆视图，改一条事实的文本并保存，观察下一次 `recall` 返回改后的版本。加一条事实（actor=user），再删另一条，观察它从磁盘和 recall 中消失。

**代表性场景**：

- 用户添加一条事实
- 用户编辑一条事实
- 用户删除一条事实
- 写入一条事实会重新生成 MEMORY.md

---

### User Story 6 —— 将 agent 历史对话中的洞察提炼进共享 memory（优先级 P2）

开发者已用 Claude Code 在某个项目上工作了数周。那些会话中讨论并确定了大量工程决策、失败路径和项目约定，但从未被显式记录为 memory 事实。开发者运行 `coffer transcript distill claude_code --project /repo`（或在 Coffer UI 中点击「提炼进 memory」）。Coffer 读取本地 `.jsonl` 对话记录文件，清洗工具调用载荷和密钥，请 LLM 提取耐久性洞察，并将它们写为项目作用域的 memory 事实。此后，任何 agent —— 包括第二台机器上的 Codex —— 都能通过 `coffer__recall` 召回这些事实，因为 memory 是共享的（Spec 007）且已同步（Spec 010）。原始对话内容从不被存储或传输。当对话记录的工作目录能解析到某个 git 项目时，提取的事实写入该项目作用域的记忆 store；若路径不在任何 git 工作树内，则回退写入全局记忆 store。

**为什么是这个优先级**：agent 在本地对话记录中积累了机构知识，这些知识原本孤立于每个会话、对其他 agent 不可见。提炼是挖掘这些知识最无侵入性的机制：它产出标准 memory 事实，免费继承跨 agent 共享和多机同步能力。它是 P2 而非 P1，因为核心共享 memory 流程（Story 1–3）必须先就位 —— 提炼是在其之上叠加的能力。完整决策依据和被否决的备选方案见 [ADR-020](../../docs/decisions/ADR-020-transcript-distillation.zh.md)。

**独立可测**：在某个 agent 配置目录下至少有一条 Claude Code 或 Codex 对话记录的项目里，运行 `coffer transcript distill <agent> --project <path> --dry-run`，观察到至少一条洞察被打印出来，但没有任何事实被写入磁盘。然后不带 `--dry-run` 再运行，通过 `coffer memory recall <store> "<topic>"` 确认：至少一条提炼事实现在可被召回，携带 `actor="agent"` 和非空的 `origin_session_id`，且不包含工具调用载荷、文件内容或疑似密钥的字符串。

**代表性场景**：

- distill transcript to memory

---

### User Story 5 —— 查看并重置记忆（优先级 P3）

开发者想知道每个作用域累积了多少记忆，并能在不删除 store 的前提下清空某个作用域。

**为什么是这个优先级**：卫生级别；不挡核心流程。

**独立可测**：查看 per-store 度量（事实条数、磁盘字节）。清空 project 作用域；确认所有事实都没了但 store 保留下来、随时可装新事实，且投影重新渲染为空。

**代表性场景**：

- 清空一个记忆作用域

（per-store 度量的 HTTP 路由由独立可测覆盖，但其专属 acceptance 测试延后 —— 见场景后的说明。）

---

### Edge Cases

- **请求 vector 但 embedding 未配置**：`recall` 带 `mode=vector` 时回退到 keyword，并在响应里标注此次回退；它从不阻塞。默认检索是 keyword+grep（零配置、离线）。
- **Claude 记忆目录里已经有真实文件**：首次投影时 Coffer 先把这些文件合并进规范化 store，再把该目录替换成 symlink —— 绝不静默覆盖。
- **Claude 改写了 `MEMORY.md`**：无害 —— 下次写入或 recall 时 Coffer 会幂等地从事实 frontmatter 重新生成 `MEMORY.md`。
- **直接在磁盘上编辑事实文件**：下一次 `recall` 会惰性扫描这个小事实目录、找出增量并重建索引，因此带外编辑会被拾取，无需 watcher。
- **空事实文本**：在 API 边界被拒；不写任何内容。
- **事实文本过长**：在 API 边界按 `max_fact_chars`（默认 8192）约束；写入前即被拒。
- **project 作用域无法解析**：若 agent 的工作目录不在某个 git 项目里，`scope=project` 被拒并给出清晰错误；`scope=global` 仍然可用。
- **某 agent 没有投影（`projection_mode = NONE`）**：记忆仍可经 MCP 完整工作；只是跳过原生投影。

## Acceptance Scenarios

每条场景至少对应一个被 `@pytest.mark.acceptance(spec="007-memory", scenario="…")` 打了标记的测试。

### Scenario: agent remembers a project fact

- **Given** 一个跑在 git 项目内的 MCP 客户端，
- **When** 它用一条事实加 `scope=project` 调 `coffer__remember`，
- **Then** 在项目记忆目录下写出一个每条事实的 markdown 文件（YAML frontmatter `name`/`description`/`metadata.type`/`origin_session_id` + 正文），重新生成 `MEMORY.md`，将该文件索引进 `documents`，并写入一条审计。

### Scenario: agent recalls a project fact

- **Given** 一个有事实的项目记忆 store，
- **When** 某 MCP 客户端用一条 query 调 `coffer__recall`，
- **Then** 返回排序后的事实，每条带 id、text、score、source、time，且在搜索前已惰性扫描事实目录、拾取任何带外增量。

### Scenario: recall spans project and global scope

- **Given** global 与 project 两个作用域都存在事实，
- **When** 某 MCP 客户端不带 scope 调 `coffer__recall`，
- **Then** 结果同时取自项目 store 与 global（sentinel）store。

### Scenario: remember at global scope

- **Given** 一个 MCP 客户端，
- **When** 它用 `scope=global` 调 `coffer__remember`，
- **Then** 该事实写入由 `project_id = WORKSPACE_GLOBAL_PROJECT_ID` 标识的 global store，且从任何项目 recall 都能返回它。

### Scenario: project scope resolves from the agent's working directory

- **Given** coffer-mcp-shim 在会话握手时上报其启动 cwd，
- **When** daemon 解析项目记忆 store，
- **Then** 它计算该 cwd 的 git-root，并解析（缺失则惰性置备）由该项目 ULID 标识的 per-project store。

### Scenario: agent updates a fact

- **Given** 一条事实已存在，
- **When** 某 MCP 客户端用事实 id 与新文本调 `coffer__update_memory`，
- **Then** 规范化 markdown 被重写、文档被重建索引、`MEMORY.md` 被重新生成，且 recall 反映新文本。

### Scenario: agent forgets a fact

- **Given** 一条事实已存在，
- **When** 某 MCP 客户端用事实 id 调 `coffer__forget`，
- **Then** markdown 文件被删除、其索引行被移除、`MEMORY.md` 被重新生成、投影重新渲染，且 recall 不再返回它。

### Scenario: project memory projects into Claude as a symlink

- **Given** 一个绑到 Claude Code agent 的项目，
- **When** 建立投影，
- **Then** `~/.claude/projects/<slug>/memory/` 是指向规范化项目记忆目录的目录 symlink，且 Claude auto-memory 保持开启。

### Scenario: edits through the Claude symlink are visible on recall

- **Given** 一个 symlink 进 Claude 的项目记忆 store，
- **When** 经由 symlink 路径编辑某个事实文件，
- **Then** 下一次 `coffer__recall` 返回编辑后的内容（惰性 reindex-on-read），且没有任何文件系统 watcher 在跑。

### Scenario: global memory renders a managed block into Codex AGENTS.md

- **Given** global 层的一个 Codex agent，
- **When** 投影运行，
- **Then** `~/.codex/AGENTS.md` 含一个持有已渲染事实的 `<!-- coffer:memory:start (managed, do not edit) -->…<!-- coffer:memory:end -->` block，标记之外的内容不被触碰，且 Codex 原生 `memories` 被禁用。

### Scenario: re-rendering a managed block is idempotent

- **Given** 一个已带 managed block 的 `AGENTS.md`，
- **When** 事实未变而投影再次运行，
- **Then** 文件内容逐字节相同（幂等渲染）。

### Scenario: existing native memory files are merged, never overwritten

- **Given** 绑定前 Claude 的项目记忆目录里已经有真实事实文件，
- **When** Coffer 建立投影，
- **Then** 这些文件先被合并进规范化 store，然后该目录被替换为 symlink —— 没有任何文件被静默覆盖。

### Scenario: user adds a fact

- **Given** 一个记忆 store，
- **When** 用户经 Coffer UI 或 CLI 添加一条事实，
- **Then** 写出 `metadata.actor = "user"` 的规范化 markdown，重新生成 `MEMORY.md`，索引该文档，并写入一条审计。

### Scenario: user edits a fact

- **Given** 一条事实已存在，
- **When** 用户改它的文本并保存，
- **Then** 规范化 markdown 被重写、文档被重建索引，且 recall 反映新文本。

### Scenario: user deletes a fact

- **Given** 一条事实已存在，
- **When** 用户删除它，
- **Then** markdown 文件与其索引行被移除、`MEMORY.md` 被重新生成，且 recall 不再返回它。

### Scenario: writing a fact regenerates MEMORY.md

- **Given** 任意写入者（agent、Claude 或用户）写入或移除一条事实，
- **When** 写入完成，
- **Then** `MEMORY.md` 从事实 frontmatter 重新生成为 `- [name](file.md) — description`，幂等地覆盖此前内容。

### Scenario: clear a memory scope

- **Given** 一个有事实的记忆 store，
- **When** 用户清空该作用域，
- **Then** 每个事实文件与其索引行被移除、`MEMORY.md` 变空、投影重新渲染为空，但 store 这个 Resource 保留。

### Scenario: built-in memory tools appear in client tool list

- **Given** 一个 MCP 客户端接入 coffer 网关，
- **When** 客户端列出 tools，
- **Then** `coffer__recall`、`coffer__remember`、`coffer__update_memory`、`coffer__forget`、`coffer__list_memory` 与其它内置工具及上游工具一起出现。

### Scenario: vector recall falls back when embedding is unconfigured

- **Given** 一个未配置 embedding provider 的记忆 store，
- **When** 用 `mode=vector` 调 `coffer__recall`，
- **Then** 调用返回 keyword 结果并在响应里标注此次回退（绝不报错）。

### Scenario: distill-transcript-to-memory

- **Given** 一个已注册的 agent，且其本地对话记录目录下至少有一个含自然语言对话轮次的 `.jsonl` 文件，
- **When** 调用 `POST /api/v1/agents/{name}/transcripts/distill`（或 CLI 中的 `coffer transcript distill <agent>`），且 `dry_run=false`，
- **Then** 对话记录被读取，工具调用载荷和密钥在 LLM 调用前被清洗，LLM 返回结构化洞察，每条洞察被写为项目作用域的 memory 事实，携带 `actor="agent"`、`origin_session_id=<对话记录会话 id>`，且 `type` ∈ `{decision, gotcha, convention, todo}`；任何已持久化事实中均不出现原始对话内容；`coffer__recall` 此后返回这些新事实；当 `dry_run=true` 时，洞察被返回但不向磁盘写入任何内容。

> **Deferred to future test work**（测试随 e2e 基础设施落地；`make verify-acceptance` 不对它们做门禁）：桌面记忆列表按作用域展示、桌面就地编辑、`coffer memory …` CLI 端到端配带 daemon、per-store 度量（HTTP 路由）。

## Requirements

### Functional Requirements

**存储与作用域**

- **FR-001**：系统 MUST 把每条记忆事实存为一个每条事实的 markdown 文件，带 YAML frontmatter（`name`、`description`、`metadata.type`、`metadata.actor`、`origin_session_id`）加 markdown 正文，并配一个重新生成的 `MEMORY.md` 索引。markdown 文件是 **唯一真相源**；SQLite 是可重建的索引。
- **FR-002**：系统 MUST 支持两种记忆作用域：**global**（一个由 `project_id = WORKSPACE_GLOBAL_PROJECT_ID`（既有 sentinel `00000000000000000000000000`）标识的 store）与 **per-project**（每项目一个、由项目 ULID 标识的 store），分别存于 `~/.coffer/memory/global/` 与 `~/.coffer/memory/projects/<project-ulid>/`。
- **FR-003**：系统 MUST 在每次 write/update/delete 时幂等地重新生成 `MEMORY.md`（`- [name](file.md) — description`，由事实 frontmatter 派生），覆盖此前内容。
- **FR-004**：系统 MUST 从 agent 在会话握手时上报的启动 cwd 解析 per-project store：daemon 计算 git-root，并解析（缺失则惰性置备）该项目 ULID 对应的 store。

**事实生命周期**

- **FR-005**：agent 与用户 MUST 能直接写入一条事实（写入时不调 LLM）。事实文本 MUST 至少 1 个字符、至多 `max_fact_chars`（默认 8192）；空或超长在 API 边界被拒，不持久化任何内容。
- **FR-006**：用户与 agent MUST 能列出事实（按作用域）、按 id 取单条、改一条事实的文本、删除单条事实、清空某作用域全部事实。清空保留 store 这个 Resource。
- **FR-007**：每条事实带 `metadata.actor`（`agent` | `user`）与可选的 `metadata.type`（如 `project` / `feedback` / `reference` / `user`）；由写入者设定。

**检索**

- **FR-008**：recall MUST 使用与 knowledge base 共享的统一检索引擎：`grep`（真实服务 —— ripgrep 扫该 store 的事实文件；对 FTS5 无法分词的内容必不可少，如 CJK）、`keyword`（FTS5 BM25，默认）、`vector`（sqlite-vec 配可配置的 embedding provider）。当请求 `vector` 但未配置 embedding provider 时，recall MUST 回退到 `keyword` 并以布尔值在响应里标注此次回退 —— 绝不阻塞。MCP `coffer__recall` 的响应包含该 `fallback` 布尔值。
- **FR-009**：`coffer__recall` MUST 默认跨 project 与 global 两个 store（显式给出 `scope` 时收窄到单个 store：`project` = 仅项目 store，`global` = 仅 global store）；跨 store 的结果用倒数排名融合（reciprocal rank fusion）合并（逐 store 的分数跨模式/跨 store 不可比；每条命中保留其逐 store 分数，只有合并后的顺序来自融合）。结果带 id、text、score、source、time —— `time` 是事实的 `updated_at`，`source` 是 `<scope>:<fact file path>`。默认 `top_k` 为 5；调用方 MAY 指定 1–20。
- **FR-010**：memory MUST 用 **lazy reindex-on-read**：`recall` 先按内容哈希扫描事实目录的增量（新增/变更/删除文件）并对账索引，再搜索，使带外编辑（含 Claude 的 symlink 编辑）即时可见，无需文件系统 watcher。

**投影与绑定**

- **FR-011**：`AgentMemoryAdapter`（随 agent driver 而非 memory kind）MUST 声明 `projection_mode` 为 `SYMLINK`、`RENDER` 或 `NONE`，投影引擎 MUST 据此分派。新增一个 agent MUST 只需新增一个 adapter —— 不改动 memory 底座。
- **FR-012**：对 Claude Code，project 层 MUST 把规范化项目记忆目录作为 **目录 symlink** 投影进 `~/.claude/projects/<slug>/memory/`（双向；auto-memory 保持开启）。若那里已存在真实记忆目录，Coffer MUST 先把其文件合并进规范化 store，再替换为 symlink —— 绝不静默覆盖。
- **FR-013**：对 Codex，Coffer MUST 把事实渲染进 `<project>/AGENTS.md`（project 层）与 `~/.codex/AGENTS.md`（global 层）中带标记栅栏的 managed block `<!-- coffer:memory:start (managed, do not edit) -->…<!-- coffer:memory:end -->`，MUST 不触碰标记之外的内容，MUST 幂等重渲染，并 MUST 禁用 Codex 原生 `memories`，使第二份副本不累积。
- **FR-014**：adapter（agent 层）MUST 执行所有原生文件改动；memory 底座 MUST 只提供规范化文件加已渲染 markdown，保持 memory 与 agent 无关、L1 config 边界干净。

**通过 MCP 集成 agent**

- **FR-015**：Coffer 的 MCP 网关 MUST 暴露内置工具 `coffer__recall(query, scope?, mode?, top_k?)`（`mode` ∈ `grep` | `keyword` | `vector`）、`coffer__remember(text, scope?, type?)`、`coffer__update_memory(id, text)`、`coffer__forget(id)`、`coffer__list_memory(scope?)`，挂在保留前缀 `coffer__` 下。`remember` 默认 `scope=project`；`recall` 默认两个作用域。
- **FR-016**：这些内置 memory 工具调用 MUST 共用既有调用日志面（`mcp_invocations` 一行：工具名 + who/when/duration/outcome，不记参数也不记返回内容）。

**Surfaces**

- **FR-017**：用户 MUST 能通过 (a) `/api/v1/memory_stores/` 下的 REST API、(b) `coffer memory …` 子命令、(c) 桌面 UI 完成完整记忆 CRUD。用户写入设 `metadata.actor = "user"`，写规范化 markdown、重新生成 `MEMORY.md`、重建索引并审计。这些 surface 上的 store 名会被校验：只有 `global` 或 `project-<26 字符 ULID>` 合法 —— 形状合法的名字会惰性 provision 其 store；其余返回 404（`MEMORY_STORE_NOT_FOUND`）。

**底座隔离**

- **FR-018**：检索/索引引擎（FTS5、sqlite-vec、embedding provider、converter）MUST 关在 infrastructure 内。Domain 与 application 层 MUST NOT 直接 import 索引/引擎类型；交互一律经共享检索端口。mem0、chroma、LlamaIndex MUST NOT 在任何地方被 import。

**迁移**

- **FR-019**：本分支未发布；**没有数据迁移**。单个迁移 MUST 删除 `memory_records` 并创建全新统一 schema。预发布构建遗留在磁盘上的旧引擎目录（chroma/LlamaIndex）原地废弃 —— 没有任何代码再读它们 —— 而非删除。旧的 mem0/chroma 文本不迁移。

**投影 surface**

- **FR-020**：投影 MUST 经 REST 管理：`GET /api/v1/memory_stores/{name}/projections` 列出某 store 的绑定，`POST /api/v1/memory_stores/{name}/projections` 建立绑定（先把已存在的原生文件合并进规范 store —— 绝不覆盖），`DELETE /api/v1/memory_stores/{name}/projections/{agent_ref}` 移除绑定。移除 MUST 撤销原生目标（删 symlink / 剥除受管块）；若撤销失败，绑定行被**保留**（确保原生产物不会被永久遗弃）且错误向上抛出以便重试。每次建立/移除 MUST 写一条 `memory_projected` 审计事件。对 Claude Code，GLOBAL 层经 RENDER 受管块投影进 `~/.claude/CLAUDE.md`（project 层是 FR-012 的 SYMLINK）。

### Key Entities

- **Memory Store**（kind 为 `memory` 的 resource）：每个作用域一个 store —— global store（sentinel ULID）或 per-project store（项目 ULID）。config 持有启用的检索模式、embedding 配置与 `max_fact_chars`。
- **Memory Fact**（一个 markdown 文件 = 一行 `documents`）：`id`、`name`、`description`、正文、`metadata`（`type`、`actor`、`origin_session_id`）、`path`、`content_sha256`、`created_at`、`updated_at`。markdown 文件是真相源。
- **Memory Hit**（recall 结果，不持久化）：`id`、`text`/passage、`score`、`source`、`time`。
- **Projection**（每 agent × 作用域）：一个 `projection_mode`（`SYMLINK` | `RENDER` | `NONE`）加上 adapter 所拥有的原生目标路径。

## Success Criteria

### Measurable Outcomes

- **SC-001**：某 agent 经 `coffer__remember` 写入的事实，能在同一项目、同一会话内被另一个 agent 经 `coffer__recall` 召回，且没有任何 per-agent 副本漂移。
- **SC-002**：经 Claude 项目记忆 symlink 编辑的事实，能在下一次 `coffer__recall` 被返回，且没有任何文件系统 watcher 在跑。
- **SC-003**：某作用域 200 条事实下，典型 keyword query 的 recall wall-clock 延迟 ≤ 300 ms（开发者笔记本）。
- **SC-004**：默认检索零配置离线可用（keyword + grep）；vector recall 为可选项，未配置时降级到 keyword（带标注），绝不报错。
- **SC-005**：新增一个 agent 的投影只需一个新的 `AgentMemoryAdapter`，不改动 memory 底座（由 adapter 分派测试验证）。
- **SC-006**：每条 Acceptance Scenario 至少有一个 `acceptance(spec="007-memory", scenario="…")` 标记的测试覆盖。
- **SC-007**：底座隔离由 importlinter 强制：`coffer.application.*` 与 `coffer.domain.*` 下任何模块都不 import 索引引擎，且 `mem0`/`chroma`/`llama_index` 任何地方都不被 import。
- **SC-008**：`make verify` 本地与 CI 都过。

## Assumptions

- 用户在自己的机器上跑 Coffer；记忆数据留在本地。为可选的 vector recall 调用已配置的云端 embedding provider 是允许的（local-first ≠ 不调远程 API）。
- 规范化格式即 Claude Code 的 auto-memory 格式，采用它使 Claude 投影为原生 symlink。
- coffer-mcp-shim 在会话握手时把其启动 cwd 传给 daemon（在支持的 agent 上实现期验证）。
- knowledge base（spec 006）与 memory 共用一套统一底座（`documents` 表按 `kind` + JSON `metadata` 区分）；二者是两个面，不是重复代码。
- 单用户并发量很小。
