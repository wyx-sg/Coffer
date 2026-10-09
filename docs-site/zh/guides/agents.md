---
title: 智能体
description: 把 Claude Code 和 Codex 注册到 Coffer、接入 Coffer，并管理它们的配置文件、MCP 条目、插件、Hook、模型、记忆和会话。
---

# 智能体 {#agents}

智能体是装在你机器上、由 Coffer 向其投递资源的编程智能体：Claude Code 或 Codex。本页讲如何注册智能体、如何把 Coffer 的 MCP 条目装进去，以及 Coffer 让你在智能体自己的文件里能看到和改动的一切。

## 智能体的用途 {#what-agents-are-for}

Coffer 共享的一切——MCP 服务器、技能、知识、记忆、模型提供商——最终都落到某个智能体上。注册智能体就是告诉 Coffer 这个智能体把配置放在哪里，这样 Coffer 就能：

- 往里面写入一个 `coffer` MCP 条目，让智能体通过[同一个网关](/zh/guides/mcp-servers)访问所有上游 MCP 服务器；
- 把[技能](/zh/guides/skills)链接进它的 `skills/` 文件夹；
- 把[模型提供商](/zh/guides/providers)投射到它的原生配置里；
- 在一个地方展示它的配置文件、MCP 条目、插件、原生记忆和会话。

Coffer 支持两种智能体类型：

| 类型 | 产品 | 默认配置目录 | Coffer 查找的程序 |
| --- | --- | --- | --- |
| `claude_code` | Claude Code（CLI 和 IDE/桌面形态） | `~/.claude` | `claude` |
| `codex` | OpenAI Codex（CLI 和 IDE 形态） | `~/.codex` | `codex` |

同一产品的 CLI 和 IDE 形态读的是同一个配置目录，所以注册一个智能体就能覆盖两者。Claude Desktop 聊天应用有自己的配置，不属于受支持的智能体。

### 每种类型一个智能体 {#one-agent-per-type}

一台机器上每种类型最多注册一个智能体，智能体的名字**就是**它的类型：`claude-code` 或 `codex`。你不用起名，智能体也没有标题或描述。凡是 Coffer 问你指哪个智能体的地方——技能或 MCP 服务器的生效范围，以及所有 `/api/v1/agents/{uid}/…` 路由——都可以填类型（`claude-code`；`claude_code` 也能识别）或智能体的 uid。

