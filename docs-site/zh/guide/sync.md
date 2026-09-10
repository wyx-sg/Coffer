# 导出与导入

换了新笔记本,或者想让台式机从笔记本已经知道的东西开始?把保险库**导出**到一个目录,把那个目录搬过去,在另一台机器上**导入**。没有远端、没有后台复制、也没有厂商云 —— 加密主密钥也绝不随目录同行。

## 在机器 A 上导出

```bash
coffer sync export ~/coffer-bundle                       # everything except credentials
coffer sync export ~/coffer-bundle --with-credentials    # + Fernet ciphertext blobs
```

产物是一个纯文本目录,你在搬走之前就能读懂它:

```
manifest.json  knowledge/  skills/  resources/  state/  [credentials/]
```

每个配置资源一个确定性 YAML,意味着同一个未发生变化的保险库两次导出字节一致 —— 因此对两个 bundle 执行 `diff -r`,能准确看出两台机器之间到底有什么不同。

## 把它搬过去

Coffer 不负责搬运这个目录,那部分归你自己。`scp`、U 盘,或者你自己的 git 仓库都可以:

```bash
scp -r ~/coffer-bundle you@machine-b:~/coffer-bundle
```

## 在机器 B 上导入

```bash
coffer sync import ~/coffer-bundle
```

导入会把知识与技能树镜像回来,据此重建 SQLite 索引,注册每一个配置资源,并运行每个 kind 的导入后步骤 —— 因此导入进来的 agent 已装好它的 shim,导入进来的技能已有符号链接。它会报告各状态区的计数,以及任何无法在本机应用的资源(例如某个 agent 的 `config_dir` 在这台机器上并不存在);这些会连同原因一起被报告,并不致命。

- **bundle 说了算。** bundle 中包含的任何东西都会替换掉本地版本 —— 你在敲下命令时就选定了方向。
- **导入从不删除。** 本机有、而 bundle 里没有的资源保持原样不动。一个 bundle 是某一台机器的快照,而不是对"哪些东西应当到处都存在"的断言。

## 哪些会随行

**在 bundle 里:**知识的 Markdown 树(条目与摄取的文档一并)、技能主库、你的配置资源(MCP 服务器、agent、技能、渠道)、各模块自有的共享状态(渠道配对、知识作用域标签、引擎设置、MCP 能力偏好,以及 agent 插件清单),以及 —— 仅在带 `--with-credentials` 时 —— **仅以 Fernet 密文形式**的凭证。

插件清单是**一份列表,不是一个安装器**。它记录这台机器上每个 agent 装了哪些插件,落在 `state/agent-plugins/<agent>.yaml`。导入时它只把这份列表存下来;不安装任何东西,也不碰任何 agent 的配置。到了新机器上,打开这个文件,用各家自己的 CLI 装上。Coffer 刻意不写别人的私有插件格式 —— 何况就算想写,它也没有 install 这条路径。

**机器本地(永不导出):**日志、可重建的 `coffer.db` 索引、`daemon.json`、PID 文件、端口分配、聊天历史与审计日志。

## 主密钥(带外)

主密钥**绝不**写入 bundle —— 只有密文会随行。请你自己把密钥搬到每台新机器:

```bash
coffer sync key export ./master.key       # 在源机器上
# 通过可信渠道搬运 master.key —— 绝不放在 bundle 里
coffer sync key import ./master.key        # 在目标机器上
```

在密钥到位之前,导入的凭证保持**锁定**(被报为 `credentials_locked`),依赖它们的资源不会启动。

这件事上守护进程不会去打开你指定的路径。`POST /api/v1/sync/key/export` 返回密钥**材料**,`POST /api/v1/sync/key/import` 接收它;文件 I/O 由 CLI 自己做(写入时置 `0600`),Web UI 的主密钥卡片则把密钥存成一次浏览器下载,并通过 `<input type="file">` 读回来。

## 让两台机器保持一致

不存在后台收敛,也没有任何东西盯着分叉。如果两台机器发生了分叉,就按你想要的方向重新导出、重新导入一次 —— 这个手工步骤,正是为了甩掉持续同步所需的那套机制而有意接受的取舍。

Web UI 的 **Sync** 设置面板无需终端即可完成这两个操作(每个按钮打开一个目录选择器,背后是守护进程的 `/api/v1/fs` 浏览辅助接口),同样的操作也通过 REST 在 `/api/v1/sync/*` 提供。

[凭证 →](/zh/guide/credentials)
