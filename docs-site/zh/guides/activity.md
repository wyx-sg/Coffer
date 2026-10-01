---
title: 活动与审计
description: 查看保险库里改了什么、智能体通过网关调用了什么、守护进程记录了什么，并控制每类记录保留多久。
---

# 活动与审计 {#activity-and-audit}

Coffer 为自己保留三类记录：保险库变更的审计日志、经 MCP 网关转发的每次调用的调用日志，以及守护进程自己的日志。本页介绍如何从 Web 界面、命令行和智能体读取它们，如何把失败的请求和对应的日志行关联起来，以及每类记录保留多久。

## 三类记录，三个问题 {#three-records-three-questions}

| 记录 | 回答的问题 | 存储位置 | 在哪里看 |
| --- | --- | --- | --- |
| 审计日志 | 改了什么，谁改的？ | `runs.db` 中的 `audit_log` 表 | **活动 → 变更**、`coffer log audit` |
| MCP 调用 | 智能体调用了什么，结果如何？ | `mcp_invocations` 表 | **活动 → MCP 调用**、`coffer log mcp` |
| 守护进程日志 | Coffer 内部发生了什么，包括哪里坏了？ | `~/.coffer/logs/daemon.log` | **活动 → 守护进程日志**、`coffer log daemon`、`coffer path logs` |

三类记录都只留在写下它们的那台机器上。[保险库同步](/zh/guides/vault-sync)从不发布它们，Coffer 也不会把它们发往任何地方。

## 活动页 {#the-activity-page}

在侧边栏打开 **活动**。标题旁的绿点表示有新记录正在流入。页面有四个标签页，每个标签页显示所选时间范围内的记录数（没有记录或日志读取失败的标签页不显示数字）：

- **全部** — 默认标签页：变更、MCP 调用以及守护进程的警告和错误合并成一条流，最新的在前。列：**时间**、**事件**、**操作者**、**耗时**。
- **变更** — 审计日志：**时间**、**事件**（用一句话描述的变更，如「已存储密钥」）和 **操作者**（谁做的）。
- **MCP 调用** — 网关转发的每次工具调用、资源读取或提示词获取各占一行：**时间**、**智能体**（哪个智能体的会话发起的）、**服务器 · 工具**、**耗时** 和 **状态**。服务器自己的 **调用记录** 标签页读的是同一份日志，只看该服务器。
- **守护进程日志** — `daemon.log` 的尾部：**时间**、**级别**、**记录器** 和 **消息**。当出问题的是 Coffer 本身、而不是它代理的东西时，看这里。行上方的一行写着文件路径，**打开日志文件** 会在你的编辑器中打开它。

行的上方有一行说明列表里有什么：在「全部」中是时间窗口内的错误和警告数（例如「最近一小时 1 个错误、1 个警告」），或者已加载多少条、共多少条；在「MCP 调用」中是窗口内的调用数、失败数和被拒数。

当前标签页会写进 URL（`/activity?tab=mcp`、`/activity?tab=daemon`；「全部」是 `/activity`），所以链接可以直接落到守护进程日志。

**筛选。** 每个标签页都可以按时间范围和自由文本筛选；按 `/` 跳到文本框。时间范围可选最近 15 分钟、1 小时、24 小时或 7 天、**保留的全部记录**，或自定义起止时间（「到」留空表示到现在）。在你选择范围之前，标签页默认显示最近一小时，守护进程日志默认显示最近 24 小时。各标签页还会根据自身记录的字段提供筛选：**智能体**（全部、变更、MCP 调用）；**服务器**（全部、MCP 调用）；**类型**（全部、变更）；**状态**（MCP 调用）；守护进程日志上有级别（**全部**、**信息**、**警告**、**错误**）和 **记录器**。

**智能体** 和 **类型** 可以同时选多个值，每个值旁边显示已加载记录中带有它的条数，记录只要匹配其中任意一个就显示。**智能体** 先列出你的智能体，再列出其他会做变更的来源：**你**（Web 界面或 Coffer 应用）、**命令行**、**Coffer** 自身和 **同步**。**类型** 列出 **MCP 调用**、**变更**（下面列出每种变更：MCP 服务器、技能、智能体、密钥、同步、设置、知识、记忆等）和 **守护进程记录**。选择智能体或类型会缩小列表，但标签页上的计数不变。

