# Data Model —— 005 Skill Manager

> English: [data-model.md](./data-model.md)

skill manager 的实体、字段、关系与 SQLite schema 增量。建立在 spec 004 的 agent kind 与 spec 001 的 kind-agnostic Resource 框架之上。

## Domain 实体（`backend/coffer/domain/skill/`）

### `SkillSource` (`domain/skill/source.py`)

记录被管理 skill 来源的 Pydantic 模型。v1 中只支持本地文件夹导入。

#### `LocalImportSource`

| 字段            | 类型                      | 说明                             |
| --------------- | ------------------------- | -------------------------------- |
| `type`          | `Literal["local_import"]` | 来源类型                         |
| `original_path` | `str`                     | 仅信息性记录；不作为持续依赖保留 |

### `SkillConfig` (`domain/skill/config.py`)

Pydantic v2 `BaseModel`。

| 字段                         | 类型               | 说明                                                 |
| ---------------------------- | ------------------ | ---------------------------------------------------- |
| `source`                     | `LocalImportSource` | 单一 local_import 来源                              |
| `skill_md_name`              | `str`              | SKILL.md frontmatter 的 `name`；等于 `Resource.name` |
| `skill_md_description`       | `str`              | frontmatter 的 `description`                         |
| `version_hash`               | `str`              | 上次同步时 SKILL.md 内容的 sha256                    |
| `last_synced_from_source_at` | `datetime \| None` | UTC；在导入时写入                                    |

### `SkillFrontmatter` (`domain/skill/frontmatter.py`)

Pydantic v2 模型，用于校验导入的文件夹，对齐 agentskills.io 约束：

| 字段            | 类型                | 约束                                              |
| --------------- | ------------------- | ------------------------------------------------- |
| `name`          | `str`               | 必填，1–64 字符，`^[a-z0-9][a-z0-9_-]{0,63}$`     |
| `description`   | `str`               | 必填，1–1024 字符                                 |
| `license`       | `str \| None`       | 可选；识别但不解读                                |
| `allowed_tools` | `list[str] \| None` | 可选（`allowed-tools`）；由列表或分隔字符串归一化 |

`name` 接受标准字符集的有据超集——标准允许小写字母、数字与连字符，Coffer 额外容忍下划线以兼容磁盘上既有的 skill。`license` 与 `allowed-tools` 均为第三方编写字段，识别它们保持纯增量：非字符串的 `license` 标量会被转为字符串，格式异常的 `allowed-tools` 被容忍（视作缺省）而非校验失败。其他一切未识别字段以 `extra='allow'` 容忍。

frontmatter 的 `description` 持久化在 skill kind 自己的 config 字段 `SkillConfig.skill_md_description` 中 —— 这是权威拷贝。`resources` 表自身的 `description` 列继承自 kind-agnostic Resource 框架；在 import 时从 frontmatter `description` 初始化以与其他 kind 保持一致，但**不**在之后重新同步（视作初次写入后用户可自由编辑的人类标签）。

### `BindingState` (`domain/skill/binding.py`)

普通 dataclass；`skill_agent_bindings` 一行在内存中的表达。

| 字段                | 类型               | 说明                                                                                                        |
| ------------------- | ------------------ | ----------------------------------------------------------------------------------------------------------- |
| `skill_resource_id` | `int`              | 外键                                                                                                        |
| `agent_resource_id` | `int`              | 外键                                                                                                        |
| `enabled`           | `bool`             |                                                                                                             |
| `last_linked_at`    | `datetime \| None` | 上次成功 link 的时间                                                                                        |
| `last_link_path`    | `str \| None`      | 上次创建 link 的绝对路径                                                                                    |
| `link_mode`         | `LinkMode \| None` | `symlink`、`junction` 或 `copy_fallback`；与 `SkillBindingOut.link_mode` 对应，UI 据此标记 degraded binding |

### `DriftKind` (`domain/skill/drift.py`)

字符串值的 enum。

| 值                      | 含义                                | 建议处置                     |
| ----------------------- | ----------------------------------- | ---------------------------- |
| `missing_link`          | binding 已启用但磁盘目标缺失        | 重新启用以重建 link          |
| `tampered_link`         | symlink 指向的不是 Coffer 的 master | 先禁用再启用，或用 `--force` |
| `replaced_with_regular` | 路径是普通文件/目录，而非 link      | 同上                         |
| `missing_master`        | binding 指向的 master 文件夹已不在  | 重新导入                     |
| `orphan_master`         | 磁盘上有 master 但 DB 无记录        | 收编或移除                   |

