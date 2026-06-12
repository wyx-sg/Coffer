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

| Kind         | Spec                                                         | 描述                                                                                                  |
| ------------ | ----------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `mcp_server` | [001-mcp-gateway](../../specs/001-mcp-gateway/spec.md)       | 一个已注册的上游 (upstream) MCP 服务器。承载传输配置、凭据引用以及网关 (gateway) 所需的逐服务器策略。 |
| `agent`      | [004-agent-registry](../../specs/004-agent-registry/spec.md) | 一个已注册的编码 agent（如 Claude Code）。承载其配置目录以及 Coffer-MCP 的安装状态。workspace 修订还将 agent 自身的文件呈现为多个面 (facet)——MCP entries（移除/开关/adopt 进 Coffer）、plugins（开关/Codex 卸载）、目录型配置项（逐子文件编辑）——全部在读取时从文件派生，绝不落库。 |
| `skill`      | [005-skill-manager](../../specs/005-skill-manager/spec.md)   | 一个主 skill 包，Coffer 可将其投递到一个或多个 agent 的 skill 目录。workspace 修订新增了未托管 skill 扫描（把手工放置的 skill adopt 进主库）以及逐 agent 的 follow-master-library 策略（开关 + 排除列表，存于 agent 配置），由同步引擎负责调和。 |

## 代码布局 (Code layout)

按「层优先」组织，每一层内部再按 kind 划分子目录。见
[ADR-002](../../docs/decisions/ADR-002-code-layout-layer-first.md)。

```
backend/coffer/
├── domain/                       # 与 kind 无关的实体 + kind 协议
│   ├── resource.py               # Resource、Kind、ResourceRef
│   ├── kind_module.py            # KindModule 组装入口数据载体
│   ├── audit.py
│   ├── mcp/                      # MCP 特定的值对象
│   ├── agent/                   # agent 特定的值对象 (config 等)
│   └── skill/                   # skill 特定的值对象
├── application/
│   ├── resource_service.py       # 与 kind 无关的 CRUD；接受 kinds 字典
│   ├── audit_service.py
│   ├── retention_service.py
│   ├── mcp/                      # MCP 特定的应用层服务
│   ├── agent/                   # agent 服务 + make_agent_kind
│   ├── skill/                   # skill 服务 + make_skill_kind
│   └── fs/                      # 文件系统浏览服务
├── infrastructure/
│   ├── persistence/              # SQLAlchemy + Alembic (统一元数据)
│   ├── credentials/              # 钥匙串适配器——唯一被允许 import `keyring` 的位置
│   ├── daemon/                   # pid_lock、端口分配
│   ├── mcp/                      # 子进程、HTTP 上游客户端
│   ├── agent/                   # agent 配置文件存储
│   └── skill/                   # 主存储、源拉取器、同步引擎
└── surfaces/
    ├── http/                     # FastAPI app + 每个 kind 的子路由 (含 agent/skill/fs 路由)
    ├── cli/                      # Typer app + 每个 kind 的子命令组
    └── shim/                     # coffer-mcp-shim 入口
```

组装入口 (`surfaces/http/app.py`、`surfaces/cli/main.py`) 显式地装配每个
kind——没有全局注册表，也不依赖 import 副作用。每个 kind 的
`make_*_kind()` 工厂 (如 `make_mcp_kind`、`make_agent_kind`、
`make_skill_kind`) 返回一个 frozen `Kind` (`domain/resource.py`)，组装入口
直接把它填入每个 app 的 `app.state.kinds` 字典 (`kind_name → Kind`)：
`app_mcp_composition.py` 设置 `"mcp_server"`，`agent_skill_wiring.py` 设置
`"agent"` 与 `"skill"`。`ResourceService` 读取该字典做与 kind 无关的分发。
一个 kind 贡献的 surface 层制品 (HTTP 路由、Typer 组) 由 `KindModule`
dataclass (`domain/kind_module.py`) 承载，它通过 `Any` 类型字段引用它们，
使 domain 层永不 import 它们。

FastAPI 依赖提供者 (`surfaces/http/dependencies.py`) 是一组基于模块级全局
单例的 `set_*` / `get_*` 函数对——组装入口在启动时对每个 `set_*` 调用一
次；对应的 `get_*` 是 `Depends()` 目标，若在初始化前访问会报错。其中 kind
特定的服务被标注为 `Any`，以避免与 kind 无关的内核 import kind 模块
(Contract 6)。

## 接口面 (Surfaces)

| Surface                        | 进程                    | 角色                                                                                             |
| ------------------------------ | ----------------------- | ------------------------------------------------------------------------------------------------ |
| REST API                       | daemon                  | 管理面 (management plane)：`/api/v1/*`。Token + CORS 鉴权。                                      |
| MCP protocol                   | daemon                  | `/mcp` HTTP/SSE 端点，承载 MCP JSON-RPC。                                                        |
| CLI (`coffer …`)               | 短生命周期子进程        | 通过 loopback HTTP 调用 daemon。                                                                 |
| Stdio shim (`coffer-mcp-shim`) | 每个 MCP 客户端会话一份 | `stdin/stdout ↔ daemon HTTP/SSE` 转发器；检测 daemon，否则拉起。                                |

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
  kind 都把各自的 ORM 模型挂到同一份 metadata 上)。迁移在 daemon 启动时执行
  (`upgrade head`)；若数据库当前 revision 不在运行版本的迁移树里 (由更新/分叉
  的版本创建)，启动会以 `DB_SCHEMA_TOO_NEW` 明确报错并快速失败，而非抛出晦涩的
  Alembic 错误。
- JSON 字段以 `TEXT` 存储，在 application 层边界由 Pydantic 校验。
- 数据库文件、daemon 发现文件、日志与每个上游的 PID 文件都收纳在
  `~/.coffer/` 下，便于单点备份。

## 跨层关注点 (Cross-cutting concerns)

| 关注点   | 位置                                                                          | 备注                                                                                 |
| -------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| 凭据     | `infrastructure/credentials/keyring_adapter.py`                               | 唯一可 import `keyring` 的文件。**daemon 是唯一 keychain 所有者**:所有 surface(桌面、CLI、shim)都通过 daemon 的 `/api/v1/keychain` 路由访问 keychain —— CLI 不在进程内直接访问(spec 006)。配置里只放 ref；在上游进程拉起时按需物化；永不落盘。 |
| 审计     | `domain/audit.py` + `application/audit_service.py` + `audit_log` 表           | 覆盖每一次资源生命周期变更。必须带 actor (cli / api / ui / system)。                 |
| 保留策略 | `application/retention_service.py` + `retention_policies` 表 + asyncio worker | 每个日志类表注册为 `PrunableTable`；中央注册表强制执行 SQL allowlist。               |
| 错误     | `domain/errors.py` + FastAPI 全局处理器                                       | 统一 `{error: {code, message, details}}` 信封；用 `X-Coffer-Trace` header 做关联。   |
| 日志     | `structlog` 以 JSON-per-line 写入 `~/.coffer/logs/`                           | 通过 contextvar 实现按请求级别的 trace ID。                                          |
