# 功能规范：Skill Manager

> English: [spec.md](./spec.md)

**Feature Branch**: `feature/skill-manager`
**Created**: 2026-05-22
**Status**: Accepted
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

用户打开 Coffer，看到以数据表呈现的 Skills 页（搜索、筛选、分页、行多选以执行批量操作），可以通过文件选择器导入或粘贴 Git URL 拉取，并浏览列表。Skills 页只管理 skill 资源本身，不管理它的按 agent binding：点击某个 skill 打开详情视图，其中有一个 Overview 元信息 tab 与一个 Files tab（文件树 + 文件查看器：渲染 Markdown 并支持编辑已存在的文本文件）。按 agent 的启用/禁用在 agent 详情页上进行——该 agent 的「Skills」tab 列出绑定到该 agent 的 skill，并带每条 binding 的开关。

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

### User Story 11 —— 跟随主库（优先级 P2）

逐 skill binding 精确但繁琐：每个新 skill 都要逐个 agent 启用。用户打开某 agent 的**「跟随主库」**开关；从此主库中的每个 skill 都自动投递到该 agent——新 skill 注册即出现、被删除的 skill 即消失——并配一份按 agent 的排除列表应对少数不想要的。不跟随的 agent 维持逐 skill binding 模式。关闭跟随时，当前已投递的集合保留为显式 binding，不会有任何东西凭空消失。

**为什么是这个优先级**：这是 skill 版的「配置一次、共享全部」——MCP 网关「一个条目服务全部」模型在文件系统侧的对应物。

**独立可测**：对一个 agent 在主库有三个 skill 时开启跟随；验证三条链接存在；注册第四个 skill；验证其链接无需额外操作即出现；排除一个 skill；验证其链接被移除而其余保留。

**代表性场景**：

- enable follow-all and deliver every master skill
- auto-deliver new skills to following agents
- auto-remove deleted skills from following agents
- exclude a skill from a following agent
- disable follow-all preserving current bindings

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
- **`~/.agents/skills` 与其他工具共用**：扫描列出所见内容，只把 Coffer 自己的链接归为托管；其余一律算非托管。删除永远是用户的显式动作——Coffer 绝不替别的工具做垃圾回收。
- **非托管条目是指向主库之外的 symlink**：列为非托管但不可收编（收编会搬走别人的事实来源）；用户可手动处理链接目标，或删除该链接。
- **非托管 skill 没有合法 SKILL.md**：以 `valid=false` 及原因列出；可删除，但在通过校验之前不可收编。
- **开启跟随时目标路径已存在同名的非 Coffer 文件夹**：该 skill 报告为冲突（与 FR-011 同规则）而不被覆盖；主库其余部分照常投递。
- **各 agent 的交付目标**：folder 模式的 agent 交付到其配置目录下的 skill 子路径——Claude Code、Codex、OpenCode 为 `<config_dir>/skills/<name>`；OpenClaw 为 `<config_dir>/workspace/skills/<name>`。Hermes（`external_dir`）folder 投递到一个 Coffer 拥有的外部目录（`~/.coffer/agent-skills/<agent>/<name>`），并由 Coffer 登记进该 agent `config.yaml` 的 `skills.external_dirs`。每个 agent 的模式、子路径与登记方式都来自能力清单，因此新增一个 agent 的交付目标是数据而非新分支。
- **交付模式尚未接通的 agent（Cursor）**：Cursor 的 `rules_mdc` 是已识别的交付模式扩展点，其端到端交付被推迟——Cursor 的 `.mdc` 规则是 project 级（`<project>/.cursor/rules/`），没有官方支持的全局/agent 级 `.mdc` 落点来投递 agent 级 skill（全局 User Rules 存在 Cursor 内部设置里、非文件）。为这类 agent 启用 skill 会在任何文件系统写入之前以明确的“交付模式尚不支持”错误（HTTP 422）拒绝，而不是用 folder 模式误交付；follow / relink 协调器会跳过这些 agent，因此注册与策略变更仍可成功。

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

### Scenario: 拒绝 description 过长的 skill

- **Given** daemon 在运行，
- **When** 用户导入一个 SKILL.md `description` 超过 1024 字符的文件夹，
- **Then** 请求以 frontmatter 不合法被拒绝，不向 `~/.coffer/skills/` 或数据库写入任何东西。

### Scenario: 识别 agentskills.io 可选 frontmatter 字段

- **Given** 一个还声明了 `license` 与实验性 `allowed-tools` 的合法 SKILL.md，
- **When** 校验该文件夹，
- **Then** 校验通过，且解析出的 frontmatter 保留 `license` 与归一化后的 `allowed-tools` 列表（而非丢弃）。

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

