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
| [`coffer__write`](#coffer-write) | 把一条长期有效的事实记入 Coffer 的知识。 | `knowledge` 功能开启时。 |
| [`coffer__search_tools`](#coffer-search-tools) | 按意图对上游工具目录排序。 | 始终存在。 |

完整列表就这两个。Coffer 的记忆笔记和它自己的记录没有对应工具：
它们用智能体自己的文件工具和 `coffer` 命令行来读。见
[不用工具读取记忆和日志](#memory-and-logs-without-a-tool)。

`coffer__write` 属于 `knowledge` [实验功能](/zh/guides/experimental-features)。
在该功能关闭期间，该工具不会出现在 `tools/list` 中，握手说明里也不会提到它，调用它得到的回应和调用一个不存在的工具完全一样。
切换功能开关在下一次列出或调用时生效，无需重启。

::: tip 智能体里的名称
Coffer 以名为 `coffer` 的 MCP 服务器装进智能体的配置，所以大多数客户端会在这些工具前面加上
自己的前缀。比如在 Claude Code 里，`coffer__write` 显示为 `mcp__coffer__coffer__write`。
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

## coffer\_\_write {#coffer-write}

把用户工作环境中长期有效的信息记入一个知识集：某个服务的事实、一条约定、一个决定及其理由、
一个坑以及怎么避开。你写的是新材料；Coffer 的整理任务会把它整理进知识集的文档，并与已有内容去重。
它不用于记录智能体眼前仓库里的东西、临时性的内容或密钥。没有对应的读取工具：
智能体用自己的文件工具，在 `coffer-guide` 技能列出的路径下读取知识。

指南：[知识](/zh/guides/knowledge)。

### 输入 {#input}

| 属性 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `collection` | string | 是 | 记到哪个知识集。`coffer-guide` 技能列出了全部知识集。 |
| `title` | string | 是 | 给人看的标题，点明主题。 |
| `description` | string | 是 | 一行话，说明它回答什么问题。整理时决定材料归属，会先读这一行。 |
| `body` | string | 否 | Markdown 正文。 |

每个知识集都允许每个智能体写入。必填属性为空或只有空白时，会报
`ValueError: 'title' must be a non-empty string`（其他属性同理）。
知识集不存在时报错，错误信息会列出你可以写入的知识集。

### 结果 {#result}

配置了内部模型时，材料会排队等待整理：

```json
{
  "collection": "global",
  "title": "Staging DB is read-only on Fridays",
  "status": "pending",
  "note": "Queued as an item. Coffer's curation folds it into this collection's documents shortly."
}
```

没有配置内部模型时，材料会单独存成一篇文档，结果里给出它的名字：

```json
{
  "path": "staging-db-read-only-on-fridays.md",
  "title": "Staging DB is read-only on Fridays",
  "description": "When staging writes fail at the end of the week",
  "file_path": "/Users/you/.coffer/vault/knowledge/global/staging-db-read-only-on-fridays.md",
  "folder_path": "/Users/you/.coffer/vault/knowledge/global",
  "status": "written",
  "note": "Filed as a document of its own: Coffer's model is not set to curate it."
}
```

### 调用示例 {#example-call}

```json
{
  "jsonrpc": "2.0",
  "id": 7,
  "method": "tools/call",
  "params": {
    "name": "coffer__write",
    "arguments": {
      "collection": "global",
      "title": "Staging DB is read-only on Fridays",
      "description": "When staging writes fail at the end of the week",
      "body": "A freeze job flips the staging primary to read-only every Friday at 18:00 UTC."
    }
  }
}
```

## coffer\_\_search\_tools {#coffer-search-tools}

按意图搜索聚合后的上游 MCP 工具目录，返回最相关的工具定义。受预算限制的 `tools/list`
没有列出的工具，就用它来找：返回的每个工具都能按名称调用，无论有没有被列出。排序是确定性的
BM25，依据每个工具的服务器、名称和描述。Coffer 自己的 `coffer__*` 工具不会出现在结果里。
搜索范围是会话生效范围内所有服务器的完整目录；没有应答的服务器会被跳过。

始终存在。背景：[MCP 网关](/zh/architecture/mcp-gateway)。

### 输入 {#input-1}

| 属性 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `query` | string | 是 | | 你想做什么，用自然语言或关键词。 |
| `top_k` | integer | 否 | `5` | 返回多少个工具。限制在 1–20 之间。 |

### 结果 {#result-1}

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

### 调用示例 {#example-call-1}

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
即 `client_name_length`；服务器的**工具**标签页和 `coffer mcp cap list <server>`
会标出每个超过 64 的工具。`mcp__coffer__`（13）加上 24 个字符的服务器名，再加 `__`
（2），留给上游工具自身名称的只剩 25 个字符。

以下情况调用会被拒绝，返回 JSON-RPC 错误码 `-32000`，并附带说明原因的信息：

- 该能力在其服务器上被关闭（在 **MCP 服务器** 下该服务器页面的**工具**标签页，
  或 `coffer mcp cap disable <server> tool:<name>`），或者
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
其中的 `instructions` 字段会被客户端放进智能体的系统提示词，最多 800 个字符，只提及本会话列表中
实际携带的内置工具。内容如下（记忆根目录是 `~/.coffer/derived/memory`，在保险库之外，这里是 `/Users/you/.coffer/derived/memory`）：

```text
Coffer is this machine's local vault: it aggregates the user's MCP servers behind one
endpoint, holds what this developer wrote down, and adds its own tools: coffer__write
(file a durable fact), coffer__search_tools (describe an upstream tool you need; results
are callable by name). Its knowledge is markdown you read with your own file tools. Its
memory notes are Markdown under /Users/you/.coffer/derived/memory/*/notes/; grep them with your
own tools. Its own logs: coffer log audit|mcp|daemon (files: coffer path logs). The
coffer-guide skill is the manual: load it for the catalogue, with paths, before asking
the developer something they may have written down.
```

（这里的换行是为了排版，实际文本是一段。）如果记忆根目录太长、放不进 800 个字符的上限，
那句话会改为指明 `coffer path memory` 打印的目录，而不是路径本身。如果本会话上一次 `tools/list`
因分层隐藏了工具，还会追加一句：

```text
Your tool list is a budgeted slice: 88 more upstream tools are unlisted, all callable.
```

## 不用工具读取记忆和日志 {#memory-and-logs-without-a-tool}

Coffer 没有用来读取记忆笔记或自身记录的工具，因为智能体用已有的能力就能做到：

| 要找 | 做法 |
| --- | --- |
| 一条记忆笔记 | 在握手说明和会话开始时投递内容所指明的记忆根目录里 grep（每个分区的笔记都在 `<root>/<partition>/notes/*.md`），再读文件。`coffer path memory [<partition>]` 打印根目录或某个分区的目录。 |
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
