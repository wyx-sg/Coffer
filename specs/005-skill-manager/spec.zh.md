# 功能规范：Skill Manager

> English: [spec.md](./spec.md)

**Feature Branch**: `feature/skill-manager`
**Created**: 2026-05-22
**Status**: Draft
**Input**: 用户描述：「Coffer 用开放的 AgentSkills 标准（agentskills.io）管理可移植的 AI skill。一份规范副本放在 `~/.coffer/skills/` 下；每个 agent 的可见性通过指向其配置目录下 `skills/` 子文件夹的目录 symlink/junction 实现。用户可以从本地路径导入 skill，或从公开 Git 仓库拉取，然后按 agent 启用或禁用每个 skill。v1 支持 Claude Code 与 Codex CLI 作为同步目标（每个 agent 是 spec 004-agent-registry 中 kind 为 `agent` 的 Resource）。」

## 用户场景与测试

### User Story 1 —— 导入已有的 skill 文件夹（优先级 P1）

某开发者已经在 `~/.claude/skills/` 或其他位置存了一些 skill。他想把这些 skill 纳入 Coffer 管理，以便跨 agent 复用并统一管理。

**为什么是这个优先级**：迁移既有资产是大多数用户上手的第一需求。没有导入功能，Coffer 就没有 skill 可以管理。

**独立可测**：在命令行导入一个已有的 skill 文件夹；验证规范副本出现在 `~/.coffer/skills/<name>/`；验证 `coffer skill list` 中可见该 skill。

**代表性场景**：

- 导入一个有效的 skill 文件夹
- 当 SKILL.md 缺失或 frontmatter 无效时拒绝导入
- 重名时拒绝导入
- 含有越界 symlink 的文件夹拒绝导入

---

### User Story 2 —— 从 Git URL 拉取 skill（优先级 P1）

开发者在某公开 GitHub 仓库里看到一个 skill，想把它拉进 Coffer。

**为什么是这个优先级**：AgentSkills 生态本就强调分享，URL 拉取是主要分发渠道。少了这个能力，用户只能用自己写的 skill。

**独立可测**：在命令行拉取一个已知的公开 skill 仓库（含 subpath）；验证创建出来的规范副本 `source.type=git`；验证 URL、ref、subpath 都被持久化。

**代表性场景**：

- 按 URL + ref + subpath 拉取公开 Git skill 仓库
- 拒绝 SSRF 攻击（loopback / 私网地址）
- v1 拒绝私有仓库
- 拉取下来未能通过 SKILL.md 校验的内容被拒绝

---

### User Story 3 —— 把 skill 对特定 agent 启用（优先级 P1）

开发者希望某个 skill 在 Claude Code 中可用，但在 Codex 中不要。他按 agent 启用后，Coffer 在该 agent 配置目录的 `skills/` 子文件夹下创建目录 symlink。

**为什么是这个优先级**：这是「统一管理」的核心价值。没有按 agent 的启停，Coffer 与手工拷贝文件没本质区别。

**独立可测**：注册一个 Claude Code agent（按 spec 004）；导入一个 skill；为该 agent 启用；验证 `<config_dir>/skills/<skill-name>` 下出现指向 `~/.coffer/skills/<skill-name>/` 的目录 symlink。

**代表性场景**：

- 为已注册 agent 启用一个 skill
- 为某 agent 禁用一个 skill（symlink 移除，master 不动）
- 同一个 skill 为多个 agent 启用（一份 master，多份 symlink）
- 目标路径已存在非 Coffer 文件时拒绝覆盖，除非加 `--force`

---

### User Story 4 —— 从源头更新 skill（优先级 P2）

开发者想拉到一个 Git 源 skill 的最新版。

**为什么是这个优先级**：没有更新能力，拉下来的 skill 会变陈旧，用户会失去信任。

**独立可测**：拉一个 Git skill；调高其上游内容；运行 `coffer skill update`；验证 master 内容已变化，所有已启用的 agent 在下次读取时都能看到新版本。

**代表性场景**：

