# Data Model —— 004 Agent Registry

> English: [data-model.md](./data-model.md)

agent registry 的实体、字段、关系与存储说明。建立在 spec 001 引入的 kind-agnostic Resource 框架之上——agent 是通用 `resources` 表中的行，因此 spec 004 不新增任何自有表。

## Domain 实体 (`backend/coffer/domain/agent/`)

### `AgentType` (`domain/agent/types.py`)

字符串值的 enum（`StrEnum`）。v1 恰好支持两个产品；每个值都同时覆盖该产品的
CLI 与 app/IDE 形态，二者共享同一个配置目录。

| 值            | 显示名       | 默认 `config_dir`（POSIX 展开） | skill 投递到       |
| ------------- | ------------ | ------------------------------- | ------------------ |
| `claude_code` | Claude Code  | `~/.claude`                     | `~/.claude/skills` |
| `codex`       | OpenAI Codex | `~/.codex`                      | `~/.codex/skills`  |

`claude_desktop` 与 `cursor` 在 v1 中被有意排除（见 spec.md「关于 agent 类型的
说明」）。将来若要加入，需要一个新 enum 值、一个 `detect_marker` 与一份配置文件
allowlist。

每个 enum 值携带：

- `display_name: str`
- `default_name() -> str`（稳定的按类型默认资源名——下划线变连字符，如 `claude_code` → `claude-code`；用户未显式提供名称时使用）
- `default_config_dir() -> Path`（该类型的标准配置目录，按宿主平台计算——`~/.claude` / `~/.codex`；用户未显式提供 `config_dir` 时使用）
- `detect_marker() -> Path`（发现（discovery）时检查的路径；通常就是 `default_config_dir` 本身）

配置文件 allowlist 与 skill 投递目标（`<config_dir>/skills`）都基于 agent 解析后的 `config_dir` 解析。

### `AgentConfig` (`domain/agent/config.py`)

Pydantic v2 `BaseModel`。注册到 `ResourceService` 的 kind 专属 config schema。

| 字段         | 类型           | 说明                                                             |
| ------------ | -------------- | ---------------------------------------------------------------- |
| `type`       | `AgentType`    | 必填；enum 值                                                    |
| `config_dir` | `Path \| None` | 可选的绝对路径覆盖；读取时默认回退到 `type.default_config_dir()` |

skill 投递到 `<config_dir>/skills`；配置文件 allowlist 基于 `config_dir` 解析。每个解析后的 `config_dir` 至多只能有一个 agent。

校验器：

- `config_dir`（设置时）必须是绝对路径；注册时会自动创建 `<config_dir>/skills` 子目录，随后解析后的 `config_dir` 必须是一个已存在、可写的目录。
- `config_dir` 不得位于 `/etc`、`/usr`、`/bin`、`/sbin`、`/System`（POSIX）或 `C:\Windows`、`C:\Program Files`（Windows）之内。
- `model_config = ConfigDict(extra="forbid")`，拒绝未知字段。
- 一个 `model_validator(mode="before")` 会从 dict 输入中剔除遗留的 `auto_detected` 键，使早期持久化了该（现已移除）标志的旧行在 `extra="forbid"` 下仍能加载。

### `ConfigFileFormat` + 配置文件 allowlist (`domain/agent/config_files.py`)

纯 domain 模块（除基于 `os.environ` 的路径构造外无 I/O，与 `types.py` 同样的
模式）。定义每个 agent 类型对外暴露、可查看/编辑的精选配置文件集合。

`ConfigFileFormat` —— `json`、`toml`、`markdown`、`text` 的 `StrEnum`。驱动保存时
的校验：`json` 用 `json.loads` 解析，`toml` 用 `tomllib.loads`；`markdown` 与
`text` 永远合法。

`ConfigFileSpec` —— 描述一个 allowlist 内文件的 frozen dataclass：

| 字段           | 类型               | 说明                                                |
| -------------- | ------------------ | --------------------------------------------------- |
| `key`          | `str`              | API/CLI 寻址用的稳定标识（如 `settings`、`memory`） |
| `display_name` | `str`              | 人类可读标签（如「User settings」）                 |
| `path`         | `Path`             | 解析后的绝对路径（按宿主计算）                      |
| `format`       | `ConfigFileFormat` | 决定校验方式                                        |

