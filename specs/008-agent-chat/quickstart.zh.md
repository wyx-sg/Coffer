# 快速上手 — Coffer Agent Chat

> English: [quickstart.md](./quickstart.md)

Chat 页面让你与 **Coffer Assistant** 对话 —— 这是 Coffer 的内置 agent。
该 agent 可以使用你 vault 中的一切：你的 MCP server 工具、你的记忆库、
你的知识库以及你的 skills。

## 1. 配置一个模型

内置 agent 需要一个 LLM。打开 **Settings → Models** 并添加一个：

| Provider | 你需要提供 |
|---|---|
| Anthropic | model id（例如 `claude-sonnet-4-6`）+ API-key 凭据 |
| OpenAI | model id（例如 `gpt-4o`）+ API-key 凭据 |
| Ollama（本地） | model id（例如 `llama3.1`）+ base URL（例如 `http://localhost:11434`） |

你添加的第一个模型会成为默认模型。云端模型通过一个凭据引用来引用它的 API
key；先存储 key 本身，再注册指向它的模型。在命令行中：

```bash
# 1. 把 API key 以一个引用名存入加密的凭据存储。
coffer credentials set anthropic-api-key     # 从 stdin 读取密钥
# 2. 注册一个从该引用解析其凭据的模型。
coffer model add --name "Sonnet" --provider anthropic \
  --model claude-sonnet-4-6 --credential-ref anthropic-api-key
coffer model list --json
```

API key 以密文形式存储在 Coffer 的加密凭据存储中，模型配置里只保留凭据引用
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

## 幕后发生了什么

- 对话与消息是 Coffer SQLite 数据库中的行 —— 而非 Resource。它们是界面产物，
  不是被配置的 vault 资产。
- 内置 agent 运行一个进程内的 LangGraph 循环，并通过 Coffer 自己的 MCP gateway
  访问你的工具，因此每次工具调用都会经过 gateway 的能力门控与调用日志。
- 每条助手消息都会记录 token 用量并显示在回复下方。每个完成的**回合**都会以
  actor `agent` 记录在 `coffer audit list` 中；单次**工具调用**则记录在 MCP
  gateway 的调用日志中（归属于该 agent 的 gateway session），而不是审计日志。

## 故障排查

**"No model configured"** —— 在你于 Settings → Models 添加模型之前，Chat 页面
会一直显示此提示。添加一个，聊天输入框便会解锁。

**回合因 provider 错误失败** —— 检查模型的凭据，对 Ollama 还要检查 base URL
是否可达。对话仍可使用；重新发送该消息即可。

**agent 没有使用你预期的工具** —— 确认相关的 MCP server、记忆库或知识库已启用；
被禁用的能力不会提供给 agent。
