# ADR-013：LangGraph 作为内置 agent 引擎，置于 AgentRuntime port 背后

> English: [ADR-013-langgraph-builtin-agent-engine.md](./ADR-013-langgraph-builtin-agent-engine.md)

**Status**: Accepted
**Date**: 2026-06-01
**Deciders**: Yuxing Wu
**Related**: spec `008-builtin-agent-chat`（FR-004、FR-006、FR-008、SC-006），spec `001-mcp-gateway`（agent 消费的那个 MCP 网关），[ADR-007](ADR-007-everything-is-a-resource-kind.md)

## Context

Spec `008-builtin-agent-chat` 给 Coffer 自己一个 agent —— 一个真正的 LLM 循环，它
必须 (a) 能跟用户配置的任何主流 provider 工作（Anthropic、OpenAI、本地 Ollama、
…），(b) 实时流式吐 token 输出和工具调用，(c) 消费 Coffer 自己的 MCP 网关工具，于
是 agent 能用 vault 管理的每一个 MCP server / skill / knowledge base / memory，以
及 (d) 暴露一个点，让 Coffer 能拦截工具执行、对敏感工具暂停下来做人在环确认。

Coffer 的 constitution 要求分层架构：domain 和 application 层不带重型第三方引擎；这
类依赖只住在 `infrastructure/` 里、置于一个 port 背后。我们选的任何 agent 引擎都带
来一棵很大的依赖树，所以引擎必须可被收束。

同一个 chat 界面还必须把**外部**被管理 agent（`claude_code`、`codex`）作为本地无头
子进程来驱动。所以 chat/会话层需要单一抽象，内部 LLM 循环和外部子进程都能满足它 ——
它绝不能被绑死在驱动内置 agent 的那个引擎上。

## Decision

**内置 agent 的 LLM 循环用 LangGraph 实现，收束在
`coffer/infrastructure/chat/builtin_runtime.py` 内，只通过 application 层定义的一个
`AgentRuntime` port 触及。** 一个 `CompositeRuntimeFactory` 按会话目标的 kind 在
LangGraph 内置 runtime 和子进程 external-agent runtime 之间做选择；两者实现同一个
port，于是 `ChatService` 与引擎无关。

具体地：

- **与 provider 无关的 model 解析。** `builtin_agent` config 带一个单独的 provider
  限定 `model` 字符串（例如 `anthropic:claude-sonnet-4-6`）。runtime 把它交给
  LangChain 的 `init_chat_model`，于是切换 provider 是一次 config 编辑、不改 Coffer
  代码。凭据从 keychain（`credential_ref`）解析，回退到 provider 约定的环境变量；缺
  key 时在任何东西被持久化之前抛 `LlmNotConfigured`（→ 503）。
- **工具调用循环。** `langgraph.prebuilt.create_react_agent` 提供循环；
  `astream_events` 产出 token delta、tool start、tool end，runtime 把它们映射到
  port 的 `RuntimeEvent` 流。
- **网关工具。** `langchain-mcp-adapters`（`MultiServerMCPClient`）用 daemon token
  连到 Coffer 自己在 `127.0.0.1` 上的 `/mcp` endpoint，把网关变成 LangChain 工具，
  由 `use_gateway` 开关把控。
- **确认那条缝。** 因为 Coffer 拥有工具 callable，名字匹配 `confirm_tools` 的工具被
  包一层，使其在运行前发出一个 `ConfirmationRequest` 并 await 一个批准/拒绝决定 ——
  这就是人在环的保证（SC-005）。
- **隔离。** LangChain/LangGraph 在 **`stream` 内部惰性 import**，于是 import
  runtime 模块或在启动时装 factory 永远不需要引擎被安装。importlinter
  **Contract 7**（`forbidden`，源 `coffer.domain` + `coffer.application`，禁止
  `langgraph` / `langchain*`）强制引擎绝不泄出 infrastructure，支撑 SC-006。

## Consequences

**正面**

- 一个 config 字段切换 provider；没有按 provider 的集成代码。
- LangGraph 的循环 + `astream_events` + `langchain-mcp-adapters` 白送 streaming、
  工具调用、MCP 工具消费，于是 Coffer 只写到它 port 的映射。
- `AgentRuntime` port 让 chat 层对内置和外部 runtime 是同一套，并让我们以后能加更多
  runtime 而不动 `ChatService`。
- 引擎变动在一个模块里消化；代码库其余部分 —— 以及 CI 的分层检查 —— 永远看不到
  LangChain。
- 确认那条缝是 Coffer 在内置 runtime 里拥有工具执行的自然结果。

**负面**

- 一棵很重的依赖树（`langgraph`、`langchain`、`langchain-core`、各 provider 适配
  器、`langchain-mcp-adapters`）进入后端。由收束 + 惰性 import + importlinter 契约
  缓解。
- LangChain 的 API 类型很松；内置 runtime 需要对那个模块做一个 mypy override。
- LangChain/LangGraph 的 API 变动是真实的；我们接受只在 `infrastructure/chat/` 里消
  化它。
- 确认强制只对内置 runtime 强；v1 里外部 agent 在它们自己的权限策略下运行（CLI
  permission 钩子被推迟）。

## Alternatives Considered

**直接用裸 provider SDK（Anthropic / OpenAI / Ollama 客户端）。** 被拒。

- 我们将重新实现工具调用循环、流式归一化、按 provider 的消息成形，然后维护一个不断
  增长的 provider 集成集合，并为每个手搓 MCP 工具管线。
- 唯一的好处 —— 没有 LangChain 依赖 —— 已被「把引擎收束在 port 背后的一个模块里」抵
  消。

**LlamaIndex agents。** 被拒。

- 它的强项是检索/索引工作流；Coffer 的 knowledge base 是它们自己的 kind，不需要
  LlamaIndex 的索引内核。
- 它的 agent + streaming + MCP 工具叙事对一个通用工具调用 chat 循环的契合度不如
  LangGraph，却仍然需要同一套 port + 隔离纪律 —— 同样的约束下杠杆更小。

**把 chat 层直接绑到所选引擎（不要 port）。** 被拒。

- 这会把 external-agent 子进程 runtime 变成二等公民，并违反分层架构约束，把一个重型
  引擎泄进 application 代码，让 SC-006 所要求的 importlinter 契约无法成立。
