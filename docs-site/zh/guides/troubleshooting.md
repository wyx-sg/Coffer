---
title: 故障排查
description: Coffer 常见问题的症状、原因和解决办法：守护进程、智能体连接、缺失的工具、Web 界面、升级、钥匙串提示、同步和消息渠道。
---

# 故障排查 {#troubleshooting}

本页按领域列出运行 Coffer 时可能遇到的问题，每个问题都分为症状、原因和解决办法。这里引用的每条消息都是 Coffer 实际会打印的。如果你的问题不在这里，先看[为 bug 报告收集信息](#collect-information-for-a-bug-report)。

::: tip 先问你的智能体
有 shell 的智能体可以读取 Coffer 自己的记录：`coffer log daemon --errors --since 1h` 查看守护进程日志，`coffer log audit --since 1h` 查看审计日志，`coffer path logs` 查看 `daemon.log` 在哪里，这样它就能直接 grep 这个文件。问一句「查一下 Coffer 的日志，看刚才什么失败了」往往是最快的第一步。见[活动与审计](/zh/guides/activity)。
:::

## 守护进程 {#the-daemon}

### 守护进程启动不了：端口被占用 {#the-daemon-will-not-start-the-port-is-taken}

**症状。** `coffer daemon start`（或任何命令）打印：

```text
port 8000 is the port Coffer's daemon binds, but something else is already using it.
  held by: pid 5120  node server.js
```

**原因。** Coffer 绑定一个固定端口（除非你改过，否则是 8000），并且从不换到别的端口。

**解决办法。** 停掉消息里指出的进程，或者把 Coffer 换到另一个端口并重启：

```sh
coffer config set daemon.port 8765
coffer daemon restart
```

如果占用者被描述为 **another Coffer daemon**，最常见的情况是你自己的守护进程还在启动：等几秒，再运行 `coffer daemon status`。见[选择端口](/zh/guides/daemon#choose-the-port)。

### "daemon failed to start within 10s; check ~/.coffer/logs/daemon.log" {#daemon-failed-to-start-within-10s-check-coffer-logs-daemon-log}

**原因。** 守护进程已经被拉起，但没能及时发布自己。原因在日志里，因为被拉起的守护进程会把一切（包括它拒绝启动的原因）都写进 `daemon.log`。

**解决办法。** 读日志的末尾：

```sh
tail -n 50 ~/.coffer/logs/daemon.log
```

最常见的条目是端口被占用（见上文）、数据库由更新的版本写出，以及 home 目录还需要做一次性升级（见下文）。MCP shim 遇到同样的情况会报告为 `coffer-mcp-shim: daemon did not come up within 10s; check ~/.coffer/logs/daemon.log`。

### 数据库 schema 太新 {#the-database-schema-is-too-new}

**症状。** 守护进程在启动时停下，日志写着：

```text
database schema revision '0118' is newer than this Coffer build understands — it was created by a newer or different version. Upgrade Coffer, or back up and remove sqlite+aiosqlite:////Users/you/.coffer/runs.db to start fresh.
```

错误码是 `DB_SCHEMA_TOO_NEW`。

**原因。** 一个更新的版本，或者一个带有当前版本没有的迁移的开发版本，迁移了历史数据库 `runs.db`。这通常发生在回滚一次升级之后，或者在不同的源码检出之间切换之后。

**解决办法。** 重新运行那个更新的版本。如果要留在当前版本，停掉守护进程，恢复那次迁移之前留下的副本 `~/.coffer/runs.db.pre-<revision>`（见[数据库迁移与自动备份](/zh/guides/daemon#database-migrations-and-automatic-backups)）。

### 守护进程要求运行 `coffer migrate` {#the-daemon-asks-for-coffer-migrate}

**症状。** 守护进程拒绝启动，并提到 `coffer migrate`（`VAULT_MIGRATION_REQUIRED`），或提到 `coffer migrate --resume`（`VAULT_MIGRATION_ON_HOLD`）。

**原因。** 这个 home 是由采用保险库布局之前的 Coffer 写出的，仍然把状态放在 `coffer.db` 里；或者一次升级回滚留下了它的暂停标记。

**解决办法。** 停掉守护进程，然后运行 `coffer migrate --rehearse` 和 `coffer migrate`；回滚之后，先运行 `coffer migrate --resume`。见[升级已有的 Coffer](/zh/guides/upgrading)。

### 命令警告守护进程是另一个版本 {#a-command-warns-that-the-daemon-is-a-different-version}

**症状。**

```text
coffer: WARNING: attached to a Coffer daemon at version 0.1.1 (/Users/you/.coffer/bin/0.1.1/coffer-daemon) but this coffer is 0.2.0; run `coffer daemon restart` to serve the current build
```


**原因。** 你安装了新版本，而旧的守护进程还在运行。守护进程比连接它的命令行和 shim 进程活得更久，所以回答请求的仍是旧版本。

**解决办法。** 运行 `coffer daemon restart`。在桌面应用里，**守护进程版本过旧**提示上有一个**重启守护进程**按钮。

### "daemon not reachable — it may have crashed" {#daemon-not-reachable-—-it-may-have-crashed}

**原因。** 命令行找到了守护进程，然后在请求中途断开了连接。

**解决办法。** 运行 `coffer daemon status`。如果它打印 `not running`，运行 `coffer daemon start`，然后读 `daemon.log`，看上一个守护进程是怎么结束的。

## 智能体和工具 {#agents-and-tools}

### 智能体在某个 Coffer 工具上报告 "All connection attempts failed" {#an-agent-reports-all-connection-attempts-failed-on-a-coffer-tool}

**原因。** 智能体的 `coffer-mcp-shim` 连不上守护进程。守护进程重启时，shim 会重新读取 `~/.coffer/daemon.json`，连上新的守护进程，并自己重试这次调用。只有在几秒内都没有守护进程起来时，它才报告这个错误，比如在 `coffer daemon stop` 之后，或者新的守护进程启动失败时。

**解决办法。**

1. 运行 `coffer daemon status`。如果它打印 `not running`，运行 `coffer daemon start`，它会启动一个守护进程，或者说明为什么启动不了。
2. 再调用一次这个工具；shim 会在下一次调用时重新连接。
3. 如果智能体仍然失败，重新连接它的 MCP 服务器，或者重启智能体会话，这会启动一个新的 shim。

shim 自己的日志是 `~/.coffer/logs/shim-<pid>-<time>.log`。

### 智能体期望的某个工具不在它的工具列表里 {#a-tool-the-agent-expects-is-not-in-its-tool-list}

按顺序逐一排查这些原因：

| 原因 | 怎么判断 | 解决办法 |
| --- | --- | --- |
| 工具没有被公布，因为工具目录超出了列出预算（默认 50 个上游工具）。 | 服务器健康，工具也已启用。 | 工具照样能用。让智能体用 `coffer__search_tools` 找到它，或者在守护进程的环境里设置 `COFFER_TOOL_TIERING=off`，列出全部工具。 |
| 服务器在这台机器上被禁用，或者它的生效范围不包括这个智能体。 | 服务器的生效范围控件，或 `coffer mcp scope <name>`。 | 启用它，或者加上这个智能体：`coffer mcp enable <name>`、`coffer mcp scope <name> --agents <agent>`。 |
| 智能体的会话没有报告身份，所以它只能看到没有限定范围的服务器。 | 智能体的 MCP 条目运行 `coffer-mcp-shim` 时没带 `--agent-uid`。 | 重新接入这个智能体：`coffer agent connect <agent>`。 |
| 这个工具被单独关掉了。 | 服务器的**工具**标签页，或 `coffer mcp cap list <name>`。 | 在那里打开它，或者运行 `coffer mcp cap enable <name> tool:<tool>`。 |
| 服务器启动不了：缺少它的启动器。 | 服务器显示 `npx isn't found on this machine`（或 `uvx` 等）。 | 把那个运行时装到守护进程的 `PATH` 能找到的地方（从 Dock 或 Finder 启动的应用不会读你 shell 的启动文件），然后点**测试**。Coffer 不安装运行时；它提示框里的**复制提示词**（或 `coffer mcp handoff <name>`）会把安装交给你的智能体，并附上它需要的命令行和 `PATH`。 |
| 服务器在出错，或者响应很慢。 | `coffer mcp test <name>`；服务器的 stderr 在 `~/.coffer/logs/upstream/<name>.log`。 | 修好服务器的配置或密钥。错过了发现阶段的服务器会在后台重试，它响应之后工具就会重新出现。出错提示框里的**复制提示词**（或 `coffer mcp test <name> --prompt`）会把诊断交给你的智能体，附上错误和 stderr 末尾，且不含任何密钥值。 |

见 [MCP 服务器](/zh/guides/mcp-servers)和[连接客户端](/zh/guides/connect-a-client)。

### 工具调用失败，日志里只写着 "upstream tool returned an error result (isError)" {#a-tool-call-fails-and-the-log-only-says-upstream-tool-returned-an-error-result-iserror}

**原因。** 上游工具在它的结果里报告了错误。Coffer 会记录这次调用失败了，但从不存储上游的消息，因为它可能回显调用的参数。

**解决办法。** 智能体能在结果里看到工具自己的错误文本。服务器那一侧，读 `~/.coffer/logs/upstream/<server>.log`。

## Web 界面 {#the-web-ui}

### "Daemon offline" 或 "Daemon not running" {#daemon-offline-or-daemon-not-running}

**原因。** 页面连不上守护进程（**守护进程离线**），或者守护进程有响应但不接受页面的令牌（**Daemon not running**）；后一种情况会在守护进程启动时短暂出现，或者在它换了新令牌重启之后出现。

**解决办法。** 在浏览器里用的话，在终端运行 `coffer daemon start`；页面每 30 秒检查一次，提示会自己消失。如果一直不消失，就刷新页面：每次加载时，守护进程都会把当前令牌交给页面。在桌面应用里，用**重启守护进程**。

### 界面丢了语言、每页条数或侧边栏状态 {#the-ui-lost-its-language-page-size-or-sidebar-state}

**原因。** 浏览器按 origin 保存这些偏好，而 origin 包含端口。守护进程现在的端口和以前不同，所以浏览器把它当成了另一个网站。

**解决办法。** 固定一个端口：`coffer config get daemon.port` 告诉你配置的端口；`coffer config unset daemon.port` 恢复为 8000。

### 页面或命令不见了，或命令提示某个功能已关闭 {#a-page-or-command-is-missing-or-a-command-says-a-feature-is-switched-off}

**原因。** 这个页面、命令或工具属于一个在这台机器上被关掉的[实验功能](/zh/guides/experimental-features)。实验功能默认关闭，关闭的功能看起来就像不存在：没有侧边栏入口，命令面板里搜不到，直接打开它的页面链接会显示「未找到」页面。四个功能是知识、记忆、同步和模型提供商。

**解决办法。** 在**设置 → 功能**里开启它，或者运行 `coffer config set feature.<key> on`（需要某个功能的命令会原样打印这一行）。`coffer config list feature.` 会显示每个功能由什么决定；如果显示 `pin`，说明 `COFFER_FEATURES` 在守护进程的环境里把它固定了，到启动守护进程的地方去改。

## 密钥和 macOS 钥匙串提示 {#secrets-and-macos-keychain-prompts}

### 每次守护进程启动时 macOS 都要求访问钥匙串 {#macos-asks-for-keychain-access-every-time-the-daemon-starts}

**原因。** 两者之一：

- 密钥的主密钥存放在系统钥匙串里（你在**设置 → 安全**里选择了这样做）。读取它每次守护进程启动都要一次提示。
- 某个资源引用了一个不在 Coffer 加密存储里的密钥。每次启动时，Coffer 会在系统钥匙串里查找一次那个引用，找到就把它移进存储。读取被锁定或被拒绝时，会在下次启动时重试，于是又一次提示。

**解决办法。**

- 把主密钥移回文件 `~/.coffer/master.key`：
  ```sh
  coffer config set secrets.storage file
  ```
  或者在**设置 → 安全**里关闭**将主密钥存入系统钥匙串**。
- 用 `coffer secret list` 找出被引用但缺失的密钥，然后用 `coffer secret set <ref>` 逐个存储。

### 命令以 9 退出："waiting for approval in the Coffer app" {#a-command-exits-9-waiting-for-approval-in-the-coffer-app}

**原因。** 这次改动把一个密钥发往了它从没去过的地方（第二个引用同一个令牌的 MCP 服务器、改过的命令行或 URL、指向新远端的推送令牌），或者替换了某个已经在用的值，或者把 `secrets.require_approval` 关掉了。改动已经保存；在你批准之前，密钥会被扣住。处于这种状态的 MCP 服务器不会启动，它的工具会以 `SECRET_BINDING_PENDING` 失败。

**解决办法。** 打开桌面应用，回应它显示的批准请求（或者用 `coffer secret approvals` 查看）。只批准你认识的目标；其余的用 `coffer secret reject <id>` 拒绝。加上 `--wait` 重新运行命令，让它等你的答复。见[密钥 → 批准](/zh/guides/secrets#approvals)。

### 无法在终端里打印密钥 {#there-is-no-way-to-print-a-secret-from-the-terminal}

**原因。** 这是有意设计：没有任何命令、路由或 MCP 工具会返回存储的值，因为你能运行的命令，智能体都能运行。`coffer secret get` 只确认某个值已被存储。

**解决办法。** 在桌面应用里显示或复制它，它会要求 Touch ID 或你的密码。要把某个值交给一条命令，把它存成一个独立的密钥，然后用 `coffer run --secret <name> -- <command>` 运行这条命令。见[密钥](/zh/guides/secrets)。

见[密钥存储](/zh/guides/secret-store)。

## 保险库同步 {#vault-sync}

| 症状 | 原因 | 解决办法 |
| --- | --- | --- |
| `coffer sync status` 以 1 退出并显示 `deletions held` | 删除断路器扣住了某一轮。 | 看一下列表（`coffer sync hold`），然后运行 `coffer sync hold --confirm` 或 `--restore`。重装之后，选恢复。 |
| `stopped on conflicts` | 两台机器以 git 无法合并的方式改了同一个文件。 | 运行 `coffer sync conflicts`，用 `coffer sync resolve <path> --mine\|--theirs\|--edited` 答复每个文件，然后运行 `coffer sync continue`；或者在**同步**页面上用**解决冲突**。要让你的智能体合并它们，点**交给智能体**（或把 `coffer sync conflicts --prompt` 给它）；它的合并显示为**智能体已合并 · 请检查**之后，看一眼 diff 再点**标记为已解决**（`coffer sync resolve <path> --edited`）。 |
| `join required` | 这台机器还没有加入远端。 | `coffer sync join` |
| 密钥无法解密 | 这台机器没有主密钥。 | `coffer sync key import <file>` |
| 推送因认证错误失败 | Coffer 不使用你的全局 git 配置，也不使用 macOS 钥匙串助手。 | 存储一个令牌并传入 `--secret-ref`，或者使用一把不需要 passphrase 提示的 SSH 密钥。通过 HTTPS 使用 GitLab 时，加上 `--username oauth2`。 |
| 你解释不了的 `push failed`、`sign-in refused` 或 `remote unreachable` | 远端那一侧的问题：受保护的分支、没有写权限的令牌、网络或 VPN 问题。 | `coffer sync status --prompt`（或者**同步**页面上消息旁边的提示词）会把诊断交给你的智能体，且不含令牌。然后点**重试**。 |

完整列表见[保险库同步的故障排查](/zh/guides/vault-sync#troubleshooting)。

## 消息渠道 {#channels}

### 机器人不回复 {#the-bot-does-not-answer}

先检查消息渠道的运行状态：

```sh
coffer channel show <name>
```

| `show` 打印的内容 | 原因 | 解决办法 |
| --- | --- | --- |
| 没有响应，或者是守护进程错误 | 守护进程没在运行。消息渠道在守护进程里运行。 | `coffer daemon start`。在 macOS 上，`coffer daemon service install` 可以在没有 Coffer 窗口的情况下让它一直运行。 |
| `runs on: <id> (another machine)` | 这个消息渠道绑定在共享这个保险库的另一台机器上，由那台机器来回复。 | 什么都不用做，或者把它挪到这里：`coffer channel bind <name>` |
| `runs on: unbound (runs nowhere)` | 这个消息渠道没有指定任何机器。 | `coffer channel bind <name>` |
| `peer: not paired` | 还没有人和这个机器人配对，所以每条消息都会被忽略。 | 运行 `coffer channel pair <name>`，然后从你自己的账号把配对码发给机器人。 |
| `inbound: websocket (…)` 并带有一行 `ws error:` | 某个 SeaTalk 消息渠道的连接失败了。错误会说明原因，比如另一个进程占着这个连接。 | 按错误指出的原因去修。 |
| `warning: …` | 平台侧的某个设置让部分配置失效了。 | 按警告里的办法去修。 |

只接受来自已配对所有者的消息。在群聊里，机器人只响应所有者发来的、在叫它的消息。见[消息渠道](/zh/guides/channels)。

## 日志在哪里 {#where-the-logs-are}

| 文件 | 写入者 |
| --- | --- |
| `~/.coffer/logs/daemon.log`（+ `.1`–`.3`） | 守护进程以及代表它做事的一切。可以在**活动 → 守护进程日志**里查看。 |
| `~/.coffer/logs/shim-<pid>-<time>.log` | 智能体启动的每个 `coffer-mcp-shim` 进程。保留七天。 |
| `~/.coffer/logs/upstream/<server>.log` | 每个 stdio MCP 服务器的 stderr。 |

`COFFER_LOG_DIR` 可以挪动这个目录。要把一次失败的 REST 调用对应到它的日志行，从响应里取出 `X-Coffer-Trace` 头，在 `daemon.log` 里搜索它；见[关联失败的请求](/zh/guides/activity#correlate-a-failed-request-with-the-log-x-coffer-trace)。

## 为 bug 报告收集信息 {#collect-information-for-a-bug-report}

1. 版本：`coffer daemon status`，或者**设置 → 关于 → 复制诊断信息**。
2. 你是怎么安装的（桌面应用、发布压缩包、源码），以及你的 macOS 版本。
3. 打印出来的错误原文，以及产生它的命令或操作。用 `coffer -v …` 重新运行失败的命令行命令，可以得到完整的 traceback 和 HTTP 上下文。
4. `daemon.log` 中相关的行（按失败发生的时间过滤），或者失败请求的 `X-Coffer-Trace` id。

::: warning 检查你粘贴的内容
Coffer 从不把密钥值写进它的日志，但上游 MCP 服务器会把它们自己的 stderr 写进 `upstream/*.log`，里面可能有任何东西。分享日志片段之前先读一遍。
:::

在 [GitHub Issues](https://github.com/wyx-sg/Coffer/issues) 上提交报告。如果是安全问题，请改为遵循[安全策略](/zh/contributing/security)。

## 相关内容 {#related}

- [运行守护进程](/zh/guides/daemon)
- [活动与审计](/zh/guides/activity)
- [常见问题](/zh/guides/faq)
- [错误码](/zh/reference/error-codes)
