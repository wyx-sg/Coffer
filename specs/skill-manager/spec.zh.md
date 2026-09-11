# 功能规范：Skill Manager

> English: [spec.md](./spec.md)

**Feature Branch**: `feature/skill-manager`
**Created**: 2026-05-22
**Status**: Accepted
**Input**: 用户描述：「Coffer 用开放的 AgentSkills 标准（agentskills.io）管理可移植的 AI skill。一份规范副本放在 `~/.coffer/skills/` 下；每个 agent 的可见性通过指向其配置目录下 `skills/` 子文件夹的目录 symlink/junction 实现。用户可以从本地路径导入 skill；每个 skill 自己的 `enabled` 标志与 `scope` 决定它被投递给哪些已注册 agent。v1 支持 Claude Code 与 Codex CLI 作为同步目标（每个 agent 是 spec agent-registry-agent-registry 中 kind 为 `agent` 的 Resource）。」

## 用户场景与测试

### User Story 1 —— 导入已有的 skill 文件夹（优先级 P1）

某开发者已经在 `~/.claude/skills/` 或其他位置存了一些 skill。他想把这些 skill 纳入 Coffer 管理，以便跨 agent 复用并统一管理。

**为什么是这个优先级**：迁移既有资产是大多数用户上手的第一需求。没有导入功能，Coffer 就没有 skill 可以管理。

**独立可测**：在命令行导入一个已有的 skill 文件夹；验证规范副本出现在 `~/.coffer/skills/<name>/`；验证 `coffer skill list` 中可见该 skill。

**代表性场景**：

- 导入一个有效的 skill 文件夹
- 当 SKILL.md 缺失或 frontmatter 无效时拒绝导入
- 重名时拒绝导入（除非请求 overwrite）
- 带 overwrite 的重新导入覆盖既有 skill
- 含有越界 symlink 的文件夹拒绝导入

---


### User Story 3 —— 决定一个 skill 能到达哪些 agent（优先级 P1）

开发者希望某个 skill 在 Claude Code 中可用，但在 Codex 中不要。他把该 skill 的 **scope** 设为 `["claude_code"]`，Coffer 就只把它投递到那里——在该 agent 配置目录的 `skills/` 子文件夹下创建目录 symlink——别处一份都没有。之后收窄 scope 会把被排除 agent 手上的副本收回。

**为什么是这个优先级**：这是「统一管理」的核心价值。没有按 agent 的投递授予，Coffer 与手工拷贝文件没本质区别。

**独立可测**：注册一个 Claude Code agent（按 spec agent-registry）；导入一个 scope 指向该 agent 的 skill；验证 `<config_dir>/skills/<skill-name>` 下出现指向 `~/.coffer/skills/<skill-name>/` 的目录 symlink。

**代表性场景**：

- deliver a skill to a registered agent（把一个 skill 投递给已注册 agent）
- reclaim a skill from an agent（从某 agent 收回一个 skill：symlink 移除，master 不动）
- deliver one skill to multiple agents（把同一个 skill 投递给多个 agent：一份 master，多份 symlink）
- refuse to overwrite a non-Coffer target（拒绝覆盖非 Coffer 目标）

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

### User Story 6 —— 在 Web UI 中管理 skill（优先级 P2）

用户打开 Coffer，看到以数据表呈现的 Skills 页（搜索、筛选、分页、行多选以执行批量操作），可以通过文件选择器导入并浏览列表。Skills 页只管理 skill 资源本身，不管理它的按 agent binding：点击某个 skill 打开详情视图，其中有一个 Overview 元信息 tab 与一个 Files tab（文件树 + 一个只读文件查看器：渲染 Markdown，其他文本文件以原文显示）。该查看器不编辑内容；要修改文件，用户在自己的外部编辑器或文件管理器中打开该文件（或其所在文件夹）——每个文件与文件夹都提供「在外部编辑器中打开」「在文件管理器中显示」操作（由本地 daemon 执行）。投递的决定做在 skill 这一侧——它的 `enabled` 开关与它的 scope——因此 agent 详情页只汇报、不决定：该 agent 的「Skills」tab 列出当前已投递给它的 skill，就投递而言是只读的。

**为什么是这个优先级**：非 CLI 用户需要一个可视化日常管理面板。

**独立可测**：打开 Web UI → Skills → 用文件选择器导入一个文件夹 → 在表格中看到它 → 打开该 skill 并把它的 scope 设为某一个 agent → 验证 symlink 已落盘，且该 agent 的 Skills tab 把这个 skill 列为已投递。

**代表性场景**：

- 通过 Web UI 文件选择器导入 skill
- 在 Web UI 中设置 skill 的 scope，并看到已投递集合随之变化
- 通过 UI 通知呈现 drift 数

---

### User Story 7 —— 命令行覆盖同等操作（优先级 P2）

开发者用 `coffer skill ...` 子命令配合 `--json` 输出，在多台机器上脚本化 skill 配置。

**独立可测**：一段 bash 脚本完成「导入 skill、为两个 agent 各启用、列出状态、跑一次 verify」全过程，无需 GUI。

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

每一次导入、投递、收回、移除都可审计。

**独立可测**：跑一遍代表性操作序列；查看审计日志；每个变更一行，含 actor、target、event type。

**代表性场景**：

- 审计导入、投递、收回、移除

---

### User Story 10 —— 呈现并收编非托管 skill（优先级 P2）

