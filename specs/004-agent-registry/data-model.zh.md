# Data Model —— 004 Agent Registry

> English: [data-model.md](./data-model.md)

agent registry 的实体、字段、关系与存储说明。建立在 spec 001 引入的 kind-agnostic Resource 框架之上——agent 是通用 `resources` 表中的行，因此 spec 004 不新增任何自有表。

## Domain 实体 (`backend/coffer/domain/agent/`)

### `AgentType` + 能力清单 (`domain/agent/types.py`、`domain/agent/descriptor.py`)

`AgentType` 是字符串值的 enum（`StrEnum`）——稳定的身份（持久化值 + API 契约 +
注册白名单）。每个值都同时覆盖该产品的 CLI 与 app/IDE 形态，二者共享同一个配置目录。

所有*按类型的行为*都集中在**能力清单**（`domain/agent/descriptor.py`）：
`AGENT_DESCRIPTORS: dict[AgentType, AgentDescriptor]`，每个 agent 一条记录。
`types.py` 的方法、`config_files_for`、各 MCP 服务与 auto-detect 都读这张表
（枚举方法通过惰性导入委托，以保持依赖图无环）。\*\*新增一个 agent = 一个枚举值

- 一条描述符记录\*\*（仅当 agent 引入全新形态时才另加 MCP 渲染器或记忆适配器）。

| 值            | 显示名       | 默认 `config_dir`    | MCP 文件 / 容器键 / 形态                   |
| ------------- | ------------ | -------------------- | ------------------------------------------ |
| `claude_code` | Claude Code  | `~/.claude`          | `~/.claude.json` · `mcpServers` · map      |
| `codex`       | OpenAI Codex | `~/.codex`           | `config.toml` · `mcp_servers` · map        |

skill 投递到 `<config_dir>/skills`。`claude_desktop`（独立的 Claude 聊天应用）仍不在范围内。

`AgentDescriptor` 携带：`display_name`、`config_subpath`、`config_files`
（allowlist 构造器）、`mcp`（`McpInjectionSpec | None`）、`mcp_source_keys`、
`skill_subpath` 与 `plugins`（`PluginCapability | None`）。每个 enum 值仍提供：

- `display_name: str`
- `default_name() -> str`（稳定的按类型默认资源名——下划线变连字符，如 `claude_code` → `claude-code`；用户未显式提供名称时使用）
- `default_config_dir() -> Path`（该类型的标准配置目录，按宿主平台计算——`~/.claude` / `~/.codex`；用户未显式提供 `config_dir` 时使用）
- `detect_marker() -> Path`（发现（discovery）时检查的路径；通常就是 `default_config_dir` 本身）

配置文件 allowlist 与 skill 投递目标（`<config_dir>/skills`）都基于 agent 解析后的 `config_dir` 解析。

### `AgentConfig` (`domain/agent/config.py`)

Pydantic v2 `BaseModel`。注册到 `ResourceService` 的 kind 专属 config schema。

| 字段                | 类型           | 说明                                                                                                 |
| ------------------- | -------------- | ---------------------------------------------------------------------------------------------------- |
| `type`              | `AgentType`    | 必填；enum 值                                                                                        |
| `config_dir`        | `Path \| None` | 可选的绝对路径覆盖；读取时默认回退到 `type.default_config_dir()`                                     |
| `follow_all_skills` | `bool`         | follow-master-library 策略开关（spec 005 FR-025）；默认 `True`，保持修订前 trust-mode 自动绑定的行为 |
| `skill_exclusions`  | `list[str]`    | following 期间排除投递的 skill 名称列表；默认 `[]`                                                   |

skill 投递到 `<config_dir>/skills`；配置文件 allowlist 基于 `config_dir` 解析。每个解析后的 `config_dir` 至多只能有一个 agent。两个策略字段*存储*在这里（本 spec 的 schema），但其投递语义由 spec 005 负责（`SkillService` 的 follow 调和）；它们出现在 `AgentOut` 上，并可通过 `PATCH /agents/{name}` 更新。

校验器：

- `config_dir`（设置时）必须是绝对路径；注册时会自动创建 `<config_dir>/skills` 子目录，随后解析后的 `config_dir` 必须是一个已存在、可写的目录。
- `config_dir` 不得位于 `/etc`、`/usr`、`/bin`、`/sbin`、`/System`（POSIX）或 `C:\Windows`、`C:\Program Files`（Windows）之内。
- `model_config = ConfigDict(extra="forbid")`，拒绝未知字段。
- 一个 `model_validator(mode="before")` 会从 dict 输入中剔除遗留的 `auto_detected` 键（并把遗留的 `skill_dir` 映射到 `config_dir` 上），使早期持久化了这些（现已移除）字段的旧行在 `extra="forbid"` 下仍能加载。

