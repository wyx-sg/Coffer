# 快速上手——仓库导出与导入

> English: [quickstart.md](./quickstart.md)

把一个 Coffer 仓库搬到你自己的另一台机器上：在机器 A 上导出到一个目录，把那个目录搬
过去，在机器 B 上导入。主密钥永不随目录同行——你只需带外把它带过去一次。

## 1. 在机器 A 上导出仓库

```bash
coffer sync export ~/coffer-bundle
```

命令会写出一个普通目录，并报告都放进去了什么：各状态区的计数（知识、记忆、技能、资源、
状态）以及 bundle 路径。

```
manifest.json  knowledge/  memory/  skills/  resources/  state/
```

里面全是文本，因此你能确切读到自己即将带走的是什么——
`resources/mcp_server/confluence.yaml` 就是每个资源一个可读文件。

如果还要把凭据一起带上，请显式要求：

```bash
coffer sync export ~/coffer-bundle --with-credentials
```

这会加上 `credentials/<ref>.enc`——**只有** Fernet 密文。主密钥永不写入 bundle。不带这个
参数时，没有任何凭据材料会离开这台机器；这是默认行为，因为一个导出目录很容易被随手落在
什么地方。

## 2. 把目录搬到机器 B

用什么方式都行——Coffer 不负责搬运：

```bash
scp -r ~/coffer-bundle you@machine-b:~/coffer-bundle
```

U 盘或者你自己的 git 仓库同样可以。

## 3. 把主密钥带过去（仅当你导出了凭据时）

在机器 A 上：

```bash
coffer sync key export ~/coffer-master.key
```

通过你信任的渠道把这个文件移到机器 B（密码管理器、安全拷贝、U 盘）——**不要**放在
bundle 里面。在机器 B 上：

```bash
coffer sync key import ~/coffer-master.key
```

> 跳过这一步导入照样成功，但导入进来的凭据会保持**锁定**：它们被报为
> `credentials_locked`，依赖它们的资源在你导入密钥之前不会启动。

## 4. 在机器 B 上导入

```bash
coffer sync import ~/coffer-bundle
```

机器 B 现在拥有同样的知识、记忆、技能、已注册资源与共享状态。每个 kind 的导入后步骤都
已经跑过，所以导入进来的 agent 已经装好了它的 shim、导入进来的 skill 绑定已经有了符号
链接——这些资源和你手工注册出来的一样可用。

命令会打印一份摘要：各状态区的计数，以及任何无法在本机应用的资源（例如某个 agent 的
`config_dir` 在这台机器上并不存在）连同它的 ref 与原因。这些只是被报告，并不致命——
其余的一切照常导入了。

## 导入会动什么、不会动什么

- **bundle 说了算。** bundle 中包含的任何东西都会替换掉本地版本。你在敲下命令时就选定了
  方向，因此没有什么需要仲裁。
- **导入从不删除。** 机器 B 有、而 bundle 里没有的资源保持原样不动。一个 bundle 是某一台
  机器的快照，而不是对"哪些东西应当到处都存在"的断言。
- **仅本机的东西不随行。** 日志、`coffer.db`、`daemon.json`、聊天历史与审计日志都留在
  原处；机器 B 上的 SQLite 索引由导入进来的文件重建。

## 让两台机器保持一致

不存在后台收敛。如果两台机器发生了分叉，就按你想要的方向重新导出、重新导入一次——这个
手工步骤正是 [Vault Export and Import](../../docs/decisions/vault-export-import.md) 有意接受的
取舍。

由于导出是确定性的，两个未发生变化的仓库导出的 bundle 字节一致，因此你可以 diff 它们来
看出到底哪里不同：

```bash
diff -r ~/bundle-from-a ~/bundle-from-b
```

## REST / Web UI

这两个操作同样可以通过 `/api/v1/sync/*` 以及 Web UI 的 **Sync** 设置面板使用——一个导出
按钮和一个导入按钮，各自打开原生目录选择器，外加用于比对指纹、执行带外密钥传递的主密钥
卡片。

密钥相关的两条路由传的是密钥**材料**，不是路径：`POST /sync/key/export` 收 `{}`，返回
`{"material": "<fernet key text>"}`；`POST /sync/key/import` 收 `{"material": "…"}`。
上面那两条 CLI 命令仍然写文件、读文件——只是文件 I/O 由 CLI 自己做，守护进程从此不打开
任何由调用方指定的路径。在 Web UI 里，导出会落成一次浏览器下载，导入则从
`<input type="file">` 读取。
