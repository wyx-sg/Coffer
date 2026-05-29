# ADR-006: Daemon 探测或拉起模式

> English: [ADR-006-daemon-detect-or-spawn.md](./ADR-006-daemon-detect-or-spawn.md)

**Status**: 已采纳 (Accepted)
**Date**: 2026-05-20
**Deciders**: Yuxing Wu
**Related**: spec `001-mcp-gateway` (FR-017, FR-018), [ADR-005](ADR-005-session-subprocess-model.md)

## 背景

Coffer 有多个入口都需要一个正在运行的 daemon：

- `coffer-mcp-shim` —— 每次 MCP 客户端 (Claude Code、Cursor) 启动时由其拉起。
- `coffer …` CLI —— 由用户临时调用。

daemon 必须**比任一单一入口活得更久**：用户期望某个 MCP 客户端的 shim 不会因为
另一个客户端的 shim 退出而死掉，也期望一次 `coffer` CLI 调用返回后 daemon 仍
继续运行。

问题在于：daemon 如何被启动、客户端如何发现它、其生命周期归谁所有。

## 决定

**探测或拉起 (detect-or-spawn) 模式，daemon 作为独立进程。**

- daemon 是绑定在 `127.0.0.1:<port>` 的独立进程，`<port>` 在启动时选定
  （默认 8000；被占用则在小范围内退而求其次取下一个空闲端口）。
- 启动时 daemon 写入 `~/.coffer/daemon.json` (mode `0600`)，内容为
  `{pid, port, token, started_at}`。
- shim 和 CLI 都使用同一个 `detect-or-spawn` 辅助函数：
  1. 读取 `~/.coffer/daemon.json`。
  2. 若文件存在且 PID 存活，则连接。
  3. 否则将 `coffer-daemon` 作为 detached 进程拉起（stdio 重定向到
     `~/.coffer/logs/daemon.log`），短暂等待 `daemon.json` 出现后再连接。
- daemon 不自动关闭。只有在显式执行 `coffer daemon stop` 或系统关机时才退出。
- 所有客户端在每个请求中通过 `X-Coffer-Token` header 携带 `daemon.json`
  中的 token。

## 后果

**正面**

- 任何入口都能引导 daemon —— 用户永远不会遇到「没有 daemon 在跑」的摩擦。
- daemon 在启动它的那个入口退出后仍然存活。一次无关的 `coffer` 命令返回后，
  基于 shim 的 MCP 客户端依然工作；某个客户端的 shim 退出也不会把 daemon
  连同其他客户端一起拖垮。
- 不需要任何特权安装。建立方式是「执行任意一次 `coffer` 命令」。
- 单一发现文件让客户端在端口变化时保持一致 —— 若 8000 被占而 daemon 选了 8001，
  所有客户端都读到同一个答案。

**负面**

- 「daemon 归谁所有」是隐式的（最先探测到缺失的那个）。引导者的清理责任由
  「daemon 不随引导者退出而退出」予以缓解。
- 如果两个客户端同时探测到缺失并同时 spawn，存在竞态。缓解方式：写入时对
  `daemon.json` 加 `flock`；同时 daemon 自身在发现已有合法 `daemon.json`
  且 PID 存活时拒绝启动。
- 由子入口（shim）自动拉起一个长生存周期进程并不常见 —— 尤其在 Windows
  上用户可能短暂看到命令窗口。缓解方式：Windows 上以
  `subprocess.CREATE_NO_WINDOW` 分离；POSIX 上使用 `os.setsid()`。

**运维后续**

- daemon 崩溃后残留的上游 MCP 子进程在下次 daemon 启动时通过
  `~/.coffer/upstream-pids/` 清理。

## 备选方案

**手动 daemon（用户在做任何事之前先 `coffer daemon start`）**。被否决。
体验糟糕：强制用户在每次与 MCP 客户端交互前记住一个准备步骤。

**由某个入口拥有 daemon（该入口退出则 daemon 死亡）**。被否决。这样只要那个
碰巧启动了 daemon 的入口退出，shim 就会损坏。detect-or-spawn 的意义正在于：
每个入口都是同一份长生存周期状态之上互相独立的入口。

**不用发现文件 —— 固定端口 + 环境共享 token**。被否决。开发机上的端口冲突
（8000 被大量使用）以及共享密钥轮换都需要某种配置或发现文件。
将所有信息放进一个文件比把状态拆分到多处更简洁。
