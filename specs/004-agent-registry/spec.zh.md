# 功能规范：Agent Registry

> English: [spec.md](./spec.md)

**Feature Branch**: `feature/004-agent-registry`
**Created**: 2026-05-22
**Status**: Draft
**Input**: 用户描述：「管理 Coffer 已知的本地安装 AI agent，让后续功能（skills、memory、knowledge base）能向它们投递资产。每个 agent 都是 kind-agnostic Resource 框架（由 spec 001-mcp-gateway 引入）下 kind 为 `agent` 的一种 Resource。v1 支持四种 agent 类型：Claude Code、Claude Desktop、Cursor、OpenAI Codex CLI。」

## 用户场景与测试

### User Story 1 —— 首次启动时自动检测已安装的 agent（优先级 P1）

开发者首次启动 Coffer 时，daemon 扫描每种受支持 agent 类型的常见安装路径并注册扫描结果。开发者无需手动输入路径，就能在列表中看到已存在的 agent。

**为什么是这个优先级**：零配置的第一印象。如果没有自动检测，用户必须先学会 agent 类型标识与默认路径，才能做任何有意义的事。

**独立可测**：在一台同时存在 `~/.claude/` 与 `~/.cursor/` 的机器上启动 daemon，列出 agent，观察 Claude Code 与 Cursor 都已注册并标记为 `auto_detected=true`。

**代表性场景**：

- 从 `~/.claude/` 检测 Claude Code
- 从平台相关的路径检测 Claude Desktop
- 检测 Cursor 与 Codex CLI
- 跳过已注册的类型
- 抑制（suppress）用户先前已移除的 agent

---

### User Story 2 —— 用自定义路径手工注册一个 agent（优先级 P1）

部分用户把 agent 装在非默认位置，或者同时有多个安装（工作、个人）。他们需要按类型添加一个 agent，并覆盖默认的 skill 目录。

**为什么是这个优先级**：自动检测覆盖常见情况，手工注册覆盖长尾。两者缺一不可。

**独立可测**：从命令行用 `--skill-dir /custom/path` 注册一个名为 `cursor-work` 的 `cursor` agent；列出 agent，观察自动检测条目与手工注册条目并存。

**代表性场景**：

- 用自定义 skill_dir 注册一个 agent
- skill_dir 缺失或不可写时拒绝注册
- 拒绝重复的 agent 名

---

### User Story 3 —— 编辑、禁用或移除一个 agent（优先级 P1）

用户的本地 agent 安装情况会随时间变化。他们需要更新 skill_dir 路径、临时关闭而不移除、或彻底删除。

**为什么是这个优先级**：一个不可变的 registry 一周内就会失去用处。

**独立可测**：注册一个 agent，更新其 skill_dir，禁用、再启用，最后移除；验证每一步状态都被持久化并写入 audit。

**代表性场景**：

- 更新已存在 agent 的 skill_dir
- 启用/禁用一个 agent
- 移除一个 agent 并观察 audit 条目

---

### User Story 4 —— 在桌面应用中管理 agent（优先级 P2）

用户打开 Coffer 桌面应用，看到一个「Agents」页面，列出每个已注册 agent 的类型、名称、skill_dir 与检测方式，并能在表单里添加或编辑。

**为什么是这个优先级**：非 CLI 用户需要一个可视化界面来理解 registry。

**独立可测**：打开桌面应用 → Agents → 用默认路径添加 Cursor → 在列表里观察 → 点进去 → 修改 skill_dir → 保存 → 列表更新。

**代表性场景**：

- agents 页面列出所有已注册 agent
- 通过桌面表单添加一个 agent
- 通过桌面表单编辑一个 agent
- 通过桌面确认对话框移除一个 agent

---

### User Story 5 —— 命令行可执行相同操作（优先级 P2）

用户脚本化 registry 配置（dotfiles、CI 机器）。所有 UI 中能做的操作都以 `coffer agent ...` 子命令的形式可用，并支持 `--json` 输出。

**为什么是这个优先级**：Coffer 面向开发者；CLI 等价能力是基本盘。

**独立可测**：一个 bash 脚本注册两个 agent，以 JSON 方式列出，编辑其中一个，移除另一个——全程不碰 GUI。

**代表性场景**：

- CLI 与 REST 操作一一对应
- 机器可读的 JSON 输出

---

### User Story 6 —— Audit registry 变更（优先级 P3）

每一次 add / edit / remove / 自动检测都带时间戳与 actor 被记录，CLI 与 UI 均可查询。

**为什么是这个优先级**：建立信任，方便排查「这是什么时候变的？」。不会阻塞 registry 的核心使用。

**独立可测**：做几次变更；查看 audit 日志；观察每一次变更一行，并带有 actor 与事件类型。

**代表性场景**：

- audit agent 生命周期事件

---

### Edge Cases

