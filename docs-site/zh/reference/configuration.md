---
title: 配置
description: Coffer 读取的每个环境变量、daemon-config.json 键、实验功能开关和运行时设置，以及它们的默认值和读取位置。
---

# 配置 {#configuration}

本页列出所有会改变 Coffer 行为的配置项：环境变量、`~/.coffer/daemon-config.json` 的键、实验功能开关，以及你在 **设置** 或命令行中修改的运行时设置。它写给需要准确了解某个设置的名称、默认值和作用的运维人员和贡献者。

Coffer 把配置放在五个地方，每个地方都有其理由：

| 位置 | 存放内容 | 为什么放这里 |
| --- | --- | --- |
| 环境变量 | 运维用的应急开关、测试和开发覆盖 | 由单个进程在启动时读取；不会被持久化 |
| `~/.coffer/daemon-config.json` | 守护进程和模型代理的端口、机器名和 id、实验功能 | 需要在其他任何东西打开之前读到，且只属于本机 |
| 保险库（`~/.coffer/vault/state/settings/internal-engine.json`） | Coffer 自用模型、整理的归属机器、维护任务 | 所有机器共享的设置；随[保险库同步](/zh/guides/vault-sync)同步 |
| 本地状态（`~/.coffer/local/`） | 保留策略、同步远端、生效范围 | 只对本机成立；从不同步 |
| 浏览器 `localStorage` | Web 界面偏好 | 按浏览器保存，从不发给守护进程 |

::: warning 环境变量与脱离启动的守护进程
守护进程通常是脱离调用方启动的——由命令行、智能体的 MCP shim、桌面应用或开机自启服务拉起——它继承的是启动它的那个进程的环境，而不是你的 shell 配置文件。只有在启动守护进程的进程的环境里设置环境变量，它才能到达守护进程，例如 `COFFER_FEATURES=run=off,models=off coffer daemon restart`。想长期保留的设置，应该放进 `daemon-config.json` 或 **设置**。
:::

## 环境变量 {#environment-variables}

### 守护进程与网络 {#daemon-and-network}

| 名称 | 默认值 | 作用 |
| --- | --- | --- |
| `COFFER_FEATURES` | 未设置 | 为该守护进程固定实验功能状态，覆盖本机设置和默认值（关闭）。语法见下文。启动时读取一次。 |
| `COFFER_ALLOWED_HOSTS` | 未设置 | 逗号分隔的额外 `Host` 请求头名称，守护进程除 `127.0.0.1`、`localhost` 和 `::1` 之外也会应答它们；`*` 关闭该检查。请求中写的是其他主机，或是另一个端口上的回环名称时，返回 `403 HOST_NOT_ALLOWED`。从不放宽 `Origin` 检查。正式发布构建会忽略它。 |
| `COFFER_CORS_ORIGINS` | 未设置 | 逗号分隔的精确源列表，整体替换跨源允许列表，同时作用于 CORS 和 `Origin` 检查。不设置时，守护进程只允许桌面应用的源（`tauri://localhost`、`http://tauri.localhost`）。守护进程自己的源始终允许；其他任何源返回 `403 ORIGIN_NOT_ALLOWED`。正式发布构建会忽略它。 |
| `COFFER_DEV_CORS` | 未设置 | `1` 会把 Vite 开发服务器的源 `http://localhost:5173` 和 `http://127.0.0.1:5173` 加入默认允许列表，同时作用于 CORS 和 `Origin` 检查。设置了 `COFFER_CORS_ORIGINS` 时忽略。正式发布构建会忽略它。`make dev` 会设置它。 |
| `COFFER_WEBUI_DIR` | 内置 | 存放已构建 Web 界面（`index.html`）的目录。不设置时，守护进程提供冻结二进制中打包的界面，在源码检出中则提供 `frontend/dist`。 |
| `COFFER_PRICE_REFRESH` | 未设置 | `off` 强制关闭每日模型价格表刷新，无论 `price_refresh` 怎么设；价格取自构建中附带的列表。测试套件和 e2e 守护进程会设置它。 |
| `COFFER_MODEL_PROXY` | 未设置 | `off` 让守护进程不启动也不监管[本地模型代理](/zh/architecture/model-proxy)；其他任何值或不设置则保持开启。测试套件会设置它。 |
| `COFFER_QUOTA_POLL` | 未设置 | `off` 停止在后台拉取 Codex 的订阅额度（每次拉取会起一个短命的 `codex app-server`）。测试套件会设置它。 |

