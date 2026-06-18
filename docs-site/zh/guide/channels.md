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

- Telegram 需要 `--bot-token-ref`;SeaTalk 需要 `--app-id --app-secret-ref --signing-secret-ref`。`--agent`(默认 `builtin`)决定由哪个 agent 应答。
- **配对是安全边界。** Coffer 是单用户的:用你自己的账号把配对码发给 bot,即成为其唯一所有者。其他任何人都被忽略。

## Telegram 与 SeaTalk 的区别

- **Telegram** 使用长轮询 —— 无需公网入口,无需暴露任何东西。
- **SeaTalk** 仅支持 webhook。Coffer **仅在某个 SeaTalk 渠道启用时**才运行一个本地回调监听器(默认环回 `127.0.0.1:8787`)。用一个隧道(cloudflared / ngrok)指向它,并注册 `<public-url>/seatalk/<channel>`。Coffer 从不暴露守护进程本身,也不管理隧道。SeaTalk 还需要一个经组织审批、具备 Bot 能力的开放平台应用。

## 使用

```bash
coffer channel notify mybot "部署完成"        # 向你已配对的账号推送一条消息
```

在已配对的聊天里,聊天内命令 `/new`、`/stop`、`/status`、`/help` 控制对话。渠道对话也会出现在应用的 **Chat** 页。

应用里的 **Channels** 页做同样的事而无需终端:添加一个渠道(一步内存密钥并注册)、配对、开关、并从渠道详情页发送一条测试消息。

[多机同步 →](/zh/guide/sync)