agent 会积累 Coffer 从未投递过的 skill——手工拷贝的文件夹、其他工具安装的 skill。今天这些是不可见的：agent 的 Skills tab 只列出 Coffer 托管的 binding。用户打开该 tab，将额外看到在 agent 的 skill 位置发现的**非托管** skill——两种类型都扫 `<config_dir>/skills`，Codex 另加 `~/.agents/skills`（Codex 同样读取的较新标准位置）。Coffer 托管的链接与 Codex 的 `.system` 内部条目被排除。对每个非托管 skill，用户可以**收编**（搬入主库、原位留下托管链接使 agent 继续可见、并记录 binding）或删除。

**为什么是这个优先级**：hub 模型只有在既有资产能流入时才成立。收编就是 User Story 1 的导入，变成一键且就地完成。

**独立可测**：把一个合法 skill 文件夹放进已注册 agent 的 `skills/` 目录；打开该 agent 的 Skills tab；观察它被列为非托管；收编它；验证主库副本存在于 `~/.coffer/skills/<name>/`、原路径现在是托管 symlink、且存在一行 binding。

**代表性场景**：

- list unmanaged skills across an agent's skill locations
- adopt an unmanaged skill into the master store
- reject adopting an invalid or conflicting unmanaged skill
- delete an unmanaged skill
- exclude managed links and system entries from the unmanaged scan

---

### User Story 11 —— 一条规则决定 skill 落在哪里（优先级 P2）

用户不该把投递配置两遍。skill 自己的两个字段就能定下来：`enabled` 决定这个 skill 是否生效，`scope` 决定它到达哪些 agent。刚导入的 skill 没有 scope，因此无需任何按 agent 的设置就到达每个已注册 agent——这就是「配置一次、共享全部」，是 MCP 网关「一个条目服务全部」模型在文件系统侧的对应物。当某个 skill 只属于一处时，用户收窄它的 scope，Coffer 就把被排除 agent 手上的副本收回。当某个 skill 暂时不该到达任何地方时，用户把它禁用，每一份已投递副本都被收回；重新启用会把它重新投递到 scope 仍然授予的每个 agent。

**必须直说的取舍**：现在不再有一个按 agent 的「这个 agent 什么都不要」总开关。要让某一个 agent 被排除在全部之外，就把它从每个 skill 的 scope 里去掉——`mcp_server` 资源本来就是这么工作的。把某个特定 skill 排除在某个 agent 之外的能力没有任何削弱；它只是从 agent 一侧移到了 skill 一侧。

**为什么是这个优先级**：用一条投递规则取代三条互相重叠的规则，才能让「投递集合」从用户在 skill 上看得见的东西直接推出来。

**独立可测**：注册两个 agent 并导入三个没有 scope 的 skill；验证存在六条链接；把其中一个 skill 的 scope 收窄到单个 agent；验证另一个 agent 的副本被收回；把第二个 skill 的 scope 设为 `[]`；验证它的两份副本都被收回；禁用第三个 skill 并验证其副本消失，再重新启用并验证它们回来。

**代表性场景**：

- a skill with no scope reaches every registered agent
- a skill scoped to no agent reaches nobody
- import delivers a skill only where its scope grants it
- disabling a skill reclaims every delivered copy
- re-enabling a skill redelivers it

---

### Edge Cases

- **导入时 skill 重名**：默认拒绝；用户要么在 SKILL.md frontmatter 里改名再试，要么带 `overwrite`（`--force`）重新导入以就地替换既有 skill —— 其按 agent 的 binding 与已投递 symlink 保留。
- **master 文件夹超过大小上限（默认 50 MB）**：导入被拒，错误信息包含上限值与调整方式提示。
- **Windows 下 symlink/junction 创建失败（FAT32 或网络共享）**：该目标降级为复制模式，审计带 `degraded=true`；UI 显示警告标记。
- **用户在外部编辑器中、从某 agent 的 `config_dir/skills` 文件夹内编辑 SKILL.md**：Coffer 的 UI 从不编辑文件内容；用户在自己的编辑器中改动（可经 Coffer 的「在外部编辑器中打开」/「在文件管理器中显示」操作进入，或直接打开）。由于 agent 路径是指向 master 的 symlink，该外部编辑实际落在 master 上，其他 agent 下次读取时即可见；不会被识别为 drift。
- **用户从某 agent 的 `config_dir/skills` 文件夹内删除一个由 Coffer 管理的文件**：同样会作用到 master；下次 `verify` 会标记其他 agent 上对应 link 是否仍能一致解析。
- **移除一个还带 skill binding 的 agent（spec agent-registry）**：spec agent-registry 定义了 agent kind 的 `on_delete` 接缝；the 005-skill-manager spec 在组装根处提供 `cleanup_bindings_for_agent` 回调，先清掉该 agent 的所有 binding 与 symlink，再删掉 agent 行本身。
- **agent 的 `config_dir` 在外部被移走或删除**：下一次同步操作会暴露失败；`verify` 报告受影响的 binding；用户通过更新 agent 的 `config_dir` 或移除该 agent 来处置。
- **`~/.agents/skills` 与其他工具共用**：扫描列出所见内容，只把 Coffer 自己的链接归为托管；其余一律算非托管。删除永远是用户的显式动作——Coffer 绝不替别的工具做垃圾回收。
- **非托管条目是指向主库之外的 symlink**：列为非托管但不可收编（收编会搬走别人的事实来源）；用户可手动处理链接目标，或删除该链接。
- **非托管 skill 没有合法 SKILL.md**：以 `valid=false` 及原因列出；可删除，但在通过校验之前不可收编。
- **投递某个 skill 时目标路径已存在同名的非 Coffer 文件夹**：该 skill 报告为冲突（与 FR-011 同规则）而不被覆盖；主库其余部分照常投递。
- **各 agent 的交付目标**：Coffer 只有一种交付方式——把 master skill 文件夹符号链接（失败则复制）进 `<config_dir>/skills/<name>`。每个 agent 的 skill 子路径来自能力清单，因此将来新增 agent 的交付目标是数据而非新分支。