`config_files_for(agent_type: AgentType) -> tuple[ConfigFileSpec, ...]` 返回精选
allowlist。v1：

| Agent         | `key`            | 路径                            | 格式       |
| ------------- | ---------------- | ------------------------------- | ---------- |
| `claude_code` | `settings`       | `~/.claude/settings.json`       | `json`     |
| `claude_code` | `settings_local` | `~/.claude/settings.local.json` | `json`     |
| `claude_code` | `global`         | `~/.claude.json`                | `json`     |
| `claude_code` | `memory`         | `~/.claude/CLAUDE.md`           | `markdown` |
| `codex`       | `config`         | `~/.codex/config.toml`          | `toml`     |
| `codex`       | `memory`         | `~/.codex/AGENTS.md`            | `markdown` |

`~/.codex/auth.json` 被有意排除（凭据/状态，而非手工编辑的配置）。`~/.claude.json`
被纳入（按产品决策），并由每次写入的 `.bak` 备份保护。

`validate_content(fmt: ConfigFileFormat, text: str) -> None` 对结构化格式的非法
内容抛出 `ConfigFileFormatInvalid`。

`spec_for(agent_type, key) -> ConfigFileSpec` 在 `key` 不在该类型 allowlist 内时
抛出 `ConfigFileNotAllowed`（驱动 404 + 不访问文件系统的规则）。

### Coffer MCP 条目 (`domain/agent/mcp_install.py`)

纯 domain 模块，在 agent 的 MCP 配置**文本**中构建/检测/移除 `coffer`
MCP-server 条目，不触碰文件系统。

- `COFFER_SERVER_KEY = "coffer"`。
- `apply_install(fmt, text, shim_path) -> str` —— 返回插入/更新了 `coffer` stdio
  条目后的新文件文本。`json`（Claude Code `~/.claude.json`）：
  `mcpServers.coffer = {"command": shim_path}`。`toml`（Codex `config.toml`）：
  `[mcp_servers.coffer]\ncommand = shim_path`，通过 `tomlkit` 编辑以保留用户的
  其它表与注释。
- `apply_uninstall(fmt, text) -> str` —— 返回移除了 `coffer` 条目后的新文本（条目
  不存在时为空操作）。
- `is_installed(fmt, text) -> bool` —— 是否存在 `coffer` 条目。

每个类型的 MCP 配置文件本身就是一个 allowlist 内的配置文件（Claude Code 的
`global`，Codex 的 `config`）。Coffer-MCP 安装/卸载操作会走 `AgentMcpService`
下描述的原子写入/备份路径写入它；它也可以像任何其它 allowlist 内配置文件一样，
通过 `AgentConfigFileService.write_file` 被编辑。两条路径共用同一套原子写入 + `.bak`
机制。

## SQLite schema 增量

**无。** `agent` kind 不需要自有表——agent 是通用 `resources` 表（来自 spec 001
的 kind-agnostic Resource 框架）中的行，而发现（discovery）是只读的，也没有抑制
列表需要持久化。因此 head 迁移版本号保持在 **0004**；spec 004 不新增任何 Alembic
迁移。

**配置文件与 Coffer-MCP 安装状态不持久化到 SQLite**——agent 磁盘上的配置文件即
为事实来源。安装状态通过按需读取相关配置文件派生得出。

### 复用已有表

- `resources`：新增 `kind='agent'` 的行。无 schema 变更。
- `audit_log`：写入新的事件类型（见下）。无 schema 变更。

## 新增的 Audit 事件类型

加入 `AuditEventType`（`domain/audit.py`）：

| 值                          | 触发时机                                                                        |
| --------------------------- | ------------------------------------------------------------------------------- |
| `agent_config_file_written` | 通过 Coffer 保存了一个配置文件（原子写入 + `.bak`）；details 携带配置文件 `key` |
| `agent_mcp_installed`       | Coffer 的 MCP server 条目被写入某个 agent 的 MCP 配置                           |
| `agent_mcp_uninstalled`     | Coffer 的 MCP server 条目被从某个 agent 的 MCP 配置中移除                       |

