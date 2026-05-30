# 请求全链路

::: tip 核心模型
Coffer 中的工具调用遵循一条简单的三跳路径：MCP 客户端 → 守护进程 → 上游服务器。两处复杂性分别在于入口（shim 将 stdio 转换为 HTTP/SSE）和分发（命名空间解析器将 `filesystem__read_file` 拆分为服务器 `filesystem` 和工具 `read_file`）。其余一切都是直接的 JSON-RPC 转发。理解了命名空间拆分和每会话子进程模型，就理解了完整的生命周期。
:::

## 三步摘要

1. **到达。** 工具调用以 JSON-RPC 2.0 `tools/call` 请求的形式到达守护进程的 `/mcp` HTTP/SSE 端点，请求携带命名空间化的工具名，例如 `{"method": "tools/call", "params": {"name": "filesystem__read_file", "arguments": {...}}}`。调用来自 shim（桥接 MCP 客户端的 stdio）或任何持有有效 `X-Coffer-Token` 的进程。

2. **命名空间解析。** 守护进程将 `<server-name>__<tool-name>` 形式拆分，以识别来源上游（`filesystem`）和工具的原始未加前缀名称（`read_file`）。它定位此下游客户端连接的 `MCPGatewaySession`，并在该会话内找到或惰性启动 `filesystem` 上游的子进程（或 HTTP 连接）。

3. **转发和返回。** 守护进程使用未加前缀的工具名向上游发出 JSON-RPC `tools/call` 请求，通过 ID 关联请求，等待上游响应，并将响应原样返回给下游客户端。上游的结果——无论是成功的内容负载还是工具级别的错误——都原封不动地转发。

## 端到端时序图

```mermaid
sequenceDiagram
    participant C as MCP 客户端<br/>（Claude Code / Codex）
    participant SH as coffer-mcp-shim
    participant D as coffer-daemon<br/>（/mcp 端点）
    participant NS as 命名空间解析器<br/>（守护进程会话内部）
    participant UP as 上游 MCP 服务器<br/>（filesystem 子进程）

    C->>SH: stdin: tools/call<br/>{"name":"filesystem__read_file","arguments":{...}}
    SH->>D: POST /mcp（HTTP/SSE）<br/>X-Coffer-Token: <token><br/>{"method":"tools/call","params":{"name":"filesystem__read_file",...}}
    D->>NS: resolve("filesystem__read_file")
    NS-->>D: server="filesystem", tool="read_file"<br/>检查能力是否已启用
    D->>D: 在 MCPGatewaySession 中<br/>找到或惰性启动<br/>filesystem 上游子进程
    D->>UP: JSON-RPC: tools/call<br/>{"name":"read_file","arguments":{...}}
    UP-->>D: {"result":{"content":[{"type":"text","text":"..."}]}}
    D-->>SH: SSE 事件：tools/call 响应<br/>（结果原样转发）
    SH-->>C: stdout: tools/call 响应
```

## Shim 的作用

MCP 客户端（Claude Code、Codex）期望通过 stdio 与 MCP 服务器通信：它们将 JSON-RPC 写入服务器的 stdin，并从服务器的 stdout 读取响应。然而，守护进程通过 HTTP/SSE 暴露 MCP（服务器到客户端通知使用长效 SSE 通道，客户端到服务器请求使用 HTTP POST）。stdio shim 桥接了这种差异：

- 它由 MCP 客户端作为上游 MCP 服务器启动。
- 它通过 HTTP/SSE 连接到守护进程的 `/mcp` 端点，使用来自 `~/.coffer/daemon.json` 的 token 进行鉴权。
- 它从 stdin 读取 JSON-RPC 消息并将其作为 HTTP POST 请求发送到守护进程。
- 它从守护进程读取 SSE 事件（响应和通知）并将其写回 stdout。

从 MCP 客户端的角度看，shim 与任何其他 stdio MCP 服务器无法区分。从守护进程的角度看，shim 只是另一个 HTTP 客户端——其连接创建一个 `MCPGatewaySession`。

连接后发生的 `initialize` 握手由守护进程处理，守护进程将自己呈现为包含所有已注册和已启用上游能力之并集的单一 MCP 服务器。

