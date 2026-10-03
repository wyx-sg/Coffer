---
title: 命令行工具
description: 声明技能需要的命令行工具，在一个页面上看清其中以及 MCP 服务器的启动器哪些缺失、版本太旧或未登录，并用 Coffer 为这台机器写好的提示词把修复交给你的智能体。
---

# 命令行工具 {#clis}

很多技能会驱动某个命令行工具——用 `gh` 分拣 issue，用 `jq` 过滤 JSON，用 `aws` 读取存储桶。工具缺失、版本比技能要求的旧、或者没登录时，照着技能做事的智能体就会在调用它的那一步失败。MCP 服务器也依赖命令：用 `uvx` 启动的 stdio 服务器，没有 `uv` 就起不来。**命令行工具** 页面列出你的技能声明需要的每个命令，以及你的 MCP 服务器启动所用的每个启动器，都在这台机器上实际检查过，有问题的排在前面。

## 声明技能需要什么 {#declare-what-a-skill-needs}

技能在 `SKILL.md` 的 frontmatter 中，用 `requires:` 列出它的命令：

```yaml
---
name: gh-triage
description: Label new GitHub issues, find duplicates and ask for missing details.
requires:
  - command: gh
    title: GitHub CLI
    min_version: "2.40"
    login_check: gh auth status
    login: gh auth login
    why: Reads and labels issues.
  - command: jq
    min_version: "1.6"
    why: Filters issue JSON.
  - uv
---
```

