# 实施计划：005 —— Skill Manager

> English: [plan.md](./plan.md)

**Branch**: `feature/skill-manager`（基于 spec 004-agent-registry，已在 PR #25 中交付）
**Date**: 2026-05-22
**Spec**: [./spec.md](./spec.md)
**Status**: Draft

## 摘要

向 Coffer 加入 `skill` 这一 Resource kind：一份按 agentskills.io 标准管理的 skill 文件夹清单，规范副本放在 `~/.coffer/skills/<name>/`，通过目录 symlink（POSIX）或 junction（Windows）投递到已注册的 agent（spec 004）。v1 的源支持本地路径导入与公开 Git URL。每对 (skill × agent) binding 提供细粒度选择。`verify` 操作检测磁盘 drift。一并交付 REST 路由、CLI 子命令与桌面 Skills 页。

## 技术上下文

| 维度             | 取值                                                                                             |
| ---------------- | ------------------------------------------------------------------------------------------------ |
| **语言 / 版本**  | Python 3.12+，TypeScript 5.x                                                                     |
| **新运行时依赖** | 无（沿用 spec 001 的 `httpx` + `git` subprocess）。                                              |
| **存储**         | SQLite（`skill_agent_bindings`）；用户内容存于 `~/.coffer/skills/`。                             |
| **测试**         | 4 层；acceptance 标记绑定到 scenario。                                                           |
| **目标平台**     | macOS arm64+x64、Windows x64、Linux x64+arm64                                                    |
| **性能目标**     | 本地导入 1 MB skill ≤ 1 秒。正常家庭网络下 Git 拉取 1 MB skill ≤ 10 秒。按 agent 启用 ≤ 100 ms。 |
| **约束**         | local-first；SSRF guard 拉取；v1 不存任何凭据；保留分层架构。                                    |
| **规模**         | 每个用户 ≤ 200 个被管理 skill；最差情况 ≤ 8 agent × 200 = 1600 binding。                         |

## Constitution 检查

| 条款                   | 合规 | 说明                                                                                                              |
| ---------------------- | ---- | ----------------------------------------------------------------------------------------------------------------- |
| I. Local-First         | ✅   | 规范副本在本地；无云端事实记录方。拉取由用户触发并写审计。                                                        |
| II. Spec-as-Truth      | ✅   | spec 先于代码提交。                                                                                               |
| III. Open-Source-Ready | ✅   | 不新增闭源依赖。                                                                                                  |
| 语言                   | ✅   | Python + TypeScript。                                                                                             |
| 架构：分层             | ✅   | sync engine、master store、source fetcher 均在 infrastructure；application 不依赖 infra 实现。                    |
| 持久化                 | ✅   | 控制面用 SQLite（binding）；skill 内容按文件保存（与 constitution 的「bulk user content stored as files」一致）。 |
| 凭据                   | ✅   | v1 无凭据。私有仓库源未来再引入 credential ref。                                                                  |
| 网络默认               | ✅   | HTTP API 仅 loopback；出站 git 拉取经 SSRF guard URL 谓词。                                                       |

## 项目结构

### 文档

```
specs/005-skill-manager/
  spec.md
  plan.md              (本文件)
  data-model.md
  contracts/api.openapi.yaml
  quickstart.md
```

### 新增后端模块