### MCP 网关 {#mcp-gateway}

| 名称 | 默认值 | 作用 |
| --- | --- | --- |
| `COFFER_TOOL_TIERING` | `auto` | `off` 向客户端列出所有上游工具。其他任何值都保持按预算分层开启。 |
| `COFFER_TOOL_TIERING_BUDGET` | `50` | 直接列出多少个上游工具，其余的只能通过 `coffer__search_tools` 找到。非正数或格式错误的值回退到默认值。 |
| `COFFER_TOOL_TIERING_WINDOW_DAYS` | `90` | 为预算给工具排序时使用的调用历史的回溯窗口。 |
| `COFFER_MCP_MAX_CONCURRENT_SPAWNS` | `4` | 一个会话同时冷启动多少个上游 MCP 服务器。 |
| `COFFER_MCP_SESSION_IDLE_S` | `1800` | `/mcp` 会话可空闲多少秒，之后回收器会关闭它及其上游进程。 |
| `COFFER_MCP_SESSION_REAPER_INTERVAL_S` | `60` | 回收器两次扫描之间的秒数。 |
| `COFFER_MCP_SHIM_PATH` | 未设置 | `coffer-mcp-shim` 二进制的绝对路径，会写进智能体的 MCP 条目，优先于 `PATH` 和打包附带的副本。文件不存在时忽略。 |

### 聊天与消息渠道 {#chat-and-channels}

| 名称 | 默认值 | 作用 |
| --- | --- | --- |
| `COFFER_TURN_IDLE_TIMEOUT_SECONDS` | `300` | 聊天或消息渠道的轮次在没有任何事件的情况下可持续多少秒，超过后看门狗会取消它。`0`、负数或非数字会关闭看门狗。 |
| `COFFER_SEATALK_SDK_DIR` | `~/.coffer/vendor` | 导入 SeaTalk WebSocket SDK 包（`seatalk_oapi_sdk`）的目录。 |
| `COFFER_SEATALK_STREAM_INTERVAL` | `0.1` | SeaTalk 回复两次流式更新之间的最小秒数。 |

### 存储位置 {#storage-locations}

保险库、本地状态、内容和派生状态都没有单独的覆盖变量：它们都在需要时从 `$HOME` 解析，`coffer path` 会打印各个根目录。下面的变量只移动历史数据库、模型代理的暂存目录和日志。它们主要是为了让测试和开发环境永远不碰真实的 home；要让守护进程使用另一个 home，请设置 `HOME`。

| 名称 | 默认值 | 作用 |
| --- | --- | --- |
| `COFFER_DB_URL` | `sqlite+aiosqlite:///~/.coffer/runs.db` | 历史数据库的 SQLAlchemy URL。无论它怎么设，主密钥文件（`master.key`）都留在 `~/.coffer`。 |
| `COFFER_PROXY_SPOOL_DIR` | `~/.coffer/proxy-usage` | 模型代理写入用量暂存文件、守护进程从中读取的目录。两个进程必须看到相同的值。 |
| `COFFER_LOG_DIR` | `~/.coffer/logs` | 存放 `daemon.log`、`proxy.log`、上游服务器日志、MCP shim 日志以及开机自启服务输出的目录。 |
| `HOME` | 用户的主目录 | 每个 `~/.coffer` 路径都在需要的那一刻相对 `$HOME` 解析，所以换一个 `HOME` 就得到完全独立的保险库。 |

### 安装脚本 {#installer}

