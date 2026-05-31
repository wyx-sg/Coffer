# 研究 — 008 Built-in Agent & Chat

> English: [research.md](./research.md)

内置 agent 与 chat 界面背后的背景和备选方案。承重的引擎决策记在
[ADR-013](../../docs/decisions/ADR-013-langgraph-builtin-agent-engine.md)。

## 为什么要给 Coffer 自己一个 agent

在 spec 008 之前，Coffer 只是*管理*外部 agent —— 它存它们的 config、把它的 MCP
网关装进它们，但它自己从不跑 LLM。一个内置 agent 让 Coffer 吃自己 vault 的狗粮：
它能调用网关暴露的每一个 MCP server / skill / knowledge base / memory 工具，不需要
任何外部 CLI。它也给非开发者用户一个开箱即用的 chat 界面（一旦配好 provider key）。
external-agent runtime 让既有的被管理 agent 也能从同一个 chat 界面使用，于是用户有
一个地方跟两者都能聊。

## 为什么内置 runtime 用 LangGraph

我们需要一个 agent 循环：(a) 能跟任何主流 provider 工作，(b) 支持流式 token 输出和
工具调用，(c) 能消费 MCP 工具，(d) 给我们一个地方拦截工具执行以做人在环确认。

**LangGraph**（选中）：

- `init_chat_model` 解析一个 provider 限定的 model 字符串（`anthropic:…`、
  `openai:…`、`ollama:…`、…），于是 `model` config 字段是切换 provider 唯一需要动
  的开关 —— Coffer 里没有按 provider 的代码。
- `create_react_agent` 给出一个现成的工具调用循环；`astream_events` 把 token
  delta、tool start、tool end 作为统一事件流暴露出来，我们把它映射到 `AgentRuntime`
  port。
- `langchain-mcp-adapters`（`MultiServerMCPClient`）把 Coffer 自己的 `/mcp` 网关变
  成 LangChain 工具，于是 agent 通过用 daemon token 连 `127.0.0.1` 拿到整套 vault
  工具集。
- 工具执行留在 Coffer 控制下（agent 调用一个我们拥有的 Python callable），这正是我
  们给 confirm 列表里的工具设门禁所需的那条缝。

代价是一棵很重的依赖树。我们通过把 LangChain / LangGraph 限制在
`infrastructure/chat/builtin_runtime.py`、并在 `stream` 内惰性 import 来消化它，于
是代码库其余部分 —— 以及启动 wiring —— 永远不需要引擎可被 import。importlinter
Contract 7 强制这道边界。

### 备选方案

**直接用裸 provider SDK（Anthropic / OpenAI / Ollama 客户端）。** 被拒。

- 我们将自己重新实现工具调用循环、流式归一化、按 provider 的消息成形，然后维护 N
  个 provider 集成。
- MCP 工具管线要按 provider 手搓。
- 唯一的好处（没有 LangChain 依赖）被「把引擎限制在 port 背后的一个模块里」抵消。

**LlamaIndex agents。** 被拒。

- 在检索/索引工作流上很强，但它的 agent + streaming + MCP 工具叙事对一个通用工具调
  用 chat 循环的契合度不如 LangGraph，而我们并不需要它的索引内核（Coffer 的
  knowledge base 是它们自己的 kind）。
- 仍然需要同一套 port + 隔离纪律，杠杆却更小。

## 与 provider 无关的 model 解析

`model` config 字段是单个 provider 限定字符串，例如 `anthropic:claude-sonnet-4-6`。
runtime 在第一个 `:` 处切出 provider，然后把整个字符串交给 `init_chat_model`。凭据：

- 云端 provider（`anthropic`、`openai`）需要 key。runtime 通过 `credential_ref` 从
  keychain 解析它，回退到 provider 约定的环境变量（`ANTHROPIC_API_KEY`、
  `OPENAI_API_KEY`）。两者都没有时，它在**任何消息被持久化之前**抛
  `LlmNotConfigured`，于是 API 干净地返回 `503 LLM_NOT_CONFIGURED`。
