---
title: 指南
description: Coffer 的全部任务型指南集中在一页，按你要做的事分组——接入智能体与工具、共享技能、知识和记忆、与智能体对话、使用应用，以及运维 Coffer。
---

# 指南 {#guides}

每篇指南从头到尾带你完成一件事：运行什么命令或点哪里、Coffer 会怎样响应、怎样确认它生效了。指南默认 Coffer 已经安装、守护进程正在运行。如果还没有，先看[安装](/zh/start/install)和[快速上手](/zh/start/quickstart)；指南里用到的术语见[核心概念](/zh/start/concepts)。

## 智能体与工具 {#agents-and-tools}

- [智能体](/zh/guides/agents)：注册 Claude Code 和 Codex、把它们接入 Coffer，并管理它们的配置文件、MCP 条目、插件、Hook、模型、记忆和对话记录。
- [连接客户端](/zh/guides/connect-a-client)：把 Claude Code、Codex 或任何其他 MCP 客户端指向 Coffer 的网关，并验证连接。
- [MCP 服务器](/zh/guides/mcp-servers)：一次注册上游 MCP 服务器，整理它们的工具，选择哪些智能体可以访问，并查看调用日志。
- [自定义工具](/zh/guides/custom-tools)：把 HTTP API 变成智能体可调用的工具，可以导入 OpenAPI 规范，也可以手动定义一个请求。
- [模型提供商](/zh/guides/providers)：把模型接入地址和它的 API 密钥存一次，把智能体切换过去，并选择 Coffer 自己的引擎所用的模型。
- [用量与额度](/zh/guides/usage)：智能体在 API 密钥类提供商和本地提供商上花了多少，以及订阅套餐还剩多少额度。
- [密钥存储](/zh/guides/secret-store)：Coffer 如何加密每个密钥、主密钥放在哪里，以及如何备份主密钥或把它带到另一台机器。
- [密钥](/zh/guides/secrets)：密钥页面、独立密钥、`coffer run`、审批，以及把明文文件移入存储。

## 智能体共享的内容 {#what-agents-share}

- [技能](/zh/guides/skills)：维护一个 AgentSkills 技能库，并把每个技能投递到你选定的智能体。
- [命令行工具](/zh/guides/clis)：看清技能和 MCP 服务器需要的命令行工具哪些缺失、版本太旧或未登录，并把修复交给你的智能体。
- [编写技能库](/zh/guides/writing-skill-libraries)：组织一个技能库，让同一份技能主体服务所有组织。
- [知识](/zh/guides/knowledge)：把你和智能体知道的东西存成一个个 Markdown 文件夹，每个智能体都用自己的文件工具读取。
- [记忆](/zh/guides/memory)：让 Coffer 把每个智能体学到的东西按仓库提炼成一套笔记，并在合适的时刻交还给智能体。

## 与智能体对话 {#talking-to-agents}

- [对话](/zh/guides/chat)：在 Web 对话页面和 Claude Code 或 Codex 交流，并查看或继续从消息渠道发起的对话。
- [消息渠道](/zh/guides/channels)：接入 Telegram 机器人或 SeaTalk 应用，配对到你的账号，然后在你已经在用的 IM 应用里驱动智能体。
- [Telegram](/zh/guides/channels-telegram) 和 [SeaTalk](/zh/guides/channels-seatalk)：每种消息渠道的配置步骤。

## 应用 {#apps}

- [Web 界面](/zh/guides/web-ui)：Web 界面如何提供和登录，以及侧边栏、命令面板和设置窗口如何布局。
- [桌面应用](/zh/guides/desktop-app)：macOS 应用，也是唯一能显示密钥值、备份主密钥或给出批准的地方。

## 运维 Coffer {#operating-coffer}

- [运行守护进程](/zh/guides/daemon)：启动、停止和监管守护进程，固定它的端口，设置登录时启动，并备份保险库。
- [手工编辑保险库](/zh/guides/vault-files)：用任何编辑器修改保险库里的普通文件，并读取、对比和恢复任意版本。
- [保险库同步](/zh/guides/vault-sync)：通过你自己拥有的私有 git 远端，让多台机器共用一个保险库。
- [升级已有的 Coffer](/zh/guides/upgrading)：用 `coffer migrate` 把旧的 Coffer home 迁到保险库布局。
- [活动与审计](/zh/guides/activity)：查看改了什么、智能体调用了什么、守护进程记录了什么，并控制每类记录保留多久。
- [实验功能](/zh/guides/experimental-features)：尚未就绪的能力如何发布，以及如何按机器开关它。
- [故障排查](/zh/guides/troubleshooting)和[常见问题](/zh/guides/faq)：常见问题的症状与解决办法，以及常见疑问的简答。
