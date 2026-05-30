# 功能规范：Agent Registry

> English: [spec.md](./spec.md)

**Feature Branch**: `feature/004-agent-registry`
**Created**: 2026-05-22
**Status**: Draft
**Input**: 用户描述：「管理 Coffer 已知的本地安装 AI agent，让后续功能（skills、memory、knowledge base）能向它们投递资产。每个 agent 都是 kind-agnostic Resource 框架（由 spec 001-mcp-gateway 引入）下 kind 为 `agent` 的一种 Resource。v1 支持两种 agent 类型：Claude Code 与 OpenAI Codex——每种都同时涵盖其 CLI 与桌面/IDE 形态，因为它们共享同一份磁盘配置。除注册 agent 外，用户还能查看并编辑每个 agent 的已知配置文件，并一键把 Coffer 自己的 MCP server 安装到某个 agent 上。」

> **关于 agent 类型的说明。** v1 恰好涵盖两个产品：**Claude Code**（`claude_code`）与 **OpenAI Codex**（`codex`）。每种都同时覆盖其 CLI _与_ app/IDE 形态，因为它们读取同一个共享配置目录——Claude Code 用 `~/.claude/`，Codex 用 `~/.codex/`。独立的 **Claude Desktop** 聊天应用（拥有自己的 `~/Library/Application Support/Claude/` 配置）与 **Cursor** 不在 v1 范围内；将来若要支持，会作为各自独立的 agent 类型、带各自的配置文件 allowlist 加入。

## 用户场景与测试

### User Story 1 —— 发现已安装的 agent 并选择要添加哪些（优先级 P1）

当开发者打开 Agents 页面（或运行 `coffer agent detect`）时，Coffer 扫描每种受支持 agent 类型的常见安装路径，并把找到的、尚未注册的那些作为**候选项（candidate）**呈现。开发者审阅后确认要添加哪些——Coffer 绝不静默注册任何 agent。

**为什么是这个优先级**：近乎零配置、且不带意外的第一印象。检测帮用户找到 agent，免去学习类型标识与默认路径之苦，但由用户掌控什么进入自己的 registry。

**独立可测**：在一台同时存在 `~/.claude/` 与 `~/.codex/` 的机器上，打开 Agents 页面，运行发现，观察 Claude Code 与 Codex 都作为候选项被提供；确认它们后观察二者均已注册。

**代表性场景**：

- 把已安装的 agent 作为候选项发现
- 后续扫描跳过已注册的类型
- 后续扫描重新呈现已移除的 agent

---

### User Story 2 —— 用自定义路径手工注册一个 agent（优先级 P1）

部分用户把 agent 装在非默认位置，或者同时有多个安装（工作、个人）。他们需要按类型添加一个 agent，并可选地覆盖 skill 目录。名称是可选的——省略时 Coffer 会派生一个稳定的按类型默认名。选择自定义路径时，桌面应用提供一个文件夹选择器（打包应用用 OS 原生对话框；Web 用 daemon 支撑的文件夹浏览器），使用户挑选一个真实目录，而不是手动输入。

**为什么是这个优先级**：发现覆盖常见情况，手工注册覆盖长尾。没有它，registry 就不完整。

**独立可测**：从命令行用 `--skill-dir /custom/path` 注册一个名为 `codex-work` 的 `codex` agent；列出 agent，观察该手工注册条目。从桌面表单添加一个不带名称的 agent，观察它以按类型默认名注册。

**代表性场景**：

- 用自定义 skill_dir 注册一个 agent
- 不带显式名称注册一个 agent
- skill_dir 缺失或不可写时拒绝注册
- 拒绝重复的 agent 名
- 浏览本地文件夹以选择一个 skill 目录

---

### User Story 3 —— 编辑或移除一个 agent（优先级 P1）

用户的本地 agent 安装情况会随时间变化。他们需要更新 skill_dir 路径或描述，或彻底删除。（agent 没有启用/禁用的概念——已注册的 agent 就是存在的。）

**为什么是这个优先级**：一个不可变的 registry 一周内就会失去用处。

**独立可测**：注册一个 agent，更新其 skill_dir，最后移除；验证每一步状态都被持久化并写入 audit。

**代表性场景**：

- 更新已存在 agent 的 skill_dir
- 移除一个 agent 并观察 audit 条目

---

### User Story 4 —— 在桌面应用中管理 agent（优先级 P2）

