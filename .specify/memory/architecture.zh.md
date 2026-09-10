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
[Layer-First Code Layout](../../docs/decisions/code-layout-layer-first.md)。由
`scripts/check_*.py` 与 importlinter 契约强制执行。

## 资源框架 (Resource framework, 与 kind 无关的内核)

coffer 中每一个由用户管理的实体都是一个**资源 (Resource)**，标识形如
`<kind>:<name>`。该框架统一处理：

- 身份 (identity)：`kind`、`name`，以及稳定的 `<kind>:<name>` 字符串引用
- 生命周期 (lifecycle)：register / update / enable / disable / delete
- 审计 (audit)：每一次生命周期变更连同 actor 一起入账
- 模式校验 (schema validation)：每个 kind 一份 Pydantic schema，分发逻辑
  与 kind 无关
- 作用域 (scope)：可选的按 agent 激活列表，由框架统一拥有；每个 kind 自行
  声明是否支持 scope，并各自拥有自己的执行点；已注册但不激活
  (registered-but-inactive) 语义 ——
  [Per-Agent Resource Scope](../../docs/decisions/per-agent-resource-scope.md)

它**不**统一调用语义 (invocation semantics)。每个 kind 自行定义其能力
(capability) 的使用方式；框架只描述一个 kind 如何被注册、如何被自描述、
如何被治理。

当前已注册的 kind：

| Kind             | Spec                                                         | 描述                                                                                                                                                                                                                                                                                                                                    |
| ---------------- | ------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `mcp_server`     | [mcp-gateway](../../specs/mcp-gateway/spec.md)       | 一个已注册的上游 (upstream) MCP 服务器。承载传输配置、凭据引用以及网关 (gateway) 所需的逐服务器策略。                                                                                                                                                                                                                                    |
| `agent`          | [agent-registry](../../specs/agent-registry/spec.md) | 一个已注册的编码 agent（如 Claude Code）。承载其配置目录以及 Coffer-MCP 的安装状态。workspace 修订还将 agent 自身的文件呈现为多个**只读**面 (facet)——MCP entries（只列出，唯一的写是 adopt 进 Coffer）、plugins（只列出）、目录型配置项（逐子文件编辑）——全部在读取时从文件派生，绝不落库。Coffer 不再为了移除、开关或卸载某个条目而写入别的工具的私有配置：plugin 的开关/卸载面与 MCP entry 的移除/开关面已删除，`agent_plugin_toggled`、`agent_plugin_uninstalled`、`agent_mcp_entry_removed` 三个审计事件也随之移除。                                                     |
| `skill`          | [skill-manager](../../specs/skill-manager/spec.md)   | 一个主 skill 包，Coffer 可将其投递到一个或多个 agent 的 skill 目录。workspace 修订新增了未托管 skill 扫描（把手工放置的 skill adopt 进主库）以及逐 agent 的 follow-master-library 策略（开关 + 排除列表，存于 agent 配置），由同步引擎负责调和。                                                                                        |
| `knowledge`      | [knowledge](../../specs/knowledge/spec.md)                 | 知识层——把 agent 所知道的一切收进一个 kind。scope 直接从资源名读出：`global` 与 `project-<ULID>`（由 cwd 的 git 根解析而来）在首次使用时自动开通，其他名字则是用户刻意创建的集合，绝不自动开通。单一存储根 `~/.coffer/knowledge/<scope>/`，下分两条 lane —— `notes/`（agent 或用户写下的内容，`coffer__write` 落这里）与 `docs/`（上传的文档，已归一为 markdown）—— 另有一个隐藏的 `.history/` 存放整理覆盖前的旧版本，以及一个隐藏的 `.raw/` 存放上传的原件。agent 经 MCP 既读也写；markdown 文件是事实，SQLite 是可重建索引。见 [Files as Truth](../../docs/decisions/files-as-truth-sqlite-retrieval.md) + [One Shared Knowledge Store](../../docs/decisions/agent-native-shared-memory.md)。 |
| `channel`        | [channels](../../specs/channels/spec.md)             | 一个消息 channel 绑定（Telegram、SeaTalk）。承载传输配置 + 凭据 ref 与一个默认 agent；已配对的 owner 从 IM 应用里与聊天平台的 agent 对话、应答审批提示并接收通知。薄 adapter 架在 turn 平台的接缝之上（spec channels FR-043…FR-055）（[Channel Adapter Framework](../../docs/decisions/channel-adapter-framework.md)）。                                                         |

