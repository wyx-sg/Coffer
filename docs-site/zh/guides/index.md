---
title: 指南
description: Coffer 的全部任务型指南集中在一页，按你要做的事分组——接入智能体与工具、共享技能、知识和记忆、与智能体对话、使用应用，以及运维 Coffer。
---

# 指南 {#guides}

一个任务一页。每篇指南都给出命令行命令和应用里的位置。指南默认 Coffer 已经安装、守护进程正在运行。如果还没有，先看[安装](/zh/start/install)和[快速上手](/zh/start/quickstart)；指南里用到的术语见[核心概念](/zh/start/concepts)。

## 智能体与工具 {#agents-and-tools}

<LinkList>

- [智能体](/zh/guides/agents) 注册 Claude Code 和 Codex，并管理它们的配置。
- [连接客户端](/zh/guides/connect-a-client) 用一个条目把智能体接入 Coffer。
- [MCP 服务器](/zh/guides/mcp-servers) 一次注册上游服务器，所有智能体共用。
- [自定义工具](/zh/guides/custom-tools) 把 HTTP API 变成工具。
- [模型提供商](/zh/guides/providers) 存一个提供商，并把智能体切换过去。
- [用量](/zh/guides/usage) 查看经过你的提供商的请求按模型、智能体或天花了多少。
- [密钥存储](/zh/guides/secret-store) 密钥如何加密，主密钥放在哪里。
- [密钥](/zh/guides/secrets) 让密钥保持加密，不进智能体配置。

</LinkList>

## 智能体共享的内容 {#what-agents-share}

<LinkList>

- [技能](/zh/guides/skills) 导入技能库并投递出去。
- [命令行工具](/zh/guides/clis) 找出缺失的命令行工具，把修复交给你的智能体。
- [编写技能库](/zh/guides/writing-skill-libraries) 组织能在智能体之间通用的技能。
- [知识](/zh/guides/knowledge) 每个智能体都能读写的 Markdown。
- [记忆](/zh/guides/memory) 共享每个智能体学到的东西。

</LinkList>

## 与智能体对话 {#talking-to-agents}

<LinkList>

- [对话](/zh/guides/chat) 在浏览器里驱动智能体。
- [消息渠道](/zh/guides/channels) 在 Telegram 或 SeaTalk 里和智能体对话。
- [Telegram](/zh/guides/channels-telegram) 配对一个 Telegram 机器人。
- [SeaTalk](/zh/guides/channels-seatalk) 配对一个 SeaTalk 机器人。

</LinkList>

## 应用 {#apps}

<LinkList>

- [Web 界面](/zh/guides/web-ui) 在浏览器里打开界面。
- [桌面应用](/zh/guides/desktop-app) 菜单栏、更新与重启。

</LinkList>

## 运维 Coffer {#operating-coffer}

<LinkList>

- [运行守护进程](/zh/guides/daemon) 启动、停止和检查守护进程。
- [手工编辑保险库](/zh/guides/vault-files) 编辑保险库里的普通文件，并恢复任意版本。
- [保险库同步](/zh/guides/vault-sync) 通过 git 让每台 Mac 共用一个保险库。
- [升级已有的 Coffer](/zh/guides/upgrading) 把旧的 Coffer home 迁到保险库布局。
- [活动与审计](/zh/guides/activity) 查看改了什么，以及每一次工具调用。
- [实验功能](/zh/guides/experimental-features) 开关尚未就绪的能力。
- [故障排查](/zh/guides/troubleshooting) 修复常见故障。
- [常见问题](/zh/guides/faq) 常见疑问的简答。

</LinkList>