## Skill delivery scope（[ADR per-agent-resource-scope](../../docs/decisions/per-agent-resource-scope.zh.md)）

`skill` resource 携带一个框架级的 `scope`——一个 agent 名列表，或 `None`
表示「对每个 agent 生效」。它连同该资源自己的 `enabled` 标志，就是投递规则的
**全部**：

```
delivered(skill, agent)  ⟺  skill.enabled AND agent_in_scope(skill.scope, agent)
```

再没有别的东西为投递把关。这与 `mcp_server` 已有的形状一致——那里也是仅由
scope 决定哪个 agent 能看到某个 server 的工具。

- **scope 的三种状态。** `None`——每个已注册 agent 都收到这个 skill（新导入
  的默认值）。`["claude_code"]`——只有列出的 agent 收到；尚未注册的名字是合法
  的，只是永远匹配不上。`[]`——没有任何 agent 收到，而这个 skill 仍留在库中，
  照常导出、照常可见。
- **`enabled` 是开关，而且是真开关。** 禁用一个 skill 会收回它的每一份已投递
  副本——逐条移除 symlink，master 文件夹不动。重新启用会把它重新投递到 scope
  仍然授予的每个 agent。
- **scope 是硬性授予。** 把一个 skill 的 scope 收窄为排除某个此前曾向其投递过
  的 agent，会在下一次调和时收回该投递，无论那份副本当初是怎么到那里的；放宽
  scope 则会投递它。不存在任何按 agent 的状态能违背 skill 的 scope 保住一份
  副本，也不存在任何按 agent 的状态能把副本挡在 scope 已授予的 agent 之外。
- **调和是执行把关点**——包括导入之后运行的按导入调和钩子（spec vault-export-import）。只要
  上述判定的答案可能发生变化，它就会运行：一个 skill 被启用或禁用、一个 skill
  的 scope 被编辑、一个 skill 被导入、一个 skill 被移除、一个 agent 被注册、
  一个 agent 的 `config_dir` 变更，以及一次同步导入之后。每次运行都重新计算该
  agent 应有的集合，投递缺失的部分，收回不再需要的部分。
- **必须直说的取舍。** 现在不再有一个按 agent 的「这个 agent 什么都不要」总
  开关。要让某一个 agent 被排除在全部之外，就把它从每个 skill 的 scope 里去
  掉——`mcp_server` 资源本来就是这么工作的。把某个特定 skill 排除在某个 agent
  之外的能力没有任何削弱；它只是从 agent 一侧移到了 skill 一侧。agent 资源不
  再携带任何 skill 投递策略。

## Acceptance Scenarios

按 `agents/sdd.md`，本节每一个 scenario 都至少被一个带 `@pytest.mark.acceptance(spec="skill-manager", scenario="…")`（Python）或 `acceptance("skill-manager", "…", …)`（TypeScript）标记的测试引用。

### Scenario: 导入合法的本地 skill 文件夹

- **Given** daemon 在运行，且不存在名为 `my-skill` 的 skill，
- **When** 用户导入一个 SKILL.md frontmatter `name: my-skill` 的文件夹，
- **Then** Coffer 把文件夹拷贝到 `~/.coffer/skills/my-skill/`，写入一条 kind 为 `skill` 的 Resource，并写一条审计记录。

### Scenario: re-import a skill with overwrite replaces it（带 overwrite 的重新导入覆盖既有 skill）

- **Given** 名为 `my-skill` 的 skill 已导入并对某 agent 启用，
- **When** 用户带 `overwrite`（`--force`）再次导入一个 frontmatter `name: my-skill` 的文件夹，
- **Then** 主库文件夹内容被原子替换、刷新该 skill 的 `version_hash`、保留其按 agent 的 binding 与已投递 symlink、并写一条 skill-update 审计记录 —— 而同样的重新导入若不带 `overwrite` 则以 `conflict`（409）拒绝。

### Scenario: 拒绝导入不合法的 skill 文件夹

- **Given** daemon 在运行，
- **When** 用户导入一个缺 SKILL.md 或 `name`/`description` frontmatter 为空的文件夹，
- **Then** 请求被明确拒绝，`~/.coffer/skills/` 与数据库都不会被写入任何东西。

### Scenario: 拒绝含有越界 symlink 的导入

- **Given** daemon 在运行，
- **When** 用户导入一个 symlink 解析到文件夹外的目录，
- **Then** 请求被拒绝并列出越界路径，不持久化任何东西。

### Scenario: 拒绝 description 过长的 skill

- **Given** daemon 在运行，
- **When** 用户导入一个 SKILL.md `description` 超过 1024 字符的文件夹，
- **Then** 请求以 frontmatter 不合法被拒绝，不向 `~/.coffer/skills/` 或数据库写入任何东西。

### Scenario: 识别 agentskills.io 可选 frontmatter 字段

- **Given** 一个还声明了 `license` 与实验性 `allowed-tools` 的合法 SKILL.md，
- **When** 校验该文件夹，
- **Then** 校验通过，且解析出的 frontmatter 保留 `license` 与归一化后的 `allowed-tools` 列表（而非丢弃）。

### Scenario: deliver a skill to a registered agent（把一个 skill 投递给已注册 agent）

