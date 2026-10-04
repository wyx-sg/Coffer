---
title: MCP 工具参考
description: Coffer 内置的 coffer__ 工具、它们的输入 schema 和返回结果、上游工具如何命名，以及网关在握手时告诉智能体什么。
---

# MCP 工具参考 {#mcp-tools-reference}

本页说明智能体连接到 Coffer 的 MCP 端点时看到的内容：内置 `coffer__*` 工具及其确切的输入
schema 和返回结果，Coffer 聚合的上游工具、资源和提示词的命名规则，以及 Coffer 在
`initialize` 握手时返回的说明文字。它面向针对 Coffer 编写提示词、技能或集成的人。
网关内部如何运作，见 [MCP 网关](/zh/architecture/mcp-gateway)。

## 一览 {#at-a-glance}

| 工具 | 用途 | 何时存在 |
| --- | --- | --- |
| [`coffer__search_tools`](#coffer-search-tools) | 按意图对上游工具目录排序。 | 始终存在。 |
| [`coffer__ask`](#coffer-ask) | 向所有者提问并等待回答。 | 仅在 Coffer 运行的对话轮次内。 |

完整列表就这两个。Coffer 的知识、记忆笔记和它自己的记录都没有对应工具：
智能体用自己的文件工具修改和读取知识与记忆，用 `coffer` 命令行读记录。见
[不用工具处理知识、记忆和日志](#memory-and-logs-without-a-tool)。

::: tip 智能体里的名称
Coffer 以名为 `coffer` 的 MCP 服务器装进智能体的配置，所以大多数客户端会在这些工具前面加上
自己的前缀。比如在 Claude Code 里，`coffer__search_tools` 显示为 `mcp__coffer__coffer__search_tools`。
:::

## 内置工具如何应答 {#how-built-in-tools-answer}

每个内置工具都返回标准的 MCP `CallToolResult`：

- 成功时，`content` 包含一个 `text` 条目，内容是序列化为 JSON 的结果，
  `structuredContent` 放同一个对象。`isError` 为 `false`。
- 工具本身失败时（缺少参数、未知的知识集），结果为 `isError: true`，并带一个包含错误信息的
  `text` 条目，模型读到后可以修正调用。Coffer 自己写的错误信息原样传出；其他任何异常都只保留
  类名，这样不会泄露任何上游内容或密钥。
- 协议层面的问题（未知的工具名、格式错误的请求）则返回 JSON-RPC 错误。

每次调用，无论成败，都会和上游调用一起记入 MCP 调用日志，服务器 uid 为保留值 `coffer`。
见[活动与审计](/zh/guides/activity)。

网关还会注入两个不在任何公开 schema 里的参数：

| 参数 | 规则 |
| --- | --- |
| `agent` | 总是由网关设为打开该会话的智能体名称（来自 shim 的 `--agent-uid`）。客户端发来的值会被丢弃。仅用于标注审计条目。 |
| `cwd` | 对 schema 中声明了 `cwd` 属性的工具，如果客户端没有发送，就用会话的启动目录填上。 |

## coffer\_\_search\_tools {#coffer-search-tools}

按意图搜索聚合后的上游 MCP 工具目录，返回最相关的工具定义。受预算限制的 `tools/list`
没有列出的工具，就用它来找：返回的每个工具都能按名称调用，无论有没有被列出。排序是确定性的
BM25，依据每个工具的服务器、名称和描述。Coffer 自己的 `coffer__*` 工具不会出现在结果里。
搜索范围是会话生效范围内所有服务器的完整目录；没有应答的服务器会被跳过。

始终存在。背景：[MCP 网关](/zh/architecture/mcp-gateway)。

### 输入 {#input}

| 属性 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `query` | string | 是 | | 你想做什么，用自然语言或关键词。 |
| `top_k` | integer | 否 | `5` | 返回多少个工具。限制在 1–20 之间。 |

### 结果 {#result}

```json
{
  "tools": [
    {
      "name": "jira__jira_get_issue",
      "description": "Get details of a specific Jira issue.",
      "inputSchema": { "type": "object", "properties": { "issue_key": { "type": "string" } }, "required": ["issue_key"] },
      "score": 7.4213
    }
  ],
  "total_searched": 138
}
```

### 调用示例 {#example-call}

```json
{
  "jsonrpc": "2.0",
  "id": 10,
  "method": "tools/call",
  "params": {
    "name": "coffer__search_tools",
    "arguments": { "query": "read a jira ticket", "top_k": 3 }
  }
}
```

## coffer\_\_ask {#coffer-ask}

在任务进行中向所有者提问并等待。这一轮对话暂停；问题显示在[对话](/zh/guides/chat)页面
（对由[渠道](/zh/guides/channels)驱动的对话，还会作为卡片发到聊天里）；所有者在任一处回答、
停止任务，或过了 24 小时，调用才返回。它的形状与 Claude Code 自己的 `AskUserQuestion` 一致，
在 Coffer 对话里 Coffer 会把后者变成同样的问题。

它是**按轮次限定**的：Coffer 为每个它运行对话轮次的智能体进程设置一个随机的
`COFFER_TURN_TOKEN`；shim 把它作为 `X-Coffer-Turn` 头发出，网关只在头里指向一个当前正在运行的轮次的会话中列出
`coffer__ask`。在终端里启动的智能体永远看不到它，直接调用会得到「coffer__ask 只能在 Coffer 对话内使用」
（`isError: true`）。因此握手说明和内置服务器页面都不提这个工具。Coffer 写进 Codex `config.toml` 的
`coffer` 条目会透传该变量（`env_vars`），并允许一次工具调用运行一整天（`tool_timeout_sec = 86400`）。

### 输入 {#input-1}

| 属性 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `context` | string | 否 | 显示在问题上方的 Markdown：摘要、diff、路径。 |
| `questions` | array | 是 | 一到四个问题。 |

每个问题：

| 属性 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `header` | string | 是 | 简短标签。 |
| `question` | string | 是 | 问题本身。 |
| `options` | array | 是 | 两到四个选项，每个 `{label, description?}`。同一问题内标签不重复。 |
| `multi_select` | boolean | 否 | 允许所有者选多个。默认 `false`。 |

所有者始终可以输入自己的回答，而不选选项。

### 结果 {#result-1}

```json
{
  "answered": true,
  "answers": [
    { "header": "Apply", "question": "Apply this change to staging?", "selected": ["Yes"], "text": null }
  ]
}
```

`selected` 是选中的标签，`text` 是所有者自己输入的话（二者可以有一个为空，但不会同时为空）。
没有得到回答时（所有者停止了任务，或过了 24 小时），结果是 `{"answered": false, "message": "…"}`。
格式不对的提问会以 `isError: true` 失败，并附上要修正的内容。

## 上游名称 {#upstream-names}

Coffer 把会话生效范围内每个已启用的 [MCP 服务器](/zh/guides/mcp-servers)的工具、资源和提示词
重新暴露出来，并以服务器名称作为命名空间，所以两个服务器永远不会撞名：

| 能力 | 形式 | 示例 |
| --- | --- | --- |
| 工具 | `<server>__<tool>` | `jira__jira_get_issue` |
| 提示词 | `<server>__<prompt>` | `github__summarize_pr` |
| 资源 URI | `coffer://<server>/<original-uri>` | `coffer://docs/file:///guide.md` |
| 内置工具 | `coffer__<tool>` | `coffer__search_tools` |

分隔符是双下划线，名称在第一个双下划线处拆分：服务器名称从不包含 `__`，上游工具名称可以包含。
`coffer__` 前缀保留给 Coffer 自己的工具。

服务器名称一经注册就固定下来，因为它是上面每个工具名的前缀，而智能体的权限规则和技能都会引用这些名称。
服务器没有单独的显示标题；想换名字，就删掉服务器重新注册。服务器名称最多 24 个字符。见
[MCP 服务器](/zh/guides/mcp-servers)。

### 客户端可见的名称长度 {#client-visible-name-length}

客户端会加上自己的前缀，所以智能体看到的是 `mcp__coffer__<server>__<tool>`。模型提供商的 API
拒绝超过 64 个字符的工具名，Cursor 会丢掉超过 60 个字符的工具。Coffer 为每个发现的能力记录这个长度，
即 `client_name_length`；服务器的**工具**标签页
会标出每个超过 64 的工具。`mcp__coffer__`（13）加上 24 个字符的服务器名，再加 `__`
（2），留给上游工具自身名称的只剩 25 个字符。

以下情况调用会被拒绝，返回 JSON-RPC 错误码 `-32000`，并附带说明原因的信息：

- 该能力在其服务器上被关闭（在 **MCP 服务器** 下该服务器页面的**工具**标签页），或者
- 服务器的[生效范围](/zh/architecture/resource-framework#reach)不包含打开该会话的智能体。

Coffer 内部的其他失败是 JSON-RPC 错误 `-32603`。上游工具失败时，它自己的 `isError: true`
结果原样返回。

### 分层 {#tiering}

当上游目录超过列表预算时，`tools/list` 只携带其中一部分：Coffer 的内置工具总在其中，
然后是按近期调用频率排序的上游工具，每个服务器至少一个。没列出的工具仍可按名称调用，
并能通过 `coffer__search_tools` 找到。预算由守护进程的环境变量设置；见[配置](/zh/reference/configuration)。

| 设置 | 默认值 |
| --- | --- |
| 预算（列出的上游工具数） | 50 |
| 用量统计窗口 | 90 天 |
| 模式 | 开启；`COFFER_TOOL_TIERING=off` 列出全部 |

## 握手说明 {#handshake-instructions}

Coffer 的 `initialize` 结果声明协议版本 `2025-06-18`、服务器名称 `coffer`，以及能力
`tools`、`resources` 和 `prompts`，每项都带 `listChanged: true`（resources 不带 `subscribe`）。
其中的 `instructions` 字段会被客户端放进智能体的系统提示词，最多 800 个字符。内容如下（记忆根目录是 `~/.coffer/derived/memory`，在保险库之外，这里是 `/Users/you/.coffer/derived/memory`）：

```text
Coffer is this machine's local vault: it aggregates the user's MCP servers behind one
endpoint, holds what this developer wrote down, and adds its own tool:
coffer__search_tools (describe an upstream tool you need; results are callable by name).
Its knowledge is markdown you read with your own file tools. Its
memory notes are Markdown under /Users/you/.coffer/derived/memory/*/notes/; grep them with your
own tools. Its own logs: coffer log audit|mcp|daemon (files: coffer path logs). The
coffer-guide skill is the manual: load it for the catalogue, with paths, before asking
the developer something they may have written down.
```

（这里的换行是为了排版，实际文本是一段。）如果记忆根目录太长、放不进 800 个字符的上限，
那句话会缩短到放得下为止。如果本会话上一次 `tools/list`
因分层隐藏了工具，还会追加一句：

```text
Your tool list is a budgeted slice: 88 more upstream tools are unlisted, all callable.
```

## 不用工具处理知识、记忆和日志 {#memory-and-logs-without-a-tool}

Coffer 没有用于知识、记忆笔记或自身记录的工具，因为智能体用已有的能力就都能做到。
要新增知识，就按 `coffer-guide` 技能的说明，直接往某个知识集里写一篇 Markdown 文档；留在知识集 `.inbox/` 文件夹里的文件，会被 Coffer 的扫描收编，补全缺失的 frontmatter 并升格为文档。
要修改文档或记忆笔记，直接就地编辑文件。

| 要找 | 做法 |
| --- | --- |
| 一篇知识文档 | 读 `coffer-guide` 技能列出的知识集文件夹下的文件。 |
| 一条记忆笔记 | 在握手说明、会话开始时的投递内容和 `coffer-guide` 技能所指明的记忆根目录里 grep（每个分区的笔记都在 `<root>/<partition>/notes/*.md`），再读文件。 |
| Coffer 里改了什么（注册、删除、密钥读取、配置写入） | `coffer log audit --since 1h` |
| 哪些 MCP 调用失败了 | `coffer log mcp --status error --since 1h`，或用 `--server <name>` 只看一个服务器 |
| 守护进程记录了什么，包括 traceback | `coffer log daemon --errors --since 1h`，或 grep `coffer path logs` 指明的文件 |

每个 `coffer log` 读取命令都支持 `--json`，方便脚本使用。见
[活动与审计](/zh/guides/activity)和[记忆](/zh/guides/memory)。

## 相关页面 {#related}

- [连接客户端](/zh/guides/connect-a-client)——把 Coffer 的 MCP 条目装进智能体。
- [MCP 服务器](/zh/guides/mcp-servers)——注册这些名称所来自的上游服务器。
- [MCP 网关](/zh/architecture/mcp-gateway)——深入了解会话、shim、发现与分层。
- [mcp-gateway 规格](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/mcp-gateway/spec.md)
