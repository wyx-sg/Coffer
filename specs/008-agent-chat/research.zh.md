# 调研 — 008 Agent Chat

> English: [research.md](./research.md)

针对聊天平台与内置 agent 的设计决策。前三项是本次修订的平台接缝（seam）决策；
其余记录内置 agent 仍然成立的决策。

## 1. 作为接缝的 agent-provider 注册表

**问题**：聊天界面如何在不依赖某个特定 agent 的前提下触达一个 agent？

**决策**：一个回合、一个对话的创建、以及它的拆除，全部通过一个以对话的
`agent_key` 为键的 `AgentProviderRegistry`。orchestrator、持久化层以及 REST/SSE
契约只知道注册表与 `AgentProvider` / `AgentAdapter` 协议。新增第二个 agent 只是
在 composition root 中的一次 `registry.register(provider, display_name)` 调用
—— 无需改动聊天页面、schema 或 wire 契约（SC-007）。

**被否决的备选**：把内置 agent 直接接进 orchestrator，并"以后再加接缝"。未经测试
的接缝不是接缝；只有当第二个 provider 今天就能被加入时平台才是真实的，而
测试中使用的 fake provider 正好证明了这一点。

## 2. 一个自包含的 `AgentAdapter`

**问题**：一个回合交给 agent 的是什么？

**决策**：`run_turn(*, history)` —— 仅此而已。一个 agent 的模型、工具、
system prompt 与配置都是它自己的；它的 provider 在构建 adapter 时注入它们
（`build_adapter`，每回合一次）。一个自带模型与工具（而非 Coffer 配置的模型 +
gateway）的 agent 可以原样接入。历史裁剪移入内置 adapter，因为上下文预算是一个
agent 特定的关注点。

这也重新定位了 `NoModelConfigured`：它由 `BuiltinAgentProvider.build_adapter`
抛出，而该方法在 `start_turn` 内、用户消息被持久化之前被调用，因此一个无模型的
回合仍然作为一个 pre-stream 409 失败。

## 3. 中断 vs. 删除

**问题**：一个回合任务可能因两种原因被取消 —— 如何区分它们？

**决策**：两者都取消该 `asyncio.Task`。它们的区别在 handler 中：

- **中断**（`interrupt_turn`，`POST .../interrupt`）：部分的助手消息（迄今产生的
  文本 + 工具块）以 `status='complete'`、`stop_reason='interrupted'` 持久化，并
  流出一个终结的 `TurnDone`。对话保留该记录并保持可用。
- **删除**（`cancel_turn`，对话删除）：不持久化任何东西 —— 对话行本来就要被移除。

`_ActiveTurn` 记录携带一个 `interrupted` 标志，任务的 `CancelledError` handler
读取它来选择路径。

## 4. agent 配置存储

**问题**：一个 agent 的每对话配置存放在哪里？

**决策**：`agent_config` 在 wire 层与注册表层是不透明的；每个 provider 在
`init_conversation` 中解释并存储它。内置 agent 唯一的配置就是模型，而
`conversations.model_id` 列已经持有它 —— 因此内置 provider 把
`agent_config["model_id"]` 映射到该列，**无需新列或迁移**。一个未来需要更丰富
配置的 provider 自带它自己的表；`init_conversation` 接缝让这一改动保持局部。
因此 `POST /conversations` 接受 `{agent_key, agent_config}`，不再接受顶层的
`model_id`（每回合切换模型仍使用 `PATCH /conversations {model_id}`，这是同一列
上的一个内置 agent 便利功能）。

## 5. agent 框架、多 provider、进程内 gateway（未变）

内置 agent 的循环是 LangGraph `create_react_agent`；LLM 客户端通过 LangChain 的
provider 包构建（`anthropic`、`openai`、`ollama`）；凭据是在运行时解析（解密）的
加密存储引用。该 agent 通过一个 `MCPGatewaySession`（`coffer-builtin-agent`）
进程内地消费 Coffer 的 MCP gateway。所有 LangGraph/LangChain import 都限制在
`infrastructure/chat`（Contract 9）。这些决策从早先的 008 草案原样沿用。

## 6. 对话持久化与流式（未变）

对话、消息与模型是 Coffer 自有的 SQLite 表，而非 Resource。LangGraph 每回合无
状态运行；Coffer 的表是 system of record。回合作为一个分离的 `asyncio.Task` 运行,
将一个 `asyncio.Queue` 排空到一个 `EventSourceResponse`；客户端断连只取消排空。
一次启动清扫会把任何 `streaming` 行翻转为 `failed`。

## 7. 不在范围内

用户创建/编辑的 agent；一个注册表管理 GUI；远程通道；超出 gateway 门控的
每 agent 能力作用域；对话摘要、搜索、导出。
