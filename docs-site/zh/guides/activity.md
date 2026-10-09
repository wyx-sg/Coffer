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
| MCP 调用 | 智能体调用了什么，结果如何？ | `mcp_invocations` 表 | **活动 → 工具调用**、`coffer log mcp` |
| 守护进程日志 | Coffer 内部发生了什么，包括哪里坏了？ | `~/.coffer/logs/daemon.log` | **活动 → 守护进程日志**、`coffer log daemon`、`coffer path logs` |

三类记录都只留在写下它们的那台机器上。[保险库同步](/zh/guides/vault-sync)从不发布它们，Coffer 也不会把它们发往任何地方。

## 活动页 {#the-activity-page}

在侧边栏打开**活动**。页头有一个 **Live** 标记（一个圆点加这个词；每当守护进程的变更流断开时显示**重新连接中…**，表示新记录没有流进来）和一个**导出**菜单。下面是四个标签页，不带数量：默认的**全部**、**变更**、**工具调用**和**守护进程日志**。日志读不出来的标签页显示一个警告图标。

- **全部**——变更、工具调用以及守护进程的警告和错误合并成一条流，最新的在前。列：**时间**、**事件**、**由谁**和**耗时**。
- **变更**——审计日志：**时间**、**事件**（用一句话描述这次变更，例如“Stored a secret”）和**由谁**（谁做的）。
- **工具调用**——网关转发的每次工具调用、资源读取或提示词获取各占一行：**时间**、**智能体**（哪个会话发起的）、**服务器 · 工具**、**耗时**和**状态**。
- **守护进程日志**——`daemon.log` 的尾部：**时间**、**级别**、**Logger** 和**消息**。当 Coffer 自己出问题、而不是它代理的东西出问题时，打开它。行上方那一行写明文件名，并显示“newest first”，事件流打开时还有“following”，**在 Finder 中打开**会定位到该文件。

行按所在的日子分组，每组有一个标题（“Today · Sep 29”），行的上方没有汇总行。当前标签页是 URL 的一部分（`/activity?tab=mcp`、`/activity?tab=daemon`；“全部”是 `/activity`）。

**筛选。** 每个标签页的筛选都在一行里：先是搜索框（按 `/` 跳进去），然后是时间范围和各个筛选标签，只要设置了任何一项，最右边就有**清除筛选**。这些都不显示结果数量。搜索匹配记录的文字，对调用还匹配服务器名称，所以没有单独的服务器筛选。各标签页再加上自己记录所带的筛选：

- 全部：**由谁**和**类型**。
- 变更：**由谁**和**类型**。
- 工具调用：先是分段的 **全部 / 成功 / 失败**（失败包括出错、超时和被拒绝），然后是**由谁**。
- 守护进程日志：先是分段的 **全部 / 信息 / 警告 / 错误** 级别，然后是 **Logger**。

时间范围可选**最近 1 小时**、**最近 24 小时**、**最近 7 天**、**最近 30 天**，或在日历上选的自定义范围（时间可选，结束时间可以是“现在”，最多回溯 90 天）。标签页默认打开在最近一小时，守护进程日志则是最近 24 小时，直到你选一个范围。

**由谁**一次可选多个值，记录匹配其中任何一个就显示。它先列出你的智能体，然后在“不是智能体”之下列出你（Web 界面或 Coffer 应用）、命令行、Coffer 自己和同步；在 工具调用上只列智能体。“全部”上的**类型**有三个值：**工具调用**、**变更**和**守护进程记录**。在“变更”上它列出十一种变更：某种资源，或者对不涉及资源的变更用密钥、同步、设置和命令行工具。筛选、搜索和时间范围都保存在地址里（`q`、`range`、`by`、`kind`、`status`、`level`、`logger`），所以 `/activity?tab=mcp&q=github` 这样的链接打开时就已经在搜索了，别的页面上的**在活动中查看**用的就是它。换到另一个标签页会保留搜索、时间范围和**由谁**，丢掉只有旧标签页才有的筛选。

