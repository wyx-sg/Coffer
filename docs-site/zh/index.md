---
layout: home
title: Coffer
description: Coffer 是给 AI 编程智能体用的本地优先保险库。它给 Claude Code 和 Codex 一个 MCP 端点、一个技能库，以及共享的知识、记忆和模型提供商，全部保存在你的机器上。

hero:
  name: Coffer
  text: 你的 AI 编程智能体的本地保险库
  tagline: MCP 服务器、技能、知识和模型提供商只配一次，本机的每个智能体都用同一套配置。
  actions:
    - theme: brand
      text: 开始使用
      link: /zh/start/quickstart
    - theme: alt
      text: Coffer 是什么？
      link: /zh/start/
    - theme: alt
      text: GitHub
      link: https://github.com/wyx-sg/Coffer

features:
  - title: 所有智能体共用一个 MCP 端点
    details: 上游 MCP 服务器只注册一次，也可以把 HTTP API 变成自定义工具。Claude Code 和 Codex 连到 Coffer 的同一个端点，看到的工具名是 server__tool，哪些智能体能用哪些工具由你决定。
    link: /zh/guides/mcp-servers
    linkText: MCP 服务器
  - title: 一个技能库，自动投递
    details: AgentSkills 格式的技能文件夹只导入一次。Coffer 把它链接进每个智能体的技能目录，保持链接正确，并由你选择哪些智能体拿到它。
    link: /zh/guides/skills
    linkText: 技能
  - title: 知识与记忆，彼此共享
    details: 用 Markdown 写知识，每个智能体都用自己的文件工具去读。Coffer 还会读取每个智能体自己的记忆，整理成其他智能体也能用的笔记。
    link: /zh/guides/knowledge
    linkText: 知识
  - title: 模型提供商只切换一次
    details: 保存一份提供商配置（接入地址和 API 密钥），把智能体切换过去。智能体与 Coffer 的本地模型代理通信，由代理在上游加上 API 密钥、在连接之间故障切换并统计用量，API 密钥不会写进智能体的配置。
    link: /zh/guides/providers
    linkText: 模型提供商
  - title: 在浏览器或手机上对话
    details: 在 Web 的对话页驱动 Claude Code 或 Codex，或者配对一个 Telegram、SeaTalk 机器人，随时随地给智能体发消息。
    link: /zh/guides/chat
    linkText: 对话
  - title: 本地优先，AI 原生
    details: 守护进程只监听 127.0.0.1，密钥以密文保存、主密钥由你持有，多台机器通过你自己的 git 远端同步。依赖你机器环境的杂事，会写成一段提示词交给你的智能体，由你决定何时发送。
    link: /zh/start/why-coffer
    linkText: 为什么用 Coffer
---

## 工作原理 {#how-it-works}

Coffer 是运行在你机器上的一个守护进程，保险库放在 `~/.coffer`。智能体通过一个很小的 stdio shim 连到它，Coffer 会把这个 shim 写进每个智能体的 MCP 配置。你可以用命令行、Web 界面、桌面应用或消息渠道管理它，它们连的都是同一个守护进程。

```mermaid
flowchart LR
  subgraph agents["你的智能体"]
    CC["Claude Code"]
    CX["Codex"]
  end
  subgraph surfaces["你的操作入口"]
    CLI["coffer 命令行"]
    WEB["Web 界面与桌面应用"]
    IM["Telegram 与 SeaTalk"]
  end
  CC --> SHIM["coffer-mcp-shim"]
  CX --> SHIM
  SHIM -->|"经回环地址的 MCP"| D["coffer-daemon"]
  CLI -->|"REST"| D
  WEB -->|"REST"| D
  IM --> D
  D <--> V[("~/.coffer 保险库")]
  D --> UP["上游 MCP 服务器"]
  D --> PR["模型提供商"]
  D -.->|"技能链接、切换提供商"| agents
```

- **网关。** 每个智能体会话都有自己的一组上游 MCP 服务器。Coffer 以 `<server>__<tool>` 为前缀列出它们的工具，旁边是 Coffer 自己的 `coffer__*` 工具。
- **投递到智能体。** 技能以目录链接的形式出现在每个智能体的 `skills/` 文件夹里。切换提供商时，Coffer 把智能体自己的配置指向 Coffer 的本地模型代理。Coffer 从不把智能体的文件复制进自己的存储。
- **保险库。** 配置和内容以普通文件的形式放在 `~/.coffer/vault`，这是一个 git 仓库：每个资源一个 JSON 文件、技能文件夹、知识集，以及密文形式的密钥。任何文件都可以手工编辑，每次改动都有历史。审计日志这类历史记录放在它旁边的 `runs.db` 里。

[架构总览](/zh/architecture/)会逐一深入讲解各个部分。

## 一行命令安装 {#install-in-one-line}

在 Apple 芯片的 Mac 上：

```sh
curl -fsSL --proto '=https' --tlsv1.2 https://wyx-sg.github.io/Coffer/install.sh | sh
```

这会把 `coffer`、`coffer-daemon` 和 `coffer-mcp-shim` 装进 `~/.coffer/bin`，并把这个目录加进你的 `PATH`。[安装指南](/zh/start/install)还介绍了桌面应用、从源码构建、升级和卸载。

::: warning 还没有正式发布的版本
安装脚本从 GitHub 上打了标签的正式版本下载，而目前还没有发布，所以现在请[从源码安装](/zh/start/install#from-source)。
:::

## 接下来读什么 {#where-to-next}

- **[入门](/zh/start/)**：Coffer 是什么、为什么这样设计，以及一个 [15 分钟快速上手](/zh/start/quickstart)。
- **[指南](/zh/guides/agents)**：智能体、MCP 服务器、技能、知识、记忆、提供商、对话、消息渠道和同步的分步操作。
- **[架构](/zh/architecture/)**：守护进程、网关、资源框架和保险库如何配合，以及这样设计的原因。
- **[参考](/zh/reference/cli)**：每一条 CLI 命令、MCP 工具、配置项和错误码。
- **[参与贡献](/zh/contributing/)**：如何搭建开发环境，以及如何通过规格来修改 Coffer。
