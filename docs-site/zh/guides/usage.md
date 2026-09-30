---
title: 用量与额度
description: 你的智能体在 API 密钥 提供商和本地提供商上花了多少，可按模型、智能体或天查看——以及订阅套餐还剩多少额度（以厂商报告的为准）。
---

# 用量与额度 {#usage-and-quota}

根据智能体的登录方式，Coffer 回答两个不同的问题：

- **使用提供商的智能体**——网关或厂商的 API 密钥，或本地模型运行时——按 token 付费。Coffer 会统计它发出的每个请求，因为每个这样的请求都经过[本地模型中转](/zh/architecture/model-proxy)。
- **使用自己订阅登录的智能体**（Claude 或 ChatGPT 套餐）按固定费用付费，额度按滚动窗口计算。重要的是五小时窗口和每周窗口还剩多少额度，而只有厂商的服务器知道这个数。Coffer 显示的是厂商自己的数字，从不做估算。

## 用量页面 {#the-usage-page}

在侧边栏（「系统」下）打开**用量**。页面分两个独立加载的区块回答这两个问题——一个读不出来时，另一个照常显示。

**订阅额度**每个智能体（Claude Code、Codex）一行，显示它登录所用的套餐。每个窗口——五小时窗口和每周窗口——是一个进度条，显示用了多少以及何时重置（「Resets 16:30 · in 2 h 24 min」）。用到 90% 及以上的窗口变为琥珀色；到 100% 时以红色显示**已达上限**。行尾显示这个数字是何时看到的、来自哪里（Codex 是 _app-server_，Claude Code 是_最近一次回复_或_状态栏_）；Claude Code 那一行有自己的**刷新**，它会重新读取最近一次回复报告的数字。还没报告过任何数据的智能体显示**还没有额度读数**并等待；重置时间已过的窗口不显示数字，而不是显示过期的数字。如果手动读取 Codex 失败——比如它的 app-server 在回答前就退出了——这一行会说明原因，并提供**重试**。

切到 API 密钥 提供商的智能体没有套餐限额：它那一行显示 **API key · OpenAI**（提供商的厂商），写着**没有订阅额度**，并指向下面的区块，它的请求在那里按实际使用的提供商计量。使用订阅登录、但在所选时间范围内也有请求经过 API 密钥 提供商的智能体显示「Claude Max login · some requests **via API key**」。

**API 密钥提供商**涵盖经过 Coffer 本地中转的每个请求：

- 时间段控件可选**今天**、**7 天**（默认）、**30 天**、**本月**或**自定义…**。自定义范围在日历上选择；选择器会标出仍保留逐请求明细的最早一天——更早的日子只保留每日汇总，页面依然会报告它们。旁边的**智能体**和**提供商**筛选标签，可以把下面的所有内容缩小到一个智能体和一个提供商。时间范围、筛选和细分方式都是页面地址的一部分，所以刷新、书签或后退都会保留它们。
- 五个数字汇总整个范围：**费用（估算）**，附请求数和其中未定价的数量；**输入**（未缓存）、**输出**（含推理）、**缓存读取**和**缓存写入**（只有 Anthropic 的协议会报告这一类）。
- **每日费用**为范围内每一天画一根柱子；悬停在柱子上可看到当天日期和费用。今天的柱子颜色较浅，因为这一天还没过完。
- 表格可以把范围**按模型**（附提供它的提供商，并在**使用者**列里列出用过它的智能体）、**按智能体**（订阅型智能体的行带 **via API key** 标记）或**按天**（最新的在前，附每天用得最多的智能体；先显示最近一周，**Show all** 列出其余）细分，最后是一行合计——已定价模型的费用。没有价格的模型显示 **—**——从不显示 $0.00——它的提示说明原因以及去哪里设置价格；标有 `*` 的费用漏掉了部分未定价的请求，标有 `*` 的请求数包含了用量一直没到达的请求。悬停在标记上可看到数量。
- **在模型提供商中编辑价格**会带你到提供商页面，在那里设置模型自己的价格。

头部的**刷新**会重新读取所有内容，并向 Codex 询问它当前的额度。筛选旁边的 **⋯** 里有**导出 CSV**，它会下载当前范围、筛选和细分下的数据——与 `coffer usage --csv` 用相同选项写出的文件一致。

在还没有任何请求经过中转的机器上，API 密钥 区块只显示空状态——**还没有 API 密钥用量**，没有可缩小的范围或筛选——并链接到模型提供商：把某个智能体切到 API 密钥 提供商，才会开始计数。使用订阅登录的智能体从不经过 Coffer，所以对它们，页面只会显示额度。

## API 密钥 提供商和本地提供商的用量 {#usage-of-api-key-and-local-providers}

### 统计什么 {#what-is-counted}

中转对它发往上游的每个请求——包括故障切换的尝试——记录一行，内容有：

- 智能体（来自它的本地中转令牌）、会话和提供商；
- 智能体请求的模型、状态码，以及请求如何结束（`completed`、`error_event`、`truncated`、`client_cancel`、`upstream_error`、`connect_error`）；
- 首 token 时间和总耗时；
- 按类别分开的 token：**输入**（未缓存）、**缓存写入**（5 分钟和 1 小时）、**缓存读取**、**输出**（含推理），以及网页搜索请求数。

在最终用量事件之前就被截断的响应，用量计为**未知**，而不是零。Coffer 存储的任何内容都不包含提示词、生成结果或 key。

