# Quickstart：Channels

> English: [quickstart.md](./quickstart.md)

在 Telegram 或 SeaTalk 里直接跟你的 Coffer agent 对话，并让 Coffer 给你
推送通知。

## Telegram

### 1. 创建 bot

在 Telegram 中打开 [@BotFather](https://t.me/BotFather)，发送 `/newbot`，
按提示操作，并复制 bot token。

### 2. 保存 token 并注册 channel

UI：**Channels → Add channel → Telegram**，粘贴 token，给 channel 起名
（例如 `my-telegram`）。该对话框会把 token 存入凭据存储并一步完成
channel 注册。

CLI 等价做法：

```bash
coffer credentials set channel/my-telegram/bot-token     # paste token at prompt
coffer channel register my-telegram --type telegram \
  --bot-token-ref channel/my-telegram/bot-token
```

### 3. 配对你的账号

```bash
coffer channel pair my-telegram        # prints an 8-character code
```

（或在 channel 页面点击 **Pair**）。在 Telegram 中打开你的 bot，把这串码
作为消息发出去。bot 会确认；你现在就是该 channel 的 owner。其他任何人的
消息都会被静默忽略。

### 4. 聊天

随便发一条消息 —— 它会落进一段与 channel 默认 agent（Coffer 受管 agent，
如 Claude Code 或 Codex）的对话，回复回到 Telegram。

> 按 [Built-in Agent Is Internal](../../docs/decisions/builtin-agent-is-internal-capability.zh.md)，
> channel 只路由到受管 agent；内置「Coffer Assistant」不再是聊天目标。

命令：`/new` 开新对话 · `/stop` 打断运行中的 turn · `/status` 查看当前
状态 · `/help`。

## SeaTalk

SeaTalk 有两种把事件投递给 bot 的方式，而平台规定每个 bot **同一时刻只能用一种**。
在注册 channel 之前先定下用哪种——这个选择同时活在 channel 上（`delivery`）和 SeaTalk
开发者后台的 app 上，两边必须一致。

- **WebSocket** —— Coffer 向 SeaTalk 打开一条出网连接，事件从这条连接上来。什么都不
  暴露：没有公网 URL，没有隧道，也没有签名 secret。它需要本机上有 SeaTalk 自己的客户端
  库（步骤 2a），而 Coffer 不分发这个库。
- **Webhook** —— SeaTalk 把每个事件 POST 到一个属于你的公网 URL，因此需要签名 secret，
  外加某样把公网接到 Coffer 本地监听器上的东西：你自己跑的隧道，或者 Coffer 替你跑的那条
  （步骤 2b）。

### 1. 创建 app

在 [SeaTalk Open Platform](https://open.seatalk.io/) 上创建一个 app，启用
**Bot** 能力并将其设为 Online，申请需要管理员审批的 scope（至少 _Send
Message to Bot User_）。记下 **App ID** 与 **App Secret**。如果走 webhook 这条路，
还要记下 Event Callback 的 **Signing Secret**；走 websocket 则根本没有这个东西。

### 2a. WebSocket 投递

把 SeaTalk 官方的 Python SDK 放到 Coffer 会去找的地方。它从 SeaTalk 自己的门户分发，
不在 PyPI 上，所以 Coffer 既不打包也不依赖它——由你提供：

```bash
mkdir -p ~/.coffer/vendor
# unpack the official SDK so that ~/.coffer/vendor/seatalk_oapi_sdk/ exists
# keep it elsewhere? point COFFER_SEATALK_SDK_DIR at that directory instead
```

注册 channel —— 没有签名 secret，没有公网 URL，也没有隧道 token：

```bash
coffer credentials set channel/st/app-secret
coffer channel register my-seatalk --type seatalk --app-id <APP_ID> \
  --app-secret-ref channel/st/app-secret --delivery websocket
```

UI：**Channels → Add channel → SeaTalk**，选择 **WebSocket**，填入 App ID 并粘贴
app secret。

然后在开发者后台把该 app 的事件投递方式切到 **WebSocket**。先在 Coffer 里启用这个
channel：后台的 **Re-verify** 只有在连接真的活着时才会通过，所以要等
`coffer channel status my-seatalk` 报出该 channel 已 **connected** 之后再去验证。
之后也用这条命令看连接状态 —— `connecting`、`connected`、`kicked`、`sdk_missing`，
或 `error` 外加最近一次的错误文本。

这条路有两件事要知道。**一个 SeaTalk app 只许一条连接**：如果同一个 app 在别处被注册
——第二台机器、同事在试——那次注册会把事件拿走，而这一条被踢掉。Coffer 会报 `kicked`
并放慢重试，而不是去抢这个 socket，所以如果那不是你有意为之，就把另一头停掉。以及
**连接断开期间事件是暂停的**：没有任何公网端点替你把它们排起来。

如果 SDK 不在，该 channel 不会启动并会把原因说出来 —— 点明它搜过的目录 —— 而 daemon
和其余每个 channel 照常运行。

### 2b. Webhook 投递

带签名 secret 注册 channel：

```bash
coffer credentials set channel/st/app-secret
coffer credentials set channel/st/signing-secret
coffer channel register my-seatalk --type seatalk --app-id <APP_ID> \
  --app-secret-ref channel/st/app-secret \
  --signing-secret-ref channel/st/signing-secret
```

UI：**Channels → Add channel → SeaTalk**，投递方式保持 **Webhook**，填入 App ID
并粘贴两个 secret。

只要有使用 webhook 投递的 SeaTalk channel 处于启用状态，Coffer 就会在
`127.0.0.1:8787`（可用 `COFFER_CALLBACK_PORT` 覆盖）上运行一个小巧的回调监听器。
这个监听器只绑 loopback，所以总得有东西把公网接到它上面。要么隧道你自己跑：

```bash
cloudflared tunnel --url http://127.0.0.1:8787
# or: ngrok http 8787
```

……要么让 Coffer 替你照看一条：在 Cloudflare 上创建一条**命名隧道**，然后在
**Channels → my-seatalk → Edit channel** 里粘贴它的 connector token，以及该隧道对外
应答的公网基址（`https://seatalk.example.com`）。token 进凭据存储，channel 只记下那个
引用；此后只要该 channel 处于启用状态，Coffer 就一直保着一个 `cloudflared` 子进程，
它死了就重启。channel 的状态卡片会显示这条托管隧道是否在跑。

两种做法都一样：在 Open Platform 上把该 app 的 **Event Callback URL** 设为
`<public-url>/seatalk/my-seatalk`。SeaTalk 会发送一条验证 challenge；监听器会自动
应答 —— 门户会把该 URL 显示为已验证。`coffer channel status my-seatalk` 会给出确切的
端口与路径、公网回调 URL，以及监听器和托管隧道是否在运行。

### 3. 配对并聊天

与 Telegram 相同，且两种投递方式下完全一致：`coffer channel pair my-seatalk`，在
SeaTalk 里把码发给 bot，然后直接开聊。回复以 SeaTalk Markdown 渲染。

### 之后切换投递方式

两边一起改，在同一次操作里改完。切换时 Coffer 会丢掉另一种方式所拥有的那些字段——
websocket channel 不保留签名 secret、公网 URL 或隧道 token，而 webhook channel 需要把
签名 secret 重新给回来——所以这次切换绝不会是单边的编辑。切到 webhook，就在后台设好
callback URL；切到 websocket，就把后台切成 WebSocket，并在 Coffer 握着连接时
Re-verify。

## 通知

任何时候都能给已配对的 channel 推送一条消息 —— 不需要任何入站消息：

```bash
coffer channel notify my-telegram "nightly build finished ✅"
```

REST：`POST /api/v1/channels/my-telegram/notify {"text": "..."}`。

UI：渠道详情页有一张 **Send test message** 卡片——输入一行文字即可推送给已
配对的对端（配对后用来确认投递最自然的方式）。在渠道完成配对前它保持禁用。

## 日常运维

- **编辑**：在渠道详情页（**Edit channel**）更换绑定的 Agent，或轮换密钥
  （Telegram 机器人 token / SeaTalk app secret + signing secret）。轮换后的
  密钥会写回同一个凭据引用，因此绑定与配对不受影响；密钥字段留空则保留当前
  值。
- **Disable** 一个 channel 可立即切断其流量（轮询停止、事件被拒收）；
  **enable** 恢复。adapter 状态显示在 `coffer channel status` 与
  Channels 页面上。
- **重新配对**：签发一个新码并从新账号发送 —— 旧的绑定会被替换。
- **Delete** 该 channel 可移除一切；过往对话仍留在会话存储里，直到留存策略清理它们。