### 未托管 skill (`domain/skill/scan.py` + `domain/agent/scan.py`) —— workspace 修订

在 agent 的 skill 位置中发现的、Coffer 不管理的 skill 形态条目的派生视图
（从不存储，FR-022）。文件系统是事实来源；adopt 与删除是仅有的两种变更。

`scan_locations(agent_type, config_dir)` 位于 `domain/agent/scan.py`
（它依赖 `AgentType`，而 `domain/skill` 不得 import 它——Contract 5c），
返回按序扫描的目录：两个类型的 `<config_dir>/skills`，外加 `codex` 的
`~/.agents/skills`。infrastructure 层（`infrastructure/skill/workspace_scan.py`）
把它们遍历成 `ScanEntry` 值（name、path、`is_dir`、`link_target`），再由
`domain/skill/scan.py` 中的纯函数 `classify` 转成 `UnmanagedSkill` 结果：

- Coffer 托管的链接（解析到 `~/.coffer/skills/` 内的 symlink）被排除；
- 点条目（如 Codex 的 `.system`）与普通文件被静默排除；
- 指向主库之外的 symlink 以 `foreign_link=True` 列出，且永不可 adopt；
- 普通目录被列出且可 adopt。

对外暴露的字段（`application/skill/unmanaged_ops.py` 中的 `UnmanagedView`）：

| 字段           | 类型          | 说明                                                                       |
| -------------- | ------------- | -------------------------------------------------------------------------- |
| `name`         | `str`         | 文件夹名                                                                   |
| `path`         | `str`         | 磁盘绝对路径                                                               |
| `location`     | `str`         | `"skills"`（`<config_dir>/skills`）或 `"agents_dir"`（`~/.agents/skills`） |
| `valid`        | `bool`        | 是否通过 AgentSkills 校验（FR-004）                                        |
| `reason`       | `str \| None` | 不合法时的失败原因                                                         |
| `foreign_link` | `bool`        | 指向主库之外的 symlink——呈现给用户但永不可 adopt                           |

### Follow 策略（存于 agent 资源的 config，spec 004）—— workspace 修订

逐 agent 的 skill 投递策略（FR-025）：`follow_all_skills: bool`（默认
`True`，保持修订前的 trust mode）加 `skill_exclusions: list[str]`。字段位于
`AgentConfig`（spec 004 的 schema，经 `PATCH /agents/{name}` / `coffer agent
follow` 更新）；本 spec 负责其投递语义。following 期间，agent 的有效 skill
集合是整个主库减去其排除项；binding 仍是持久的投递记录。
`application/skill/follow_ops.py` 在开关翻转、skill 注册或移除、排除列表
变化时调和投递；关闭开关会把当前已投递的 skill 保留为显式的逐 skill
binding。策略通过注入的 `agent_skill_policy_resolver` 读取，skill 代码绝不
import agent-kind 代码（Contract 5c）。

## SQLite schema 增量

迁移 `20260526_0005_skill_tables.py`（revision `0005`，down_revision `0004`）新增 skill 绑定表。agent 本身存在共享的 `resources` 表里，因此 spec 004 不需要专门的 agent-tables 迁移。

### `skill_agent_bindings`

| 列                  | 类型                                     | 约束                                                             |
| ------------------- | ---------------------------------------- | ---------------------------------------------------------------- |
| `skill_resource_id` | `int`                                    | FK → `resources(id)` ON DELETE CASCADE                           |
| `agent_resource_id` | `int`                                    | FK → `resources(id)` ON DELETE CASCADE                           |
| `enabled`           | `bool`                                   | not null, default `0`                                            |
| `last_linked_at`    | `timestamp`                              | nullable                                                         |
| `last_link_path`    | `text`                                   | nullable                                                         |
| `link_mode`         | `text`                                   | nullable；非空时取 `symlink` / `junction` / `copy_fallback` 之一 |
| 主键                | `(skill_resource_id, agent_resource_id)` |                                                                  |

索引：`idx_bindings_agent`，列 `(agent_resource_id, enabled)`，支持「某 agent 启用了哪些 skill」查询。

### 复用已有表

- `resources`：新增 `kind='skill'` 的行；无 schema 变更。
- `audit_log`：新增若干事件类型（见下）。

## 新增的审计事件类型

加入 `AuditEventType`：

