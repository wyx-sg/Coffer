# Research — 001 MCP Gateway

> English: [research.md](./research.md)

库选型、备选评估，以及那些尚未到需要单独 ADR 的决策的参考文献。架构层面的关键选择各自有自己的 ADR，存放在 `docs/decisions/`；本文件记录其下一层——具体依赖、协议细节、构建期工具选择。

## Backend runtime dependencies（添加到 `backend/pyproject.toml`）

| Add                   | Version                              | Why this choice                                                                                                                                                                                                                                                  |
| --------------------- | ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `sqlalchemy[asyncio]` | `>=2.0,<3.0`                         | 异步 ORM 与 FastAPI 的 async 风格一致；SQLAlchemy 2.0 提供更干净的类型化 declarative。考虑过裸 `sqlite3` + 手写 SQL——四个 kind × CRUD + retention + audit 的手写量足以证明引入 ORM 合理。                                                                        |
| `aiosqlite`           | `>=0.20`                             | SQLAlchemy 在异步 session 下使用的异步 SQLite 驱动。                                                                                                                                                                                                             |
| `alembic`             | `>=1.13`                             | schema 迁移。考虑过 code-managed schema（直接 `Base.metadata.create_all`）——被否决，因为宪法要求 schema 变更通过 PR review 且可回滚。                                                                                                                            |
| `keyring`             | `>=25.0`                             | OS keychain 访问。仅 `infrastructure/credentials/` 引入它（Contract 4）。                                                                                                                                                                                        |
| `httpx`               | `>=0.27`                             | 已是 dev 依赖；提升为运行时。用于 HTTP MCP 上游和（测试中）FastAPI 进程内测试客户端。                                                                                                                                                                            |
| `typer`               | `>=0.12`                             | CLI 框架。考虑过 Click——Typer 包装 Click 并加入对 Pydantic 友好的类型注解驱动的参数解析，与既有 FastAPI/Pydantic 风格一致。                                                                                                                                      |
| `rich`                | `>=13.7`                             | CLI 输出渲染（Typer 推荐；`coffer mcp list` 需要表格 + tree 视图）。                                                                                                                                                                                             |
| `structlog`           | `>=24.1`                             | 结构化 JSON 日志。考虑过 stdlib `logging` + JSON formatter——被否决，因为 FR-014 要求的 trace-id 传播需要 structlog 的 contextvars 集成。                                                                                                                         |
| `mcp`                 | `>=1.0`（Anthropic 官方 Python SDK） | 用于：(a) contract test 的 oracle；(b) coffer 包装的 framing helper（`stdio_server`、`streamable_http_server`）。考虑过手写 JSON-RPC framing——被否决，SDK 已处理协议层细节（取消、progress token、initialize 协商）。                                            |
| `psutil`              | `>=5.9`                              | 孤儿子进程清理所需的 PID 存活性 + 命令行验证（[ADR-006](../../docs/decisions/ADR-006-daemon-detect-or-spawn.md)）。考虑过仅 POSIX 的 `os.kill(pid, 0)`——被否决，因为孤儿清扫需要确认该进程确实是 coffer 拉起来的 MCP 服务器，而非偶然复用了同一 PID 的无关进程。 |

## MCP protocol — concrete forwarding decisions

以下决策固化在 [ADR-004](../../docs/decisions/ADR-004-capability-state-model.md) 和 [ADR-005](../../docs/decisions/ADR-005-session-subprocess-model.md)；具体协议语义集中在此，便于实现时统一参照。

### Methods coffer forwards