- **Given** agent `claude_code` 已按 spec agent-registry 注册，且一个 scope 授予 `claude_code` 的已启用 skill `my-skill` 已被导入，
- **When** 该 skill 的投递调和运行，
- **Then** 在 `<config_dir>/skills/my-skill` 处创建一个指向 `~/.coffer/skills/my-skill/` 的目录 symlink（Windows 上是 junction），同时写入一行 `skill_agent_bindings` 记录该 agent 持有一份已投递副本。

### Scenario: reclaim a skill from an agent（从某 agent 收回一个 skill）

- **Given** 某 skill 已投递给某 agent，且目标 symlink 已存在，
- **When** 该 skill 不再投递给这个 agent（其 scope 不再授予该 agent，或该 skill 被禁用），
- **Then** symlink 被移除，该 agent 的投递记录被清除，master 文件夹不变。

### Scenario: deliver one skill to multiple agents（把同一个 skill 投递给多个 agent）

- **Given** 两个 agent 已注册，
- **When** 一个 scope 同时授予二者的已启用 skill 被调和，
- **Then** 两条 symlink（每个 agent 各一条）同时存在，都指向同一份 master。

### Scenario: refuse to overwrite a non-Coffer target（拒绝覆盖非 Coffer 目标）

- **Given** 用户已在目标 link 路径上放了一个普通文件或目录，
- **When** 某个 skill 被投递给该 agent，
- **Then** 该冲突被报告，已有目标保持原样不动；投递的其余部分照常进行。

### Scenario: 检测 agent skill 目录中的 drift

- **Given** 某 binding 存在但其磁盘目标已被删除、被替换或被重指向，
- **When** 用户运行 `coffer skill verify`，
- **Then** 报告按 drift 类别列出每条与建议处置方式，并以非零 exit code 退出；不做自动修复。

### Scenario: 移除 skill 清理所有 binding

- **Given** 某 skill 已对两个 agent 启用，
- **When** 用户移除该 skill，
- **Then** 两个目标 symlink 都被移除，bindings 被级联删除，master 文件夹被删除，并写一条带 config 快照的审计记录。

### Scenario: 移除 agent（按 spec agent-registry）时清理其 skill binding

- **Given** 某 agent 当前有若干已启用 skill，
- **When** 用户移除该 agent，
- **Then** spec agent-registry 中 agent kind 的 `on_delete` 钩子调用 skill 模块，先移除该 agent 的每条 binding 与对应 symlink，再删除 agent 行；master 文件夹保持不变。

### Scenario: 桌面与 CLI 覆盖每一项操作

- **Given** daemon 在运行，
- **When** 用户在 Web UI 与 `coffer skill ...` 中分别执行每一项操作，
- **Then** 两个 surface 产生相同效果，且 CLI 的读类操作均支持 `--json`。

### Scenario: 审计 skill 全生命周期

- **Given** 用户跑完一组代表性操作，
- **When** 他查看审计日志，
- **Then** 每一个事件都带时间戳、actor、target、event type 与必要的 payload（如更新前后的内容哈希）。

### Scenario: view a skill's files as a tree（以树形查看 skill 的文件）

- **Given** 一个已导入的 skill，其 master 文件夹含 `SKILL.md` 及一个内含文件的嵌套子目录，
- **When** 用户请求该 skill 的文件列表，
- **Then** Coffer 返回以 master 文件夹为根的递归只读树，每个节点带 name、相对路径、磁盘绝对路径、type（`file`/`dir`）、文件大小与 children，按目录优先再按名称排序，且不包含任何越界 symlink 目标。

### Scenario: view a single skill file's contents（查看单个 skill 文件内容）

- **Given** 一个含可读文本文件的已导入 skill，
- **When** 用户按相对路径请求该文件内容，
- **Then** Coffer 返回该文件文本、真实字节大小、该文件的磁盘绝对路径及其所在文件夹的绝对路径，以及 `binary=false`/`truncated=false`；不存在的路径返回 not-found 错误。

### Scenario: reject reading a path outside the skill folder（拒绝读取 skill 文件夹之外的路径）

- **Given** 一个已导入的 skill，
- **When** 用户请求一个解析后位于 master 文件夹之外的路径（`..` 穿越、绝对路径或越界 symlink）的文件内容，
- **Then** 请求在任何文件被读取前以 `400` 错误拒绝，且不返回任何内容。

### Scenario: edit and save a skill file（编辑并保存 skill 文件）

- **Given** 一个已导入、含有某个已存在文本文件的 skill，
- **When** 用户在应用内编辑器中编辑该文件（或编程 REST/CLI 客户端为其保存新内容），按相对路径提交并带回读取时返回的指纹，
- **Then** Coffer 原子地覆盖该文件并返回该文件的新指纹，随后读取返回新内容；写入不存在的路径、master 文件夹之外的路径、已存在的二进制文件，或超过大小上限的内容都会被拒绝（`404`/`400`），且文件保持不变。省略指纹的保存仍会写入，因此从未先读取文件的编程客户端照常可用。

### Scenario: reject a stale save of a skill file（拒绝 skill 文件的过期保存）

- **Given** 一个在应用内编辑器中打开的 skill 文件，其读取返回了内容指纹，
- **When** 用户先在自己的外部编辑器中改动了同一个文件，之后才用已过期的指纹保存应用内缓冲区，
- **Then** Coffer 以 `conflict`（409，`SKILL_FILE_STALE`）拒绝该保存，并让外部编辑过的文件在磁盘上逐字节不变；重新读取会得到当前指纹，重试保存即可成功。

### Scenario: list unmanaged skills across an agent's skill locations（列出 agent 各 skill 位置的非托管 skill）