### Scenario: edit a skill file（编辑 skill 文件）

- **Given** 一个已导入、含有某个已存在文本文件的 skill，
- **When** 用户按相对路径为该文件保存新内容，
- **Then** Coffer 原子地覆盖该文件，随后读取返回新内容；写入不存在的路径、master 文件夹之外的路径、已存在的二进制文件，或超过大小上限的内容都会被拒绝（`404`/`400`），且文件保持不变。

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

### Scenario: enable follow-all and deliver every master skill（开启跟随并投递主库全部 skill）

- **Given** 一个尚未跟随的已注册 agent，主库中有三个 skill，
- **When** 用户开启该 agent 的跟随主库开关，
- **Then** 同步引擎把三个 skill 全部投递给该 agent（链接 + binding 行），该 agent 的有效集合等于主库减去其（空的）排除列表。

### Scenario: auto-deliver new skills to following agents（向跟随中的 agent 自动投递新 skill）

- **Given** 一个已开启跟随的 agent，
- **When** 主库注册一个新 skill（导入、拉取或收编），
- **Then** daemon 无需用户进一步操作即把它投递给该 agent。

### Scenario: auto-remove deleted skills from following agents（从跟随中的 agent 自动移除已删除 skill）

- **Given** 一个已开启跟随、且有一个已投递 skill 的 agent，
- **When** 该 skill 从主库被移除，
- **Then** 该 agent 的链接与 binding 作为移除的一部分被清理。

### Scenario: exclude a skill from a following agent（在跟随中的 agent 上排除一个 skill）

- **Given** 一个已开启跟随、且有一个已投递 skill 的 agent，
- **When** 用户为该 agent 排除该 skill，
- **Then** 其链接与 binding 被移除，该 skill 进入该 agent 的排除列表，且后续主库变化在排除解除之前绝不重新投递它。

### Scenario: disable follow-all preserving current bindings（关闭跟随并保留现有 binding）

- **Given** 一个已开启跟随、且有若干已投递 skill 的 agent，
- **When** 用户关闭跟随开关，
- **Then** 每个当前已投递的 skill 都保留为显式逐 skill binding 且链接完好，后续主库新增不再自动投递。

### Scenario: deliver a skill to OpenCode under skills/（投递到 OpenCode 的 skills/）

- **Given** 一个已注册的 OpenCode agent 和一个已导入的主库 skill，
- **When** 该 skill 被投递给该 agent，
- **Then** 它落在 `<config_dir>/skills/<name>`（含其 `SKILL.md`）并解析到规范的主库文件夹。

### Scenario: deliver a skill to OpenClaw under workspace/skills/（投递到 OpenClaw 的 workspace/skills/）

- **Given** 一个已注册的 OpenClaw agent 和一个已导入的主库 skill，
- **When** 该 skill 被投递给该 agent，
- **Then** 它落在 `<config_dir>/workspace/skills/<name>`（解析到主库文件夹），而不在扁平的 `skills/` 位置。

### Scenario: deliver a skill to an external-dir agent and register the directory（投递到 external-dir agent 并登记目录）

- **Given** 一个已注册的 Hermes agent（`external_dir` 投递）和一个已导入的主库 skill，
- **When** 该 skill 被投递给该 agent，
- **Then** skill 文件夹落在一个 Coffer 拥有的外部目录（解析到主库文件夹）——而不在该 agent 自己的 `skills/` 下——且该目录被登记进该 agent `config.yaml` 的 `skills.external_dirs`，保留用户其它配置键/注释并按解析后的路径去重。

### Scenario: deregister an external-dir agent's directory when its last skill is removed（移除最后一个 skill 时注销 external-dir agent 的目录）

- **Given** 一个 Hermes agent，其 Coffer 拥有的外部目录已登记在 `config.yaml` 中，
- **When** 最后一个已投递的 skill 被禁用（或该 agent 被删除），
- **Then** Coffer 的条目从 `skills.external_dirs` 中移除（并裁剪已空的列表），而用户自己添加的目录保持不变。

### Scenario: enabling a skill for a non-folder-delivery agent fails cleanly（为非文件夹投递的 agent 启用 skill 干净失败）

- **Given** 一个已注册的 agent，其 skill 投递模式不是基于文件夹（Cursor 的 `rules_mdc`），
- **When** 用户为该 agent 启用某 skill，
- **Then** 请求在任何文件系统写入之前以 `unprocessable_entity`（422）拒绝，且跟随驱动的自动投递跳过该 agent 而不报错。

## Requirements

### Functional Requirements