```
backend/coffer/domain/skill/
  __init__.py
  source.py            # 判别式联合 LocalImportSource | GitSource
  config.py            # SkillConfig（Pydantic）
  frontmatter.py       # SKILL.md frontmatter Pydantic 模型
  validator.py         # AgentSkills 规范校验器（纯函数）
  binding.py           # BindingState dataclass
  drift.py             # DriftKind enum + DriftEntry/DriftReport

backend/coffer/application/skill/
  __init__.py
  service.py           # SkillService 门面（import/fetch/enable/disable/remove）
  update_ops.py        # 从 service 拆出来的 update 流
  verify_ops.py        # 从 service 拆出来的 drift 校验流
  ports.py             # service 依赖的 protocol
  kind.py              # make_skill_kind(...) -> Kind

backend/coffer/infrastructure/skill/
  __init__.py
  persistence.py       # SkillBindingRepo（SQLAlchemy）
  master_store.py      # ~/.coffer/skills/ 布局辅助 + 原子替换
  sync_engine.py       # 跨平台目录链接辅助（POSIX/Windows）
  source_fetcher.py    # 经 SSRF guard 的 git clone 辅助
  ssrf_guard.py        # host 谓词（loopback / RFC1918 / link-local 拒绝）

backend/coffer/infrastructure/persistence/migrations/versions/
  20260526_0005_skill_tables.py   # skill_agent_bindings（revision 0005，down_revision 0004）

backend/coffer/surfaces/http/skill_routes.py
backend/coffer/surfaces/http/agent_skill_wiring.py    # 跨 kind 组装（agent on_delete → skill 清理）
backend/coffer/surfaces/cli/skill_cmd.py
```

### 新增前端模块

```
frontend/src/pages/SkillsPage.tsx
frontend/src/components/skills/
  FetchForm.tsx
  ImportForm.tsx
  SkillTable.tsx            # 按 agent 切换 + drift 提示
frontend/src/lib/api/skills.ts
frontend/src/lib/hooks/useSkills.ts
frontend/src/i18n/locales/{en,zh}.json     # skill 文案追加
```

## 分阶段

### Phase 0 —— 调研（在会话中已收口）

- 投递机制：symlink（POSIX）/ junction（Windows）。拒绝：复制（drift）、配置指针（多数 agent 路径写死）。
- v1 源：本地导入 + 公开 Git URL。Marketplace（agentskills.io）与私有仓库延后。
- 信任模型：导入即等于「对所有已注册 agent 启用」（单用户保险库）。
- Schema：`skill_agent_bindings` 表逐行 binding（拒绝：在 `resources.config` 中存数组）。

### Phase 1 —— 数据模型 + 契约

- 写 data-model.md（完成）与 contracts/api.openapi.yaml（完成）。
- 新增 Alembic 迁移 `20260526_0005_skill_tables.py`（revision `0005`，down_revision `0004`），创建 `skill_agent_bindings`。agent 存在共享的 `resources` 表里，因此 spec 004 不需要 agent-tables 迁移。

### Phase 2 —— 后端实现

1. Domain：`SkillSource` 联合、`SkillConfig`、`SkillFrontmatter`、`AgentSkillsValidator`（纯函数）。在多种 malformed 输入下做单测。
2. Infrastructure：
   - `SyncEngine.make_directory_link / remove_directory_link / classify_target`（跨平台）。
   - `SourceFetcher.fetch_git`：带 SSRF guard 的 shallow clone。
   - `SkillBindingRepo`（SQLAlchemy）。
3. Application：`SkillService`（import/fetch/update/enable/disable/remove/verify/cleanup_bindings_for_agent）。
4. Surface：`skill_routes.py`、`skill_cmd.py` CLI、组装根接线。
5. 跨 spec 接线：`surfaces/http/agent_skill_wiring.py` 暴露 `wire_agent_and_skill_kinds(app, resource_svc, audit, sm)`：构造 skill kind，并用一个 closure 包装 agent kind 的 `on_delete`，先调用 `skill_service.cleanup_bindings_for_agent(ref)`，再委派给原 agent `on_delete`，把包装后的 agent kind 写回 `app.state.kinds["agent"]`。

### Phase 3 —— 测试

- 单元：
  - `AgentSkillsValidator`：缺 SKILL.md、空 frontmatter、越界 symlink、大小上限。
  - `SyncEngine` 跨平台：POSIX `os.symlink`、Windows junction 创建/移除；FAT32 风格失败下的 copy fallback（mock）。
  - `ssrf_guard`：loopback / RFC1918 / link-local 拒绝；公开 host 通过。
  - `SkillConfig` 判别式 round-trip。