除了类型，智能体唯一的设置就是**配置目录**，外加[模型绑定](#models)。注册时默认使用该类型的标准目录（`~/.claude`、`~/.codex`），除非你另行指定。把 Coffer 指向别的目录，是把这唯一的智能体挪过去，绝不会新增第二个。注册一个已注册过的类型会被拒绝，返回 `409 AGENT_TYPE_REGISTERED`。

::: info 智能体自己的文件才是真相来源
Coffer 从不把智能体的配置复制进自己的存储。配置文件、MCP 条目、插件和原生记忆，每次查看时都从磁盘读取，会话则由智能体自己列出。智能体记录本身只保存类型、配置目录和模型绑定。
:::

## 注册智能体 {#register-an-agent}

<Shot name="agents-list" alt="智能体页面：一个已连接，一个尚未连接。" />

### 从检测到的智能体注册 {#from-detected-agents}

Coffer 靠两个信号检测智能体：`PATH` 上的程序——用的是你登录 shell 给出的 `PATH`，所以即使守护进程是从 Dock 启动的，用 Homebrew 或 Node 版本管理器装的智能体也能被找到——以及它的配置目录。顺带会读取程序版本（`claude --version`、`codex --version`）。Coffer 从不自行注册任何东西，守护进程启动时也不会自动注册智能体。

Coffer 会报告每一种受支持的类型（无论是否已注册），状态是以下之一：

| 状态 | 程序 | 配置目录 | 你能做什么 |
| --- | --- | --- | --- |
| **已安装** | 找到 | 存在 | 连接它。 |
| **已安装，未运行过** | 找到 | 尚未创建 | 连接它。在标准目录注册时会创建该目录，里面只放 Coffer 需要的东西（`skills` 文件夹）。 |
| **未安装** | 缺失 | 存在 | 没有可添加的：这个目录是以前安装留下的。重装智能体，或者忽略它。 |
| **缺失** | 缺失 | 不存在 | 这台机器上什么都没有。该类型仍会列出，所以每种类型总有一行。 |

对每种类型，Coffer 会查看它的标准目录；如果守护进程的环境设置了该类型自己的变量（Claude Code 是 `CLAUDE_CONFIG_DIR`，Codex 是 `CODEX_HOME`），还会查看变量指向的目录。第二个目录永远不会成为第二个智能体：标准目录存在时，它作为这唯一智能体的**使用其他配置目录**选项提供；只有它存在时，它就是「连接」注册的目录。Coffer 不会搜索磁盘的其他位置；要使用别的目录，见[使用其他配置目录](#use-a-different-config-directory)。已注册的类型不会再次提供。

**Web 界面：** **智能体**页面始终恰好有两行，先 Claude Code 后 Codex，不管各自是否安装。检测是自动的——打开页面时、窗口重新获得焦点时，以及每隔几分钟——所以没有「检测」按钮，也没有「添加智能体」对话框。每一行显示一种状态，并提供它对应的那一个操作：

| 行显示 | 含义 | 操作 |
| --- | --- | --- |
| **未连接** | 已安装，Coffer 还没有连接它——新发现的智能体和被你断开的智能体显示一样 | **连接** |
| **已连接** | Coffer 的条目和 Hook 都在智能体里 | 无 |
| **需要修复** | 连接缺了一部分 | **修复** |
| **配置残留** | 有目录，但 `PATH` 上没有程序 | 无；**交给 &lt;Agent&gt; ▾**（重装交接）在该行 **⋯** 旁边 |
| **未安装** | 两者都没有 | 无；**交给 &lt;Agent&gt; ▾**（安装交接）在该行 **⋯** 旁边 |

没装智能体的行不显示版本，名字下面写**这台 Mac 上没有**，或写目录里还剩什么。**总览**只列出需要你处理的智能体：需要修复的、配置目录残留的，以及它的记忆 Hook 没有被智能体批准或从未运行过的。同一个 Hook 问题每个智能体只列一行：未批准的 Hook 只显示为待批准那一行，只有智能体会运行却从未触发的 Hook 才显示为从未触发。仅仅是未连接或未安装的智能体不会列出，首次运行也不会。

Coffer 不负责安装智能体，而安装又依赖具体机器，所以找不到程序的行会把活交给一个智能体，而不是给出安装命令。该行在 **⋯** 前面放着交接拆分按钮**交给 &lt;Agent&gt; ▾**，用的是守护进程写的一段提示词：在这台机器上安装（或重装）这个智能体，保留它现有的配置目录，确保它的程序能在 Coffer 查找的 `PATH` 上被找到（提示词里列出了这个 `PATH`），并用 `claude --version` 或 `codex --version` 确认，然后回来点**再检查一次**——登录留给你自己。**交给 &lt;Agent&gt;**会在你的首选终端里启动默认的交接智能体，把提示词作为它的第一条消息；▾ 后面是**交给**另一个智能体（它可用时）和**复制提示词**，后者复制它，给 Coffer 之外的任意助手用。没有受管智能体可以执行时（缺失的智能体自己装不了自己），该行只提供**复制提示词**。**⋯** 菜单不会重复它。智能体页面概览 tab 的问题状态里也提供同样的提示词。你仍然可以按厂商文档自己安装智能体；程序一出现在 `PATH` 上，这一行会自动更新。

对新发现的智能体点**连接**，会在标准目录注册它并连接它。它会先打开**审阅改动**——列出将写入的每个文件和新增的行——在你应用之前什么都不写。首次运行时，如果两个智能体都已安装且都没连接，**全部连接**会在一次确认里审阅并连接两者。已注册的行还会显示它的提供商（它所用的 Coffer 连接，或它的内置登录）、从智能体自己的配置里读出的默认模型（配置里没写时显示**内置默认**，即智能体按厂商的默认走；智能体自己报告了默认模型时（Codex 会报告）括号里写出它），以及有多少技能、MCP 服务器和插件送达它，点开进入智能体的页面。表格下方有一行说明这些数量的含义。

### 使用其他配置目录 {#use-a-different-config-directory}

Claude Code 用 `CLAUDE_CONFIG_DIR` 启动时会读取另一个目录，Codex 则是 `CODEX_HOME`。如果你就是这样运行智能体的，把这个目录告诉 Coffer，注册时或之后都可以。

对已注册的智能体，同一个菜单项会把它挪过去。

**Web 界面：** 在该行（或智能体页面）的 **⋯** 菜单里选**使用其他配置目录…**。用系统原生的文件夹对话框选择文件夹（只有宿主没有原生对话框时才用应用内浏览器）；对话框会列出该类型的常见文件哪些存在。对尚未添加的智能体，**使用此目录**会直接在该目录注册它，但不连接。对已连接的智能体，按钮写的是**审阅改动**：智能体在它的目录里带着 Coffer 的 `coffer` 条目和记忆 Hook，所以换目录会把这两样从旧目录取出、写进新目录，你会在任何东西挪动之前先看到这些行。

接受目录之前，Coffer 会先创建 `<config_dir>/skills`，然后检查该目录存在、是目录、可写，且不是系统位置（`/etc`、`/usr`、`/var/folders/` 之外的 `/var`、`/System`、`C:\Windows`、`C:\Program Files` 等）。被拒绝的注册不会留下任何东西。非标准目录必须事先存在；只有「已安装、未运行过」的智能体的标准目录会替你创建。挪动智能体会把它的技能重新投递到新目录。

当 Coffer 自己启动一个注册在非标准目录上的智能体时——一次[对话](/zh/guides/chat)或[消息渠道](/zh/guides/channels)轮次、一次模型列表探测、一次插件卸载——它会把 `CLAUDE_CONFIG_DIR` 或 `CODEX_HOME` 设为那个目录，让智能体读到 Coffer 放在那里的技能、MCP 条目和设置。

### 编辑和断开连接 {#edit-and-disconnect}

智能体行和智能体页面上的 **⋯** 菜单包含**使用其他配置目录…**、**在访达中显示配置目录**、**复制 uid**、和**断开连接…**（只要有任何部分已安装）。没有**移除**：列表里始终有两个受支持智能体各一行，想把 Coffer 的条目和 Hook 从某个智能体里拿掉，就断开它。

- **编辑**修改配置目录或[模型绑定](#models)。名字就是类型，不能改。所有引用智能体的地方——生效范围列表、消息渠道的默认智能体、已安装的 MCP 条目——保存的都是智能体不可变的 `uid`。
- **断开连接…**会从智能体里删掉 Coffer 的网关条目和记忆 Hook，文件里的其他内容原样保留（见[把智能体接入 Coffer](#connect-an-agent-to-coffer)）。智能体仍保持已注册，所以[生效范围](/zh/guides/skills)授予它的技能会继续投递。

## 把智能体接入 Coffer {#connect-an-agent-to-coffer}

接入会一次性把 Coffer 需要的一切写进智能体自己的配置：

| 部分 | 作用 | 何时 |
| --- | --- | --- |
| 网关 MCP 条目 | 一个指向 `coffer-mcp-shim` 的 `coffer` stdio MCP 服务器条目。智能体通过它访问所有启用的上游服务器、Coffer 自己的工具，以及投递给它的知识。 | 总是 |
| 记忆投递 Hook | 两个 Hook 条目——会话开始、每次提问——Coffer 通过它们把记忆交给智能体。见[记忆](/zh/guides/memory#install-the-hook)。 | 总是 |

<Shot name="agent-page" alt="智能体页面，含 Coffer 写入的连接条目。" />

断开连接会移除这两部分，而且只移除 Coffer 自己的条目；这些文件里的其他内容保持原样。

**Web 界面：** 概览 tab 的**连接**区展示每个部分——MCP 条目和记忆 Hook，各自所在的文件，以及是否为最新——并在区块标题处放着当前状态所需的那一个修复按钮：未连接时是**连接**，需要修复时是**修复**，Codex 还没批准 Coffer 的 Hook 时是**重新检查**。已连接的智能体这里没有按钮；**断开连接…**在 ⋯ 菜单里。页面头部永远不会变成修复按钮：它只有智能体的图标、名字、一个状态标签（**已连接**、**未连接**、**需要修复**、**Hook 未获批准**或**配置残留**）、**新建对话**和 ⋯ 菜单。在**智能体**列表里，行上是同样的状态和同样的操作。每次连接、修复和断开都会先打开同一个**审阅改动**预览：修复只列出缺失的部分，断开只列出它要删的行。如果写入中途失败，预览会指出哪一项失败，保留已经生效的改动，并只对失败的那项提供重试。

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

记忆 Hook 的两个条目见[文件系统](/zh/reference/filesystem)。

接入是幂等的：再接入一次会原地重写每个条目，绝不会加第二个。什么都没装时断开连接也会成功，且不做任何改动。每次写入都会备份，并按部分记入审计（`agent_mcp_installed` / `agent_mcp_uninstalled`、`memory_delivery_installed` / `memory_delivery_removed`）。连接状态每次都从文件读取，Coffer 不存储它。

### 为什么 shim 路径是绝对路径 {#why-the-shim-path-is-absolute}

守护进程可能从桌面应用、登录服务或虚拟环境里运行，它们都不继承你 shell 的 `PATH`，智能体也可能不继承。所以 Coffer 写的是完整路径。它按以下顺序解析 shim：

1. `COFFER_MCP_SHIM_PATH`，如果设置了且文件存在；
2. 守护进程 `PATH` 上的 `coffer-mcp-shim`；
3. 运行守护进程的 Python 解释器的 scripts 目录（`pip` 和 `uv` 放置控制台脚本的地方）；
4. 与正在运行的可执行文件打包在一起的二进制；
5. 已部署的 `~/.coffer/bin/coffer-mcp-shim`。

当结果是安装版时，Coffer 写入稳定的 `~/.coffer/bin/coffer-mcp-shim` 链接，而不是带版本号的目录，这样条目在升级后依然有效。如果找不到任何 shim，安装会以 `SHIM_NOT_FOUND` 失败，指出缺失的二进制，且不写入任何东西。这个拒绝会附带一段交接提示词：列出 Coffer 查找过的每个位置，并请一个智能体找到或重装 shim，使其能在 `~/.coffer/bin/coffer-mcp-shim` 解析到。接入的审阅界面会在**重试**旁提供**复制提示词**。

### 智能体 uid 与生效范围 {#the-agent-uid-and-reach}

`--agent-uid` 参数是网关判断一个会话属于哪个智能体的依据。shim 在 MCP `initialize` 握手里传递它，网关在整个会话里用它决定该智能体能看到哪些服务器。[生效范围](/zh/architecture/resource-framework)只列了某些智能体的服务器，对其他所有会话都是隐藏的。

条目携带 uid，是因为 Coffer 只把它写进这个文件一次、之后不再回头改，而 uid 正是所有其他记录保存的身份。手写的、不带 `--agent-uid` 的 shim 条目仍然能用，但它的会话身份不明，只能看到对所有智能体生效的服务器。详见[连接客户端](/zh/guides/connect-a-client)。

## Coffer 读什么、写什么 {#what-coffer-reads-and-what-it-writes}

Coffer 只通过一小组有文档说明的面接触智能体的文件：

| 面 | Coffer 读 | Coffer 写 |
| --- | --- | --- |
| 白名单内的配置文件 | 是（列出；文件内容仅在你预览时读取） | 从不替你写；你在自己的编辑器里改 |
| 智能体配置里的 MCP 条目 | 是 | 安装/卸载 `coffer`、移除、纳入托管 |
| 插件 | 清单和启用状态 | 启用开关；按该类型自己的方式卸载 |
| 模型提供商 key | 是（每轮调和都会检查） | 当你切换[提供商](/zh/guides/providers)时，以及把值已过时的投射重新对齐时 |
| 原生记忆库 | 是 | 从不 |
| 会话（智能体自己的对话记录） | 是，通过智能体 | 仅在你要求时重命名和删除，通过智能体 |
| Codex `auth.json` | 从不 | 从不 |

Coffer 的每次写入：

- 原子替换文件（临时文件加重命名）；
- 如果文件在 Coffer 读取之后变了——智能体在这期间改写了它——就以 `CONFIG_FILE_STALE` 拒绝写入，文件保持原样；
- 把之前的内容复制到 `~/.coffer/config-backups`（每次写入一个带时间戳的文件，从不放在智能体的文件旁边）；**配置备份**保留策略默认在 30 天后删除旧备份，并始终保留每个文件最新的一份；
- 用 `tomlkit` 编辑 Codex 的 `config.toml`，你的注释、键顺序以及 Codex 自己的内部表（`[marketplaces.*]`、`[hooks.state.*]`、`[projects.*]`）逐字节保留；
- 记录一条审计条目。

当某个配置文件无法解析时，MCP 和插件 tab 会显示解析错误，并对该文件切换为只读；智能体页面的其他部分照常可用。

## 配置文件 {#config-files}

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

**Web 界面：** 打开智能体，选择**配置文件**。这个 tab 左边是文件树，右边是只读预览，中间的分隔条可以拖动。文件树列出智能体的配置文件；`agents/` 这样的目录条目可展开，列出里面的文件。只列出已存在的文件：智能体还没创建的文件不会出现，因为 Coffer 不创建配置文件。选中一个文件即可按磁盘上的原样预览——进入时默认打开第一个文件，当前打开的文件记在页面地址里。预览顶部的工具栏显示文件路径和大小，并有**在编辑器中打开**和**在访达中显示**；文件树顶部的图标可在访达中显示整个配置文件夹。要修改文件，用**在编辑器中打开**。Coffer 没有编辑器、**新建文件**或**删除**：配置文件要在你自己的编辑器里改（在**设置 › 通用**里选择），或者让智能体去改。Coffer 自己对这些文件的改动——接入、修复、插件开关、MCP 条目、切换提供商——都会先经过**审阅改动**。

**API：** `GET /agents/{uid}/config-files` 列出文件及其键、路径、文件夹、格式、大小和修改时间。`GET /agents/{uid}/config-files/{key}/content` 读取单个文件用于预览（`subagents` 目录再加列表里给出的 `?child=<相对路径>`）。没有写入文件的路由。

::: tip 你的编辑不会被覆盖
Coffer 会把它写入的每个文件的上一版内容保存在 `~/.coffer/config-backups` 下，并拒绝写入在 Coffer 读取之后变了的文件。如果你或智能体在 Coffer 即将写入时编辑了文件，Coffer 的写入会以 `CONFIG_FILE_STALE` 被拒绝，你的编辑保留。
:::

## 管理智能体自己的 MCP 条目 {#manage-the-agent-s-own-mcp-entries}

智能体经常在自己的文件里直接配置 MCP 服务器。**MCP 服务器** tab 先放 Coffer 管理的部分——一行**来自 Coffer**，说明有多少已注册服务器通过网关条目对这个智能体生效，列出前几个名字，并链接到**打开 MCP 服务器 ›**，也就是按这个智能体筛选后的 MCP 服务器页面（`/mcp-servers?agent=<uid>`）——然后是**智能体自己的 MCP 服务器**：它文件里的直接条目，带搜索。Coffer 的服务器不在这里逐个列出。自有条目提供**纳入托管**；与已注册 MCP 服务器重复的条目提供**移除重复项**，它会把条目从智能体文件中删掉，因为网关已经在提供它。第二行**来自 Coffer** 统计对这个智能体生效的自定义工具分组，并链接到**打开自定义工具 ›**，也就是按这个智能体筛选后的[自定义工具](/zh/guides/custom-tools)列表（`/custom-tools?agent=<uid>`）；第一行只统计已注册的 MCP 服务器。一行最多一个按钮；把任意条目从它的文件里取出的**移除…**在该行的 **⋯** 菜单里。

| 类型 | 直接条目读取自 |
| --- | --- |
| Claude Code | `.claude.json`（`global` 文件）和 `settings.json` 里的 `mcpServers` |
| Codex | `config.toml` 里的 `[mcp_servers.*]`（会显示 `enabled` 标志，但从不写入） |

点击直接服务器所在的行（或它的名字），会在对话框里打开它的条目。对话框以只读方式展示智能体文件里关于该服务器的全部内容：传输方式、命令及每个参数（或 URL）、工作目录、格式支持时的 `enabled` 标志、环境变量和 HTTP 头的名字、条目带的其他键，以及所在的配置文件。密钥值永远不离开守护进程：环境变量和请求头的值只显示为*已设置*或*密钥 · 已隐藏*，名字看起来像密钥的其他键（规则见下）显示为*已隐藏*。Coffer 不会为了展示这些而启动直接服务器，所以不列工具。对话框页脚把行上的两个操作放在**关闭**两侧：左边是**移除**（或**移除重复项**），右边是**纳入托管**。

对直接条目你可以做两件事：

- 从源文件中**移除**它（原子写入、在 Coffer 的文件夹里保留一份备份副本，审计为 `agent_mcp_entry_removed`）。
- **纳入托管**：Coffer 把条目注册为一个 `mcp_server` 资源，确认能读回，然后才删除直接条目。任何失败都会回滚新资源，并让智能体的文件保持逐字节不变。之后该服务器通过网关提供给每个智能体。

当条目的环境变量或请求头在一个看起来像密钥的键下（包含 `TOKEN`、`SECRET`、`PASSWORD`、`PASSWD`、`API_KEY`、`APIKEY`、`CREDENTIAL` 或 `AUTHORIZATION`）带有非空值时，纳入托管对话框会在**存储为**下逐个列出它们，默认选**密钥**。Coffer 把当前值存进它的[加密密钥存储](/zh/guides/secret-store)，新资源的配置里只带引用。像 `Authorization: Bearer abc…` 这样的请求头值会被拆开：`abc…` 存为密钥，请求头行的认证方案设为 Bearer。名字冲突会被拒绝：换一个**在 Coffer 中的名称**。对同时出现在两个文件里的 Claude Code 名字，纳入的是你打开的那一条。`coffer` 条目本身永远不能用这种方式移除或纳入托管。

## 插件 {#plugins}

**插件** tab 在标签栏的**更多**里，列出已安装的插件——都是智能体自己的，因为 Coffer 不安装插件——带搜索、版本和市场、启用开关，以及一个只有**卸载…**一项的 **⋯** 菜单。缓存目录已不存在的插件标记为**缓存缺失**，并在**更多**上显示一个警告点；Coffer 不会尝试修复。

点击插件所在的行（或它的名字）可打开它的信息对话框。对话框展示插件的 `<name>@<marketplace>` id、版本、作者、描述和主页、来源市场，以及安装目录。下方列出插件提供的一切，从其包的默认位置读取：

| 内容 | 读取自 |
| --- | --- |
| 技能及其描述 | `skills/<name>/SKILL.md` |
| 命令及其描述 | `commands/*.md` |
| 子智能体及其描述 | `agents/*.md` |
| Hook 事件 | `hooks/hooks.json` |
| MCP 服务器 | `.mcp.json` |

对话框只读取插件文件，不改动任何东西。启用和卸载在 tab 上。

| | Claude Code | Codex |
| --- | --- | --- |
| 清单读取自 | `plugins/installed_plugins.json`、`known_marketplaces.json` | `config.toml` 里的 `[plugins."…"]` 和 `[marketplaces.*]` |
| 启用/停用写入 | 只写 `settings.json` 里的 `enabledPlugins` | 只写插件自己的 `enabled` 字段 |
| 卸载 | 运行 `claude plugin uninstall <id>` | 从 `config.toml` 删除条目，并删除 `plugins/cache/<marketplace>/<plugin>/` |

Coffer 从不写 Claude Code 自己的清单文件。当 `claude` CLI 不在 `PATH` 上时，卸载不可用（`PLUGIN_UNINSTALL_UNSUPPORTED`），Web 界面会隐藏这个操作。安装插件和管理市场仍由智能体自己的工具负责。

## Hook {#hooks}

**Hooks** tab 展示智能体将运行的每个 Hook，直接从智能体的文件读取：每个 Hook 的事件、matcher、命令，以及它来自哪里——智能体自己的某个设置文件，或某个插件（按名字）。只包含已开启的插件，因为停用插件的 Hook 不会运行。项目自己设置里的 Hook 不显示，因为 Coffer 不知道你在哪些仓库里使用这个智能体。它分两部分，Coffer 的在前。

| | Claude Code | Codex |
| --- | --- | --- |
| 智能体自己的文件 | `settings.json`、`settings.local.json` | `hooks.json` |
| 插件 | 每个已启用插件的 `hooks/hooks.json` | 每个已启用插件的 `hooks/hooks.json`（如果有） |
| Coffer 自己的 Hook | `settings.json` 里的 `SessionStart` 和 `UserPromptSubmit` | `hooks.json` 里同样的两个事件 |

**Coffer 的记忆 Hook**——[记忆投递 Hook](/zh/guides/memory#install-the-hook)——在它的两个条目上各有标记，并作为一个 Hook 上报，放在最上面的一块属性里：它的状态和最近触发的时间、命令、所在的事件，以及声明它的文件。修复按钮在这一块的标题处（**修复**，或**重新检查**），状态为什么有问题写在这一块里。状态说明它的情况：

- **最新**——恰好装在两个事件上，每个都恰好是当前版本 Coffer 写入的命令。
- **已过期**——Coffer 的 Hook 在，但命令与 Coffer 现在写的不同，或所在事件集合不同。守护进程会在下一轮调和时重写它；**修复**会立即重写。
- **缺失**——没有 Coffer 的 Hook。**修复**会重新把智能体接入 Coffer，从而装上它。

对 Codex，它还会说明 Codex 是否会运行这个 Hook。Codex 会跳过你没批准的条目，而 Coffer 的 Hook 只有两个条目都被批准才算已批准，所以**未批准**（或 Coffer 更新改了命令之后的**批准后已变更**）意味着至少有一个条目已安装但不会运行。智能体页面会显示 **Hook 未获批准**，总览的**需要你处理**里也会列出它。打开 Codex，运行 `/hooks`，信任 Coffer 的两个条目。Coffer 不会替你批准，之后用**重新检查**重新读取 Codex 的批准情况。

它还会根据[审计日志](/zh/guides/activity)显示 Hook 最近一次触发的时间。一个你每天都在用的智能体显示**从未触发**，就说明这个智能体没有在运行该 Hook；这一块会写出最可能的原因并链接到**活动**，总览的**需要你处理**里也会列出它。

**智能体自己的 Hook** 是一张表，列为**事件**、**命令**、**匹配器**和**文件**，不含 Coffer 的 Hook，带一个对命令的搜索，以及一个显示每个事件有多少 Hook 的**事件**筛选；一旦其中之一缩小了表格，它会说明显示了多少个、共多少个。点一行查看详情：完整的命令、事件及其何时运行、匹配器、类型、超时、文件，以及条目在文件里的位置（`hooks.<event>[group].hooks[hook]`），并有**复制命令**和**在编辑器中打开**。这个 tab 上的一切都是只读的：Coffer 从不编辑其他工具的 Hook，所以 Hook 要在它自己的文件里改，点文件名会在你的编辑器里打开那个文件。

## 模型 {#models}

模型目录回答的是「这个智能体可以用哪些模型」。Coffer 每次都从已安装的智能体读回它，所以新发布的模型不需要 Coffer 发版就会出现：

- **Claude Code：** 内嵌在 `claude` 二进制里的模型别名（例如 `opus`、`sonnet`、`haiku`），加上 `.claude.json` 里的 `additionalModelOptionsCache`。
- **Codex：** Codex app server 的 `model/list` RPC（以指向智能体目录的 `CODEX_HOME` 运行），加上 `config.toml` 里提到的模型。

每个来源独立失败：未登录的 Codex 或变了布局的二进制，只会让那个来源的模型缺失。

当智能体所在的[模型提供商](/zh/guides/providers)整理了模型列表时，选择器会改为提供那份列表。

智能体记录保存着提供商投射写入智能体配置的模型绑定。它在智能体的总览里修改：**模型**下的**更改…**会在写入之前先展示将要写的行（见[智能体页面](#the-agent-page-in-the-web-ui)）。

## Web 界面中的智能体页面 {#the-agent-page-in-the-web-ui}

智能体页面以智能体类型寻址（`/agents/claude_code`、`/agents/codex`）。页面头部有智能体的图标、名字、一个状态标签和 **⋯** 菜单——名字下面没有说明行——它也永远不会变成修复按钮。下面是八个 tab，都不带数量。六个在标签栏里，各有自己的地址：**总览**（`/agents/<type>`）、**技能**、**MCP 服务器**、**Hooks**、**配置文件**和**会话**（`…/skills`、`…/mcp-servers`、`…/hooks`、`…/config`、`…/sessions`）。**更多**里放最少用的两个，**插件**和**记忆**（`…/plugins`、`…/memory`）；其中一个打开时，**更多**会显示它的名字并带下划线，**更多**上的警告点表示里面有 tab 需要处理。没有模型 tab。

**总览**是单列，从上到下：

1. **连接**——[连接](#connect-an-agent-to-coffer)的两个部分，以及当前状态所需的那一个按钮。
2. **这个智能体能用什么**——六张卡片，三列两行：**MCP 服务器**、**技能**、**配置文件**、**插件**、**Hooks** 和**记忆**。每张显示数量、一条事实，以及当智能体自己的东西等着你看时的警告「N 个待查看」；整张卡片点开对应 tab。
3. **模型**——**提供商**、**模型**和**路径**（经由 Coffer 的中转，带**测试**；或直连），以及**更改…**。
4. **详情**——**版本**、**配置目录**、**UID** 和**注册于**。智能体的名字就是类型，所以没有名字或标题可编辑。

**轮换中转令牌**在头部的 **⋯** 菜单里，只有智能体经由 Coffer 的中转运行时才提供。

### 更改智能体的模型 {#change-an-agent-s-model}

**模型**下的**更改…**会为两个智能体打开同一个小表单。选一个**提供商**——智能体的内置登录，或一个能覆盖它的已启用提供商（见[模型提供商](/zh/guides/providers)）——然后：

- **Claude Code：** **模型**和**各档位的模型**——Opus、Sonnet、Haiku，提供商列出 Fable 时还有 Fable——并预填建议值。它写入智能体的 `settings.json`。
- **Codex：** **模型**，没有档位。它写入 `config.toml` 和旁边 Coffer 自己的模型列表文件 `coffer-model-catalog.json`，所以审阅里是两项改动。
- **内置登录**只问**模型**，没有分档：**内置默认**（智能体自己的配置没有指定模型），或智能体自己的某个模型，默认选中它配置里现在写的那个。Coffer 把它写进智能体自己配置的顶层 `model`——Codex 是 `config.toml`，Claude Code 是 `settings.json`——选**内置默认**则删掉这一项。选内置登录时还会取出 Coffer 写过的键，并清掉 Coffer 为提供商记下的模型。对 Codex，正在使用会列出自有模型的提供商时，Codex 自己的模型列表为空，只提供**内置默认**。

在**模型**下面，Coffer 会自动用选中的模型、按智能体实际的调用方式测试提供商（Claude Code 总是走 Anthropic 兼容接口，只提供 OpenAI 兼容接口的提供商会在这里失败）——**正在测试连接…**，然后是带用时的**连接正常**，或带原因和**重试**的**连接失败**。针对这一对提供商和模型的测试通过之前，**审阅改动**不可用（内置登录不需要测试），旁边有一行说明原因。通过后它会打开每个文件将增删的确切行，并注明只有这些行会变、会在 Coffer 的文件夹里保留一份备份副本；**应用**才会写入。如果审阅画出之后文件在磁盘上变了——智能体重写了它，或你编辑了它——应用会拒绝、什么都不写，说明哪个文件变了，并提供**重新加载预览**。应用成功后会提示：重启该智能体后生效，已打开的会话仍用原来的设置。提供商的**使用方**列表里的链接（**Codex › 更改模型**）会在到达时直接打开这个表单。

### 原生记忆和会话 {#native-memory-and-sessions}

**记忆** tab 以只读方式列出智能体自己的记忆库：

- **Claude Code：** 每个项目一个库，位于 `<config_dir>/projects/<slug>/memory/`，标注真实的项目目录。
- **Codex：** 全局的 `<config_dir>/memories/MEMORY.md`，按它把任务组路由到的项目拆成每项目一行。

打开一行会在文件树里显示该库的文件，并带只读预览。开启「记忆」[实验功能](/zh/guides/experimental-features)时，tab 以 **Coffer 的记忆**开头——Coffer 给这个智能体的记忆 Hook、它最近触发的时间和投递的内容，附带指向[记忆](/zh/guides/memory)页面的链接，以及 Hook 过期或缺失时的**修复**——智能体自己的库排在后面。

**会话** tab 列出智能体自己的会话——你在终端或应用里跑的，以及[消息渠道](/zh/guides/channels)发起的——带标题、智能体、工作目录和最近活动时间。Coffer 向智能体自己要这份列表（Claude Code 的会话列表，Codex 的 `thread/list`），不解析智能体的文件。搜索匹配标题和目录。属于某个消息渠道对话的会话还会显示它的消息渠道，轮次运行时显示**运行中**，等你回答时显示**等你处理**，并带行内**停止**。

打开一行，就在你的首选终端里、会话所在的目录恢复这个会话：Claude Code 是 `claude --resume <id>`，Codex 是 `codex resume <id>`。分体按钮的**复制命令**是给 Coffer 不认识的终端用的替代方式。运行中的轮次或等待中的提问会先询问：在消息渠道里回答，或停止轮次并在终端中继续。在**设置 › 通用 › 首选终端**里选择终端；见[对话](/zh/guides/chat#open-in-terminal)。

**⋯** 菜单有**重命名**和**删除…**，都由智能体对它自己的会话执行（Claude Code 的 `rename_session` 和 `delete_session`，Codex 的 `thread/name/set` 和 `thread/delete`）。删除会先确认，而且是永久的。删除某个消息渠道对话在用的会话，也会移除该对话的那一行，消息渠道的下一条消息会开始一个新的。如果会话已经不存在，错误是 `NATIVE_SESSION_NOT_FOUND`，刷新列表即可。无法列出会话的智能体类型会返回 `AGENT_TYPE_UNSUPPORTED`。

Claude Code 会删除超过 `cleanupPeriodDays`（默认约 30 天）没有动过的会话，已经没有的会话会从这个列表里消失。想保留更久，请在 Claude Code 的 `settings.json` 里调大它；见[对话](/zh/guides/chat#chat-and-the-agent-s-own-sessions)。

原生记忆库是普通文件；**记忆** tab 会显示每个库所在的文件夹，你可以用自己的工具读取其中的文件。

Coffer 不展示会话文本：读一个会话要去智能体自己的界面。Coffer 从不把会话或原生记忆写入、存储或发送到任何地方。

## 智能体上的技能 {#skills-on-an-agent}

**技能** tab 以一行**来自 Coffer** 开头：Coffer 投递给这个智能体的技能有多少个、前几个名字，以及**打开技能 ›**，它会打开按这个智能体筛选后的[技能](/zh/guides/skills)页面（`/skills?agent=<uid>`）——Coffer 的技能不在这里逐个列出。它下面是**智能体自己的技能**——Coffer 不管理的技能文件夹——带搜索。每行有一个状态词——**未托管**、**无效的 SKILL.md**、**外部链接**或**重复**——最多一个按钮。有效的文件夹提供**纳入托管**，它会先询问**在 Coffer 中的名称**和它的**生效范围**（默认所有智能体，可以缩小，也可以关闭），再把它移进 Coffer 的技能库；与 Coffer 投递的技能同名的文件夹提供**删除重复项**，确认后会删除智能体的那份副本。点一行会打开这个文件夹自己的页面——它的属性，以及文件树加只读查看器里的文件——页面头部有**纳入托管**和带**删除…**的 **⋯** 菜单。哪些技能对智能体生效是按技能逐个决定的；见[技能](/zh/guides/skills)。

## 一次操作智能体自己的多个条目 {#act-on-several-items-at-once}

在**技能**、**MCP 服务器**和**插件**标签页上，智能体自己的列表可以批量操作；Coffer 管理的部分（**来自 Coffer** 那一行）不可以。每一行都有复选框，列表上方的复选框会选中搜索结果里的所有行；所在配置文件无法解析的 MCP 条目没有复选框。勾选行之后，一条显示「已选 N / M」的操作栏会取代搜索框，带有各项操作和**清除**；按 **Esc** 可清空选择。

| 标签页 | 操作 | 说明 |
| --- | --- | --- |
| 技能 | **纳入托管**、**删除…** | 纳入托管只处理未托管的文件夹，并一次询问一个所有技能共用的生效范围；每个技能沿用原文件夹名。 |
| MCP 服务器 | **纳入托管**、**移除…** | 纳入托管只处理绕过 Coffer 的条目，沿用各自的名称并使用默认的密钥引用；对话框会说明有多少个密钥值移入[密钥库](/zh/guides/secret-store)。 |
| 插件 | **启用**、**停用**、**卸载…** | 启用和停用无需确认，并跳过已处于该状态的插件。智能体的程序找不到时，卸载不可用并说明原因。 |

Coffer 会对每个条目各发一次与单项操作相同的请求，依次进行，所以 Coffer 里已有同名项时只有该条目失败。对话框或提示会说明所选条目中有多少被跳过。全部成功时给出一次确认并清空选择；有失败时会按名称列出原因，**重试**只重发这些条目。

## 故障排查 {#troubleshooting}

| 现象 | 原因 | 解决 |
| --- | --- | --- |
| **连接**失败，提到 `coffer-mcp-shim` | 守护进程找不到 shim | 在守护进程的环境里设置 `COFFER_MCP_SHIM_PATH`，或重装 Coffer，确保 `~/.coffer/bin/coffer-mcp-shim` 存在。 |
| 智能体显示**已连接**，但没有 Coffer 工具 | 智能体没重启，或读的是另一个配置目录 | 重启智能体。自定义目录的话，用指向它的 `CLAUDE_CONFIG_DIR` / `CODEX_HOME` 启动智能体。 |
| 智能体显示**找不到** | 它注册过，但它的 CLI（`claude` 或 `codex`）不在守护进程的 `PATH` 上，目录也没了 | 安装 CLI，或让守护进程能看到它。 |
| 智能体显示**配置残留** | 它的程序不在你登录 shell 的 `PATH` 上；只剩配置目录 | 重装智能体（该行的**交给 &lt;Agent&gt; ▾**），或把它的程序放到 `PATH` 上。 |
| 检测为**已安装，未运行过** | 程序已安装，但从没创建过配置目录 | 照样连接：在标准目录注册会创建它。 |
| 注册被拒绝，返回 `AGENT_TYPE_REGISTERED` | 该类型已有注册的智能体；每种类型只有一个 | 要换目录，改用该行 **⋯** 菜单里的**使用其他配置目录…**。 |
| Coffer 的改动失败，返回 `CONFIG_FILE_STALE` | 智能体的文件在 Coffer 读取之后变了 | 再执行一次该操作；Coffer 会重新读取文件。 |
| 插件卸载不见了 | `claude` 不在 `PATH` 上 | 自己运行 `claude plugin uninstall <id>`。 |

## 相关 {#related}

- [连接客户端](/zh/guides/connect-a-client)——shim、HTTP 端点和智能体身份
- [MCP 服务器](/zh/guides/mcp-servers)——网关向智能体提供什么
- [模型提供商](/zh/guides/providers)——把接入地址投射到智能体
- [智能体切面](/zh/architecture/agent-facets)——Coffer 如何把智能体之间的差异集中在一处
- [资源框架](/zh/architecture/resource-framework)——生效范围与不可变 uid
- 规格：[agent-registry](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/agent-registry/spec.md)、[claude-code](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/agent-registry/claude-code/spec.md)、[codex](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/agent-registry/codex/spec.md)
