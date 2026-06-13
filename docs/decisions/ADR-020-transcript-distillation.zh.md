# ADR-020 — Transcript Distillation：读取 Agent 对话记录，写入 Memory 事实

> English: [ADR-020-transcript-distillation.md](./ADR-020-transcript-distillation.md)

- **状态：** 已接受
- **Spec:** [007-memory](../../specs/007-memory/spec.md)（扩展 —— 不分配新 spec 编号）
- **关联：** [ADR-012](./ADR-012-files-as-truth-sqlite-retrieval.md)（files-as-truth + SQLite 检索）、[ADR-013](./ADR-013-agent-native-shared-memory.md)（agent 原生共享 memory）、[ADR-016](./ADR-016-multi-machine-sync.md)（多机同步）、Spec 004（agent 注册表 —— 只读工作区不变量）

## 背景

Coffer agent 通过 MCP `recall`/`remember` 网关与 coding agent（Claude Code、Codex）实时交互。但这些会话还会产生本地对话记录 —— 写在 `~/.claude/projects/` 或 `~/.codex/sessions/` 下的 `.jsonl` 文件 —— 其中可能包含耐久性的工程决策、项目约定、失败路径和待办事项，这些内容从未被显式记录为 memory 事实。这些机构知识会在会话之间丢失，对其他 agent 和机器不可见。

我们希望挖掘这些知识，同时避免：
- 持久化原始对话内容（其中包含密钥、工具调用载荷、文件内容和命令输出），
- 写入外部 agent 自己的会话存储（Coffer 不应拥有或破坏它），
- 引入新的顶层规范（输出是 memory 事实，完全受现有 Spec 007 不变量约束）。

## 决策

将 **transcript distillation**（对话记录提炼）能力作为 Spec 007 Memory 的扩展加入。它分三个只读摄取步骤执行：

1. **读取** —— `TranscriptReaderPort` 适配器从已注册 agent 的工作区配置目录（如 Claude Code 的 `~/.claude/projects/`、Codex 的 `~/.codex/sessions/`）读取 `.jsonl` 文件。这与 Spec 004 基于许可列表的配置文件读取方式一致：只读、不写。

2. **清洗与提炼** —— 提取自然语言对话轮次（用户 + 助手文本）；丢弃所有 `tool_use`/`tool_result` 块、文件内容段落和命令输出。通过一次性 LLM 调用（经现有 `build_chat_model` 基础设施）向模型传入经清洗的对话，返回一个结构化洞察的 JSON 数组，类型为 `decision`、`gotcha`、`convention` 或 `todo`。

3. **写入事实** —— 每条提炼出的洞察经 `InsightSinkPort` → `MemoryService` 写入，成为项目作用域的 memory 事实（Spec 007 `MemoryFact`，`actor="agent"`，`origin_session_id` 设为对话记录的会话 id）。原始对话内容不会进入事实正文。

跨 agent 共享和跨机同步是自然的后果：memory 事实已通过 MCP `recall` 网关共享（Spec 007），并通过 git 同步（Spec 010 / ADR-016）。无需新增任何基础设施。

### 架构 —— 自包含的 `distill` 切片

新增一个 `distill` 切片横跨全部四层
（`domain/distill/`、`application/distill/`、`infrastructure/distill/`、
`surfaces/http/distill/`），**仅通过在组合根处连线的端口**（`surfaces/http/wiring.py`）与 `agent` 和 `memory` 切片通信。这是唯一可以跨 kind 边界 import 的地方（满足 import-linter Contract 5）。`application/distill/` 中的应用层代码不得 import `application.agent`、`application.memory` 或任何 `infrastructure.*` 模块。

### 不变量