- **第二次启动时的自动检测**：已注册的类型被跳过；扫描不会重复创建已有条目。
- **用户删除一个自动检测出来的 agent**：下次扫描时该类型不会被自动重建（已抑制）。用户可以随时手动重新添加。
- **agent 类型不在受支持列表中**：注册拒绝，给出清晰错误信息与受支持类型列表。
- **`skill_dir` 路径不存在或不可写**：注册拒绝；不留下任何中间状态。
- **`skill_dir` 指向特权路径**（`/etc`、`/usr` 等）：注册拒绝。
- **在 `agent` kind 内出现重名**：被 kind-agnostic Resource 框架拒绝。

（并发 detect 请求由上方的显式 acceptance scenario 覆盖，见「concurrent detect requests are serialized」。）

## Acceptance Scenarios

按 `agents/sdd.md` 与 `agents/testing.md` 的约定，本节中每一个 scenario 都至少被一个带 `@pytest.mark.acceptance(spec="004-agent-registry", scenario="…")`（Python）或 `acceptance("004-agent-registry", "…", …)`（TypeScript）标记的测试引用。

### Scenario: detect installed agents on first launch

- **Given** 一台全新的 Coffer 安装，存在 `~/.claude/` 与 `~/.cursor/`，
- **When** daemon 首次启动，
- **Then** Coffer 注册一个 `claude_code` agent 与一个 `cursor` agent，二者均带 `auto_detected=true`，并使用默认 `skill_dir`。

### Scenario: skip already-registered types on subsequent launch

- **Given** 已注册一个 `claude_code` agent，
- **When** daemon 重新启动并重新扫描，
- **Then** 不会再次注册第二个 `claude_code` agent。

### Scenario: respect user removal across launches

- **Given** 一个自动检测出来的 agent 已被用户移除，
- **When** daemon 重新启动并重新扫描，
- **Then** 该类型不会被自动重新注册。

### Scenario: register an agent with custom skill_dir

- **Given** daemon 正在运行，
- **When** 用户以一个明确、可写的 `skill_dir` 注册一个受支持类型的 agent，
- **Then** 该 agent 以该路径被持久化，并出现在 `coffer agent list` 中。

### Scenario: reject registration with invalid skill_dir

- **Given** daemon 正在运行，
- **When** 用户注册的 agent 的 `skill_dir` 不存在、不是目录或不可写，
- **Then** 注册被拒绝并给出指向该路径的错误信息，且不留下任何持久化数据。

### Scenario: reject duplicate agent name

- **Given** 已经存在名为 `cursor-work` 的 agent，
- **When** 用户尝试用同一名字再注册一个 agent，
- **Then** 注册被拒绝并给出清晰错误。

### Scenario: update an existing agent

- **Given** 一个已注册的 agent，
- **When** 用户把它的 `skill_dir` 更新到一个新的可写路径，
- **Then** 变更被持久化，写入 audit 条目，后续操作看到新路径。

### Scenario: remove an agent

- **Given** 一个已注册的 agent（任何 binding 清理由 spec 005 处理），
- **When** 用户移除它，
- **Then** 该 agent 被删除，写入 audit 条目，`coffer agent list` 不再显示它。

### Scenario: desktop app agents page

- **Given** Coffer 桌面应用已启动，且至少有一个已注册 agent，
- **When** 用户打开 Agents 页面，
- **Then** 每个已注册 agent 都带有类型、名称、`skill_dir` 与检测方式出现在列表中。

> Story 4 的桌面表单 add/edit/remove 流程在 e2e 层覆盖；打包的 acceptance 标记见 `e2e/web/specs/shell_agents.spec.ts`。

### Scenario: CLI surface mirrors REST operations

- **Given** daemon 正在运行并暴露 REST agent 路由，
- **When** 用户调用 `coffer agent add`、`list`、`edit`、`rm` 或 `detect`，
- **Then** 每个子命令调用对应的 REST endpoint 并产生等价的状态变化；每个读取类子命令额外支持 `--json` 以输出机器可读结果。

### Scenario: reject registration into privileged system path

- **Given** daemon 正在运行，
- **When** 用户尝试注册的 agent，其 `skill_dir` 落在特权位置（`/etc`、`/usr`、`/bin`、`/sbin`、`/System`、`C:\Windows` 或 `C:\Program Files`）之下，
- **Then** 注册以 `unprocessable_entity`（422）被拒绝，且不产生任何 resource 行、audit 事件或文件系统写入。

### Scenario: concurrent detect requests are serialized

- **Given** daemon 正在运行并暴露 `POST /api/v1/agents/detect`，
- **When** 在同一台存在相同受支持安装标记的机器上并发到达两个 detect 请求，
- **Then** 自动检测被串行化，使得每个受支持类型在两次响应汇总下至多被注册一次（不出现重复的 `agent:<name>` 行）。

### Scenario: audit lifecycle events

- **Given** 用户已经注册、编辑或移除过 agent，
- **When** 查看 audit 日志，
- **Then** 自动检测的新增以 `agent_auto_registered` 记录；用户移除自动检测 agent 时还会附带一条 `agent_type_suppressed`；其他所有生命周期变化（手工创建、更新、启用、禁用、移除）通过 kind-agnostic 的 `resource_created` / `resource_updated` / `resource_enabled` / `resource_disabled` / `resource_removed` 事件呈现，每条都携带时间戳、actor 与对应 agent 引用。