用户打开 Coffer 桌面应用，看到一个「Agents」页面，列出每个已注册 agent 的类型、名称与 skill_dir，并能在表单里添加或编辑。

**为什么是这个优先级**：非 CLI 用户需要一个可视化界面来理解 registry。

**独立可测**：打开桌面应用 → Agents → 用默认路径添加 Codex → 在列表里观察 → 点进去 → 修改 skill_dir → 保存 → 列表更新。

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

### User Story 7 —— 查看并编辑一个 agent 的配置文件（优先级 P2）

agent 注册之后，用户希望直接在 Coffer 里查看并调整该 agent 自己的配置文件（例如 Claude Code 的 `settings.json`、Codex 的 `config.toml`），无需离开应用去翻找 dotfile。Coffer 展示该 agent 类型的一组精选已知配置文件，让用户打开其中一个以读取当前内容、就地编辑并保存回去。保存时，Coffer 会按文件格式校验内容（畸形的 JSON/TOML 会被拒绝、文件保持不变），原子写入，并保留上一版本的 `.bak`，使错误的编辑始终可恢复。编辑时还提供一个无依赖的编辑器内查找/替换工具作为便利功能。

**为什么是这个优先级**：手工定位 agent 配置意味着要记住每个文件在哪、用什么格式。把这组精选文件集中到一处呈现、一眼可见可编辑、并对错误编辑有兜底——是让 registry 超越「记账」、真正变得有用的第一个功能。

**独立可测**：注册一个 `claude_code` agent；列出其配置文件；打开 `settings.json`；编辑并保存；观察新内容可读回且保留了 `.bak`；打开一个尚未创建的文件（如 `CLAUDE.md`），观察它读为空内容且未被创建。

**代表性场景**：

- 列出 agent 的精选配置文件，带存在性与大小元信息
- 读取一个已存在配置文件的内容
- 把尚未创建的配置文件读成空内容
- 拒绝读取不在该 agent 类型 allowlist 内的 key
- 用合法内容保存一个配置文件
- 拒绝畸形的配置文件内容

---

### User Story 8 —— 一键把 Coffer 的 MCP 安装到某个 agent（优先级 P2）

用户希望自己的 agent（Claude Code、Codex）真正用上 Coffer。在 agent 的管理界面点击「安装 Coffer MCP」，Coffer 就把自己的 MCP server 条目写进该 agent 的 MCP 配置——一个指向 `coffer-mcp-shim` 二进制的 `coffer` stdio 条目。状态指示器显示 Coffer 当前是否已安装，用户也可卸载以移除该条目。

**为什么是这个优先级**：手工把一个 MCP server 接进客户端（正确地编辑 `~/.claude.json` 或 `~/.codex/config.toml`）正是 Coffer 要消除的摩擦。一键就闭合了「Coffer 知道你的 agent」与「你的 agent 能用上 Coffer」之间的回路。

**独立可测**：注册一个尚未安装 Coffer 的 `claude_code` agent；查看状态（未安装）；安装；观察 `~/.claude.json` 的 `mcpServers` 中写入了一个 `coffer` 条目，其 `command` 为 shim 的绝对路径；查看状态（已安装）；再次安装（不重复）；卸载；观察该条目被移除。

**代表性场景**：

- 报告某个 agent 的 Coffer-MCP 安装状态
- 把 Coffer 的 MCP 条目安装进一个 Claude Code agent（`~/.claude.json`）
- 把 Coffer 的 MCP 条目安装进一个 Codex agent（`~/.codex/config.toml`）
- 安装具有幂等性——重复安装不会产生重复条目
- 卸载移除 Coffer 条目
- 安装/卸载以原子方式写入并带 `.bak` 备份，且写入一条 audit 条目

---

### Edge Cases

