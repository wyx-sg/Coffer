# 实施计划：008 — Agent Chat

> English: [plan.md](./plan.md)

**Branch**: `feature/agent-chat`
**Spec**: [./spec.md](./spec.md)
**Status**: Draft

## 概要

交付聊天**平台**及其上的一个 agent。该平台是一个聊天界面、持久化的多对话历史、
一个流式回合协议、一个人工审批通道，以及用户中断 —— 全部针对一个
**agent-provider 注册表**表达，因此第二个 agent 是一个注册表条目，而非一次
重构。所交付的这一个 agent 是内置的 "Coffer Assistant"：一个进程内的 LangGraph
ReAct 循环，运行在用户配置的 LLM 上，使用 Coffer 的 MCP gateway 所聚合的每一个
工具。

本次修订重构了 008 早先一版把内置 agent 硬接进聊天界面的草案。接缝被做实了：
orchestrator、持久化与 wire 契约现在只知道注册表；内置 agent 被重新表达为它背后
的一个 `AgentProvider` + `AgentAdapter`，其外部行为不变。

## 技术背景

| 维度 | 取值 |
|---|---|
| **语言 / 版本** | Python 3.12+，TypeScript 5.x |
| **主要依赖** | `langgraph`、`langchain`、`langchain-anthropic`、`langchain-openai`、`langchain-ollama` —— 限制在 `coffer.infrastructure.chat`（importlinter Contract 9）。本次修订不新增依赖。 |
| **存储** | SQLite `conversations` / `chat_messages` / `chat_models`（Alembic `0005`）。**无迁移** —— 平台重构不新增列。 |
| **测试** | 带 acceptance 标记的 4 层模型。LLM 通过 `FakeChatModel` 伪造；平台接缝以一个 `FakeAgentAdapter` / `FakeAgentProvider` 演练；审批通道由一个 fake provider 证明，其 adapter 会请求审批。 |
| **约束** | LangGraph/LangChain 限制在 `infrastructure/chat`。内置 agent 外部行为不变。DB 或日志中无凭据材料。文件大小 + importlinter 契约成立。 |

## 宪法检查

- **Local-first** —— 对话、消息与审批决策从不离开设备；LLM provider 只是推理
  provider。
- **Spec-as-Truth** —— `spec.md` 先被修订；`contracts/api.openapi.yaml` 是由
  `make verify-contract` 把关的 wire 契约。
- **分层架构** —— `domain/chat` 保持纯净（它只新增了 `ApprovalRequest` frozen
  dataclass）。`application/chat` 定义平台接缝（`AgentAdapter`、`AgentProvider`、
  `ApprovalGate` 端口；注册表与审批通道的具体实现）。`infrastructure/chat` 持有
  LangGraph adapter 与 `BuiltinAgentProvider`。import 方向不变；Contract 9 不变。
- **凭据** —— 模型 API key 仍是运行时解析的凭据引用。

## 平台接缝（冻结契约）

逐字接口见 [data-model.md](./data-model.md)。简而言之：

- **`AgentAdapter.run_turn(*, history, approvals)`** —— 自包含。adapter 携带它
  自己的模型、工具与配置；orchestrator 只注入历史与审批通道。
- **`AgentProvider`** —— `agent_key`、`init_conversation`、`build_adapter`、
  `on_conversation_deleted`、`availability`。扩展的单元。
- **`AgentProviderRegistry`** —— 聊天界面唯一知道的东西。第二个 agent = 在
  composition root 中一次 `registry.register(...)` 调用。
- **`ApprovalGate` / `ApprovalDecision` / `ApprovalRequest`** —— 人工审批通道：
  一个回合发出 `ApprovalRequest`、`await` `approvals.wait(request_id)`，并在一个
  决策被提交时恢复。

## 重构如何保留内置行为

| 关注点 | 之前 | 之后 |
|---|---|---|
| 模型解析 | `TurnOrchestrator.start_turn` | `BuiltinAgentProvider.build_adapter`（在此抛出 `NoModelConfigured`） |
| system prompt + skill 目录 | 在 `TurnOrchestrator._run_turn` 中构建 | 在 `BuiltinAgentProvider.build_adapter` 中构建 |
| 历史裁剪 + 截断提示 | `TurnOrchestrator._run_turn` | 在 `LangGraphBuiltinAgent.run_turn` 内（一个内置 agent 关注点） |
| `run_turn` 输入 | `history, tool_gateway, model, system_prompt` | `history, approvals`（其余在构建时烘焙进 adapter） |
| 工具循环、递归上限、事件映射 | `LangGraphBuiltinAgent` / `_event_mapping` | 未变 |

未变的 008 acceptance 场景 + e2e 是内置 agent 可观察行为未改变的回归证明。

## 项目结构 — 后端

```text
backend/coffer/
├── domain/chat/events.py            # MODIFY  + ApprovalRequest, extend AgentEvent
├── domain/errors.py                 # MODIFY  + UnknownAgent, AgentConfigRejected, ApprovalNotFound
├── application/chat/
│   ├── ports.py                     # MODIFY  ApprovalDecision/Gate, AgentProvider, new AgentAdapter
│   ├── approvals.py                 # CREATE  ApprovalChannel (concrete ApprovalGate)
│   ├── registry.py                  # CREATE  AgentProviderRegistry
│   ├── turn_orchestrator.py         # MODIFY  _ActiveTurn, registry-driven, interrupt_turn, submit_approval
│   └── service.py                   # MODIFY  create→init_conversation, delete→on_conversation_deleted
├── infrastructure/chat/
│   ├── builtin_provider.py          # CREATE  BuiltinAgentProvider (the one registered provider)
│   └── langgraph_agent.py           # MODIFY  run_turn(history, approvals); self-contained adapter
└── surfaces/http/
    ├── chat/schemas.py              # MODIFY  ConversationCreate, + AgentOut/AgentListOut/ApprovalSubmit
    ├── chat/conversation_routes.py  # MODIFY  POST body; + GET /chat/agents
    ├── chat/turn_routes.py          # MODIFY  + POST .../approvals, + POST .../interrupt
    ├── dependencies.py              # MODIFY  + set/get_agent_registry
    ├── wiring.py                    # MODIFY  wire_chat builds registry + BuiltinAgentProvider
    └── errors.py                    # MODIFY  map new error codes
```