- 本地 provider（`ollama`）无需 key；没有 key 不是错误。

可选的 `temperature` / `max_tokens` 只在设置了时才透传，否则用 provider 自己的默认。

## 外部 agent 的无头调用

Coffer 通过以无头 streaming 模式把被管理外部 agent 的 CLI 作为本地子进程拉起、并把
stdout 映射成 runtime 事件来驱动它们。按 agent 类型：

- `claude_code` → `claude -p <prompt> --output-format stream-json --verbose`；
  runtime 读 `stream-json` 的 assistant 块并发出它们的文本。
- `codex` → `codex exec --json <prompt>`。

二进制从一个显式 override（`COFFER_CHAT_BIN_<TYPE>`）或 `PATH` 解析；缺二进制以一个
结构化的 `UPSTREAM_UNAVAILABLE` 错误浮现（assistant 消息被标记为 `failed`），而不
是崩溃。每个 agent 在它注册的 `config_dir` 下运行（经 `CLAUDE_CONFIG_DIR` /
`CODEX_HOME` 传入），于是它看到 Coffer 已经装进它的那个 MCP 网关。子进程始终被回收
—— 正常结束、出错、停止、daemon 关闭时 —— 于是不留孤儿进程（SC-003）。

行映射器刻意宽容：它处理一个 `{"text": …}` 形状（我们的 stub）、Claude Code
`stream-json` assistant 块、以及一个纯文本回退，并忽略未知的控制 JSON。`cursor` 以
及其他没有文档化无头 streaming 模式的类型，在本规范里不作为 chat 目标。

## 确认方式

目标：用户标记为敏感的工具，没有显式批准绝不运行（SC-005），且一个没被回应的确认绝
不破坏 store。

- **内置 runtime（Coffer 控制执行）。** 每个名字匹配该 agent `confirm_tools` glob
  的网关工具被包一层。当 agent 调用它时，包装器发出一个 `ConfirmationRequest` 事件
  （工具名 + 参数）并 await 一个决定 future，而不是运行。
  `ChatService.resolve_confirmation` 解析那个 future：批准则运行原工具并返回结果；
  拒绝则向 agent 返回一个「declined」字符串，于是它优雅继续。Stop 把所有待处理
  future 解析为拒绝。这是强保证那条路径。
- **external-agent runtime。** Coffer 不控制 agent 的工具执行，所以确认只在 agent
  CLI 暴露了 permission-prompt 钩子的地方强制；否则 agent 在它自己配置的权限策略下
  运行（并向用户呈现）。v1 里 external runtime 的 `resolve_confirmation` 是 no-op，
  且它们的 `confirm_tools` 为空。接通一个 CLI permission 钩子被推迟。

### 确认备选方案

**对整轮做飞前批准（批准一次，然后随意跑）。** 被拒 —— 太粗；一轮可能在好几个安全
工具之后才走到一个敏感工具，而用户想要按工具控制。

**只用策略阻断（直接拒掉敏感工具、不提示）。** 被拒 —— 抹掉了人在环的价值；用户明确
想要批准/拒绝。

## 持久化形状

会话和消息是控制面数据，所以它们住在 SQLite（不是文件）。消息用一个 autoincrement
的 `seq` 主键做会话内稳定排序，加一个唯一 `mid` 做 domain id；tool call 作为一个嵌
在消息里的 JSON 摘要数组存（仅名字 + 截断的参数/结果摘要 —— 绝不存完整 payload ——
对齐网关 invocation-logging 纪律）。streaming delta 是瞬态的：只有最终确定的
assistant 内容和 tool-call 元数据被持久化，于是重启返回历史而不重跑任何一轮。

## 自动标题

在一个占位标题会话的第一轮 user/assistant 往返之后，生成一个短标题。一个
`TitleGenerator` port 可以从这次往返产出一个；若它缺失或失败，标题回退为截断后的首
条 user 消息（首行，截上限）。标题生成永远不阻塞、不让这一轮失败 —— 它在 finalize
路径里运行、错误被吞掉。