- **第二次扫描时的发现**：已注册的类型不会作为候选项被提供；发现绝不重复已有条目。
- **用户删除一个 agent**：移除并非永久。下次扫描会把该 agent 重新作为候选项呈现（删除可能是误操作）；Coffer 不保留任何抑制列表。用户再确认一次即可重新添加。
- **agent 类型不在受支持列表中**：注册拒绝，给出清晰错误信息与受支持类型列表（`claude_code`、`codex`）。
- **`skill_dir` 路径不存在或不可写**：注册拒绝；不留下任何中间状态。
- **`skill_dir` 指向特权路径**（`/etc`、`/usr` 等）：注册拒绝。
- **在 `agent` kind 内出现重名**：被 kind-agnostic Resource 框架拒绝。
- **配置文件 key 不在该类型 allowlist 内**：读取以 `not_found`（404）拒绝；对未知 key 不做任何文件系统访问。
- **配置文件尚不存在**：以 `exists=false` 与空内容列出并可读；读取绝不创建该文件。
- **Coffer MCP 已安装时再次安装**：幂等——就地更新 `coffer` 条目，绝不重复；状态仍为 `installed`。
- **未安装时卸载 Coffer MCP**：空操作（no-op）成功；状态报告 `not_installed`。
- **无法解析 `coffer-mcp-shim` 二进制**：安装被拒绝并给出指明缺失二进制的清晰错误；不向 agent 配置写入任何内容。
- **在主目录之外浏览文件夹**：daemon 支撑的文件夹浏览器列出用户导航到的任何可读目录的子目录；它绝不返回文件内容。不可读或不存在的路径返回错误，而非部分列表。

## Acceptance Scenarios

按 `agents/sdd.md` 与 `agents/testing.md` 的约定，本节中每一个 scenario 都至少被一个带 `@pytest.mark.acceptance(spec="004-agent-registry", scenario="…")`（Python）或 `acceptance("004-agent-registry", "…", …)`（TypeScript）标记的测试引用。

### Scenario: discover installed agents as candidates

- **Given** 一份存在 `~/.codex/` 且尚未注册任何 agent 的 Coffer 安装，
- **When** 用户运行发现，
- **Then** Coffer 报告一个 `codex` 候选项（类型、显示名、配置目录、默认 `skill_dir`、建议名称）且不注册任何内容——发现是只读的。

### Scenario: skip already-registered types on subsequent scan

- **Given** 已注册一个 `codex` agent，
- **When** 用户再次运行发现，
- **Then** `codex` 不会作为候选项被提供。

### Scenario: re-surface removed agents on subsequent scan

- **Given** 一个 agent 已被用户移除，且其安装标记仍然存在，
- **When** 用户再次运行发现，
- **Then** 该 agent 再次作为候选项被提供（移除并非永久；没有抑制列表）。

### Scenario: register an agent with custom skill_dir

- **Given** daemon 正在运行，
- **When** 用户以一个明确、可写的 `skill_dir` 注册一个受支持类型的 agent，
- **Then** 该 agent 以该路径被持久化，并出现在 `coffer agent list` 中。

### Scenario: reject registration with invalid skill_dir

- **Given** daemon 正在运行，
- **When** 用户注册的 agent 的 `skill_dir` 不存在、不是目录或不可写，
- **Then** 注册被拒绝并给出指向该路径的错误信息，且不留下任何持久化数据。

### Scenario: reject duplicate agent name

- **Given** 已经存在名为 `codex-work` 的 agent，
- **When** 用户尝试用同一名字再注册一个 agent，
- **Then** 注册被拒绝并给出清晰错误。

### Scenario: reject a second agent for an already-registered config dir

- **Given** 已注册一个 `codex` agent（其配置目录为 `~/.codex`），
- **When** 用户尝试再注册一个 `codex` agent（解析到同一个配置目录），即便名称与 skill_dir 不同，
- **Then** 注册被拒绝并给出清晰错误，且不持久化任何内容——同一个配置目录至多只能注册一个 agent。

### Scenario: register an agent without an explicit name

- **Given** daemon 正在运行，
- **When** 用户注册一个受支持类型的 agent 但不提供名称，
- **Then** 该 agent 以一个稳定的按类型默认名注册（下划线变连字符，如 `claude_code` → `claude-code`）。

### Scenario: browse local folders to choose a skill directory

- **Given** daemon 正在运行，
- **When** Web 文件夹浏览器请求某个可读目录的子目录，
- **Then** Coffer 返回该目录的路径、其父目录与其直接子目录（不含文件内容）；不可读或不存在的路径返回错误。

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
- **Then** 每个已注册 agent 都带有类型、名称与 `skill_dir` 出现在列表中。

> Story 4 的桌面表单 add/edit/remove 流程在 e2e 层覆盖；打包的 acceptance 标记见 `e2e/web/specs/shell_agents.spec.ts`。

### Scenario: CLI surface mirrors REST operations

