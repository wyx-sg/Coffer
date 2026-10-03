---
title: SeaTalk
description: 为 Coffer 配置 SeaTalk 消息渠道：创建 SeaTalk 开放平台应用，提供 WebSocket SDK，登记并配对消息渠道，然后在私聊、群组和线程里使用。
---

# SeaTalk {#seatalk}

本指南配置一个 SeaTalk 消息渠道：在 SeaTalk 开放平台上创建机器人应用，提供 SeaTalk 的 WebSocket SDK，在 Coffer 里登记消息渠道，把应用切换到 WebSocket 投递，并配对你的账号。然后介绍群组、线程、引用消息、卡片、上限和故障排查。所有消息渠道共有的部分（命令、生效范围、机器绑定、安全）见[消息渠道](/zh/guides/channels)。

没有哪个智能体有官方的 SeaTalk 集成，所以你在 SeaTalk 里和智能体做的一切都经过这个消息渠道。

## SeaTalk 如何连接 {#how-seatalk-connects}

Coffer 通过**每个消息渠道一条出站 WebSocket 连接**接收 SeaTalk 事件。守护进程主动连到 SeaTalk，用应用的 ID 和 secret 认证，SeaTalk 再通过这条连接推送事件。不暴露任何东西：没有公网 URL、没有监听端口、没有隧道，也没有要校验的签名。回复和通知通过 HTTPS 发往 `openapi.seatalk.io`。

由此带来两点：

- **WebSocket 客户端是 SeaTalk 自己的 SDK，需要你自己提供。** 它从 SeaTalk 的门户分发，不在公共 PyPI 上，也没有公开许可证，所以 Coffer 不能随包发布或依赖它。没有它，SeaTalk 消息渠道能发送，但收不到任何东西。
- **每个 SeaTalk 应用只有一条连接。** 第二个进程登记同一个应用（另一台机器，或同事在测试）会把连接抢走。每个消息渠道只绑定一台机器。

## 前提条件 {#prerequisites}

