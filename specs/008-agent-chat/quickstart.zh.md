# 快速上手 — Coffer Agent Chat

> English: [quickstart.md](./quickstart.md)

> **注（[ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.zh.md)）。**
> 下文描述的 **Coffer Assistant** 聊天人格已退场。聊天现在**只**与 Coffer 受管
> agent（Claude Code、Codex）对话，页面标签为 **Chat（聊天）**（而非 _Vault Console
> 金库控制台_）。本地模型不再是聊天 agent；它驱动内部 `coffer__*` 能力——语义化的
> `coffer__search_tools` 与对你知识/记忆的 `coffer__ask` agentic-RAG 工具。下文描述的是
> 早先的内置 agent 聊天流程，保留作历史参考。

Chat 页面让你与 **Coffer Assistant** 对话 —— 这是 Coffer 的内置 agent。
该 agent 可以使用你 vault 中的一切：你的 MCP server 工具、你的记忆库、
你的知识库以及你的 skills。

## 1. 配置一个 LLM connection

Coffer 的内部引擎需要一个 LLM。打开 **Settings → LLM Connections** 并添加一个：

| Provider       | 你需要提供                                                             |
| -------------- | ---------------------------------------------------------------------- |
| Anthropic      | model id（例如 `claude-sonnet-4-6`）+ API-key 凭据                     |
| OpenAI         | model id（例如 `gpt-4o`）+ API-key 凭据                                |
| Ollama（本地） | model id（例如 `llama3.1`）+ base URL（例如 `http://localhost:11434`） |

把其中一条 connection 标记为**内部引擎默认**，让 Coffer 自身的引擎在其上运行。
云端 connection 通过一个凭据引用来引用它的 API key；先存储 key 本身，再注册指向
它的 connection。在命令行中：

```bash
# 1. 把 API key 以一个引用名存入加密的凭据存储。
coffer credentials set anthropic-api-key     # 从 stdin 读取密钥
# 2. 注册一个从该引用解析其凭据的 connection。
coffer provider add sonnet --wire anthropic \
  --base-url https://api.anthropic.com \
  --model claude-sonnet-4-6 --credential-ref anthropic-api-key
# 3. 把它设为 Coffer 的内部引擎默认。
coffer provider internal-default sonnet
coffer provider list --json
```

API key 以密文形式存储在 Coffer 的加密凭据存储中，connection 配置里只保留凭据引用
—— 明文 key 从不接触数据库。

## 2. 开始聊天

打开 **Chat** 页面（位于侧边栏顶部）。点击 **New conversation**，在对话框中
选择一个 agent —— Coffer 内置了 **Coffer Assistant**，即它的内置 agent ——
然后确认。输入一条消息，agent 就会逐 token 流式回复。

向它询问需要用到你 vault 的问题，例如：

> What do my memory notes say about OAuth?

agent 会调用匹配的工具（`coffer__recall`、`coffer__search_knowledge`、
`coffer__load_skill`，或你的任意 MCP server 工具）。每次调用都会在对话线程中
以一张内联卡片出现，你可以展开它查看输入与结果。

## 3. 管理对话

对话历史是 Chat 页面的左侧栏（可折叠）。创建新对话、在它们之间切换、重命名
或删除。一切都本地存储在 SQLite 中，并在重启后保留。

## 4. 按对话切换模型

如果你配置了多个模型，对话顶栏中的模型选择器可以改变该对话使用的模型。该选择
从下一个回合起生效；每条回复都会记录产生它的模型。

## 5. 从命令行聊天

```bash
coffer chat -m "say hello"        # 单回合，打印回复
coffer chat                       # 交互式多回合会话
```

CLI 对话与桌面应用展示的是同一批对话。

## 对话保留（含一条升级说明）

对话遵循一个两阶段生命周期，两个窗口都可在 **Settings → Data** 中配置：

1. **自动归档闲置对话** —— 一段时间（默认 **7 天**）没有新消息的对话会被归档
   （它离开活跃列表，但不会被销毁）。
2. **删除已归档对话** —— 已归档的对话（及其消息）会在**归档之后**配置的天数
   （默认 **30 天**）被删除。

任一窗口都可设为*关闭*以停用该阶段。活跃对话（从未归档）永远不会被删除阶段删除。

> **升级说明（行为变更）。** 早期版本按*最后活动时间*删除对话（单阶段）。现在的
> 生命周期是上面的两阶段模型：删除窗口从*归档时刻*起算，而非最后活动时间，并新增了
> 独立的自动归档窗口。升级时，遗留的单阶段保留设置会被重置为新默认值（归档 7 天 +
> 删除 30 天）；你此前*已禁用*的设置会保持禁用。如果你之前自定义过对话保留，升级后
> 请到 **Settings → Data** 重新确认。这是安全的：新的删除阶段只会移除*已归档*的
> 对话，因此该变更不会删除任何活跃对话。

## 幕后发生了什么

- 对话与消息是 Coffer SQLite 数据库中的行 —— 而非 Resource。它们是界面产物，
  不是被配置的 vault 资产。
- 内置 agent 运行一个进程内的 LangGraph 循环，并通过 Coffer 自己的 MCP gateway
  访问你的工具，因此每次工具调用都会经过 gateway 的能力门控与调用日志。
- 每条助手消息都会记录 token 用量并显示在回复下方。每个完成的**回合**都会以
  actor `agent` 记录在 `coffer audit list` 中；单次**工具调用**则记录在 MCP
  gateway 的调用日志中（归属于该 agent 的 gateway session），而不是审计日志。

## 故障排查

**"No model configured"** —— 在你于 Settings → LLM Connections 添加一条 connection
并将其标记为内部引擎默认之前，Chat 页面会一直显示此提示。配置好后，聊天输入框便会解锁。

**回合因 provider 错误失败** —— 检查模型的凭据，对 Ollama 还要检查 base URL
是否可达。对话仍可使用；重新发送该消息即可。

**agent 没有使用你预期的工具** —— 确认相关的 MCP server、记忆库或知识库已启用；
被禁用的能力不会提供给 agent。
