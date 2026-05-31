# Coffer 架构

> English: [architecture.md](./architecture.md)

> 本文是对当前正在构建的系统的架构快照。每项选择背后的「为什么」记录
> 在 `docs/decisions/ADR-*.md` 中。本文所描述的范围，由 `roadmap.md` 中
> 处于活动状态的规范决定。

## 分层 (Layering)

```
surfaces  →  application  →  domain
                   ↓
            infrastructure
```

import 规则以及「跨层公共模块只在第二个 feature 也需要它时才抽取」这条
规则都是不变量 (invariant)，其唯一权威源是
[`constitution.md`](./constitution.md)；「层优先」代码布局背后的理由见
[ADR-002](../../docs/decisions/ADR-002-code-layout-layer-first.md)。由
`scripts/check_*.py` 与 importlinter 契约强制执行。

## 资源框架 (Resource framework, 与 kind 无关的内核)

coffer 中每一个由用户管理的实体都是一个**资源 (Resource)**，标识形如
`<kind>:<name>`。该框架统一处理：

- 身份 (identity)：`kind`、`name`，以及稳定的 `<kind>:<name>` 字符串引用
- 生命周期 (lifecycle)：register / update / enable / disable / delete
- 审计 (audit)：每一次生命周期变更连同 actor 一起入账
- 模式校验 (schema validation)：每个 kind 一份 Pydantic schema，分发逻辑
  与 kind 无关

它**不**统一调用语义 (invocation semantics)。每个 kind 自行定义其能力
(capability) 的使用方式；框架只描述一个 kind 如何被注册、如何被自描述、
如何被治理。

当前已注册的 kind：

| Kind             | Spec                                                         | 描述                                                                                                                                          |
| ---------------- | ------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `mcp_server`     | [001-mcp-gateway](../../specs/001-mcp-gateway/spec.md)       | 一个已注册的上游 (upstream) MCP 服务器。承载传输配置、凭据引用以及网关 (gateway) 所需的逐服务器策略。                                         |
| `agent`          | [004-agent-registry](../../specs/004-agent-registry/spec.md) | 一个已注册的编码 agent（Claude Code、Cursor、Codex CLI …）。承载该 agent 的本地 skill 目录及 Coffer 驱动同步所需的 agent 专属配置。           |
| `skill`          | [005-skill-manager](../../specs/005-skill-manager/spec.md)   | 一个被管理的 AgentSkills 格式 skill。规范副本放在 `~/.coffer/skills/<name>/`；各 agent 的可见性通过 `SyncEngine` 的链接 / 拷贝 binding 投递。 |
| `knowledge_base` | [006-knowledge-base](../../specs/006-knowledge-base/spec.md) | 一个本地 RAG 语料库。文档落在 `~/.coffer/kb/<name>/raw/`、索引落在 `index/`；LlamaIndex 仅出现在 infrastructure adapter 中。                  |

## 代码布局 (Code layout)

按「层优先」组织，每一层内部再按 kind 划分子目录。见
[ADR-002](../../docs/decisions/ADR-002-code-layout-layer-first.md)。

```
backend/coffer/
├── domain/                       # 与 kind 无关的实体 + kind 协议
│   ├── resource.py
│   ├── audit.py
│   └── mcp/                      # MCP 特定的值对象
├── application/
│   ├── resource_service.py       # 与 kind 无关的 CRUD；接受 kinds 字典
│   ├── audit_service.py
│   ├── retention_service.py
│   └── mcp/                      # MCP 特定的应用层服务
├── infrastructure/
│   ├── persistence/              # SQLAlchemy + Alembic (统一元数据)
│   ├── credentials/              # 钥匙串适配器——唯一被允许 import `keyring` 的位置
│   ├── daemon/                   # pid_lock、端口分配
│   └── mcp/                      # 子进程、HTTP 上游客户端
└── surfaces/
    ├── http/                     # FastAPI app + 每个 kind 的子路由
    ├── cli/                      # Typer app + 每个 kind 的子命令组
    └── shim/                     # coffer-mcp-shim 入口
```

组装入口 (`surfaces/http/app.py`、`surfaces/cli/main.py`) 显式地通过一
个 `KindModule` dataclass 装配每个 kind——没有全局注册表，也不依赖
import 副作用。

## 接口面 (Surfaces)

| Surface                        | 进程                    | 角色                                                              |
| ------------------------------ | ----------------------- | ----------------------------------------------------------------- |
| REST API                       | daemon                  | 管理面 (management plane)：`/api/v1/*`。Token + CORS 鉴权。       |
| MCP protocol                   | daemon                  | `/mcp` HTTP/SSE 端点，承载 MCP JSON-RPC。                         |
| CLI (`coffer …`)               | 短生命周期子进程        | 通过 loopback HTTP 调用 daemon。                                  |
| Stdio shim (`coffer-mcp-shim`) | 每个 MCP 客户端会话一份 | `stdin/stdout ↔ daemon HTTP/SSE` 转发器；检测 daemon，否则拉起。 |

## 进程 (Processes)

- **`coffer-daemon`** — 长生命周期的 FastAPI 服务，监听
  `127.0.0.1:<auto-port>`。持有全部状态；唯一的 SQLite 写入者。
- **Stdio shim** — 短生命周期；其生命周期绑定到单个 MCP 客户端进程。

两者通过 `~/.coffer/daemon.json` 发现 daemon (PID + 端口 + token，权限位
`0600`)。见
[ADR-006](../../docs/decisions/ADR-006-daemon-detect-or-spawn.md)。

## 持久化 (Persistence)

- **SQLite** 落盘于 `~/.coffer/coffer.db`，WAL 模式，单写入者。
- **SQLAlchemy 2.0 async** 作为 ORM；**Alembic** 统一管理迁移 (所有
  kind 都把各自的 ORM 模型挂到同一份 metadata 上)。
- JSON 字段以 `TEXT` 存储，在 application 层边界由 Pydantic 校验。
- 数据库文件、daemon 发现文件、日志与每个上游的 PID 文件都收纳在
  `~/.coffer/` 下，便于单点备份。

## 跨层关注点 (Cross-cutting concerns)

| 关注点   | 位置                                                                          | 备注                                                                                 |
| -------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| 凭据     | `infrastructure/credentials/keyring_adapter.py`                               | 唯一可 import `keyring` 的文件。配置里只放 ref；在上游进程拉起时按需物化；永不落盘。 |
| 审计     | `domain/audit.py` + `application/audit_service.py` + `audit_log` 表           | 覆盖每一次资源生命周期变更。必须带 actor (cli / api / ui / system)。                 |
| 保留策略 | `application/retention_service.py` + `retention_policies` 表 + asyncio worker | 每个日志类表注册为 `PrunableTable`；中央注册表强制执行 SQL allowlist。               |
| 错误     | `domain/errors.py` + FastAPI 全局处理器                                       | 统一 `{error: {code, message, details}}` 信封；用 `X-Coffer-Trace` header 做关联。   |
| 日志     | `structlog` 以 JSON-per-line 写入 `~/.coffer/logs/`                           | 通过 contextvar 实现按请求级别的 trace ID。                                          |