未变的后端文件：`domain/chat/{conversation,message,model}.py`、
`application/chat/{system_prompt,history,model_service}.py`、
`infrastructure/chat/{_event_mapping,langchain_models,gateway_tool_provider,
persistence,model_persistence}.py`、`0005` 迁移、`surfaces/cli/*`
（内置 agent 是 CLI 默认值；CLI 忽略未知的 SSE 事件）。

## 项目结构 — 前端

```text
frontend/src/
├── lib/api/chat.ts                  # MODIFY  ConversationCreate; + AgentInfo, listAgents, submitApproval, interruptTurn
├── lib/chat/streamClient.ts         # MODIFY  + ApprovalRequestEvent in the AgentEvent union
├── lib/hooks/useChatTurn.ts         # MODIFY  handle approval_request; expose interrupt() + pendingApproval
├── lib/hooks/useChatAgents.ts       # CREATE  GET /chat/agents query
├── lib/hooks/useConversations.ts    # MODIFY  create body shape
├── components/chat/ApprovalCard.tsx        # CREATE  generic allow/deny card
├── components/chat/NewConversationDialog.tsx # CREATE  agent picker + per-agent config area
├── components/chat/Composer.tsx     # MODIFY  + Stop button while streaming
├── components/chat/MessageThread.tsx # MODIFY  render ApprovalCard; wire interrupt
├── pages/ChatPage.tsx               # MODIFY  new-conversation dialog; interrupt
└── i18n/locales/{en,zh}.json        # MODIFY  agent picker / approval / interrupt keys
```

`NewConversationDialog` 按 `agent_key` 渲染每 agent 的配置区域（内置 → 模型
选择）。它的结构 —— 一个对 agent 类型的 switch —— 正是让一个未来 agent 的配置
区域能够直接落入而无需重做该对话框的关键。

## 测试

- **Unit** —— `test_agent_registry.py`、`test_approval_channel.py`（新）；
  `test_turn_orchestrator_with_fake_adapter.py` 为注册表驱动的 API、中断与审批
  转发而重做 —— 用一个会请求审批的 fake adapter 驱动，这就是 spec 关于审批场景
  的 "fake test adapter" acceptance 证明；`test_chat_service_with_fakes.py` 为
  `agent_key` + `init_conversation` 而重做。`conftest.py` 中的共享 fake 新增
  `FakeAgentProvider` 与 `make_chat_services` 装配辅助。
- **Integration** —— `test_builtin_provider.py`（新 —— `init_conversation`、
  `build_adapter`、`NoModelConfigured`）；`test_langgraph_agent_real`、
  `test_http_routes`（含 agents / approvals / interrupt 路由守卫）、
  `test_composition_root_chat`（通过真实装配的 agent 注册表场景），以及
  `test_delete_cancels_turn` 为新签名而重做。
- **Contract** —— `test_chat_openapi.py` 扩展以涵盖三个新端点。
- **Frontend** —— `ApprovalCard.test.tsx`、`NewConversationDialog.test.tsx`
  （新）；现有的 chat 组件/hook 测试沿用。
- **e2e** —— `chat.spec.ts` 为新对话框 + agent picker 而重做。

`spec.md` 中的每个 acceptance 场景都带一个覆盖性 `acceptance(...)` 标记；
`make verify-acceptance` 报告零未覆盖场景。

## Importlinter 契约

无契约变更。新的 `application/chat` 模块（`registry`、`approvals`）与新的
`infrastructure/chat/builtin_provider` 都位于现有源模块内部；
`BuiltinAgentProvider` 是 composition-root 构建的 adapter，恰如
`LangGraphBuiltinAgent` 在 Contract 9 下已经是的那样。

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| 重构悄然改变内置行为 | 未变的 008 acceptance 场景 + e2e 是回归闸门；`make verify` 必须保持绿色。 |
| `start_turn` 在 one-in-flight 检查上的竞态 | `_ActiveTurn` 在 `TurnInProgress` 守卫之后、任何 `await` 之前，同步地登记进 `_ACTIVE_TURNS`。 |
| 一个被中断的回合重复持久化或挂起 SSE | 回合任务拥有持久化；`finally` 始终入队 end-of-stream 哨兵；中断在 `CancelledError` 路径上恰好持久化一次。 |
| `build_adapter` 的 I/O（skill 获取、模型构建）较晚浮现 | `build_adapter` 在 `start_turn` 中、用户消息持久化之前且任务派生之前运行，因此 `NoModelConfigured` 与 provider 错误作为一个 pre-stream JSON error 返回。 |
| 审批等待在回合无决策结束时泄漏 | 审批 future 绑定到回合任务；中断/取消在 `wait()` 中抛出 `CancelledError`；通道随 `_ActiveTurn` 一并丢弃。 |

## 不在范围内（推迟）

用户创建或用户编辑的 agent；一个管理注册表的 GUI；远程通道；超出 gateway 门控 +
审批通道的每 agent 能力作用域；对话摘要、搜索、导出。见 `spec.md` 的 Assumptions。
