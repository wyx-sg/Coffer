# Quickstart：009 —— Channels

> English: [quickstart.md](./quickstart.md)

在 Telegram 或 SeaTalk 里直接跟你的 Coffer agent 对话，点一下就批准工具
调用，并让 Coffer 给你推送通知。

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

随便发一条消息 —— 它会落进一段与 channel 默认 agent（未另行配置时为
内置的 Coffer Assistant）的对话，回复回到 Telegram。同一段对话在 Chat
页面也可见。

命令：`/new` 开新对话 · `/stop` 打断运行中的 turn · `/status` 查看当前
状态 · `/help`。

## SeaTalk

### 1. 创建 app

在 [SeaTalk Open Platform](https://open.seatalk.io/) 上创建一个 app，启用
**Bot** 能力并将其设为 Online，申请需要管理员审批的 scope（至少 *Send
Message to Bot User*）。记下 **App ID**、**App Secret** 与 Event
Callback 的 **Signing Secret**。

### 2. 注册 channel

UI：**Channels → Add channel → SeaTalk**，填入 App ID 并粘贴两个
secret。

CLI 等价做法：

```bash
coffer credentials set channel/st/app-secret
coffer credentials set channel/st/signing-secret
coffer channel register my-seatalk --type seatalk --app-id <APP_ID> \
  --app-secret-ref channel/st/app-secret \
  --signing-secret-ref channel/st/signing-secret
```

### 3. 暴露回调监听器

只要有 SeaTalk channel 处于启用状态，Coffer 就会在 `127.0.0.1:8787`（可
用 `COFFER_CALLBACK_PORT` 覆盖）上运行一个小巧的回调监听器。把一条隧道
指向它：

```bash
cloudflared tunnel --url http://127.0.0.1:8787
# or: ngrok http 8787
```

复制公网 URL，在 Open Platform 上把该 app 的 **Event Callback URL** 设为
`<public-url>/seatalk/my-seatalk`。SeaTalk 会发送一条验证 challenge；
监听器会自动应答 —— 门户会把该 URL 显示为已验证。随时可用
`coffer channel status my-seatalk` 查看确切的端口与路径。

### 4. 配对并聊天

与 Telegram 相同：`coffer channel pair my-seatalk`，在 SeaTalk 里把码发给
bot，然后直接开聊。工具审批提示以交互式卡片到达；回复以 SeaTalk
Markdown 渲染。

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
- **Delete** 该 channel 可移除一切；过往对话仍留在 Chat 历史中。