## 命名空间化

聚合多个上游 MCP 服务器而不发生冲突的核心设计选择是双下划线命名空间：通过 Coffer 暴露的每个工具、资源和提示都携带来源服务器的注册名称作为前缀。

| 上游服务器                 | 上游工具名            | Coffer 命名空间化名称         |
| -------------------------- | --------------------- | ----------------------------- |
| `filesystem`               | `read_file`           | `filesystem__read_file`       |
| `github`                   | `search_repositories` | `github__search_repositories` |
| `postgres`                 | `query`               | `postgres__query`             |
| `filesystem`（第二个实例） | `read_file`           | `filesystem2__read_file`      |

分隔符 `__`（双下划线）之所以被选择，是因为它在自然 MCP 工具名称中很少见，且与工具名称中按惯例使用的单下划线在视觉上有清晰区分。服务器名称来自用户分配的注册名称——与 `coffer mcp add <name>` 中使用的名称相同。此名称是稳定且持久化的；更改它需要重新注册。

**分发。** 当 `tools/call` 请求以 `filesystem__read_file` 为名到达时，守护进程在第一个 `__` 处拆分：

- `server_name = "filesystem"`
- `tool_name = "read_file"`

然后它：

1. 在数据库中查找名为 `filesystem` 的 `mcp_server` 资源并验证其已启用。
2. 检查服务器 `filesystem` 上工具 `read_file` 的能力偏好——如果用户已禁用此工具，则在联系上游之前拒绝调用，返回 `TOOL_DISABLED` 错误。
3. 找到此下游客户端的 `MCPGatewaySession`，并获取（或惰性启动）`filesystem` 上游的子进程。
4. 向上游子进程发出 `{"method": "tools/call", "params": {"name": "read_file", "arguments": ...}}`，使用新的请求 ID。
5. 通过请求 ID 关联上游的响应并将其返回给下游客户端。

**资源和提示。** 相同的命名空间化适用于此。资源 URI 包含服务器前缀。提示名称遵循相同的 `<server>__<prompt>` 惯例。分发逻辑是对称的。

## 会话模型与惰性启动

每个下游客户端连接在守护进程中创建一个 `MCPGatewaySession`（按 [ADR-005](/zh/reference/adr/ADR-005-session-subprocess-model)）。此会话拥有该连接的上游子进程。子进程不在会话创建时启动——它们在第一次需要时惰性启动，即路由到给定上游的第一个 `tools/list` 或 `tools/call` 支付一次子进程启动和 `initialize` 握手的代价。同一会话中的后续调用重用正在运行的上游。

同时连接的两个 MCP 客户端（例如 Claude Code 和 Codex 同时运行）产生两个独立的 `MCPGatewaySession` 对象，每个都有自己的上游子进程集。它们不共享任何状态。这防止了一个客户端的上游崩溃影响另一个客户端，并保持 MCP 协议正确性：每个上游 `initialize` 为每个会话新鲜协商能力，守护进程无需多路复用或伪造会话状态。

每个会话还维护每个上游能力列表的 60 秒内存缓存。缓存由 TTL 到期、来自上游的 `notifications/tools/list_changed` 通知或用户发起的能力刷新来失效。能力 schema 和描述从不写入数据库——只有用户的每能力启用/禁用偏好标志被持久化，以能力名称为键。

## 网关做什么和不做什么

::: tip 网关做什么

- 将所有已注册已启用上游 MCP 服务器的工具、资源和提示聚合到单一命名空间化的 MCP 接口面中。
- 拆分命名空间化名称并将调用路由到正确的上游。
- 在转发任何调用之前强制执行每能力启用/禁用策略。
- 在每次工具调用或资源读取时重置会话不活动超时（以便长期运行的会话在活跃使用期间保持活跃）。
- 在子进程启动时将上游的授权 token（通过凭据引用配置时）转发到上游——凭据从不被记录或存储。
- 为每次工具调用记录调用条目（时间戳、目标、持续时间、结果）——不记录参数或返回内容。
  :::