**详情。** 选中一行会在列表旁的抽屉中打开它。失败的调用会先显示错误以及该服务器的近况——从什么时候开始失败、最近 24 小时出了多少次错；变更会说明谁做的、影响了什么，然后以 diff 形式展示前后的配置（密钥值从不记录）；守护进程记录显示消息和 traceback。下方是各项事实——智能体、会话、服务器和传输方式、工具、耗时、调用 id——以及前后五分钟内写下的记录和原始记录。调用只显示元数据：参数和结果从不存储。箭头可以切换到上一条或下一条记录，底部给出下一步操作：**打开** 资源、失败调用对应服务器的 **守护进程日志记录**，或复制记录。

在 **守护进程日志** 中，点击一行会在该行下方原地展开，显示 traceback、**复制记录**，以及——当记录里带有服务器和工具时——**查看这次 MCP 调用**，它会切换到「MCP 调用」并查找那次调用。

**新记录会自动出现。** 当你停在列表顶部且没有打开任何记录时，新记录一写入就出现在顶部。一旦你向下滚动或打开了某条记录，列表就保持不动，一个 **↑ N new** 按钮会统计等待中的记录数；点它或滚回顶部就能把它们加进来。没有暂停或刷新按钮。每类日志的最新记录每隔几秒重新读取一次，守护进程在[事件流](/zh/architecture/event-stream)上宣告的变更会让审计日志的新记录立即出现。

**更早的记录。** 每个标签页一次加载 200 条；底部的 **加载更早的记录** 按日志游标取下一页，直到时间范围读完。旁边 Coffer 会说明 MCP 调用和变更保留多久，并附上指向设置位置 **设置 › 数据** 的链接。

**导出。** 标题旁的 **⋯** 菜单中，**导出筛选后的记录…** 下有 **导出为 JSON** 和 **导出为 CSV**。两者都会把当前标签页中符合当前筛选条件的所有记录——不只是已加载的——最多 10,000 条，写到你保存的文件里。

## 审计条目记录了什么 {#what-an-audit-entry-records}

每个条目包含：

| 字段 | 含义 |
| --- | --- |
| `timestamp` | 发生时间，UTC。 |
| `event_type` | 发生了什么，例如 `resource_created`、`resource_scope_updated`、`secret_revealed`、`skill_bound`、`provider_switched`、`sync_run`、`token_rotated`。 |
| `resource_kind`、`resource_name` | 涉及的资源，使用当时的名字。 |
| `resource_uid` | 资源的 uid，所以改名后历史仍能对上。 |
| `actor` | 谁做的（见下文）。 |
| `details` | 结构化的内容，存储前按类型脱敏。`secret_set` 只记录写入了一个密钥，绝不记录密钥本身。 |

**actor** 取以下之一：

| Actor | 显示为 | 来源 |
| --- | --- | --- |
| `ui` | 你（Web 界面） | Web 界面发送 `X-Coffer-Actor: ui`。 |
| `desktop` | 你（Coffer 应用） | 桌面应用确认过的操作。 |
| `cli` | 命令行 | 命令行发送 `X-Coffer-Actor: cli`。 |
| `api` | API | 没有发送 `X-Coffer-Actor` 请求头的 REST 调用方。 |
| `system` | Coffer | 守护进程自主行为，例如后台任务。 |
| `sync` | 同步 | 同步轮次应用另一台机器的改动。 |
| `channel` | 消息渠道 | 从聊天渠道发起的操作。 |
| `human` | human | 不是由任何 Coffer 操作造成的保险库文件改动——你的编辑器、shell、智能体自己的文件工具、你自己的 `git commit`。保险库提交之后，它以 `vault_file_edited` 审计，每个文件一条（见[手动编辑保险库](/zh/guides/vault-files)）。 |
| 智能体的名字 | 该名字 | 智能体自己的操作，例如它的记忆 Hook 投递一条笔记（`memory_delivery_fired`，details 中写明时机、会话和笔记）。 |

