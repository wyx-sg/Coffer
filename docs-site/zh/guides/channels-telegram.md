---
title: Telegram
description: 为 Coffer 配置 Telegram 消息渠道：用 BotFather 创建机器人，保存它的令牌，登记消息渠道，配对你的账号，然后和智能体聊天。
---

# Telegram {#telegram}

本指南从零开始配置一个 Telegram 消息渠道：用 BotFather 创建机器人，把它的令牌存进 Coffer，登记消息渠道，配对你的账号，拿到智能体的第一条回复。然后介绍媒体、群组、上限和故障排查。所有消息渠道共有的部分（命令、生效范围、安全）见[消息渠道](/zh/guides/channels)。

Telegram 是你完全可以自己搞定的消息渠道。它不需要公网 URL、不需要隧道、不需要厂商 SDK，也不需要组织审批：Coffer 通过出站连接长轮询 `api.telegram.org` 上的 Telegram Bot API。

## 前提条件 {#prerequisites}

- 守护进程正在运行，且至少登记了一个智能体。见[快速开始](/zh/start/quickstart)。
- Telegram 应用，已登录你想用来拥有这个消息渠道的账号。

## 1. 创建机器人 {#_1-create-a-bot}

1. 在 Telegram 里打开和 [@BotFather](https://t.me/BotFather) 的聊天。
2. 发送 `/newbot`，然后选一个显示名，以及一个以 `bot` 结尾的用户名（比如 `my_coffer_bot`）。
3. BotFather 会回复机器人的令牌，形如 `123456789:AAH…`。复制它。

::: danger
令牌就是对这个机器人的完全控制权。别让它出现在聊天记录、截图和 shell 历史里。如果泄露了，给 BotFather 发 `/revoke`，并在 Coffer 里轮换它（见[轮换令牌](#rotate-the-token)）。
:::

你不需要设置描述或命令列表：Coffer 启动时会注册机器人的命令菜单，并填上空着的描述。你自己在 BotFather 里设置的描述会保持原样。

## 2. 登记消息渠道 {#_2-register-the-channel}

```text [Web UI]
Channels → Add channel
  1 Platform:       Telegram
  2 Connect:
      Name:           my-telegram
      Default agent:  claude-code
      Bot token:      123456789:AAH…
    → Connect
  3 Pair:           the code to send the bot (or Pair later)
```

默认智能体是一个已登记的智能体，和**智能体**页面列出的一致。消息渠道只保存在本机，并立刻开始轮询。无法解析的令牌引用会被拒绝，不会保存任何东西。

确认它在运行：消息渠道的页头会显示它的状态和运行位置。

## 3. 配对你的账号 {#_3-pair-your-account}

1. 生成一个配对码：在消息渠道的**总览**里点**生成配对码**。对话框会显示配对码和配对链接。

2. 在登录了你账号的手机上打开配对链接（网页上的**在 Telegram 中打开**），点 **Start**。或者打开机器人，把 `K7QM3XPA` 作为消息发过去。
3. 机器人确认配对，并发一次帮助信息。你就是所有者了。

配对码只能用一次，一小时后过期，猜错 10 次后作废。配对之前，机器人不回复任何人。

## 4. 发送第一条消息 {#_4-send-your-first-message}

给机器人发一条消息，比如 `list the files in my home directory`。你应该看到：

1. Coffer 一收到消息，你的消息上就出现 👀 表情回应，轮次开始时变成 👨‍💻；
2. 较长的轮次会显示状态行（`⏳ Working · 12s · 2 steps`，然后是最新的步骤），以及正在写的回复；
3. 格式化好的最终回复，状态行被移除；
4. 轮次结束时你的消息上出现 👌 回应；失败是 😢，被停止是 🤷。Telegram 只允许机器人用一份固定的 emoji 列表做回应，这几个都在列表里。

在 Web 界面打开**对话**，同一个对话就在那里，消息渠道显示 `Telegram · DM`（悬停可看到消息渠道名称）。

## 回复的样子 {#how-replies-look}

Telegram 回复是根据智能体的 Markdown 构建的。

- **富文本消息**：如果 Coffer 连到的 Bot API 服务器支持，带标题、列表、表格或代码的回复会以保留这些结构的富文本消息发送。
- **HTML 回退**：否则回复会转换成 Telegram 支持的 HTML 子集，按段落边界拆成每条最多 4,000 个字符的消息。Telegram 拒收的 HTML 片段会以纯文本重发。
- **实时进度**：在私聊中，如果服务器支持消息草稿，回复会流进一个草稿，草稿上还带 Telegram 自己的停止按钮，按下它等同于 `/stop`。如果服务器支持富文本草稿，状态头会放在草稿可折叠的思考区块里。在群组中，轮次运行超过约 1.5 秒后会出现一条状态消息，随轮次进展被编辑，发送最终回复时被删除；它是静默发送的，不会让群里的手机震动。很快完成的回复根本不会产生状态消息。
- **提及**：在群组中，每个回答都是对你消息的回复，并以一个真正的 @ 提及开头，所以即使群很热闹你也会收到通知。
- **撤回**：群组里每条回复都带一个内联 🗑 按钮，所有者也可以引用一条回复并发送 `/del`。两种方式都会删除整个回复，不论它被拆成了几条消息。Telegram 允许机器人删除 48 小时内的消息；超过之后会私下告诉所有者已无法删除。如果机器人在该聊天里有删除消息的权限，Coffer 也会删掉 `/del` 这条消息；想让聊天保持整洁，就给它这个权限。只有所有者的点击才算数。群组回复仍按上文所述流式输出。见[撤回回复](/zh/guides/channels#withdrawing-a-reply)。
- **详情**：`## Details` 小节会被折叠：富文本消息里是 `<details>` 区块，HTML 回退里是可展开的引用。
- **私密的命令回答**：在群组中，如果服务器支持临时消息，`/help` 的回答，以及「该命令只能在私聊里用」的那一行提示，只显示给你。
- **卡片**：在私聊里，不带参数的 `/model`、`/dir` 或 `/resume` 会回复一个内联键盘；`/status` 带 **New**、**Model**、**Resume** 和 **Dir** 按钮（轮次运行时还有 **Stop**）。`/help` 在私聊里带 **New**、**Stop**、**Model**、**Status** 和 **Resume**，在群组里只带 **New** 和 **Stop**。`/new` 在私聊里带 **Agent**、**Model** 和 **Dir**，在群组里只带 **Agent**。卡片标题是一个标题行或加粗的第一行。

Coffer 会对每个较新的 Bot API 能力（富文本消息、草稿、富文本草稿、临时消息）各探测一次。如果服务器以不支持为由拒绝，Coffer 在守护进程的整个生命周期里都不再尝试，改用较旧的机制，所以旧服务器损失的是格式和实时性，而不是送达。

## 命令菜单 {#command-menus}

每次消息渠道启动，Coffer 都会向 Telegram 注册机器人的命令菜单，内容和帮助文本用的是同一份列表：

| 位置 | 菜单里的命令 |
| --- | --- |
| 私聊 | 全部九个：`/new`、`/stop`、`/model`、`/dir`、`/status`、`/resume`、`/thread`、`/del`、`/help` |
| 群组 | `/new`、`/stop`、`/del`、`/help` |

每个菜单注册两遍，一遍英文描述，一遍中文描述，所以设成中文的 Telegram 客户端会显示中文菜单。隐藏的 `/start` 从不列出。

从群组菜单点的命令会以 `/status@my_coffer_bot` 的形式到达。Coffer 把它当作发给本机器人的 `/status`，所以即使群组要求 @ 提及，它也会回答。点名另一个机器人的命令（比如 `/status@some_other_bot`）不是给它的，会被忽略。

## 媒体 {#media}

Telegram 能附在消息上的每种类型都会驱动一个轮次：照片、文档、语音消息、音频、视频、动图、贴纸和圆形视频消息。

- 照片按最大尺寸接收。说明文字会成为消息正文。
- 相册（一起发送的几张照片）会收集一秒钟，作为**一个**轮次处理，带上全部图片和相册的说明文字。
- PDF 之类的文档会提取成文字交给智能体。打开语音转文字时（**设置 › 通用 → 语音转文字**），语音和音频会被转写；否则智能体拿到的是音频文件。
- 超过 20 MB 的文件（Bot API 对机器人的下载上限）永远不会被拉取。轮次文字里会注明一次，所以智能体的回复会提到它没收到这个文件。
- 下载失败的文件会记为 `[attachment '<name>' could not be downloaded]`，轮次用消息的其余部分继续运行。

智能体用一行 `MEDIA:/absolute/path` 把文件发回来；图片以照片形式送达，其他文件以文档形式送达，最大 50 MB。见[消息渠道 → 回传文件](/zh/guides/channels#sending-files-back)。

::: info 令牌从不进日志
Telegram 的文件 URL 里包含机器人令牌，所以下载失败只按错误类别或 HTTP 状态记录，从不记录 URL。
:::

## 私聊里的并行对话 {#parallel-conversations-in-a-private-chat}

`/thread [title]` 会打开一个名为 `🧵#N title` 的私聊话题，其中的消息在它自己的对话里运行（[并行对话](/zh/guides/channels#parallel-conversations)）。Telegram 只为开启了 **Threaded Mode** 的机器人创建私聊话题：在 BotFather 里打开机器人的设置，把它打开。没有开启时，`/thread` 会回复这条说明，什么也不打开。你自己在私聊里创建的任何话题也各自是一个对话。

## 群组和论坛话题 {#groups-and-forum-topics}

1. 把机器人加进群组。
2. @ 提及它（`@my_coffer_bot summarise the last deploy`），或回复它的某条消息。
3. 机器人会以回复你消息的形式作答。在开启了论坛功能的超级群组里，它会在你发言的那个话题里回答。

所有者第一条发给机器人的消息会把这个群组登记为该消息渠道的一个对端。其他成员的消息会被拒绝，并收到一句简短回复。

Telegram 的 Bot API 读不到聊天历史，所以机器人从不读取群组或话题里更早的消息：它只回答提及它的那条消息。引用你指的那条消息，或者把上下文写进你自己的消息里。

Bot API 只报告普通消息正文里的提及，所以照片或文件说明文字里的 @ 提及不会被识别。请在单独的一条文字消息里提及机器人。

### 隐私模式 {#privacy-mode}

Telegram 机器人默认**开启隐私模式**，即机器人只能看到提及它、回复它或者是命令的消息。这正是默认的 `require_mention: true` 所期望的，所以不需要改。

如果你关掉 `require_mention`，让机器人对群组里所有者的每条消息都做出反应（消息渠道的**设置** → **接收消息** → **仅在被 @ 时回复**），机器人还需要能看到这些消息：

1. 在 BotFather 里发送 `/setprivacy`，选择这个机器人，再选 **Disable**。
2. 把机器人移出群组再重新加入。这个改动只对机器人之后加入的群组生效。

在你这么做之前，消息渠道页面会显示一条警告，写明这个修复办法。

## 轮换令牌 {#rotate-the-token}

在消息渠道页面在 Telegram 拒绝旧令牌时选择横幅里的**更换 token**，或者**设置** → **连接**下的**更换密钥…**；把新令牌粘贴到 **Bot token**，然后选**更换并重启**。粘贴时 Coffer 会向 Telegram 检查这个令牌，并显示**可用——这是 @your_bot**；如果是同一个机器人，还会说明配对仍然有效；被 Telegram 拒绝的令牌会在字段下说明。令牌会写到消息渠道已经在用的那个引用下，所以配对不受影响。

## 上限 {#limits}

| 上限 | 值 |
| --- | --- |
| 回复消息长度 | 每条 4,000 个字符，按段落拆分 |
| 接收文件大小 | 20 MB（Bot API 下载上限） |
| 发送文件大小 | 50 MB |
| 相册收集窗口 | 1 秒 |
| 每张卡片的按钮数 | 6 个，含翻页；callback data 最多 64 字节 |
| 每个对话的等待消息数 | 10 |

## 故障排查 {#troubleshooting}

**机器人完全不回复。**
在**消息渠道**下打开该渠道的页面。

- 页头显示它没有运行：消息渠道已关闭，或者没有可用的默认智能体。状态和消息渠道页面会说明是哪种。
- 总览的**谁可以使用**里没有任何人：先配对。未配对的机器人不回复任何人。

**机器人回复了别人，或者在配置第二台机器后不再回复。**
有两个消费者在轮询同一个机器人。同一个令牌被登记了两次（在两个消息渠道名下，或者在两台机器上）时就会这样（Telegram 会对第二个轮询方返回 `409 Conflict`）。只保留一个登记，见[在另一台机器上使用机器人](/zh/guides/channels#using-the-bot-on-another-machine)。

**机器人忽略群组里的消息。**
提及它或回复它。如果你关掉了 `require_mention`，检查上面提到的隐私模式警告。

**守护进程日志里反复出现 `telegram.poll.retry`。**
轮询一直失败。除了网络问题，当另一个程序在轮询同一个机器人，或者机器人设置了 webhook（比如你之前测试过的某个机器人框架设的）时，Telegram 也会拒绝 `getUpdates`。Coffer 不会替你删除 webhook：停掉另一个程序，或者用 Bot API 的 `deleteWebhook` 方法清除 webhook。Coffer 会自己退避并恢复。**活动 → 守护进程日志**会显示这些记录。

**格式看起来很平。**
Bot API 服务器不提供富文本消息，所以回复用的是 HTML 回退。所有内容仍然会送达。

## 相关 {#related}

- [消息渠道](/zh/guides/channels)：所有消息渠道的命令、生效范围和安全。
- [SeaTalk](/zh/guides/channels-seatalk)
- [密钥存储](/zh/guides/secret-store)
- [规格：channels/telegram](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/channels/telegram/spec.md)
