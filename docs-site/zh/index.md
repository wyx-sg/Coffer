---
layout: home
hero:
  name: Coffer
  text: 本地优先的 AI agent 保险库
  tagline: 为你机器上的每个 AI agent 提供一个安全、共享的统一接口。工具、技能、知识库、记忆只配置一次,每个 agent 看到的都是同一个保险库。一切都不离开你的机器。
  actions:
    - theme: brand
      text: 快速开始
      link: /zh/guide/getting-started
    - theme: alt
      text: GitHub
      link: https://github.com/wyx-sg/Coffer
features:
  - title: 本地优先 · 加密存储
    details: 所有状态都在你自己的机器上 —— 没有云账号,没有厂商锁定。密钥以 Fernet 加密静态存储,由你掌控的主密钥保护。
  - title: 一个 MCP 端点
    details: 聚合每一个上游 MCP 服务器,以 &lt;server&gt;__&lt;tool&gt; 带命名空间重新暴露。Claude Code、Codex 及任何 MCP 客户端看到的工具完全一致。
  - title: 技能 · 知识 · 记忆
    details: 维护一份主技能库并投递给每个 agent;整理可被 agent 检索的知识库;让所有 agent 共享同一份记忆。
  - title: 与任意 agent 对话
    details: 在 Web UI 里,与 Coffer 内置 agent 对话 —— 或驱动 Claude Code、Codex —— 流式输出。
  - title: 随处触达你的 agent
    details: 配对一个 Telegram 或 SeaTalk 渠道,在手机上与 agent 对话。换新机器?把整个保险库导出到一个目录,搬过去再导入即可。
  - title: CLI · Web UI
    details: 用终端,或用守护进程自己提供的本地 Web UI 驱动整个保险库 —— 一句 `coffer open` 就能进去。agent 自动发现守护进程,无需配置端口或 token。
---

## 工作原理

```mermaid
flowchart LR
  subgraph You["你"]
    UI["CLI · Web UI"]
    IM["Telegram · SeaTalk"]
  end
  A["AI agents<br/>Claude Code · Codex"] -->|MCP| D
  UI --> D
  IM --> D
  D["coffer-daemon<br/>保险库:MCP 网关 · 技能 · 知识 · 记忆 · agents · 对话"]
  D -->|带命名空间的工具| U["上游 MCP 服务器"]
  D -->|对话| L["LLM 提供方"]
  D -->|导出 / 导入| G["你自己搬运的目录"]
```

Coffer 是一个常驻的本地守护进程,持有你的保险库。MCP 网关只是其中一部分:每个 AI agent 通过一个自动发现的端点接入,看到同一批工具、技能、知识与记忆 —— 同时密钥保持加密,一切都不离开你的机器。搬到你自己的另一台机器上是一个明确的动作:把保险库导出到一个目录,搬过去,再导入。

## 快速上手

```bash
# 聚合一个上游 MCP 服务器,然后让 Claude Code 指向 Coffer。
coffer mcp add filesystem --stdio "npx -y @modelcontextprotocol/server-filesystem /tmp"
claude mcp add coffer coffer-mcp-shim

# 整理一个知识库和一个共享技能 —— 你的 agent 会自动获取。
coffer kb create handbook
coffer skill import ./my-skill

# 在终端里与 Coffer 内置 agent 对话。
coffer chat -m "我有哪些 MCP 服务器和知识库?"
```

[阅读完整指南 →](/zh/guide/getting-started)