| 值                     | 触发时机                                          |
| ---------------------- | ------------------------------------------------- |
| `skill_imported`       | 本地导入成功                                      |
| `skill_updated`        | 就地文件编辑改动了 skill 内容（details 含前后哈希） |
| `skill_bound`          | 按 agent 启用 binding（创建 symlink）             |
| `skill_unbound`        | 按 agent 禁用 binding（移除 symlink）             |
| `skill_drift_detected` | `verify` 报告 drift（details 含计数与类别）       |

workspace 修订新增：

| 值                        | 触发时机                                                                    |
| ------------------------- | --------------------------------------------------------------------------- |
| `skill_adopted`           | 一个未托管 skill 文件夹被 adopt 进主库（FR-023）                            |
| `skill_unmanaged_deleted` | 一个未托管 skill 文件夹被从 agent workspace 中删除（FR-024）                |
| `skill_autobind_skipped`  | 自动绑定 / follow 调和跳过某个 agent（如目标冲突；尽力而为）                |
| `skill_relinked`          | 某个已启用 binding 的托管链接在新投递路径上被重建（如 `config_dir` 变更后） |

skill **删除** 没有专门的事件——删除一个 skill 走 `ResourceService.delete`，
它发出通用的 `resource_deleted` 事件（`details` 含删除前快照），与任何其他
resource kind 一样。

## 磁盘布局

```
~/.coffer/
  skills/
    <skill-name>/           # 规范 master，每个 skill 一份
      SKILL.md
      scripts/ ...           # 可选
      references/ ...        # 可选
      assets/ ...            # 可选
      .coffer.meta.json      # 源 provenance 冗余；非权威
```

`.coffer.meta.json` 复制 `SkillConfig` 的一个子集，用于 DB 丢失时的取证恢复。该文件由 `MasterStore` 在 master 内容拷贝完成后立即写入（即 import 流程末尾），并在之后每次成功同步时就地重写。Coffer 运行时**不**读取这个文件；DB 才是权威，发生分歧以 DB 为准。

持久化的 key：

| Key                          | 来源                                     | 说明                             |
| ---------------------------- | ---------------------------------------- | -------------------------------- |
| `source`                     | `SkillConfig.source`                     | local_import 来源含 original_path |
| `skill_md_name`              | `SkillConfig.skill_md_name`              | 写入时与 master 文件夹名一致     |
| `skill_md_description`       | `SkillConfig.skill_md_description`       |                                  |
| `version_hash`               | `SkillConfig.version_hash`               | 上次同步时 SKILL.md 的 sha256    |
| `last_synced_from_source_at` | `SkillConfig.last_synced_from_source_at` | ISO-8601 UTC                     |

每个 agent 的 symlink 目标位于：

```
<config_dir>/skills/<skill-name>  → symlink/junction 指向  ~/.coffer/skills/<skill-name>
```

### 各 agent 的交付目标

每个 agent 通过能力清单（`domain/agent/descriptor.py`）声明 Coffer _如何_ 以及
_交付到哪里_：`skill_delivery_mode`（`SkillDeliveryMode` —
`folder` / `rules_mdc` / `external_dir`），folder 模式还携带 agent 配置目录下的
`skill_subpath`。skill 服务通过组合根注入的 resolver 读取该模式，resolver 返回
普通字符串（契约 5：服务永不导入 descriptor）。

| Agent          | 交付模式       | folder 目标                  | 状态                               |
| -------------- | -------------- | ---------------------------- | ---------------------------------- |
| Claude Code    | `folder`       | `<config_dir>/skills/<name>` | 已交付                             |
| Codex          | `folder`       | `<config_dir>/skills/<name>` | 已交付                             |
| `rules_mdc`    | —              | —                            | 保留扩展点（当前无 agent 类型使用）|
| `external_dir` | —              | —                            | 保留扩展点（当前无 agent 类型使用）|

folder 交付通过 symlink（FAT32 上回退为复制）把 master 目录链接到目标，agent 读取
到的是规范的 `SKILL.md`，路径为 `<config_dir>/skills/<name>/SKILL.md`。

**`external_dir` 与 `rules_mdc`——保留扩展点。** 这两个 `SkillDeliveryMode` 枚举值
作为有意保留的扩展点存在，当前没有任何 agent 类型使用。为使用这些模式的（假想）
agent 启用 skill 会在任何文件系统写入之前抛出 `SkillDeliveryUnsupported`（HTTP 422）；
follow / relink 协调器会跳过此类 agent，因此注册、配置目录变更和策略变更流程永远
不会失败。