### `ConfigFileFormat` + 配置文件 allowlist (`domain/agent/config_files.py`)

纯 domain 模块（除基于 `os.environ` 的路径构造外无 I/O，与 `types.py` 同样的
模式）。定义每个 agent 类型对外暴露的精选配置文件集合。这些文件在 **UI 中只读
呈现**——查看器渲染内容并提供「在外部编辑器中打开 / 显示 / 复制路径」（HTTP 的
`ConfigFileInfo` / `ConfigFileContent` 视图同时携带文件 `path` 与其所在文件夹的
`folder_path` 以支撑这些操作，FR-038）；程序化读取与写入仍走 REST API / CLI。

`ConfigFileFormat` —— `json`、`toml`、`yaml`、`markdown`、`text` 的 `StrEnum`。
驱动保存时的校验：`json` 用 `json.loads` 解析，`toml` 用 `tomllib.loads`，`yaml`
用 `yaml.safe_load`；`markdown` 与 `text` 永远合法。

`ConfigFileKind` —— `file`、`directory` 的 `StrEnum`。`directory` 条目
（FR-034）解析为一个文件目录而非单个文件；其 `format` 描述的是**子文件**。

`ConfigFileSpec` —— 描述一个 allowlist 内文件的 frozen dataclass：

| 字段           | 类型               | 说明                                                      |
| -------------- | ------------------ | --------------------------------------------------------- |
| `key`          | `str`              | API/CLI 寻址用的稳定标识（如 `settings`、`instructions`） |
| `display_name` | `str`              | 人类可读标签（如「User settings」）                       |
| `path`         | `Path`             | 解析后的绝对路径（按宿主计算）                            |
| `format`       | `ConfigFileFormat` | 决定校验方式（目录条目时为子文件的校验方式）              |
| `kind`         | `ConfigFileKind`   | `file`（默认）或 `directory`                              |

`config_files_for(agent_type, config_dir=None) -> tuple[ConfigFileSpec, ...]`
返回基于该 agent 实际配置目录解析的精选 allowlist。当前集合（原 `memory` 键
更名为 `instructions`——这些是人工撰写的指令文件，与 agent 写入的 memory 不同，
后者属于 spec 007 的领域）：

| Agent         | `key`            | 路径                               | 格式       | kind        |
| ------------- | ---------------- | ---------------------------------- | ---------- | ----------- |
| `claude_code` | `settings`       | `~/.claude/settings.json`          | `json`     | `file`      |
| `claude_code` | `settings_local` | `~/.claude/settings.local.json`    | `json`     | `file`      |
| `claude_code` | `global`         | `~/.claude.json`                   | `json`     | `file`      |
| `claude_code` | `instructions`   | `~/.claude/CLAUDE.md`              | `markdown` | `file`      |
| `claude_code` | `subagents`      | `~/.claude/agents/`                | `markdown` | `directory` |
| `codex`       | `config`         | `~/.codex/config.toml`             | `toml`     | `file`      |
| `codex`       | `instructions`   | `~/.codex/AGENTS.md`               | `markdown` | `file`      |
| `codex`       | `hooks`          | `~/.codex/hooks.json`              | `json`     | `file`      |

（`global` 始终锚定在 `$HOME`——即使配置目录本身被覆盖，Claude Code 也把 `~/.claude.json` 放在主目录根部。）

`~/.codex/auth.json` 被有意排除（凭据/状态，而非手工编辑的配置）。`~/.claude.json`
被纳入（按产品决策），并由每次写入的 `.bak` 备份保护。

`validate_content(fmt: ConfigFileFormat, text: str) -> None` 对结构化格式的非法
内容抛出 `ConfigFileFormatInvalid`。

`spec_for(agent_type, key) -> ConfigFileSpec` 在 `key` 不在该类型 allowlist 内时
抛出 `ConfigFileNotAllowed`（驱动 404 + 不访问文件系统的规则）。

### 目录型配置条目 (FR-034/FR-035)

`kind=directory` 的 allowlist 条目列出其子文件而非携带内容；磁盘上的目录即为
事实来源（派生，从不存储）。目录条目是 Claude Code 的 `subagents`
（`~/.claude/agents/`，每个个人 subagent 一个 Markdown 文件，允许嵌套路径）。

`DirEntryInfo` —— 描述一个子文件的 frozen dataclass：

| 字段          | 类型       | 说明                      |
| ------------- | ---------- | ------------------------- |
| `relpath`     | `str`      | 相对条目目录的 POSIX 路径 |
| `size`        | `int`      | 字节大小                  |
| `modified_at` | `datetime` | 最后修改时间              |