知识层就是**一个基底 (substrate)**：**落盘的 markdown 文件是事实源；SQLite 是
可重建索引**（`coffer reindex` 据文件重建）。它一直都是同一个基底——`documents`、
`chunks`、FTS5 与 sqlite-vec 从一开始就是共用的，分成两副的只是门面（一个
`memory` kind 与一个 `knowledge_base` kind），直到 **2026-09-10** 两者合并成这一个
kind。一个落库的 lane 判别字段 `documents.lane`（`notes` | `docs`）记录某条
索引行归哪个写入方所有——note 数与文档数按 lane 分别统计——但检索刻意横跨两条
lane，因为统一检索正是这次合并的意义所在。分类的那根轴就是人真正会区分的两件
事：谁写下的，和谁上传的。除此之外没有别的 lane —— 早先 `knowledge/inbox/` 到主题
文档的梯度，以及 `rules/`、`handoff/`、`superseded/`，已于 **2026-09-11** 退役；
`coffer__set_handoff` 与 `coffer__resume` 随交接 lane 一起退役，因此这一层对外只有
六个工具：`coffer__search`、`coffer__grep`、`coffer__read`、`coffer__list`、
`coffer__write`、`coffer__delete`。

`notes/` 的可读性由**定期整理**维持：一趟有界的 agentic 流程，合并重复的 note、把
它们重写成主题文档，任何覆盖或合并之前先把旧版本复制进 `.history/`。它由一个
形状照抄 `RetentionWorker` 的后台 worker 驱动——开机跑一趟补齐，之后按间隔执行——
未配置 internal model 时空转，也可从 UI 或 `coffer knowledge organize` 手动触发。
每趟整理写进 Coffer 自己的审计日志；不再有 per-scope 的变更记录文件。

摄取把任意格式转成 markdown，藏在 infrastructure 的一个 `MarkdownConverter` 端口
背后（默认 `markitdown[docx,pdf,pptx,xls,xlsx]`），原件留在 `.raw/` 里作出处，
随后分块、跟踪外部来源（`check-sources` / `update-source`）并重建索引。检索模式
——`grep`（直接扫原始文件）、`keyword`（FTS5 + `bm25()`）、`vector`（sqlite-vec）
与 `hybrid`——是**内部引擎细节**，不是调用方要做的选择
（[Retrieval Mode Is Internal](../../docs/decisions/retrieval-mode-is-internal.zh.md)）。
逐 scope 的配置不带任何 embedding 字段：embedding 经安装级配置解析，一个 scope 只
要在检索模式里列出 `vector` 就算选用了向量检索。基底与检索的决策见
[Files as Truth](../../docs/decisions/files-as-truth-sqlite-retrieval.md) 与
[One Shared Knowledge Store](../../docs/decisions/agent-native-shared-memory.md)；它们取代了
LlamaIndex 与 mem0 两个引擎。agent 只经 MCP 访问该层——写进
agent 配置文件的原生投影已由
[Memory via MCP](../../docs/decisions/memory-via-mcp-not-native-projection.zh.md)
退役。

## 代码布局 (Code layout)

按「层优先」组织，每一层内部再按 kind 划分子目录。见
[Layer-First Code Layout](../../docs/decisions/code-layout-layer-first.md)。

```
backend/coffer/
├── domain/                       # 与 kind 无关的实体 + kind 协议
│   ├── resource.py               # Resource、Kind、ResourceRef
│   ├── kind_module.py            # KindModule 组装入口数据载体
│   ├── audit.py
│   ├── mcp/                      # MCP 特定的值对象
│   ├── agent/                   # agent 特定的值对象 (config 等)
│   ├── skill/                   # skill 特定的值对象
│   ├── knowledge/               # scope、lane、entry、document、retrieval 值对象
│   └── channel/                 # channel 配置、信封、seatalk 签名
├── application/
│   ├── resource_service.py       # 与 kind 无关的 CRUD；接受 kinds 字典
│   ├── audit_service.py
│   ├── retention_service.py
│   ├── credentials/              # 共享的 CredentialResolver (ref → secret)
│   ├── mcp/                      # MCP 特定的应用层服务
│   ├── agent/                   # agent 服务 + make_agent_kind
│   ├── skill/                   # skill 服务 + make_skill_kind
│   ├── knowledge/               # knowledge 服务 + make_knowledge_kind
│   ├── channel/                 # adapter 协议、配对、入站、运行时
│   └── fs/                      # 文件系统浏览服务
├── infrastructure/
│   ├── persistence/              # SQLAlchemy + Alembic (统一元数据)
│   ├── credentials/              # 加密凭据存储 + 主密钥——唯一被允许 import `keyring` 的位置
│   ├── daemon/                   # pid_lock、端口分配
│   ├── mcp/                      # 子进程、HTTP 上游客户端
│   ├── agent/                   # agent 配置文件存储
│   ├── skill/                   # 主存储、同步引擎
│   ├── knowledge/               # 文件树、converter、分块、FTS5 + sqlite-vec 索引
│   └── channel/                 # telegram/seatalk 传输、peer 仓储、渲染
└── surfaces/
    ├── http/                     # FastAPI app + 每个 kind 的子路由 (含 agent/skill/fs 路由)
    ├── cli/                      # Typer app + 每个 kind 的子命令组
    ├── shim/                     # coffer-mcp-shim 入口
    └── callback/                 # channel 回调监听器 (独立进程)
```