- **Given** 一个已注册 `codex` agent，`<config_dir>/skills` 下有一条 Coffer 托管链接与一个手工拷贝的 skill 文件夹，`~/.agents/skills` 下另有一个 skill 文件夹，
- **When** 用户列出该 agent 的非托管 skill，
- **Then** Coffer 恰好返回两个手工放置的 skill——各带名称、路径、位置与来自 SKILL.md 校验的 `valid` 标志——并排除托管链接。

### Scenario: adopt an unmanaged skill into the master store（把非托管 skill 收编进主库）

- **Given** 一个 SKILL.md 合法、名称与主库不冲突的非托管 skill 文件夹，
- **When** 用户收编它，
- **Then** Coffer 按 FR-004 校验、把文件夹搬到 `~/.coffer/skills/<name>/`、注册 `skill` 资源、把原路径替换为托管链接、为该 agent 记录一条 binding 并审计此次收编——任何失败都让原文件夹原地原样不动。

### Scenario: reject adopting an invalid or conflicting unmanaged skill（拒绝收编不合法或冲突的非托管 skill）

- **Given** 一个缺合法 SKILL.md、或与既有主库 skill 重名、或是指向主库之外 symlink 的非托管条目，
- **When** 用户尝试收编它，
- **Then** 请求按原因以特定错误拒绝（不合法：`unprocessable_entity` 422；重名：`conflict` 409；外部链接：`unprocessable_entity` 422），且不搬移、不注册、不建链接。

### Scenario: delete an unmanaged skill（删除非托管 skill）

- **Given** agent skill 位置中的一个非托管 skill 文件夹，
- **When** 用户删除它（显式、经确认的动作），
- **Then** 该文件夹从磁盘移除并写一条审计记录，主库内容与 binding 不被触碰。

### Scenario: exclude managed links and system entries from the unmanaged scan（非托管扫描排除托管链接与系统条目）

- **Given** 某 agent 的 skill 目录同时包含 Coffer 托管链接与（Codex 的）`.system` 条目，
- **When** 用户列出非托管 skill，
- **Then** 托管链接与 `.system` 条目都不出现在结果中。

### Scenario: a skill with no scope reaches every registered agent（没有 scope 的 skill 到达每个已注册 agent）

- **Given** 两个已注册 agent，以及一个 scope 未设置（`None`）的已启用 skill，
- **When** 对每个 agent 运行投递调和，
- **Then** 两个 agent 都持有一份已投递副本；此后再注册第三个 agent，也会无需任何进一步用户操作地把该 skill 投递过去。

### Scenario: a skill scoped to no agent reaches nobody（scope 为空的 skill 谁也到不了）

- **Given** 两个已注册 agent，各自持有某个已启用 skill 的一份已投递副本，
- **When** 用户把该 skill 的 scope 设为 `[]`，
- **Then** 两份已投递副本都被收回，该 skill 仍留在库中（照常列出、照常导出），在其 scope 重新授予某个 agent 之前没有任何 agent 收到它。

### Scenario: import delivers a skill only where its scope grants it（导入只把 skill 投递到其 scope 授予之处）

- **Given** 两个已注册 agent：`claude_code` 与 `codex`，
- **When** 用户导入一个 scope 为 `["claude_code"]` 的 skill，
- **Then** 导入后的调和只把它投递给 `claude_code`，`codex` 什么也没收到。

### Scenario: disabling a skill reclaims every delivered copy（禁用一个 skill 收回它的每一份已投递副本）

- **Given** 一个已投递给两个 agent 的已启用 skill，
- **When** 用户禁用该 skill 资源，
- **Then** 两条 symlink 都被移除、两条投递记录都被清除，而该 skill 的 scope 与其 master 文件夹保持不变。

### Scenario: re-enabling a skill redelivers it（重新启用一个 skill 会把它重新投递）

- **Given** 一个已禁用、当前没有任何已投递副本、且 scope 授予两个 agent 的 skill，
- **When** 用户重新启用该 skill 资源，
- **Then** 它被重新投递给两个 agent——链接重建、投递记录恢复——无需任何按 agent 的操作。

### Scenario: scoping a skill away from an agent reclaims the delivered copy（把 skill 移出某 agent 的 scope 会收回已投递副本）

- **Given** 一个已启用、当前已投递给某个 agent 且 scope 中包含该 agent 名字的 skill，
- **When** 用户把这个 skill 的 scope 编辑为排除这个 agent，下一次调和运行，
- **Then** 已投递的 symlink 被移除、投递记录被清除——scope 是硬性授予，没有任何按 agent 的状态能违背它保住这份副本。

### Scenario: opt-in repair re-delivers repairable drift from master

- **Given** 某 agent 的 skill 目录中：一条已启用 binding 的 Coffer 链接缺失；另一条的 Coffer 链接已被篡改（旧链接指向别处）；第三条 binding 的路径被用户自有的外部普通目录占据；第四条 binding 的 master 文件夹已不存在，
- **When** 用户执行 opt-in 修复（`coffer skill verify --fix` / `POST /skills/repair`），
- **Then** 缺失的链接重新创建并指向 master；被篡改的链接先备份到 `<path>.coffer-backup-<ts>`，再重新创建并指向 master；外部普通目录完全保持原样，仍在报告中列为需手动处理；missing-master 条目保持原样并报告为需手动处理；每次重新投递作为 repair 事件写入审计日志。

## Requirements

### Functional Requirements

**Resource 模型**

