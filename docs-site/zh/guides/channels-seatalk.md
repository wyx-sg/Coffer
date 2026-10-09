---
title: SeaTalk
description: 为 Coffer 配置 SeaTalk 消息渠道：创建 SeaTalk 开放平台应用，提供 WebSocket SDK，登记并配对消息渠道，然后在私聊、群组和线程里使用。
---

# SeaTalk {#seatalk}

本指南配置一个 SeaTalk 消息渠道：在 SeaTalk 开放平台上创建机器人应用，提供 SeaTalk 的 WebSocket SDK，在 Coffer 里登记消息渠道，把应用切换到 WebSocket 投递，并配对你的账号。然后介绍群组、线程、引用消息、卡片、上限和故障排查。所有消息渠道共有的部分（命令、生效范围、安全）见[消息渠道](/zh/guides/channels)。

没有哪个智能体有官方的 SeaTalk 集成，所以你在 SeaTalk 里和智能体做的一切都经过这个消息渠道。

## SeaTalk 如何连接 {#how-seatalk-connects}

Coffer 通过**每个消息渠道一条出站 WebSocket 连接**接收 SeaTalk 事件。守护进程主动连到 SeaTalk，用应用的 ID 和 secret 认证，SeaTalk 再通过这条连接推送事件。不暴露任何东西：没有公网 URL、没有监听端口、没有隧道，也没有要校验的签名。回复和通知通过 HTTPS 发往 `openapi.seatalk.io`。

由此带来两点：

- **WebSocket 客户端是 SeaTalk 自己的 SDK，需要你自己提供。** 它从 SeaTalk 的门户分发，不在公共 PyPI 上，也没有公开许可证，所以 Coffer 不能随包发布或依赖它。没有它，SeaTalk 消息渠道能发送，但收不到任何东西。
- **每个 SeaTalk 应用只有一条连接。** 第二个进程登记同一个应用（另一台机器，或同事在测试）会把连接抢走。只在一台机器上把 SeaTalk 应用登记为消息渠道。

## 前提条件 {#prerequisites}