::: warning 网关不做什么
**不主动转发流式进度通知。** MCP 协议包含上游在长时间运行的工具调用期间可以发出的进度通知（`notifications/progress`）。当前 Coffer 网关不主动将这些中间进度通知转发给下游客户端。这是一个刻意的、明确的范围选择：实现正确的进度转发代理需要基于进度 token 的每通知路由，这是额外的记录管理复杂性。对于单用户、容忍延迟的用例，返回最终结果就足够了。如果你的上游在调用期间发出进度通知，客户端不会在调用中途看到它们；它将在调用完成时收到最终结果。

**不进行响应转换。** 上游的响应原样返回给下游客户端。网关不检查、重写或过滤工具结果的内容。如果上游返回二进制块，网关转发该二进制块。

**不进行参数重写。** 工具调用参数原样转发给上游。网关不添加、删除或重写参数。
:::

## 错误路径

当出错时，守护进程总是向下游客户端返回结构良好的错误。错误从不挂起或返回非结构化响应。

**统一错误信封。** 管理 API 的所有错误遵循以下结构：

```json
{
  "error": {
    "code": "TOOL_DISABLED",
    "message": "Tool filesystem__read_file is disabled",
    "details": { "server": "filesystem", "tool": "read_file" }
  }
}
```

`X-Coffer-Trace` 响应头携带关联 ID，该 ID 出现在 `~/.coffer/logs/daemon.log` 下的结构化日志中，将 HTTP 错误响应与日志中的完整请求上下文关联起来。

**具体故障模式：**

| 场景                       | 守护进程的处理方式                                                                                                    |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| 工具或能力已禁用           | 在联系上游之前以 `TOOL_DISABLED`（JSON-RPC 代码 -32000）拒绝。                                                        |
| 上游服务器在启动时不可达   | 调用返回上游不可达错误。服务器在守护进程的会话状态中被标记为不健康。后续调用触发带有有界重试的重启尝试。              |
| 上游在调用中途崩溃         | 进行中的调用返回错误。会话将上游标记为不健康。下一次对该上游的调用触发带退避的重启。                                  |
| 上游返回工具错误           | 错误原样转发给下游客户端。Coffer 不重新解释或吞没上游错误。                                                           |
| 调用超时                   | 每次调用时重置会话不活动超时。如果上游在配置的每次调用超时内没有响应，守护进程返回超时错误。                          |
| 守护进程在 shim 活跃时崩溃 | shim 检测到 HTTP/SSE 连接已关闭，向 MCP 客户端返回干净的错误（而不是挂起），并可能尝试通过 detect-or-spawn 重新连接。 |

**调用日志记录。** 每次工具调用、资源读取和提示获取都记录在 `mcp_invocations` 表中：时间戳、目标能力（命名空间化形式）、持续时间和结果（成功或错误）。参数和返回内容从不存储。这为用户提供了活动历史记录和网关 I/O 的审计跟踪，而不会因敏感参数值而产生隐私风险。

## 示例 JSON-RPC 交换

在 shim 的 stdin/stdout 边界处看到的完整往返：

**客户端 → shim → 守护进程（`tools/call` 请求）：**

```json
{
  "jsonrpc": "2.0",
  "id": 42,
  "method": "tools/call",
  "params": {
    "name": "filesystem__read_file",
    "arguments": {
      "path": "/tmp/example.txt"
    }
  }
}
```

**守护进程 → shim → 客户端（成功响应）：**

```json
{
  "jsonrpc": "2.0",
  "id": 42,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Hello, world!\n"
      }
    ]
  }
}
```

**守护进程 → shim → 客户端（能力已禁用错误）：**

```json
{
  "jsonrpc": "2.0",
  "id": 43,
  "error": {
    "code": -32000,
    "message": "Tool filesystem__write_file is disabled"
  }
}
```

守护进程不向上游的成功结果添加任何包装或额外字段。错误结构遵循 JSON-RPC 2.0，Coffer 特定的负代码在 -32000 范围内。

---

**参见：** [规约 001：MCP 网关](/zh/reference/specs/001-mcp-gateway/spec)，[ADR-005：会话子进程模型](/zh/reference/adr/ADR-005-session-subprocess-model)
