---
title: 指南
description: Coffer 的全部任务型指南集中在一页，按你要做的事分组——接入智能体与工具、共享技能、知识和记忆、与智能体对话、使用应用，以及运维 Coffer。
---

# 指南 {#guides}

一个任务一页。每篇指南都给出命令行命令和应用里的位置。指南默认 Coffer 已经安装、守护进程正在运行。如果还没有，先看[安装](/zh/start/install)和[快速上手](/zh/start/quickstart)；指南里用到的术语见[核心概念](/zh/start/concepts)。

## 智能体与工具 {#agents-and-tools}

<LinkList :items="[
{ title: '智能体', desc: '注册 Claude Code 和 Codex，并管理它们的配置。', link: '/zh/guides/agents' },
{ title: '连接客户端', desc: '用一个条目把智能体接入 Coffer。', link: '/zh/guides/connect-a-client' },
{ title: 'MCP 服务器', desc: '一次注册上游服务器，所有智能体共用。', link: '/zh/guides/mcp-servers' },
{ title: '自定义工具', desc: '把 HTTP API 变成工具。', link: '/zh/guides/custom-tools' },
{ title: '模型提供商', desc: '存一个提供商，并把智能体切换过去。', link: '/zh/guides/providers' },
{ title: '用量与额度', desc: '查看智能体花了多少、还剩多少额度。', link: '/zh/guides/usage' },
{ title: '密钥存储', desc: '密钥如何加密，主密钥放在哪里。', link: '/zh/guides/secret-store' },
{ title: '密钥', desc: '让密钥保持加密，不进智能体配置。', link: '/zh/guides/secrets' }
]" />

## 智能体共享的内容 {#what-agents-share}

<LinkList :items="[
{ title: '技能', desc: '导入技能库并投递出去。', link: '/zh/guides/skills' },
{ title: '命令行工具', desc: '找出缺失的命令行工具，把修复交给你的智能体。', link: '/zh/guides/clis' },
{ title: '编写技能库', desc: '组织能在智能体之间通用的技能。', link: '/zh/guides/writing-skill-libraries' },
{ title: '知识', desc: '每个智能体都能读写的 Markdown。', link: '/zh/guides/knowledge' },
{ title: '记忆', desc: '共享每个智能体学到的东西。', link: '/zh/guides/memory' }
]" />

## 与智能体对话 {#talking-to-agents}

<LinkList :items="[
{ title: '对话', desc: '在浏览器里驱动智能体。', link: '/zh/guides/chat' },
{ title: '消息渠道', desc: '在 Telegram 或 SeaTalk 里和智能体对话。', link: '/zh/guides/channels' },
{ title: 'Telegram', desc: '配对一个 Telegram 机器人。', link: '/zh/guides/channels-telegram' },
{ title: 'SeaTalk', desc: '配对一个 SeaTalk 机器人。', link: '/zh/guides/channels-seatalk' }
]" />

## 应用 {#apps}

<LinkList :items="[
{ title: 'Web 界面', desc: '在浏览器里打开界面。', link: '/zh/guides/web-ui' },
{ title: '桌面应用', desc: '菜单栏、更新与重启。', link: '/zh/guides/desktop-app' }
]" />

## 运维 Coffer {#operating-coffer}

<LinkList :items="[
{ title: '运行守护进程', desc: '启动、停止和检查守护进程。', link: '/zh/guides/daemon' },
{ title: '手工编辑保险库', desc: '编辑保险库里的普通文件，并恢复任意版本。', link: '/zh/guides/vault-files' },
{ title: '保险库同步', desc: '通过 git 让每台 Mac 共用一个保险库。', link: '/zh/guides/vault-sync' },
{ title: '升级已有的 Coffer', desc: '把旧的 Coffer home 迁到保险库布局。', link: '/zh/guides/upgrading' },
{ title: '活动与审计', desc: '查看改了什么，以及每一次工具调用。', link: '/zh/guides/activity' },
{ title: '实验功能', desc: '开关尚未就绪的能力。', link: '/zh/guides/experimental-features' },
{ title: '故障排查', desc: '修复常见故障。', link: '/zh/guides/troubleshooting' },
{ title: '常见问题', desc: '常见疑问的简答。', link: '/zh/guides/faq' }
]" />
