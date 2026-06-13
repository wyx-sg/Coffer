# 多机同步

**同步**(sync)通过一个**你自己拥有的 git 仓库**推送和拉取保险库状态,让一个 Coffer 保险库在你所有机器上保持一致 —— 没有厂商云,且加密主密钥永远不离开你的掌控。

## 配置

```bash
coffer sync init git@github.com:me/coffer-vault.git    # 指向你自己的远端、启用、首次同步
coffer sync                                            # 完整同步:导出 → 拉取 → 推送 → 导入
coffer sync status                                     # clean / syncing / conflicted / error
```

- 远端是一个你拥有的私有 git URL;Coffer 使用你环境里的 git 凭证(SSH key 或 token),与一次普通的 `git push` 完全一样。Coffer 不提供任何托管端点。
- `coffer sync config --auto on --interval 300` 启用可选的周期性同步;自动同步默认**关闭**。

## 哪些会传输

**会镜像:**知识库与记忆的 Markdown、你的配置资源(MCP 服务器、agent、技能、渠道),以及**仅以 Fernet 密文形式**的凭证。**机器本地(永不同步):**日志、可重建的 `coffer.db` 索引、`daemon.json`、PID 文件、端口分配。

## 主密钥(带外)

加密主密钥**绝不**写入仓库 —— 只有密文会传输。请你自己把密钥搬到每台新机器:

```bash
coffer sync key export ./master.key       # 在源机器上
# 通过可信渠道搬运 master.key —— 绝不经由仓库
coffer sync key import ./master.key        # 在目标机器上
```

在密钥到位之前,导入的凭证保持**锁定**(`coffer sync status` 会报告),依赖它们的资源不会启动。

## 冲突

一次 git 合并冲突会让本次运行停在 `conflicted` 状态且不导入任何内容 —— 两边都不丢弃。解决后再次运行:

```bash
coffer sync resolve --theirs path/to/resource.json   # 或 --ours / --resolved
coffer sync
```

每个资源一个文件,使冲突保持很小。一个桌面 **Sync** 设置面板无需终端即可完成这一切,同样的操作也通过 REST 在 `/api/v1/sync/*` 提供。

[凭证 →](/zh/guide/credentials)