- 把 Git 源 skill 更新到新的上游内容
- 检测并告警两次版本之间 SKILL.md frontmatter 的 `name` 变化
- 内容未变时为 no-op 更新

---

### User Story 5 —— 检测并报告 drift（优先级 P2）

agent 的 `config_dir/skills` 文件夹可能被外部篡改（删除、替换、编辑）。开发者需要看到当前哪里和 Coffer 不一致，然后自己决定怎么处理。

**为什么是这个优先级**：用户对同步引擎的信任来自「不一致时能讲清楚」。

**独立可测**：手动删除某 agent 的 `config_dir/skills` 文件夹下的一个 symlink；运行 `coffer skill verify`；观察 drift 报告把该 missing link 列出，并附建议处置方式。

**代表性场景**：

- 检测到目标位置 link 缺失
- 检测到 link 被篡改（变成普通文件，或 symlink 指向了别的目标）
- 检测到 master 文件夹缺失
- 检测到 orphan master（磁盘上存在 master 文件夹但 DB 中无记录）
- 不在用户明确指令下自动修复

---

### User Story 6 —— 在桌面 App 中管理 skill（优先级 P2）

用户打开 Coffer，看到以数据表呈现的 Skills 页（搜索、筛选、分页、行多选以执行批量操作），可以通过文件选择器导入或粘贴 Git URL 拉取，并浏览列表。Skills 页只管理 skill 资源本身，不管理它的按 agent binding：点击某个 skill 打开详情视图，其中有一个 Overview 元信息 tab 与一个只读的 Files tab（文件树 + 文件查看器）。按 agent 的启用/禁用在 agent 详情页上进行——该 agent 的「Skills」tab 列出绑定到该 agent 的 skill，并带每条 binding 的开关。

**为什么是这个优先级**：非 CLI 用户需要一个可视化日常管理面板。

**独立可测**：打开桌面 App → Skills → 用文件选择器导入一个文件夹 → 在表格中看到它 → 打开 agent 详情页 → 它的 Skills tab → 把该 skill 对该 agent 切到 enabled → 验证 symlink 已落盘。

**代表性场景**：

- 通过桌面文件选择器导入 skill
- 通过桌面 URL 表单拉取 skill
- 通过桌面切换控件按 agent 启停
- 通过 UI 通知呈现 drift 数

---

### User Story 7 —— 命令行覆盖同等操作（优先级 P2）

开发者用 `coffer skill ...` 子命令配合 `--json` 输出，在多台机器上脚本化 skill 配置。

**独立可测**：一段 bash 脚本完成「导入一个 skill、再拉一个、为两个 agent 各启用、列出状态、跑一次 verify」全过程，无需 GUI。

**代表性场景**：

- 命令行覆盖每一个可视化操作
- 机器可读的 JSON 输出

---

### User Story 8 —— 干净地移除 skill（优先级 P3）

开发者删除一个 skill 时，每个 agent 的 symlink 都要被清掉，master 文件夹也要被删除。

**为什么是这个优先级**：留下残留 symlink 的删除会悄悄迷惑 agent。

**独立可测**：把某 skill 对两个 agent 启用；删除该 skill；验证两个目标 symlink 都被清除，master 文件夹已被删除。

**代表性场景**：

- 移除带有 active binding 的 skill
- 在审计中以快照方式记录此次移除

---

### User Story 9 —— 审计 skill 全生命周期（优先级 P3）

每一次导入、拉取、启用、禁用、更新、移除都可审计。

**独立可测**：跑一遍代表性操作序列；查看审计日志；每个变更一行，含 actor、target、event type。

**代表性场景**：

- 审计导入、拉取、启用、禁用、更新、移除

---

### Edge Cases