- 守护进程正在运行，且至少登记了一个智能体。见[快速开始](/zh/start/quickstart)。
- 能访问 [SeaTalk 开放平台](https://open.seatalk.io/)，有创建应用的权限，并拿到你所在组织对相关权限范围要求的审批。

## 1. 创建 SeaTalk 应用 {#_1-create-the-seatalk-app}

1. 在 SeaTalk 开放平台上创建一个应用。
2. 启用 **Bot** 能力，并把机器人设为 **Online**。
3. 申请机器人需要的权限范围。最少需要 *Send Message to Bot User*；可能需要你们组织的管理员审批。如果希望消息渠道的主人列表显示每位主人的 SeaTalk 头像，再加上 *Get Employee Profile*；没有它时列表显示姓名首字母。
4. 记下应用的 **App ID** 和 **App Secret**。

事件投递设置留到第 4 步：只有在 Coffer 持有连接时，SeaTalk 才能校验 WebSocket 投递。

## 2. 提供 WebSocket SDK {#_2-supply-the-websocket-sdk}

1. 从 SeaTalk 开放平台下载 SeaTalk 用于 WebSocket 事件回调的 Python SDK。包名是 `seatalk_oapi_sdk`；见 SeaTalk 的 [WebSocket Event Callback](https://open.seatalk.io/docs/WebSocket-Event-Callback) 文档。下载这一步由你来做，因为它在平台的登录之后。
2. 其余的交给你的智能体。消息渠道登记好之后（第 3 步），等待 SDK 的消息渠道会显示**未安装 SeaTalk 的 Python SDK**，链接到 SeaTalk 的下载页面，并提供**交给 &lt;Agent&gt;**（它的菜单可复制提示词；没有 Coffer 托管的智能体可用时只提供**复制提示词**）：一段让智能体把压缩包解压到 Coffer vendor 目录的提示词。放好之后点**重试**。

SDK 由 `coffer-seatalk-bridge` 加载，这是放在守护进程旁边的一个独立程序，读不到主密钥。守护进程从不导入 SDK：那个目录是你的智能体可写的，放进去的代码不该在能读到主密钥的地方运行。SeaTalk 消息渠道启动时，守护进程才启动桥接进程，在它的标准输入上交给它应用 ID 和应用密钥，并从它读回渠道的事件。SDK 缺失时它会一直重试。你可以在登记消息渠道之前或之后添加 SDK；已经在等待的消息渠道不用重启守护进程就能用上它。

要手动处理，就解压压缩包，让包目录位于 Coffer 的 vendor 目录下：

```text
~/.coffer/vendor/seatalk_oapi_sdk/
```

想放在别处，就在守护进程启动的环境里，把 `COFFER_SEATALK_SDK_DIR` 设为**包含** `seatalk_oapi_sdk/` 的那个目录。

## 3. 登记消息渠道 {#_3-register-the-channel}

```text [Web UI]
Channels → Add channel
  Type:           SeaTalk
  Name:           my-seatalk
  App ID:         <APP_ID>
  App secret:     <APP_SECRET>
  Default agent:  claude-code
→ Create
```

配置内容是 App ID 和指向 App Secret 的引用，外加每个消息渠道都有的字段。消息渠道只保存在本机，并立刻开始连接。

检查连接：消息渠道状态行上的 **SeaTalk connection** 标记连上后显示**已连接**（Connected）。等到它连上再做下一步。

## 4. 把应用切换到 WebSocket 投递 {#_4-switch-the-app-to-websocket-delivery}

1. 在 SeaTalk 开发者后台打开应用的事件回调设置，把投递方式设为 **WebSocket**。SeaTalk 每个机器人只允许一种投递方式。
2. 点 **Re-verify**。只有 Coffer 持有实时连接时它才能通过，这就是为什么要先登记消息渠道。

## 5. 配对你的账号 {#_5-pair-your-account}

1. 在消息渠道的**总览**里选**生成配对码**。
2. 在 SeaTalk 里打开和机器人的私聊，发送那个八位配对码。
3. 机器人确认配对，并发一次帮助卡片。SeaTalk 没有命令菜单，所以机器人靠这张卡片告诉你它接受什么；发送 `/help` 可以再看一次。

SeaTalk 没有启动链接，所以要你手动输入配对码。它只能用一次，一小时后过期，猜错 10 次后作废。

给机器人发一条消息。输入中提示会立刻出现，轮次结束时答案作为一条新消息送达，对话会出现在 Web 的[对话](/zh/guides/chat)页面上，消息渠道显示为 `SeaTalk · DM`。

## 连接状态 {#connection-states}

消息渠道页面上的 **SeaTalk connection** 标记把连接作为消息渠道的入站状态报告。通过 REST 读取时，字段是 `status.inbound.websocket_state` 和 `status.inbound.websocket_error`。

| 状态 | 消息渠道页面上的显示 | 含义 |
| --- | --- | --- |
| `connecting` | **连接中** — 连接中…（尝试失败后为**重连中** — 重连中…） | 正在向 SeaTalk 注册。 |
| `connected` | **已连接** | 事件正在流入。 |
| `kicked` | **被挤下线** — 连接被另一个进程占用 | 另一个进程登记了同一个应用。Coffer 会等 60 秒再试，而不是去抢连接。 |
| `sdk_missing` | **无法启动** — 未找到 SeaTalk SDK | 桥接进程无法导入 `seatalk_oapi_sdk`。错误信息会写明搜索过的目录。 |
| `rejected` | **Token 被拒** — 连接被拒绝 | SeaTalk 在注册握手时拒绝了这个应用：App ID 有误，或 App Secret 已在 SeaTalk 开放平台重新生成。横幅提供**更换密钥**；`websocket_error` 原样保存 SeaTalk 的回答。Coffer 会继续重试，所以在同一引用下更换密钥后会自行恢复。 |
| `error` | **网络问题** — 连不上平台——正在重试 | 上一次尝试在途中失败（DNS 失败、超时、连接断开），不是 SeaTalk 拒绝了这个应用；`websocket_error` 原样保存错误信息。Coffer 以 1 到 30 秒的退避重试，横幅提供**立即重新连接**，不会让你更换密钥。 |

第一次尝试之前没有连接状态：消息渠道打开后约两秒内守护进程就会启动它，在那之前 `status.starting` 为 true，页面显示**连接中**，不会显示失败。连接断开期间 SeaTalk 发来的事件，Coffer 不会在任何地方排队保存。

## 回复的样子 {#how-replies-look}

- **轮次运行期间**：SeaTalk 没有表情回应，也不能编辑文字消息，所以表示正在工作的只有输入中提示。它会立刻出现，每 3 秒续一次，直到回复发出，私聊和群组线程都是如此。超过 200 人的群组里，SeaTalk 会悄悄跳过群组输入中提示。
- **私聊**：答案以一条普通的新消息送达，所以 SeaTalk 会像对待任何消息一样通知你。只发送智能体在最后一次工具调用之后写的内容；它在步骤之间说的话不会发出。长答案会在段落边界拆成几条消息，第一条之后的每条都编号为 `(2/3)`、`(3/3)`。
- **群组**：完成的答案以一张交互卡片送达，太长则拆成几张卡片，开头会 @ 提问的人。用卡片是因为 SeaTalk 能重写卡片，却不能删除或编辑别的消息，所以所有者才能撤回群组回复（见下）。每张卡片都带一个 🗑 按钮。
- **格式**：智能体的 Markdown 会转成 SeaTalk Markdown：粗体、斜体、行内代码、代码块和列表。标题变成粗体，链接变成 `label (url)`，因为 SeaTalk 两者都不支持。表格变成每行一个列表项（大表格还会以 `.csv` 附上），超过 30 行的代码块以文件形式送达。消息会被拆分，保持在 SeaTalk 4,096 字节的上限以内。
- **长小节**：SeaTalk 不能折叠文字，所以答案会完整送达，包括智能体放在 `## Details` 这类标题下的小节。
- **撤回回复。** SeaTalk 开放平台没有删除机器人消息的 API，只有交互卡片可以重写，而且只能由发送它的机器人重写。所以当所有者撤回一条群组回复时——点它的 🗑 按钮，或引用它并发送 `/del`——Coffer 会把这条回复的每张卡片重写成一张中性的「🗑 Withdrawn」卡片，不带按钮。文字从聊天里消失，卡片本身还在。SeaTalk 允许重写 7 天；超过之后会私下告诉所有者该回复已无法撤回。只有所有者的点击或命令才算数；不引用的 `/del` 撤回群组或话题里最近的一条回复。私聊里的回复是普通消息，在 SeaTalk 上无法撤回。见[撤回回复](/zh/guides/channels#withdrawing-a-reply)。

## 群组和线程 {#groups-and-threads}

1. 把机器人加进群组。
2. @ 提及它。SeaTalk 只把 @ 提及投递给机器人；其他群消息永远到不了 Coffer。
3. 所有者的第一次 @ 提及会把这个群组登记为消息渠道的一个对端。其他人的提及会收到一句简短的 "not authorized" 回复。

回答会发到哪里：

- **在群组主聊天里 @ 提及**：机器人以你的消息为根开一个线程，在那里回答。它不读历史：线程里只有你的消息。
- **在线程里 @ 提及**：机器人读取这个线程，并在其中回答。一个对话第一次在某个线程里回答时，它的轮次带上该线程最近的 20 条消息，以及其中的图片和文件。这个对话之后在该线程里的每个轮次，只带上自它上一轮以来其他人发的消息——没有新消息就什么都不带——因为智能体的会话里已经有了其余内容。较早的消息被略去时，线程块末尾有一行说明略去了多少条，智能体可以用 `coffer__channel_read_thread` 工具一页一页地读取。在线程里发 `/new` 会重新从最近的 20 条开始。
- **私聊里的线程**：以同样的方式读取和回答。在私聊里任何消息下的线程内回复，都留在私聊的对话里，带着它的上下文；只有用 `/thread` 打开的线程才是单独的对话。`/thread` 会把你发的这条 `/thread` 消息作为线程的根：机器人在这个线程里回复一条标记为 `🧵#N title` 的消息，你接着在同一个线程里说话。（从 `/thread` 按钮点出来，或在线程里发送时，没有可作根的消息，机器人会自己发那条带标记的消息，你在它下面回复。）

**机器人能读到线程里的多少内容，由 SeaTalk 决定，而不是 Coffer。** SeaTalk 只返回**最近 7 天**内发送的回复；更早的线程只会返回根消息加上最近的内容，不管它在应用里看起来有多长。悄悄话和已删除的消息永远不会返回。机器人入群之前发送的回复，受它入群时群组的「Chat history for new members」设置限制。线程早于这个窗口时，Coffer 会在轮次的上下文里说明这一点，读取工具也会说明，让智能体告诉你它看不到哪些内容，而不是去猜。把缺失的消息转发或引用过来，就能把它们带进来。

每个群组线程都是一个独立的对话，所以你可以在一个线程里用 Claude Code，在另一个线程里用 Codex。群组里的回答以 @ 你开头，所以 SeaTalk 会通知你。

因为在主聊天里 @ 提及总会开一个新线程，所以在主聊天里发 `@bot /new <agent>` 设置的是**群组的默认智能体**，群组里每个新线程都从它开始；`@bot /stop` 停止群组里正在运行的所有轮次。`/del` 撤回回复，见[回复的样子](#how-replies-look)。`/model`、`/dir`、`/status`、`/resume` 和 `/thread` 只能在私聊里用，在群里发会得到一行私下的提示。在群组线程里，`/new` 和 `/stop` 只作用于该线程。见 [SeaTalk 上的群组默认值](/zh/reference/channel-commands#group-defaults-on-seatalk)。

如果希望机器人不理会同时 @ 了其他人的消息，在消息渠道**设置**标签页的**群聊中**下打开**忽略同时 @ 了其他人的消息**。SeaTalk 没有**仅在被 @ 时回复**开关：它本来就只投递 @ 提及。

机器人从不读取群组主聊天里的最近消息。SeaTalk 不给自建应用这个权限，而且你发给机器人的那条消息本就应该带上它需要的内容。

### 引用消息 {#quoted-messages}

你引用一条消息来回复时，Coffer 会用机器人自己的密钥查出被引用的消息，把它作为 `> sender: …` 行放在你的文字上方并入轮次，附带它的图片和文件。SeaTalk 对每个应用给同一条消息不同的 id，所以只有收到引用的那个机器人能解析它；智能体自己的工具做不到。查找失败时，轮次只用你的消息运行。

### 转发的聊天记录 {#forwarded-chat-history}

转发的聊天记录会被展平成一个 `[Forwarded chat record]` 区块，每条消息一行。其中的图片（包括嵌套在其他记录里转发的记录中的图片）会被下载并附上，所以有视觉能力的智能体看到的是图片本身，而不是它打不开的链接。

### 群组事件 {#group-events}

如果机器人被移出群组，或者群组被解散，该群组的会话就会停止。如果群组被转换成外部群组（其他组织的人也能看），机器人会在群里发一条警告。消息渠道继续工作。

## 卡片 {#cards}

在私聊里，不带参数的 `/model`、`/dir` 或 `/resume` 会回复一张交互卡片；`/status` 带 **New**、**Model**、**Resume** 和 **Dir** 按钮（轮次运行时还有 **Stop**）。`/help` 为聊天里能用的每个命令各带一个按钮（分页），私聊九个，群组四个群命令；`/new` 在私聊里带 **Agent**、**Model** 和 **Dir**，在群组里只带 **Agent**。点这些按钮和输入对应命令的效果完全一样。智能体提出的问题也会以卡片形式送达，每个选项一个按钮、各占一行（多选的选项会切换 `✓`，由 **Submit** 提交）；点一下或直接输入文字都是回答，之后卡片会被改写为 `✓ Answered: …`。

- 按钮最多排成三行。短标签共用一行；像 "Claude Code" 这样的长标签独占一行。
- 一张卡片最多六个按钮；更长的列表用 **← Prev** 和 **Next →** 翻页。
- 你点了某个选项后，卡片会被重写，让勾选标记移过去。SeaTalk 只允许对同一个机器人在最近 7 天内发出的交互卡片这样做。对更早的卡片，选择仍然生效；翻页则会以一张新卡片送达。
- 标题截断到 120 个字符，描述截断到 1,000 个字符。

## 媒体 {#media}

SeaTalk 能附带的一切都会驱动一个轮次：图片、文件和文档、视频，以及语音或音频。Coffer 用应用的令牌下载每个附件，因为 SeaTalk 的文件链接需要认证。

- 文档会提取成文字交给智能体。
- 打开语音转文字时（**设置 › 通用 → 语音转文字**），语音会被转写；否则智能体拿到的是音频文件。
- 文件保留它的真实文件名。

智能体用一行 `MEDIA:/absolute/path` 把文件发回来。它会以图片或文件消息的形式出现在同一个聊天和线程里，说明文字作为随后的一条消息。见[消息渠道 → 回传文件](/zh/guides/channels#sending-files-back)。

## 轮换 App Secret {#rotate-the-app-secret}

在消息渠道页面选择**更换密钥**（在 **⋯** 菜单里，或在**设置** → **密钥**下），粘贴到 **App Secret**，然后选**更换并重启**。粘贴时 Coffer 会向 SeaTalk 检查 App ID 和 secret，被拒绝的 secret 会在字段下说明。secret 会写到消息渠道现有的引用下，所以配对不变。在**设置** → **密钥**下，App Secret 显示为密钥的名字（链接到它的页面），旁边是**更换密钥…**；其中的**改用其他密钥**会让消息渠道改用另一个已存的密钥，并让适配器用它重启。**App ID** 在**设置** → **密钥**下原地编辑。

## 上限 {#limits}

| 上限 | 值 |
| --- | --- |
| 普通消息 | 不超过 4,096 字节 |
| 卡片重写窗口 | 7 天，仅限交互卡片 |
| 卡片内容 | 6 个按钮，最多 3 行；标题 120 个字符，描述 1,000 个字符 |
| 线程分页 | 每页 100 条消息，页数有上限 |
| 线程历史 | 只有最近 7 天的回复；不含悄悄话和已删除的消息 |
| 撤回机器人消息 | 没有删除 API；群组回复卡片在 7 天内可被重写为「🗑 Withdrawn」 |
| 每个应用的连接数 | 1 |

## 故障排查 {#troubleshooting}

**状态是 `sdk_missing`。**
检查 `~/.coffer/vendor/seatalk_oapi_sdk/`（或 `$COFFER_SEATALK_SDK_DIR/seatalk_oapi_sdk/`）是否存在；如果你用了 `COFFER_SEATALK_SDK_DIR`，确认它设置在守护进程启动的环境里，而不只是你当前的 shell；桥接进程从守护进程的环境里读取它。在此期间回复和通知仍然可用。

**状态是 `kicked`。**
另一个进程占用了这个应用的连接。常见原因：同一个应用在第二台机器上也登记成了消息渠道，或者某个测试脚本用了同一个 App ID。停掉另一个；Coffer 大约一分钟内会重连。要在机器之间迁移消息渠道，见[在另一台机器上使用机器人](/zh/guides/channels#using-the-bot-on-another-machine)。

**开发者后台里 Re-verify 失败。**
消息渠道还没连上。等 **SeaTalk connection** 标记显示已连接（Connected）后再点一次 **Re-verify**。

**显示 `connected`，但机器人从不回答。**
检查配对（`peer: not paired` 表示机器人不回复任何人），以及在群组里你是否 @ 了它。然后检查后台的投递方式是否设为 WebSocket；用其他投递方式时，SeaTalk 会把事件发到别处。

**机器人说它只能看到线程里的几条消息。**
SeaTalk 只返回线程最近 7 天的回复（见[群组和线程](#groups-and-threads)），所以更早的讨论即使你能滚动看到，机器人也看不到。把更早的消息转发或引用过来，给智能体补上这部分上下文。在这个窗口之内，一个轮次只带上线程最近的消息；让智能体往前多读，它会使用 `coffer__channel_read_thread`。

## 相关 {#related}

- [消息渠道](/zh/guides/channels)：所有消息渠道的命令、生效范围和安全。
- [Telegram](/zh/guides/channels-telegram)
- [密钥存储](/zh/guides/secret-store)
- [规格：channels/seatalk](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/channels/seatalk/spec.md)
- [SeaTalk Inbound Over WebSocket](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/seatalk-websocket-inbound.md)