- **FR-001**：系统必须把每个被管理的 skill 注册为 kind 为 `skill` 的 Resource，按 `skill:<name>` 标识，`<name>` 来自 SKILL.md frontmatter。
- **FR-002**：系统必须按 kind 专属 schema 校验 skill 配置：字段含 `source`（变种：仅 `local_import`）、`skill_md_name`、`skill_md_description`、`version_hash`、`last_synced_from_source_at`。

**规范存储**

- **FR-003**：系统必须把每个被管理 skill 的内容存到 `~/.coffer/skills/<name>/`，并以此为唯一可编辑的事实来源。
- **FR-004**：系统必须按 AgentSkills 规范校验每一个被导入的 skill 文件夹：存在 `SKILL.md`；frontmatter `name` 非空（小写字母数字、连字符或下划线，≤64 字符）、`description` 非空且 ≤1024 字符；不含越界 symlink；总大小不超过可配置上限（默认 50 MB）。违反任一项的文件夹以 `unprocessable_entity`（422）拒绝，且不写入任何内容。
- **FR-027**：系统必须识别它理解的 agentskills.io 可选 frontmatter 字段——`license` 与实验性的 `allowed-tools`——解析并保留它们而非丢弃，同时容忍任何其他未识别字段，让非 Coffer 编写的 skill 也能干净通过校验。`allowed-tools` 接受列表或以逗号/空白分隔的字符串，归一化为工具名列表；格式异常的值被容忍（视作缺省），绝不构成校验失败。同理，非字符串的 `license` 标量（如未加引号的年份或版本号）会被转为字符串而非拒绝。

**源**

- **FR-005**：系统必须支持从本地路径导入 skill；原始源路径仅作为 provenance 记录，不会被持续依赖。重名（已存在同名 skill）默认拒绝（`conflict`，409）；带显式 `overwrite` 标志（CLI `--force`）时就地替换既有 skill —— 主库文件夹内容原子替换、刷新其 `version_hash` 与 `last_synced_from_source_at`、并保留其按 agent 的 binding 与已投递 symlink（主库文件夹名不变）。重新导入覆盖是 skill 唯一的更新机制（无可重新拉取的实时源）；该替换以 update 事件审计。

**按 agent 投递**

- **FR-008**：每对 `(skill, agent)` binding 都是内部的投递记账，存在 `skill_agent_bindings` 表：一行表示该 agent 当前持有一份已投递副本，并附上次成功的 link path、link mode 与上次 link 的时间。它不是面向用户的维度，任何 surface 都不把它作为开关暴露。
- **FR-009**：把一个 skill 投递给某 agent 必须在 `<config_dir>/skills/<skill-name>` 创建一个指向 `~/.coffer/skills/<skill-name>/` 的目录 symlink（POSIX）或目录 junction（Windows）。
- **FR-010**：收回一份已投递副本必须移除目标 link，不动 master。
- **FR-011**：投递必须报告、绝不覆盖：当目标路径上已经存在不是 Coffer 托管链接的东西时，该 skill 被报告为冲突、既有目标原封不动，投递的其余部分照常进行。（在重新建链前先备份目标的做法只存在于 FR-029 的显式 opt-in drift 修复中。）
- **FR-012**：当符号链接/目录 junction 不可用（如 FAT32、网络共享）时，系统可降级为复制模式；绑定记录 `link_mode=copy_fallback`（enable 事件审计为 `mode: copy_fallback`），UI 必须呈现该降级状态（Agent 的 Skills 标签页对此类绑定显示 "已复制" 警示徽标）。
- **FR-012a**（[ADR per-agent-resource-scope](../../docs/decisions/per-agent-resource-scope.zh.md)）：当且仅当该 skill 资源已启用**且**该 agent 在这个 skill 的 scope 内时，这个 skill 才必须被投递给该 agent——即 `skill.enabled AND agent_in_scope(skill.scope, agent)`。没有别的标志为投递把关：既不是 FR-008 的投递记账，也不是 agent 资源上的任何字段。调和过程中发现一份该判定不再授予的已投递副本，必须按 FR-010 收回它（移除链接、清除投递记录）；发现一份该判定现在授予、而该 agent 尚未持有的副本，必须投递它。

**Drift**

- **FR-015**：系统必须提供 `verify` 操作，对每条已启用 binding 比对其磁盘目标，并按 drift 类别（missing link、tampered link、missing master、orphan master）报告与建议处置方式。
- **FR-016**：系统不得自动修复 drift；修复必须由用户显式触发。
- **FR-029**：系统必须提供显式、opt-in 的 drift 修复操作（`coffer skill verify --fix`，`POST /skills/repair`），从主库重新投递可安全修复的 drift——即 missing link 与 tampered link——并且不得修改外部/用户内容（replaced-with-regular）、缺失的 master，或孤立 master；上述情况保持原样并报告为需要手动处理。每次修复写入审计。

**非托管 skill（工作区增补）**