`validate_child_relpath(root, relpath) -> Path` 是子路径的安全边界（纯路径
运算；symlink 逃逸在 I/O 时由 store 复查）：在任何文件系统访问之前，拒绝
路径穿越（`..`）、绝对路径、反斜杠、隐藏段，以及小写 `.md` 之外的任何扩展名。

### MCP 注入——正交两轴 (`domain/agent/mcp_injection.py`、`mcp_install.py`)

MCP 配置在不同 agent 间沿**两条相互独立的轴**变化，由 `McpInjectionSpec`
（在清单里按 agent 持有）刻画：

- **格式（format）** —— `json` / `toml`，决定解析/序列化器（`json` 用标准库、`toml` 用 `tomlkit`）。
- **形状（shape）** —— `container_key`（顶层表：`mcpServers` / `mcp_servers`）+ `entry_style`（`McpEntryStyle`）：`COMMAND_MAP`（`{"command": shim}`——Claude Code/Codex）。

`mcp_install.py` 以纯文本变换（不触碰文件系统）构建/检测/移除 `coffer` 条目：

- `COFFER_SERVER_KEY = "coffer"`。
- `apply_install(fmt, text, shim_path, *, container_key=None, entry_style=COMMAND_MAP) -> str`
  —— 插入/更新 `coffer` 条目。`container_key` 按格式取默认值
  （`default_container_key`）。幂等。
- `apply_uninstall(fmt, text, *, container_key=None) -> str` —— 移除 `coffer` 条目
  （不存在时为空操作）。
- `is_installed` / `installed_command`（`*, container_key=None`）—— 存在性 / shim
  路径（后者同时处理 command-map 与 command-array 两种形状）。

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

workspace 修订新增：

| 值                          | 触发时机                                                         |
| --------------------------- | ---------------------------------------------------------------- |
| `agent_config_file_deleted` | 一个目录条目的子文件被删除（先前内容保留为 `.bak`）              |
| `agent_mcp_entry_removed`   | 一个直连 MCP 条目被从 agent 的配置文件中移除（FR-026）           |
| `agent_mcp_entry_adopted`   | 一个直连 MCP 条目被 adopt 为已注册的 `mcp_server` 资源（FR-028） |
| `agent_plugin_toggled`      | 一个 plugin 的启用状态在其文档化的配置面上被更改（FR-032）       |
| `agent_plugin_uninstalled`  | 一个 Codex plugin 条目 + 缓存目录被移除（FR-033）                |

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

| 方法                                                                                              | 用途                                                                                                                                                                                                                                                                                                                                                  |
| ------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `list_files(name) -> list[ConfigFileInfo]`                                                        | 对该 agent 类型的每个 `ConfigFileSpec`，返回 key、显示名、路径、所在文件夹的 `folder_path`（支撑只读 UI 的 打开/显示/复制路径，FR-038）、格式、`kind`、`exists`，存在时附带大小 + mtime。目录条目额外携带 `files`（递归 `.md` 列表，`DirEntryInfo` 行）。                                                                                             |
| `read_file(name, key) -> ConfigFileContent`                                                       | 解析 `spec_for(type, key)`；返回内容 + `path` + `folder_path` + 格式 + `exists` + `fingerprint` + `memory_block`（`path`/`folder_path` 这一对支撑「在外部编辑器中打开 / 显示 / 复制路径」，FR-038）。文件不存在 → 空内容、`exists=False`、`fingerprint=""`、不创建文件。                                                                              |
| `write_file(name, key, content, *, expected_fingerprint=None, actor) -> ConfigFileInfo`           | 解析 `spec_for(type, key)`；`validate_content(format, content)`（畸形 json/toml → `ConfigFileFormatInvalid` → 422，文件不变）；提供 `expected_fingerprint` 时，若磁盘内容自读取后已变化则以 `ConfigFileStale`（→ 409）拒绝（FR-036）；`store.write_text_atomic`（原子 + `.bak`）；写一条 `agent_config_file_written`；返回刷新后的 `ConfigFileInfo`。 |
| `read_child(name, key, relpath) -> ConfigFileContent`                                             | 先 `validate_child_relpath`，再读取目录条目的一个子文件；返回形状同 `read_file`。                                                                                                                                                                                                                                                                     |
| `write_child(name, key, relpath, content, *, expected_fingerprint=None, actor) -> ConfigFileInfo` | 子文件的写即建（create-on-write）保存；与 `write_file` 共用同一套校验 / 过期检查 / 原子写入 / audit 机制（FR-035）。                                                                                                                                                                                                                                  |
| `delete_child(name, key, relpath, *, actor) -> None`                                              | 删除一个子文件，先前内容保留为 `.bak`；记录 `agent_config_file_deleted`。                                                                                                                                                                                                                                                                             |

