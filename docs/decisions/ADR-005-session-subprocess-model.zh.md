# ADR-005: 每个下游客户端会话一套独立的上游子进程

> English: [ADR-005-session-subprocess-model.md](./ADR-005-session-subprocess-model.md)

**Status**: 已采纳 (Accepted)
**Date**: 2026-05-20
**Deciders**: Yuxing Wu
**Related**: spec `001-mcp-gateway` (Edge Cases — concurrent clients), [ADR-006](ADR-006-daemon-detect-or-spawn.md)

## 背景

当两个 MCP 客户端（例如 Claude Code 和 Cursor）同时连接到 Coffer 时，
gateway 必须决定如何管理上游 MCP 服务器子进程：

- 所有下游会话 (session) 共享同一上游子进程，由 gateway 多路复用 MCP 协议
  流量。
- 每个下游会话拥有一套独立的上游子进程，互不共享。

MCP 是按 session 的协议：每条连接都以 `initialize` 握手开始，协商协议版本与
客户端 / 服务端能力 (capability)，之后服务端可能携带会话级状态（订阅、通知
路由、progress token）。让一个服务端被多个客户端共享，意味着 gateway 要在
MCP 之上重新实现 session 语义 —— 这不在协议的设计范围内。

*不共享*的代价是 N × M 个子进程（N 个并发客户端会话 × M 个注册上游）。
在单用户开发机上 N 极少超过 3，多数 stdio 形态的 MCP 服务器启动时间不到
一秒，内存占用不到 100 MB。

## 决定

**每个下游客户端会话一套独立的上游子进程。**

- 下游客户端连接时（通过 HTTP/SSE 端点或经由 `coffer-mcp-shim`），创建一个
  `MCPGatewaySession`。
- 在该 session 内，每个上游 MCP 服务器**懒加载** —— 在首次需要时（第一次
  路由到它的 `tools/list` 或调用）才拉起，而非 session 启动时一次性拉起。
- 该 session 拥有的所有子进程在 session 销毁时被回收。
- session 之间不共享子进程状态。

## 后果

**正面**

- 保持 MCP 协议正确性：每个 session 对应一个上游 session，无需多路复用层。
- 实现简洁：gateway 在每个 `(session, upstream)` 对上通过单一上游连接转发
  JSON-RPC，请求 id 关联简单直接。
- 故障隔离：某个客户端 session 中的上游崩溃不会影响另一客户端的 session。
- 能力发现缓存（见 [ADR-004](ADR-004-capability-state-model.md)）天然按 session 维度，与子进程连接的
  per-session 生命周期完美契合。

**负面**

- 资源代价随 N × M 增长。3 个并发客户端 + 10 个上游 = 至多 30 个子进程。
  对当前用户群（单个开发者）而言可以接受。若假设性地走向群集部署，需要
  重新评估多路复用层。
- 首次调用的冷启动延迟：每个 session 在首次访问某个上游时要承担一次 spawn +
  initialize 时间。由懒加载缓解（只有实际被用到的上游才付出这笔成本）。

**运维后续**

- 子进程监管：spawn、健康检查、回退重启 (respawn-with-backoff)、回收，
  都在 session 层实现。daemon 崩溃后的孤儿进程处理是另一关注点
  （PID 文件在下次 daemon 启动时清理）。

## 备选方案

**共享上游 + gateway 内做 session 多路复用**。被否决。

- MCP 的 per-session `initialize` 握手和能力协商并非为扇出设计：要把两个声明
  了不同能力的客户端服务于同一上游 session，会逼迫 gateway 在中途伪造或代理
  状态。
- 通知路由（`tools/list_changed` 应送给哪个客户端？`progress` 对应哪个请求
  id？）会变成一个非平凡的簿记层。
- 预估实现工作量：约为 per-session 方案的 3 倍，且存在大量微妙 bug 的风险
  （客户端之间通知泄漏、能力不匹配）。
- 资源节省（1 个子进程 vs N 个）在单用户规模下无法支撑这种复杂度。

**预热式拉起（session 开始就启动所有注册上游）**。被否决。

- 当客户端在一个 session 里只用到 10 个注册服务器中的 2 个时是浪费。
- 在用户感知最强的 session 启动阶段加入明显延迟。
- 懒加载 + 60 秒能力缓存能在不付预热代价的前提下达成同样的稳态。

**daemon 级别的单例子进程池（跨所有 session 共享）**。在精神上等同于多路
复用；否决理由相同。此外，daemon 重启会一次性失效所有 session 状态，
而 per-session 模型在隔离性上更胜一筹。
