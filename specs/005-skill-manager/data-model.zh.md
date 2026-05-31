# Data Model —— 005 Skill Manager

> English: [data-model.md](./data-model.md)

skill manager 的实体、字段、关系与 SQLite schema 增量。建立在 spec 004 的 agent kind 与 spec 001 的 kind-agnostic Resource 框架之上。

## Domain 实体（`backend/coffer/domain/skill/`）

### `SkillSource` (`domain/skill/source.py`)

判别式 Pydantic 联合，记录被管理 skill 的来源。

```
SkillSource = Annotated[LocalImportSource | GitSource, Discriminator("type")]
```

#### `LocalImportSource`

| 字段            | 类型                      | 说明                             |
| --------------- | ------------------------- | -------------------------------- |
| `type`          | `Literal["local_import"]` | 判别字段                         |
| `original_path` | `str`                     | 仅信息性记录；不作为持续依赖保留 |

#### `GitSource`

| 字段          | 类型             | 说明                                            |
| ------------- | ---------------- | ----------------------------------------------- |
| `type`        | `Literal["git"]` | 判别字段                                        |
| `git_url`     | `HttpUrl`        | 必须通过 SSRF guard（按 spec 001 constitution） |
| `git_ref`     | `str`            | 分支 / 标签 / commit ref，例如 `main`           |
| `git_subpath` | `str`            | 相对仓库根的子路径；位于根目录时为 `""`         |

### `SkillConfig` (`domain/skill/config.py`)

Pydantic v2 `BaseModel`。

| 字段                         | 类型               | 说明                                                 |
| ---------------------------- | ------------------ | ---------------------------------------------------- |
| `source`                     | `SkillSource`      | 判别式联合                                           |
| `skill_md_name`              | `str`              | SKILL.md frontmatter 的 `name`；等于 `Resource.name` |
| `skill_md_description`       | `str`              | frontmatter 的 `description`                         |
| `version_hash`               | `str`              | 上次同步时 SKILL.md 内容的 sha256                    |
| `last_synced_from_source_at` | `datetime \| None` | UTC；在 import/fetch/update 时写入                   |

### `SkillFrontmatter` (`domain/skill/frontmatter.py`)

Pydantic v2 模型，用于校验导入/拉取下来的文件夹。对齐 agentskills.io 的最小集：`name`、`description`；额外字段以 `extra='allow'` 容忍。

frontmatter 的 `description` 持久化在 skill kind 自己的 config 字段 `SkillConfig.skill_md_description` 中 —— 这是权威拷贝，frontmatter 改名也会覆盖它。`resources` 表自身的 `description` 列继承自 kind-agnostic Resource 框架；在 import/fetch 时从 frontmatter `description` 初始化以与其他 kind 保持一致，但**不**在后续 update 时重新同步（视作初次写入后用户可自由编辑的人类标签）。

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
| `missing_master`        | binding 指向的 master 文件夹已不在  | 重新导入或拉取               |
| `orphan_master`         | 磁盘上有 master 但 DB 无记录        | 收编或移除                   |

## SQLite schema 增量

迁移 `20260526_0006_skill_tables.py`（独立；spec 004 自带 `20260525_0005_agent_tables.py`）新增：

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

| 值                     | 触发时机                                    |
| ---------------------- | ------------------------------------------- |
| `skill_imported`       | 本地导入成功                                |
| `skill_fetched`        | Git 拉取成功                                |
| `skill_updated`        | Git 更新有内容变化（details 含前后哈希）    |
| `skill_update_noop`    | update 检查后无变化                         |
| `skill_renamed`        | 带 `--allow-rename` 完成的 frontmatter 改名 |
| `skill_removed`        | skill Resource 被删除（details 含快照）     |
| `skill_bound`          | 按 agent 启用 binding（创建 symlink）       |
| `skill_unbound`        | 按 agent 禁用 binding（移除 symlink）       |
| `skill_drift_detected` | `verify` 报告 drift（details 含计数与类别） |

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

`.coffer.meta.json` 复制 `SkillConfig` 的一个子集，用于 DB 丢失时的取证恢复。该文件由 `MasterStore` 在 master 内容拷贝/替换完成后立即写入（即 import、fetch、update 流程末尾），并在之后每次成功同步时就地重写。Coffer 运行时**不**读取这个文件；DB 才是权威，发生分歧以 DB 为准。

持久化的 key：

| Key                          | 来源                                     | 说明                             |
| ---------------------------- | ---------------------------------------- | -------------------------------- |
| `source`                     | `SkillConfig.source`（判别式）           | 含 `type` 与各变种字段的完整联合 |
| `skill_md_name`              | `SkillConfig.skill_md_name`              | 写入时与 master 文件夹名一致     |
| `skill_md_description`       | `SkillConfig.skill_md_description`       |                                  |
| `version_hash`               | `SkillConfig.version_hash`               | 上次同步时 SKILL.md 的 sha256    |
| `last_synced_from_source_at` | `SkillConfig.last_synced_from_source_at` | ISO-8601 UTC                     |

每个 agent 的 symlink 目标位于：

```
<config_dir>/skills/<skill-name>  → symlink/junction 指向  ~/.coffer/skills/<skill-name>
```

## Application 服务契约（`backend/coffer/application/skill/`）