`ConfigFileContent.fingerprint` 是用于乐观并发写入的内容指纹（FR-036）——
读取返回它，写入带回它。`ConfigFileContent.memory_block` 在文本包含 spec 007
所拥有的受管 memory-projection 块标记时为 true（FR-037）；编辑器只呈现提示，
绝不解析该块。

### `AgentMcpService` (`application/agent/mcp_service.py`)

通过同一个 store 编辑 agent 的 MCP 配置文件来安装/卸载 Coffer 的 MCP 条目。复用
`domain/agent/mcp_install.py`。

| 方法                     | 用途                                                                                                                                                                                                           |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `status(name) -> bool`   | 读取 agent 的 MCP 配置文件；返回 `is_installed`。                                                                                                                                                              |
| `install(name, actor)`   | 解析 shim 路径（`COFFER_MCP_SHIM_PATH` → `shutil.which("coffer-mcp-shim")` → 解释器脚本目录 → 打包回退；全部落空则抛 `ShimNotFound`）。`apply_install`；原子写入 + `.bak`；audit `agent_mcp_installed`。幂等。 |
| `uninstall(name, actor)` | `apply_uninstall`；原子写入 + `.bak`；audit `agent_mcp_uninstalled`。条目不存在时为空操作。                                                                                                                    |

## Workspace 修订 —— 派生实体（从不存储）

workspace 各个面（FR-025..FR-033）在 agent 自己的配置文件上操作；磁盘上的文件
始终是事实来源，Coffer 不保留任何副本。下面两个实体都是读取时的投影。

### Agent MCP 条目 (`domain/agent/mcp_entries.py` —— `McpEntry`)

agent 自身文件中配置的一个 MCP server 条目。从 claude_code 的 `~/.claude.json`

- `settings.json` `mcpServers` 映射以及 codex 的 `config.toml`
  `[mcp_servers.*]` 表解析而来（纯文本变换；`tomlkit` 保留用户的 TOML 布局）。

| 字段               | 类型             | 说明                                                                                                                   |
| ------------------ | ---------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `name`             | `str`            | 配置文件中的条目键                                                                                                     |
| `source`           | `str`            | 来源文件的 allowlist key（`global`/`settings`/`config`）                                                               |
| `transport`        | `str`            | `stdio` 或 `http`（派生：存在 `url` → `http`）                                                                         |
| `command` / `args` | `str?` / `tuple` | stdio 启动参数                                                                                                         |
| `env` / `headers`  | `dict[str,str]`  | `repr=False`——值可能携带密钥；HTTP 上只输出**键名**（`env_keys`、`header_keys`，外加标记疑似密钥键名的 `secret_keys`） |
| `url`              | `str \| None`    | http 传输目标                                                                                                          |
| `enabled`          | `bool \| None`   | 格式定义了逐条目开关时的标志（codex）；claude_code 为 `None`                                                           |
| `is_coffer`        | `bool`           | Coffer 自己的 gateway 条目——移除/开关/adopt 均受保护                                                                   |
| `matches_resource` | `str \| None`    | 等价的已注册 `mcp_server` 资源，由 application 层填充                                                                  |

配套工具：`parse_entries`、`remove_entry`、`set_entry_enabled`（仅 TOML）、
`secret_env_keys`（TOKEN/SECRET/PASSWORD/API_KEY/CREDENTIAL/AUTHORIZATION
模式）以及 `to_transport_config`（条目 → `mcp_server` 传输配置，密钥键移入
`credential_refs` 供 adopt 使用）。畸形文件抛出 `AgentConfigParseError`，
列表视图将其降级为一条 `parse_errors` 而非整体失败（FR-030）。

### `PluginCapability` / `PluginModel` (`domain/agent/descriptor.py`)

能力清单的插件 facet。`PluginModel` 是策略判别符——`CLAUDE`、`CODEX`——各自映射到
`plugin_state.py` 中的一种解析/开关/卸载策略。`PluginCapability`（frozen）
携带让服务无需 `AgentType` 分支即可分派的全部信息：

| 字段            | 类型          | 说明                     |
| --------------- | ------------- | ------------------------ |
| `model`         | `PluginModel` | 解析/开关/卸载策略       |
| `config_key`    | `str \| None` | 写入面的 allowlist key   |
| `can_toggle`    | `bool`        | 是否支持 `set_enabled`   |
| `can_uninstall` | `bool`        | 是否支持 `uninstall`     |

