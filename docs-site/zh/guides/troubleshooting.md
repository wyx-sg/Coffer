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
port 38470 is the port Coffer's daemon binds, but something else is already using it.
  held by: pid 5120  node server.js
```

**原因。** Coffer 绑定一个固定端口（除非你改过，否则是 38470），并且从不换到别的端口。

**解决办法。** 停掉消息里指出的进程，或者把 Coffer 换到另一个端口并重启：

```sh
coffer config set daemon.port 8765
coffer daemon restart
```

如果占用者被描述为 **another Coffer daemon**，最常见的情况是你自己的守护进程还在启动：等几秒，再运行 `coffer daemon status`。见[选择端口](/zh/guides/daemon#choose-the-port)。

### "daemon failed to start within 30s; check ~/.coffer/logs/daemon.log" {#daemon-failed-to-start-within-30s-check-coffer-logs-daemon-log}

**原因。** 守护进程已经被拉起，但没能及时发布自己。原因在日志里，因为被拉起的守护进程会把一切（包括它拒绝启动的原因）都写进 `daemon.log`。

**解决办法。** 读日志的末尾：

```sh
tail -n 50 ~/.coffer/logs/daemon.log
```

最常见的条目是端口被占用（见上文）以及数据库由更新的版本写出（见下文）。MCP shim 遇到同样的情况会报告为 `coffer-mcp-shim: daemon did not come up within 10s; check ~/.coffer/logs/daemon.log`。

### 数据库 schema 太新 {#the-database-schema-is-too-new}

**症状。** 守护进程在启动时停下，日志写着：

```text
database schema revision '0147' is newer than this Coffer build understands — it was created by a newer or different version. Upgrade Coffer, or back up and remove sqlite+aiosqlite:////Users/you/.coffer/runs.db to start fresh.
```

错误码是 `DB_SCHEMA_TOO_NEW`。

**原因。** 一个更新的版本，或者一个带有当前版本没有的迁移的开发版本，迁移了历史数据库 `runs.db`。这通常发生在回滚一次升级之后，或者在不同的源码检出之间切换之后。

**解决办法。** 重新运行那个更新的版本。如果要留在当前版本，停掉守护进程，恢复那次迁移之前留下的副本 `~/.coffer/runs.db.pre-<revision>`（见[数据库迁移与自动备份](/zh/guides/daemon#database-migrations-and-automatic-backups)）。

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
| 服务器在这台机器上被禁用，或者它的生效范围不包括这个智能体。 | 服务器的**生效范围**控件和启用开关。 | 启用它，或者在**可用范围**里加上这个智能体。 |
| 智能体的会话没有报告身份，所以它只能看到没有限定范围的服务器。 | 智能体的 MCP 条目运行 `coffer-mcp-shim` 时没带 `--agent-uid`。 | 在该智能体页面再次点击**连接**。 |
| 这个工具被单独关掉了。 | 服务器的**工具**标签页。 | 在那里打开它。 |
| 服务器启动不了：缺少它的启动器。 | 服务器显示 `npx isn't found on this machine`（或 `uvx` 等）。 | 把那个运行时装到守护进程的 `PATH` 能找到的地方（从 Dock 或 Finder 启动的应用不会读你 shell 的启动文件），然后点**测试**。Coffer 不安装运行时；它提示框里的**复制提示词**会把安装交给你的智能体，并附上它需要的命令行和 `PATH`。 |
| 服务器在出错，或者响应很慢。 | 服务器页面上的**测试**（或 `coffer mcp test <name>`）；服务器的 stderr 在 `~/.coffer/logs/upstream/<name>.log`。 | 修好服务器的配置或密钥。错过了发现阶段的服务器会在后台重试，它响应之后工具就会重新出现。出错提示框里的**复制提示词**会把诊断交给你的智能体，附上错误和 stderr 末尾，且不含任何密钥值。 |

见 [MCP 服务器](/zh/guides/mcp-servers)和[连接客户端](/zh/guides/connect-a-client)。

### 工具调用失败，日志里只写着 "upstream tool returned an error result (isError)" {#a-tool-call-fails-and-the-log-only-says-upstream-tool-returned-an-error-result-iserror}

**原因。** 上游工具在它的结果里报告了错误。Coffer 会记录这次调用失败了，但从不存储上游的消息，因为它可能回显调用的参数。