**Resource 模型**

- **FR-001**：系统必须把每个被管理的 skill 注册为 kind 为 `skill` 的 Resource，按 `skill:<name>` 标识，`<name>` 来自 SKILL.md frontmatter。
- **FR-002**：系统必须按 kind 专属 schema 校验 skill 配置：字段含 `source`（变种：`local_import` | `git`）、`skill_md_name`、`skill_md_description`、`version_hash`、`last_synced_from_source_at`。

**规范存储**

- **FR-003**：系统必须把每个被管理 skill 的内容存到 `~/.coffer/skills/<name>/`，并以此为唯一可编辑的事实来源。
- **FR-004**：系统必须按 AgentSkills 规范校验每一个被导入或拉取的 skill 文件夹：存在 `SKILL.md`；frontmatter `name` 非空（小写字母数字、连字符或下划线，≤64 字符）、`description` 非空且 ≤1024 字符；不含越界 symlink；总大小不超过可配置上限（默认 50 MB）。违反任一项的文件夹以 `unprocessable_entity`（422）拒绝，且不写入任何内容。
- **FR-027**：系统必须识别它理解的 agentskills.io 可选 frontmatter 字段——`license` 与实验性的 `allowed-tools`——解析并保留它们而非丢弃，同时容忍任何其他未识别字段，让非 Coffer 编写的 skill 也能干净通过校验。`allowed-tools` 接受列表或以逗号/空白分隔的字符串，归一化为工具名列表；格式异常的值被容忍（视作缺省），绝不构成校验失败。同理，非字符串的 `license` 标量（如未加引号的年份或版本号）会被转为字符串而非拒绝。

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

**非托管 skill（工作区增补）**

- **FR-022**：系统必须扫描已注册 agent 的 skill 位置——两种类型的 `<config_dir>/skills`，`codex` 另加 `~/.agents/skills`——并列出**非托管**条目：一切既不是 Coffer 托管链接（目标解析在 `~/.coffer/skills/` 之内的链接）也不是 Codex `.system` 条目的内容。每个结果携带名称、路径、位置与 `valid` 标志（FR-004 校验），不合法时附原因。扫描只读，在请求时派生。
- **FR-023**：用户必须能收编一个合法的非托管 skill。收编按 FR-004 校验文件夹、搬到 `~/.coffer/skills/<name>/`、注册 `skill` 资源、投递托管链接（FR-009）、并为该 agent 记录一条启用的 binding——按此顺序，注册之前的任何失败都让原文件夹不被搬动、不被改变（注册之后主库副本即为权威；投递失败会如实暴露并经 binding 重试，绝不回滚资源）。托管链接始终投递到该 agent 的规范投递位置 `<config_dir>/skills/<name>`：从 `<config_dir>/skills` 收编时原路径就地替换；从 `~/.agents/skills` 收编时则做归并——该处原文件夹被移除、链接落在 `<config_dir>/skills`（Codex 两个位置都读取，agent 仍然可见该 skill）。重名以 `conflict`（409）拒绝；不合法文件夹与指向主库之外的 symlink 以 `unprocessable_entity`（422）拒绝。以收编事件审计。
- **FR-024**：用户必须能以显式、经确认的动作删除一个非托管条目。删除只从磁盘移除该条目，绝不动主库内容或 binding，并写入审计。

**跟随主库（工作区增补）**

- **FR-025**：每个 agent 必须携带一个跟随主库标志与一份按 agent 的 skill 排除列表（存于 agent 资源的 config，spec 004）。跟随期间，agent 的有效 skill 集合是整个主库减去其排除项；同步引擎必须在标志变化、skill 注册或移除、以及排除列表变化时执行对账投递。目标路径冲突遵循 FR-011（报告、绝不覆盖）。关闭标志必须把当前已投递的 skill 保留为显式逐 skill binding。该标志对新注册的 agent 默认开启，与增补前的自动绑定行为一致。
- **FR-026**：非托管 skill 与跟随操作必须可通过 REST API、`coffer agent skill …` / `coffer skill …` CLI（读取支持 `--json`）、以及桌面应用中该 agent 的 Skills tab 完成。

**生命周期**

- **FR-017**：移除一个 skill 必须移除每个 agent 的 symlink、级联删除 binding、删除 master 文件夹，并以快照方式写入审计。
- **FR-018**：移除 agent（按 spec 004）必须触发 skill 模块的 `on_delete` 钩子，先移除该 agent 的 binding 与 symlink，再删除 agent 行。

**Surface**