- **FR-022**：系统必须扫描已注册 agent 的 skill 位置——两种类型的 `<config_dir>/skills`，`codex` 另加 `~/.agents/skills`——并列出**非托管**条目：一切既不是 Coffer 托管链接（目标解析在 `~/.coffer/skills/` 之内的链接）也不是 Codex `.system` 条目的内容。每个结果携带名称、路径、位置与 `valid` 标志（FR-004 校验），不合法时附原因。扫描只读，在请求时派生。
- **FR-023**：用户必须能收编一个合法的非托管 skill。收编按 FR-004 校验文件夹、搬到 `~/.coffer/skills/<name>/`、注册 `skill` 资源、投递托管链接（FR-009）、并为该 agent 记录一条启用的 binding——按此顺序，注册之前的任何失败都让原文件夹不被搬动、不被改变（注册之后主库副本即为权威；投递失败会如实暴露并经 binding 重试，绝不回滚资源）。托管链接始终投递到该 agent 的规范投递位置 `<config_dir>/skills/<name>`：从 `<config_dir>/skills` 收编时原路径就地替换；从 `~/.agents/skills` 收编时则做归并——该处原文件夹被移除、链接落在 `<config_dir>/skills`（Codex 两个位置都读取，agent 仍然可见该 skill）。重名以 `conflict`（409）拒绝；不合法文件夹与指向主库之外的 symlink 以 `unprocessable_entity`（422）拒绝。以收编事件审计。
- **FR-024**：用户必须能以显式、经确认的动作删除一个非托管条目。删除只从磁盘移除该条目，绝不动主库内容或 binding，并写入审计。

**投递调和（工作区增补）**

- **FR-025**：系统必须仅依据 FR-012a 的判定，按 agent 调和投递。一次调和把该 agent 应有的集合算作 `{s.name for s in skills if s.enabled and agent_in_scope(s.scope, agent_name)}`，投递其中该 agent 尚未持有的每一个 skill，并收回每一份不再需要的已持有副本。它必须在以下时机运行：一个 skill 被启用或禁用、一个 skill 的 scope 被编辑、一个 skill 被导入、一个 skill 被移除、一个 agent 被注册、一个 agent 的 `config_dir` 变更，以及一次同步导入之后的 post-import 钩子。目标路径冲突遵循 FR-011（报告、绝不覆盖）。agent 资源不携带任何形式的 skill 投递策略——没有跟随标志、没有排除列表、没有按 agent 的退出开关；唯一的输入是 skill 的 `enabled` 标志与它的 `scope`。
- **FR-026**：非托管 skill 操作必须可通过 REST API、`coffer agent skill …` / `coffer skill …` CLI（读取支持 `--json`）、以及 Web UI 中该 agent 的 Skills tab 完成。投递本身不是这个 surface 上的操作：它由 skill 资源的 `enabled` 标志与 `scope`，经通用的资源启停与 scope surface 控制。

**生命周期**

- **FR-017**：移除一个 skill 必须移除每个 agent 的 symlink、级联删除 binding、删除 master 文件夹，并以快照方式写入审计。
- **FR-018**：移除 agent（按 spec agent-registry）必须触发 skill 模块的 `on_delete` 钩子，先移除该 agent 的 binding 与 symlink，再删除 agent 行。

**Surface**

- **FR-019**：每一项管理操作必须可通过（a）REST API、（b）`coffer skill ...` CLI（含 `--json`）、（c）Web UI 的 Skills 页 三种 surface 完成。按 `(skill, agent)` 的启用/禁用不在其列：`POST /skills/{name}/enable` 与 `POST /skills/{name}/disable` 两条 REST 路由，以及 `coffer skill enable|disable` CLI 命令，均已**移除**。投递由 skill 的 `enabled` 标志与 `scope` 经通用资源 surface 驱动——`coffer scope set skill:<name> --agents …` 与 `coffer resource enable|disable skill:<name>`。
- **FR-021**：系统必须提供 skill master 文件夹的**只读**视图：一棵递归文件树（name、相对路径、磁盘绝对路径、type、size、children）以及单个文件的内容（含其磁盘绝对路径与所在文件夹的绝对路径）。Markdown 文件渲染为格式化 Markdown，其他文本文件以原文显示。每次文件读取还必须返回内容指纹（FR-028），以便该文件的应用内编辑可以有条件地保存。读取必须限制在 master 文件夹内——任何解析后位于其外的路径（`..` 穿越、绝对路径或越界 symlink）必须被拒绝。文件读取必须做大小上限（超限时截断并带 `truncated` 标记），并把非 UTF-8 / 含 NUL 字节的文件标记为 binary 且内容为空。不跟随越界 symlink。
- **FR-006**：应用内文件查看器必须在文件与所在文件夹两种粒度上提供以下操作：（a）在用户首选的外部编辑器中打开目标（该全局首选项在 ui-shell 中定义；默认为操作系统默认应用），（b）在操作系统文件管理器（Finder / 资源管理器）中显示目标。打开与显示通过 daemon 的文件系统动作端点（spec agent-registry FR-039）执行真正的操作系统动作,因为环回 daemon 就在用户自己的机器上（ADR: daemon-proxies-os-file-actions）。没有 copy-path 回退。这些操作与应用内编辑（FR-028）并存：用户在 Coffer 内保存小改动，遇到更大的改动再转向自己的编辑器。
- **FR-028**：系统必须提供写入，在与 FR-021 相同的限制与大小上限下**覆盖 master 文件夹中已存在的文本文件**；必须拒绝在此创建新文件/目录、写到文件夹之外、或用文本覆盖二进制文件。写入必须是原子的，且不跟随越界 symlink。应用内编辑器与编程客户端（REST/CLI）共用这一个端点。由于 master 文件夹同时也是用户在自己编辑器里编辑的文件夹，文件读取必须返回**内容指纹**（对文件磁盘原始字节取摘要——而非对可能被截断的返回文本，这样超大文件的指纹仍能原样回传，且截断点之后的修改同样能被发现）；写入可以带回该指纹：当它与磁盘上的字节不再匹配时，写入必须以 `conflict`（409）拒绝并保持文件逐字节不变，使用户重新读取并重新应用，而不是悄悄丢掉对方的修改。省略指纹的写入仍为无条件写入（后写者胜），这正是从未先读取文件的编程客户端所需要的。
- **FR-030**：「添加 skill」导入对话框必须提供一个文件夹选择器（复用 spec agent-registry FR-023/FR-024 的共享组件——通过 daemon 打开宿主的原生目录对话框,回退到 daemon 支撑的文件夹浏览器）,让用户选取 skill 文件夹而非手敲其绝对路径。选取的绝对路径喂给既有的导入操作（FR-005）;手动输入路径仍受支持。