## Application 服务契约（`backend/coffer/application/skill/`）

### `SkillService`

| 方法                                                           | 用途                                                                                                     |
| -------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `import_local(path, actor) -> Resource`                        | 读 SKILL.md，校验，拷到 master，注册 Resource，写审计，返回。自动为每个已注册 agent 绑定（trust 模式）。 |
| `enable_for(skill_ref, agent_ref, force=False, actor) -> None` | upsert binding，创建 symlink（FAT32 上 copy fallback）。                                                 |
| `disable_for(skill_ref, agent_ref, actor) -> None`             | 标记 binding 为 disabled，移除 link。                                                                    |
| `verify() -> DriftReport`                                      | 遍历每条已启用 binding，按 `DriftKind` 分类 drift。                                                      |
| `remove(ref, actor) -> None`                                   | 级联清理 symlink、删除 master，委派 `ResourceService.delete`。                                           |
| `cleanup_bindings_for_agent(agent_ref) -> None`                | 由 spec 004 的 `agent.on_delete` 钩子调用；移除该 agent 的所有 binding 与 symlink。                      |

workspace 修订的新增能力（以自由函数实现于 `unmanaged_ops.py` /
`follow_ops.py`；逐 agent 启用/禁用流程拆分到 `binding_ops.py` 以满足文件
大小上限——风格同 `lifecycle_ops.py`，概念上都是 skill 子包私有）：

| 方法                                                                   | 用途                                                                                                                                                               |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `list_unmanaged(agent_name) -> list[UnmanagedView]`                    | FR-022 对 agent skill 位置的只读扫描（见上文「未托管 skill」）。                                                                                                   |
| `adopt_unmanaged(agent_name, skill_name, location, actor) -> Resource` | FR-023：校验 → 移动到 `~/.coffer/skills/<name>/` → 注册 → 把托管链接投递到 `<config_dir>/skills/<name>` → 为该 agent 记录已启用的 binding；audit `skill_adopted`。 |
| `delete_unmanaged(agent_name, skill_name, location, actor) -> None`    | FR-024：仅从磁盘删除该文件夹；audit `skill_unmanaged_deleted`。                                                                                                    |
| follow 调和（`follow_ops.py`）                                         | FR-025：在开关/排除项/skill 集合变化时调和投递；关闭开关时把已投递的 skill 保留为显式 binding。                                                                    |

### 文件查看器（`application/skill/file_ops.py`）

紧邻 `service.py` 的无状态辅助函数（与 `verify_ops.py`
同一模式），向 surface 暴露 skill 的 master 文件夹。**读取**辅助函数
（`build_file_tree`、`read_skill_file`）支撑只读的应用内查看器，并为每个节点
暴露磁盘绝对路径，使 UI 能提供「在外部编辑器中打开」/「在文件管理器中显示」
操作（FR-027）；UI 查看器从不编辑内容。另一个**写入**辅助函数
（`write_skill_file`）支撑编程式 REST/CLI 覆盖（FR-028），是此处唯一的写入——
应用内 UI 不用它编辑内容。无 DB、无审计；containment 通过解析每个候选路径并要求
其位于解析后的 master 文件夹内来强制，沿用 `domain/skill/validator.py` 的越界
路径检查方式。

| 函数                                                               | 用途                                                                                                                                                              |
| ------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `build_file_tree(master_folder) -> FileNode`                       | 递归列出 master 文件夹；跳过真实目标越界的 symlink；不跟进 symlink 目录。每个节点带磁盘绝对路径。                                                                 |
| `read_skill_file(master_folder, relpath) -> FileContent`           | 解析 `master_folder/relpath`，校验其位于文件夹内（否则 `ValueError`），带大小上限读取并检测 binary；返回文件绝对路径及所在文件夹绝对路径。                        |
| `write_skill_file(master_folder, relpath, content) -> FileContent` | FR-028 编程式（REST/CLI）覆盖已存在文本文件，使用与读取相同的 containment 与大小上限；拒绝创建新文件/目录、写到文件夹之外或覆盖二进制文件；原子。应用内 UI 不用。 |

#### 文件节点结构（`FileNode` / `SkillFileNodeOut`）

递归树中的一个节点。根节点的 `path == ""`。

