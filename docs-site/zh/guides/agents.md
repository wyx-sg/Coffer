---
title: 智能体
description: 把 Claude Code 和 Codex 注册到 Coffer、接入 Coffer，并管理它们的配置文件、MCP 条目、插件、Hook、模型、记忆和对话记录。
---

# 智能体 {#agents}

智能体是装在你机器上、由 Coffer 向其投递资源的编程智能体：Claude Code 或 Codex。本页讲如何注册智能体、如何把 Coffer 的 MCP 条目装进去，以及 Coffer 让你在智能体自己的文件里能看到和改动的一切。

## 智能体的用途 {#what-agents-are-for}

Coffer 共享的一切——MCP 服务器、技能、知识、记忆、模型提供商——最终都落到某个智能体上。注册智能体就是告诉 Coffer 这个智能体把配置放在哪里，这样 Coffer 就能：

- 往里面写入一个 `coffer` MCP 条目，让智能体通过[同一个网关](/zh/guides/mcp-servers)访问所有上游 MCP 服务器；
- 把[技能](/zh/guides/skills)链接进它的 `skills/` 文件夹；
- 把[模型提供商](/zh/guides/providers)投射到它的原生配置里；
- 在一个地方展示它的配置文件、MCP 条目、插件、原生记忆和对话记录。

Coffer 支持两种智能体类型：

| 类型 | 产品 | 默认配置目录 | Coffer 查找的程序 |
| --- | --- | --- | --- |
| `claude_code` | Claude Code（CLI 和 IDE/桌面形态） | `~/.claude` | `claude` |
| `codex` | OpenAI Codex（CLI 和 IDE 形态） | `~/.codex` | `codex` |

同一产品的 CLI 和 IDE 形态读的是同一个配置目录，所以注册一个智能体就能覆盖两者。Claude Desktop 聊天应用有自己的配置，不属于受支持的智能体。

### 每种类型一个智能体 {#one-agent-per-type}

一台机器上每种类型最多注册一个智能体，智能体的名字**就是**它的类型：`claude-code` 或 `codex`。你不用起名，智能体也没有标题或描述。凡是 Coffer 问你指哪个智能体的地方——`coffer agent …`、`coffer path agent`、`coffer scan --agent`、技能或 MCP 服务器的 `--agents` 范围，以及所有 `/api/v1/agents/{uid}/…` 路由——都可以填类型（`claude-code`；`claude_code` 也能识别）或智能体的 uid。