- **Given** daemon 正在运行并暴露 REST agent 路由，
- **When** 用户调用 `coffer agent add`、`list`、`edit`、`rm` 或 `detect`，
- **Then** 每个子命令调用对应的 REST endpoint 并产生等价的状态变化；每个读取类子命令额外支持 `--json` 以输出机器可读结果。

### Scenario: reject registration into privileged system path

- **Given** daemon 正在运行，
- **When** 用户尝试注册的 agent，其 `skill_dir` 落在特权位置（`/etc`、`/usr`、`/bin`、`/sbin`、`/System`、`C:\Windows` 或 `C:\Program Files`）之下，
- **Then** 注册以 `unprocessable_entity`（422）被拒绝，且不产生任何 resource 行、audit 事件或文件系统写入。

### Scenario: audit lifecycle events

- **Given** 用户已经注册、编辑或移除过 agent，
- **When** 查看 audit 日志，
- **Then** 每一次生命周期变化（创建、更新、移除）都通过 kind-agnostic 的 `resource_created` / `resource_updated` / `resource_deleted` 事件呈现，每条都携带时间戳、actor 与对应 agent 引用。（agent 没有启用/禁用的概念；发现是只读的、不注册任何内容——二者都不发出任何 audit 事件。）

### Scenario: reject unsupported agent type

- **Given** daemon 正在运行，
- **When** 用户尝试注册 `claude_code` 或 `codex` 之外的类型（例如 `cursor`、`claude_desktop`），
- **Then** 注册以 `unprocessable_entity`（422）被拒绝，并指明这两个受支持类型，且不留下任何持久化数据。

### Scenario: list an agent's config files

- **Given** 一个已注册的 `claude_code` agent，
- **When** 用户列出其配置文件，
- **Then** Coffer 返回该类型的精选集合——`settings.json`、`settings.local.json`、`~/.claude.json`、`CLAUDE.md`——每个都带解析后的路径、格式与 `exists` 标志（存在时附带大小与修改时间）。

### Scenario: read an existing config file

- **Given** 一个 `settings.json` 已存在的已注册 agent，
- **When** 用户读取该配置文件 key，
- **Then** Coffer 返回该文件的当前文本内容、其格式（`json`）与 `exists=true`。

### Scenario: read a not-yet-created config file

- **Given** 一个 `CLAUDE.md` 在磁盘上不存在的已注册 agent，
- **When** 用户读取该配置文件 key，
- **Then** Coffer 返回空内容与 `exists=false`，且不创建该文件。

### Scenario: reject config-file key outside the allowlist

- **Given** 一个已注册 agent，
- **When** 用户引用不在该 agent 类型精选 allowlist 内的配置文件 key，
- **Then** Coffer 以 `not_found`（404）响应，且不做任何文件系统读取。

### Scenario: save a config file with valid content

- **Given** 一个 `settings.json` 已存在的已注册 `claude_code` agent，
- **When** 用户向该配置文件 key 写入新的、格式良好的内容，
- **Then** Coffer 按文件格式校验内容，原子写入并保留上一版本的 `.bak`，写一条 `agent_config_file_written` audit 条目，下次读取即可读回新内容。

### Scenario: reject malformed config-file content

- **Given** 一个 `settings.json`（`json` 文件）已存在的已注册 agent，
- **When** 用户向该 key 写入畸形内容（如非法 JSON），
- **Then** Coffer 以 `unprocessable_entity`（422）响应，磁盘文件保持不变，不写 `.bak`，也不写任何写入 audit 条目。

### Scenario: report Coffer-MCP install status

- **Given** 一个 MCP 配置中不含 `coffer` server 条目的已注册 agent，
- **When** 用户查询 Coffer-MCP 安装状态，
- **Then** Coffer 报告 `installed=false`。

### Scenario: install Coffer's MCP into an agent

- **Given** 一个已注册的 `claude_code` agent 与一个可解析的 `coffer-mcp-shim` 二进制，
- **When** 用户安装 Coffer 的 MCP，
- **Then** 在 `~/.claude.json` 的 `mcpServers` 中写入一个 `coffer` 条目，其 `command` 为 shim 的绝对路径；先前文件备份到 `.bak`；写入一条 `agent_mcp_installed` audit 条目；安装状态报告 `installed=true`。

### Scenario: install Coffer's MCP is idempotent

- **Given** 一个已安装 Coffer MCP 的 agent，
- **When** 用户再次安装，
- **Then** 就地更新已有的 `coffer` 条目（绝不重复），状态仍报告 `installed=true`。

