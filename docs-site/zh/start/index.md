---
title: Coffer 是什么？
description: Coffer 是一个本地守护进程加保险库，本机所有 AI 编程智能体都连到它上面，MCP 服务器、技能、知识、记忆和模型提供商只需配置一次，所有智能体共用。
---

# Coffer 是什么？ {#what-is-coffer}

Coffer 是一个面向 AI 编程智能体的本地优先保险库。它是你机器上的一个守护进程，Claude Code 和 Codex 都连到它上面。这样 MCP 服务器、技能、知识、记忆和模型提供商只需配置一次，而不是每个智能体各配一遍。本页写给正在判断 Coffer 是否适合自己工作方式的人，介绍 Coffer 解决什么问题、管理哪些东西、在哪里使用，以及它不是什么。

## 问题所在 {#the-problem}

每个 AI 编程智能体都各自保存一份所有东西：

- **MCP 服务器。** Claude Code 从 `~/.claude.json` 读取，Codex 从 `~/.codex/config.toml` 读取。你给一个智能体加了服务器，忘了另一个，两边的列表就慢慢对不上了。
- **技能。** 每个智能体有自己的 `skills/` 目录。你在一个目录里改进了某个技能，另一个目录里的还是旧的。
- **记忆。** Claude Code 把关于你项目的笔记写进自己的记忆，Codex 也一样。两者互相读不到，同一件事你得分别教每个智能体一遍。
- **密钥和提供商。** 换一个模型网关，就得手动改每个智能体的配置，API 密钥 也要粘贴进好几个文件。

这些都存在各智能体自己的文件里，彼此之间没有任何联系。你用的智能体越多，副本就越多。

## Coffer 是什么 {#what-coffer-is}

Coffer 是**一个守护进程加一个保险库**：

- **`coffer-daemon`** 是一个常驻进程，监听 `127.0.0.1`（默认端口 38470）。它持有 Coffer 的全部状态，并提供 MCP 端点、REST API 和 Web 界面。
- **保险库**是 `~/.coffer/vault`，一个由普通文件组成的 git 仓库：每个资源一个 JSON 文件，外加技能文件夹、知识集和加密后的密钥。它旁边的 `~/.coffer` 里还放着本机专属的设置、一个历史数据库，以及 Coffer 可以重建的状态，比如记忆树。
- **`coffer-mcp-shim`** 是一个小型 stdio 程序，每个智能体把它当作普通 MCP 服务器启动。它会找到正在运行的守护进程（没有就启动一个），然后把会话转发过去。

在**智能体**页面连接 Claude Code 时，Coffer 会往 Claude Code 的 MCP 配置里写入一条 `coffer` 条目。此后，你在 Coffer 里注册的每个 MCP 服务器，Claude Code 都通过这一条目访问。

## 它管理什么 {#what-it-manages}

Coffer 管理的一切都是**资源**，共七种**类型**。每个资源都有一个不可变的 id、一个名字、一个开关（知识集和记忆分区没有开关，始终开启）和一份审计记录。