除了类型，智能体唯一的设置就是**配置目录**，外加[模型绑定](#models)。注册时默认使用该类型的标准目录（`~/.claude`、`~/.codex`），除非你另行指定。把 Coffer 指向别的目录，是把这唯一的智能体挪过去，绝不会新增第二个。注册一个已注册过的类型会被拒绝，返回 `409 AGENT_TYPE_REGISTERED`。

::: details 从允许同类型多个智能体的旧版本升级
早期版本允许你用自选的名字注册同一类型的多个智能体。升级时，一条数据库迁移会让每种类型只保留一个智能体，其余的删掉。保留的优先顺序是：已接入 Coffer 的那个（它的 Coffer MCP 条目带着它的 uid），然后是启用中的，然后是最近使用的，最后是位于标准目录的。所有引用了被删智能体的生效范围列表和消息渠道默认智能体，都会改指向保留下来的那个；保留的智能体改名为它的类型；每个被删的智能体会以 `migration.0109.agent_dropped` 记在守护进程日志里。被删智能体的配置目录里仍留着 Coffer 写过的东西，比如技能链接或 `coffer` MCP 条目；如果你不再用那个目录，请手动清理。智能体上的标题和描述会被清空。
:::

::: info 智能体自己的文件才是真相来源
Coffer 从不把智能体的配置复制进自己的存储。配置文件、MCP 条目、插件、原生记忆和对话记录，每次查看时都从磁盘读取。智能体记录本身只保存类型、配置目录和模型绑定。
:::

## 注册智能体 {#register-an-agent}

### 从检测到的智能体注册 {#from-detected-agents}

Coffer 靠两个信号检测智能体：`PATH` 上的程序——用的是你登录 shell 给出的 `PATH`，所以即使守护进程是从 Dock 启动的，用 Homebrew 或 Node 版本管理器装的智能体也能被找到——以及它的配置目录。顺带会读取程序版本（`claude --version`、`codex --version`）。Coffer 从不自行注册任何东西，守护进程启动时也不会自动注册智能体。

Coffer 会报告每一种受支持的类型（无论是否已注册），状态是以下之一：

| 状态 | 程序 | 配置目录 | 你能做什么 |
| --- | --- | --- | --- |
| **已安装** | 找到 | 存在 | 添加。 |
| **已安装，未运行过** | 找到 | 尚未创建 | 添加。在标准目录注册时会创建该目录，里面只放 Coffer 需要的东西（`skills` 文件夹）。 |
| **未安装** | 缺失 | 存在 | 没有可添加的：这个目录是以前安装留下的。重装智能体，或者忽略它。 |
| **缺失** | 缺失 | 不存在 | 这台机器上什么都没有。该类型仍会列出，所以每种类型总有一行。 |

对每种类型，Coffer 会查看它的标准目录；如果守护进程的环境设置了该类型自己的变量（Claude Code 是 `CLAUDE_CONFIG_DIR`，Codex 是 `CODEX_HOME`），还会查看变量指向的目录。第二个目录永远不会成为第二个智能体：标准目录存在时，它作为这唯一智能体的**使用其他配置目录**选项提供；只有它存在时，它就是「添加」注册的目录。Coffer 不会搜索磁盘的其他位置；要使用别的目录，见[使用其他配置目录](#use-a-different-config-directory)。已注册的类型不会再次提供。

**Web 界面：** **智能体**页面始终恰好有两行，先 Claude Code 后 Codex，不管各自是否安装或添加。检测是自动的——打开页面时、窗口重新获得焦点时，以及每隔几分钟——所以没有「检测」按钮，也没有「添加智能体」对话框。每一行显示一种状态，并提供它对应的那一个操作：

| 行显示 | 含义 | 操作 |
| --- | --- | --- |
| **已检测到，未添加** | 已安装，配置目录存在 | **添加** |
| **已安装，未运行过** | 已安装，目录尚未创建（标记为*未创建*） | **添加**——预览会写明它将创建的目录 |
| **配置残留** | 有目录，但 `PATH` 上没有程序 | **复制提示词**（重装交接）；行下方的提示提供同样的提示词和**显示文件夹** |
| **未安装** | 两者都没有 | **复制提示词**（安装交接） |
| **已接入** / **未接入** / **需要修复** | 已添加；它与 Coffer 的连接完整、不存在或不完整 | **断开连接** / **连接** / **修复** |
| **已停用** | 已添加但被关闭 | **启用** |

Coffer 不负责安装智能体，而安装又依赖具体机器，所以找不到程序的行会把活交给一个智能体，而不是给出安装命令。**复制提示词**复制的是守护进程写的一段提示词：在这台机器上安装（或重装）这个智能体，保留它现有的配置目录，确保它的程序能在 Coffer 查找的 `PATH` 上被找到（提示词里列出了这个 `PATH`），并用 `claude --version` 或 `codex --version` 确认，然后回来点**再检查一次**——登录留给你自己。把它粘贴给任意助手即可。当有另一个受管智能体可用时，该行的 ⋯ 菜单还提供**交给智能体**，它会新开一个对话，把提示词放进输入框，但不发送。智能体页面的空状态和概览 tab 的问题状态里也提供同样的提示词。你仍然可以按厂商文档自己安装智能体；程序一出现在 `PATH` 上，这一行会自动更新。

**添加**会在标准目录注册智能体并接入它。它会先打开预览——列出将写入的每个文件和新增的条目——在你确认之前什么都不写。首次运行时，如果两个智能体都已安装且都没添加，**全部添加**会在一次确认里预览并添加两者。已注册的行还会显示它的模型，以及有多少技能、MCP 服务器和插件对它生效，并可打开智能体页面。

**CLI：**

```sh
coffer scan
# lists the types seen here that are not registered (kind "agent"), one row per type,
# with its state and version and — when it can be added — the command that registers it

coffer agent add codex            # register the codex agent at ~/.codex
# registered: agent codex
```

`coffer scan` 打印的命令是 `coffer agent add <type>`，只有当找到的目录不是该类型的标准目录时才会加上 `--config-dir`。

在该类型的程序找不到时，`coffer agent prompt <type>` 会打印智能体页面复制的那段安装或重装提示词（`--json` 把它放在 `handoff` 下）；程序找得到时，它会说没有需要交接的内容，并以退出码 5 结束。对于程序已经不在的已注册智能体，`coffer agent show <name>` 会提示你用它。

### 使用其他配置目录 {#use-a-different-config-directory}

Claude Code 用 `CLAUDE_CONFIG_DIR` 启动时会读取另一个目录，Codex 则是 `CODEX_HOME`。如果你就是这样运行智能体的，把这个目录告诉 Coffer。注册时：

```sh
coffer agent add claude-code --config-dir ~/work/.claude
```

对已注册的智能体，把它挪过去：

```sh
coffer agent edit claude-code --config-dir ~/work/.claude
```

**Web 界面：** 在该行（或智能体页面）的 **⋯** 菜单里选**使用其他配置目录…**。用系统原生的文件夹对话框选择文件夹（只有宿主没有原生对话框时才用应用内浏览器）；对话框会列出该类型的常见文件哪些存在。对尚未添加的智能体，这一步会直接在该目录注册它。

接受目录之前，Coffer 会先创建 `<config_dir>/skills`，然后检查该目录存在、是目录、可写，且不是系统位置（`/etc`、`/usr`、`/var/folders/` 之外的 `/var`、`/System`、`C:\Windows`、`C:\Program Files` 等）。被拒绝的注册不会留下任何东西。非标准目录必须事先存在；只有「已安装、未运行过」的智能体的标准目录会替你创建。挪动智能体会把它的技能重新投递到新目录。

当 Coffer 自己启动一个注册在非标准目录上的智能体时——一次[对话](/zh/guides/chat)或[消息渠道](/zh/guides/channels)轮次、一次模型列表探测、一次插件卸载——它会把 `CLAUDE_CONFIG_DIR` 或 `CODEX_HOME` 设为那个目录，让智能体读到 Coffer 放在那里的技能、MCP 条目和设置。

### 编辑、停用和移除 {#edit-disable-and-remove}

```sh
coffer agent edit claude-code --config-dir ~/work2/.claude
coffer agent disable claude-code
coffer agent rm claude-code
```

在 Web 界面里，智能体行和智能体页面上的 **⋯** 菜单包含**使用其他配置目录…**、**显示配置目录**、**复制 uid**、**断开连接**、**停用** / **启用**和**从 Coffer 中移除**。

- **编辑**修改配置目录或[模型绑定](#models)。名字就是类型，不能改。所有引用智能体的地方——生效范围列表、消息渠道的默认智能体、已安装的 MCP 条目——保存的都是智能体不可变的 `uid`。
- **停用**让 Coffer 不再往智能体里写、也不再从中读：已投递的技能会被移除，它的原生记忆不再被聚合，它的配置也不再进入模型目录。重新启用会恢复技能授予的内容。在 Web 界面里是 ⋯ 菜单中的**停用**；已停用智能体的页面提供**启用**。
- **移除**删除注册，并移除 Coffer 投递的技能。智能体本身仍保持安装状态，只要它的程序或配置目录还在，`coffer scan` 就会再次提供它。

::: warning 移除智能体会留下 Coffer 的条目
在命令行和 REST API 上，移除智能体并不会断开它。`coffer` MCP 条目会继续上报一个没有任何已注册智能体对应的 `uid`，于是它的会话只能看到对所有智能体生效的服务器。请在移除前运行 `coffer agent disconnect <type>`，或在重新注册后再接入一次。Web 界面里的**从 Coffer 中移除**会先断开，再移除。
:::

## 把智能体接入 Coffer {#connect-an-agent-to-coffer}

接入会一次性把 Coffer 需要的一切写进智能体自己的配置：

| 部分 | 作用 | 何时 |
| --- | --- | --- |
| 网关 MCP 条目 | 一个指向 `coffer-mcp-shim` 的 `coffer` stdio MCP 服务器条目。智能体通过它访问所有启用的上游服务器、Coffer 自己的工具，以及投递给它的知识。 | 总是 |
| 记忆投递 Hook | 四个 Hook 条目——会话开始、每次提问、每条 shell 命令执行前后——Coffer 通过它们把记忆交给智能体。见[记忆](/zh/guides/memory#install-the-hook)。 | 总是 |

断开连接会移除这两部分，而且只移除 Coffer 自己的条目；这些文件里的其他内容保持原样。

**Web 界面：** 当智能体未接入或连接不完整（显示**需要修复**）时，智能体页面的头部提供**连接到 Coffer**；概览 tab 的**连接**卡片展示每个部分——MCP 条目和记忆 Hook，各自所在的文件，以及是否为最新。在**智能体**列表里，**Coffer** 列显示**已接入**、**未接入**或**需要修复**，行上提供**连接**或**修复**。每次连接、修复和断开都会先打开同一个**审阅改动**预览：修复只列出缺失的部分，断开只列出它要删的行。如果写入中途失败，预览会指出哪一项失败，保留已经生效的改动，并只对失败的那项提供重试。

**CLI：**

```sh
coffer agent connect claude-code
# connected agent claude-code to Coffer
#   gateway MCP entry: installed (/Users/you/.coffer/bin/coffer-mcp-shim)
#   memory delivery hook: installed (: coffer-memory; coffer memory hook --agent-uid …)

coffer agent show claude-code                # the connection, beside the agent's record (--json for the raw answer)
# ...
# coffer_connection: connected
#   gateway MCP entry: installed (/Users/you/.coffer/bin/coffer-mcp-shim)

coffer agent disconnect claude-code
```

接入后重启智能体（或重新加载它的 MCP 服务器），让它启动 shim。

只有网关条目而没有 Hook 的智能体会一直显示**需要修复**，直到你再接入一次。

### 各写到哪里 {#what-gets-written-where}

| 智能体 | 文件 | 条目 |
| --- | --- | --- |
| Claude Code，默认目录 | `~/.claude.json` | `mcpServers.coffer` |
| Claude Code，自定义目录 | `<config_dir>/.claude.json` | `mcpServers.coffer` |
| Codex | `<config_dir>/config.toml` | `[mcp_servers.coffer]` |

Claude Code 的条目长这样：

```json
{
  "mcpServers": {
    "coffer": {
      "command": "/Users/you/.coffer/bin/coffer-mcp-shim",
      "args": ["--agent-uid", "9a006a32d0bf5787955c43d54e4b44e9"]
    }
  }
}
```

Codex 的：

```toml
[mcp_servers.coffer]
command = "/Users/you/.coffer/bin/coffer-mcp-shim"
args = ["--agent-uid", "9a006a32d0bf5787955c43d54e4b44e9"]
```

记忆 Hook 的四个条目见[文件系统](/zh/reference/filesystem)。

接入是幂等的：再接入一次会原地重写每个条目，绝不会加第二个。什么都没装时断开连接也会成功，且不做任何改动。每次写入都会备份，并按部分记入审计（`agent_mcp_installed` / `agent_mcp_uninstalled`、`memory_delivery_installed` / `memory_delivery_removed`）。连接状态每次都从文件读取，Coffer 不存储它。

### 为什么 shim 路径是绝对路径 {#why-the-shim-path-is-absolute}

守护进程可能从桌面应用、登录服务或虚拟环境里运行，它们都不继承你 shell 的 `PATH`，智能体也可能不继承。所以 Coffer 写的是完整路径。它按以下顺序解析 shim：

1. `COFFER_MCP_SHIM_PATH`，如果设置了且文件存在；
2. 守护进程 `PATH` 上的 `coffer-mcp-shim`；
3. 运行守护进程的 Python 解释器的 scripts 目录（`pip` 和 `uv` 放置控制台脚本的地方）；
4. 与正在运行的可执行文件打包在一起的二进制。

当结果是安装版时，Coffer 写入稳定的 `~/.coffer/bin/coffer-mcp-shim` 链接，而不是带版本号的目录，这样条目在升级后依然有效。如果找不到任何 shim，安装会以 `SHIM_NOT_FOUND` 失败，指出缺失的二进制，且不写入任何东西。这个拒绝会附带一段交接提示词：列出 Coffer 查找过的每个位置，并请一个智能体找到或重装 shim，使其能在 `~/.coffer/bin/coffer-mcp-shim` 解析到。接入的审阅界面会在**重试**旁提供**复制提示词**，`coffer agent connect` 则在错误下方打印它。

### 智能体 uid 与生效范围 {#the-agent-uid-and-reach}

`--agent-uid` 参数是网关判断一个会话属于哪个智能体的依据。shim 在 MCP `initialize` 握手里传递它，网关在整个会话里用它决定该智能体能看到哪些服务器。[生效范围](/zh/architecture/resource-framework)只列了某些智能体的服务器，对其他所有会话都是隐藏的。

条目携带 uid，是因为 Coffer 只把它写进这个文件一次、之后不再回头改，而 uid 正是所有其他记录保存的身份。手写的、不带 `--agent-uid` 的 shim 条目仍然能用，但它的会话身份不明，只能看到对所有智能体生效的服务器。详见[连接客户端](/zh/guides/connect-a-client)。

## Coffer 读什么、写什么 {#what-coffer-reads-and-what-it-writes}

Coffer 只通过一小组有文档说明的面接触智能体的文件：

| 面 | Coffer 读 | Coffer 写 |
| --- | --- | --- |
| 白名单内的配置文件 | 是 | 是，当你在编辑器或 CLI 中保存时 |
| 智能体配置里的 MCP 条目 | 是 | 安装/卸载 `coffer`、移除、纳入托管 |
| 插件 | 清单和启用状态 | 启用开关；按该类型自己的方式卸载 |
| 模型提供商 key | 是（每轮调和都会检查） | 当你切换[提供商](/zh/guides/providers)时，以及把值已过时的投射重新对齐时 |
| 原生记忆库 | 是 | 从不 |
| 对话记录 | 是 | 从不 |
| Codex `auth.json` | 从不 | 从不 |

每次写入：

- 通过白名单**键**定位文件，从不使用你提供的路径——未知的键返回 404，且不访问任何文件；
- 写入前校验 `json` 和 `toml` 内容，格式错误的输入会被拒绝，文件不动；
- 原子替换文件（临时文件加重命名）；
- 把之前的内容保存为 `<file>.bak`，更早的副本轮转为 `.bak.1` 和 `.bak.2`；
- 用 `tomlkit` 编辑 Codex 的 `config.toml`，你的注释、键顺序以及 Codex 自己的内部表（`[marketplaces.*]`、`[hooks.state.*]`、`[projects.*]`）逐字节保留；
- 记录一条审计条目。

当某个配置文件无法解析时，MCP 和插件 tab 会显示解析错误，并对该文件切换为只读；智能体页面的其他部分照常可用。

## 编辑配置文件 {#edit-config-files}

每种类型有一份固定白名单：

| 类型 | 键 | 文件 |
| --- | --- | --- |
| `claude_code` | `settings` | `<config_dir>/settings.json` |
| | `settings_local` | `<config_dir>/settings.local.json` |
| | `global` | `~/.claude.json`（默认目录）或 `<config_dir>/.claude.json`（自定义目录） |
| | `instructions` | `<config_dir>/CLAUDE.md` |
| | `subagents` | `<config_dir>/agents/`——一个目录，每个子智能体一个 Markdown 文件 |
| `codex` | `config` | `<config_dir>/config.toml` |
| | `instructions` | `<config_dir>/AGENTS.md` |
| | `hooks` | `<config_dir>/hooks.json` |

**Web 界面：** 打开智能体，选择**配置文件**。选中一个文件即可查看；点**编辑**后查看器变为可编辑。内容旁边可以用外部编辑器打开文件，或在文件管理器中显示它。有未保存的草稿时，切换文件、tab 或页面前会先询问，使用的是所有编辑器共用的**不保存就离开？**对话框。

**CLI：**

```sh
coffer path agent claude-code config                        # where each allowlisted file is
coffer agent config edit claude-code instructions          # opens $EDITOR
coffer agent config edit codex config --from-file ./config.toml

# Directory entries (Claude Code subagents)
coffer agent config edit claude-code subagents/reviewer.md --from-file ./reviewer.md
coffer agent config rm claude-code subagents/reviewer.md
```

要读文件，用你自己的工具打开 `coffer path agent <type> config` 打印的路径。读取不存在的文件会返回空内容，不会创建它。目录条目里的文件必须留在该目录内，并以 `.md` 结尾。

::: tip 并发编辑会被拒绝，而不是覆盖
每次读取都会返回内容指纹。编辑器和 `coffer agent config edit` 保存时会把它带回来；如果文件在此期间在磁盘上变了——智能体自己改写了它，或者你在别处保存过——写入会以 `CONFIG_FILE_STALE` 被拒绝（CLI 退出码 5），文件保持原样。重新打开后再保存即可。
:::

## 管理智能体自己的 MCP 条目 {#manage-the-agent-s-own-mcp-entries}

智能体经常在自己的文件里直接配置 MCP 服务器。**MCP 服务器** tab 把两者列在一张表里：Coffer 的服务器（通过网关条目提供）和智能体自己的条目，每行都标出归属方和所在文件。归属筛选——**全部**、**Coffer 的**、**智能体自己的**——用来缩小范围，并保存在地址里（`?owner=`）。自有条目提供**纳入托管**；与已注册 MCP 服务器重复的条目提供**删除重复项**，它会把条目从智能体文件中删掉，因为网关已经在提供它。

| 类型 | 直接条目读取自 |
| --- | --- |
| Claude Code | `.claude.json`（`global` 文件）和 `settings.json` 里的 `mcpServers` |
| Codex | `config.toml` 里的 `[mcp_servers.*]`（会显示 `enabled` 标志，但从不写入） |

点击直接服务器的名字可打开它的详情页。页面以只读方式展示智能体文件里关于该服务器的全部内容：传输方式、命令及每个参数（或 URL）、工作目录、格式支持时的 `enabled` 标志、环境变量和 HTTP 头的名字、条目带的其他键，以及所在的配置文件，路径旁有**在编辑器中打开**和**显示**。密钥值永远不离开守护进程：环境变量和请求头的值只显示为*已设置*或*密钥 · 已隐藏*，名字看起来像密钥的其他键（规则见下）显示为*已隐藏*。Coffer 不会为了展示这个页面而启动直接服务器，所以页面不列工具。页面上的两个操作与行上的相同；用标题栏的后退箭头回到智能体的 **MCP 服务器** tab。

对直接条目你可以做两件事：

- 从源文件中**移除**它（原子写入、保留 `.bak`，审计为 `agent_mcp_entry_removed`）。
- **纳入 Coffer 托管**：Coffer 把条目注册为一个 `mcp_server` 资源，确认能读回，然后才删除直接条目。任何失败都会回滚新资源，并让智能体的文件保持逐字节不变。之后该服务器通过网关提供给每个智能体。从详情页纳入托管会打开新受管服务器的页面。

```sh
coffer scan --agent claude-code                       # direct MCP entries have kind "mcp"
coffer scan --ref claude-code:github --source global  # one entry in full, secrets withheld
coffer discard mcp claude-code:old-server --source settings
coffer adopt mcp claude-code:github --secret GITHUB_TOKEN=github/token
```

ref 的格式是 `<agent>:<entry>`，与 scan 打印的一致。

当条目的环境变量或请求头在一个看起来像密钥的键下（包含 `TOKEN`、`SECRET`、`PASSWORD`、`PASSWD`、`API_KEY`、`APIKEY`、`CREDENTIAL` 或 `AUTHORIZATION`）带有非空值时，纳入托管要求为每一个都提供 `--secret KEY=REF` 映射。Coffer 把当前值存进它的[加密密钥存储](/zh/guides/secret-store)中你指定的 ref 下，新资源的配置里只带 ref。名字冲突会被拒绝，并给出建议的替代名（用 `--name` 自选）。对同时出现在两个文件里的 Claude Code 名字，用 `--source` 传入文件的键（`global` 或 `settings`）。`coffer` 条目本身永远不能用这种方式移除或纳入托管。

## 插件 {#plugins}

**插件** tab 列出已安装的插件（都是智能体自己的；归属筛选与其他列表 tab 相同），包括版本、市场、启用开关和**卸载**。缓存目录已不存在的插件标记为**缓存缺失**；Coffer 不会尝试修复。

点击插件名字可打开它的详情页。页面展示插件的 `<name>@<marketplace>` id、版本、作者、描述和主页、来源市场，以及安装目录，附带**在编辑器中打开**和**显示**按钮。下方列出插件提供的一切，从其包的默认位置读取：

| 内容 | 读取自 |
| --- | --- |
| 技能及其描述 | `skills/<name>/SKILL.md` |
| 命令及其描述 | `commands/*.md` |
| 子智能体及其描述 | `agents/*.md` |
| Hook 事件 | `hooks/hooks.json` |
| MCP 服务器 | `.mcp.json` |

页面头部有与 tab 上相同的启用开关和**卸载**。卸载之后页面回到智能体的插件 tab；标题栏的后退箭头也一样。这个页面只读取插件文件，不改动任何东西。

```sh
coffer agent plugin list claude-code
coffer agent plugin show claude-code formatter@acme
coffer agent plugin disable claude-code formatter@acme
coffer agent plugin enable claude-code formatter@acme
coffer agent plugin rm codex formatter@acme
```

| | Claude Code | Codex |
| --- | --- | --- |
| 清单读取自 | `plugins/installed_plugins.json`、`known_marketplaces.json` | `config.toml` 里的 `[plugins."…"]` 和 `[marketplaces.*]` |
| 启用/停用写入 | 只写 `settings.json` 里的 `enabledPlugins` | 只写插件自己的 `enabled` 字段 |
| 卸载 | 运行 `claude plugin uninstall <id>` | 从 `config.toml` 删除条目，并删除 `plugins/cache/<marketplace>/<plugin>/` |

Coffer 从不写 Claude Code 自己的清单文件。当 `claude` CLI 不在 `PATH` 上时，卸载不可用（`PLUGIN_UNINSTALL_UNSUPPORTED`），Web 界面会隐藏这个操作。安装插件和管理市场仍由智能体自己的工具负责。

## Hook {#hooks}

**Hooks** tab 在一张表里列出智能体将运行的每个 Hook（归属筛选同上），直接从智能体的文件读取：每个 Hook 的 matcher、命令，以及它来自哪里——智能体自己的某个设置文件，或某个插件（按名字）。只包含已开启的插件，因为停用插件的 Hook 不会运行。项目自己设置里的 Hook 不显示，因为 Coffer 不知道你在哪些仓库里使用这个智能体。

| | Claude Code | Codex |
| --- | --- | --- |
| 智能体自己的文件 | `settings.json`、`settings.local.json` | `hooks.json` |
| 插件 | 每个已启用插件的 `hooks/hooks.json` | 每个已启用插件的 `hooks/hooks.json`（如果有） |
| Coffer 自己的 Hook | `settings.json` 里的 `SessionStart`、`UserPromptSubmit`、`PreToolUse` 和 `PostToolUse` | `hooks.json` 里同样的四个事件 |

Coffer 自己的 Hook——[记忆投递 Hook](/zh/guides/memory#install-the-hook)——在它的四个条目上各有标记，并作为一个 Hook 上报。在 tab 上它是一行：事件列显示**记忆钩子 · 4 个事件**，并为它所在的每个事件显示一个标签，表格上方的汇总也只计一次。它的状态说明它的情况：

- **最新**——恰好装在四个事件上，每个都恰好是当前版本 Coffer 写入的命令。
- **已过期**——Coffer 的 Hook 在，但命令与 Coffer 现在写的不同，或所在事件集合不同。守护进程会在下一轮调和时重写它；**修复**会立即重写。
- **缺失**——没有 Coffer 的 Hook。**修复**会重新把智能体接入 Coffer，从而装上它。

对 Codex，它还会说明 Codex 是否会运行这个 Hook。Codex 会跳过你没批准的条目，而 Coffer 的 Hook 只有四个条目都被信任才算受信任，所以 **Needs approval in Codex**（或 Coffer 更新改了命令之后的 **Needs re-approval in Codex**）意味着至少有一个条目已安装但不会运行。打开 Codex，运行 `/hooks`，信任 Coffer 的四个条目。Coffer 不会替你批准。

它还会根据[审计日志](/zh/guides/activity)显示 Hook 最近一次触发的时间。一个你每天都在用的智能体显示「从未触发」，就说明这个智能体没有在运行该 Hook。

tab 上其余内容都是只读的：Coffer 从不编辑其他工具的 Hook。每行的**打开文件**会在编辑器中打开声明它的文件。

```sh
coffer agent hooks claude-code
# * SessionStart [startup|resume|clear|compact]  (user)  : coffer-memory; coffer memory hook …
# * UserPromptSubmit  (user)  : coffer-memory; coffer memory hook …
# * PreToolUse [Bash]  (user)  : coffer-memory; coffer memory hook …
#   PreToolUse [Bash]  (user)  ./lint.sh
# * PostToolUse [Bash]  (user)  : coffer-memory; coffer memory hook …
#   SessionStart  (plugin formatter@acme)  ./plug.sh
# coffer hook: current on PostToolUse,PreToolUse,SessionStart,UserPromptSubmit, last fired 2026-09-29T08:12:03Z

coffer agent hooks claude-code --json   # the full answer, with each hook's file
```

## 模型 {#models}

模型目录回答的是「这个智能体可以用哪些模型」。Coffer 每次都从已安装的智能体读回它，所以新发布的模型不需要 Coffer 发版就会出现：

- **Claude Code：** 内嵌在 `claude` 二进制里的模型别名（例如 `opus`、`sonnet`、`haiku`），加上 `.claude.json` 里的 `additionalModelOptionsCache`。推理强度档位来自已安装的 Claude Agent SDK；不报告默认档位，因为运行时没有公布。
- **Codex：** Codex app server 的 `model/list` RPC（以指向智能体目录的 `CODEX_HOME` 运行），加上 `config.toml` 里提到的模型。每个模型带有自己的推理强度档位和默认值。

每个来源独立失败：未登录的 Codex 或变了布局的二进制，只会让那个来源的模型缺失。

```sh
coffer agent models claude_code
# opus  Opus 5.5  efforts: low, medium, high, xhigh, max
# sonnet  Sonnet 5  efforts: low, medium, high, xhigh, max
```

`coffer agent models` 接受智能体的类型。当智能体所在的[模型提供商](/zh/guides/providers)整理了模型列表时，选择器会改为提供那份列表。

智能体记录保存着提供商投射写入智能体配置的模型绑定：

```sh
coffer agent edit claude-code --model sonnet --effort high --tier haiku=haiku
coffer agent edit claude-code --clear-tiers
coffer agent edit codex --model gpt-5.5
```

改动会在下次切换该智能体的提供商时写到磁盘上。

## Web 界面中的模型、原生记忆和会话 {#model-native-memory-and-sessions-in-the-web-ui}

智能体页面以智能体类型寻址（`/agents/claude_code`、`/agents/codex`），有九个 tab，各有自己的地址：**总览**（`/agents/<type>`）、**模型**、**技能**、**MCP 服务器**、**插件**、**Hooks**、**配置文件**、**记忆**和**会话**（`/agents/<type>/model`、`…/skills`、`…/mcp-servers`、`…/plugins`、`…/hooks`、`…/config`、`…/memory`、`…/sessions`）。总览展示 Coffer 连接、每种已安装资源类型的一行汇总（点开进入对应 tab）、模型、详情——类型、配置目录、uid、注册时间——以及最近的会话；智能体的名字就是类型，所以没有名字或标题可编辑。

**模型** tab 是切换智能体提供商的唯一位置：内置登录或某个兼容连接、模型、该模型报告的推理强度档位，以及——Claude Code 使用连接时——每个档位的模型（Opus、Sonnet、Haiku，连接列出 Fable 时还有 Fable），并预填建议值。连接必须先通过**测试连接**；审阅面板会在**确认切换**之前列出 Coffer 将写入的内容。

### 原生记忆和会话 {#native-memory-and-sessions}

**记忆** tab 以只读方式列出智能体自己的记忆库：

- **Claude Code：** 每个项目一个库，位于 `<config_dir>/projects/<slug>/memory/`，标注真实的项目目录。
- **Codex：** 全局的 `<config_dir>/memories/MEMORY.md`，按它把任务组路由到的项目拆成每项目一行。

打开一行会显示该库的文件和只读预览。记忆投递 Hook 属于智能体的 [Coffer 连接](#connect-an-agent-to-coffer)，不在这个 tab 里。

**会话** tab 列出智能体自己的 CLI 会话——它的本地对话记录（Claude Code 是 `<config_dir>/projects/**/*.jsonl`，Codex 是 `<config_dir>/sessions/**/*.jsonl`），带标题、项目、消息数和活动时间，可搜索、可排序。选中一个会在列表旁以对话形式打开，附带你提问的**目录**；harness 自己注入的块折叠在**运行环境上下文**下。

```sh
coffer path agent claude-code memory                   # the native memory stores
coffer path agent claude-code transcripts              # the transcript folders
coffer agent transcript claude-code -q "release" --sort message_count
coffer agent transcript claude-code <session_id> --limit 50
```

原生记忆库是普通文件；用你自己的工具读取 `coffer path` 打印的路径即可。

对话记录文本在展示前会清除密钥，过长的轮次会被截断并标记，会话按轮次窗口分段读取。Coffer 从不写入、存储或向任何地方发送对话记录或原生记忆。

## 智能体上的技能 {#skills-on-an-agent}

**技能** tab 在一张带归属筛选的表里，列出 Coffer 投递给该智能体的技能，以及智能体自有、Coffer 不管理的技能文件夹。自有文件夹会打开只读预览，并提供**纳入托管**进 Coffer 的技能库；与 Coffer 投递的技能同名的文件夹提供**删除重复项**，确认后会删除智能体的那份副本。哪些技能对智能体生效是按技能逐个决定的；见[技能](/zh/guides/skills)。

## 故障排查 {#troubleshooting}

| 现象 | 原因 | 解决 |
| --- | --- | --- |
| **连接到 Coffer** 失败，提到 `coffer-mcp-shim` | 守护进程找不到 shim | 在守护进程的环境里设置 `COFFER_MCP_SHIM_PATH`，或重装 Coffer，确保 `~/.coffer/bin/coffer-mcp-shim` 存在。 |
| 状态显示**已接入**，但智能体没有 Coffer 工具 | 智能体没重启，或读的是另一个配置目录 | 重启智能体。自定义目录的话，用指向它的 `CLAUDE_CONFIG_DIR` / `CODEX_HOME` 启动智能体。 |
| **Availability** 显示**未找到** | 智能体的 CLI（`claude` 或 `codex`）不在守护进程的 `PATH` 上 | 安装 CLI，或让守护进程能看到它。 |
| 智能体显示**未安装** | 它的程序不在你登录 shell 的 `PATH` 上；只剩配置目录 | 重装智能体，或把它的程序放到 `PATH` 上。 |
| 检测为**已安装，未运行过** | 程序已安装，但从没创建过配置目录 | 照样添加：在标准目录注册会创建它。 |
| 添加被拒绝，返回 `AGENT_TYPE_REGISTERED` | 该类型已有注册的智能体；每种类型只有一个 | 要换目录，改用 `coffer agent edit <name> --config-dir <dir>`。 |
| 保存失败，返回 `CONFIG_FILE_STALE` | 打开之后文件变了 | 重新打开文件再保存。 |
| 插件卸载不见了 | `claude` 不在 `PATH` 上 | 自己运行 `claude plugin uninstall <id>`。 |

## 相关 {#related}

- [连接客户端](/zh/guides/connect-a-client)——shim、HTTP 端点和智能体身份
- [MCP 服务器](/zh/guides/mcp-servers)——网关向智能体提供什么
- [模型提供商](/zh/guides/providers)——把接入地址投射到智能体
- [智能体切面](/zh/architecture/agent-facets)——Coffer 如何把智能体之间的差异集中在一处
- [资源框架](/zh/architecture/resource-framework)——生效范围与不可变 uid
- 规格：[agent-registry](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/agent-registry/spec.md)、[claude-code](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/agent-registry/claude-code/spec.md)、[codex](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/agent-registry/codex/spec.md)
