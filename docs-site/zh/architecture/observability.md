# 可观测性

关于审计追踪和调用记录（谁做了什么，谁调用了什么），请参阅[审计与问责](/zh/architecture/audit)。

## 这解决了什么问题

一个开发者运行着一个繁忙的 vault：几十个 MCP 服务器、面向多个 agent 的 chat 会话、一个已连接的消息通道，以及周期性的 sync 运行——同时在进行。没有运维可观测性，诊断线上问题就会变得不透明：「为什么这个服务器突然开始返回错误？」「那个失败的请求、chat turn 或 sync 运行期间究竟发生了什么？」结构化日志和链路追踪关联能回答这些问题，而无需用户运行独立的监控栈。

Coffer 的方案刻意保持精简：结构化本地日志，而非 metrics 管道。所有可观测性数据都留在本机，并在 `~/.coffer/` 的备份范围内。

## 日志：structlog JSON-per-line

daemon 使用配置为 JSON 输出的 `structlog`，将日志写入 `~/.coffer/logs/`。每行日志是一个完整的 JSON 对象，具有固定的顶级键集合加上事件特定的字段：

```json
{
  "timestamp": "2026-05-20T14:23:01.123Z",
  "level": "info",
  "logger": "coffer.surfaces.http.resource",
  "event": "resource_registered",
  "trace_id": "b3d8e2f1-...",
  "resource_ref": "mcp_server:filesystem",
  "actor": "cli",
  "duration_ms": 12
}
```

一个 `contextvar` 在请求的整个异步调用栈中传递 `trace_id`。当 FastAPI handler 调用应用层服务，应用层服务调用 repository，repository 调用 ORM 时，在任意深度发出的每条日志行都与外层请求共享相同的 `trace_id`。这使得无需分布式追踪系统就能从原始日志行中重建完整的按请求追踪记录。

日志文件位于 `~/.coffer/logs/`。轮换由 Python 的 `logging.handlers.RotatingFileHandler` 处理（按大小轮换：每个文件最大 10 MB，保留 3 个备份文件）。日志与数据库一样，都在 `~/.coffer/` 的备份范围内。

日志行永远不包含密钥材料。密钥只以密文形式存于凭据存储中，其明文从不作为日志字段传递——因此不需要也不存在任何清理处理器。structlog 管道依次为：`merge_contextvars`、`add_log_level`、`TimeStamper`、`_add_trace_id`、`JSONRenderer`。

## 链路追踪关联

daemon 的每个 HTTP 响应还携带一个带有请求级别 UUID 的 `X-Coffer-Trace` header。该 UUID 出现在该请求的 daemon 结构化日志中、请求处理期间产生的任何审计条目中，以及来自该请求的任何调用记录中。关联是机械化的：从错误响应中取出 trace ID，在 `~/.coffer/logs/` 中 grep 它即可。

同一套结构化日志与 trace-id 关联如今也覆盖了 vault 的其余部分——chat turn、通道事件和 sync 运行都流经同一个由 `contextvar` 传递的 trace ID，并落在同样的 JSON 日志行中。

::: tip CLI 用法
使用 `--verbose` 标志运行 `coffer` 时，CLI 会在人类可读错误信息旁边打印 `X-Coffer-Trace` ID。对于需要将 CLI 输出与 daemon 日志关联起来的脚本化工作流，这是关键线索。
:::

## 错误：统一响应信封

所有接口面均以相同的结构返回错误：

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "No mcp_server named 'my-server'.",
    "details": {}
  }
}
```

`code` 是定义在 `domain/errors.py` 中的稳定 UPPER_SNAKE_CASE 机器可读字符串。`message` 是面向开发者的人类可读句子。`details` 字段携带结构化上下文（例如，当 kind 未找到时，已注册的 kind 名称列表；或校验错误时被违反的约束）。

## 另请参阅

- [审计与问责](/zh/architecture/audit) — 审计日志、调用日志和保留策略
- [架构参考](/zh/reference/project/architecture) — 跨层关注点表中的错误和日志条目
- [Spec 001 参考](/zh/reference/specs/001-mcp-gateway/spec) — token 鉴权和 `X-Coffer-Actor` header 语义