- **不持久化原始对话。** 解析时丢弃 `tool_use`/`tool_result` 块、文件内容和命令输出。只有清洗后的自然语言文本传给 LLM，只有提炼出的事实被存储。
- **永不写入外部 agent 的会话存储。** Coffer 在此流程中读取 `~/.claude/` 和 `~/.codex/`，但绝不向其写入。Spec 004 的只读不变量完全保留。
- **每条事实携带来源信息。** 每条提炼事实带有 `origin_session_id`（对话记录的会话 id）和 `actor="agent"`，其自动化来源可被审计。
- **送达 LLM 前先清洗密钥。** 消息文本先经正则表达式清洗器处理，识别并脱敏常见密钥模式（API 密钥、令牌、私钥块），并截断超长文本块，之后才传给 LLM。
- **防御性解析。** Claude Code 和 Codex 的 `.jsonl` 格式无文档且不稳定。各 agent 的读取适配器（`parse_claude_code`、`parse_codex`）跳过未知行，对单条坏记录从不抛出异常。生态研究发现：没有主流 agent 会通过共享介质持久化或同步原始对话记录；跨 agent 共享的主流模式是共享提炼后的 memory。

## 考虑过的备选方案

### 备选方案 A —— 新增 hub 资源类型：`conversation` / `transcript`

将完整（或经清洗的）对话记录作为新的 Coffer resource kind 存储，经 Spec 010 git 同步，让 agent 直接查询对话语料库。

**已否决。** 原始对话记录体积庞大，包含密钥、工具调用载荷和文件内容。ADR-012 的 files-as-truth 模型以及路线图中明确的非目标（「工具调用参数或结果的持久化」）均禁止持久化工具调用内容。通过用户的 git 仓库（ADR-016）同步数 MB 的 JSONL 文件会使历史记录膨胀、污染 diff。agent 生态中没有人通过用户自控的 git 仓库同步原始对话记录；主流的跨 agent 共享模式是共享提炼后的 memory。引入新 kind 还需要 UI、API、迁移和契约工作，而这些工作产生的用户价值并不比已可通过 `recall` 查询的提炼事实多。

### 备选方案 B —— 在 Agent Chat 页（Spec 008）添加本地对话记录浏览器

在现有 Spec 008 Agent Chat 页中新增一个 tab，列出历史会话，允许用户浏览或通过将历史轮次重新注入新会话来「继续」对话。

**v1 阶段已否决。** 对用户而言，持久价值在于提炼出的知识进入 memory，而非对历史对话的回放。浏览/继续功能是一个不同问题（会话恢复）上的叠加工作，在生态中没有牵引力。它不影响本 ADR，如有用户需求可独立添加。

### 备选方案 C —— 写回外部 agent 的会话存储

将提炼出的洞察作为新条目直接持久化到 `~/.claude/` 或 `~/.codex/`，使 coding agent 能在其自身历史中原生「看到」提炼出的事实。

**已否决。** 这将违反 Spec 004 的只读不变量：「内部状态文件只读，绝不写入。」它还需要逆向工程各 agent 的写入格式（无文档且可能变更），写入格式错误的条目可能损坏用户真实的 agent 历史。正确的注入通道是 MCP `recall` 网关（已就位）和原生投影（Spec 007 FR-012/FR-013），而非直接写入 agent 自己的会话存储。

## 后果

- 新增 `distill` 切片横跨全部四层；它仅依赖自身的 Protocol 端口（在 `wiring.py` 中连线），保持 import 契约干净。
- 新增两条 HTTP 路由：`GET /api/v1/agents/{name}/transcripts`（列出会话）和 `POST /api/v1/agents/{name}/transcripts/distill`（执行提炼）。契约声明在 `specs/007-memory/contracts/transcripts.openapi.yaml`。
- `coffer transcript list|distill` CLI 子命令提供脚本化访问。
- 前端在 Agent 详情页新增「Conversations」tab（一键将某次会话提炼进 memory）。
- 不分配新 spec 编号。Spec 007 的用户故事、验收场景和功能需求在原有文件中就地扩展。
- 对话记录 `.jsonl` 格式无文档；各 agent 的适配器标记为防御性实现，当 agent 厂商发布稳定格式或发生破坏性 schema 变更时，需相应更新。