| 类型 | 是什么 | 指南 |
| --- | --- | --- |
| `mcp_server` | 一个上游 MCP 服务器（stdio 或 HTTP），由 Coffer 运行并重新暴露给每个智能体 | [MCP 服务器](/zh/guides/mcp-servers) |
| `agent` | 一个已注册的本地编程智能体：Claude Code 或 Codex | [智能体](/zh/guides/agents) |
| `skill` | 一个 [AgentSkills](https://agentskills.io) 文件夹，投递到各智能体的 `skills/` 目录 | [技能](/zh/guides/skills) |
| `knowledge` | 一个知识集：`~/.coffer/vault/knowledge/` 下存放 Markdown 文档的文件夹 | [知识](/zh/guides/knowledge) |
| `memory` | Coffer 从智能体自身记忆中生成的一个笔记分区，每个仓库一个，另加 `global` | [记忆](/zh/guides/memory) |
| `channel` | 一个 Telegram 或 SeaTalk 机器人，让你在手机上和智能体聊天 | [消息渠道](/zh/guides/channels) |
| `provider` | 一份模型提供商配置（协议、base URL、密钥），由 Coffer 写入每个智能体的配置 | [模型提供商](/zh/guides/providers) |

Coffer 还提供一些不属于资源类型的能力：加密的[密钥存储](/zh/guides/secret-store)、一个 Web 版[对话](/zh/guides/chat)页面、[活动与审计](/zh/guides/activity)记录，以及通过你自己的 git 远端进行的[保险库同步](/zh/guides/vault-sync)。

## 在哪里使用 {#where-you-use-it}

所有入口都连同一个守护进程，所以在一处做的修改会出现在其他所有地方。

| 入口 | 用途 |
| --- | --- |
| **CLI**（`coffer …`） | 一份很短的命令清单：启动、停止和检查守护进程，在带密钥的环境里运行命令，读取 Coffer 的日志。见 [CLI 参考](/zh/reference/cli)。 |
| **Web 界面** | 浏览和编辑一切。守护进程在自己的地址（`http://127.0.0.1:38470/`）上提供它，打开时你已经处于登录状态。见 [Web 界面](/zh/guides/web-ui)。 |
| **桌面应用** | 同样的界面，放在一个原生 macOS 窗口里，带 Dock 图标和菜单栏图标。它会替你启动守护进程。见[桌面应用](/zh/guides/desktop-app)。 |
| **MCP 端点** | 智能体通过 `coffer-mcp-shim` 连接的地方。智能体看到的是上游工具，外加 Coffer 自己的 `coffer__*` 工具。见[连接客户端](/zh/guides/connect-a-client)。 |
| **消息渠道** | Telegram 和 SeaTalk 机器人，让你在手机上驱动智能体、接收通知。见[消息渠道](/zh/guides/channels)。 |

## Coffer 不是什么 {#what-coffer-is-not}

- **不是云服务。** Coffer 没有托管后端，也没有账号。API 只绑定回环地址。云服务只会以你选用的模型提供商和 MCP 服务器的身份出现。如果你在几台机器之间同步保险库，走的是你自己的 git 仓库，而且每台机器都保有完整副本。
- **不是智能体。** Coffer 不是一个陪你聊天的助手。它的对话页面和消息渠道驱动的是*你的*智能体（Claude Code 或 Codex）。Coffer 只会为转写语音消息运行自己的模型，而且要你配置了才会。
- **不是编排器。** Coffer 不规划工作，也不在智能体之间传递任务。它是智能体下面的共享层：它们共用的工具、文件和设置。
- **不替代智能体自己的配置。** 智能体自己的文件仍然是事实来源。Coffer 只写入它管理的、有文档说明的条目，写入是原子的，并在 Coffer 自己的文件夹里留一份备份副本；其余内容只在需要时读取。

## 支持的平台和智能体 {#supported-platforms-and-agents}

| | 支持情况 |
| --- | --- |
| 智能体 | Claude Code（`claude_code`）和 Codex（`codex`） |
| 预编译二进制和桌面应用 | Apple 芯片（arm64）的 macOS |
| 从源码 | Python 3.12 或更高版本。发布构建和登录服务面向 macOS。 |
| MCP 客户端 | 任何能运行 stdio MCP 服务器的客户端都能用 `coffer-mcp-shim`。只有 Claude Code 和 Codex 支持一步安装、技能投递和提供商切换。 |

## 下一步 {#next-steps}

- [为什么选 Coffer](/zh/start/why-coffer)：Coffer 背后的设计决策，以及它们对你意味着什么。
- [安装](/zh/start/install)：安装 Coffer 的所有方式。
- [快速上手](/zh/start/quickstart)：用大约 15 分钟连接 Claude Code、注册一个 MCP 服务器并投递一个技能。
- [核心概念](/zh/start/concepts)：其余文档中用到的术语。