`AgentDescriptor.plugins` 为 `PluginCapability | None`。各 agent 映射：Claude Code `CLAUDE`/`settings`/仅开关；Codex `CODEX`/`config`/完整。

### Agent Plugin (`domain/agent/plugin_state.py` —— `PluginInfo` / `MarketplaceInfo`)

一个已安装的 plugin，id 为 `<name>@<marketplace>`。Codex 的状态在 `config.toml`（`[plugins."…"]` +
`[marketplaces.*]`，可读，plugins 表可写）。Claude Code 的状态分布在内部清单文件
`installed_plugins.json` / `known_marketplaces.json`（只读输入——Coffer 绝不写
它们）与文档化的写入面 `settings.json` `enabledPlugins` 之间。

| 字段          | 类型   | 说明                                                   |
| ------------- | ------ | ------------------------------------------------------ |
| `id`          | `str`  | `<name>@<marketplace>`（按最后一个 `@` 拆分）          |
| `name`        | `str`  |                                                        |
| `marketplace` | `str`  |                                                        |
| `enabled`     | `bool` | 配置无显式标志时默认 `True`                            |
| `installed`   | `bool` | 是否出现在安装清单中；仅存于 settings 的孤儿为 `False` |

`MarketplaceInfo` 携带 `name`、`source_type`、`source`（只读）。HTTP 视图
（`PluginView`）用 `cache_present`（plugin 的缓存目录是否在磁盘上）替代
`installed`——不做任何修复（FR-031）。

### `AgentMcpEntryService` (`application/agent/mcp_entry_service.py`)

| 方法                                                                  | 用途                                                                                                                                                                                                   |
| --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `list_entries(name)`                                                  | 解析该 agent 类型所有承载 MCP 的文件；标注 `is_coffer` 与 `matches_resource`；收集逐文件的 `parse_errors`。                                                                                            |
| `set_enabled(name, entry, enabled, actor)`                            | 就地切换 `enabled` 标志（仅 codex `config.toml`——claude_code → `McpEntryToggleUnsupported` → 422）。`coffer` 条目 → `McpEntryProtected`。                                                              |
| `remove_entry(name, entry, source=None, actor)`                       | 从来源文件移除条目（原子 + `.bak`）；当 claude_code 在两个文件中都有同名条目时由 `source` 消歧（否则 `McpEntrySourceAmbiguous`）；audit `agent_mcp_entry_removed`。                                    |
| `adopt(name, entry, source=None, new_name=None, secrets=None, actor)` | FR-028 升级：疑似密钥键必须映射到 keychain 引用（`AdoptSecretUnresolved` 列出未解析的键）；注册 `mcp_server` 资源 → 验证可回读 → 移除来源条目，之后任何失败都会回滚；audit `agent_mcp_entry_adopted`。 |

### `AgentPluginService` (`application/agent/plugin_service.py`)

| 方法                                           | 用途                                                                                                                                                                                            |
| ---------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `list_plugins(name)`                           | 按 `descriptor.plugins.model` 分派；从文档化文件解析 plugin + marketplace 状态；计算 `cache_present`；收集 `parse_errors`。无能力 → 空列表。                                                    |
| `set_enabled(name, plugin_id, enabled, actor)` | 按 `PluginModel` 分派；只写能力的 `config_key` 面；audit `agent_plugin_toggled`。                              |
| `uninstall(name, plugin_id, actor)`            | 按 `PluginModel` 分派；移除条目（Codex 还删除缓存目录）；`can_uninstall=false`（Claude Code）→ `PluginUninstallUnsupported` → 422；audit `agent_plugin_uninstalled`。 |


### `ConfigFileStorePort`（Protocol，定义在 application）

application 层接口；具体实现位于 `infrastructure/agent/config_file_store.py`
（Contract 4——application 不得直接 import infrastructure）。

- `read_text(path) -> str | None` —— 文件不存在时为 `None`。
- `stat(path) -> FileStat | None` —— 大小 + mtime，不存在时为 `None`。
- `write_text_atomic(path, text) -> None` —— 临时文件 + `os.replace`；若目标存在，
  先复制到 `<path>.bak`；按需创建父目录。
- `list_dir(root) -> list[DirEntryInfo] | None` —— `root` 下常规 `.md` 文件的
  递归列表（跳过 symlink 文件，按 relpath 排序）；`root` 不是目录时为 `None`。
- `delete_with_backup(path) -> bool` —— 先把内容复制到 `<path>.bak`，再删除文件。
- `fingerprint(text) -> str` —— 支撑 FR-036 过期检查的内容指纹。

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