**可观测**

- **FR-020**：系统必须为每一次导入、投递、收回、移除与 drift 修复事件写入一条审计记录。

### Key Entities

- **Skill**：kind 为 `skill` 的 Resource，按 `skill:<name>`（name 来自 SKILL.md frontmatter）标识。承载源 provenance、内容哈希、元数据；内容文件夹位于 `~/.coffer/skills/<name>/`。携带一个框架级 `scope`（一个 agent 名列表，或 `None` 表示对每个 agent 生效），它连同该资源自己的 `enabled` 标志直接决定投递（ADR per-agent-resource-scope；见「Skill delivery scope」）。
- **Skill Source**：记录 skill 来源的结构。本地导入仅含原始路径作 provenance 用。
- **Skill–Agent Binding**：内部的投递记账，不是面向用户的开关。连接一个 skill Resource 与一个 agent Resource（kind `agent`，按 spec agent-registry）的一行，记录该 agent 当前持有一份已投递副本，并附最近 link path、link mode 与最近 link 时间。磁盘上的 symlink 是 live 表达；这一行是「投递了什么」的持久化记录。
- **Drift Report**：`verify` 返回的瞬时结构，列出每条与磁盘不一致的 binding，附 drift 类型与建议处置方式。
- **Unmanaged Skill（非托管 skill）**：在 agent skill 位置发现的、Coffer 不管理的 skill 形条目的派生（绝不存储）视图——名称、路径、位置、`valid` 标志。文件系统是事实来源；收编或删除是仅有的两种变更。

## Success Criteria

### Measurable Outcomes

- **SC-001**：从零安装开始，用户可在 60 秒内完成「导入既有 `~/.claude/skills/<one-skill>/`、对自动检测到的 Claude Code agent 启用、达到 ready 状态」。
- **SC-003**：把一个 skill 对两个 agent 启用产生两条合法的目录 symlink（Windows 上为 junction），两个 agent 的读取进程看到同样的 SKILL.md 内容。
- **SC-004**：手动删掉某 agent 侧的一条 symlink 后，`coffer skill verify` 必须在 5 秒内识别为 drift，并以非零 exit code 退出。
- **SC-005**：删除一个对两个 agent 启用的 skill 后，磁盘上无残留 symlink、无残留 master 文件夹，DB 中无孤儿 binding 行。
- **SC-006**：本规范每一个 Acceptance Scenario 都至少被一个带 `acceptance(spec="skill-manager", scenario="…")` 的测试覆盖，`make verify-acceptance` 报告 0 个未覆盖 scenario。
- **SC-007**：全套 `make verify` 在本地与 CI 通过；`make verify-all`（含 e2e）在 macOS 与 Linux 通过；Windows 在 junction 模式与 copy-fallback 模式下分别通过。
- **SC-008**：SKILL.md 内容永不离开用户机器；由集成测试中的网络出站扫描自动验证。
- **SC-009**：新导入的 skill 在 5 秒内投递到其 scope 授予的每个 agent，除导入本身外无需任何用户操作。
- **SC-010**：在托管链接与手工放置 skill 混杂的机器上，非托管扫描恰好列出手工放置的条目——零托管链接、零 `.system` 条目——由基于构造 fixture 树的集成测试验证。

## Assumptions

- spec agent-registry-agent-registry 已上线（PR #25）；agent kind 及其 CRUD、审计、`on_delete` 钩子均已可用。
- spec mcp-gateway-mcp-gateway 引入的 kind-agnostic Resource 框架、审计日志与 `<kind>:<name>` 标识方案已就位。
- spec ui-shell-ui-shell 的应用外壳——侧栏 IA、布局、路由骨架、设计系统——已就位；Skills 页是渲染在该外壳之上的功能 surface，填上 002-ui-shell 预留的 `/skills` 导航位。
- skill 遵循开放 AgentSkills 标准（SKILL.md 至少含 `name`/`description` frontmatter，见 agentskills.io），并按标准的精确约束校验（`name` ≤64 字符、`description` ≤1024 字符），同时识别可选的 `license` 与实验性 `allowed-tools` 字段；不符合规范的文件夹不在本规范处理之列。
- 本地导入的 skill 是时间点拷贝；原路径仅用于追溯，不用于同步。
- Windows 用户的文件系统支持目录 junction；FAT32 与网络共享降级为 copy 模式。
- 两种 agent 类型的投递位置维持 `<config_dir>/skills`。Codex 还会读取 `~/.agents/skills`（其较新的标准位置），并把 `<config_dir>/skills` 视为向后兼容的 legacy 位置——非托管扫描覆盖两处；迁移 Coffer 的投递目标是一项已记录、延后到未来变更的决策。
- agent 资源不携带任何 skill 投递策略。投递完全落在 skill 资源上——它的 `enabled` 标志与它的 `scope`——这些语义由本 spec 拥有。
- 浏览即装 skill 目录（发现机制）已原型化后撤回（简化，2026-06-20），原因是缺乏可供浏览的内容生态；安装目录作为未来工作仍有可能落地。
- v2 将探索：远程目录索引、agent 间的 skill 推荐、项目级 skill（仓库内 `.claude/skills/`）。