由 `install.sh`（[`docs-site/public/install.sh`](https://github.com/wyx-sg/Coffer/blob/main/docs-site/public/install.sh)）读取。

| 名称 | 默认值 | 作用 |
| --- | --- | --- |
| `COFFER_INSTALL_DIR` | `~/.coffer/bin` | 二进制的安装位置。 |
| `COFFER_VERSION` | 最新发布版 | 要安装的发布 tag，例如 `v0.1.0`（开头的 `v` 可省略）。 |
| `COFFER_NO_MODIFY_PATH` | `0` | `1` 跳过把安装目录加入 shell 配置文件。 |
| `ZDOTDIR`、`XDG_CONFIG_HOME` | shell 默认值 | 用于找到要修改的 zsh 和 fish 配置文件。 |

```sh
curl -fsSL --proto '=https' --tlsv1.2 https://wyx-sg.github.io/Coffer/install.sh \
  | COFFER_VERSION=v0.1.0 COFFER_NO_MODIFY_PATH=1 sh
```

### 开发与测试 {#development-and-tests}

这些是给贡献者用的。不要在你日常使用的守护进程上设置它们。

| 名称 | 默认值 | 作用 |
| --- | --- | --- |
| `COFFER_PORT_RANGE_START`、`COFFER_PORT_RANGE_END` | 未设置 | 绑定该范围内第一个空闲端口，而不是配置的单一端口。优先级高于 `daemon-config.json`。只设置一端时，另一端回退到 `8000` 或 `8009`。 |
| `COFFER_EVAL_CAPTURE` | 未设置 | 把每次 `coffer__search_tools` 查询及其结果以 JSON 行的形式记录下来，供评测工具使用。`1`、`true` 或 `yes` 写入 `~/.coffer/eval-capture.jsonl`；其他任何非假值都被当作输出路径。 |
| `COFFER_RUN_BENCHMARKS` | 未设置 | `1` 运行慢到进不了 `make verify` 的性能预算测试，比如调和单轮成本（`make verify-benchmark`）。 |

### Coffer 为它启动的进程设置的变量 {#variables-coffer-sets-for-processes-it-starts}

Coffer 从不从自己的环境读取这些变量；它为子进程设置它们。你会在智能体的配置或进程列表中看到它们。

| 名称 | 设置给 | 用途 |
| --- | --- | --- |
| `CLAUDE_CONFIG_DIR` | Claude Code 的轮次 | 当已注册智能体的配置目录不是 `~/.claude` 时，让 Claude Code 指向它。 |
| `CODEX_HOME` | Codex 的轮次 | 当已注册智能体的配置目录不是 `~/.codex` 时，让 Codex 指向它。 |
| `COFFER_GIT_TOKEN`、`COFFER_GIT_USERNAME` | 保险库同步期间的 `git` | 同步远端的令牌及随之发送的用户名，由 credential helper 在运行时读取，所以令牌永远不会出现在 `argv` 中或磁盘上。 |
| `PATH`、`HOME` | 开机自启服务 | 安装服务时从你的登录 shell 采集，这样守护进程能找到 `npx`、`uvx` 等上游启动器。 |

桌面应用读取 `HOME`（或 `USERPROFILE`）、`SHELL` 和 `PATH`，用来定位 `~/.coffer` 并探测登录 shell 的 `PATH`；它自己不定义任何变量。

## daemon-config.json {#daemon-config-json}

`~/.coffer/daemon-config.json` 存放守护进程在打开数据库之前就需要的设置，以及必须只留在一台机器上的设置。写入时权限为 `0600`。守护进程以合并方式写入并保留它不认识的键，所以较新 Coffer 写的文件在旧版本下也不会丢内容。无法解析的文件会被忽略，并在 `daemon.log` 中记一条警告，改用默认值。

```json
{
  "port": 8123,
  "proxy_port": 8001,
  "machine_name": "studio",
  "machine_id": "3f0c9a…",
  "features": {},
  "price_refresh": true
}
```

| 键 | 类型 | 默认值 | 作用 | 修改方式 |
| --- | --- | --- | --- | --- |
| `port` | 1024–65535 的整数，或 `null` | `8000` | 守护进程绑定的唯一端口。守护进程宁可拒绝启动也不会换到别的端口。下次启动时生效。 | `coffer config set daemon.port <port>`、`coffer config unset daemon.port` |
| `proxy_port` | 1024–65535 的整数，或 `null` | `8001` | [本地模型代理](/zh/architecture/model-proxy)在 `127.0.0.1` 上绑定的端口，也是投射到智能体配置中的端口。无效值会被忽略并记警告，改用默认值。代理下次启动时生效。 | 编辑文件 |
| `machine_name` | 字符串 | 去掉 `.local` 的主机名 | 本机在保险库同步中的显示名称。可随意修改；没有任何东西引用它。 | **同步** 页面、`coffer sync machine rename` |
| `machine_id` | 字符串 | 由主机派生 | 由主机派生的机器 id 的缓存，在同步的保险库中用来指代本机。删除后会重新算出同一个值。 | 由守护进程写入 |
| `features` | 布尔值组成的对象 | `{}` | 本机的实验功能开关。立即生效。注册表中没有声明的键会被忽略。 | **设置 → 功能**、`coffer config set feature.<key> on\|off` |
| `price_refresh` | 布尔值 | `true` | 守护进程是否每天从 genai-prices 刷新一次模型价格表。关闭时使用构建中附带的价格表。每次刷新时读取。 | **设置 › 通用 → 刷新模型价格**、`coffer config set prices.refresh on\|off` |

守护进程的运行时状态——它的 pid、端口和 API 令牌——在另一个文件 `~/.coffer/daemon.json` 中，启动时创建、退出时删除。见[文件与目录](/zh/reference/filesystem#daemon-files)。

## 实验功能 {#experimental-features}

实验功能是在你开启之前一直关闭的能力，按机器开启；关闭期间它看起来就像不存在——它的页面、命令和路由都不可用——但不会删除它保存的任何东西。每个注册表条目写明它的键、它拥有的路由和资源类型。

注册表里有四个功能，按这个顺序：

| 键 | 关闭的内容 | REST 前缀 |
| --- | --- | --- |
| `knowledge` | 知识 | `/api/v1/knowledge` |
| `memory` | 记忆 | `/api/v1/memory` |
| `sync` | 保险库同步 | `/api/v1/sync` |
| `models` | 模型提供商、本地模型代理和用量 | `/api/v1/providers`、`/api/v1/models`、`/api/v1/proxy`、`/api/v1/usage` |

其余一切始终开启，包括对话和消息渠道。其他任何键都不是功能：`coffer config set feature.<key>` 会报告未知设置，`PUT /api/v1/daemon/features/<key>` 会返回 `FEATURE_UNKNOWN`。注册表没有声明的键，其已保存的设置会被忽略。

功能关闭期间，它的路由返回 `404`，错误码为 `FEATURE_DISABLED`，命令行会打印开启它的命令。注册表位于 [`domain/features.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/domain/features.py)。

### 功能状态如何决定 {#how-a-feature-s-state-is-decided}

优先级从高到低：

1. **固定值** — 守护进程所在进程的 `COFFER_FEATURES` 中的条目。被固定的功能无法从界面或命令行修改（`409 FEATURE_PINNED`）。
2. **设置** — `daemon-config.json` 中 `features` 下本机的值。
3. **默认值** — 每个构建中的每个功能都是关。

**设置 → 功能** 在每个构建中都会列出这四个功能，状态的来源报告为 `pin`、`setting` 或 `default`。被固定的功能，开关不可用。

### COFFER_FEATURES 语法 {#coffer-features-syntax}

逗号分隔的 `key=value` 条目列表。`on`、`true` 和 `1` 表示开启；`off`、`false` 和 `0` 表示关闭。条目两侧的空白会被忽略，值不区分大小写。未知的键或格式错误的条目会被记录并跳过，绝不会让守护进程停下。

```sh
COFFER_FEATURES="knowledge=on,models=off" coffer daemon restart
```

### 命令 {#commands}

```sh
coffer config list feature.             # every feature, its state, and what decided it (feature.knowledge, feature.memory, feature.sync, feature.models)
coffer config set feature.<key> on      # switch on, at once; <key> is knowledge, memory, sync or models
coffer config set feature.<key> off
coffer config unset feature.<key>       # back to off
```

面向任务的指南见[实验功能](/zh/guides/experimental-features)。

## 运行时设置 {#runtime-settings}

这些设置保存在保险库或 `~/.coffer/local/` 中（注明的除外），在 Web 界面或桌面应用的 **设置** 中修改，或者用命令行修改。标注为*同步*的设置会通过[保险库同步](/zh/guides/vault-sync)带到其他机器。

### 设置 → 通用 {#settings-→-general}

| 设置 | 默认值 | 作用 | 命令行 | 存储位置 |
| --- | --- | --- | --- | --- |
| **每页行数** | `20`（可选 10、20、50、100） | 每个表格的初始每页行数。 | — | 浏览器 `localStorage`（`coffer.pageSize`） |
| **首选编辑器** | 系统默认 | Coffer 打开托管文件时使用的应用或命令。 | — | 浏览器 `localStorage`（`coffer.preferredEditor`） |
| **开机自启动** | 关 | 安装一个 launchd agent（`~/Library/LaunchAgents/dev.coffer.daemon.plist`），在登录时启动守护进程并在崩溃后重启它。仅限 macOS。 | `coffer daemon service install`、`uninstall`、`status` | plist 文件 |
| **实验功能**（设置 → 功能） | 关 | 见[实验功能](#experimental-features)。 | `coffer config set feature.<key>` | `daemon-config.json` |

### 设置 › 通用 → Coffer 自用模型 {#settings-›-general-→-coffer-s-model}

内部引擎的设置是保险库中的一个文档 `state/settings/internal-engine.json`，全部都是*同步*的。你也可以手动编辑这个文件；文件不存在表示全部使用默认值。每项都对应一个 `coffer config` 键；`coffer config list engine.` 会打印它们及其当前值和默认值。

| 设置 | 默认值 | 作用 | 命令行 |
| --- | --- | --- | --- |
| **使用的模型提供商** / **模型** | 无 | Coffer 自己的任务（记忆提炼、知识整理、生成描述）所用的连接和模型。没有模型时，这些任务不调用模型。 | `coffer config set engine.provider <connection>`、`coffer config set engine.model <model>`、`coffer config unset engine.model` |
| **单次调用的时间上限** | `60` 秒 | 对 Coffer 自用模型的一次调用最长可以用多久。 | `coffer config set engine.timeout <s>`、`coffer config unset engine.timeout` |
| **转写用的模型提供商** / **转写模型** | 关 | 语音消息在交给智能体之前用于转写的连接和模型。其中任一项未设置时，Coffer 不做任何转写。 | `coffer config set transcribe.provider <connection>`、`coffer config set transcribe.model <model>`、`coffer config unset transcribe.model` |
| **维护任务** — aggregate | 开，每 1 小时 | 把智能体自己的记忆文件读入派生的记忆树。 | `coffer config set engine.upkeep.aggregate.enabled on\|off`、`coffer config set engine.upkeep.aggregate.interval <s>` |
| **维护任务** — distil | 开，每 6 小时 | 按自己的间隔运行，而不是在每次 aggregate 之后：用 Coffer 自用模型把每个分区的新原始条目提炼成笔记，并重写它的 `MEMORY.md`。没有新内容的分区不产生任何调用。 | `coffer config set engine.upkeep.distil.…` |
| **维护任务** — curate | 开，每 1 小时 | 把每个知识集收件箱中的新材料整理进它的文档。 | `coffer config set engine.upkeep.curate.…` |
| **刷新模型价格** | 开 | 每天一次从 genai-prices 获取最新的模型价格表；关闭时使用构建中附带的价格表。这一项是**本机**的（`daemon-config.json` 中的 `price_refresh`），不同步。 | `coffer config set prices.refresh on\|off`、`coffer config unset prices.refresh` |
| 整理的归属机器（**Runs on:**） | 每台机器 | 在同步的保险库中唯一允许运行整理的那台机器。 | `coffer config set engine.curate_owner this\|<machine id>`、`coffer config unset engine.curate_owner` |

维护任务的间隔最小为 60 秒；`coffer config unset engine.upkeep.<pass>.interval` 会把某个任务恢复为默认值。`coffer daemon status` 显示正在进行的任务。

### 同步远端 {#sync-remote}

同步远端是一个本机文件 `~/.coffer/local/sync/remote.json`，在 **同步** 页面（**配置**）或用 `coffer sync remote set` 设置。见[保险库同步](/zh/guides/vault-sync)。

| 设置 | 默认值 | 作用 | 命令行 |
| --- | --- | --- | --- |
| **间隔（秒）** | `3600` | 两次自动同步轮次之间的秒数。至少为 `60`：更小的值会被拒绝。 | `coffer sync remote set --interval <s>` |
| **推送密钥** | 无 | 保存推送令牌的密钥。 | `coffer sync remote set --secret-ref <ref>` |
| 用户名 | `coffer` | 与 HTTPS 令牌一起发送的用户名。GitHub 和 GitLab 会忽略它；Bitbucket 和 Azure DevOps 需要真实的用户名。 | `coffer sync remote set --username <name>` |
| **包含加密密钥** | 关 | 提交并推送 `vault/secret/`（只有密文，绝不含主密钥）。 | `coffer sync remote set --with-secret`、`--without-secret` |
| **自动同步** | 开 | 关闭会暂停定时器；远端及其历史保留，**立即同步** 仍能执行一轮。 | `coffer sync remote pause`、`resume` |

### 设置 → 数据 {#settings-→-data}

保留策略决定各类行保留多久。保留任务在启动时清理一次，之后每 6 小时一次。策略只属于本机，保存在 `~/.coffer/local/retention.json`。

| 策略 | 键 | 默认值 | 作用 |
| --- | --- | --- | --- |
| **审计日志** | `audit_log` | 365 天 | 删除早于窗口的审计条目。 |
| **MCP 调用** | `mcp_invocations` | 30 天 | 删除网关调用日志行。 |
| **同步轮次** | `sync_runs` | 90 天 | 删除同步轮次的历史。 |
| **自动归档闲置对话** | `conversations_archive` | 7 天 | 归档这么久没有新消息的对话。 |
| **删除已归档对话** | `conversations` | 30 天 | 在归档后这么久删除已归档的对话及其消息。 |

键是 `coffer config` 键 `retention.<key>` 的后缀；两条聊天策略都作用于 `conversations` 表。策略可以设为 **永久保留**（值为 `forever`）。同一次运行还会删除 `~/.coffer/content/channel-media` 和 `~/.coffer/content/chat-media` 中超过 30 天的文件，以及超过 7 天的旧 shim 日志和上游日志。

```sh
coffer config list retention.
coffer config set retention.audit_log 90
coffer config set retention.mcp_invocations forever
coffer log prune
```

### 设置 → 安全 {#settings-→-security}

| 设置 | 默认值 | 作用 | 命令行 |
| --- | --- | --- | --- |
| **将主密钥存入系统钥匙串** | 关（文件） | 在 `~/.coffer/master.key` 和系统钥匙串（服务 `coffer`，条目 `master-key`）之间移动密钥的主密钥。主密钥本身不变，所以已存的密钥仍然可读。这次移动会被审计。仅限开发构建：签名的发布版把主密钥保存在自己的钥匙串访问组中，拒绝移动。 | `coffer config set secrets.storage file\|keychain` |
| 新密钥去处需审批（`secrets.require_approval`） | 开 | 开启时，密钥发往新的去处或目标之前，要先在桌面应用中等待审批；正在使用的密钥换新值也一样。关闭时，两者都无需询问直接批准。开启立即生效；关闭则要等桌面应用中的一次审批。见[密钥](/zh/guides/secrets#switching-the-protection-off)。 | `coffer config set secrets.require_approval on\|off` |

## 相关内容 {#related}

- [文件与目录](/zh/reference/filesystem)
- [运行守护进程](/zh/guides/daemon)
- [实验功能](/zh/guides/experimental-features)
- [密钥存储](/zh/guides/secret-store)
- [命令行参考](/zh/reference/cli)
- [分发与发布](/zh/architecture/distribution)