FR-011 要求的生命周期步骤——注册、更新与移除——通过已有的 kind-agnostic `resource_created`、`resource_updated`、`resource_deleted` 事件发出（每条都携带对应的 `agent:<name>` 引用）。这些不新增 `agent_*` 重复事件；surfaces 按 `kind='agent'` 加 kind-agnostic 事件类型过滤。一次成功的配置文件保存会发出 `agent_config_file_written`（引用 `agent:<name>`，details 为 `{key}`）。agent 没有启用/禁用的概念，且发现（discovery）是只读的、不注册任何内容，因此二者都不发出任何 audit 事件。

## Application 服务契约 (`backend/coffer/application/agent/`)

### `AgentService`

| 方法                                                                              | 用途                                                                                                                                                                                                 |
| --------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `register(type, name=None, config_dir=None, description=None, actor) -> Resource` | 自动创建 `<config_dir>/skills`、校验解析后的 `config_dir`，再委派给 `ResourceService.register(kind='agent', ...)`。`name` 可选——省略时取 `type.default_name()`（如 `claude_code` → `claude-code`）。 |
| `update_config_dir(ref, new_path, actor) -> Resource`                             | 委派给 `ResourceService.update_config`。                                                                                                                                                             |
| `list() -> list[Resource]`                                                        | 委派给 `ResourceService.list(kind='agent')`。                                                                                                                                                        |
| `remove(ref, actor) -> None`                                                      | 通过 `ResourceService.delete` 删除。移除并非永久——没有抑制列表，因此该 agent 会在下次扫描时重新作为发现候选项出现。                                                                                  |

### `AutoDetectService`

| 方法                                 | 用途                                                                                                                                                                                                                                              |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `discover() -> list[AgentCandidate]` | 只读扫描：检查每个 `AgentType` 的安装标记；对任何标记存在但尚未在 `resources` 中注册的类型，产出一个 `AgentCandidate`。不注册、不写入任何内容。**不**在 daemon 启动时调用；由 `GET /api/v1/agents/candidates` 与 `coffer agent detect` 按需调用。 |

`AgentCandidate` 是一个派生的值对象（不是 SQLite 实体，从不存储）：一个已安装但
未注册、用户可确认以注册的 agent。字段：`type`（`AgentType`）、`display_name`、
`config_dir`（该类型的默认配置目录，字符串）、`default_skill_dir`（该类型的默认
skill 目录，字符串）与 `suggested_name`（即该类型的 `default_name()`）。
被移除的 agent 会在下次扫描时重新作为候选项出现——没有抑制列表。

### `BrowseService` (`application/fs/browse_service.py`)

为选择自定义 `config_dir` 的 Web 文件夹选择器提供支撑（FR-023/FR-024）。只读：给定
一个目录路径（默认用户主目录），列出该目录的直接子目录——绝不返回文件内容。

| 方法                                  | 用途                                                                                                                                          |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `browse(path=None) -> FsBrowseResult` | 解析 `path`（默认主目录）；返回其解析后路径、其父目录（文件系统根处为 `None`）与其直接子目录。不可读或不存在的路径 → 报错，绝不返回部分列表。 |

桌面应用使用 OS 原生目录对话框；Web 通过 `GET /api/v1/fs/browse` 使用这个
daemon 支撑的浏览器，由前端组件 `FolderPicker.tsx` 呈现。

### `AgentConfigFileService` (`application/agent/config_file_service.py`)

把 agent 解析为其 `AgentType`，再通过 `ConfigFileStorePort` 在该类型的配置文件
allowlist 上操作。

| 方法                                                         | 用途                                                                                                                                                                                                                                           |
| ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `list_files(name) -> list[ConfigFileInfo]`                   | 对该 agent 类型的每个 `ConfigFileSpec`，返回 key、显示名、路径、格式、`exists`，存在时附带大小 + mtime。                                                                                                                                       |
| `read_file(name, key) -> ConfigFileContent`                  | 解析 `spec_for(type, key)`；返回内容 + 格式 + `exists`。文件不存在 → 空内容、`exists=False`、不创建文件。                                                                                                                                      |
| `write_file(name, key, content, *, actor) -> ConfigFileInfo` | 解析 `spec_for(type, key)`；`validate_content(format, content)`（畸形 json/toml → `ConfigFileFormatInvalid` → 422，文件不变）；`store.write_text_atomic`（原子 + `.bak`）；写一条 `agent_config_file_written`；返回刷新后的 `ConfigFileInfo`。 |

