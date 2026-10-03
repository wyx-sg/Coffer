---
title: 用量
description: 你的智能体在 API 密钥提供商和本地提供商上花了多少，可按模型、智能体或天查看——模型提供商的用量 tab 和 coffer usage 命令——以及在命令行里，订阅套餐还剩多少额度。
---

# 用量 {#usage}

用量是**模型提供商**的第二个 tab，地址是 `/model-providers/usage`。它回答一个问题：你的智能体经由 API 密钥提供商或本地提供商发出的请求花了多少？使用提供商的智能体按 token 付费，Coffer 会统计它发出的每个请求，因为每个这样的请求都经过[本地模型中转](/zh/architecture/model-proxy)。使用自己订阅登录的智能体从不经过 Coffer，所以不会出现在这里。

## 用量 tab {#the-usage-tab}

打开**模型提供商**，在**提供商**旁选择**用量**。页头——标题、**实验**标签和**添加提供商**——与提供商 tab 上的是同一个。侧边栏里没有「用量」条目。

- 筛选行从**时间范围**开始——**今天**、**最近 7 天**（默认）、**最近 30 天**、**本月**或**自定义范围…**，按日期选择；选择器会说明哪一天起仍有逐请求明细，因为更早的日子只保留每日汇总，页面仍会报告它们。接着是**智能体**和**提供商**，把下面的一切缩小到一个智能体和一个提供商，最右边是**导出 CSV**，它下载的正是你正在看的范围、筛选和分组——和 `coffer usage --csv` 用同样选项写出的是同一个文件。范围、筛选和分组都是页面地址的一部分，所以刷新、书签或后退都会保留它们。没有刷新按钮：这些数字是 Coffer 自己的。
- 五个数字汇总该范围：**费用（估算）**——它的帮助提示说明估算怎么算——带请求数、**输入**（未缓存）、**输出**（含推理）、**缓存读取**和**缓存写入**（只有 Anthropic 的线路协议会报告的类别）。如果有些模型没有价格，**1 个模型未定价**只会在费用这个数字里出现一次，是一个指向它所在提供商里那个模型的链接，在那里你可以设置价格；页面上其他地方不会重复它。
- **每日费用**为范围内的每一天画一根柱；悬停可看那天的日期和费用。今天的柱颜色较浅，因为这一天还没结束。
- 表格把范围按**按模型**（带服务它的提供商，以及用过它的智能体）、**按智能体**或**按天**（最新的在前；最近一周先显示，**显示全部**列出其余）拆开，末尾是汇总行——已定价模型的费用。没有价格的模型显示 **—**——从不是 $0.00——悬停提示会说明原因和去哪里设置；标了 `*` 的费用漏掉了一些未定价的请求，标了 `*` 的请求数包含了用量始终没到的请求。把鼠标悬停在标记上可看数量。

在还没有任何请求经过中转的机器上，这个 tab 只有它的空状态——**还没有 API 密钥用量**，带**打开提供商**，没有范围或筛选可缩小：把智能体切换到 API 密钥提供商才是开始计数的起点。关闭「模型」[实验功能](/zh/guides/experimental-features)后，这个 tab 和整个页面会像该功能的其余部分一样消失。

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
- 没有任何来源定价的模型标为**未定价**并单独计数——从不按零计费。在你给提供商设置价格之前，它的费用在 tab 和 `coffer usage` 里显示为 `—`。
- 每个请求的费用和计算时所用的价格一起存储，所以之后的价格表不会改写历史。

### 保留多久 {#how-long-it-is-kept}

逐请求的记录和 MCP 调用日志保留一样久（默认 30 天；用 `coffer config set retention.mcp_invocations <days>` 修改）。每日汇总保留一年。

## 订阅额度 {#subscription-quota}

Web 界面不显示订阅额度。对使用自己登录的智能体，Coffer 仍可以从命令行和 REST API（`GET /api/v1/usage/quota`）读取厂商自己报告的剩余额度：

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

Claude Code 每次刷新时都会把有文档说明的 `rate_limits` 对象传给 statusline 命令。`coffer usage statusline` 把它转发给 Coffer，然后用同样的输入运行你自己的 statusline 命令，并打印它的输出——所以即使守护进程没在运行，你的 statusline 也照常工作。Coffer 从不自动安装它，也没有任何地方会替你修改设置。当 Claude Code 还没有读数时，`coffer usage quota --prompt` 会打印一段给智能体的提示词：提示词写明你 Claude Code 智能体的 `settings.json`，请智能体把你当前的 `statusLine.command` 包装成 `coffer usage statusline -- '<it>'`（或者添加一个只运行 `coffer usage statusline` 的命令），并在保存前把 diff 给你看。要自己动手，就在 `~/.claude/settings.json`（或你的 Claude Code 智能体所用的配置目录）里设置：

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
