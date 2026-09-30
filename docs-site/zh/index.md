---
layout: home
title: Coffer
description: Coffer 是给 AI 编程智能体用的本地优先保险库。MCP 服务器、自定义工具、技能、知识、记忆和模型提供商只配一次，Claude Code 和 Codex 共同使用，全部保存在你的机器上。

hero:
  name: Coffer
  text: 你的 AI 编程智能体的本地优先保险库
  tagline: MCP 服务器、技能、知识、记忆和模型提供商只配一次，本机的每个智能体都共享同一套。
  actions:
    - theme: brand
      text: 从这里开始
      link: /zh/start/
    - theme: alt
      text: 安装
      link: /zh/start/install
    - theme: alt
      text: GitHub
      link: https://github.com/wyx-sg/Coffer

features:
  - title: 所有智能体共用一个 MCP 端点
    details: 上游 MCP 服务器只注册一次。Claude Code 和 Codex 连到 Coffer 的同一个端点，看到的工具名是 server__tool；每个服务器暴露哪些工具、哪些智能体能用由你决定，每次调用都会记录（从不记录参数）。
    link: /zh/guides/mcp-servers
    linkText: MCP 服务器
  - title: 任何 HTTP API 都能变成自定义工具
    details: 导入一份 OpenAPI 规范或描述一个请求，这个 API 就成了智能体可调用的工具。请求由网关发出，并在出站时加上你的密钥。
    link: /zh/guides/custom-tools
    linkText: 自定义工具
  - title: 一个技能库，自动投递
    details: AgentSkills 技能文件夹只添加一次，来源可以是文件夹、压缩包或 git 仓库。Coffer 把它们链接进每个智能体的技能目录，跟踪上游更新，并告诉你技能需要的命令行工具哪些缺失或未登录。
    link: /zh/guides/skills
    linkText: 技能
  - title: 每个智能体都能读的知识
    details: 由普通 Markdown 组成的知识集，智能体用自己的文件工具读取，并通过 coffer__write 往里添加。可选的整理流程会把新材料合并进已有文档，并保留可撤销的历史。
    link: /zh/guides/knowledge
    linkText: 知识
  - title: 跨智能体共享的记忆
    details: Coffer 只读不写地读取每个智能体自己的记忆，按仓库提炼成笔记（外加一套全局笔记），再把合适的笔记交还给每个智能体——Claude Code 学到的，Codex 也知道。
    link: /zh/guides/memory
    linkText: 记忆
  - title: 模型提供商与用量
    details: 提供商只保存一次，把智能体切换过去。智能体与 Coffer 的本地模型代理通信，由代理在上游加上 API 密钥、在连接之间故障切换并统计用量，API 密钥不会写进智能体的配置。
    link: /zh/guides/providers
    linkText: 模型提供商
  - title: 在浏览器或手机上对话
    details: 在 Web 的对话页驱动 Claude Code 或 Codex，或者配对一个 Telegram、SeaTalk 机器人，在私聊、群组和线程里给智能体发消息。
    link: /zh/guides/chat
    linkText: 对话
  - title: 多台机器共用一个保险库
    details: 保险库是一个由普通文件组成、可以手工编辑的 git 仓库。让每台机器指向你自己的 git 远端；干净的合并直接应用，冲突等你决定，密钥只以密文传输。
    link: /zh/guides/vault-sync
    linkText: 保险库同步
  - title: 本地优先，AI 原生
    details: 守护进程只监听 127.0.0.1，密钥在你持有的主密钥下加密保存，每次改动都有审计。依赖你机器环境的杂事，会写成一段提示词交给你的智能体，由你决定是否发送。
    link: /zh/start/why-coffer
    linkText: 为什么用 Coffer
---

## 从这里开始 {#start-here}

第一次接触 Coffer？按顺序读这五页。全部读完大约半小时，读完后 Coffer 已经在运行，你也知道它是怎么工作的。

1. **[Coffer 是什么？](/zh/start/)** 它解决什么问题、管理什么、在哪里使用。
2. **[安装](/zh/start/install)** 把安装交给你的编程智能体，或者自己选一种安装方式。
3. **[快速上手](/zh/start/quickstart)** 大约十五分钟接入 Claude Code、注册一个 MCP 服务器并添加一个技能。
4. **[核心概念](/zh/start/concepts)** 资源、类型、生效范围和保险库：其他每一页都会用到的术语。
5. **[架构总览](/zh/architecture/)** 守护进程、网关和保险库如何配合，以及为什么这样设计。

之后，要完成某件事就去[指南](/zh/guides/)，要查某条命令就去[参考](/zh/reference/cli)。

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

## 安装 {#install}

Coffer 运行在你的 Mac 上，最快的安装方式是让你已经在用的编程智能体来装。把[让你的智能体来安装](/zh/start/install#let-your-agent-install-it)里的提示词粘贴给 Claude Code 或 Codex：智能体会阅读安装页，选出适合这台机器的方式并检查结果，动到 Coffer 自己目录以外的任何东西之前都会先问你。

如果要手动安装，[安装页](/zh/start/install)介绍了每一种方式。一行命令安装脚本、桌面应用和发布压缩包都从 GitHub 上打了标签的版本下载，适用于 Apple 芯片的 macOS：

```sh
curl -fsSL --proto '=https' --tlsv1.2 https://wyx-sg.github.io/Coffer/install.sh | sh
```

这会把 `coffer`、`coffer-daemon` 和 `coffer-mcp-shim` 装进 `~/.coffer/bin`，并把这个目录加进你的 `PATH`。在打出发布版本之前，以及在没有发布构建的机器上，请用 Python 3.12 或更高版本[从源码安装](/zh/start/install#from-source)。

## 接下来读什么 {#where-to-next}

- **[入门](/zh/start/)**：Coffer 是什么、为什么这样设计，以及一个 [15 分钟快速上手](/zh/start/quickstart)。
- **[指南](/zh/guides/)**：智能体、MCP 服务器、技能、知识、记忆、提供商、对话、消息渠道和同步的分步操作。
- **[架构](/zh/architecture/)**：守护进程、网关、资源框架和保险库如何配合，以及这样设计的原因。
- **[参考](/zh/reference/cli)**：每一条 CLI 命令、MCP 工具、配置项和错误码。
- **[参与贡献](/zh/contributing/)**：如何搭建开发环境，以及如何通过规格来修改 Coffer。