- **导入时 skill 重名**：拒绝；用户必须先在 SKILL.md frontmatter 里改名再试。
- **更新时 frontmatter 中的 `name` 变了**：默认拒绝；`--allow-rename` 触发对 master 文件夹的原子重命名，并重建所有已启用的 symlink。审计日志保留每条历史事件原始的名字；当前 Resource 行记录改名后的新名字。
- **master 文件夹超过大小上限（默认 50 MB）**：导入或拉取被拒，错误信息包含上限值与调整方式提示。
- **Git 拉取遇到私有仓库或需鉴权的 URL**：拒绝；v1 不处理上游 skill 源的凭据。
- **Git 拉取目标不可达 / DNS 失败 / 超时**：操作干净地失败，返回网络错误；不会留下半写的 master 文件夹，也不会留下 DB 记录。
- **Windows 下 symlink/junction 创建失败（FAT32 或网络共享）**：该目标降级为复制模式，审计带 `degraded=true`；UI 显示警告标记。
- **用户在某 agent 的 `config_dir/skills` 文件夹内编辑 SKILL.md**：由于 agent 路径是指向 master 的 symlink，该编辑实际落在 master 上，其他 agent 下次读取时即可见；不会被识别为 drift。
- **用户从某 agent 的 `config_dir/skills` 文件夹内删除一个由 Coffer 管理的文件**：同样会作用到 master；下次 `verify` 会标记其他 agent 上对应 link 是否仍能一致解析。
- **移除一个还带 skill binding 的 agent（spec 004）**：spec 004 定义了 agent kind 的 `on_delete` 接缝；the 005-skill-manager spec 在组装根处提供 `cleanup_bindings_for_agent` 回调，先清掉该 agent 的所有 binding 与 symlink，再删掉 agent 行本身。
- **agent 的 `config_dir` 在外部被移走或删除**：下一次同步操作会暴露失败；`verify` 报告受影响的 binding；用户通过更新 agent 的 `config_dir` 或移除该 agent 来处置。

## Acceptance Scenarios

按 `agents/sdd.md`，本节每一个 scenario 都至少被一个带 `@pytest.mark.acceptance(spec="005-skill-manager", scenario="…")`（Python）或 `acceptance("005-skill-manager", "…", …)`（TypeScript）标记的测试引用。

### Scenario: 导入合法的本地 skill 文件夹

- **Given** daemon 在运行，且不存在名为 `my-skill` 的 skill，
- **When** 用户导入一个 SKILL.md frontmatter `name: my-skill` 的文件夹，
- **Then** Coffer 把文件夹拷贝到 `~/.coffer/skills/my-skill/`，写入一条 kind 为 `skill` 的 Resource，并写一条审计记录。

### Scenario: 拒绝导入不合法的 skill 文件夹

- **Given** daemon 在运行，
- **When** 用户导入一个缺 SKILL.md 或 `name`/`description` frontmatter 为空的文件夹，
- **Then** 请求被明确拒绝，`~/.coffer/skills/` 与数据库都不会被写入任何东西。

### Scenario: 拒绝含有越界 symlink 的导入

- **Given** daemon 在运行，
- **When** 用户导入一个 symlink 解析到文件夹外的目录，
- **Then** 请求被拒绝并列出越界路径，不持久化任何东西。

### Scenario: 拉取公开 Git skill 仓库

- **Given** daemon 在运行，且某公开 Git URL 在已知 subpath 处提供合法 skill，
- **When** 用户运行 `coffer skill fetch <url> --ref <ref> --subpath <path>`，
- **Then** Coffer 做 shallow clone、校验 SKILL.md、把该 subpath 拷贝到 `~/.coffer/skills/<name>/`，并持久化 `source.type=git` 与 `git_url`/`git_ref`/`git_subpath`。

### Scenario: 拒绝 SSRF 拉取

- **Given** daemon 在运行，
- **When** 用户尝试从 loopback 或 RFC1918 URL 拉取，
- **Then** SSRF guard 在任何网络往返之前直接拒绝该请求。

### Scenario: 把 skill 对已注册 agent 启用

- **Given** agent `claude_code` 已按 spec 004 注册，且 skill `my-skill` 已被导入，
- **When** 用户为 `claude_code` 启用 `my-skill`，
- **Then** 在 `<config_dir>/skills/my-skill` 处创建一个指向 `~/.coffer/skills/my-skill/` 的目录 symlink（Windows 上是 junction），同时写入一行 `skill_agent_bindings` 记录该 link。

### Scenario: 把 skill 对某 agent 禁用