| 字段 | 含义 |
| --- | --- |
| `command` | 命令的裸名称，也就是在终端里敲的那个。必填。 |
| `title` | 显示名称，例如 `GitHub CLI`。 |
| `min_version` | 技能能用的最低版本，写成点分数字。要加引号——不加的话，YAML 会把 `2.40` 读成数字 `2.4`。 |
| `login_check` | **同一个命令**的一个子命令，已登录时以 0 退出，例如 `gh auth status`。 |
| `login` | 用来登录的命令。Coffer 从不运行它；[登录提示词](#logging-in)会把它告诉你的智能体。 |
| `why` | 一行说明，技能用这个命令做什么。 |

裸名称（`- uv`）表示一个没有附加条件的命令，`- "node>=20.1"` 表示带最低版本的命令；`requires: [jq, "gh>=2.40"]` 和 `requires: {commands: [...]}` 也按同样的方式读取。Coffer 用不了的条目——写的是路径而不是名称、登录检查运行的是另一个程序——会被跳过，并在命令行工具页面上显示警告，`tools:` 里不匹配任何 MCP 服务器或自定义工具分组的名字也一样（见[技能需要的工具](/zh/guides/skills#tools-a-skill-needs)）；它永远不会阻止技能被导入或投递。

Coffer 每次检查时都从技能文件夹读取 `requires:`，所以你在编辑器里改完，下一次 **重新检查** 就能读到，无需重新导入技能。这个顶层的 `requires:` 列的是命令；它和 `metadata.requires` 无关，后者是技能库用来声明[一个领域依赖哪些技能](/zh/guides/writing-skill-libraries#declared-dependencies)的。

## MCP 服务器启动所用的启动器 {#launchers-your-mcp-servers-start-with}

每个已开启、以命令方式（stdio）启动的 MCP 服务器都需要它的启动器。Coffer 把启动器列在提供它的那个命令下——`uvx` 列在 `uv` 下，`npx` 列在 `node`（Node.js）下，`bunx` 列在 `bun` 下，其他启动器（比如 `docker`）就列它自己。无需任何声明：服务器自己的命令就够了。启动器没有最低版本，也没有登录检查；从路径启动的服务器（`./run.sh`）是一个文件而不是命令，不会列出；已关闭或通过 HTTP 访问的服务器什么都不需要。

## Coffer 如何检查一个命令 {#how-coffer-checks-a-command}

每个命令一行，不管有多少技能和服务器需要它：

1. **找得到吗？** 在你真实的 `PATH` 上查找这个命令——你的登录 shell 的 `PATH`，与守护进程继承到的合并在一起——也就是你从终端启动智能体时它拿到的那个 `PATH`。只有你的 shell 会去找的位置（Homebrew、`~/.local/bin`）里装的命令也能找到。
2. **版本。** Coffer 运行 `<command> --version`，把版本和所有技能要求中**最高**的那个最低版本比较。读不出的版本显示为未知，不会被判为太旧。
3. **登录了吗？** 如果有技能声明了登录检查，Coffer 只在你点击**检查**时运行它（打开页面、以及轮询它的提醒列表都不会运行）——不经过 shell，限时 10 秒——只看它是否成功。**它的输出不读就丢弃**：登录检查可能打印你的账户名或令牌，这些都不会被保留、记录或显示。

之后每个命令的状态是 **未找到**、**版本过旧**、**未登录** 或 **就绪** 之一。结果会一直保留，直到你点 **重新检查** 或守护进程重启。

## 命令行工具页面 {#the-clis-page}

页面左边是列表，右边是你选中的命令的详情页。列表把 **需要你处理** 的——先是未找到，然后是版本过旧，再是未登录——放在 **就绪** 之上，每个命令附带它的版本或问题，以及有多少 MCP 服务器和技能需要它。详情页有两个区块。**本机情况** 显示它在哪里找到、版本与最低要求的对比、登录状态以及 Coffer 上次检查的时间。**依赖方** 列出所有用它启动的 MCP 服务器（点开进入该服务器的页面，附带它启动所用的启动器），以及所有需要它的技能和各自要求的最低版本；没人需要的命令行工具会这样说明。需要你处理的命令会在顶部的横幅里用一句大白话说明它造成的影响——“duckdb 无法启动，data-profiling 会在调用 uv 的那一步失败。”——并在旁边提供[交接](#hand-the-install-to-your-agent)。页面没有命令浏览器：工具有哪些子命令和选项，由智能体在使用它时自己去读 `--help`，所以 Coffer 既不显示也不保存。页面不显示任何安装、更新或登录命令，也没有任何要你在终端里运行的东西。

页面唯一的操作是 **重新检查**，它会重新探测每个命令（横幅里自己的 **重新检查** 只探测那一个）。**添加命令行工具** 接受一个命令名或可执行文件的路径，可选填标题、最低版本、描述和登录检查，用来检查没有任何技能或服务器声明的工具。只有你手动添加的命令行工具才有 **编辑**，以及 **⋯** 菜单里的 **移除**；移除只是让 Coffer 不再检查它，工具仍然装在这台机器上。技能或服务器需要的命令行工具，头部右侧是空的，也不能在这里移除，因为只要还有东西需要它，它就会一直列出。

技能自己的页面有一个 **依赖** 标签页，列出该技能声明的内容，每个命令都链接到它在这里的位置，需要你处理时提供同样的交接。只要有必需的命令缺失、版本过旧或未登录，**总览** 就会把它列在需要你处理的事项里，侧边栏的 **命令行工具** 入口也会显示一个计数。只有 MCP 服务器需要的启动器，在总览中只列一次，即该服务器自己的“启动器在这台机器上找不到”这一项，不会再作为命令行工具重复列出。

## 把安装交给你的智能体 {#hand-the-install-to-your-agent}

Coffer 自己不安装任何东西。人们装工具的方式五花八门——Homebrew、apt、各语言自己的包管理器、厂商提供的安装程序——合适的方式取决于机器。你的智能体能看这台机器并做出选择；它需要 Coffer 提供的只是事实。所以对缺失或版本过旧的命令，Coffer 会写一段简短的**安装提示词**：

```text
Please install the command-line tool `gh` (GitHub CLI) on this machine.

- Needed by the Coffer skills: gh-triage (version 2.40 or newer).
- This machine: macOS 15.6, arm64.

Choose the right install method for this machine.
When you are done, run `gh --version` to confirm it works.
Check with me before running anything that needs sudo or changes system settings.
If a login is needed, tell me how and I will log in myself; do not handle my credentials.
```

启动器会额外列出用它启动的服务器（`` - Needed by the MCP servers Coffer starts: duckdb (started with `uvx`). ``）。版本过旧的命令会得到同样的提示词，只是改为要求更新，并附上找到的版本和位置。提示词不写任何安装命令：选哪个是智能体的事。命令的页面和技能的 **依赖** 标签页提供一个拆分按钮**交给智能体 ▾**：

- **交给智能体**——打开一个新[对话](/zh/guides/chat)草稿，提示词已经填在输入框里；智能体和文件夹在回复框里选，默认是你上次用的。
- ▾ 菜单里的**复制提示词**——粘贴到你用的任何智能体里，终端或 IDE 都行。会弹出“已复制提示词”。

前者**在你按下发送之前，什么都不会发出去**：托管的智能体以完整权限运行，所以先读一读它将被要求做什么。这台机器上没有托管智能体时，只提供复制提示词。

智能体完成后，点 **重新检查**。

## 登录 {#logging-in}

Coffer 从不替你登录，页面也不显示任何登录命令。未登录的命令同样通过交接交给你的智能体：提示词写明失败的登录检查和技能声明的登录命令，只要求智能体告诉你该运行什么；登录由你自己运行，要求输入的内容也由你自己输入。然后点 **重新检查**。

## 在命令行上 {#on-the-command-line}

```sh
coffer cli list                 # every required command, problems first
coffer cli list --json
coffer cli show uv              # one command: path, version, login, servers and skills
coffer cli check                # probe every command again
coffer cli check gh             # probe one again
coffer cli prompt gh            # the prompt to give your agent
coffer cli prompt gh | pbcopy   # straight to the clipboard on macOS
```

`coffer cli prompt` 打印的正是页面复制的那段文字，对已就绪的命令以非零退出。全部选项见 [CLI 参考](/zh/reference/cli/cli)。

## 相关 {#related}

- [技能](/zh/guides/skills)——导入技能与 `SKILL.md` 格式。
- [编写技能库](/zh/guides/writing-skill-libraries)——组织较大的技能集。
- [技能依赖](/zh/architecture/skill-requirements)——检查与交接如何工作。