### `SkillService`

| 方法                                                           | 用途                                                                                                     |
| -------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `import_local(path, actor) -> Resource`                        | 读 SKILL.md，校验，拷到 master，注册 Resource，写审计，返回。自动为每个已注册 agent 绑定（trust 模式）。 |
| `fetch_git(url, ref, subpath, actor) -> Resource`              | SSRF guard shallow clone，校验，拷贝，注册。自动 bind。                                                  |
| `update(ref, allow_rename=False, actor) -> UpdateOutcome`      | 重新拉取 Git 源，对比哈希，有变化时原子替换 master；改名时除非加开关，否则拒绝。                         |
| `enable_for(skill_ref, agent_ref, force=False, actor) -> None` | upsert binding，创建 symlink（FAT32 上 copy fallback）。                                                 |
| `disable_for(skill_ref, agent_ref, actor) -> None`             | 标记 binding 为 disabled，移除 link。                                                                    |
| `verify() -> DriftReport`                                      | 遍历每条已启用 binding，按 `DriftKind` 分类 drift。                                                      |
| `remove(ref, actor) -> None`                                   | 级联清理 symlink、删除 master，委派 `ResourceService.delete`。                                           |
| `cleanup_bindings_for_agent(agent_ref) -> None`                | 由 spec 004 的 `agent.on_delete` 钩子调用；移除该 agent 的所有 binding 与 symlink。                      |

### 文件查看器（`application/skill/file_ops.py`）

紧邻 `service.py` 的只读、无状态辅助函数（与 `verify_ops.py` / `update_ops.py`
同一模式），向 surface 暴露 skill 的 master 文件夹。无 DB、无审计、无写入；
containment 通过解析每个候选路径并要求其位于解析后的 master 文件夹内来强制，
沿用 `domain/skill/validator.py` 的越界路径检查方式。

| 函数                                                     | 用途                                                                                                 |
| -------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `build_file_tree(master_folder) -> FileNode`             | 递归列出 master 文件夹；跳过真实目标越界的 symlink；不跟进 symlink 目录。                            |
| `read_skill_file(master_folder, relpath) -> FileContent` | 解析 `master_folder/relpath`，校验其位于文件夹内（否则 `ValueError`），带大小上限读取并检测 binary。 |

#### 文件节点结构（`FileNode` / `SkillFileNodeOut`）

递归树中的一个节点。根节点的 `path == ""`。

| 字段       | 类型              | 说明                                           |
| ---------- | ----------------- | ---------------------------------------------- |
| `name`     | `str`             | 条目的基名                                     |
| `path`     | `str`             | 相对 master 文件夹根的 POSIX 路径（根为 `""`） |
| `type`     | `"file" \| "dir"` | 节点类型                                       |
| `size`     | `int \| None`     | 文件为字节大小；目录为 `null`                  |
| `children` | `list[FileNode]`  | 目录有值（目录优先再按名称排序）；文件为 `[]`  |

#### 文件内容结构（`FileContent` / `SkillFileContentOut`）

单个文件的只读内容。

| 字段        | 类型   | 说明                                         |
| ----------- | ------ | -------------------------------------------- |
| `path`      | `str`  | 相对 master 文件夹根的 POSIX 路径            |
| `content`   | `str`  | 文件文本；`binary` 为真时为空（`""`）        |
| `truncated` | `bool` | 文件超出 256 KiB 读取上限、仅返回前缀时为真  |
| `binary`    | `bool` | 文件非 UTF-8 或含 NUL 字节时为真（内容为空） |
| `size`      | `int`  | 磁盘上文件的真实字节大小（与是否截断无关）   |

### `SourceFetcher` (`infrastructure/skill/source_fetcher.py`)

提供 `fetch_git(url, ref, subpath) -> Path`：返回一个临时目录，里面是位于 `subpath` 的克隆内容。通过 `git` 子进程调用并先做 SSRF guard：在发起 `git clone --depth=1 --branch=<ref> --filter=blob:none` 之前校验 URL host 不是 loopback / RFC1918 / link-local。

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

1. 构造 `SkillBindingRepo`、`MasterStore`、`SyncEngine`、`SourceFetcher`，以及 `SkillService`（含其 `update_ops` / `verify_ops` 协作者）。
2. 通过 `make_skill_kind(...)` 构造 skill `Kind`，注册到 `app.state.kinds["skill"]`。
3. 读取由 `_wire_agent_kind` 已注册的 agent `Kind`，构造一个新的 `Kind`，其 `on_delete` 是一个 closure：先 `await skill_svc.cleanup_bindings_for_agent(ref)`，再委派给原 agent `on_delete`。包装后的 agent kind 覆盖 `app.state.kinds["agent"]` 的旧条目。
4. 挂载 `skill_routes` 路由。

这种 closure 组装让两个 kind 在 application 层互不依赖（彼此都不 import），跨 kind 胶水统一汇聚到组装根。

## 约束小结

- 全部 HTTP 仅 loopback。
- Git 拉取经 SSRF guard URL 谓词（拒绝 loopback / RFC1918 / link-local）。
- v1 无 keychain 条目（skill 源不带鉴权）。
- 单 skill 文件大小上限（默认 50 MB）可通过 `~/.coffer/daemon.json` 配置；v1 出厂使用默认值。