- **Given** 某 skill 已对某 agent 启用，且目标 symlink 已存在，
- **When** 用户对该 agent 禁用该 skill，
- **Then** symlink 被移除，binding 被标记为 disabled，master 文件夹不变。

### Scenario: 对多个 agent 启用

- **Given** 两个 agent 已注册，
- **When** 用户为它们都启用同一个 skill，
- **Then** 两条 symlink（每个 agent 各一条）同时存在，都指向同一份 master。

### Scenario: 拒绝覆盖非 Coffer 目标

- **Given** 用户已在目标 link 路径上放了一个普通文件或目录，
- **When** 用户为该 agent 启用某 skill，
- **Then** 操作被拒绝；若加 `--force`，已有目标被备份到 `<path>.coffer-backup-<ts>`，然后再创建 link。

### Scenario: 更新一个 Git 源 skill

- **Given** 某 skill 是从 Git URL 拉取来的，
- **When** 用户运行 `coffer skill update <name>` 且上游已提供不同内容，
- **Then** master 文件夹被原子替换为新内容，写一条审计记录，所有已启用的 agent 在原 symlink 上即可读到新版。

### Scenario: 更新时检测 frontmatter 改名

- **Given** 某次更新会改动 SKILL.md frontmatter 的 `name`，
- **When** 用户运行 update 时未加 `--allow-rename`，
- **Then** 更新被拒绝并在错误信息中告知新名字；若加 `--allow-rename`，master 文件夹被重命名，所有已启用的 symlink 在新名字下被重建。

### Scenario: 检测 agent skill 目录中的 drift

- **Given** 某 binding 存在但其磁盘目标已被删除、被替换或被重指向，
- **When** 用户运行 `coffer skill verify`，
- **Then** 报告按 drift 类别列出每条与建议处置方式，并以非零 exit code 退出；不做自动修复。

### Scenario: 移除 skill 清理所有 binding

- **Given** 某 skill 已对两个 agent 启用，
- **When** 用户移除该 skill，
- **Then** 两个目标 symlink 都被移除，bindings 被级联删除，master 文件夹被删除，并写一条带 config 快照的审计记录。

### Scenario: 移除 agent（按 spec 004）时清理其 skill binding

- **Given** 某 agent 当前有若干已启用 skill，
- **When** 用户移除该 agent，
- **Then** spec 004 中 agent kind 的 `on_delete` 钩子调用 skill 模块，先移除该 agent 的每条 binding 与对应 symlink，再删除 agent 行；master 文件夹保持不变。

### Scenario: 桌面与 CLI 覆盖每一项操作

- **Given** daemon 在运行，
- **When** 用户在桌面与 `coffer skill ...` 中分别执行每一项操作，
- **Then** 两个 surface 产生相同效果，且 CLI 的读类操作均支持 `--json`。

### Scenario: 审计 skill 全生命周期

- **Given** 用户跑完一组代表性操作，
- **When** 他查看审计日志，
- **Then** 每一个事件都带时间戳、actor、target、event type 与必要的 payload（如更新前后的内容哈希）。

### Scenario: view a skill's files as a tree（以树形查看 skill 的文件）

- **Given** 一个已导入的 skill，其 master 文件夹含 `SKILL.md` 及一个内含文件的嵌套子目录，
- **When** 用户请求该 skill 的文件列表，
- **Then** Coffer 返回以 master 文件夹为根的递归只读树，每个节点带 name、相对路径、type（`file`/`dir`）、文件大小与 children，按目录优先再按名称排序，且不包含任何越界 symlink 目标。

### Scenario: view a single skill file's contents（查看单个 skill 文件内容）

- **Given** 一个含可读文本文件的已导入 skill，
- **When** 用户按相对路径请求该文件内容，
- **Then** Coffer 返回该文件文本、真实字节大小，以及 `binary=false`/`truncated=false`；不存在的路径返回 not-found 错误。

### Scenario: reject reading a path outside the skill folder（拒绝读取 skill 文件夹之外的路径）