组装入口 (`surfaces/http/app.py`、`surfaces/cli/main.py`) 显式地装配全部五个
kind——没有全局注册表，也不依赖 import 副作用。每个 kind 的
`make_*_kind()` 工厂 (`make_mcp_kind`、`make_agent_kind`、`make_skill_kind`、
`make_knowledge_kind`、`make_channel_kind`) 返回一个 frozen
`Kind` (`domain/resource.py`)，组装入口直接把它填入每个 app 的
`app.state.kinds` 字典 (`kind_name → Kind`)：`app_mcp_composition.py` 设置
`"mcp_server"`，`agent_skill_wiring.py` 设置 `"agent"` 与 `"skill"`，
`knowledge_wiring.py` 设置 `"knowledge"`，`channel_wiring.py` 设置
`"channel"`。`ResourceService` 读取该字典做与 kind 无关的分发。
一个 kind 贡献的 surface 层制品 (HTTP 路由、Typer 组) 由 `KindModule`
dataclass (`domain/kind_module.py`) 承载，它通过 `Any` 类型字段引用它们，
使 domain 层永不 import 它们。

FastAPI 依赖提供者 (`surfaces/http/dependencies.py`) 是一组基于模块级全局
单例的 `set_*` / `get_*` 函数对——组装入口在启动时对每个 `set_*` 调用一
次；对应的 `get_*` 是 `Depends()` 目标，若在初始化前访问会报错。其中 kind
特定的服务被标注为 `Any`，以避免与 kind 无关的内核 import kind 模块
(Contract 6)。

## 接口面 (Surfaces)

| Surface                        | 进程                    | 角色                                                                                                                   |
| ------------------------------ | ----------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| REST API                       | daemon                  | 管理面 (management plane)：`/api/v1/*`。Token 鉴权；默认同源 (same-origin)，`COFFER_DEV_CORS` 可放行 Vite dev origin。 |
| Web UI                         | daemon                  | 构建好的前端，由 daemon 以静态文件形式在它自己的 loopback origin 上提供 —— 与 API 同源，因此不存在需要重新构建再重新安装的桌面外壳。`coffer open` 铸造一个一次性短时效 code，在该 origin 上打开浏览器并把 code 放在 URL fragment 里，页面再用它换取 API token（spec mcp-gateway FR-024 / FR-025）。 |
| MCP protocol                   | daemon                  | `/mcp` HTTP/SSE 端点，承载 MCP JSON-RPC。                                                                              |
| CLI (`coffer …`)               | 短生命周期子进程        | 通过 loopback HTTP 调用 daemon。                                                                                       |
| Stdio shim (`coffer-mcp-shim`) | 每个 MCP 客户端会话一份 | `stdin/stdout ↔ daemon HTTP/SSE` 转发器；检测 daemon，否则拉起。                                                      |
| Callback listener              | daemon 拉起的子进程     | 只服务带签名的 channel webhook (`POST /seatalk/{channel}`)；loopback 端口，公网侧由用户自行运行的隧道承接 (spec channels)。 |

## 进程 (Processes)

- **`coffer-daemon`** — 长生命周期的 FastAPI 服务，监听
  `127.0.0.1:<auto-port>`。持有全部状态；唯一的 SQLite 写入者。
- **Stdio shim** — 短生命周期；其生命周期绑定到单个 MCP 客户端进程。
- **Callback listener** — daemon 拉起的子进程，只在
  `127.0.0.1:<callback-port>` 上服务带签名的 channel 回调路径；在任何
  SeaTalk channel 处于启用状态时运行 (spec channels，[Channel Adapter Framework](../../docs/decisions/channel-adapter-framework.md))。

两者通过 `~/.coffer/daemon.json` 发现 daemon (PID + 端口 + token，权限位
`0600`)。见
[Detect-or-Spawn](../../docs/decisions/daemon-detect-or-spawn.md)。

## 持久化 (Persistence)