## Requirements

### Functional Requirements

**Resource 模型**

- **FR-001**: 系统 MUST 将每个已知的本地 agent 注册为 kind 为 `agent` 的 Resource，按 spec 001-mcp-gateway 的 `<kind>:<name>` 约定，标识为 `agent:<name>`。
- **FR-002**: 系统 MUST 用一个 kind 专属 schema 校验 agent 配置，字段包括 `type`（enum）、`skill_dir`（path，可选覆盖）、`auto_detected`（bool）。
- **FR-003**: 系统 MUST 在 v1 中支持 `claude_code`、`claude_desktop`、`cursor`、`codex_cli` 这四个 agent 类型；注册任何其它类型以 `unprocessable_entity`（422）被拒绝。

**自动检测**

- **FR-004**: daemon 启动时，系统 MUST 扫描每种受支持 agent 类型的安装标记，并为每一个当前不存在且不在用户抑制列表的类型注册一个 Resource。
- **FR-005**: 系统 MUST 持久化一份「已抑制类型」列表，记录用户先前移除的 agent 类型，并在后续扫描中跳过这些类型的自动注册，直至用户再次手工注册。

**生命周期**

- **FR-006**: 用户 MUST 能注册、列出、查看、更新（skill_dir、description）、启用/禁用与移除 agent。
- **FR-007**: 系统 MUST 在接受 `skill_dir` 值之前验证其存在、是目录、可写且不是特权系统路径。
- **FR-008**: 系统 MUST 拒绝任何会造成重复 `agent:<name>` 的注册。

**界面**

- **FR-009**: 每一个管理操作 MUST 同时通过 (a) REST API、(b) `coffer agent ...` CLI、与 (c) 桌面 Agents 页面提供。
- **FR-010**: CLI MUST 在每个读取类操作上支持 `--json` 以提供机器可读输出。

**可观测性**

- **FR-011**: 系统 MUST 为每一个生命周期事件写入一条 audit 条目：agent 创建（auto 或 manual）、更新、启用、禁用、移除。
- **FR-012**: 系统 MUST 通过 REST API（`POST /api/v1/agents/detect`）、`coffer agent detect` CLI 与桌面 Agents 页面，提供一个按需重新跑自动检测的 `detect` 操作。

### Key Entities

- **Agent**：一个 kind 为 `agent` 的 Resource。代表一份本地安装的 AI agent。Config: `type`（受支持的 enum）、`skill_dir`（path 或按类型默认）、`auto_detected`（来源）。标识为 `agent:<name>`。
- **Agent Type**：一个 enum 值，标识一个已知 agent 产品。每个类型有一个默认 `skill_dir`（当用户未覆盖时使用）、一个显示名、以及一个用于自动检测的安装标记扫描器。
- **Suppressed Type Record**：一个小的系统状态行，标记用户显式移除过该类型的自动检测 agent；用于在后续启动中抑制自动重新注册。

## Success Criteria

### Measurable Outcomes

- **SC-001**：在一台至少存在两种受支持 agent 安装路径的机器上，daemon 首次启动后正好自动注册这些 agent，零手工步骤。
- **SC-002**：从一份全新安装开始，用户能在 60 秒内用自定义 `skill_dir` 注册一个额外 agent，并在 `coffer agent list --json` 中看到它，期间最多查阅一次文档。
- **SC-003**：本 spec 中每一个 Acceptance Scenario 至少被一个带 `acceptance(spec="004-agent-registry", scenario="…")` 标记的测试覆盖；`make verify-acceptance` 报告零未覆盖 scenario。
- **SC-004**：完整 `make verify` 套件在本地与 CI 中通过；`make verify-all`（额外包含 e2e）在 macOS 与 Linux 上通过。
- **SC-005**：任何 `skill_dir` 值都不允许写到该目录之外（path-traversal 检查），由一个专门的安全测试验证。

## Assumptions

- 用户在自己的机器上运行 Coffer；不存在多租户或远程访问需求。
- v1 支持的四种 agent 类型足以覆盖用户已安装的 agent；增加新类型属于后续 spec 的改动，新增一个 enum 值与一个安装标记扫描器。
- agent 把自己的 skill 库存放在本地文件系统中一个可被发现的目录里。仅 Web 形态的 agent（例如 claude.ai）超出 v1 范围，需要后续 spec 通过 API 同步加入。
- 由 spec 001-mcp-gateway 定义的 kind-agnostic Resource 框架、audit 日志与 `<kind>:<name>` 标识方案已就绪。
- 来自 spec 002-ui-shell 的应用外壳——侧栏 IA、布局、路由骨架与设计系统——已就绪；桌面 Agents 页面是一个功能 surface，渲染在该外壳内，并填入 002-ui-shell 预留的 `/agents` 导航位。
- Skill bindings（agent 与某个 skill 之间的关系）由 spec 005-skill-manager 引入和管理；spec 004 不定义 skill 操作，只暴露一个用于级联清理的 `on_delete` 钩子。