### `AgentMcpService` (`application/agent/mcp_service.py`)

通过同一个 store 编辑 agent 的 MCP 配置文件来安装/卸载 Coffer 的 MCP 条目。复用
`domain/agent/mcp_install.py`。

| 方法                     | 用途                                                                                                                                                                                                           |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `status(name) -> bool`   | 读取 agent 的 MCP 配置文件；返回 `is_installed`。                                                                                                                                                              |
| `install(name, actor)`   | 解析 shim 路径（`COFFER_MCP_SHIM_PATH` → `shutil.which("coffer-mcp-shim")` → 解释器脚本目录 → 打包回退；全部落空则抛 `ShimNotFound`）。`apply_install`；原子写入 + `.bak`；audit `agent_mcp_installed`。幂等。 |
| `uninstall(name, actor)` | `apply_uninstall`；原子写入 + `.bak`；audit `agent_mcp_uninstalled`。条目不存在时为空操作。                                                                                                                    |

### `ConfigFileStorePort`（Protocol，定义在 application）

application 层接口；具体实现位于 `infrastructure/agent/config_file_store.py`
（Contract 4——application 不得直接 import infrastructure）。

- `read_text(path) -> str | None` —— 文件不存在时为 `None`。
- `stat(path) -> FileStat | None` —— 大小 + mtime，不存在时为 `None`。
- `write_text_atomic(path, text) -> None` —— 临时文件 + `os.replace`；若目标存在，
  先复制到 `<path>.bak`；按需创建父目录。

## Kind 装配 (`backend/coffer/application/agent/kind.py`)

`make_agent_kind(...)` 返回一个 `Kind`：

- `name='agent'`
- `display_name='Agent'`
- `config_schema=AgentConfig`
- `on_delete=...` —— 由 `ResourceService.delete` 调用的级联钩子，用于调用 **skill 侧** 的 binding 清理（skill 模块提供回调；agent kind 不直接 import skill 模块——在 composition root 通过 kind 模块上的 setter 装配）。

## Composition root 装配

在 `surfaces/http/app.py` 中，`_wire_agent_kind(app, resource_svc, audit, sm)`：

1. 构建 `AgentService` + `AutoDetectService` + `BrowseService`。
2. 在一个 `ConfigFileStore` 之上构建 `AgentConfigFileService` + `AgentMcpService`。
3. 通过 `make_agent_kind(on_delete_hook)` 构造 `Kind`。
4. 注册进 `app.state.kinds['agent']`。
5. 挂载 `agent_routes`（注册 + candidates）、`agent_config_routes`（配置文件 + MCP 安装）与 `fs_routes`（只读文件夹浏览）。

发现（discovery）是只读的，且**不**在启动时运行——绝不自动注册任何 agent。用户
按需运行发现，并确认要添加哪些候选项。

`on_delete_hook` 绑定到由 skill 模块（the 005-skill-manager spec）提供的可调用对象，使得移除 agent 时——一旦 the 005-skill-manager spec 装配该回调——在删除资源行之前同步触发 `SkillService.cleanup_bindings_for_agent(...)`。spec 004 只暴露该钩子接缝。

## 约束小结

- 所有 HTTP 路由绑定 `127.0.0.1`，共用 `X-Coffer-Token` 鉴权（依 spec 001）。
- 无新增凭据存储条目——`agent` config 不含凭据。配置文件读取不解析或抽取任何
  密钥；`~/.codex/auth.json` 被排除在 allowlist 之外。
- 配置文件在 Coffer 中可编辑。对 agent 自己的配置文件（位于 `~/.claude/`、
  `~/.codex/` 与 `~/.claude.json`）的所有写入——无论是用户保存还是 Coffer-MCP
  安装/卸载——都**只能**通过 allowlist 内的 `key` 寻址，绝不接受调用方提供的路径，
  且每次都由原子写入与 `.bak` 备份保护。用户保存还会在落盘前按文件格式校验内容。
  绝不读写任何超出已解析 allowlist 条目的路径。