- **SQLite** 落盘于 `~/.coffer/coffer.db`，WAL 模式，单写入者。
- **SQLAlchemy 2.0 async** 作为 ORM；**Alembic** 统一管理迁移 (所有
  kind 都把各自的 ORM 模型挂到同一份 metadata 上)。迁移在 daemon 启动时执行
  (`upgrade head`)；若数据库当前 revision 不在运行版本的迁移树里 (由更新/分叉
  的版本创建)，启动会以 `DB_SCHEMA_TOO_NEW` 明确报错并快速失败，而非抛出晦涩的
  Alembic 错误。
- JSON 字段以 `TEXT` 存储，在 application 层边界由 Pydantic 校验。
- **知识基底索引就在同一个 `coffer.db` 里：** SQLite **FTS5**
  （常规 FTS5 表，chunk 文本在索引内部存一份，`bm25()` 关键词排序）+
  **sqlite-vec**（对 chunk embedding 做向量 KNN）。没有独立的
  chroma / LlamaIndex / mem0 store ——
  `~/.coffer/knowledge/<scope>/` 下的 markdown 文件才是事实；DB（含 FTS 索引）可据其重建
  （[Files as Truth](../../docs/decisions/files-as-truth-sqlite-retrieval.md)）。
- 数据库文件、daemon 发现文件、日志、knowledge 文件树与每个上游的 PID 文件
  都收纳在 `~/.coffer/` 下，便于单点备份。

## 跨层关注点 (Cross-cutting concerns)

| 关注点      | 位置                                                                                         | 备注                                                                                                                                                                                                                                                                                                                                                                                                                                |
| ----------- | -------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 凭据        | `infrastructure/credentials/`(`encrypted_store.py`、`master_key.py`、`keyring_adapter.py`）  | 密钥只以 Fernet 密文形式存于 `credentials` 表；主密钥（默认 `0600` 文件，opt-in 时存于操作系统钥匙串）与 legacy 迁移是唯一的 `keyring` 使用方。**daemon 是唯一凭据存储所有者**:所有 surface(Web UI、CLI、shim)都通过 daemon 的 `/api/v1/credentials` 路由访问密钥，并通过 `/api/v1/settings/credentials` 切换主密钥存储位置 —— CLI 不在进程内直接访问存储（[Envelope-Encrypted Credentials](../../docs/decisions/envelope-encrypted-credential-store.zh.md)）。配置里只放 ref；在上游进程拉起时按需物化（解密）；明文永不落盘。 |
| 审计        | `domain/audit.py` + `application/audit_service.py` + `audit_log` 表                          | 覆盖每一次资源生命周期变更。必须带 actor (cli / api / ui / system)。                                                                                                                                                                                                                                                                                                                                                                |
| 保留策略    | `application/retention_service.py` + `retention_policies` 表 + asyncio worker                | 每个日志类表注册为 `PrunableTable`；中央注册表强制执行 SQL allowlist。                                                                                                                                                                                                                                                                                                                                                              |
| 错误        | `domain/errors.py` + FastAPI 全局处理器                                                      | 统一 `{error: {code, message, details}}` 信封；用 `X-Coffer-Trace` header 做关联。                                                                                                                                                                                                                                                                                                                                                  |
| 日志        | `structlog` 以 JSON-per-line 写入 `~/.coffer/logs/`                                          | 通过 contextvar 实现按请求级别的 trace ID。                                                                                                                                                                                                                                                                                                                                                                                         |
| Converter   | `MarkdownConverter` 端口 + 逐格式 adapter，落在 `infrastructure/`                            | 唯一 import converter 库的地方（文本/源码走 passthrough、csv 走专用转换器、其余走 MarkItDown；新引擎可按格式插拔）。any-format → markdown。                                                                                                                                                                                                                                                                                         |
| 导出 / 导入 | `application/sync/` + `infrastructure/sync/` + CLI 与 HTTP 表面 | 一次性地把仓库**导出到一个目录**、并把这样一个目录**导入回来**（spec vault-export-import，[Vault Export and Import](../../docs/decisions/vault-export-import.md)）。没有 git、没有远程、没有工作区、没有后台 worker、没有墓碑，也没有自己的表。导出会镜像知识与技能的文件树、把每个配置资源序列化成一个**确定性** YAML、导出各模块自有的共享状态，并在被明确要求时**仅以密文**携带凭据（主密钥带外引导）。导入按资源 bundle-wins、从不删除、逐资源报告失败，并运行每个 kind 的导入后钩子。基于 `$HOME` 的相对路径归一化让一个 bundle 可在机器之间搬运。属横切，不是 kind。资源的 `scope`——一个 agent 名字列表（[Per-Agent Resource Scope](../../docs/decisions/per-agent-resource-scope.md)）——作为普通字段搭乘资源文档穿过导出与导入。 |