并非每个事件都会被审计。审计日志保留的是：落在 Coffer 之外的变更（写进智能体配置的文件）、不可逆或涉及安全的变更（删除、在桌面应用中查看密钥或由 `coffer run` 解析密钥、审批、主密钥备份、以 `vault_file_restored` 恢复保险库文件的早期版本），以及事后从当前状态无法看出的变更（保留窗口）。保险库的每一次改动同时也是一个标明写入者的提交，所以即使审计日志没记的，`coffer vault history <path>` 也能回答是谁改了某个文件。例行的运行时事件只是日志行，不是审计行。每个被审计的事件也会以同样的事件名写入守护进程日志，所以两边都能搜到。

## 用命令行查询审计日志 {#query-the-audit-log-from-the-cli}

```sh
coffer log audit                                   # newest 50
coffer log audit --kind mcp_server --name filesystem
coffer log audit --event-type secret_resolved --since 2026-09-01T00:00:00Z
coffer log audit --event-type memory_delivery_fired --limit 20
coffer log audit --trace 44e10b60da1b4f26         # one request's or turn's rows
coffer log audit --json
```

| 选项 | 含义 |
| --- | --- |
| `--kind` | 资源类型，例如 `mcp_server`、`agent`、`skill`。 |
| `--name` | 资源名。需要配合 `--kind`。 |
| `--event-type` | 某一种事件类型。 |
| `--since` | ISO 8601 下界，或者 `30m`、`1h`、`2d` 这样的时长。 |
| `--trace` | 只看一个请求或轮次的行：它的 trace id，也就是抽屉、`X-Coffer-Trace` 响应头或一行守护进程日志上显示的那个。`coffer log mcp` 和 `coffer log daemon` 也接受它。 |
| `--limit` | 1–500，默认 50。 |
| `--json` | 机器可读的输出。 |

通过 REST，同样的查询是 `GET /api/v1/audit`，它还接受 `event_prefix`，用来选择一族事件，例如 `sync_` 或 `skill_`。

## 用命令行查询 MCP 调用 {#query-mcp-invocations-from-the-cli}

```sh
coffer log mcp                              # every server, newest 20
coffer log mcp --server filesystem          # one server
coffer log mcp --status error --since 1d --json
```

不带 `--server` 时，输出包括 Coffer 自己的内置工具调用（服务器为 `coffer`）以及已删除服务器的行（`deleted:<name>`）。`--limit` 接受 1–500。

每次调用处于四种状态之一：

| 状态 | 含义 |
| --- | --- |
| `ok` | 上游及时应答且没有标记错误。 |
| `error` | 服务器起不来、调用抛出异常，或工具返回的结果设置了 `isError`。 |
| `timeout` | 上游没有在该服务器的请求超时时间内应答。 |
| `denied` | Coffer 在到达上游之前就拒绝了：服务器或该能力被禁用，或服务器不在该智能体的生效范围内。 |

::: info 参数和结果从不存储
调用日志记录的是谁、在什么时候、调用了什么、耗时多久、结果如何。它没有存放调用参数或返回值的列。对于报告了 `isError` 的工具，存下的消息是 Coffer 的固定文本 `upstream tool returned an error result (isError)`，而不是上游自己的消息，因为那可能回显参数。要查看工具失败的原因，请看该服务器在 `~/.coffer/logs/upstream/<server>.log` 中的 stderr。
:::

## 用命令行读取守护进程日志 {#read-the-daemon-log-from-the-cli}

```sh
coffer log daemon                           # newest 100 records
coffer log daemon --errors --since 1h
coffer log daemon --json
coffer path logs                            # the log directory and its daemon.log
```

`coffer log daemon` 读取 `daemon.log` 的尾部，并按 **守护进程日志** 标签页的方式规整格式。`--limit` 接受 1–500。`coffer path logs` 打印文件位置（`COFFER_LOG_DIR` 可以改变它），方便你直接 `grep`。