### Scenario: uninstall Coffer's MCP from an agent

- **Given** 一个已安装 Coffer MCP 的 agent，
- **When** 用户卸载它，
- **Then** 从 agent 的 MCP 配置中移除 `coffer` 条目；文件备份到 `.bak`；写入一条 `agent_mcp_uninstalled` audit 条目；状态报告 `installed=false`。

### Scenario: config-file and MCP operations mirror across surfaces

- **Given** daemon 暴露了配置文件与 MCP 安装路由，
- **When** 用户调用等价的 `coffer agent config …` / `coffer agent mcp …` CLI 子命令，
- **Then** 每个子命令调用对应的 REST endpoint 并产生等价状态，读取类子命令支持 `--json`。

## Requirements

### Functional Requirements

**Resource 模型**

- **FR-001**: 系统 MUST 将每个已知的本地 agent 注册为 kind 为 `agent` 的 Resource，按 spec 001-mcp-gateway 的 `<kind>:<name>` 约定，标识为 `agent:<name>`。
- **FR-002**: 系统 MUST 用一个 kind 专属 schema 校验 agent 配置，字段包括 `type`（enum）与 `skill_dir`（path，可选覆盖）。
- **FR-003**: 系统 MUST 在 v1 中支持 `claude_code` 与 `codex` 两个 agent 类型；注册任何其它类型（包括 `claude_desktop`、`cursor`）以 `unprocessable_entity`（422）被拒绝。每个受支持类型都同时覆盖该产品的 CLI 与 app/IDE 形态，二者共享同一个配置目录。

**发现（检测 = 发现 + 确认）**

- **FR-004**: 系统 MUST 提供一个只读的发现操作，扫描每种受支持 agent 类型的常见安装标记，并把已安装但尚未注册的类型作为**候选项（candidate）**报告（每个携带类型、显示名、配置目录、默认 `skill_dir` 与一个建议名称）。发现 MUST NOT 自动注册任何内容——由用户审阅候选项并确认要添加哪些。daemon MUST NOT 在启动时自动注册 agent。
- **FR-005**: 只要安装标记仍存在，被移除的 agent MUST 在后续扫描中重新作为发现候选项出现——移除并非永久（可能是误操作）。系统 MUST NOT 保留任何「已抑制类型」列表。

**生命周期**

- **FR-006**: 用户 MUST 能注册、列出、查看、更新（skill_dir、description）与移除 agent。agent **没有启用/禁用的概念**——已注册的 agent 就是存在的，agent 层面不存在启用/禁用状态。注册时 agent 名称是可选的——省略时系统 MUST 派生一个稳定的按类型默认名（下划线变连字符，如 `claude_code` → `claude-code`）。
- **FR-007**: 系统 MUST 在接受 `skill_dir` 值之前验证其存在、是目录、可写且不是特权系统路径。
- **FR-008**: 系统 MUST 拒绝任何会造成重复 `agent:<name>` 的注册，并 MUST 拒绝为同一个配置目录注册多于一个 agent。`config_dir` 由 agent 类型派生，因此每个受支持类型——也即每个磁盘上的配置目录——至多只能注册一次；第二次尝试以 `conflict`（409）拒绝且不持久化任何内容。

**配置文件**

- **FR-013**: 每个受支持 agent 类型 MUST 定义一份精选的配置文件 allowlist，每个条目携带稳定的 `key`、一个显示名、一个解析后的绝对路径与一个 `format`（`json`、`toml`、`markdown` 或 `text`）。v1 中：Claude Code → `settings.json`、`settings.local.json`、`~/.claude.json`、`CLAUDE.md`；Codex → `config.toml`、`AGENTS.md`。
- **FR-014**: 用户 MUST 能列出一个 agent 的配置文件，并对每个文件给出其 key、显示名、路径、格式与存在性（文件存在时附带大小与修改时间）。
- **FR-015**: 用户 MUST 能读取任一 allowlist 内配置文件的内容。不存在的文件读为空内容、`exists=false`，且读取不会创建它。
- **FR-016**: 用户 MUST 能写入（保存）任一 allowlist 内配置文件的内容。写入前 MUST 按文件的 `format` 校验内容；畸形的 `json`/`toml` MUST 被拒绝（`unprocessable_entity`，422）且磁盘文件保持不变。`markdown`/`text` 文件接受任意内容。
- **FR-017**: 写入 MUST 是原子的（临时文件 + rename），并 MUST 保留上一版本内容的 `.bak` 副本，使错误编辑可恢复；每次成功写入 MUST 写一条 `agent_config_file_written` audit 条目。Coffer-MCP 安装/卸载操作（FR-022）复用同一套原子写入 + `.bak` 机制。
- **FR-018**: 配置文件的读取与写入 MUST 只能通过 allowlist 内的 `key` 寻址（绝不接受调用方提供的路径）；未知 key 返回 `not_found`（404）且不做任何文件系统访问。