- 守护进程正在运行，且至少登记了一个智能体。见[快速开始](/zh/start/quickstart)。
- 能访问 [SeaTalk 开放平台](https://open.seatalk.io/)，有创建应用的权限，并拿到你所在组织对相关权限范围要求的审批。

## 1. 创建 SeaTalk 应用 {#_1-create-the-seatalk-app}

1. 在 SeaTalk 开放平台上创建一个应用。
2. 启用 **Bot** 能力，并把机器人设为 **Online**。
3. 申请机器人需要的权限范围。最少需要 *Send Message to Bot User*；可能需要你们组织的管理员审批。
4. 记下应用的 **App ID** 和 **App Secret**。

事件投递设置留到第 4 步：只有在 Coffer 持有连接时，SeaTalk 才能校验 WebSocket 投递。

## 2. 提供 WebSocket SDK {#_2-supply-the-websocket-sdk}

1. 从 SeaTalk 开放平台下载 SeaTalk 用于 WebSocket 事件回调的 Python SDK。包名是 `seatalk_oapi_sdk`；见 SeaTalk 的 [WebSocket Event Callback](https://open.seatalk.io/docs/WebSocket-Event-Callback) 文档。下载这一步由你来做，因为它在平台的登录之后。
2. 其余的交给你的智能体。消息渠道登记好之后（第 3 步），等待 SDK 的消息渠道会显示**未安装 SeaTalk 的 Python SDK**，链接到 SeaTalk 的下载页面，并提供**交给智能体**（它的菜单可复制提示词；没有 Coffer 托管的智能体可用时只提供**复制提示词**）：一段让智能体把压缩包解压到 Coffer vendor 目录的提示词。放好之后点**重试**。

Coffer 只在 SeaTalk 消息渠道启动时才导入 SDK，从不在守护进程启动时导入；SDK 缺失时它会一直重试。你可以在登记消息渠道之前或之后添加 SDK；已经在等待的消息渠道不用重启守护进程就能用上它。

要手动处理，就解压压缩包，让包目录位于 Coffer 的 vendor 目录下：

```text
~/.coffer/vendor/seatalk_oapi_sdk/
```

想放在别处，就在守护进程启动的环境里，把 `COFFER_SEATALK_SDK_DIR` 设为**包含** `seatalk_oapi_sdk/` 的那个目录。

## 3. 登记消息渠道 {#_3-register-the-channel}

::: code-group

```sh [CLI]
# Paste the App Secret at the prompt; it is read from stdin
coffer secret set channel/st/app-secret

coffer channel add my-seatalk --type seatalk \
  --app-id <APP_ID> \
  --app-secret-ref channel/st/app-secret \
  --agent claude-code
```

```text [Web UI]
Channels → Add channel
  Type:           SeaTalk
  Name:           my-seatalk
  App ID:         <APP_ID>
  App secret:     <APP_SECRET>
  Default agent:  claude-code
→ Create
```

:::

配置内容是 App ID 和指向 App Secret 的引用，外加每个消息渠道都有的字段。消息渠道绑定到这台机器，并立刻开始连接。

检查连接：

```sh
coffer channel show my-seatalk
```

```text
channel:  my-seatalk (seatalk)
uid:      4c7a…
agent:    claude-code
gating:   require_mention=on  ignore_other_mentions=off
idle:     new conversation after 24 h idle
secret:   app_secret_ref = channel/st/app-secret
enabled:  True    running: True
runs on:  3f9c… (this machine)
pairing:  no pending code
peer:     not paired
inbound:  websocket (connected)
```

等到 `connected` 再做下一步。消息渠道页面状态行上的 **SeaTalk connection** 标记显示的是同样的状态。

## 4. 把应用切换到 WebSocket 投递 {#_4-switch-the-app-to-websocket-delivery}

1. 在 SeaTalk 开发者后台打开应用的事件回调设置，把投递方式设为 **WebSocket**。SeaTalk 每个机器人只允许一种投递方式。
2. 点 **Re-verify**。只有 Coffer 持有实时连接时它才能通过，这就是为什么要先登记消息渠道。

## 5. 配对你的账号 {#_5-pair-your-account}

1. 在消息渠道的**总览**里选**生成配对码**，或运行 `coffer channel pair my-seatalk`。
2. 在 SeaTalk 里打开和机器人的私聊，发送那个八位配对码。
3. 机器人确认配对，并发一次帮助卡片。SeaTalk 没有命令菜单，所以机器人靠这张卡片告诉你它接受什么；发送 `/help` 可以再看一次。

SeaTalk 没有启动链接，所以要你手动输入配对码。它只能用一次，一小时后过期，猜错 10 次后作废。

给机器人发一条消息。输入中提示会立刻出现，回复流式写进一条消息，对话会出现在 Web 的[对话](/zh/guides/chat)页面上，来源标记为 `SeaTalk · DM`。

## 连接状态 {#connection-states}

`coffer channel show` 和消息渠道页面上的 **SeaTalk connection** 标记把连接作为消息渠道的入站状态报告。用 `--json` 时，字段是 `status.inbound.websocket_state` 和 `status.inbound.websocket_error`。

| 状态 | 消息渠道页面上的显示 | 含义 |
| --- | --- | --- |
| `connecting` | **连接中** — 连接中…（尝试失败后为**重连中** — 重连中…） | 正在向 SeaTalk 注册。 |
| `connected` | **已连接** | 事件正在流入。 |
| `kicked` | **被挤下线** — 连接被另一个进程占用 | 另一个进程登记了同一个应用。Coffer 会等 60 秒再试，而不是去抢连接。 |
| `sdk_missing` | **无法启动** — 未找到 SeaTalk SDK | 无法导入 `seatalk_oapi_sdk`。错误信息会写明搜索过的目录。 |
| `error` | **无法连接** — 连接被拒绝 | 上一次尝试失败；`websocket_error` 原样保存错误信息。Coffer 以 1 到 30 秒的退避重试。 |

第一次尝试之前不显示任何状态。连接断开期间 SeaTalk 发来的事件，Coffer 不会在任何地方排队保存。

## 回复的样子 {#how-replies-look}

- **流式输出**：回复是一条随智能体写作不断增长的消息，轮次一开始就带着状态行（`⏳ Working · 0s`）出现。每次更新都带着到目前为止的完整文字，状态行的计时每 10 秒走一次。长时间的工具调用期间，Coffer 每 10 秒重发一次最新文字，因为 SeaTalk 会结束 30 秒没有更新的流。3.67 之前的 SeaTalk 客户端要等流关闭时才显示完成的消息。
- **长回复**：一个流最多承载 4,096 个字符。更长的回复会在段落边界结束流，剩下的内容作为普通消息送达，编号为 `(2/3)`、`(3/3)`。
- **长轮次**：结束一个流不会通知任何人，因为那条消息是在轮次开始时创建的。所以超过消息渠道阈值（默认 90 秒）的轮次，最后会在同一线程里发一条新消息：`✅ Done · 4m 12s — <first line>`；在群组里它会 @ 提问的人。
- **格式**：智能体的 Markdown 会转成 SeaTalk Markdown：粗体、斜体、行内代码、代码块和列表。标题变成粗体，链接变成 `label (url)`，因为 SeaTalk 两者都不支持。表格变成每行一个列表项（大表格还会以 `.csv` 附上），超过 30 行的代码块以文件形式送达。消息会被拆分，保持在 SeaTalk 4,096 字节的上限以内。
- **详情**：`## Details` 小节放在一张以回答第一行为标题的卡片后面；**Details** 会把它作为回复发到卡片的线程里，**As file** 会把它作为 `.md` 文件发送。
- **回执**：SeaTalk 没有表情回应，所以轮次运行期间每 3 秒续一次输入中提示，私聊和群组线程都是如此。超过 200 人的群组里，SeaTalk 会悄悄跳过群组输入中提示。
- **工具进度**：状态行下面列出最新的几次工具调用，每次一行。在**群组**里这一行只写工具名（`⏳ Bash`），因为群里每个人都看得到，而工具的输入里可能带着命令、查询或路径。在**私聊**里会附上智能体自己写的一句话描述或文件名（`⏳ Bash · list the desktop`），从不显示原始命令。
- **回复不能删除或修改。** SeaTalk 开放平台没有撤回机器人消息的 API，已经结束的流也不能再更新。只有交互卡片可以重写，而且只能由发送它的机器人重写，所以 Coffer 不给流式回复提供删除按钮。依赖答案之前先核对它的依据；错误的回复会一直留在聊天里。

连续约 10 分钟没有新内容时，保活会放弃，所以沉默这么久的轮次会让它的流失效。如果流被 SeaTalk 结束（出错，或者间隔超过 30 秒），Coffer 不会重用它。不完整的消息留在聊天里，完整的回复以普通消息发送。

## 群组和线程 {#groups-and-threads}

1. 把机器人加进群组。
2. @ 提及它。SeaTalk 只把 @ 提及投递给机器人；其他群消息永远到不了 Coffer。
3. 所有者的第一次 @ 提及会把这个群组登记为消息渠道的一个对端。其他人的提及会收到一句简短的 "not authorized" 回复。

回答会发到哪里：

- **在群组主聊天里 @ 提及**：机器人以你的消息为根开一个线程，在那里回答。它不读历史：线程里只有你的消息。
- **在线程里 @ 提及**：机器人会读整个线程的每一页，从最早的开始，下载之前消息里带的图片和文件，然后在该线程里回答。
- **私聊里的线程**：以同样的方式读取和回答。在私聊里任何消息下的线程内回复，都留在私聊的对话里，带着它的上下文；只有用 `/thread` 打开的线程才是单独的对话。`/thread` 会发一条标记为 `🧵#N title` 的消息，你在它下面回复。

**机器人能读到线程里的多少内容，由 SeaTalk 决定，而不是 Coffer。** SeaTalk 只返回**最近 7 天**内发送的回复；更早的线程只会返回根消息加上最近的内容，不管它在应用里看起来有多长。悄悄话和已删除的消息永远不会返回。机器人入群之前发送的回复，受它入群时群组的「Chat history for new members」设置限制。线程早于这个窗口时，Coffer 会在轮次的上下文里说明这一点，让智能体告诉你它看不到哪些内容，而不是去猜。把缺失的消息转发或引用过来，就能把它们带进来。

每个群组线程都是一个独立的对话，所以你可以在一个线程里用 Claude Code，在另一个线程里用 Codex。群组里的回答以 @ 你开头，所以 SeaTalk 会通知你。

因为在主聊天里 @ 提及总会开一个新线程，所以在主聊天里发的命令设置的是**群组默认值**：`@bot /model …`、`@bot /dir …` 和 `@bot /new <agent>` 决定群组里每个新线程从什么开始，`@bot /status` 显示这些默认值和正在运行的线程，`@bot /stop` 停止群组里正在运行的所有轮次。在线程里，命令只作用于该线程。见 [SeaTalk 上的群组默认值](/zh/reference/channel-commands#group-defaults-on-seatalk)。

如果希望机器人不理会同时 @ 了其他人的消息，在消息渠道**设置**标签页的**群聊中**下打开**忽略同时 @ 了其他人的消息**，或者运行 `coffer channel edit my-seatalk --ignore-other-mentions`。SeaTalk 没有**仅在被 @ 时回复**开关：它本来就只投递 @ 提及。

机器人从不读取群组主聊天里的最近消息。SeaTalk 不给自建应用这个权限，而且你发给机器人的那条消息本就应该带上它需要的内容。

### 引用消息 {#quoted-messages}

你引用一条消息来回复时，Coffer 会用机器人自己的密钥查出被引用的消息，把它作为 `> sender: …` 行放在你的文字上方并入轮次，附带它的图片和文件。SeaTalk 对每个应用给同一条消息不同的 id，所以只有收到引用的那个机器人能解析它；智能体自己的工具做不到。查找失败时，轮次只用你的消息运行。

### 转发的聊天记录 {#forwarded-chat-history}

转发的聊天记录会被展平成一个 `[Forwarded chat record]` 区块，每条消息一行。其中的图片（包括嵌套在其他记录里转发的记录中的图片）会被下载并附上，所以有视觉能力的智能体看到的是图片本身，而不是它打不开的链接。

### 群组事件 {#group-events}

如果机器人被移出群组，或者群组被解散，该群组的会话就会停止。如果群组被转换成外部群组（其他组织的人也能看），机器人会在群里发一条警告。消息渠道继续工作。

## 卡片 {#cards}

不带参数的 `/model`、`/dir`、`/resume` 或 `/kb` 会回复一张交互卡片；`/status` 带 **New**、**Model**、**Resume** 和 **Dir** 按钮（轮次运行时还有 **Stop**），`/help` 带 **New**、**Stop**、**Model**、**Status** 和 **Resume**，`/new` 带 **Agent**、**Model** 和 **Dir**。点这些按钮和输入对应命令的效果完全一样。智能体以提问结尾时，这个问题也会以卡片形式送达，每个答案一个按钮；点一下就把那个答案作为你的回复发出去。

- 按钮最多排成三行。短标签共用一行；像 "Claude Code" 这样的长标签独占一行。
- 一张卡片最多六个按钮；更长的列表用 **← Prev** 和 **Next →** 翻页。
- 你点了某个选项后，卡片会被重写，让勾选标记移过去。SeaTalk 只允许对同一个机器人在最近 7 天内发出的交互卡片这样做。对更早的卡片，选择仍然生效；翻页则会以一张新卡片送达。
- 标题截断到 120 个字符，描述截断到 1,000 个字符。

## 媒体 {#media}

SeaTalk 能附带的一切都会驱动一个轮次：图片、文件和文档、视频，以及语音或音频。Coffer 用应用的令牌下载每个附件，因为 SeaTalk 的文件链接需要认证。

- 文档会提取成文字交给智能体。
- 打开语音转文字时（**设置 › 通用 → Coffer 自用模型**），语音会被转写；否则智能体拿到的是音频文件。
- 文件保留它的真实文件名。

智能体用一行 `MEDIA:/absolute/path` 把文件发回来。它会以图片或文件消息的形式出现在同一个聊天和线程里，说明文字作为随后的一条消息。见[消息渠道 → 回传文件](/zh/guides/channels#sending-files-back)。

## 轮换 App Secret {#rotate-the-app-secret}

在消息渠道页面选择**更换密钥**（在 **⋯** 菜单里，或在**设置** → **密钥**下），粘贴到**新的 App Secret**，然后选**更换并重启**。secret 会写到消息渠道现有的引用下，所以配对和机器绑定都不变。**App ID** 在**设置** → **密钥**下原地编辑。

## 上限 {#limits}

| 上限 | 值 |
| --- | --- |
| 流式回复 | 每个流 4,096 个字符；其余作为普通消息 |
| 普通消息 | 不超过 4,096 字节 |
| 流空闲上限 | 30 秒（Coffer 每 10 秒重发一次） |
| 卡片重写窗口 | 7 天，仅限交互卡片 |
| 卡片内容 | 6 个按钮，最多 3 行；标题 120 个字符，描述 1,000 个字符 |
| 线程分页 | 每页 100 条消息，页数有上限 |
| 线程历史 | 只有最近 7 天的回复；不含悄悄话和已删除的消息 |
| 撤回机器人消息 | 不支持 |
| 每个应用的连接数 | 1 |

## 故障排查 {#troubleshooting}

**状态是 `sdk_missing`。**
检查 `~/.coffer/vendor/seatalk_oapi_sdk/`（或 `$COFFER_SEATALK_SDK_DIR/seatalk_oapi_sdk/`）是否存在；如果你用了 `COFFER_SEATALK_SDK_DIR`，确认它设置在守护进程启动的环境里，而不只是你当前的 shell。在此期间回复和通知仍然可用。

**状态是 `kicked`。**
另一个进程占用了这个应用的连接。常见原因：同一个应用在第二台机器上也登记成了消息渠道，或者某个测试脚本用了同一个 App ID。停掉另一个；Coffer 大约一分钟内会重连。要在机器之间迁移消息渠道，在当前运行它的机器上用 `coffer channel bind`。

**开发者后台里 Re-verify 失败。**
消息渠道还没连上。等 `coffer channel show` 显示 `connected` 后再点一次 **Re-verify**。

**显示 `connected`，但机器人从不回答。**
检查配对（`peer: not paired` 表示机器人不回复任何人），以及在群组里你是否 @ 了它。然后检查后台的投递方式是否设为 WebSocket；用其他投递方式时，SeaTalk 会把事件发到别处。

**机器人说它只能看到线程里的几条消息。**
SeaTalk 只返回线程最近 7 天的回复（见[群组和线程](#groups-and-threads)），所以更早的讨论即使你能滚动看到，机器人也看不到。今天开始的线程能完整读取。把更早的消息转发或引用过来，给智能体补上这部分上下文。

**流式回复中途停下，答案又在下面重新出现一遍。**
SeaTalk 结束了这个流。完整的答案是下面发出的那一份。

## 相关 {#related}

- [消息渠道](/zh/guides/channels)：所有消息渠道的命令、生效范围、机器绑定和安全。
- [Telegram](/zh/guides/channels-telegram)
- [密钥存储](/zh/guides/secret-store)
- [规格：channels/seatalk](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/channels/seatalk/spec.md)
- [SeaTalk Inbound Over WebSocket](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/seatalk-websocket-inbound.md)
