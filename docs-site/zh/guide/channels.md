# 渠道

**渠道**(channel)让你从一个即时通讯应用 —— **Telegram** 或 **SeaTalk** —— 触达你的 Coffer agent。把渠道配对到你自己的账号,然后就能在 IM 聊天里与 agent 对话,并接收 Coffer 推送给你的通知。

## 注册渠道

先把 bot 密钥存入凭证库,然后用对它的**引用**(而非密钥本身)注册渠道:

```bash
coffer credentials set tg-bot-token                          # 在提示处粘贴 token
coffer channel register mybot --type telegram --bot-token-ref tg-bot-token
coffer channel pair mybot                                    # → 一个 8 位、一次性的配对码
coffer channel status mybot                                  # 适配器状态 + 已配对的对端
```

- Telegram 需要 `--bot-token-ref`;SeaTalk 需要 `--app-id --app-secret-ref`,再加上 webhook 投递时的 `--signing-secret-ref`,或出网长连接传输的 `--delivery websocket`。`--agent`(默认 `claude_code`)决定由哪个 agent 应答。
- **配对是安全边界。** Coffer 是单用户的:用你自己的账号把配对码发给 bot,即成为其唯一所有者。其他任何人都被忽略。

## Telegram 与 SeaTalk 的区别

- **Telegram** 使用长轮询 —— 无需公网入口,无需暴露任何东西。
- **SeaTalk** 有两种投递事件的方式,而平台规定一个 bot 同一时刻只能用一种 —— 因此每个渠道各自挑一种传输。
  - 走 **webhook** 时,SeaTalk 把事件 POST 到一个公网 URL。Coffer **仅在某个使用 webhook 的 SeaTalk 渠道启用时**才运行一个本地回调监听器(默认环回 `127.0.0.1:8787`),你在开放平台上注册 `<public-url>/seatalk/<channel>`。该监听器只绑环回,所以总得有东西把公网接到它上面:要么隧道你自己跑(cloudflared / ngrok),要么在渠道上记一个 Cloudflare connector token,Coffer 就会在该渠道启用期间一直替它看住一个 `cloudflared` 子进程。Coffer 从不暴露守护进程本身。
  - 走 **websocket** 时,Coffer 改为持有一条到 SeaTalk 的出网长连接:没有公网 URL,没有隧道,没有监听器,也没有签名密钥。它需要 SeaTalk 自己的客户端库,而 Coffer 既不打包也不依赖它 —— 把它放进 `~/.coffer/vendor`(或用 `COFFER_SEATALK_SDK_DIR` 指向你存放它的地方)。没有它,只有那一个渠道拒绝启动并说出缺了什么;其余一切照常运行。
  - 两种方式都需要一个经组织审批、具备 Bot 能力的开放平台应用,且渠道的传输方式必须与开发者后台里该应用的事件投递设置一致。

## 使用

```bash
coffer channel notify mybot "部署完成"        # 向你已配对的账号推送一条消息
```

在已配对的聊天里,聊天内命令 `/new`、`/stop`、`/status`、`/help` 控制对话。

应用里的 **Channels** 页做同样的事而无需终端:添加一个渠道(一步内存密钥并注册)、配对、开关、并从渠道详情页发送一条测试消息。

[导出与导入 →](/zh/guide/sync)