**解决办法。** 智能体能在结果里看到工具自己的错误文本。服务器那一侧，读 `~/.coffer/logs/upstream/<server>.log`。

## Web 界面 {#the-web-ui}

### "正在重新连接守护进程…" 或 "Coffer 的守护进程没有运行" {#reconnecting-to-the-daemon-or-coffer-s-daemon-isn-t-running}

**原因。** 页面连不上守护进程。最初几秒，页面仍然保留，变暗，上方是一条**正在重新连接守护进程…**提示条，在 1、2、4、8 秒后重试（**立即重试**马上再试一次）；守护进程仍然没有响应时，页面会换成**Coffer 的守护进程没有运行**。守护进程有响应、但还没有给这个页面的令牌，说明它还在启动；这会在守护进程启动时短暂出现，或者在它换了新令牌重启之后出现。

**解决办法。** 在桌面应用里，点**启动守护进程**。在浏览器里用的话，在终端运行 `coffer daemon start`（页面上有这条命令可以复制）；页面每 30 秒检查一次，或者点**重试**立即检查，守护进程一响应提示就会自己消失。桌面应用里的**打开守护进程日志**，或终端里的 `coffer log daemon`，可以看到它为什么停了。如果一直不消失，就刷新页面：每次加载时，守护进程都会把当前令牌交给页面。

### Coffer 需要 git {#coffer-needs-git}

**现象。** 应用或 Web 界面在每个页面的位置都显示 **Coffer 需要 git**；`coffer` 命令会打印原因和一段给智能体的提示词，然后以退出码 10 结束：

```text
Coffer needs git, and git isn't installed on this machine. The vault keeps its history and syncs with git. Install git, then check again: press Check again in Coffer, or run the command again.
```

`coffer daemon status` 会报告 `status:  setup`，并给出同样的说明。

**原因。** 保险库是一个 git 仓库，同步的合并需要 git 2.40 或更高版本。没有 git，或者版本太旧时，守护进程仍会启动，但停在一个设置状态：它提供页面和状态，拒绝一切需要保险库的请求（`GIT_NEEDED`，503）。它会在自己的 `PATH` 和你的登录 shell 的 `PATH` 上找 git，所以即使守护进程是从程序坞启动的，终端里能找到的 git 也会被用上。

**解决办法。** 安装或更新 git。界面上的**复制提示词**（或命令打印的提示词）把这件事交给你的智能体，由它选择适合这台机器的做法。然后点**重新检查**：git 就绪后，Coffer 会重启守护进程并正常打开。在终端里，`coffer daemon restart` 效果相同。

### 界面丢了语言或侧边栏状态 {#the-ui-lost-its-language-or-sidebar-state}

**原因。** 浏览器按 origin 保存这些偏好，而 origin 包含端口。守护进程现在的端口和以前不同，所以浏览器把它当成了另一个网站。

**解决办法。** 固定一个端口：`coffer config get daemon.port` 告诉你配置的端口；`coffer config unset daemon.port` 恢复为 38470。

### 因为功能已关闭，页面或工具不见了 {#a-page-or-tool-is-missing-because-a-feature-is-switched-off}

**原因。** 这个页面或工具属于一个在这台机器上被关掉的[实验功能](/zh/guides/experimental-features)。实验功能默认关闭，关闭的功能看起来就像不存在：没有侧边栏入口，命令面板里搜不到，直接打开它的页面链接会显示「未找到」页面。两个实验功能是知识和记忆；同步和模型提供商（含用量）始终开启，不会以这种方式被隐藏。

**解决办法。** 在**设置 → 功能**里开启它。**决定方**会显示每个功能由什么决定；如果显示 `pin`，说明 `COFFER_FEATURES` 在守护进程的环境里把它固定了，到启动守护进程的地方去改。

## 密钥和 macOS 钥匙串提示 {#secrets-and-macos-keychain-prompts}

### 命令以 9 退出："waiting for approval" {#a-command-exits-9-waiting-for-approval}