- 集成：
  - 导入 → 注册 → 自动 bind → 验证 symlink 已建立。
  - 对两个 agent 启用 → 两条 link 都存在 → 禁用其一 → 仅剩一条。
  - 更新 Git 源（mock clone）→ master 被原子替换。
  - drift 场景（删 link / 用普通文件替换 / 挪走 master）→ `verify` 正确按类别报告。
  - 删除 skill → binding + symlink + master 一并清理。
  - 移除 agent（按 spec 004）→ 该 agent 的 binding + symlink 被清，master 不动。
- 契约：OpenAPI snapshot；CLI `--json` 稳定。
- E2E：在 `tmp_path` 真实文件系统下，使用一个伪造的 `~/.claude/skills/` 风格目标目录作为自动检测到的 agent，整套 import + enable + 通过 link 读 SKILL.md。
- 每个 scenario 各一个 `@pytest.mark.acceptance(spec="005-skill-manager", scenario="…")` 标记。

### Phase 4 —— 前端

- React `SkillsPage`：列表、import 表单、fetch 表单（URL）、按 agent 切换、以及一个 "Verify drift" 操作，通过 UI 通知呈现 drift 数（更花哨的 drift indicator chip 留给后续）。
- i18n 英文 + 简体中文。

## 风险与未知

- **Windows 目录 junction** 在边缘情况（跨卷目标、网络驱动器）下与 symlink 行为不同。CI 矩阵需要覆盖 junction 成功路径与 copy fallback 路径。
- **用户机上 Git 可用性**：v1 要求 `PATH` 上有 `git`。未来可考虑打包 libgit2-bindings。
- **更新时 SKILL.md frontmatter 改名**：原子重建所有 symlink 需要小心 Windows 上 junction 必须先删后建的顺序；方案在单测里覆盖。

## Workspace 修订（在 `feature/agent-workspace` 上交付）

spec.md 的 workspace 修订（FR-022..FR-026）新增了未托管 skill 扫描与
follow-master-library 策略。各层新增模块：

- **Domain**：`skill/scan.py`（纯函数 `classify`，把扫描条目分类为 `UnmanagedSkill` 结果——托管链接与点条目被排除，foreign link 被标记且永不可 adopt）；`agent/scan.py`（属 spec 004 的目录树：按 agent 类型的 `scan_locations`——放在那里是因为它依赖 `AgentType`，而 `domain/skill` 不得 import 它，Contract 5c）。
- **Infrastructure**：`skill/workspace_scan.py`（把扫描位置的文件系统遍历成 `ScanEntry` 值）。
- **Application**：`skill/unmanaged_ops.py`（未托管的 list/adopt/delete，FR-022..FR-024）、`skill/follow_ops.py`（FR-025 follow 调和：开关/排除项/skill 集合变化时触发）、以及 `skill/binding_ops.py`（逐 agent 启用/禁用从 `service.py` 拆出以满足文件大小上限）——全部为 `lifecycle_ops.py` 风格的自由函数。
- **Surfaces**：`http/agent_unmanaged_skill_routes.py`（`/agents/{name}/unmanaged-skills*`）；CLI `coffer skill unmanaged|adopt|rm-unmanaged`（位于 `skill_cmd.py`）与 `coffer agent follow --on/--off --exclude`（位于 `agent_workspace_cmd.py`；策略字段经由 spec 004 的 `PATCH /agents/{name}`）。
- **前端**：`AgentSkillsTab` v2——follow 开关与排除模式下的逐 skill 切换、带 adopt/删除的未托管 skill 区块、foreign-link 与降级 binding 徽标。

新增 audit 事件：`skill_adopted`、`skill_unmanaged_deleted`、
`skill_autobind_skipped`、`skill_relinked`。无 schema 变更——扫描在请求时
派生，follow 策略存于 agent 资源的 config（spec 004）。

## 留给后续规范的开放项

- agentskills.io marketplace 浏览 UI。
- 私有 Git 源 + credential ref。
- 项目级 skill（仓库内 `.claude/skills/`）—— 发现与管理。
- Skill 版本化 / 钉到某个 commit / 多版本共存。