- **Given** 一个已导入的 skill，
- **When** 用户请求一个解析后位于 master 文件夹之外的路径（`..` 穿越、绝对路径或越界 symlink）的文件内容，
- **Then** 请求在任何文件被读取前以 `400` 错误拒绝，且不返回任何内容。

## Requirements

### Functional Requirements

**Resource 模型**

- **FR-001**：系统必须把每个被管理的 skill 注册为 kind 为 `skill` 的 Resource，按 `skill:<name>` 标识，`<name>` 来自 SKILL.md frontmatter。
- **FR-002**：系统必须按 kind 专属 schema 校验 skill 配置：字段含 `source`（变种：`local_import` | `git`）、`skill_md_name`、`skill_md_description`、`version_hash`、`last_synced_from_source_at`。

**规范存储**

- **FR-003**：系统必须把每个被管理 skill 的内容存到 `~/.coffer/skills/<name>/`，并以此为唯一可编辑的事实来源。
- **FR-004**：系统必须按 AgentSkills 规范校验每一个被导入或拉取的 skill 文件夹：存在 `SKILL.md`、frontmatter `name` 与 `description` 非空、不含越界 symlink、总大小不超过可配置上限（默认 50 MB）。

**源**

- **FR-005**：系统必须支持从本地路径导入 skill；原始源路径仅作为 provenance 记录，不会被持续依赖。
- **FR-006**：系统必须支持从公开 Git URL 拉取 skill（带 ref 与可选 subpath），通过 SSRF guard 客户端做 shallow clone（遵循 Coffer constitution）。
- **FR-007**：v1 必须拒绝需要鉴权的 Git URL；私有仓库支持留给后续规范。

**按 agent 投递**

- **FR-008**：每对 `(skill, agent)` binding 记录在 `skill_agent_bindings` 表，包含 enabled 与 last successful link path。
- **FR-009**：启用一个 binding 必须在 `<config_dir>/skills/<skill-name>` 创建一个指向 `~/.coffer/skills/<skill-name>/` 的目录 symlink（POSIX）或目录 junction（Windows）。
- **FR-010**：禁用一个 binding 必须移除目标 link，不动 master。
- **FR-011**：启用时若目标位置已存在非 Coffer 目标，未加 `--force` 则拒绝；`--force` 在创建 link 前先备份既有目标。
- **FR-012**：当符号链接/目录 junction 不可用（如 FAT32、网络共享）时，系统可降级为复制模式；绑定记录 `link_mode=copy_fallback`（enable 事件审计为 `mode: copy_fallback`），UI 必须呈现该降级状态（Agent 的 Skills 标签页对此类绑定显示 "已复制" 警示徽标）。

**更新**

- **FR-013**：系统必须支持按用户指令刷新 Git 源 skill；本地导入的 skill 应通过重新导入而非更新来刷新。
- **FR-014**：系统必须检测并拒绝改动 SKILL.md frontmatter `name` 的更新，除非用户传 `--allow-rename`；该开关触发对 master 文件夹的原子重命名与所有已启用 symlink 的重建。

**Drift**

- **FR-015**：系统必须提供 `verify` 操作，对每条已启用 binding 比对其磁盘目标，并按 drift 类别（missing link、tampered link、missing master、orphan master）报告与建议处置方式。
- **FR-016**：系统不得自动修复 drift；修复必须由用户显式触发。

**生命周期**

- **FR-017**：移除一个 skill 必须移除每个 agent 的 symlink、级联删除 binding、删除 master 文件夹，并以快照方式写入审计。
- **FR-018**：移除 agent（按 spec 004）必须触发 skill 模块的 `on_delete` 钩子，先移除该 agent 的 binding 与 symlink，再删除 agent 行。

**Surface**

- **FR-019**：每一项管理操作必须可通过（a）REST API、（b）`coffer skill ...` CLI（含 `--json`）、（c）桌面 Skills 页 三种 surface 完成。
- **FR-021**：系统必须提供 skill master 文件夹的只读视图：一棵递归文件树（name、相对路径、type、size、children）以及单个文件的内容。读取必须限制在 master 文件夹内——任何解析后位于其外的路径（`..` 穿越、绝对路径或越界 symlink）必须被拒绝。文件读取必须做大小上限（超限时截断并带 `truncated` 标记），并把非 UTF-8 / 含 NUL 字节的文件标记为 binary 且内容为空。不做任何写入，不跟随越界 symlink。

