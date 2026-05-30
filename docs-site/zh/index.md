---
layout: home
hero:
  name: Coffer
  text: 本地优先的 AI agent 保险库
  tagline: 一个地方统一管理所有 MCP 服务器。配置一次,每个客户端看到的工具完全一致。
  actions:
    - theme: brand
      text: 快速开始
      link: /zh/guide/getting-started
    - theme: alt
      text: GitHub
      link: https://github.com/wyx-sg/Coffer
features:
  - title: 本地优先
    details: 所有状态都在你自己的机器上 —— 没有云账号,没有厂商锁定。
  - title: 统一接口
    details: 聚合上游 MCP 服务器,以 &lt;server&gt;__&lt;tool&gt; 带命名空间重新暴露。
  - title: 配置一次,处处可用
    details: Claude Code、Codex 及其他 MCP 客户端看到的工具完全一致。
  - title: Agent 注册表
    details: 检测并注册你的本地 AI 编码助手,编辑它们的配置文件,一键将 Coffer 安装进 Claude Code 或 Codex。
  - title: 自动发现 shim
    details: coffer-mcp-shim 自动发现(必要时拉起)守护进程,无需配置端口或 token。
  - title: CLI · Web · 桌面端
    details: 用终端、Web UI 或桌面应用来驱动网关。
---

<div style="text-align:center; margin: 2.5rem 0 1rem;">
  <img src="/screenshots/resources.png" alt="Coffer —— 一个地方统一管理所有 MCP 服务器" style="border-radius:12px; box-shadow:0 10px 40px rgba(31,27,23,.14); max-width:100%; height:auto;" />
</div>

<div style="display:flex; gap:1rem; flex-wrap:wrap; justify-content:center; margin-bottom:1rem;">
  <img src="/screenshots/server-detail.png" alt="单个服务器详情 —— 健康状态、传输方式与已发现的能力" style="border-radius:12px; box-shadow:0 10px 40px rgba(31,27,23,.14); flex:1 1 360px; min-width:0; max-width:49%; height:auto;" />
  <img src="/screenshots/observability.png" alt="审计日志 —— 对任意资源或能力的每一次生命周期变更" style="border-radius:12px; box-shadow:0 10px 40px rgba(31,27,23,.14); flex:1 1 360px; min-width:0; max-width:49%; height:auto;" />
</div>

## 工作原理

```mermaid
flowchart LR
  C["MCP 客户端<br/>Claude Code · Codex"] --> S["coffer-mcp-shim<br/>自动发现守护进程"]
  S --> D["coffer-daemon<br/>统一网关"]
  D --> U["上游 MCP 服务器"]
```

## 快速上手

```bash
coffer mcp add filesystem --stdio "npx -y @modelcontextprotocol/server-filesystem /tmp"
claude mcp add coffer coffer-mcp-shim
```

[阅读完整指南 →](/zh/guide/getting-started)