- **FR-019**：每一项管理操作必须可通过（a）REST API、（b）`coffer skill ...` CLI（含 `--json`）、（c）桌面 Skills 页 三种 surface 完成。
- **FR-021**：系统必须提供 skill master 文件夹的视图：一棵递归文件树（name、相对路径、type、size、children）以及单个文件的内容。Markdown 文件渲染为格式化 Markdown，其他文本文件以原文显示。读取必须限制在 master 文件夹内——任何解析后位于其外的路径（`..` 穿越、绝对路径或越界 symlink）必须被拒绝。文件读取必须做大小上限（超限时截断并带 `truncated` 标记），并把非 UTF-8 / 含 NUL 字节的文件标记为 binary 且内容为空。系统还必须允许在同样的限制与大小上限下**覆盖 master 文件夹中已存在的文本文件**；必须拒绝在此创建新文件/目录、写到文件夹之外、或用文本覆盖二进制文件。写入必须是原子的。不跟随越界 symlink。

**可观测**

- **FR-020**：系统必须为每一次导入、拉取、启用、禁用、更新、改名、移除与 drift 修复事件写入一条审计记录。

### Key Entities

- **Skill**：kind 为 `skill` 的 Resource，按 `skill:<name>`（name 来自 SKILL.md frontmatter）标识。承载源 provenance、内容哈希、元数据；内容文件夹位于 `~/.coffer/skills/<name>/`。
- **Skill Source**：判别式记录（`local_import` 或 `git`），描述 skill 来源。Git 包含 URL、ref、可选 subpath；本地导入仅含原始路径作 provenance 用。
- **Skill–Agent Binding**：连接一个 skill Resource 与一个 agent Resource（kind `agent`，按 spec 004）的一行；带 `enabled` 标志与最近 link path。磁盘上的 symlink 是 live 表达；binding 是持久化表达。
- **Drift Report**：`verify` 返回的瞬时结构，列出每条与磁盘不一致的 binding，附 drift 类型与建议处置方式。
- **Unmanaged Skill（非托管 skill）**：在 agent skill 位置发现的、Coffer 不管理的 skill 形条目的派生（绝不存储）视图——名称、路径、位置、`valid` 标志。文件系统是事实来源；收编或删除是仅有的两种变更。
- **Follow Policy（跟随策略）**：按 agent 的状态（标志 + 排除列表，按 spec 004 存于 agent 资源 config），声明该 agent 接收整个主库。binding 仍是持久化的投递记录；策略驱动同步引擎的对账。

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
- **SC-009**：开启跟随后，新注册的 skill 在 5 秒内投递到跟随中的 agent，除注册本身外无需任何用户操作。
- **SC-010**：在托管链接与手工放置 skill 混杂的机器上，非托管扫描恰好列出手工放置的条目——零托管链接、零 `.system` 条目——由基于构造 fixture 树的集成测试验证。

## Assumptions

- spec 004-agent-registry 已上线（PR #25）；agent kind 及其 CRUD、审计、`on_delete` 钩子均已可用。
- spec 001-mcp-gateway 引入的 kind-agnostic Resource 框架、审计日志与 `<kind>:<name>` 标识方案已就位。
- spec 002-ui-shell 的应用外壳——侧栏 IA、布局、路由骨架、设计系统——已就位；桌面 Skills 页是渲染在该外壳之上的功能 surface，填上 002-ui-shell 预留的 `/skills` 导航位。
- skill 遵循开放 AgentSkills 标准（SKILL.md 至少含 `name`/`description` frontmatter，见 agentskills.io），并按标准的精确约束校验（`name` ≤64 字符、`description` ≤1024 字符），同时识别可选的 `license` 与实验性 `allowed-tools` 字段；不符合规范的文件夹不在本规范处理之列。
- v1 仅支持公开 Git URL；需鉴权的上游 skill 源留给后续工作。
- 本地导入的 skill 是时间点拷贝；原路径仅用于追溯，不用于同步。
- Windows 用户的文件系统支持目录 junction；FAT32 与网络共享降级为 copy 模式。
- 两种 agent 类型的投递位置维持 `<config_dir>/skills`。Codex 还会读取 `~/.agents/skills`（其较新的标准位置），并把 `<config_dir>/skills` 视为向后兼容的 legacy 位置——非托管扫描覆盖两处；迁移 Coffer 的投递目标是一项已记录、延后到未来变更的决策。
- 跟随主库标志与排除列表存于 agent 资源的 config（spec 004 的 schema）；其投递语义由本 spec 拥有。
- v2 将探索：marketplace 浏览（agentskills.io API）、agent 间的 skill 推荐、项目级 skill（仓库内 `.claude/skills/`）、通过 credential ref 支持私有 Git 源。