| Direction         | Method                                                                                                                                           | Coffer behaviour                                                                                                                            |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------- |
| client → upstream | `initialize`                                                                                                                                     | coffer 自行响应（向客户端声明能力）。在首次需要时再向每个上游发起自己的 `initialize`。                                                      |
| client → upstream | `tools/list` `tools/call`                                                                                                                        | 通过下文 "Namespace transformation" 中的命名空间转换转发。                                                                                  |
| client → upstream | `resources/list` `resources/read` `resources/subscribe` `resources/unsubscribe`                                                                  | 通过 URI 前缀转换转发。                                                                                                                     |
| client → upstream | `prompts/list` `prompts/get`                                                                                                                     | 通过命名空间转换转发。                                                                                                                      |
| client → upstream | `roots/list` (request from upstream)                                                                                                             | 透传给下游客户端；把响应回传。                                                                                                              |
| client → upstream | `sampling/createMessage` (request from upstream)                                                                                                 | 按能力协商。若下游客户端在 initialize 时声明了 `sampling` 能力则转发；否则向上游返回 `method-not-found`。                                   |
| upstream → client | `notifications/tools/list_changed` `notifications/resources/list_changed` `notifications/prompts/list_changed` `notifications/resources/updated` | 转发给下游客户端；让 coffer 对应上游的缓存失效。                                                                                            |
| upstream → client | `notifications/progress`                                                                                                                         | 透传；保留 `progressToken`；重置对应 pending-request 的 idle 计时器（见下文 [Streaming progress decision](#streaming-progress-decision)）。 |
| upstream → client | `notifications/message` (server log)                                                                                                             | 丢弃（避免冲淹下游客户端；落到 `~/.coffer/logs/upstream-<name>.log`）。                                                                     |

### Namespace transformation

| Capability   | Wire form upstream uses | Wire form coffer presents downstream    |
| ------------ | ----------------------- | --------------------------------------- |
| Tool         | `<original_name>`       | `<server_name>__<original_name>`        |
| Prompt       | `<original_name>`       | `<server_name>__<original_name>`        |
| Resource URI | `<original_uri>`        | `coffer://<server_name>/<original_uri>` |

Tool / prompt 分隔符为 `__`（双下划线）。考虑过 `:`、`.`、`/`、`-`——这些字符在上游工具名中本就合法，会冲突。`__` 是 mcpjungle 已采用的约定；扫描公开 MCP 服务器注册表显示零工具名含 `__`。

### Streaming progress decision

公开的 MCP 网关（mcpjungle、metamcp、mcp-proxy）都保留 `progressToken` 并在进度到来时重置请求超时，但**都不会主动把 `notifications/progress` 从上游转发到下游**。已对照 `mcpjungle/internal/service/mcp/tool.go`（保留 progressToken；不转发 progress）与 `metamcp/apps/backend/src/lib/metamcp/metamcp-proxy.ts`（`resetTimeoutOnProgress: true`；不转发 progress）核对。coffer 与生态对齐：

- 在转发 `tools/call` 时保留传入的 `_meta.progressToken`
- 当上游发送 `notifications/progress` 时，重置每请求的 idle 计时器（避免长工具触发我们的 120 s 超时）
- v0 **不**把这些 progress 通知转发给下游；roadmap.md 中以非目标记录此事。

### Initialize handshake

coffer 同时扮演 server（对下游客户端）和 client（对上游服务器）。两次独立握手：

| Pair                        | Coffer's role | Capabilities coffer declares                                                               |
| --------------------------- | ------------- | ------------------------------------------------------------------------------------------ |
| downstream client ↔ coffer | server        | `tools`、`resources`、`prompts`。不声明 `logging`。`sampling` 依赖下游客户端是否声明支持。 |
| coffer ↔ each upstream     | client        | `roots`（让上游可询问）、`sampling`（透传）、`experimental: {}`                            |

协议版本：coffer 双向都声明**其捆绑的 `mcp` SDK 支持的最高版本**。版本间协商由 SDK 处理。

## SQLite configuration

每次连接打开时应用的 PRAGMA：

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
PRAGMA cache_size = -64000;
PRAGMA temp_store = MEMORY;
```

通过 SQLAlchemy 的 `event.listens_for(engine.sync_engine, "connect")` 注入，确保对每个新连接生效（WAL 是按 database 的，其余按连接）。

## Daemon discovery file format

`~/.coffer/daemon.json`（mode `0600`）:

```json
{
  "version": 1,
  "pid": 12345,
  "port": 8001,
  "token": "<32-char URL-safe random>",
  "started_at": "2026-05-20T12:34:56Z",
  "binary_path": "/Applications/Coffer.app/Contents/.../coffer-daemon"
}
```

`version` 允许未来的 schema 演进。客户端容忍未知字段。`version` 不匹配时，客户端会在重启后重新读取。

发现流程（shim、CLI 通用）：

1. 打开 `~/.coffer/daemon.json`；缺失 → spawn 流程。
2. 解析 JSON；非法 → 备份原文件 + spawn 流程。
3. 用 `psutil.pid_exists` 检查 `pid` 是否存活；不存活 → spawn 流程。
4. 验证 `psutil.Process(pid).name()` 包含 `coffer-daemon`；不匹配 → spawn 流程（PID 已被复用）。
5. 向 `127.0.0.1:port` 建立 TCP 连接；连接被拒 → spawn 流程。
6. 否则：连上了。

spawn 流程对 `~/.coffer/daemon.lock` 使用 `flock`，以序列化并发的 detect-or-spawn 竞争。

## Port allocation

范围 `8000`–`8009`。按顺序尝试，首个空闲胜出。若 10 个都被占用，daemon 拒绝启动并以明确错误退出非零。该范围选得小（便于运维），靠近习惯的默认 (`8000`)，且在 well-known 端口之外（≥1024）。

## Test fixtures

### `fake_mcp_server.py`

一个用官方 `mcp` SDK 实现的真实 MCP 服务器，行为由 CLI flag 参数化：

```bash
python -m coffer.tests.fixtures.fake_mcp_server \
  --scenario basic \
  --tools read_file write_file \
  --resources file:///tmp/example.txt \
  --crash-after-calls 0 \
  --init-delay-ms 0 \
  --notify-list-changed-after 0
```

| Scenario   | Behaviour                                                                                                          |
| ---------- | ------------------------------------------------------------------------------------------------------------------ |
| `basic`    | 返回配置好的 tool/resource/prompt；回显调用参数。                                                                  |
| `slow`     | 在响应 `initialize` 前等待 `--init-delay-ms`。                                                                     |
| `crash`    | 在 `--crash-after-calls` 次工具调用后退出。                                                                        |
| `mutating` | 在 `--notify-list-changed-after` 次调用后发送 `notifications/tools/list_changed`；后续 `tools/list` 返回不同集合。 |

存放路径：`backend/tests/fixtures/fake_mcp_server.py`。integration 测试通过一个 pytest fixture 引入它，该 fixture 产出一个 `Popen`。

## References

- [Model Context Protocol Specification 2025-06-18](https://spec.modelcontextprotocol.io/specification/2025-06-18/)
- [mcpjungle source](https://github.com/mcpjungle/MCPJungle) — token-passthrough oracle
- [metamcp source](https://github.com/metatool-ai/metamcp) — `resetTimeoutOnProgress` pattern
- [SQLite WAL documentation](https://www.sqlite.org/wal.html)
- Coffer ADRs: `docs/decisions/ADR-001` through `ADR-006`.
