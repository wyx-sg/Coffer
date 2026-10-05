# Coffer

[English](./README.md) · **简体中文**

<p align="center">
  <a href="https://wyx-sg.github.io/Coffer/zh/"><img alt="文档" src="https://img.shields.io/badge/docs-coffer-4353D8"></a>
  <a href="./LICENSE"><img alt="License: AGPL-3.0" src="https://img.shields.io/badge/license-AGPL--3.0-blue"></a>
  <img alt="平台：macOS" src="https://img.shields.io/badge/platform-macOS-555">
</p>

> 给 AI 编程智能体用的本地保险库。MCP 服务器、技能、知识、记忆和模型提供商只配一次，本机所有智能体共用。

Coffer 是运行在你机器上的一个守护进程，你的编程智能体都连到它（目前支持 Claude Code 和 Codex）。智能体共用的东西都以普通文件放在 `~/.coffer` 下，再由 Coffer 投递给每个智能体。你可以用 Web 界面、macOS 桌面应用，或者在手机上通过聊天渠道管理它。没有账号，也没有云端后台：守护进程只监听 `127.0.0.1`。

📖 **文档：** <https://wyx-sg.github.io/Coffer/zh/>（[English](https://wyx-sg.github.io/Coffer/)）

## 能做什么

- **一个 MCP 入口**供所有智能体使用，可按智能体控制可见范围，并记录每次调用。
- **一个技能库**，链接到每个智能体并保持最新。
- **知识和记忆**以普通文件存放，每个智能体都能读。
- **模型提供商**经由本地代理接入，代理持有密钥并统计用量。
- **密钥**加密保存；智能体能用，但永远拿不到明文。
- **聊天渠道和对话**，在手机上驱动你的智能体，再到终端里接着做。
- **保险库同步**，通过你自己的 git 远端在多台机器间同步。

## 安装

**系统要求：** git 2.40 或更高版本；一个要连接的编程智能体（Claude Code 或 Codex）。预编译构建只面向 Apple 芯片的 macOS；其他机器请从源码安装（Python 3.12+、Node.js 20）。ripgrep 可选。见[系统要求](https://wyx-sg.github.io/Coffer/zh/start/install#requirements)。

把下面这段粘贴给一个能在你机器上执行命令的编程智能体：

```text
Install Coffer on this machine by following
https://wyx-sg.github.io/Coffer/start/install — pick the install path that fits
this machine. Ask me before running anything with sudo or editing my shell
profile. When it is installed, check it with `coffer daemon status`, then tell me
which coding agents it found here. Do not handle any credentials: if a step needs
a login, tell me what to do instead.
```

也可以自己按[安装指南](https://wyx-sg.github.io/Coffer/zh/start/install)操作。

## 参与贡献

[`AGENTS.md`](./AGENTS.md) 是操作手册，[贡献指南](https://wyx-sg.github.io/Coffer/zh/contributing/)讲流程；`make verify` 是每个改动必须通过的门禁。安全问题请按[安全策略](./SECURITY.md)私下报告。

## 许可证

Copyright © 2026 Asen。Coffer 以 [GNU Affero 通用公共许可证 v3.0 或更高版本](./LICENSE)发布：你可以使用、修改和再分发它；基于它分发或通过网络提供的作品，必须以同一许可证发布并公开源码。
