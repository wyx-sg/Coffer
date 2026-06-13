# 凭证

Coffer 把你注册的每个密钥 —— API key、bot token —— 以 **Fernet 密文**形式存入本地 SQLite 数据库,由一把**主密钥**解锁。加密是透明的:需要密钥的功能去引用它,Coffer 仅在使用时在内存中解密。明文绝不进入日志、审计记录或事件。

## 存储并引用一个密钥

```bash
coffer credentials set openai-key            # 在隐藏提示处粘贴值(或通过 stdin 管道输入)
coffer credentials list                      # → openai-key | present
coffer credentials get openai-key            # 仅检查是否存在([redacted])
coffer credentials get openai-key --show     # 打印真实值(一次被审计的读取)
coffer credentials delete openai-key
```

- 其他功能取的是**引用**而非密钥本身:模型用 `--credential-ref openai-key`,渠道用 `--bot-token-ref`,以此类推。
- 优先用提示或 stdin,而非 `--value`(它会出现在你的 shell 历史里)。

## 主密钥存放在哪

任一时刻只有一个后端处于活动状态:

```bash
coffer credentials storage                   # 显示当前后端
coffer credentials storage --set keychain    # 把密钥移入操作系统钥匙串
coffer credentials storage --set file        # 把它移回 0600 文件
```

- **file**(默认)—— `~/.coffer/master.key`,权限 `0600`。零钥匙串提示。它不防御已经能读取 `~/.coffer/` 的攻击者。
- **keychain**(可选)—— 操作系统钥匙串。防御对 `~/.coffer/` 的离线窃取,代价是每次守护进程启动至多一次提示。切换只搬运密钥;不会重新加密任何密钥。

::: warning 备份数据库时一并备份主密钥
`coffer.db` 现在只保存密文。恢复它需要匹配的主密钥,因此请把 `~/.coffer/master.key`(或你的钥匙串条目)与数据库一起备份。若密文存在却解析不到密钥,守护进程会拒绝启动,而不是半盲运行。
:::

在应用里,存储后端是 **Settings → Security** 下的一个开关。各个密钥则在你注册引用它们的模型、渠道与 MCP 服务器时被设置。

[Web UI →](/zh/guide/web-ui)
