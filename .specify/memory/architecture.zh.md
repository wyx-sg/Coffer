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
| `skill`          | [skill-manager](../../specs/skill-manager/spec.md)   | 一个主 skill 包，Coffer 可将其投递到一个或多个 agent 的 skill 目录。workspace 修订新增了未托管 skill 扫描（把手工放置的 skill adopt 进主库）。投递由 skill 自身的 `enabled` 与其 agent scope 取交集决定，任一侧变化即调谐——本行曾描述的那套 agent 侧 follow-master-library 策略已删除。                                                                                        |
| `knowledge`      | [knowledge](../../specs/knowledge/spec.md)                 | 一个 **collection**——`~/.coffer/knowledge/` 下的一个顶层文件夹，装着 markdown 文件，用户爱怎么嵌套怎么嵌套。collection 是系统唯一认得的边界，它之所以是 Resource，就是为了让框架的 per-agent scope 能授权它；没有任何东西从 cwd 推导，也没有任何东西自动开通。agent 经 MCP 读写它，人在自己的编辑器里读写它，双方触及的是同一批字节。见 [Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md)。 |
| `channel`        | [channels](../../specs/channels/spec.md)             | 一个消息 channel 绑定（Telegram、SeaTalk）。承载传输配置 + 凭据 ref 与一个默认 agent；已配对的 owner 从 IM 应用里与受管 agent 对话并接收通知。薄 adapter 架在 turn 平台的接缝之上（spec channels FR-043…FR-055），Web 端 Chat 页面作为第二个接口面也架在同一层上（spec channels FR-072…FR-078）——消息一旦到达 turn 编排器，下游就不再知道它来自哪个接口面（[Channel Adapter Framework](../../docs/decisions/channel-adapter-framework.zh.md)、[Chat 是单属主的实时镜像](../../docs/decisions/chat-single-owner-live-mirror.zh.md)）。                                                         |

知识层是**一个目录，不是一个索引**。`~/.coffer/knowledge/<collection>/` 下的
markdown 文件就是任何东西的唯一副本：没有 `documents` 表、没有 chunk 表、没有
FTS5 索引、也没有向量，因此没有任何东西需要对账，用户在自己编辑器里改过的文件
下一次读取就是活的
（[Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md)，
它取代了 Files as Truth 与 Retrieval Mode Is Internal）。

文件的**路径就是它的身份**——名字是可读的 slug，不是 ULID，因为没有索引之后，
文件名正是 agent 在 grep 结果里读到的东西。frontmatter 只带 `title`、
`description`、`actor` 和时间戳，别无其它；`description` 是必填的，因为目录就是
检索界面，一个不描述自己的文件根本找不到。collection 在自己的 `README.md` 里
描述自己，而不是在某一行数据库记录里，于是在文件夹里翻看的人看到的和目录看到
的是同一句话。

检索就是**目录加 ripgrep**。`list` 一次走一层——先是 collection，再是某个目录的
子项，每个文件带上它的标题与描述——而目录是在调用时遍历目录树生成的，从不物化。
`grep` 以字面或正则匹配调用方可读的每一个 collection；`read` 返回整个文件。没有
模式、没有排序、没有分块、没有 `top_k`，也没有 `search` 工具：没有带排序的索引
之后，它只会是 `grep` 的第二个名字。语义匹配从 embedding 转移到了「模型读目录」，
只要目录塞得进上下文就成立——到几百篇文件都还从容。

五个 MCP 工具：`coffer__list`、`coffer__grep`、`coffer__read`、`coffer__write`、
`coffer__delete`。Coffer 还会通过既有的 skill 通道**投递一个知识 skill**
（spec knowledge FR-042），因为这套设计背后的审计发现：只靠工具描述，agent 从不
主动伸手够这一层——一个月里每一次知识调用都发生在语料被建起来的那一天。没有任何
东西被注入会话，也不往任何 agent 自己的记忆里写
（[Memory via MCP](../../docs/decisions/memory-via-mcp-not-native-projection.md)）。