**可观测**

- **FR-020**：系统必须为每一次导入、拉取、启用、禁用、更新、改名、移除与 drift 修复事件写入一条审计记录。

### Key Entities

- **Skill**：kind 为 `skill` 的 Resource，按 `skill:<name>`（name 来自 SKILL.md frontmatter）标识。承载源 provenance、内容哈希、元数据；内容文件夹位于 `~/.coffer/skills/<name>/`。
- **Skill Source**：判别式记录（`local_import` 或 `git`），描述 skill 来源。Git 包含 URL、ref、可选 subpath；本地导入仅含原始路径作 provenance 用。
- **Skill–Agent Binding**：连接一个 skill Resource 与一个 agent Resource（kind `agent`，按 spec 004）的一行；带 `enabled` 标志与最近 link path。磁盘上的 symlink 是 live 表达；binding 是持久化表达。
- **Drift Report**：`verify` 返回的瞬时结构，列出每条与磁盘不一致的 binding，附 drift 类型与建议处置方式。

## Success Criteria

### Measurable Outcomes

- **SC-001**：从零安装开始，用户可在 60 秒内完成「导入既有 `~/.claude/skills/<one-skill>/`、对自动检测到的 Claude Code agent 启用、达到 ready 状态」。
- **SC-002**：拉取一个 1-MB 的公开 Git skill（含校验与拷贝）在正常家庭网络下 10 秒内完成。
- **SC-003**：把一个 skill 对两个 agent 启用产生两条合法的目录 symlink（Windows 上为 junction），两个 agent 的读取进程看到同样的 SKILL.md 内容。
- **SC-004**：手动删掉某 agent 侧的一条 symlink 后，`coffer skill verify` 必须在 5 秒内识别为 drift，并以非零 exit code 退出。
- **SC-005**：删除一个对两个 agent 启用的 skill 后，磁盘上无残留 symlink、无残留 master 文件夹，DB 中无孤儿 binding 行。
- **SC-006**：本规范每一个 Acceptance Scenario 都至少被一个带 `acceptance(spec="005-skill-manager", scenario="…")` 的测试覆盖，`make verify-acceptance` 报告 0 个未覆盖 scenario。
- **SC-007**：全套 `make verify` 在本地与 CI 通过；`make verify-all`（含 e2e）在 macOS 与 Linux 通过；Windows 在 junction 模式与 copy-fallback 模式下分别通过。
- **SC-008**：除用户显式拉取已知公开 URL 的情形外，SKILL.md 内容永不离开用户机器；由集成测试中的网络出站扫描自动验证。

## Assumptions

- spec 004-agent-registry 已上线（PR #25）；agent kind 及其 CRUD、审计、`on_delete` 钩子均已可用。
- spec 001-mcp-gateway 引入的 kind-agnostic Resource 框架、审计日志与 `<kind>:<name>` 标识方案已就位。
- spec 002-ui-shell 的应用外壳——侧栏 IA、布局、路由骨架、设计系统——已就位；桌面 Skills 页是渲染在该外壳之上的功能 surface，填上 002-ui-shell 预留的 `/skills` 导航位。
- skill 遵循开放 AgentSkills 标准（SKILL.md 至少含 `name`/`description` frontmatter，见 agentskills.io）；不符合规范的文件夹不在本规范处理之列。
- v1 仅支持公开 Git URL；需鉴权的上游 skill 源留给后续工作。
- 本地导入的 skill 是时间点拷贝；原路径仅用于追溯，不用于同步。
- Windows 用户的文件系统支持目录 junction；FAT32 与网络共享降级为 copy 模式。
- v2 将探索：marketplace 浏览（agentskills.io API）、agent 间的 skill 推荐、项目级 skill（仓库内 `.claude/skills/`）、通过 credential ref 支持私有 Git 源。