**Coffer MCP 安装**

- **FR-019**: 用户 MUST 能一键把 Coffer 自己的 MCP server 安装到某个 agent。安装把一个 `coffer` MCP-server 条目写进 agent 的 MCP 配置——`claude_code` 写到 `~/.claude.json` 的 `mcpServers`，`codex` 写到 `~/.codex/config.toml` 的 `[mcp_servers.coffer]`——使用 stdio shim，`command` 设为 `coffer-mcp-shim` 二进制的绝对路径（先在 `PATH` 中解析，再查找当前解释器的脚本目录——这样即使守护进程的 `PATH` 不含 venv，也能找到装在 venv 里的 shim——最后回退到打包的二进制；环境变量 `COFFER_MCP_SHIM_PATH` 优先于以上全部）。若无法解析 shim，安装被拒绝且不写入任何内容。
- **FR-020**: 安装 MUST 幂等——重复安装就地更新已有的 `coffer` 条目，绝不产生重复。系统 MUST 暴露一个状态操作，报告该 agent 当前是否已安装 Coffer 的 MCP。
- **FR-021**: 用户 MUST 能卸载 Coffer 的 MCP，从 agent 的 MCP 配置中移除 `coffer` 条目。未安装时卸载为空操作（no-op）成功。
- **FR-022**: 安装与卸载 MUST 复用 FR-017 的原子写入 + `.bak` 机制，并写一条 audit 条目（`agent_mcp_installed` / `agent_mcp_uninstalled`）。

**界面**

- **FR-009**: 每一个管理操作——注册/列出/查看/更新/移除、配置文件列出/读取/写入、以及 Coffer-MCP 安装/卸载/状态——MUST 同时通过 (a) REST API、(b) `coffer agent ...` CLI、与 (c) 桌面 Agents 页面提供。
- **FR-010**: CLI MUST 在每个读取类操作上支持 `--json` 以提供机器可读输出。

**可观测性**

- **FR-011**: 系统 MUST 为每一个生命周期事件写入一条 audit 条目：agent 创建、更新、移除；配置文件写入（`agent_config_file_written`）；Coffer MCP 安装/卸载。（agent 没有启用/禁用的概念；发现是只读的——二者都不发出任何 audit 事件。）
- **FR-012**: 系统 MUST 暴露一个只读的发现操作，把已安装但未注册的 agent 列为候选项，可通过 REST API（`GET /api/v1/agents/candidates`）、`coffer agent detect` CLI 与桌面 Agents 页面访问。

**Skill 目录选择器**

- **FR-023**: 选择自定义 `skill_dir` 时，桌面应用 MUST 提供一个文件夹选择器，而非要求用户手动输入路径。在打包桌面应用中，它 MUST 使用 OS 原生目录对话框；在 Web 上，它 MUST 使用 daemon 支撑的文件夹浏览器（FR-024）。两者都产出一个绝对路径，随后在注册前按 FR-007 校验。
- **FR-024**: 系统 MUST 暴露一个只读的文件系统浏览操作（`GET /api/v1/fs/browse`），给定一个目录路径（默认用户主目录），返回该路径、其父目录与其直接子目录。它 MUST NOT 返回文件内容，且 MUST 与所有其它 daemon 路由一样受同样的 loopback + token 鉴权保护。

### Key Entities