**tidy** 这一趟保留了下来：对单个 collection 的一次有界 agentic 改写，由
internal-engine 连接驱动，动手之前先把每个旧版本归档进隐藏的 `.history/`。它随时
可以手动触发（UI，以及 `coffer knowledge organize`）；按间隔跑它的后台 worker 由
`internal_engine_config` 上一个安装级设置控制，**默认关闭**，因为一个会在无人值守
下改写人与 agent 共享文件的东西，应该由操作者自己打开。

没有摄取界面。人添加知识的方式就是把一个 markdown 文件放进目录——文件系统就是
上传路径，下一次调用就能看见。

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
│   ├── knowledge/               # 目录与文件的值对象、错误
│   └── channel/                 # channel 配置、信封、seatalk 签名
├── application/
│   ├── resource_service.py       # 与 kind 无关的 CRUD；接受 kinds 字典
│   ├── audit_service.py
│   ├── retention_service.py
│   ├── credentials/              # 共享的 CredentialResolver (ref → secret)
│   ├── mcp/                      # MCP 特定的应用层服务
│   ├── agent/                   # agent 服务 + make_agent_kind
│   ├── skill/                   # skill 服务 + make_skill_kind
│   ├── knowledge/               # 一个服务、五个工具、tidy、skill 种子
│   ├── channel/                 # adapter 协议、配对、入站、运行时
│   └── fs/                      # 文件系统浏览服务
├── infrastructure/
│   ├── persistence/              # SQLAlchemy + Alembic (统一元数据)
│   ├── credentials/              # 加密凭据存储 + 主密钥——唯一被允许 import `keyring` 的位置
│   ├── daemon/                   # pid_lock、端口分配
│   ├── mcp/                      # 子进程、HTTP 上游客户端
│   ├── agent/                   # agent 配置文件存储
│   ├── skill/                   # 主存储、同步引擎
│   ├── knowledge/               # 路径、文件树、frontmatter、ripgrep
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
| Web UI                         | daemon                  | 构建好的前端，由 daemon 以静态文件形式在它自己的 loopback origin 上提供 —— 与 API 同源，因此不存在需要重新构建再重新安装的桌面外壳。daemon 把自己的实时 API token 注入到它提供的 `index.html` 中（`window.__COFFER_TOKEN__`，覆盖每条 SPA 路由，`no-store`），因此它提供的任何页面都已鉴权且不持久化任何东西；`coffer open` 只负责解析 daemon 当前的端口并在那里打开浏览器。随页面下发的 token 正是 loopback `Host` 校验成为强制项的原因（spec mcp-gateway FR-024 / FR-025 / FR-027，[由 daemon 把 token 放进它提供的页面里](../../docs/decisions/daemon-serves-the-token-in-the-page.zh.md)）。 |
| MCP protocol                   | daemon                  | `/mcp` HTTP/SSE 端点，承载 MCP JSON-RPC。                                                                              |
| CLI (`coffer …`)               | 短生命周期子进程        | 通过 loopback HTTP 调用 daemon。                                                                                       |
| Stdio shim (`coffer-mcp-shim`) | 每个 MCP 客户端会话一份 | `stdin/stdout ↔ daemon HTTP/SSE` 转发器；检测 daemon，否则拉起。                                                      |
| Callback listener              | daemon 拉起的子进程     | 只服务带签名的 channel webhook (`POST /seatalk/{channel}`)；loopback 端口，公网侧由用户自行运行的隧道承接 (spec channels)。 |

## 进程 (Processes)

- **`coffer-daemon`** — 长生命周期的 FastAPI 服务，监听
  `127.0.0.1:<port>` —— 端口取用户在 `~/.coffer/daemon-config.json` 里固定的那个，
  未固定则取 8000–8009 中第一个空闲端口。持有全部状态；唯一的 SQLite 写入者。
