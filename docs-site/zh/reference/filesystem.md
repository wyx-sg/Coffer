---
title: 文件与目录
description: Coffer 在 ~/.coffer 下保存的每个文件和目录，以及它写进智能体配置目录的内容：归谁所有、是否同步、能否安全删除。
---

# 文件与目录 {#files-and-directories}

本页列出 Coffer 在磁盘上保存的一切：`~/.coffer` 目录树、它之外的那一个文件，以及 Coffer 写进每个已注册智能体自身配置目录的条目。备份保险库、安全清理，或者想弄清楚某个文件是干什么的，都可以查这一页。

下面所有路径都相对 `$HOME` 解析。目录树没有逐项覆盖的方式，环境变量能挪动的只有日志、模型代理的用量暂存目录和历史数据库（见[配置](/zh/reference/configuration#storage-locations)）。

## ~/.coffer 目录树 {#the-coffer-tree}

状态分五种[存储类别](/zh/architecture/persistence)保存，每种一个目录或文件，另外还有守护进程和安装程序需要的文件：

```text
~/.coffer/
├── vault/                        # the vault: a git repository — configuration and content
├── local/                        # this machine only: never synced, can be set again
├── content/                      # media and the chat workspace: your only copy, not synced
├── runs.db                       # history (SQLite, WAL mode)
├── runs.db-wal, runs.db-shm      # SQLite write-ahead log and shared memory
├── runs.db.pre-<revision>        # copy taken before a schema migration (newest 3 kept)
├── derived/                      # rebuilt from the rest: always safe to delete
├── master.key                    # secret master key (when stored as a file)
├── machine-id                    # fallback machine id (only if the host gives none)
├── daemon.json                   # running daemon: pid, port, API token
├── daemon.lock                   # spawn lock
├── daemon-config.json            # ports, machine name, experimental features
├── proxy.json                    # running model proxy: pid, port, control token
├── proxy-usage/                  # model proxy usage spool, ingested by the daemon
├── bin/                          # deployed builds and the stable symlinks
├── logs/                         # daemon, proxy, shim and upstream logs
├── upstream-pids/                # pid files of spawned upstream MCP servers
├── vendor/                       # operator-supplied SeaTalk SDK
└── eval-capture.jsonl            # only with COFFER_EVAL_CAPTURE set
```

### 保险库 {#the-vault}

`~/.coffer/vault/` 从 Coffer 第一次运行起就是一个 git 仓库，不管你开没开同步。每一次被接受的改动都是一个提交，并注明写入者。见[手动编辑保险库](/zh/guides/vault-files)。

```text
~/.coffer/vault/
├── manifest.json                       # {"schema_version": 3}
├── resources/<kind>/<name>.json        # mcp_server, skill, channel, provider, knowledge
├── state/mcp-preferences/<server>.json
├── state/channel-peers/<channel>.json
├── state/settings/internal-engine.json
├── knowledge/<collection>/             # documents, README.md, hidden .inbox/
├── skills/<name>/                      # skill master folders
├── secret/<ref>.enc
├── machines/<machine id>.json
└── .git/
```

| 路径 | 用途 | 所有者 | 是否同步 | 能否安全删除 |
| --- | --- | --- | --- | --- |
| 整个 `vault/` | 你的配置和亲手编写的内容，以及 `.git/` 里的完整历史。 | 你、守护进程、同步 | 是，开启[保险库同步](/zh/guides/vault-sync)时 | **不能。** 这是唯一一份。复制前先停掉守护进程。 |
| `manifest.json` | 保险库的布局版本号 `schema_version`，每轮同步合并任何东西之前先读它。 | 守护进程 | 是 | 不能 |
| `resources/<kind>/<name>.json` | 每个资源一个 JSON 文件：`uid`、`kind`、`format_version`、`name`、可选的 `title`、`description`、`config`。身份以文件里的 `uid` 为准，而不是路径。 | 你、守护进程 | 是 | 不能：所有同步的机器上这个资源都会消失。 |
| `state/mcp-preferences/<server>.json` | 你在某个 MCP 服务器上关掉的工具、提示词和资源，附带该服务器的 uid。 | 你、守护进程 | 是 | 可以：该服务器上的一切都会重新打开。 |
| `state/channel-peers/<channel>.json` | 与某个消息渠道配对的身份，包括所有者。 | 守护进程 | 是 | 配对关系会丢失。 |
| `state/settings/internal-engine.json` | Coffer 的模型、整理所有者机器、单次调用超时、转写模型，以及每类维护任务的开关和间隔。不存在时用默认值。 | 你、守护进程 | 是 | 可以：设置恢复默认。 |
| `knowledge/<collection>/` | 一个知识集：任意层级嵌套的 Markdown 文档，加一个描述它的 `README.md`。你、你的智能体和 Coffer 的整理任务都会编辑这些文件。 | 你、守护进程 | 是 | **不能。** 这是写下来的知识。 |
| `knowledge/<collection>/.inbox/` | 等待整理进文档的条目：上传文件提取出的文本、智能体写进去的 Markdown 文件、在知识页面添加的文档。 | 守护进程 | 是 | 不能：尚未整理的条目会丢失。 |
| `skills/<name>/` | 托管技能的主副本：`SKILL.md`、其他文件，以及 `.coffer.meta.json`（Coffer 的元数据）。智能体拿到的是指向这个目录的符号链接。 | 你、守护进程 | 是 | **不能。** 删掉目录会让投递给智能体的链接失效。 |
| `secret/<ref>.enc` | 一个密钥的 Fernet 密文，权限 `0600`。从不包含主密钥本身。除非同步远端允许携带密钥，否则不进仓库。 | 守护进程 | 仅在 `--with-secret` 时 | **不能。** 密钥就没了。 |
| `machines/<machine id>.json` | 每台参与同步的机器一个描述文件：名称、操作系统、主机名、Coffer 版本、上一轮同步、上次收敛的提交、密钥指纹、智能体及其插件。 | 同步（每台机器只写自己的） | 是 | 在**同步**页面的机器列表里用**退役**移除另一台机器。 |
| `.git/` | 上面所有文件的历史。每轮同步前的快照是 `refs/tags/coffer/pre-apply/` 下的标签。`.git/info/exclude` 列出仓库忽略的内容。 | 守护进程 | 同步的就是这些提交 | **不能。** 所有版本和回滚能力都会丢失。 |

### 本机 {#local}

| 路径 | 用途 | 所有者 | 是否同步 | 能否安全删除 |
| --- | --- | --- | --- | --- |
| `local/resources/agent/<name>.json` | 本机的智能体，每个一个资源文件。 | 守护进程 | 从不 | 该智能体在本机被取消注册。 |
| `local/reach.json` | 每个资源在本机的生效范围：是否启用，对哪些智能体生效。 | 守护进程 | 从不 | 每个资源恢复为所属类型的默认生效范围。 |
| `local/engine.json` | 本机上次修改 Coffer 引擎设置的时间。 | 守护进程 | 从不 | 可以。 |
| `local/retention.json` | 每张可清理表的保留期限，以及上次清理的时间。 | 守护进程 | 从不 | 可以：使用默认值。 |
| `local/curation.json` | 每篇知识文档在上次整理完成时的内容，用来察觉之后有人手动改过。 | 守护进程 | 从不 | 整理会把每篇文档重新读一遍。 |
| `local/skill-source-status.json` | 本机上次在每个从 Git 导入的技能来源处看到的情况。 | 守护进程 | 从不 | 可以：下次检查会补上。 |
| `local/secret/` | 仅限本机的密文，比如模型代理的令牌。 | 守护进程 | 从不 | 代理令牌会重新生成；使用提供商的智能体会重新读取自己的令牌。 |
| `local/secret-boundary/` | `bindings.json`、`approvals.json`、`settings.json`、`times.json`：每个密钥被批准发往哪个目的地、待处理的审批、密钥边界的开关、每个密钥首次存到本机的时间。 | 守护进程 | 从不 | 每个密钥都要重新等待审批。 |
| `local/sync/remote.json` | 唯一的同步远端：URL、分支、推送用密钥引用、是否携带密钥、间隔、是否暂停。 | 守护进程 | 从不 | 本机忘掉这个远端。 |
| `local/sync/round.json` | 一轮停下的同步、一次保留，或一次加入尚待选择的项目，以及你目前的回答。 | 守护进程 | 从不 | 下一轮会重新提问。 |

本机文件解析失败时，会被挪到一边改名为 `<name>.unreadable-<n>`，并按空文件读取。

### 内容 {#content}

| 路径 | 用途 | 所有者 | 是否同步 | 能否安全删除 |
| --- | --- | --- | --- | --- |
| `content/channel-media/` | 通过 Telegram 和 SeaTalk 收到的附件，保存下来让智能体能打开。超过附件保留期（默认 30 天）的文件会被清理。 | 守护进程 | 否 | 可以。 |
| `content/chat-media/` | 在对话页面上附加的文件：每次上传的字节（`<id><ext>`），旁边是一个记录名称、类型和大小的小文件 `<id>.json`。超过附件保留期（默认 30 天）的文件会被清理。 | 守护进程 | 否 | 可以。对话里仍显示文件标签，但之后的轮次再也打不开它。 |
| `content/workspace/` | 没选工作目录时，对话默认使用的工作目录。 | 守护进程 | 否 | 仅在没有对话使用它时可以。 |

### 历史与密钥 {#history-and-keys}

| 路径 | 用途 | 所有者 | 是否同步 | 能否安全删除 |
| --- | --- | --- | --- | --- |
| `runs.db` | 历史：审计日志、MCP 调用日志、对话和消息、消息渠道的线程与发件箱、同步轮次与用量。`COFFER_DB_URL` 可以指定另一个数据库。 | 守护进程 | 从不 | 丢的是历史，不是配置。先停守护进程。 |
| `runs.db-wal`、`runs.db-shm` | SQLite 预写日志和共享内存索引。WAL 里可能有已提交但还没合并进 `runs.db` 的数据。 | 守护进程 | 否 | **不能**，而且守护进程运行时，绝不要只复制 `runs.db` 而不带上它们。 |
| `runs.db.pre-<revision>`（及 `-wal`、`-shm`） | 迁移修改表结构之前做的副本。只保留最新三份。 | 守护进程 | 否 | 升级后的守护进程工作正常后可以。 |
| `master.key` | 解密已存密钥的 Fernet 主密钥，权限 `0600`。主密钥存放在操作系统钥匙串中时（服务 `coffer`，条目 `master-key`）不存在这个文件。 | 守护进程 | **从不。** 在桌面应用中备份，再通过**设置 › 安全 › 导入主密钥**装到另一台机器上。 | **不能。** 没有它，所有已存密钥都无法读取。 |
| `machine-id` | 随机 id，权限 `0600`，只在主机不提供硬件 id（macOS 的 `IOPlatformUUID`、Linux 的 machine-id）时使用。从不重写。 | 守护进程 | 否 | 不能：新 id 会让本机在已同步的保险库中分裂成两个身份。 |

### 派生数据 {#derived}

`derived/` 下的一切都能从其余数据重建，所以（在守护进程停止时）删除它总是安全的。**设置 → 数据** 可以帮你清掉这些缓存。

| 路径 | 用途 | 由谁重建 |
| --- | --- | --- |
| `derived/derived.db` | MCP 服务器健康状态、哪些技能副本投递到了哪些智能体、每项上游能力首次和最近一次被看到的时间。表结构版本不一致时会重建。 | 健康检查、技能投递、网关 |
| `derived/memory/<partition>/` | `global` 或某个仓库的派生记忆：`MEMORY.md`（索引）、`notes/`、`RETIRED.md`（退役了什么、为什么），以及隐藏的 `.raw/`（聚合读到的原文）。根目录的 `.source_state.json` 记录上一次聚合读了什么。 | 聚合与提炼（`RETIRED.md` 中的退役决定和你对笔记的编辑会丢失） |
| `derived/cache/agent/.transcript_summaries.json` | 对话记录读取器已经解析过的内容。 | 下一次读取，会比较慢 |
| `derived/resources/` | 派生的资源文件：记忆分区，以及 `skill/coffer-guide.json`。 | 守护进程启动时 |
| `derived/skills/coffer-guide/` | Coffer 自带的指南技能，由当前构建渲染。 | 守护进程启动时 |
| `derived/sync-conflicts/` | 停下的同步轮次中冲突文件的标注副本，供手工合并。 | 在编辑器里重新打开该文件 |

### 守护进程文件 {#daemon-files}

| 路径 | 用途 | 所有者 | 是否同步 | 能否安全删除 |
| --- | --- | --- | --- | --- |
| `daemon.json` | 正在运行的守护进程的运行时状态：`version`、`pid`、`port`、`token`、`started_at`、`binary_path`。权限 `0600`。每个客户端（CLI、shim、桌面应用、Web 界面开发服务器）都从这里读端口和 API 令牌。守护进程退出时删除。 | 守护进程 | 否 | 仅在没有守护进程运行时可以。过期的文件会被识别并忽略。 |
| `daemon.lock` | `flock` 锁文件，让“检测或启动”串行执行，两个客户端就不会启动两个守护进程。按设计在两次运行之间留在磁盘上。 | 守护进程、CLI、shim | 否 | 没有守护进程正在启动时可以。 |
| `daemon-config.json` | 打开数据库之前读取的设置：`port`、`proxy_port`、`machine_name`、`machine_id`（缓存）、`features`。权限 `0600`。见[配置](/zh/reference/configuration#daemon-config-json)。 | 守护进程、CLI | 否（有意只属于本机） | 可以：守护进程会回退到 38470 端口、主机名和默认值（每个实验功能都关闭）。 |
| `proxy.json` | 正在运行的[模型代理](/zh/architecture/model-proxy)的运行时状态：`port`、`pid`、`started_at`、`version` 和 `control_token`，后者是守护进程用来向代理推送状态、通知它排空的令牌。权限 `0600`。代理绑定好 socket 后写入；退出时仅当文件里记录的仍是自己的 pid 才删除。代理能活过守护进程重启，新的守护进程通过这个文件找到它。 | 模型代理 | 否 | 仅在没有代理运行时可以。 |
| `proxy-usage/<pid>-<start>-<seq>.jsonl`（打开期间为 `.jsonl.part`） | 模型代理的用量记录，每行一个 JSON 对象，只含元数据。代理从不打开数据库；守护进程会导入每个写完的文件。`COFFER_PROXY_SPOOL_DIR` 可以挪动这个目录。 | 模型代理、守护进程 | 否 | 已写完但尚未导入的文件会从用量报告中丢失。 |
| `upstream-pids/<server-uid>-<pid>.json` | 守护进程启动的每个上游 MCP 服务器进程一个文件，这样崩溃后下一个守护进程能回收孤儿进程。 | 守护进程 | 否 | 守护进程停止时可以。 |

见[守护进程与进程](/zh/architecture/daemon)和[运行守护进程](/zh/guides/daemon)。

### 二进制文件 {#binaries}

| 路径 | 用途 | 所有者 | 是否同步 | 能否安全删除 |
| --- | --- | --- | --- | --- |
| `bin/<version>/` | 每个已部署的 frozen 构建一个目录，里面有 `coffer`、`coffer-daemon` 和 `coffer-mcp-shim`，每个都带一个复制完成后才写入的 `.<name>.version` 标记文件。保留当前版本和上一个版本。 | 安装程序、守护进程（frozen 构建） | 否 | 旧版本目录可以删，但符号链接指向的那个不行。 |
| `bin/coffer`、`bin/coffer-daemon`、`bin/coffer-mcp-shim` | 指向当前版本目录的相对符号链接，升级时原子切换。智能体的 MCP 条目、登录服务和你的 `PATH` 都使用这些固定名称。 | 安装程序、守护进程 | 否 | 不能：智能体的 MCP 条目指向 `bin/coffer-mcp-shim`。 |

要手动撤销一次升级，把这些符号链接指回上一个版本目录即可。frozen 守护进程启动时会把同级二进制部署到这里；源码安装则使用 `pip` 放到 `PATH` 上的命令行脚本。见[分发与发布](/zh/architecture/distribution)。

### 日志 {#logs}

| 路径 | 用途 | 所有者 | 是否同步 | 能否安全删除 |
| --- | --- | --- | --- | --- |
| `logs/daemon.log`、`daemon.log.1`…`.3` | 守护进程日志，每行一个 JSON 对象，达到 10 MB 时轮转，保留三份备份。桌面应用和登录服务也把自己的记录写进同一个文件。显示在**活动**页面，可用 `coffer log daemon` 读取、用 `coffer path logs` 定位。 | 守护进程、桌面应用 | 否 | 轮转出来的文件可以删。守护进程运行时别动当前文件。 |
| `logs/proxy.log` | 模型代理的标准错误输出：只有元数据，从不包含请求体、提示词或密钥。 | 守护进程（监管者）、模型代理 | 否 | 可以。 |
| `logs/shim-<pid>-<epoch>.log` | 每个 MCP shim 进程一个文件，只在 shim 有东西要记录时才创建。7 天后清理。 | shim | 否 | 可以。 |
| `logs/upstream/<server>.log`、`.log.1` | 每个 stdio 上游 MCP 服务器的标准错误输出。达到 2 MB 时挪到一边；`.1` 副本 7 天后清理。 | 守护进程 | 否 | 可以。 |

`COFFER_LOG_DIR` 会把守护进程、代理、上游和 shim 的日志一起挪走。见[可观测性](/zh/architecture/observability)。

### 其他文件 {#other-files}

| 路径 | 用途 | 所有者 | 是否同步 | 能否安全删除 |
| --- | --- | --- | --- | --- |
| `vendor/` | 你放 SeaTalk WebSocket SDK（`seatalk_oapi_sdk`）的地方。Coffer 只读取它。 | 你 | 否 | 不用 SeaTalk 就可以。 |
| `eval-capture.jsonl` | 捕获的 `coffer__search_tools` 调用，仅在设置了 `COFFER_EVAL_CAPTURE` 时存在。 | 守护进程 | 否 | 可以。 |

## ~/.coffer 之外 {#outside-coffer}

| 路径 | 用途 | 所有者 | 能否安全删除 |
| --- | --- | --- | --- |
| `~/Library/LaunchAgents/dev.coffer.daemon.plist` | 登录时启动守护进程、崩溃后重启它的登录服务（macOS）。运行 `~/.coffer/bin/coffer-daemon`，日志写到 `~/.coffer/logs/daemon.log`。 | 守护进程（**设置 → 守护进程 → 开机自启动**） | 请改为关闭**开机自启动**。 |
| 你的 shell 配置文件 | `install.sh` 会把 `~/.coffer/bin` 追加到 `PATH`，除非设置了 `COFFER_NO_MODIFY_PATH=1`。 | 安装程序 | 手动删掉那一行。 |

## 智能体配置目录里的内容 {#inside-an-agent-s-config-directory}

Coffer 只会为你要求的事写入已注册智能体自己的配置目录：把它连接到 Coffer、投递技能、切换模型提供商，或在智能体页面上编辑配置文件。每次写入都是原子的，被编辑文件的上一版会保存为 `<file>.bak`、`<file>.bak.1` 和 `<file>.bak.2`。

配置目录默认是 Claude Code 的 `~/.claude` 和 Codex 的 `~/.codex`。如果智能体注册在别的目录，Coffer 为它启动的每个进程都会设置 `CLAUDE_CONFIG_DIR` 或 `CODEX_HOME`。

### Claude Code {#claude-code}

| 文件 | Coffer 写入什么 | 何时写入 |
| --- | --- | --- |
| `~/.claude.json`（非默认目录时在配置目录内） | `mcpServers.coffer`：`{"command": "~/.coffer/bin/coffer-mcp-shim", "args": ["--agent-uid", "<uid>"]}`，shim 路径为绝对路径。 | 把智能体连接到 Coffer 时。见[智能体](/zh/guides/agents#connect-an-agent-to-coffer)。 |
| `settings.json` | `apiKeyHelper` 设为 `<absolute path to coffer> proxy token --agent-uid <agent uid>`（例如 `/Users/you/.coffer/bin/coffer …`；只有找不到 CLI 时才用裸的 `coffer`），它会打印该智能体的本地代理令牌；`env.ANTHROPIC_BASE_URL` 设为模型代理的 `http://127.0.0.1:<proxy port>/anthropic`；把 `127.0.0.1,localhost` 追加到 `env.NO_PROXY`；以及模型相关的键（`model`、`env.ANTHROPIC_DEFAULT_<TIER>_MODEL`、`modelPicker`）。从不写入提供商的 API 密钥。 | 把智能体切换到某个模型提供商时。见[模型提供商](/zh/guides/providers)。 |
| `settings.json` | 两个 Hook 条目，命令以 `: coffer-memory;` 开头，并以完整路径运行 `coffer` CLI：`coffer memory hook --agent-uid <uid> --cwd "$PWD"`。分别是 `hooks.SessionStart`（matcher `startup\|resume\|clear\|compact`，超时 10 秒）和 `hooks.UserPromptSubmit`（超时 5 秒）。 | 把智能体连接到 Coffer。见[记忆](/zh/guides/memory#install-the-hook)。 |
| `skills/<name>` | 指向 `~/.coffer/vault/skills/<name>` 的符号链接（不支持符号链接时为副本）。 | 向智能体投递技能时。见[技能](/zh/guides/skills)。 |

### Codex {#codex}

| 文件 | Coffer 写入什么 | 何时写入 |
| --- | --- | --- |
| `config.toml` | `[mcp_servers.coffer]`，`command` 设为 shim，`args = ["--agent-uid", "<uid>"]`。 | 把智能体连接到 Coffer 时。 |
| `config.toml` | `model_provider = "coffer"`；一个 `[model_providers.coffer]` 表，其中 `base_url` 设为模型代理的 `http://127.0.0.1:<proxy port>/openai/v1`，`supports_websockets = false`，`requires_openai_auth = false`，以及一条 `auth` 命令（以绝对路径调用 `coffer`，`args = ["proxy", "token", "--agent-uid", "<agent uid>"]`）；还有指向下面模型目录的 `model_catalog_json`。从不写入提供商的 API 密钥。 | 把智能体切换到某个模型提供商时。 |
| `coffer-model-catalog.json` | 提供商精选的模型列表，让 Codex 自己的模型选择器能显示它。关闭提供商时删除。 | 把智能体切换到某个模型提供商时。 |
| `hooks.json` | 与 Claude Code 相同的两个 Hook 条目，事件、matcher 和超时都一样，都运行 `coffer memory hook`。Codex 在 `config.toml` 的 `[hooks.state]` 中记录对每个条目的批准，Coffer 只读不写。 | 把智能体连接到 Coffer。 |
| `skills/<name>` | 指向 `~/.coffer/vault/skills/<name>` 的符号链接。 | 向智能体投递技能时。 |

Coffer 通过 `coffer` 服务器键、`: coffer-memory` 标记，以及运行 `coffer` CLI（裸名或任意路径）加 `proxy token` 的 `apiKeyHelper` 来识别自己的条目，并且只删除这些。其他条目——你自己的 MCP 服务器、其他工具的 Hook、你的 `env`——保持原样。Coffer 会读取智能体的原生记忆文件，但从不写入。

::: tip 清理智能体
卸载 Coffer 之前，先断开每个智能体与 Coffer 的连接，并在每个智能体的页面上移除提供商投影，然后再删除 `~/.coffer`。先删 `~/.coffer` 的话，智能体会指向一个已经不存在的 shim。
:::

## 相关页面 {#related}

- [配置](/zh/reference/configuration)
- [持久化](/zh/architecture/persistence)
- [安全模型](/zh/architecture/security)
- [保险库同步](/zh/guides/vault-sync)
- [手动编辑保险库](/zh/guides/vault-files)
- [故障排查](/zh/guides/troubleshooting)