只统计经过中转的流量。其他工具用同一个 key 发出的请求，或智能体在切到该提供商之前发出的请求，都不计入。

### 查看 {#reading-it}

```sh
coffer usage                          # today, by model
coffer usage --range 7d --by agent    # last 7 days, by agent
coffer usage --range month --by day   # this calendar month, day by day
coffer usage --range custom --from 2026-09-01 --to 2026-09-15
coffer usage --agent codex --provider openai   # only Codex's requests through the provider "openai"
coffer usage --csv > usage.csv        # the same summary as CSV
coffer usage requests --limit 20      # the latest requests, newest first
```

范围按本地日期计算：**today**、**7d** 和 **30d**（都包含今天）、**month**（本自然月）以及 **custom**（两端都包含）。每个模型一行，写明提供它的提供商；每一行都列出发送其请求的智能体，多的在前。`--agent` 接受智能体类型（`claude_code`、`codex`），`--provider` 接受提供商名字；在 REST 上，它们是汇总和 CSV 的查询参数 `agent_type` 与 `connection_uid`。REST 路由是 `GET /api/v1/usage/summary`、`GET /api/v1/usage/requests` 和 `GET /api/v1/usage/export.csv`。

### 费用 {#cost}

费用是**估算值**，按模型和 token 类别分别计算：

- 每个请求按实际回答它的提供商的价格计价，价格取自第一个有价格的来源：你在提供商上**设置**的价格（中转商和代理商的收费各不相同）、**本地**运行时免费、列出模型时提供商**自己 API** 报告的价格，或 Coffer **随附**的价格表（pydantic 的 genai-prices：按提供商区分，含历史价格、长上下文档位和缓存价格）——它随每个版本发布，每天更新一次，除非在设置 › 通用里关掉了**刷新模型价格**。计算请求费用时从不临时查询价格。见[模型价格](./providers.md#model-prices)。
- 价格里没有列出的缓存类别按输入价格计费，所以估算值偏高。
- 没有任何来源定价的模型标为**未定价**并单独计数——从不按零计费。在你给提供商设置价格之前，它的费用在页面和 `coffer usage` 里显示为 `—`；这个横线的提示会写明所用价格表的日期。
- 每个请求的费用和计算时所用的价格一起存储，所以之后的价格表不会改写历史。

### 保留多久 {#how-long-it-is-kept}

逐请求的记录和 MCP 调用日志保留一样久（默认 30 天；用 `coffer config set retention.mcp_invocations <days>` 修改）。每日汇总保留一年。

## 订阅额度 {#subscription-quota}

```sh
coffer usage quota            # the latest windows per agent, with when they were seen
coffer usage quota --refresh  # ask Codex now
```

每个值都显示为其来源生成它那一刻的**快照**。没有新值时就不显示数字：Coffer 会说明上次看到它是什么时候，或者从没看到过。重置时间已过的窗口不显示数字。

### Codex {#codex}

Coffer 询问 Codex 自己的 `codex app-server`（`account/rateLimits/read`），这与 Codex 的 `/status` 用的是同一个来源。你要求时它会读取；Codex 智能体使用自己的登录时，后台最多每五分钟读一次；手动刷新最多每 30 秒一次。Coffer 驱动的会话也会实时推送更新。每个窗口显示已用百分比、窗口长度和重置时间。

### Claude Code {#claude-code}

Claude Code 在 Coffer 驱动的会话（[对话](/zh/guides/chat)和[消息渠道](/zh/guides/channels)轮次）里报告它的额度：每个 `rate_limit_event` 都会更新五小时窗口和每周窗口。因此，一个你只在自己终端里使用的 Claude Code 智能体什么都不会显示——除非你主动启用下面的 statusline 包装。

Coffer 从不读取 Claude Code 或 Codex 的登录令牌，也从不调用未公开的用量端点：Anthropic 的条款禁止其他工具收集 claude.ai 令牌，而上面这些数字不需要令牌就能拿到。

### 可选：Claude Code 的 statusline {#opt-in-claude-code-s-statusline}

Claude Code 每次刷新时都会把有文档说明的 `rate_limits` 对象传给 statusline 命令。`coffer usage statusline` 把它转发给 Coffer，然后用同样的输入运行你自己的 statusline 命令，并打印它的输出——所以即使守护进程没在运行，你的 statusline 也照常工作。Coffer 从不自动安装它，用量页面上也没有会修改你设置的开关。当 Claude Code 还没有读数时，它那一行会提供一段给智能体的提示词（**复制提示词**或**交给智能体**；`coffer usage quota --prompt` 打印同样的文本）：提示词写明你 Claude Code 智能体的 `settings.json`，请智能体把你当前的 `statusLine.command` 包装成 `coffer usage statusline -- '<it>'`（或者添加一个只运行 `coffer usage statusline` 的命令），并在保存前把 diff 给你看。要自己动手，就在 `~/.claude/settings.json`（或你的 Claude Code 智能体所用的配置目录）里设置：

```json
{
  "statusLine": {
    "type": "command",
    "command": "coffer usage statusline -- ~/.claude/my-statusline.sh"
  }
}
```

`--` 后面没有命令时，它什么都不打印。它最多等守护进程一秒，而且从不启动守护进程。

## 相关 {#related}

- [模型提供商](/zh/guides/providers)——把智能体切换到提供商
- [本地模型中转](/zh/architecture/model-proxy)——请求如何被转发和计量