- **Stdio shim** — 短生命周期；其生命周期绑定到单个 MCP 客户端进程。
- **Callback listener** — daemon 拉起的子进程，只在
  `127.0.0.1:<callback-port>` 上服务带签名的 channel 回调路径；在任何
  SeaTalk channel 处于启用状态时运行 (spec channels，[Channel Adapter Framework](../../docs/decisions/channel-adapter-framework.md))。

两者通过 `~/.coffer/daemon.json` 发现 daemon (PID + 端口 + token，权限位
`0600`) —— 那是运行态，启动时写入、退出时删除。与它成对的
`~/.coffer/daemon-config.json` 存放 daemon 必须在**绑定端口之前**、因而也在任何
数据库存在之前就读到的设置：目前是那个可选的固定端口。见
[Detect-or-Spawn](../../docs/decisions/daemon-detect-or-spawn.md)。

## 持久化 (Persistence)

- **SQLite** 落盘于 `~/.coffer/coffer.db`，WAL 模式，单写入者。
- **SQLAlchemy 2.0 async** 作为 ORM；**Alembic** 统一管理迁移 (所有
  kind 都把各自的 ORM 模型挂到同一份 metadata 上)。迁移在 daemon 启动时执行
  (`upgrade head`)；若数据库当前 revision 不在运行版本的迁移树里 (由更新/分叉
  的版本创建)，启动会以 `DB_SCHEMA_TOO_NEW` 明确报错并快速失败，而非抛出晦涩的
  Alembic 错误。
- JSON 字段以 `TEXT` 存储，在 application 层边界由 Pydantic 校验。
- **知识层完全不拥有任何表。** 一个 collection 就是与 kind 无关的 `resources`
  表里的一行，和其它 Resource 一样，它的内容是文件。带索引的那一版用过的十一
  张表——`documents`、`chunks`、六张 `documents_fts*`、`embedding_config` 以及两
  张 scope 附表——已由 migration 0066 删除
  （[Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md)）。
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
| 文档抽取    | `DocumentExtractor` 端口 + `infrastructure/chat/document_extract.py`                         | 唯一 import 转换库的地方（MarkItDown，惰性导入且为可选依赖）。它服务的是**入站 channel 附件**（spec channels FR-030）：PDF 或 docx 以抽取出的文本抵达 agent，而不是一个不透明的路径；库缺失或抽取失败时退化为文件附件。知识层不转换任何东西——文件系统就是它的摄入界面，markdown 是它持有的唯一格式（[Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md)）。 |
| 导出 / 导入 | `application/sync/` + `infrastructure/sync/` + CLI 与 HTTP 表面 | 一次性地把仓库**导出到一个目录**、并把这样一个目录**导入回来**（spec vault-export-import，[Vault Export and Import](../../docs/decisions/vault-export-import.md)）。此外还有一个**备份远端**：一个用户自己拥有的 git 仓库，由定时 worker 导出进去、在导出结果发生变化时提交、然后推送——仅单向备份，绝不合并，绝不充当事实记录方（章程 0.5.0 例外）。它带来一行 `sync_remotes` 配置、一个背后只有单一子进程适配器的 `GitMirror` 端口，以及一个形状照搬 `RetentionWorker` 的 worker；恢复是一条显式命令，可以先检出更早的修订再导入。仍然没有墓碑、没有机器注册表、没有文件监听——那些属于收敛，而收敛并未建造。导出会镜像知识与技能的文件树、把每个配置资源序列化成一个**确定性** YAML、导出各模块自有的共享状态，并在被明确要求时**仅以密文**携带凭据（主密钥带外引导）。导入按资源 bundle-wins、从不删除、逐资源报告失败，并运行每个 kind 的导入后钩子。基于 `$HOME` 的相对路径归一化让一个 bundle 可在机器之间搬运。属横切，不是 kind。资源的 `scope`——一个 agent 名字列表（[Per-Agent Resource Scope](../../docs/decisions/per-agent-resource-scope.md)）——作为普通字段搭乘资源文档穿过导出与导入。 |