- **Agent**：一个 kind 为 `agent` 的 Resource。代表一份本地安装的 AI agent。Config: `type`（受支持的 enum）、`skill_dir`（path 或按类型默认）。标识为 `agent:<name>`。
- **Agent Type**：一个 enum 值，标识一个已知 agent 产品（`claude_code`、`codex`）。每个类型有一个默认 `skill_dir`、一个显示名、一个用于发现的安装标记扫描器，以及一份精选的**配置文件 allowlist**。
- **Agent Candidate（候选项）**：一个被发现的、已安装但尚未注册的 agent——类型、显示名、配置目录、默认 `skill_dir` 与建议名称。在扫描时派生，从不存储；用户确认某个候选项即可注册它。
- **Config File（配置文件）**：属于某个 agent 类型、在 allowlist 内的精选文件，以稳定的 `key` 标识。携带显示名、解析后的绝对路径、`format`（`json` / `toml` / `markdown` / `text`），以及（存在时）大小与修改时间。按 key 读写，绝不按任意路径。不持久化到 SQLite——磁盘上的文件即为事实来源。
- **Coffer MCP Install Status（安装状态）**：某个 agent 的派生（非存储）状态：其 MCP 配置文件中是否存在 `coffer` MCP-server 条目。

## Success Criteria

### Measurable Outcomes

- **SC-001**：在一台至少存在两种受支持 agent 安装路径的机器上，运行发现恰好把这些 agent 作为候选项呈现，用户对每个只需一次确认即可添加——无需手动输入类型标识或路径。
- **SC-002**：从一份全新安装开始，用户能在 60 秒内用自定义 `skill_dir` 注册一个额外 agent，并在 `coffer agent list --json` 中看到它，期间最多查阅一次文档。
- **SC-003**：本 spec 中每一个 Acceptance Scenario 至少被一个带 `acceptance(spec="004-agent-registry", scenario="…")` 标记的测试覆盖；`make verify-acceptance` 报告零未覆盖 scenario。
- **SC-004**：完整 `make verify` 套件在本地与 CI 中通过；`make verify-all`（额外包含 e2e）在 macOS 与 Linux 上通过。
- **SC-005**：任何 `skill_dir` 值都不允许写到该目录之外（path-traversal 检查），由一个专门的安全测试验证。
- **SC-006**：用户能从桌面应用与 CLI 两端打开、编辑并保存 agent 的 `settings.json`（Claude Code）或 `config.toml`（Codex）；畸形的保存会被拒绝且文件保持不变，成功保存时会保留上一版本的 `.bak`。
- **SC-007**：用户能一键把 Coffer 的 MCP 安装到一个新注册的 agent，重启该 agent 后它能列出 Coffer 聚合的工具；重复安装绝不产生重复条目，卸载将其移除。

## Assumptions

- 用户在自己的机器上运行 Coffer；不存在多租户或远程访问需求。
- v1 支持的两种 agent 类型（`claude_code`、`codex`）足以覆盖用户已安装的 agent；增加新类型（例如 Claude Desktop 聊天应用、Cursor、Gemini CLI）属于后续 spec 的改动，新增一个 enum 值、一个安装标记扫描器与一份配置文件 allowlist。
- 每个受支持 agent 的 CLI 与 app/IDE 形态读取同一个共享配置目录（Claude Code 用 `~/.claude/`，Codex 用 `~/.codex/`），因此 Coffer 对每个 agent 管理一份配置集合。
- 配置文件以可编辑、可保存的原始文本方式呈现（带 `.bak` 兜底）；编辑器内的查找/替换是一项 UI 便利功能。结构化的逐字段编辑、以及对 `~/.claude.json` 内 MCP-server 列表的管理（超出一键写入的 Coffer 条目之外）不在 v1 范围内。凭据/状态文件 `~/.codex/auth.json` 被有意排除在 allowlist 之外。
- agent 把自己的 skill 库存放在本地文件系统中一个可被发现的目录里。仅 Web 形态的 agent（例如 claude.ai）超出 v1 范围，需要后续 spec 通过 API 同步加入。
- 由 spec 001-mcp-gateway 定义的 kind-agnostic Resource 框架、audit 日志与 `<kind>:<name>` 标识方案已就绪。
- 来自 spec 002-ui-shell 的应用外壳——侧栏 IA、布局、路由骨架与设计系统——已就绪。桌面 Agents 页面渲染在该外壳内的 `/agents`，作为一个**独立的顶级导航项**（与 Resources、System 分组平级，**不**嵌套在 Resources 之下——agent 是 vault 资产的消费者，而非资产本身）。agent 资源不出现在 kind-agnostic 的资源/MCP 浏览页中，该页只列出注册了资源卡片 UI 的 kind。
- Skill bindings（agent 与某个 skill 之间的关系）由 spec 005-skill-manager 引入和管理；spec 004 不定义 skill 操作，只暴露一个用于级联清理的 `on_delete` 钩子。