| 字段       | 类型              | 说明                                                             |
| ---------- | ----------------- | ---------------------------------------------------------------- |
| `name`     | `str`             | 条目的基名                                                       |
| `path`     | `str`             | 相对 master 文件夹根的 POSIX 路径（根为 `""`）                   |
| `abs_path` | `str`             | 磁盘绝对路径（用于在外部编辑器中打开 / 显示，FR-027） |
| `type`     | `"file" \| "dir"` | 节点类型                                                         |
| `size`     | `int \| None`     | 文件为字节大小；目录为 `null`                                    |
| `children` | `list[FileNode]`  | 目录有值（目录优先再按名称排序）；文件为 `[]`                    |

#### 文件内容结构（`FileContent` / `SkillFileContentOut`）

单个文件的内容。应用内查看器只读渲染；编程式写入（FR-028）返回相同结构。

| 字段              | 类型   | 说明                                         |
| ----------------- | ------ | -------------------------------------------- |
| `path`            | `str`  | 相对 master 文件夹根的 POSIX 路径            |
| `abs_path`        | `str`  | 文件的磁盘绝对路径（FR-027）                 |
| `folder_abs_path` | `str`  | 文件所在文件夹的磁盘绝对路径（FR-027）       |
| `content`         | `str`  | 文件文本；`binary` 为真时为空（`""`）        |
| `truncated`       | `bool` | 文件超出 256 KiB 读取上限、仅返回前缀时为真  |
| `binary`          | `bool` | 文件非 UTF-8 或含 NUL 字节时为真（内容为空） |
| `size`            | `int`  | 磁盘上文件的真实字节大小（与是否截断无关）   |

### `SyncEngine` (`infrastructure/skill/sync_engine.py`)

跨平台目录链接辅助。放在 `infrastructure/` 是因为它直接操作宿主文件系统（Windows 上还要调用 `cmd.exe /c mklink`）；application 层通过 `application/skill/ports.py` 中的端口访问它。

| 方法                                                                 | 用途                                                                                                                                                                                                                                                                                          |
| -------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `make_directory_link(target: Path, link: Path) -> LinkMode`          | POSIX：`os.symlink(target, link, target_is_directory=True)`。Windows：先试 `os.symlink`；遇到 `OSError(WinError 1314)` 则回退到 `subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)])`（junction）。返回 `LinkMode.SYMLINK \| LinkMode.JUNCTION \| LinkMode.COPY_FALLBACK`。 |
| `remove_directory_link(link: Path) -> None`                          | 先识别类型再正确删除（junction vs symlink vs copy-tree）。                                                                                                                                                                                                                                    |
| `classify_target(link: Path, expected_master: Path) -> TargetStatus` | 返回对应的 `DriftKind`（或 `OK`）。                                                                                                                                                                                                                                                           |

### `AgentSkillsValidator` (`domain/skill/validator.py`)

纯函数校验：传入文件夹路径，返回 `ValidationOk(name, description)` 或 `ValidationError(reason, details)`。检查项：`SKILL.md` 存在、frontmatter 可解析、`name` 与 `description` 非空、文件夹内不含越界 symlink、总大小 ≤ 50 MB。

## 组装根接线

`surfaces/http/app.py` 调用 `surfaces/http/agent_skill_wiring.py` 中的 `wire_agent_and_skill_kinds(app, resource_svc, audit, sm)`。该函数：

1. 构造 `SkillBindingRepo`、`MasterStore`、`SyncEngine`，以及 `SkillService`（含其 `verify_ops` 协作者）。
2. 通过 `make_skill_kind(...)` 构造 skill `Kind`，注册到 `app.state.kinds["skill"]`。
3. 读取由 `_wire_agent_kind` 已注册的 agent `Kind`，构造一个新的 `Kind`，其 `on_delete` 是一个 closure：先 `await skill_svc.cleanup_bindings_for_agent(ref)`，再委派给原 agent `on_delete`。包装后的 agent kind 覆盖 `app.state.kinds["agent"]` 的旧条目。
4. 挂载 `skill_routes` 路由。

这种 closure 组装让两个 kind 在 application 层互不依赖（彼此都不 import），跨 kind 胶水统一汇聚到组装根。

## 约束小结

- 全部 HTTP 仅 loopback。
- 文件大小上限：每个 skill 文件夹总计 50 MB，由 `validate_skill_folder` 强制。该上限是 `SkillService` 构造函数默认值（`size_limit_bytes`）；目前尚未接到配置文件，因此 v1 始终使用硬编码的 50 MB。
