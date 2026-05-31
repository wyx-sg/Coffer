# 核心概念

四个核心概念构成了 Coffer 的工作基础。理解它们，有助于你推断注册服务器、接入客户端或查看守护进程状态时背后发生了什么。

## 资源 Kind

Coffer 中每一个由用户管理的实体都是一个**资源 (Resource)**，标识形如 `<kind>:<name>`。资源框架统一处理所有 kind 的身份 (identity)、生命周期（register / update / enable / disable / delete）、审计与模式校验。

目前已发布三个 kind：

- `mcp_server`——一个已注册的上游 MCP 服务器，承载传输配置、凭据引用以及各服务器的策略。
- `agent`——一个已注册的本地 AI 编码助手（`claude_code` 或 `codex`），Coffer 可以查看和编辑它经过策展的配置文件，并可将自身的 MCP 服务器安装进去。
- `skill`——一个 AgentSkills 文件夹，Coffer 从单一的 master 副本管理它，并可将其交付到某个 agent 的配置目录。按 agent 的启用/禁用绑定在该 agent 的详情页中管理。

该框架与 kind 无关：未来新增 kind 时，无需改动核心资源机制。

## 网关（守护进程）

**网关**是运行在 `127.0.0.1:<auto-port>` 上的长生命周期 FastAPI 守护进程。它持有全部状态（存储在 `~/.coffer/coffer.db` 的 SQLite 中），聚合上游 MCP 服务器，并通过统一的 `/mcp` HTTP/SSE 端点重新暴露其工具。

由于守护进程是唯一的写入者，所有连接的客户端都能看到一致的、最新的服务器视图。通过 `coffer daemon start` 启动守护进程，其他进程通过 `~/.coffer/daemon.json`（PID + 端口 + token，权限位 `0600`）来发现它。

## Shim

`coffer-mcp-shim` 是短生命周期的 stdio 转发器，负责将一个 MCP 客户端会话桥接到守护进程。每个 MCP 客户端进程对应一个 shim 实例，其生命周期绑定到该客户端会话。

shim 启动时，检查 `~/.coffer/daemon.json`。如果守护进程未运行，shim 会自动拉起它。随后，shim 将客户端的 `stdin/stdout` 转发到守护进程的 HTTP/SSE 端点，透明地完成 stdio MCP 协议与 HTTP 之间的转换。这就是为什么客户端只需一行配置——shim 会自动处理发现与连接的全部工作。

## 本地优先

所有用户状态都驻留在用户本机。云服务——LLM、工具 API——仅作为提供方，绝不充当任何仓库状态的事实记录方。HTTP API 只绑定到 `127.0.0.1`。

这意味着你已注册的服务器列表、凭据和审计历史永远不会发送到任何厂商的云端。把用户状态复制到厂商掌控的云端是一项章程修订 (constitutional amendment)，而不是一个配置选项。