## 让智能体查看 Coffer {#let-an-agent-look-into-coffer}

会话中出问题时，智能体可以用同样的命令自己去读 Coffer 的历史：在它的 shell 里运行 `coffer log audit`、`coffer log mcp` 和 `coffer log daemon --errors --since 1h`，或者对 `coffer path logs` 给出的守护进程日志做 `grep`。这些都不会返回密钥值。像「我的 Jira 工具一直失败，查一下 Coffer 的日志」这样的提示词就够了：`coffer-guide` 技能会告诉智能体去哪里看，所以它不会让你去找文件。

## 把失败的请求与日志关联起来：`X-Coffer-Trace` {#correlate-a-failed-request-with-the-log-x-coffer-trace}

守护进程处理的每个 HTTP 请求都有一个 trace id。守护进程把它作为 `trace_id` 写到该请求产生的每条日志记录上，并在每个响应（包括错误响应）的 `X-Coffer-Trace` 响应头中返回。要查一次失败请求期间发生了什么：

```sh
curl -si -H "X-Coffer-Token: $TOKEN" http://127.0.0.1:8000/api/v1/resources/nope \
  | grep -i x-coffer-trace
# x-coffer-trace: 3f9c0a6e2b7d4e1f9a0c5b2d8e7f6a1c

grep 3f9c0a6e2b7d4e1f9a0c5b2d8e7f6a1c ~/.coffer/logs/daemon.log
```

客户端也可以自己发送 `X-Coffer-Trace` 请求头，让同一个操作发起的多次调用共用一个 id；`coffer` 命令行和 MCP shim 不这样做，所以它们的每个请求都有自己的 id。该值最长 64 个字符，只保留字母、数字和 `._:-`；处理后不再成立的值会被替换成新的 id。

## 控制记录保留多久 {#control-how-long-records-are-kept}

一个后台任务在守护进程启动时以及此后每六小时清理一次。每类记录有一条策略：

| 策略 | 默认值 | 作用 |
| --- | --- | --- |
| `audit_log` | 365 天 | 删除更早的审计条目。 |
| `mcp_invocations` | 30 天 | 删除更早的调用行。 |
| `sync_runs` | 90 天 | 删除更早的同步轮次历史。 |
| `conversations_archive` | 7 天 | 归档这么久没有新消息的对话。 |
| `conversations` | 30 天 | 在归档后这么久删除已归档的对话（连同其消息）。 |

::: code-group

```sh [CLI]
coffer config list retention.
coffer config set retention.audit_log 730
coffer config set retention.mcp_invocations forever   # never prune this table
coffer log prune                                      # apply every policy now
coffer log prune --table mcp_invocations
```

```text [Web UI]
Settings → Data → History
```

:::

天数至少为 1。Web 界面的 **历史记录** 区块只显示人们通常会调的三项——**变更**（`audit_log`）、**MCP 调用**（`mcp_invocations`）和 **对话**（`conversations`）；其余的用命令行设置。在 Web 界面中缩短窗口会先请求确认，因为下一次清理会删除更早的行，确认框会显示将删除的数量；**立即清理过期数据** 会立即应用所有策略。修改策略本身也会以 `retention_updated` 审计。

守护进程日志是文件而不是表，所以没有策略：`daemon.log` 在 10 MB 时轮转，保留三份轮转文件。`~/.coffer/logs/` 中每个进程的 shim 日志和轮转出去的上游日志七天后删除。

## 工作原理 {#how-it-works}

审计列表为什么短、日志读取器如何规整各个写入方的格式、trace id 如何到达日志行，见[可观测性](/zh/architecture/observability)。

## 相关内容 {#related}

- [故障排查](/zh/guides/troubleshooting)
- [运行守护进程](/zh/guides/daemon#logs)
- [MCP 服务器](/zh/guides/mcp-servers)
- [MCP 工具参考](/zh/reference/mcp-tools)
- 规格：[resource-framework](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/resource-framework/spec.md)、[daemon](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/daemon/spec.md)
