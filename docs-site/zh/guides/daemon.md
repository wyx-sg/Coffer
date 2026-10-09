---
title: 运行守护进程
description: 启动、停止和监管 Coffer 的守护进程，固定它的端口，设置开机自启，并安全地升级、回滚和备份保险库。
---

# 运行守护进程 {#running-the-daemon}

守护进程就是 Coffer 进程本身：每个保险库一个后台程序，在 `127.0.0.1` 上提供 MCP 网关、REST API 和 Web 界面。本页写给安装了 Coffer、想弄清楚以下问题的人：守护进程怎么启动、监听在哪里、往磁盘写了什么，以及怎样升级、回滚和备份。

## 守护进程的作用 {#what-the-daemon-is-for}

Coffer 的其他部分都是守护进程的客户端：`coffer` 命令行、你的智能体启动的 `coffer-mcp-shim`、浏览器标签页里的 Web 界面，以及[桌面应用](/zh/guides/desktop-app)。它们自己都不保存保险库状态。

你很少需要手动启动它。任何需要守护进程的入口，发现没有在运行时都会自己启动一个，并与调用方脱离：

- 任何需要和守护进程通信的 `coffer` 命令（`coffer daemon status` 除外，它只查看），
- 通过 `coffer-mcp-shim` 连接 Coffer 的智能体，
- 启动时的桌面应用。

每个保险库只运行一个守护进程。如果两个入口同时抢着启动，`~/.coffer/daemon.lock` 上的锁会让其中一个胜出，另一个直接连上它。守护进程只绑定回环接口，每个管理调用都要带上它启动时生成的令牌，所以它提供的任何东西都无法从其他机器访问。

## 启动、停止和检查守护进程 {#start-stop-and-check-the-daemon}

```sh
coffer daemon start      # spawn it in the background, if none is running
coffer daemon status     # ask the running daemon how it is; never starts one
coffer daemon stop       # SIGTERM, then wait for it to exit
coffer daemon restart    # stop (if running), then start
```

在 Web 界面里，**设置 → 守护进程 → 重启** 也能从浏览器重启它：守护进程先启动继任者，继任者等它退出后再绑定端口，然后它自己退出，页面从新守护进程（带着新令牌）重新加载。桌面应用的重启则是从外部先停再启。`coffer daemon restart` 始终从外部执行，所以对已经不响应的守护进程也有效。

`coffer daemon status` 打印守护进程对自身的报告：

```text
status:  ready
version: 0.2.0
port:    38470
pid:     41822
```

