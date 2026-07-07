# ADR-040：重新放宽 agent 注册表（opencode、hermes、cursor；openclaw 走独立轨道）

> English: [ADR-040-re-widen-agent-registry.md](ADR-040-re-widen-agent-registry.md)

**状态**：Accepted
**日期**：2026-07-08
**决策者**：Yuxing Wu
**相关**：spec `004-agent-registry`（FR-003 + FR-003a 能力矩阵）；spec `008-agent-chat`（FR-005a agent providers）；spec `011-provider-switching`（原生配置投影）；反转数据迁移 `0031_drop_removed_agent_types`；基于 [ADR-032](ADR-032-provider-switching.md)（`env_key` 投影缝）与 [ADR-037](ADR-037-rules-runtime-injection.md)（SessionStart 注入）

## 背景

2026 年 6 月的一次简化把 Coffer 收窄到恰好两种受管 agent 类型（`claude_code`、`codex`），并**删除**了曾以 `enabled=False` 存在的 `cursor` / `opencode` / `openclaw` / `hermes` 枚举值。数据迁移 `0031_drop_removed_agent_types` 移除了这些类型的持久化行；agent 的 `type` 在 DB 层**没有约束**（agent 存在通用 `resources` 表里、以 `config_json.type` 记录），所以这次收窄只是代码 + 数据层面的。

用户现在希望 Coffer 管理更多编码 agent——**opencode**、**hermes**、**cursor**——每个都要有与 Claude Code / Codex 相同的能力面（聊天、MCP 注入、session-context/规则注入、provider 投影、原生记忆关闭、config 文件管理、发现）。这反转了那次简化。注册表本就是为此设计的：每类型的行为都由能力清单（`AGENT_DESCRIPTORS`）承载，聊天面读取 agent-provider 注册表（spec 008），所以加一个 product 就是加数据——当其 wire 协议是新的时，再加一个 chat-provider adapter。

调研这四个被删 product 后有三个事实决定了本决策：

1. **opencode、hermes、cursor 是叶子编码 CLI**——和 Claude Code、Codex 一样，Coffer 驱动一个、管理一套 config。它们套得进 manifest。
2. **两个能力 gap 是真实且属于上游**，不是 Coffer 的 bug：
   - **opencode 没有 shell 命令生命周期 hook**——只有进程内 JS 插件回调（`session.created` / `session.idle`）。Coffer 的 SessionStart-hook 注入（[ADR-037](ADR-037-rules-runtime-injection.md)）无法表达"落一个 JS 插件文件"，那是另一种机制，不是 `HookInjectionSpec` 的放宽。
   - **cursor 锁死 Cursor 自己的后端**、不暴露自定义 LLM base URL，所以 Coffer 无法把自己的 LLM 连接（spec 011）投影进去。
3. **openclaw 不是叶子编码 CLI。** 它是一个对等网关，自己编排 Claude Code / Codex / OpenCode，自带多 agent 路由、持久记忆、MCP host、hooks、channels。Coffer 的"注入 MCP + 注入 session hook + 驱动一轮"模型套不上它——那些层活在 openclaw 自己拥有的 config 里，会与 Coffer 冲突。

## 决策

**把 `opencode`、`hermes`、`cursor` 重新加为受管 agent 类型**，每个都是一条 `AgentDescriptor` 记录（config 目录、config 文件白名单、MCP 注入形状，以及它支持的可选 hook / provider 投影 / 原生记忆 facet），当 wire 协议是新的时再加一个注册在与 Claude Code / Codex 同一缝里的 chat-provider adapter。交付采用**按 agent 竖切**（一个 agent 一个端到端 PR），按 adapter 风险从低到高：opencode → hermes → cursor。

**能力 gap 建模为"缺席的 descriptor facet"，而非错误。** product 上游缺某个 facet 就不设它；服务优雅降级（例如对 opencode 请求关闭原生记忆返回 `NATIVE_MEMORY_DISABLE_UNSUPPORTED` / 422，界面隐藏该开关），逐 agent 的支持在 spec 004 的**能力矩阵**（FR-003a）里列出。具体：opencode 首个 slice 不带 session-hook 注入（其 plugin-drop 是记录在案的后续 slice）、也不带原生记忆关闭（它没有跨会话原生记忆）；cursor 不带 provider 投影（上游无自定义 base URL）。

**openclaw 不作为受管叶子 agent 加回。** 它是对等控制面。唯一自洽的集成是把它的网关当作 OpenAI 兼容的模型端点（`openclaw gateway` + `POST /v1/chat/completions`，`model: "openclaw/<agentId>"`），这是 LLM-连接 的事、不是 agent 注册表的事。留给**独立设计轨道**；本 ADR 记录它为何不在注册表内。

无需新的数据库迁移——agent 的 `type` 没有 DB 层约束，重新加回枚举值即可恢复对这些类型的接受；`0031` 删除的行不予恢复（那些行本就不可用、其 config 无法重建，与 `0031` 给出的理由一致）。

## 影响

- manifest 缝被二次验证：加一个叶子 agent 是一条 descriptor 记录（+ 可选 chat adapter），聊天面、持久化、wire 契约都不变（spec 008 SC-007）。
- opencode 复用 JSON config 机器；它引入一个新的 `McpEntryStyle`（`TYPED_LOCAL_OBJECT`，opencode 的 `{type, command[], enabled}` 形状），以及一个 `opencode.json` 的 `provider` 块投影，其 `apiKey` 引用 `COFFER_PROVIDER_KEY`——与 Codex 相同的环境注入缝（[ADR-032](ADR-032-provider-switching.md)）。
- hermes 将引入 YAML config 处理（它的 `config.yaml` 承载 MCP + hooks + memory）和一个原生记忆关闭目标；它的 hook 对齐度最高（`on_session_start` / `on_session_end`，JSON stdin/stdout，类似 Claude）。
- cursor 带着一个记录在案的对齐缺口交付（无 provider 投影）；其 chat adapter 解析 Cursor 的 `stream-json` NDJSON。
- 各界面须读能力矩阵（缺某 facet 的 agent 隐藏该操作）。前端的 `Record<AgentType, …>` 映射会强制补上新键。

## 备选方案

- **保持两类型下限。** 用户否决——他们要更多受管 agent 且全对齐。
- **按功能横切**（先注册所有类型，再逐能力层铺到所有 agent）。否决：太晚才可用，且一个坏 adapter 会阻塞每个 agent；按 agent 竖切每个 PR 交付一个可用 agent，也符合 Coffer 的 one-spec-per-scope SDD。
- **把 openclaw 当叶子编码 agent。** 否决：架构不匹配——它的 MCP/hook/memory 层是自己的、会与 Coffer 重复或冲突；把它当 OpenAI 兼容端点驱动是唯一自洽路径。
- **新开一个伞形 spec（012-multi-agent）。** 否决：这些关注点已有 owner spec（004 注册表/facet、008 聊天、011 投影）；变更分配进它们，而非在新 spec 里重复。
