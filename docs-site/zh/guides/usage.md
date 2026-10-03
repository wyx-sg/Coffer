---
title: 用量
description: 你的智能体通过 API 密钥 提供商和本地提供商花了多少，可按模型、智能体或天在「模型提供商」的用量标签页查看。
---

# 用量 {#usage}

智能体通过 API 密钥或本地提供商花了多少，Coffer 会统计，因为每个这样的请求都经过[本地模型中转](/zh/architecture/model-proxy)。

使用自己订阅登录的智能体（Claude 或 ChatGPT 套餐）从不经过 Coffer，所以 Coffer 对它什么也不显示。套餐还剩多少额度只有厂商知道，请在厂商自己的应用里查看。

## 用量标签页 {#the-usage-tab}

在侧边栏打开**模型提供商**，切到它的**用量**标签页（地址为 `/model-providers?tab=usage`）。页面涵盖经过 Coffer 本地中转的每个请求：

- 时间段控件可选**今天**、**最近 7 天**（默认）、**最近 30 天**、**本月**或**自定义范围…**。自定义范围在日历上选择，最多回溯 90 天；选择器会标出仍保留逐请求明细的最早一天，因为更早的日子只保留每日汇总。旁边的**智能体**和**提供商**筛选标签，可以把下面的所有内容缩小到一个智能体和一个提供商。时间范围、筛选和细分方式都是页面地址的一部分，所以刷新、书签或后退都会保留它们。
- 四个数字汇总整个范围：**费用（估算）**，附请求数和其中未定价的模型数；**输入**（未缓存）、**输出**（含推理）、**缓存读取**和**缓存写入**（只有 Anthropic 的协议会报告这一类）。
- **每日费用**为范围内每一天画一根柱子；悬停在柱子上可看到当天日期和费用。今天的柱子颜色较浅，因为这一天还没过完。
- 表格可以把范围**按模型**（附提供它的提供商，并在**使用者**列里列出用过它的智能体）、**按智能体**或**按天**（最新的在前，附每天用得最多的智能体；先显示最近一周，“Showing 7 of N days”，**Show all** 列出其余）细分，最后是一行合计——已定价模型的费用。没有价格的模型显示 **—**——从不显示 $0.00——它的提示说明原因以及去哪里设置价格；标有 `*` 的费用漏掉了部分未定价的请求，标有 `*` 的请求数包含了用量一直没到达的请求。悬停在标记上可看到数量。
- 表格底部的**编辑价格**会带你到提供商页面，在那里设置模型自己的价格。
- 筛选旁边的**导出 CSV**会下载当前范围、筛选和细分下的数据，与 `coffer usage --csv` 用相同选项写出的文件一致。

在还没有任何请求经过中转的机器上，这个标签页只显示空状态——**还没有 API 密钥用量**，没有可缩小的范围或筛选——并带一个**提供商**链接：把某个智能体切到 API 密钥 提供商，才会开始计数。

## 统计什么 {#what-is-counted}

中转对它发往上游的每个请求——包括故障切换的尝试——记录一行，内容有：

- 智能体（来自它的本地中转令牌）、会话和提供商；
- 智能体请求的模型、状态码，以及请求如何结束（`completed`、`error_event`、`truncated`、`client_cancel`、`upstream_error`、`connect_error`）；
- 首 token 时间和总耗时；
- 按类别分开的 token：**输入**（未缓存）、**缓存写入**（5 分钟和 1 小时）、**缓存读取**、**输出**（含推理），以及网页搜索请求数。

在最终用量事件之前就被截断的响应，用量计为**未知**，而不是零。Coffer 存储的任何内容都不包含提示词、生成结果或 key。

只统计经过中转的流量。其他工具用同一个 key 发出的请求，或智能体在切到该提供商之前发出的请求，都不计入。

## 查看 {#reading-it}

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

## 费用 {#cost}

费用是**估算值**，按模型和 token 类别分别计算：

- 每个请求按实际回答它的提供商的价格计价，价格取自第一个有价格的来源：你在提供商上**设置**的价格（中转商和代理商的收费各不相同）、**本地**运行时免费、列出模型时提供商**自己 API** 报告的价格，或 Coffer **随附**的价格表（pydantic 的 genai-prices：按提供商区分，含历史价格、长上下文档位和缓存价格）——它随每个版本发布，每天更新一次，除非在设置 › 通用里关掉了**刷新模型价格**。计算请求费用时从不临时查询价格。见[模型价格](./providers.md#model-prices)。
- 价格里没有列出的缓存类别按输入价格计费，所以估算值偏高。
- 没有任何来源定价的模型标为**未定价**并单独计数——从不按零计费。在你给提供商设置价格之前，它的费用在页面和 `coffer usage` 里显示为 `—`；这个横线的提示会写明所用价格表的日期。
- 每个请求的费用和计算时所用的价格一起存储，所以之后的价格表不会改写历史。

## 保留多久 {#how-long-it-is-kept}

逐请求的记录和 MCP 调用日志保留一样久（默认 30 天；用 `coffer config set retention.mcp_invocations <days>` 修改）。每日汇总保留一年。

## 相关 {#related}

- [模型提供商](/zh/guides/providers)——把智能体切换到提供商
- [本地模型中转](/zh/architecture/model-proxy)——请求如何被转发和计量