守护进程正常服务时 `status` 为 `ready`，关闭过程中为 `draining`，等待 git 时为 `setup`：这时命令还会打印原因和一段给智能体的提示词（见 [Coffer 需要 git](/zh/guides/troubleshooting#coffer-needs-git)）。没有更早的阶段可看：守护进程启动完成后才打开端口。两个[实验功能](/zh/guides/experimental-features)——知识和记忆——在你开启之前都是关闭的。脚本里可加 `--json`。

没有守护进程运行时，`coffer daemon status` 打印 `status:  not running`（`--json` 下为 `{"status": "stopped"}`），退出码为 3。它不会启动守护进程，所以它的回答不会改变它所报告的对象；要启动请用 `coffer daemon start`。

几个值得了解的行为：

- `start` 判断「已在运行」靠的是询问守护进程，而不是检查 `daemon.json` 是否存在。崩溃后残留的发现文件不会阻止启动。只有新的守护进程应答了状态调用，`start` 才报告成功；如果守护进程拒绝启动（需要先迁移保险库、git 太旧），它会说明原因并指向 `daemon.log`。
- `start` 在拉起进程前先检查端口。如果端口被其他程序占用，你会立刻看到诊断，而不是等十秒超时（见[端口被占用时](#when-the-port-is-taken)）。
- `stop` 在发信号前先确认记录的 pid 确实是 Coffer 守护进程。如果该 pid 已被其他进程复用，`stop` 会删除过期的 `daemon.json` 并说明情况，而不会误杀无关进程。
- 在守护进程绑定前读取的设置（端口），要靠 `restart` 才能生效。

要打开守护进程提供的界面，在浏览器里访问 `http://127.0.0.1:<port>`；端口在 `~/.coffer/daemon.json` 里（默认 38470）。[桌面应用](/zh/guides/desktop-app)会替你打开。

## 选择端口 {#choose-the-port}

守护进程默认监听 **38470 端口**，从不扫描其他端口。固定端口能让界面的书签一直可用，也能让浏览器为该源保存的内容（界面语言、侧边栏状态、首选编辑器）不会因为端口变动而重置。

要改端口：

```sh
coffer config get daemon.port        # the configured port
coffer config set daemon.port 8765   # always bind 8765 from now on
coffer daemon restart                # apply it (or Restart now on Settings → Daemon)
coffer config unset daemon.port      # back to 38470
```

`daemon.port` 接受 1024 到 65535 的端口。该设置写入 `~/.coffer/daemon-config.json`，守护进程在绑定前读取它，所以这些命令在没有守护进程时也能用。这是有意为之：最需要改端口的时候，恰恰是守护进程因端口被占而起不来的时候。**设置 → 守护进程** 通过运行中的守护进程写同一个文件，点它的 **立即重启** 让改动生效，页面随后从新端口重新加载。

改动在下次启动时生效。如果守护进程正在旧端口上运行，`set` 和 `unset` 会提示你运行 `coffer daemon restart`。

### 端口被占用时 {#when-the-port-is-taken}

如果端口被其他进程占用，守护进程宁可拒绝启动也不会换端口，并指出是谁占用了它：

```text
port 38470 is the port Coffer's daemon binds, but something else is already using it.
  held by: pid 5120  python3 -m http.server 38470
  fix one of:
    stop that process, then    coffer daemon start
    use a different port       coffer config set daemon.port <port>
```

如果占用者本身就是 Coffer 守护进程，消息会说明这一点：最常见的情况是你自己的守护进程还在启动，等几秒再运行 `coffer daemon status` 即可。如果它服务的是另一个保险库（例如在临时 `HOME` 下跑的测试），消息会给出结束它的 `kill` 命令。

## 开机自启守护进程（macOS） {#start-the-daemon-at-login-macos}

按需启动时，守护进程恰好在智能体当天第一次调用、或没有打开 Coffer 窗口时收到聊天消息的那一刻是停着的，谁先来谁就得等冷启动。在 macOS 上，你可以把它装成每用户的 launchd agent：

打开 **设置 → 守护进程 → 开机自启动**：守护进程会在登录时启动，崩溃后重启。

该服务就是 plist 文件 `~/Library/LaunchAgents/dev.coffer.daemon.plist`（label 为 `dev.coffer.daemon`）。它：

- 在你登录时启动守护进程；
- **只在非正常退出后**重启它。主动停止（`coffer daemon stop`、从桌面应用退出，或守护进程因被另一个取代而让位）不会触发重启；
- 带上你自己的 `PATH`（安装时从登录 shell 读取），所以用 `npx` 或 `uvx` 启动的 MCP 服务器仍能找到；
- 运行 `~/.coffer/bin/coffer-daemon`，这个软链接始终指向当前构建，所以升级后依然有效（源码安装会回退到 Python 模块命令）；
- 与其他任何方式启动时一样，写入同一个 `~/.coffer/logs/daemon.log`。

关掉开关会删除 plist，但不会停掉正在运行的守护进程。每次改动都会记录一条 `daemon_residency_updated` 审计条目。

::: info
开机自启服务仅限 macOS。在其他系统上，**开机自启动** 开关会报告不支持。
:::

## 守护进程读写的文件 {#files-the-daemon-reads-and-writes}

| 路径 | 说明 |
| --- | --- |
| `~/.coffer/daemon.json` | 所有客户端都读的发现文件：`version`（文件的 schema 版本）、`pid`、`port`、`token`、`started_at`、`binary_path`。权限 `0600`，原子写入，守护进程退出时删除。文件缺失或格式错误即视为「没有守护进程」。 |
| `~/.coffer/daemon.lock` | 保证每个保险库只有一个守护进程的锁。它在两次运行之间一直留在磁盘上；锁在于打开的文件，而不在于文件是否存在。 |
| `~/.coffer/daemon-config.json` | 在其他任何东西打开之前读取的本机设置：`port`、`proxy_port`（本地模型代理的端口）、`features`（本机的实验功能开关）、`machine_id` 和 `machine_name`。权限 `0600`。从不同步。 |
| `~/.coffer/vault/`、`local/`、`content/`、`derived/`、`runs.db` | Coffer 的状态，分为五种存储类别；见[持久化](/zh/architecture/persistence)。 |
| `~/.coffer/logs/` | 日志；见下文。 |
| `~/.coffer/bin/` | 已部署的二进制（仅冻结构建）；见[升级与回滚](#upgrades-and-rollback)。 |

完整布局见[文件与目录](/zh/reference/filesystem)。

## 日志 {#logs}

守护进程、它拉起的进程以及代表它行事的各个入口写的所有内容都进同一个文件，一条时间线就能回答「那前后还发生了什么」：

```text
~/.coffer/logs/daemon.log        one JSON object per line for the daemon's own records
~/.coffer/logs/daemon.log.1..3   rotations (10 MB each, three kept)
~/.coffer/logs/shim-<pid>-<time>.log     one per coffer-mcp-shim process
~/.coffer/logs/upstream/<server>.log     each stdio MCP server's stderr
```

超过七天的 shim 日志和轮转出去的上游日志会被自动清理。`daemon.log` 及其轮转文件从不删除，只做轮转。在守护进程的环境中设置 `COFFER_LOG_DIR` 可以把目录放到别处。

你很少需要直接打开这个文件：**活动 → 守护进程日志** 标签页会读取它并支持按级别过滤，`coffer log daemon` 在命令行打印同样的记录（`--errors` 只看错误，`--since 1h` 看最近一段时间）。`coffer path logs` 打印目录和 `daemon.log` 的位置，这样 shell 里的智能体可以直接 grep 这个文件。见[活动与审计](/zh/guides/activity)。

## 访问令牌 {#the-access-token}

守护进程每次启动都生成一个新的随机令牌，并写入 `daemon.json`。客户端从那里读取；守护进程提供给浏览器的页面也带着它，所以重启后普通刷新一下就能重新认证，无需你做任何事。

不重启而轮换令牌：在 **设置 → 安全 → 守护进程访问令牌** 点 **轮换…** 并确认。读 `daemon.json` 的客户端会拿到新值；已打开的浏览器标签页需要刷新。

## 升级与回滚 {#upgrades-and-rollback}

冻结构建（桌面应用或发布归档）每次启动都会部署自己的二进制。每个版本有自己的目录，对外的名字是指向其中的软链接：

```text
~/.coffer/bin/coffer           -> 0.2.0/coffer
~/.coffer/bin/coffer-daemon    -> 0.2.0/coffer-daemon
~/.coffer/bin/coffer-mcp-shim  -> 0.2.0/coffer-mcp-shim
~/.coffer/bin/0.2.0/           the build now in use
~/.coffer/bin/0.1.1/           the previous build, kept for rollback
```

文件是原子复制的，软链接也是原子切换的，所以升级过程中启动 `coffer-mcp-shim` 的智能体永远不会看到写了一半的二进制。保留最新的两个版本目录，更旧的会被清理。新构建不再附带的二进制，其链接会被删除。

守护进程比连接到它的命令行和 shim 进程活得更久，所以装了新版本后，回应请求的可能仍是旧守护进程。每个客户端都会比较版本并给出警告，然后继续执行：

```text
coffer: WARNING: attached to a Coffer daemon at version 0.1.1 (/Users/you/.coffer/bin/0.1.1/coffer-daemon) but this coffer is 0.2.0; run `coffer daemon restart` to serve the current build
```

运行 `coffer daemon restart`，警告就会消失。桌面应用会把同样的情况显示为 **守护进程版本过旧** 提示，并附带 **重启守护进程** 按钮。

回滚到上一个构建：

1. 停止守护进程：`coffer daemon stop`。
2. 把链接指回旧目录：
   ```sh
   cd ~/.coffer/bin
   for b in coffer coffer-daemon coffer-mcp-shim; do ln -sfn 0.1.1/$b $b; done
   ```
3. 如果新构建迁移过历史数据库，先恢复它迁移前留的副本（见下一节），否则旧构建会拒绝打开它。
4. 重新启动：`coffer daemon start`。

## 数据库迁移与自动备份 {#database-migrations-and-automatic-backups}

历史数据库 `runs.db` 的 schema 迁移在守护进程启动时执行。迁移修改它之前，守护进程会把它（连同 `-wal` 和 `-shm` 附属文件）复制到原文件旁边，命名为 `runs.db.pre-<revision>`，其中 `<revision>` 是该文件当时所处的 schema 版本。保留最新的三份副本。schema 已是最新时不会复制，也就是说，除了升级后的第一次启动，每次启动都不复制。

回到迁移前的副本：

```sh
coffer daemon stop
cd ~/.coffer
mv runs.db runs.db.broken
cp runs.db.pre-<revision> runs.db          # and the -wal / -shm files, if present
```

然后启动与该 schema 匹配的构建。

### DB_SCHEMA_TOO_NEW {#db-schema-too-new}

如果数据库被更新的构建迁移过，或者被一个带有本构建所没有的迁移的开发分支迁移过，守护进程启动时会停下并报：

```text
database schema revision '0147' is newer than this Coffer build understands — it was created by a newer or different version. Upgrade Coffer, or back up and remove sqlite+aiosqlite:////Users/you/.coffer/runs.db to start fresh.
```

重新安装那个更新的构建，或者恢复该构建迁移前留下的 `runs.db.pre-*` 副本。


## 备份保险库 {#back-up-a-vault}

Coffer 保存的一切都在 `~/.coffer` 下。无法重建的部分是：

| 路径 | 为什么重要 |
| --- | --- |
| `vault/` | 每个资源定义、共享设置、知识集、技能文件夹和加密密钥，以及它们在 `vault/.git` 中的完整历史。 |
| `local/` | 本机的智能体、生效范围、保留策略、同步远端和密钥审批。 |
| `content/` | 附件和聊天工作目录。 |
| `runs.db`（+ `-wal`、`-shm`） | 对话、审计日志、调用日志、同步轮次、用量。 |

`derived/`，包括从智能体自己的记忆文件派生出的记忆树，都可以重新生成。要取得一致的副本，先停止守护进程：

```sh
coffer daemon stop
cp -R ~/.coffer ~/coffer-backup-$(date +%F)
coffer daemon start
```

::: warning
这份副本不包含主密钥，主密钥在 macOS 钥匙串中：没有它，副本里的密钥只是谁也读不了的密文。在桌面应用中备份主密钥（**设置 › 安全 › 备份主密钥**），并像对待密码一样保管这份备份。
:::

如果你在多台机器上用 Coffer，[保险库同步](/zh/guides/vault-sync)会把保险库仓库连同历史推送到你自己的 git 仓库，这也顺带成了知识、技能和资源定义的异地备份。

## 智能体的 home 变量不会被继承 {#agent-home-variables-are-not-inherited}

如果你从一个导出了 `CLAUDE_CONFIG_DIR` 或 `CODEX_HOME` 的 shell 启动守护进程，守护进程会在启动时把它们从自己的环境中移除，并在日志中记下移除了哪些。否则它拉起的每个智能体都会针对那个目录运行，而 Coffer 却把技能和配置投递到智能体注册的目录里。注册时指定了自定义配置目录的智能体，在 Coffer 拉起它时会在它自己的变量中拿到该目录。见[智能体](/zh/guides/agents)。

## 工作原理 {#how-it-works}

检测或拉起、发现文件、取代机制以及优雅退出流程，见[守护进程与进程](/zh/architecture/daemon)。发布打包和二进制布局见[分发与发布](/zh/architecture/distribution)。

## 相关内容 {#related}

- [故障排查](/zh/guides/troubleshooting)
- [活动与审计](/zh/guides/activity)
- [实验功能](/zh/guides/experimental-features)
- [桌面应用](/zh/guides/desktop-app)
- [命令行参考](/zh/reference/cli)
- 规格：[daemon](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/daemon/spec.md) · 决策记录：[Detect-or-Spawn](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/daemon-detect-or-spawn.md)