**详情。** 在“全部”、“变更”或“工具调用”上选中一行，会在页面旁边打开一个 640 像素宽的抽屉；**Esc**、点击抽屉外部或 ✕ 关闭它，**↑** 和 **↓** 切到上一条或下一条记录。失败的调用以它的错误开头，并说明它的服务器最近怎么样（从什么时候开始失败，以及过去 24 小时里有多少次错误）；变更会说明谁做的、动了什么，然后把改动前后的配置以 diff 展示（密钥的值从不记录）。下面是各项事实、它前后五分钟内写入的记录，以及原始记录，默认折叠，需要时再展开。调用接着显示它带了什么：参数、返回结果或错误，[自定义工具](/zh/guides/custom-tools)还有 HTTP 请求和响应，每一部分都是可折叠的区块，带**复制**（见[调用记录了什么](#what-a-call-records)）。底部是下一步：**打开**该资源，旁边是**复制详情**。

在**守护进程日志**上，一行改为就地在它自己那一行下面展开，带着它的 traceback、**复制记录**，以及——当记录点名了服务器和工具时——**显示这次 工具调用**，它会切到 工具调用并搜索那次调用。

**把失败交给智能体。** 只有依赖这台机器的失败才提供**交给 &lt;Agent&gt; ▾**：服务器从未应答的调用（在它的抽屉里），以及展开的、关于外部服务或环境的守护进程错误。被拒绝的调用、服务器自己返回的错误和 Coffer 内部的错误都不提供交接；这类守护进程错误只提供**复制记录**。

**新记录会自己到来。** 当你位于列表顶部、也没有打开任何东西时，新记录一写入就出现在顶部。一旦你向下滚动或打开了一条记录，列表就保持不动，一个 **↑ N 条新记录** 按钮统计等着的数量；点它，或滚回顶部，就把它们带进来。没有暂停或刷新按钮。日志加载失败的标签页会显示一条警告横幅，带着错误和只针对那份日志的**重试**；其他记录照常工作，在“全部”上横幅会说明下面哪些记录是完整的。

**更早的记录。** 每个标签页一次加载一页记录。框的最后一行写着“Showing 30 of 1,204”，并提供**加载更多 50 条**；全部保留的记录都显示出来之后，它会这样说，并说明 工具调用和变更保留多久，附一个到**设置 › 数据**的链接。

**首次运行。** 什么都还没有记录时，没有什么可筛选的，所以页面隐藏筛选行和**导出**，并说“Changes you make in Coffer and the tools agents call through it show up here.”，附**连接智能体**和**添加 MCP 服务器**。时间范围内为空而更早的记录仍在，则不算首次运行：筛选保留。

**导出。** 页头的**导出 ⌄**菜单有 **JSON** 和 **CSV**。两者都会写出当前标签页中匹配当前筛选的每一条记录，而不只是已加载的，最多 10,000 条，保存成你选的文件。记录的交接提示词不在其中。

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

并非每个事件都会被审计。审计日志保留的是：落在 Coffer 之外的变更（写进智能体配置的文件）、不可逆或涉及安全的变更（删除、在桌面应用中查看密钥或由 `coffer run` 解析密钥、审批、主密钥备份），以及事后从当前状态无法看出的变更（保留窗口）。保险库的每一次改动同时也是一个标明写入者的提交，所以即使审计日志没记的，保险库的 git 历史（在保险库文件夹中执行 `git log -- <path>`）也能回答是谁改了某个文件。例行的运行时事件只是日志行，不是审计行。每个被审计的事件也会以同样的事件名写入守护进程日志，所以两边都能搜到。

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
| `--q` | 自由文本，不区分大小写，匹配事件代码、资源名、执行者和详情——也就是页面上的搜索框。 |
| `--q-type` | 配合 `--q`：同样算作匹配的事件类型（可重复），就像页面把译文里含有该文本的事件也加进来。 |
| `--cursor` | 读下一页：上一次读取打印出的 `next_cursor`。后面还有内容的页面会在末尾给出要用的 `--cursor` 值。 |
| `--limit` | 1–500，默认 50。 |
| `--json` | 机器可读的输出。 |

通过 REST，同样的查询是 `GET /api/v1/audit`，它还接受 `event_prefix`，用来选择一族事件，例如 `sync_` 或 `skill_`。

## 用命令行查询 MCP 调用 {#query-mcp-invocations-from-the-cli}

```sh
coffer log mcp                              # every server, newest 20
coffer log mcp --server filesystem          # one server
coffer log mcp --status failed --since 1d --json   # every outcome but ok
coffer log mcp --agent-uid <agent-uid> --q timeout
coffer log mcp --uid coffer                 # Coffer's own tools, or a deleted server's uid
```

不带 `--server` 时，输出包括 Coffer 自己的内置工具调用（服务器为 `coffer`）以及已删除服务器的行（以其 uid 显示）。`--status` 接受 `ok`、`error`、`timeout`、`denied`，或用 `failed` 表示除 `ok` 以外的所有结果；`--agent-uid` 只保留某个智能体的调用；`--q` 搜索工具、错误、会话、结果和服务器名；`--uid` 按写入这些行时的服务器 uid 过滤，能选中 `--server` 叫不出名字的 `coffer` 和已删除的服务器（`--uid` 和 `--q` 读的是所有服务器，所以不能和 `--server` 同用）。`--limit` 接受 1–500，`--cursor` 读下一页。[自定义工具](/zh/guides/custom-tools#environments)的调用还会写明它在哪个环境里发出：活动页面在工具旁边（`@live`）和抽屉里显示它，`--json` 以 `environment` 字段带出。`coffer log mcp` 会打印每次调用的 id；`coffer log call <id>` 打印一次调用及其内容。

每次调用处于四种状态之一：

| 状态 | 含义 |
| --- | --- |
| `ok` | 上游及时应答且没有标记错误。 |
| `error` | 服务器起不来、调用抛出异常，或工具返回的结果设置了 `isError`。 |
| `timeout` | 上游没有在该服务器的请求超时时间内应答。 |
| `denied` | Coffer 在到达上游之前就拒绝了：服务器或该能力被禁用，或服务器不在该智能体的生效范围内。 |

### 调用记录了什么 {#what-a-call-records}

每次调用保存它的参数，以及结果或错误。自定义工具的调用还保存它发出的 HTTP 请求（方法、URL、请求头、请求体）和收到的响应（状态码、响应头、响应体）。写入之前，Coffer 会把下面这些遮盖成 `••••••`：

- 它注入给这个服务器或自定义工具的每一个密钥值；
- 整个凭据请求头（`Authorization`、`Cookie`、`X-Api-Key`，以及名字里带 token、secret、key 或 auth 的请求头）；
- 名字表明是密钥的字段（`password`、`token`、`api_key` 之类）；
- 它的泄漏规则认得的任何明文密钥，例如 `ghp_…` 开头的 GitHub 令牌。

每一部分在 16 KB 处截断；被截断的部分会写明原来有多大。这些记录跟随调用日志的保留期（默认 30 天）。这一行的错误消息仍是 Coffer 的固定文本，例如工具标记了错误时是 `upstream tool returned an error result (isError)`；上游实际说了什么，在这次调用的**错误**部分里。经过 Coffer 模型代理的模型请求不记录。

在命令行用 `coffer log call <id>` 读取一次调用及其内容（`coffer log mcp` 会打印 id）。要在这台机器上停止记录内容，在**设置 › 数据 › 历史记录**里关掉**记录工具调用内容**，或运行 `coffer settings call-content set --set enabled=false`。关闭期间的调用只保留元数据，抽屉里会这样说明。

## 用命令行读取守护进程日志 {#read-the-daemon-log-from-the-cli}

```sh
coffer log daemon                           # newest 100 records
coffer log daemon --errors --since 1h
coffer log daemon --level warning --q sync --with-total
coffer log daemon --json
coffer path logs                            # the log directory and its daemon.log
```

`coffer log daemon` 读取 `daemon.log` 的尾部，并按 **守护进程日志** 标签页的方式规整格式。`--level` 只保留某个严重级别及以上的记录（`debug`、`info`、`warning`、`error`、`critical`），`--q` 搜索消息、记录器、级别和折叠的行，`--with-total` 还会统计最近尾部里的匹配数，`--cursor` 读下一页。`--limit` 接受 1–500。这个命令经由守护进程读取，守护进程没在运行时会先启动它；`coffer path logs` 打印文件位置（`COFFER_LOG_DIR` 可以改变它），不需要守护进程，方便你直接 `grep`。

## 让智能体查看 Coffer {#let-an-agent-look-into-coffer}

会话中出问题时，智能体可以用同样的命令自己去读 Coffer 的历史：在它的 shell 里运行 `coffer log audit`、`coffer log mcp` 和 `coffer log daemon --errors --since 1h`，或者对 `coffer path logs` 给出的守护进程日志做 `grep`。这些都不会返回密钥值。像「我的 Jira 工具一直失败，查一下 Coffer 的日志」这样的提示词就够了：`coffer-guide` 技能会告诉智能体去哪里看，所以它不会让你去找文件。

## 把失败的请求与日志关联起来：`X-Coffer-Trace` {#correlate-a-failed-request-with-the-log-x-coffer-trace}

守护进程处理的每个 HTTP 请求都有一个 trace id。守护进程把它作为 `trace_id` 写到该请求产生的每条日志记录上，并在每个响应（包括错误响应）的 `X-Coffer-Trace` 响应头中返回。要查一次失败请求期间发生了什么：

```sh
curl -si -H "X-Coffer-Token: $TOKEN" http://127.0.0.1:38470/api/v1/resources/nope \
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

在 **设置 → 数据 → 历史记录** 中设置每个窗口。

天数至少为 1。Web 界面的 **历史记录** 区块只显示人们通常会调的两项——**改动**（`audit_log`）和**工具调用**（`mcp_invocations`）；其余策略保持上表中的默认值。缩短窗口会先请求确认，因为下一次清理会删除更早的行，确认框会显示将删除的数量；**立即清理过期数据** 会立即应用所有策略。修改策略本身也会以 `retention_updated` 审计。

守护进程日志是文件而不是表，所以没有策略：`daemon.log` 在 10 MB 时轮转，保留三份轮转文件。`~/.coffer/logs/` 中每个进程的 shim 日志和轮转出去的上游日志七天后删除。

## 工作原理 {#how-it-works}

审计列表为什么短、日志读取器如何规整各个写入方的格式、trace id 如何到达日志行，见[可观测性](/zh/architecture/observability)。

## 相关内容 {#related}

- [故障排查](/zh/guides/troubleshooting)
- [运行守护进程](/zh/guides/daemon#logs)
- [MCP 服务器](/zh/guides/mcp-servers)
- [MCP 工具参考](/zh/reference/mcp-tools)
- 规格：[resource-framework](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/resource-framework/spec.md)、[daemon](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/daemon/spec.md)