**原因。** 这次改动把一个密钥发往了它从没去过的地方（第二个引用同一个令牌的 MCP 服务器、改过的命令行或 URL、指向新远端的推送令牌），或者把 `secrets.require_approval` 关掉了，或者让 `coffer run` 去用一个你还没允许它使用的独立密钥（该密钥的页面会显示 **允许 `coffer run`…**，见[密钥](/zh/guides/secrets#allow-coffer-run-to-use-it)）。改动已经保存；在你批准之前，密钥会被扣住。命令已经打印了审批 id 和批准它们的命令（`next: coffer approval approve <id>`）。处于这种状态的 MCP 服务器不会启动，它的工具会以 `SECRET_BINDING_PENDING` 失败；自定义工具的调用会返回同样的工具错误，写明审批 id 和同一条命令，而且只影响在等待的那个环境。

**解决办法。** 运行打印出来的 `coffer approval approve <id>`（或让智能体运行），并确认桌面应用弹出的 Touch ID 或密码提示；也可以打开桌面应用直接回应（在**密钥**页面，点**查看**会打开审批对话框）。只批准你认识的目标；其余的用**拒绝**或 `coffer approval reject <id>` 拒绝。改动已经保存，无需重新运行。如果 `coffer approval approve` 以 `11` 退出，说明验证被取消或超时，审批仍在等待；以 `12` 退出，说明桌面应用没在运行且无法启动——打开它再运行一次。见[密钥 → 批准](/zh/guides/secrets#approvals)。

### 应用提示“This is not Coffer's daemon — nothing was sent” {#the-app-says-this-is-not-coffer-s-daemon-—-nothing-was-sent}

**原因。** 桌面应用要求它找到的守护进程证明自己持有主密钥，而回答没有通过校验。通常是过期的 `~/.coffer/daemon.json` 指向了一个不是你的守护进程的进程；偶尔是有东西故意占着这个端口。应用没有发出令牌，也没有发出授权。

**解决。** 退出应用，运行 `coffer daemon restart`（或停掉占着端口的进程），再打开应用。如果在你信任的机器上反复出现，用 `lsof -i :<port>` 查看占着 Coffer 端口的进程。

### 更新之后所有批准都回来了，或某个密钥又要求批准 {#every-approval-came-back-after-an-update-or-a-secret-asks-again}

**原因。** `~/.coffer/local/secret-boundary/` 下的文件是封印过的。被手工编辑过、从另一台 Mac 拷来的文件，或（签名构建里）封印功能出现之前的版本写的文件，校验不过，会被当作空文件读取；守护进程会记一次 `secret_boundary.state_unsealed`。保护回到开启，绑定需要重新批准。

**解决。** 在桌面应用里重新批准即可。丢的只是这些批准。

### 签名的 Coffer 无视我的 `HTTPS_PROXY` 或证书包 {#a-signed-coffer-ignores-my-https-proxy-or-certificate-bundle}

**原因。** 这是有意为之。签名的守护进程和模型代理会丢弃它们继承来的代理和证书变量（`HTTPS_PROXY`、`ALL_PROXY`、`NO_PROXY`、`SSL_CERT_FILE`、`NODE_EXTRA_CA_CERTS` 等），这样别的程序就没法把它们指向自己的代理或证书颁发机构。

**解决。** 在 macOS 系统设置 › 网络里设置代理，并把证书装进 macOS 钥匙串，Coffer 从那里读取两者。开发构建仍然遵循环境变量。

### 添加密钥后，HTTP 服务器或自定义工具返回 401 {#an-http-server-or-custom-tool-answers-401-after-you-add-a-key}

**原因。** 请求头的认证方案和已存的密钥对不上。Coffer 发送的是 `<方案> <密钥>`。如果密钥里因为旧的设置已经写着 `Bearer …`，而这一行的方案也是 **Bearer**，服务器收到的就是 `Bearer Bearer …`。如果这一行的方案是 **None**，而 API 要的是 `Authorization: Bearer <key>`，就少了 `Bearer` 这个词。`X-Api-Key` 这类请求头应选 **None**。

**解决。** 打开服务器的**编辑**对话框（或自定义工具分组的），找到那一行请求头，把方案设为 API 文档写的那种。密钥里只存原始密钥：在密钥那一行的选择器里选**修改 &lt;name&gt; 的值…**（在服务器的页面上是**更换密钥…** › **输入新值**），粘贴不带 `Bearer` 的密钥。保存后点**测试**。见 [MCP 服务器 → 认证方案](/zh/guides/mcp-servers#register-an-http-server)。

### 无法在终端里打印密钥 {#there-is-no-way-to-print-a-secret-from-the-terminal}

**原因。** 这是有意设计：没有任何命令、路由或 MCP 工具会返回存储的值，因为你能运行的命令，智能体都能运行。`coffer secret list` 只显示哪些值已被存储。

**解决办法。** 在桌面应用里显示或复制它，它会要求 Touch ID 或你的密码；`coffer secret reveal <ref>` 可以从终端打开这次显示，值仍然只显示在应用里。要把某个值交给一条命令，把它存成一个独立的密钥，在该密钥的页面上允许 `coffer run` 使用它（在桌面应用里用 Touch ID 或密码确认），然后用 `coffer run --secret ENV=coffer://secret/<id> -- <command>` 运行这条命令。见[密钥](/zh/guides/secrets#allow-coffer-run-to-use-it)。

见[密钥存储](/zh/guides/secret-store)。

## 保险库同步 {#vault-sync}

| 症状 | 原因 | 解决办法 |
| --- | --- | --- |
| **同步**页面显示 `deletions held`（**查看删除**） | 删除断路器扣住了某一轮。 | 在**查看暂扣的删除**里看一下列表，然后点**删除 N 个文件**或**保留文件**。重装之后，选保留文件。 |
| `stopped on conflicts` | 两台机器以 git 无法合并的方式改了同一个文件。 | 在**同步**页面上用**解决冲突**：答复每个文件，然后点**继续这一轮**。要让你的智能体合并它们，点**交给 &lt;Agent&gt;**；它的合并显示为**智能体已合并 · 请检查**之后，用**在编辑器中打开**读一遍那份副本，再点**标记为已解决**。 |
| `join required` | 这台机器还没有加入远端。 | **同步**页面上的**加入并拉取** |
| 密钥无法解密 | 这台机器没有主密钥。 | **设置 › 安全**里的**导入主密钥** |
| 推送因认证错误失败 | Coffer 不使用你的全局 git 配置，也不使用 macOS 钥匙串助手。 | 存储一个令牌并在**远端**标签页的**密钥**里选中它，或者使用一把不需要 passphrase 提示的 SSH 密钥。 |
| 你解释不了的 `push failed`、`sign-in refused` 或 `remote unreachable` | 远端那一侧的问题：受保护的分支、没有写权限的令牌、网络或 VPN 问题。 | **同步**页面上消息旁边的提示词会把诊断交给你的智能体，且不含令牌。然后点**重试**。 |

完整列表见[保险库同步的故障排查](/zh/guides/vault-sync#troubleshooting)。

## 消息渠道 {#channels}

### 机器人不回复 {#the-bot-does-not-answer}

先打开这个消息渠道的页面：它的状态行会说明哪里不对。

| 页面上显示的内容 | 原因 | 解决办法 |
| --- | --- | --- |
| 没有响应，或者是守护进程错误 | 守护进程没在运行。消息渠道在守护进程里运行。 | `coffer daemon start`。在 macOS 上，**设置 → 守护进程 → 开机自启动** 可以在没有 Coffer 窗口的情况下让它一直运行。 |
| 在另一台机器上运行 | 这个消息渠道绑定在共享这个保险库的另一台机器上，由那台机器来回复。 | 什么都不用做，或者在该消息渠道的页面上用**在本机运行…**把它挪到这里。 |
| **无处运行** | 这个消息渠道没有指定任何机器。 | 在该消息渠道**设置**标签页的**运行在**里选一台机器。 |
| **未配对** | 还没有人和这个机器人配对，所以每条消息都会被忽略。 | 在该消息渠道的**总览**上点**生成配对码**，然后从你自己的账号把配对码发给机器人。 |
| 入站状态下有一行 `ws error:` | 某个 SeaTalk 消息渠道的连接失败了。错误会说明原因，比如另一个进程占着这个连接。 | 按错误指出的原因去修。 |
| 一条警告 | 平台侧的某个设置让部分配置失效了。 | 按警告里的办法去修。 |

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
3. 打印出来的错误原文，以及产生它的命令或操作。用 `coffer -v …` 重新运行失败的 `coffer` 命令，可以得到完整的 traceback 和 HTTP 上下文。
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
