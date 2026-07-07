# 功能规范：Agent Registry

> English: [spec.md](./spec.md)

**Feature Branch**: `feature/004-agent-registry`
**Created**: 2026-05-22
**Status**: Accepted
**Input**: 用户描述：「管理 Coffer 已知的本地安装 AI agent，让后续功能（skills、memory、knowledge base）能向它们投递资产。每个 agent 都是 kind-agnostic Resource 框架（由 spec 001-mcp-gateway 引入）下 kind 为 `agent` 的一种 Resource。v1 支持两种 agent 类型：Claude Code 与 OpenAI Codex——每种都同时涵盖其 CLI 与桌面/IDE 形态，因为它们共享同一份磁盘配置。除注册 agent 外，用户还能查看（只读）每个 agent 的已知配置文件并在外部编辑器中打开它们，并一键把 Coffer 自己的 MCP server 安装到某个 agent 上。」

> **关于 agent 类型的说明。** 受支持的产品：**Claude Code**（`claude_code`，`~/.claude/`）、**OpenAI Codex**（`codex`，`~/.codex/`），以及——由下方多 agent 增补重新加回的——**opencode**（`opencode`，`~/.config/opencode/`），随后的 slice 还将加入 **hermes**（`~/.hermes/`）与 **cursor**（`~/.cursor/`）。每种都同时覆盖其 CLI _与_ app/IDE 形态，因为它们读取同一个共享配置目录。每类型的行为都集中在能力清单（`AGENT_DESCRIPTORS`）里——新增一个产品 = 一个枚举值 + 一条描述符记录（配置文件 allowlist、MCP 注入形态等）。独立的 **Claude Desktop** 聊天应用（拥有自己的 `~/Library/Application Support/Claude/` 配置）不在范围内。

> **多 agent 重新加宽增补（[ADR-040](../../docs/decisions/ADR-040-re-widen-agent-registry.zh.md)）。** 早先的一次简化把 registry 收窄到两个产品，并删除了 `cursor` / `opencode` / `openclaw` / `hermes` 枚举值（数据迁移 `0031`）。本增补为另外三个**受管 coding CLI**——`opencode`、`hermes`、`cursor`——撤销该收窄，每个都作为一条 `AgentDescriptor` 记录交付，外加当其 wire 协议尚未被覆盖时的一个 chat-provider 适配器（spec 008）。清单还是它一贯的那个接缝；重新加宽是数据、而非新机制，除非某产品的原生格式不同于两个原始 agent 所用的 JSON/TOML。有两条约束被记录为**能力 gap** 而非 bug，并经清单呈现，使不受支持的操作被隐藏而非失败：(a) `opencode` 没有 shell 命令生命周期 hook——只有进程内 JS 插件回调——因此其 session-context 注入不同于 Claude Code/Codex；(b) `cursor` 锁死在 Cursor 自己的后端，不暴露自定义 LLM base URL，因此 provider/API-key 投影（spec 011）对它是 **N/A**。第四个被移除的类型 **openclaw** **不**作为受管叶子 agent 重新加回：它是一个自身编排 coding CLI 的对等网关，只能作为 OpenAI 兼容端点集成，留给独立的设计线（[ADR-040](../../docs/decisions/ADR-040-re-widen-agent-registry.zh.md) 记录了原因）。逐 agent 的 facet 支持在 Requirements（FR-003）下的 **Agent 能力矩阵**中列表化。

> **工作区增补（Workspace amendment）。** Story 9–12 把 registry 扩展到 agent 真实的磁盘工作区：agent 自己文件里实际配置的 MCP server、agent 已安装的插件、以及目录型配置条目。指导原则是**收编 → 主库 → 投递（ingest → hub → deliver）**：在 agent 工作区里发现的任何可共享内容，都可以被收编进 Coffer 的中枢（MCP 网关、spec 005 的 skill 主库），再投递给任意 agent，而不是作为各 agent 各自为政的一次性配置存在。所有写操作只经由每个 agent 的文档化配置路径；内部状态文件只读、绝不写入。

> **关于内置 agent（[ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.zh.md)）。** 本 registry 只持有**受管** agent——本地安装、由 Coffer 投递资产的外部 coding agent（Claude Code、Codex……）。原 `builtin`「Coffer Assistant」**不**是这里注册的 agent：[ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.zh.md) 让它退出聊天人格，把其本地模型重塑为只能通过 `coffer__*` MCP 工具触达的 Coffer 内部能力。（spec 008 中那个独立的聊天 agent-provider 注册表同样去掉 `builtin` provider，只列受管 agent。）

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

部分用户把 agent 装在非默认位置，或者同时有多个安装（工作、个人）。他们需要按类型添加一个 agent，并可选地覆盖配置目录。名称是可选的——省略时 Coffer 会派生一个稳定的按类型默认名。选择自定义路径时，桌面应用提供一个文件夹选择器（打包应用用 OS 原生对话框；Web 用 daemon 支撑的文件夹浏览器），使用户挑选一个真实目录，而不是手动输入。

**为什么是这个优先级**：发现覆盖常见情况，手工注册覆盖长尾。没有它，registry 就不完整。

**独立可测**：从命令行用 `--config-dir /custom/path` 注册一个名为 `codex-work` 的 `codex` agent；列出 agent，观察该手工注册条目。从桌面表单添加一个不带名称的 agent，观察它以按类型默认名注册。

**代表性场景**：

- register an agent with a custom config dir
- 不带显式名称注册一个 agent
- config_dir 缺失或不可写时拒绝注册
- 拒绝重复的 agent 名
- browse local folders to choose a config dir

---

### User Story 3 —— 编辑或移除一个 agent（优先级 P1）

用户的本地 agent 安装情况会随时间变化。他们需要更新 config_dir 路径或描述，或彻底删除。（agent 没有启用/禁用的概念——已注册的 agent 就是存在的。）

**为什么是这个优先级**：一个不可变的 registry 一周内就会失去用处。

**独立可测**：注册一个 agent，更新其 config_dir，最后移除；验证每一步状态都被持久化并写入 audit。

**代表性场景**：

- 更新已存在 agent 的 config_dir
- 移除一个 agent 并观察 audit 条目

---

### User Story 4 —— 在桌面应用中管理 agent（优先级 P2）

用户打开 Coffer 桌面应用，看到一个「Agents」页面，列出每个已注册 agent 的类型、名称与 config_dir，并能在表单里添加或编辑。

**为什么是这个优先级**：非 CLI 用户需要一个可视化界面来理解 registry。

**独立可测**：打开桌面应用 → Agents → 用默认路径添加 Codex → 在列表里观察 → 点进去 → 修改 config_dir → 保存 → 列表更新。

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

### User Story 7 —— 查看一个 agent 的配置文件并在外部编辑器中打开它们（优先级 P2）

agent 注册之后，用户希望直接在 Coffer 里查看该 agent 自己的配置文件（例如 Claude Code 的 `settings.json`、Codex 的 `config.toml`），无需离开应用去翻找 dotfile。Coffer 展示该 agent 类型的一组精选已知配置文件，让用户打开其中一个，在**只读**查看器中读取当前内容。对每个文件，Coffer 提供「在外部编辑器中打开」「在文件管理器中显示」等操作，让用户在自己的编辑器里做任何编辑。Coffer 不就地编辑配置文件内容；程序化写入路径（REST/CLI）保留校验 + 原子写入 + `.bak` 兜底。

**为什么是这个优先级**：手工定位 agent 配置意味着要记住每个文件在哪、用什么格式。把这组精选文件集中到一处呈现、一眼可见、一键进入用户自己的编辑器——是让 registry 超越「记账」、真正变得有用的第一个功能。

**独立可测**：注册一个 `claude_code` agent；列出其配置文件；在只读查看器中打开 `settings.json`，观察响应给出该文件的 `path` 与其所在文件夹的 `folder_path`（支撑 打开/显示）；打开一个尚未创建的文件（如 `CLAUDE.md`），观察它读为空内容且未被创建。

**代表性场景**：

- 列出 agent 的精选配置文件，带存在性与大小元信息
- 读取一个已存在配置文件的内容
- 把尚未创建的配置文件读成空内容
- 拒绝读取不在该 agent 类型 allowlist 内的 key

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

### User Story 9 —— 查看并管理 agent 真实的 MCP server（优先级 P2）

如今 agent 的 MCP 服务器 tab 只能回答「Coffer 自己的 shim 装没装」。用户想看到的是自己的 agent **实际**配置了什么：agent 自己配置文件里的每一条 MCP server 条目——Claude Code 从 `~/.claude.json` 的 `mcpServers` 与 `settings.json` 的 `mcpServers` 双源解析，Codex 从 `config.toml` 的 `[mcp_servers.*]` 解析。每条目显示传输方式（stdio 命令或 HTTP URL）、来源文件，以及（仅 Codex——其格式定义了逐条目开关）启用状态。用户可以移除条目，或切换 Codex 条目的开关；Coffer 自己的 `coffer` 条目特殊呈现，由既有的安装/卸载动作管理。

**为什么是这个优先级**：当前 tab 对每个 agent 显示同一份 Coffer 全局列表，具有误导性。呈现 agent 的真实配置是其他一切 MCP 管理动作的前提。

**独立可测**：注册一个 `config.toml` 带若干 `[mcp_servers.*]` 条目的 `codex` agent；打开 MCP tab；观察恰好这些条目连同传输方式与启用标志被列出；移除一条并观察它从文件中消失（保留 `.bak`）；切换另一条并观察其 `enabled` 字段被就地改写。

**代表性场景**：

- list an agent's real MCP entries
- remove a direct MCP entry
- toggle a Codex MCP entry's enabled flag
- reject toggling a Claude Code MCP entry
- degrade to read-only when MCP config is unparseable

---

### User Story 10 —— 把直连 MCP server 收编进 Coffer（优先级 P2）

一条直连 MCP 条目只惠及一个 agent。用户对某条直连条目点击「收编进 Coffer」：Coffer 把它注册为 `mcp_server` 资源（从而经网关服务于**所有** agent），并从 agent 配置中移除这条已多余的直连条目。若条目的环境变量携带疑似密钥的值，Coffer 引导其存入 OS keychain、资源只存引用。若已存在等价资源，Coffer 提议只移除重复的直连条目。

**为什么是这个优先级**：这是 Coffer hub-and-spoke 模型的「收编」半边——把散落在各 agent 的配置变成共享的、由网关服务的资源的那个动作。

**独立可测**：对一个带直连 stdio 条目的 `codex` agent 执行收编；观察新的 `mcp_server` 资源被注册、直连条目从 `config.toml` 中移除、网关把该上游的工具服务给所有 agent。

**代表性场景**：

- adopt a direct MCP entry into Coffer
- reject adoption on resource name conflict
- require keychain mapping for secret-like env values
- adoption failure leaves agent config untouched

---

### User Story 11 —— 管理 agent 的插件（优先级 P2）

有以文件落盘插件体系的 agent，都在 agent 的插件 tab 暴露：全部已安装插件在同一张表里列出——所属 marketplace 是其中一列，而非按 marketplace 分组的若干区块——带启用状态与磁盘缓存是否存在。每一行可展开，显示该插件的清单信息（描述、版本、作者、主页）以及它附带的 skill、命令、MCP server，这些信息只读地从插件的安装目录（agent 插件清单里记录的 `installPath`）读取。由于这些组件属于该插件，它们在此处展示，而不在 agent 的 Skill / MCP 页面出现——后者只列出 agent 自己的独立资源。插件 facet 通过能力清单（capability manifest）做了泛化——每个 agent 记录带一个 `PluginCapability`（插件模型判别符、写入面的 allowlist key，以及 `can_toggle`/`can_uninstall` 标志），服务按数据分派而非按 agent 分支。每个能力映射到该 agent 的文档化配置面；内部状态文件只读、绝不写入。安装新插件与 marketplace 管理留给 agent 自己的工具链。

各 agent 的插件支持：

| Agent       | 插件模型                                                                                                   | 写入面          | 列出 | 开关 | 卸载                         |
| ----------- | ---------------------------------------------------------------------------------------------------------- | --------------- | ---- | ---- | ---------------------------- |
| Claude Code | `settings.json` 的 `enabledPlugins` 映射（内部 `installed_plugins.json` / `known_marketplaces.json` 只读） | `settings.json` | 是   | 是   | 是（经 `claude plugin` CLI） |
| Codex       | `[plugins."<name>@<marketplace>"]` 表 + 缓存目录                                                           | `config.toml`   | 是   | 是   | 是（条目 + 缓存）            |

**为什么是这个优先级**：插件是真实、持久的 agent 配置，而今天 Coffer 对其完全不可见。可见性加上便宜又安全的写操作（开关、受支持处的卸载）覆盖了日常需求；安装留在它本来就好用的地方。

**独立可测**：注册一个配置了插件的 `codex` agent；打开插件 tab；观察插件按 marketplace 分组并带启用状态；禁用一个并观察 `config.toml` 中写入 `enabled = false`；卸载一个并观察其配置条目与缓存目录都消失。

**代表性场景**：

- list an agent's plugins with enabled state
- surface a plugin's manifest detail (version/description/author) and the skills, commands, and MCP servers it bundles, read from its install directory
- toggle a plugin's enabled state
- uninstall a Codex plugin
- uninstall a Claude Code plugin via its CLI (Coffer never hand-writes Claude's internal files)
- reject Claude uninstall when its plugin CLI is unavailable
- flag a plugin whose cache is missing

---

### User Story 12 —— 管理目录型配置条目（优先级 P2）

有些 agent 配置不是单个文件而是一个 prose 文件目录——Claude Code 的 `agents/` 目录下每个个人 subagent 一个 Markdown 文件。用户在配置文件 tab 展开这样的条目，看到其中的文件，在只读查看器中打开某个（带对该子文件及其文件夹的「在外部编辑器中打开」「显示」）。新建、写入与删除单个文件通过 REST API / `coffer agent` CLI 以程序化方式提供——校验、原子写入与 `.bak` 兜底与单文件条目完全一致。allowlist 还新增 Codex 的 `hooks.json`；把 `memory` key 改名为 `instructions`（CLAUDE.md / AGENTS.md 是人写的指令，不是 agent 自写的记忆）。

**为什么是这个优先级**：subagent 定义正是 hub 模型希望「先可见、后可收编」的那类可共享 prose；今天它们完全不可见。

**代表性场景**：

- list a directory config entry's files
- create a file inside a directory entry
- delete a file inside a directory entry
- reject directory file paths outside the entry
- reject stale config-file writes

---

### Edge Cases

- **第二次扫描时的发现**：已注册的类型不会作为候选项被提供；发现绝不重复已有条目。
- **用户删除一个 agent**：移除并非永久。下次扫描会把该 agent 重新作为候选项呈现（删除可能是误操作）；Coffer 不保留任何抑制列表。用户再确认一次即可重新添加。
- **agent 类型不在受支持列表中**：注册拒绝，给出清晰错误信息与受支持类型列表（清单中的类型——`claude_code`、`codex`、`opencode`，以及稍后的 `hermes` / `cursor`）。
- **`config_dir` 路径不存在或不可写**：注册拒绝；不留下任何中间状态。
- **`config_dir` 指向特权路径**（`/etc`、`/usr` 等）：注册拒绝。
- **在 `agent` kind 内出现重名**：被 kind-agnostic Resource 框架拒绝。
- **配置文件 key 不在该类型 allowlist 内**：读取以 `not_found`（404）拒绝；对未知 key 不做任何文件系统访问。
- **配置文件尚不存在**：以 `exists=false` 与空内容列出并可读；读取绝不创建该文件。
- **Coffer MCP 已安装时再次安装**：幂等——就地更新 `coffer` 条目，绝不重复；状态仍为 `installed`。
- **未安装时卸载 Coffer MCP**：空操作（no-op）成功；状态报告 `not_installed`。
- **无法解析 `coffer-mcp-shim` 二进制**：安装被拒绝并给出指明缺失二进制的清晰错误；不向 agent 配置写入任何内容。
- **在主目录之外浏览文件夹**：daemon 支撑的文件夹浏览器列出用户导航到的任何可读目录的子目录；它绝不返回文件内容。不可读或不存在的路径返回错误，而非部分列表。
- **agent 配置文件解析失败**：受影响的 facet（MCP 条目、插件）显示明确的解析错误状态并降级只读；其他 facet 与 tab 不受影响。在文件恢复可解析之前，对该文件的写操作一律拒绝。
- **同一 MCP 条目名同时出现在 Claude Code 的两个来源文件中**：两条都列出，各自标注来源文件；移除/收编请求携带来源，确保编辑正确的那份。
- **Coffer 自己的 `coffer` MCP 条目**：永不可收编，也不作为普通直连条目列出——它是网关的安装状态，由 Story 8 的安装/卸载管理。
- **对与既有资源等价的条目请求收编**：Coffer 报告匹配（`matches_resource`），并提议移除多余的直连条目，而非创建重复资源。
- **插件已配置但缓存目录缺失**：以 `cache_present=false` 列出，让用户看到漂移；Coffer 不尝试修复（重装属于 agent 自己的工具链）。
- **agent 自身进程在 Coffer 读与写之间改写了配置文件**：写入因指纹不匹配被拒绝为过期（409）；用户重新读取后重试。Coffer 每次写入保留的 `.bak` 在相反方向的竞争中保证旧内容可恢复。
- **指令文件包含 spec 007 的记忆投影受管块**：只读查看器标注该区块由记忆功能管理；任何编辑都发生在用户的外部编辑器中。
- **`~/.codex/auth.json` 及其他凭据/状态文件**：永不进入任何 allowlist 或列表；插件与 MCP 解析也绝不读取它们。

## Acceptance Scenarios

按 `agents/sdd.md` 与 `agents/testing.md` 的约定，本节中每一个 scenario 都至少被一个带 `@pytest.mark.acceptance(spec="004-agent-registry", scenario="…")`（Python）或 `acceptance("004-agent-registry", "…", …)`（TypeScript）标记的测试引用。

### Scenario: discover installed agents as candidates

- **Given** 一份存在 `~/.codex/` 且尚未注册任何 agent 的 Coffer 安装，
- **When** 用户运行发现，
- **Then** Coffer 报告一个 `codex` 候选项（类型、显示名、默认配置目录、建议名称）且不注册任何内容——发现是只读的。

### Scenario: skip already-registered types on subsequent scan

- **Given** 已注册一个 `codex` agent，
- **When** 用户再次运行发现，
- **Then** `codex` 不会作为候选项被提供。

### Scenario: re-surface removed agents on subsequent scan

- **Given** 一个 agent 已被用户移除，且其安装标记仍然存在，
- **When** 用户再次运行发现，
- **Then** 该 agent 再次作为候选项被提供（移除并非永久；没有抑制列表）。

### Scenario: register an agent with a custom config dir

- **Given** daemon 正在运行，
- **When** 用户以一个明确、可写的 `config_dir` 注册一个受支持类型的 agent，
- **Then** 该 agent 以该路径被持久化（并自动创建其 `<config_dir>/skills` 子目录），并出现在 `coffer agent list` 中。

### Scenario: reject registration with an invalid config dir

- **Given** daemon 正在运行，
- **When** 用户注册的 agent 的 `config_dir` 不存在、不是目录或不可写，
- **Then** 注册被拒绝并给出指向该路径的错误信息，且不留下任何持久化数据。

### Scenario: reject duplicate agent name

- **Given** 已经存在名为 `codex-work` 的 agent，
- **When** 用户尝试用同一名字再注册一个 agent，
- **Then** 注册被拒绝并给出清晰错误。

### Scenario: reject a second agent for an already-registered config dir

- **Given** 已注册一个 `codex` agent（其配置目录为 `~/.codex`），
- **When** 用户尝试再注册一个 `codex` agent（解析到同一个配置目录），即便名称与 config_dir 不同，
- **Then** 注册被拒绝并给出清晰错误，且不持久化任何内容——同一个配置目录至多只能注册一个 agent。

### Scenario: register an agent without an explicit name

- **Given** daemon 正在运行，
- **When** 用户注册一个受支持类型的 agent 但不提供名称，
- **Then** 该 agent 以一个稳定的按类型默认名注册（下划线变连字符，如 `claude_code` → `claude-code`）。

### Scenario: browse local folders to choose a config dir

- **Given** daemon 正在运行，
- **When** Web 文件夹浏览器请求某个可读目录的子目录，
- **Then** Coffer 返回该目录的路径、其父目录与其直接子目录（不含文件内容）；不可读或不存在的路径返回错误。

### Scenario: open a managed file via the daemon (web open/reveal)

- **Given** daemon 正在运行，只读查看器正在显示一个受管文件，
- **When** Web 界面请求 daemon 打开一个已存在的绝对路径（可选带首选编辑器）或在文件管理器中显示它，
- **Then** daemon 为该路径启动 OS 应用 / 文件管理器并返回成功；相对路径或不存在的路径被拒绝，且不启动任何进程。

### Scenario: update an existing agent

- **Given** 一个已注册的 agent，
- **When** 用户把它的 `config_dir` 更新到一个新的可写路径，
- **Then** 变更被持久化，写入 audit 条目，后续操作看到新路径。

### Scenario: remove an agent

- **Given** 一个已注册的 agent（任何 binding 清理由 the 005-skill-manager spec 处理），
- **When** 用户移除它，
- **Then** 该 agent 被删除，写入 audit 条目，`coffer agent list` 不再显示它。

### Scenario: desktop app agents page

- **Given** Coffer 桌面应用已启动，且至少有一个已注册 agent，
- **When** 用户打开 Agents 页面，
- **Then** 每个已注册 agent 都带有类型、名称与 `config_dir` 出现在列表中。

> Story 4 的桌面表单 add/edit/remove 流程在 e2e 层覆盖；打包的 acceptance 标记见 `e2e/web/specs/shell_agents.spec.ts`。

### Scenario: CLI surface mirrors REST operations

- **Given** daemon 正在运行并暴露 REST agent 路由，
- **When** 用户调用 `coffer agent add`、`list`、`edit`、`rm` 或 `detect`，
- **Then** 每个子命令调用对应的 REST endpoint 并产生等价的状态变化；每个读取类子命令额外支持 `--json` 以输出机器可读结果。

### Scenario: reject registration into privileged system path

- **Given** daemon 正在运行，
- **When** 用户尝试注册的 agent，其 `config_dir` 落在特权位置（`/etc`、`/usr`、`/bin`、`/sbin`、`/System`、`C:\Windows` 或 `C:\Program Files`）之下，
- **Then** 注册以 `unprocessable_entity`（422）被拒绝，且不产生任何 resource 行、audit 事件或文件系统写入。

### Scenario: audit lifecycle events

- **Given** 用户已经注册、编辑或移除过 agent，
- **When** 查看 audit 日志，
- **Then** 每一次生命周期变化（创建、更新、移除）都通过 kind-agnostic 的 `resource_created` / `resource_updated` / `resource_deleted` 事件呈现，每条都携带时间戳、actor 与对应 agent 引用。（agent 没有启用/禁用的概念；发现是只读的、不注册任何内容——二者都不发出任何 audit 事件。）

### Scenario: reject unsupported agent type

- **Given** daemon 正在运行，
- **When** 用户尝试注册受支持集合之外的类型（例如 `claude_desktop`、`gemini_cli` 或一个垃圾值），
- **Then** 注册以 `unprocessable_entity`（422）被拒绝，并指明受支持类型，且不留下任何持久化数据。

### Scenario: list an agent's config files

- **Given** 一个已注册的 `claude_code` agent，
- **When** 用户列出其配置文件，
- **Then** Coffer 返回该类型的精选集合——`settings.json`、`settings.local.json`、`~/.claude.json`、`CLAUDE.md`（key 为 `instructions`）以及 `agents/` 目录条目——每个都带解析后的路径、其所在文件夹的绝对路径（`folder_path`）、格式与 `exists` 标志（存在时附带大小与修改时间）。

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
- **When** 用户通过 REST API 或 `coffer agent` CLI 向该配置文件 key 写入新的、格式良好的内容（应用内 UI 是只读的），
- **Then** Coffer 按文件格式校验内容，原子写入并保留上一版本的 `.bak`，写一条 `agent_config_file_written` audit 条目，下次读取即可读回新内容。

### Scenario: reject malformed config-file content

- **Given** 一个 `settings.json`（`json` 文件）已存在的已注册 agent，
- **When** 用户通过 REST API 或 `coffer agent` CLI 向该 key 写入畸形内容（如非法 JSON）（应用内 UI 是只读的），
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

### Scenario: list an agent's real MCP entries

- **Given** 一个已注册的 `codex` agent，其 `config.toml` 定义了若干 `[mcp_servers.*]` 条目（含 `coffer`），
- **When** 用户列出该 agent 的 MCP 条目，
- **Then** Coffer 返回每个条目的名称、来源文件、传输方式（stdio 命令或 HTTP URL）与 `enabled` 标志，把 `coffer` 条目标记为 `is_coffer=true`，且不存储任何内容——列表在读取时从文件派生。

### Scenario: remove a direct MCP entry

- **Given** 一个带直连（非 Coffer）MCP 条目的已注册 agent，
- **When** 用户移除该条目（`claude_code` 时携带来源文件），
- **Then** 该条目恰好从其来源文件中被原子写入删除并保留先前内容的 `.bak`，写一条 `agent_mcp_entry_removed` audit 条目，下次列出不再显示它。

### Scenario: toggle a Codex MCP entry's enabled flag

- **Given** 一个已注册 `codex` agent 带一条启用中的直连 MCP 条目，
- **When** 用户禁用该条目，
- **Then** 该条目在 `config.toml` 中的 `enabled` 字段被就地改写（原子 + `.bak`），列表反映新状态。

### Scenario: reject toggling a Claude Code MCP entry

- **Given** 一个带直连 MCP 条目的已注册 `claude_code` agent，
- **When** 用户尝试切换该条目的启用状态，
- **Then** 请求以 `unprocessable_entity`（422）与说明性错误码被拒绝——Claude Code 的格式没有逐条目启用标志——且不触碰任何文件。

### Scenario: degrade to read-only when MCP config is unparseable

- **Given** 一个已注册 agent，其承载 MCP 的配置文件包含非法 JSON/TOML，
- **When** 用户列出该 agent 的 MCP 条目，
- **Then** Coffer 报告一个指明文件与解析错误的解析失败状态而非让请求失败，并在该文件恢复可解析之前拒绝对它的条目级写操作。

### Scenario: adopt a direct MCP entry into Coffer

- **Given** 一个已注册 agent 带一条名称与既有资源不冲突的直连 stdio MCP 条目，
- **When** 用户收编该条目，
- **Then** Coffer 先注册一个等价的 `mcp_server` 资源（schema 校验、审计），验证其可读回，再从 agent 配置中移除该直连条目（原子 + `.bak`），写一条 `agent_mcp_entry_adopted` audit 条目，且该上游现在经网关服务于所有 agent。

### Scenario: reject adoption on resource name conflict

- **Given** 已存在与某直连条目同名的 `mcp_server` 资源，
- **When** 用户不改名收编该条目，
- **Then** 请求以 `conflict`（409）拒绝并附建议替代名，不创建资源，agent 配置不被触碰。

### Scenario: require keychain mapping for secret-like env values

- **Given** 一条直连 MCP 条目，其环境变量在疑似密钥的 key（如 `API_TOKEN`）下携带值，
- **When** 用户收编该条目但未为该 key 提供 keychain 映射，
- **Then** 请求被拒绝并列出未解决的 key；提供映射后，密钥经 daemon 存入 OS keychain，创建的资源配置只携带引用、绝不携带值。

### Scenario: adoption failure leaves agent config untouched

- **Given** 一次在资源注册之后失败的收编尝试（如配置文件写入因过期被拒），
- **When** 操作中止，
- **Then** 已创建的资源被回滚，agent 配置文件与尝试前逐字节一致，失败以特定错误码报告。

### Scenario: list an agent's plugins with enabled state

- **Given** 一个已注册 `codex` agent，其 `config.toml` 定义了 `[marketplaces.*]` 与 `[plugins."<name>@<marketplace>"]` 条目且缓存目录存在，
- **When** 用户列出该 agent 的插件，
- **Then** Coffer 返回每个插件的 `<name>@<marketplace>` id、启用状态、marketplace 分组与 `cache_present=true`，一切在读取时从文档化文件派生。

### Scenario: toggle a plugin's enabled state

- **Given** 一个带启用中插件的已注册 agent，
- **When** 用户禁用它，
- **Then** 只有文档化位置被写入——Codex 条目的 `enabled` 字段，或 Claude Code `settings.json` 的 `enabledPlugins` 映射——内部插件状态文件在前后逐字节一致，并写一条 `agent_plugin_toggled` audit 条目。

### Scenario: uninstall a Codex plugin

- **Given** 一个带已安装插件的已注册 `codex` agent，
- **When** 用户卸载它，
- **Then** `[plugins."…"]` 条目从 `config.toml` 中移除（原子 + `.bak`），该插件在 `~/.codex/plugins/cache/` 下的缓存目录被删除，并写一条 `agent_plugin_uninstalled` audit 条目。

### Scenario: uninstall a Claude Code plugin via its CLI

- **Given** 一个带已安装插件的已注册 `claude_code` agent，且 `claude` CLI 在 PATH 上，
- **When** 用户卸载它，
- **Then** Coffer 运行 `claude plugin uninstall <id>`（绝不亲手写 Claude 的内部 `installed_plugins.json` / `settings.json`），请求成功，并写一条 `agent_plugin_uninstalled` audit 条目。

### Scenario: reject Claude uninstall when its CLI is unavailable

- **Given** 一个 `claude` CLI 不在 PATH 上的已注册 `claude_code` agent，
- **When** 用户尝试卸载某插件，
- **Then** 请求以 `unprocessable_entity`（422）与错误码 `PLUGIN_UNINSTALL_UNSUPPORTED` 被拒绝，且不写任何内容——此时列表也隐藏应用内的卸载入口。

### Scenario: flag a plugin whose cache is missing

- **Given** 一个 `codex` agent，其 `config.toml` 引用了一个磁盘上没有缓存目录的插件，
- **When** 用户列出该 agent 的插件，
- **Then** 该插件以 `cache_present=false` 列出，且不尝试任何修复。

### Scenario: list a directory config entry's files

- **Given** 一个已注册 `claude_code` agent，其 `agents/` 目录含 Markdown subagent 文件（可嵌套），
- **When** 用户列出该配置条目，
- **Then** Coffer 返回 `kind=directory` 的条目及其文件（条目相对路径、大小、修改时间）；目录缺失时以 `exists=false`、零文件列出，且读取不创建它。

### Scenario: create a file inside a directory entry

- **Given** 一个带 `agents/` 目录条目的已注册 `claude_code` agent，
- **When** 用户通过 REST API 或 `coffer agent` CLI 向条目内一个新 `.md` 文件路径写入内容（应用内 UI 是只读的），
- **Then** 文件经原子写入机制创建，写一条 `agent_config_file_written` audit 条目，下次列出包含它。

### Scenario: delete a file inside a directory entry

- **Given** 一个含文件的目录条目，
- **When** 用户通过 REST API 或 `coffer agent` CLI 删除该文件（应用内 UI 是只读的），
- **Then** 文件被移除且其先前内容保留为 `.bak`，写一条 `agent_config_file_deleted` audit 条目，下次列出不再显示它。

### Scenario: reject directory file paths outside the entry

- **Given** 一个带目录配置条目的已注册 agent，
- **When** 用户寻址的子路径包含 `..`、绝对路径或非 `.md` 扩展名，
- **Then** 请求在任何文件系统访问之前被拒绝——越界以 `not_found`（404），不允许的扩展名以 `unprocessable_entity`（422）。

### Scenario: reject stale config-file writes

- **Given** 用户读取了某配置文件（或目录子文件），随后它被另一进程在磁盘上修改，
- **When** 用户携带先前读取的指纹写回内容，
- **Then** 写入以 `conflict`（409）拒绝且磁盘文件不变；重新读取得到允许写入的新指纹。

### Scenario: the native memory scan lists an agent's own per-project stores

- **Given** 一个已注册的 `claude_code` agent，其 `<config_dir>/projects/<slug>/memory` 目录含 `.md` 事实文件（外加一个 `MEMORY.md` 索引），
- **When** 用户扫描该 agent 的原生记忆，
- **Then** Coffer 为每个项目返回一个 store，其 `project` 标签与 `path` 为**真实**项目目录（从项目的 session transcript `cwd` 还原，而非有损 slug）、真实的 `memory_dir`，以及排除 `MEMORY.md` 的 `.md` 文件 `item_count`（当某 store 唯一内容是内联 `MEMORY.md` 时为 `1`）——只读，一切在读取时从磁盘派生，且不发出任何 audit 事件。没有原生记忆布局的 agent 类型，或没有 `projects/` 目录的 agent，返回空列表。

### Scenario: the native memory scan lists Codex's global memory by project

- **Given** 一个已注册的 `codex` agent，其 `<config_dir>/memories/MEMORY.md` 含若干 `# Task Group` 块，每块带一行 `applies_to: cwd=…` 把它路由到一个或多个项目工作目录，
- **When** 用户扫描该 agent 的原生记忆，
- **Then** Coffer 把这份全局单文档解析成「每个不同 cwd 一行」——`project`/`path` 为该 cwd，`item_count` 为路由到此 cwd 的 Task Group 数，`memory_dir` 为所有行共享的那个全局 store——只读且不发出任何 audit 事件；没有 `memories/MEMORY.md` 时列表为空。

### Scenario: importing a native memory store adopts it into Coffer

- **Given** 一个已注册的 `claude_code` agent，以及一个其项目能解析到真实 git 项目的原生记忆 store（通过解码后的 slug，或当有损 slug 无法解码时通过兄弟 transcript `.jsonl` 中记录的 `cwd`），
- **When** 用户按 `memory_dir` 导入该 store，
- **Then** Coffer 读取每个事实文件（跳过 `MEMORY.md`），把每条写成项目作用域的 Coffer memory 事实，进入该项目 store 的 `knowledge/inbox/` 通道（一次受信任的导入可写到 32768 字符的领域上限），上报 `imported`/`skipped` 计数以及解析出的 `store` 与 `project_path`，并把 spec 007 的 organizer 作为**后台**任务调度（`organized=true`），使数十次内部 LLM 调用绝不阻塞请求。这些 memory 写入经 spec 007 既有的 memory 事件审计；导入本身不新增 004 audit 事件。

### Scenario: importing a store outside a git project maps to no Coffer store

- **Given** 一个已注册的 `claude_code` agent，以及一个其路径无法映射到 Coffer 项目的原生记忆 store（不是 git 项目，或有损 slug 无法解码且无 transcript `cwd`），
- **When** 用户导入该 store，
- **Then** Coffer 不污染任何 inbox，返回零导入结果——`imported=0`、`store=null`、`project_path=null`、`organized=false`——而非报错。

## Requirements

### Functional Requirements

**Resource 模型**

- **FR-001**: 系统 MUST 将每个已知的本地 agent 注册为 kind 为 `agent` 的 Resource，按 spec 001-mcp-gateway 的 `<kind>:<name>` 约定，标识为 `agent:<name>`。
- **FR-002**: 系统 MUST 用一个 kind 专属 schema 校验 agent 配置，字段包括 `type`（enum）与 `config_dir`（path，可选的绝对路径覆盖；省略时回退到该类型的标准位置——`claude_code` 用 `~/.claude`，`codex` 用 `~/.codex`）。skill 投递到 `<config_dir>/skills`。
- **FR-003**: 系统 MUST 支持 `claude_code`、`codex` 与 `opencode` 这些 agent 类型，`hermes` 与 `cursor` 由多 agent 增补的后续 slice 加入；注册清单之外的任何类型（例如 `claude_desktop` 聊天应用、某个 Gemini CLI）以 `unprocessable_entity`（422）被拒绝。每类型的行为由能力清单（`AGENT_DESCRIPTORS`）定义，因此新增一个类型 = 一个枚举值 + 一条描述符记录（外加，当该产品的 wire 协议是新的时，一个 chat-provider 适配器）。每个受支持类型都同时覆盖该产品的 CLI 与 app/IDE 形态，二者共享同一个配置目录。某个产品若在上游不存在某个 facet 的能力，就在其描述符中把该 facet 声明为缺失，界面 MUST 隐藏对应操作而非让它失败（逐 facet 的支持见下方能力矩阵）。

**Agent 能力矩阵（FR-003a）。** 逐 agent 的 facet 支持。「✓」= 与两个原始 agent 完全对齐；「N/A」= 该能力在上游不存在（有记录的 gap，作为缺失的描述符 facet 呈现，而非 bug）；形态不同时以注释说明。

| Agent | 配置目录 | chat provider（spec 008） | Coffer-MCP 注入（FR-019） | session hook（FR-043/044） | provider 投影（spec 011） | 原生记忆禁用（FR-046） | 交付 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `claude_code` | `~/.claude/` | Claude Agent SDK | ✓ `mcpServers` JSON | ✓ `settings.json`（Start+End） | ✓ `apiKeyHelper` | ✓ `autoMemoryEnabled` | 已交付 |
| `codex` | `~/.codex/` | `codex app-server` | ✓ `[mcp_servers]` TOML | ✓ `hooks.json`（仅 Start） | ✓ `[model_providers]` env_key | ✓ `features.memories` | 已交付 |
| `opencode` | `~/.config/opencode/` | `opencode run --format json`（JSONL） | ✓ `mcp` typed-local JSON | **N/A**——无 shell hook，仅进程内 JS 插件回调（session-context 注入为后续 plugin-drop slice） | ✓ `provider` 块，`apiKey:"{env:COFFER_PROVIDER_KEY}"` | **N/A**——无跨会话原生记忆 | 本 slice |
| `hermes` | `~/.hermes/` | ACP / OpenAI 兼容 HTTP | ✓ `mcp_servers` YAML | ✓ `on_session_start`/`on_session_end`（config.yaml） | ✓ `model.base_url` | ✓ `memory_enabled:false` | slice 2 |
| `cursor` | `~/.cursor/` | `cursor-agent -p --output-format stream-json`（NDJSON） | ✓ `mcp.json` 中的 `mcpServers` | best-effort `hooks.json`（headless 覆盖未文档化） | **N/A**——锁死 Cursor 后端，无自定义 base URL | **N/A**——仅 IDE 开关，无 CLI | slice 3 |

第四个被移除的类型 `openclaw` 是一个对等网关（自带 agent 运行时、多 agent 路由、原生记忆、MCP host）；它**不是**受管的叶子 agent，不在本矩阵之内（独立的设计线，[ADR-040](../../docs/decisions/ADR-040-re-widen-agent-registry.zh.md)）。

**发现（检测 = 发现 + 确认）**

- **FR-004**: 系统 MUST 提供一个只读的发现操作，扫描每种受支持 agent 类型的常见安装标记，并把已安装但尚未注册的类型作为**候选项（candidate）**报告（每个携带 `type`、`display_name`、`config_dir`、`default_skill_dir` 与 `suggested_name`）。发现 MUST NOT 自动注册任何内容——由用户审阅候选项并确认要添加哪些。daemon MUST NOT 在启动时自动注册 agent。
- **FR-005**: 只要安装标记仍存在，被移除的 agent MUST 在后续扫描中重新作为发现候选项出现——移除并非永久（可能是误操作）。系统 MUST NOT 保留任何「已抑制类型」列表。

**生命周期**

- **FR-006**: 用户 MUST 能注册、列出、查看、更新（config_dir、description）与移除 agent。agent **没有启用/禁用的概念**——已注册的 agent 就是存在的，agent 层面不存在启用/禁用状态。注册时 agent 名称是可选的——省略时系统 MUST 派生一个稳定的按类型默认名（下划线变连字符，如 `claude_code` → `claude-code`）。
- **FR-007**: 注册时系统 MUST 自动创建 `<config_dir>/skills` 子目录，再验证解析后的 `config_dir` 存在、是目录、可写且不是特权系统路径，方可接受该值。skill 投递到 `<config_dir>/skills`。
- **FR-008**: 系统 MUST 拒绝任何会造成重复 `agent:<name>` 的注册，并 MUST 拒绝为同一个配置目录注册多于一个 agent。`config_dir` 由 agent 类型派生，因此每个受支持类型——也即每个磁盘上的配置目录——至多只能注册一次；第二次尝试以 `conflict`（409）拒绝且不持久化任何内容。

**配置文件**

- **FR-013**: 每个受支持 agent 类型 MUST 定义一份精选的配置文件 allowlist（在其能力清单记录中），每个条目携带稳定的 `key`、一个显示名、一个解析后的绝对路径与一个 `format`（`json`、`toml`、`yaml`、`markdown` 或 `text`）。Claude Code → `settings.json`、`settings.local.json`、`~/.claude.json`、`CLAUDE.md`（key 为 `instructions`）与 `agents/` 目录条目（FR-034）；Codex → `config.toml`、`AGENTS.md`（key 为 `instructions`）与 `hooks.json`。原 `memory` key 改名为 `instructions`——这些文件是人写的指令，区别于 agent 自写的记忆（spec 007 的领域）。
- **FR-014**: 用户 MUST 能列出一个 agent 的配置文件，并对每个文件给出其 key、显示名、路径、所在文件夹的绝对路径（`folder_path`）、格式与存在性（文件存在时附带大小与修改时间）。`path`/`folder_path` 这一对支撑只读 UI 的「在外部编辑器中打开 / 在文件管理器中显示」（FR-038）。
- **FR-015**: 用户 MUST 能读取任一 allowlist 内配置文件的内容。不存在的文件读为空内容、`exists=false`，且读取不会创建它。
- **FR-016**: 系统 MUST 通过 REST API 与 `coffer agent` CLI 为任一 allowlist 内配置文件的内容暴露一个程序化写入（保存）；应用内 UI 是只读的，不写入配置文件内容。写入前 MUST 按文件的 `format` 校验内容；畸形的 `json`/`toml` MUST 被拒绝（`unprocessable_entity`，422）且磁盘文件保持不变。`markdown`/`text` 文件接受任意内容。
- **FR-017**: 写入 MUST 是原子的（临时文件 + rename），并 MUST 保留上一版本内容的 `.bak` 副本，使错误编辑可恢复；每次成功写入 MUST 写一条 `agent_config_file_written` audit 条目。Coffer-MCP 安装/卸载操作（FR-022）复用同一套原子写入 + `.bak` 机制。
- **FR-018**: 配置文件的读取与写入 MUST 只能通过 allowlist 内的 `key` 寻址（绝不接受调用方提供的路径）；未知 key 返回 `not_found`（404）且不做任何文件系统访问。

**Coffer MCP 安装**

- **FR-019**: 用户 MUST 能一键把 Coffer 自己的 MCP server 安装到某个 agent。安装把一个 `coffer` stdio MCP-server 条目写进 agent 的 MCP 配置，按该 agent 清单中 `McpInjectionSpec` 声明的形态——`claude_code` 写 `~/.claude.json` 的 `mcpServers`；`codex` 写 `~/.codex/config.toml` 的 `[mcp_servers.coffer]`。`command` 设为 `coffer-mcp-shim` 二进制的绝对路径（先在 `PATH` 中解析，再查找当前解释器的脚本目录——这样即使守护进程的 `PATH` 不含 venv，也能找到装在 venv 里的 shim——最后回退到打包的二进制；环境变量 `COFFER_MCP_SHIM_PATH` 优先于以上全部）。若无法解析 shim，安装被拒绝且不写入任何内容。
- **FR-020**: 安装 MUST 幂等——重复安装就地更新已有的 `coffer` 条目，绝不产生重复。系统 MUST 暴露一个状态操作，报告该 agent 当前是否已安装 Coffer 的 MCP。
- **FR-021**: 用户 MUST 能卸载 Coffer 的 MCP，从 agent 的 MCP 配置中移除 `coffer` 条目。未安装时卸载为空操作（no-op）成功。
- **FR-022**: 安装与卸载 MUST 复用 FR-017 的原子写入 + `.bak` 机制，并写一条 audit 条目（`agent_mcp_installed` / `agent_mcp_uninstalled`）。

**Agent MCP 条目（工作区增补）**

- **FR-025**: 系统 MUST 解析并列出 agent 自己文件中配置的 MCP server 条目——`claude_code` 从 `~/.claude.json` 的 `mcpServers` 与 `settings.json` 的 `mcpServers` 双源解析（每条标注来源文件）；`codex` 从 `config.toml` 的 `[mcp_servers.*]` 解析。每条目携带名称、来源、传输方式（stdio 命令或 HTTP URL）、格式定义了的 `enabled` 标志（Codex）、标记 Coffer 自身网关条目的 `is_coffer`，以及在存在等价已注册 `mcp_server` 资源时给出其名称的 `matches_resource`。条目在读取时派生，绝不存储。
- **FR-026**: 用户 MUST 能移除一条直连 MCP 条目。移除只编辑该条目的来源文件（`claude_code` 在两个文件同名时由调用方消歧），复用 FR-017 的原子写入 + `.bak` 机制，并写一条 `agent_mcp_entry_removed` audit 条目。`coffer` 条目不可经此操作移除——它由 FR-019/FR-021 管理。
- **FR-027**: 用户 MUST 能就地切换 Codex 条目的 `enabled` 标志。对没有逐条目标志的 `claude_code`，切换以 `unprocessable_entity`（422）与说明性错误码被拒绝。
- **FR-028**: 用户 MUST 能把直连 MCP 条目收编进 Coffer。收编 (a) 经标准资源流程（schema 校验 + 审计）把条目注册为 `mcp_server` 资源，(b) 验证资源可读回，再 (c) 按 FR-026 移除来源条目——严格按此顺序。任何失败都中止操作、回滚已创建的资源、保持 agent 配置逐字节不变；成功时审计为 `agent_mcp_entry_adopted`。与既有资源的名称冲突以 `conflict`（409）拒绝并附建议替代名；与既有资源等价的条目经 `matches_resource` 报告，让用户改为移除重复条目。`coffer` 条目永不可收编。
- **FR-029**: 收编 MUST NOT 把密钥值持久化进资源配置。当条目的环境变量在疑似密钥的 key（`TOKEN`、`KEY`、`SECRET`、`PASSWORD` 等模式）下携带值时，收编请求 MUST 为每个被标记的 key 提供 keychain 映射，否则以列出未解决 key 的响应拒绝。映射的值经 daemon 存入 OS keychain（遵循凭据不变量）；资源配置只携带引用。
- **FR-030**: 当某个 agent 配置文件无法解析时，受影响的 facet MUST 降级为明确的解析错误状态（文件路径 + 解析器报错）而不拖垮整个视图，且在该文件恢复可解析之前 MUST 拒绝对它的条目级写操作。

**插件（工作区增补）**

- **FR-031**: 系统 MUST 列出 agent 的已安装插件及启用状态，按 marketplace 分组。`codex` 的列表从 `config.toml`（`[plugins."<name>@<marketplace>"]`、`[marketplaces.*]`）加上文档化缓存目录 `~/.codex/plugins/cache/<marketplace>/<plugin>/` 的存在性派生；`claude_code` 的清单从 `~/.claude/plugins/installed_plugins.json` 与 `known_marketplaces.json` 只读派生，启用状态来自 `settings.json` 的 `enabledPlugins`。已配置但缓存缺失的插件标记 `cache_present=false`；不尝试修复。
- **FR-032**: 用户 MUST 能启用/禁用插件。写操作只触碰文档化位置——Codex 条目的 `enabled` 字段；Claude Code `settings.json` 的 `enabledPlugins` 映射——且 MUST 绝不写 agent 的内部状态文件。审计为 `agent_plugin_toggled`。
- **FR-033**: 用户 MUST 能卸载插件，按每个 agent 的策略分派。`codex`：从 `config.toml` 移除 `[plugins."…"]` 条目并删除该插件的缓存目录。`claude_code`：Coffer 委派给 `claude plugin uninstall <id>`——绝不亲手写 Claude 的内部 `installed_plugins.json`，由该 CLI 拥有这部分状态。当 `claude` CLI 不在 PATH 上时，操作以 `unprocessable_entity`（422）/ `PLUGIN_UNINSTALL_UNSUPPORTED` 拒绝，且应用内卸载入口被隐藏（列表上报 `can_uninstall=false`）；CLI 报错则以 `PLUGIN_UNINSTALL_FAILED`（422）呈现。两条成功路径都审计为 `agent_plugin_uninstalled`。Coffer 不提供插件安装与 marketplace 管理；二者都留给 agent 自己的工具链。

**目录型配置条目（工作区增补）**

- **FR-034**: 配置文件 allowlist 条目 MAY 是**目录条目**（`kind=directory`）：解析到一个目录并列出其文件（条目相对路径、大小、修改时间），而非携带内容。Claude Code 的目录条目是 `agents/`（每个个人 subagent 一个 Markdown 文件，允许嵌套路径）。目录缺失时以 `exists=false`、零文件列出；读取绝不创建它。
- **FR-035**: 用户 MUST 能读取目录条目内的单个文件；该读取对 UI 的只读查看器可用。单个文件的写入（写即创建）与删除是程序化的，通过 REST API 与 `coffer agent` CLI 提供。子路径在任何文件系统访问之前于服务端校验：MUST 解析在条目目录之内（无 `..`、无绝对路径、无 symlink 逃逸）且带 `.md` 扩展名。写入复用 FR-017 机制；删除把先前内容保留为 `.bak`。审计为 `agent_config_file_written` / `agent_config_file_deleted`。
- **FR-036**: 配置文件读取（单文件与目录子文件）MUST 返回内容指纹；写入 MUST 带回该指纹，且当磁盘内容自读取后已变化时以 `conflict`（409）拒绝、文件保持不变。
- **FR-037**: 当指令文件包含由另一个功能定义的受管块——spec 007 的记忆投影块——时，只读查看器 MUST 标注该区块由那个功能拥有。每个块使用其各自独有的标记并被独立改写；标记格式由定义它的功能拥有。

**原生记忆（工作区增补）**

以下两条需求把 registry 扩展到 coding agent 自己的原生逐项目记忆——区别于 FR-013 的 `instructions` 配置文件（CLAUDE.md / AGENTS.md 是人写的指令；这里是 agent 自写的记忆 store）。其「转换」（把导入的事实整理进 Coffer 主题文档）由 spec 007 的 organizer 拥有；本 spec 只读取 agent 的 store 并把其事实交给那个 organizer。

- **FR-040**: 系统 MUST 暴露一个只读的**原生记忆扫描**，列出某 agent 类型自己的原生记忆 store。支持两种布局。`claude_code` 为逐项目布局，store 位于 `<config_dir>/projects/<slug>/memory/`：每个含 `memory/` 目录的项目一行，`item_count` 为排除 `MEMORY.md` 的 `.md` 事实文件数——当无事实文件但 `MEMORY.md` 含内联内容（较旧/手写的 hub 文档）时为 `1`，因为该内联文档本身即可导入条目。`project` 标签与 `path` 为**真实**项目目录，从该项目的 session transcript `cwd` 还原（slug 编码有损——`/`、`.`、`_` 全部坍缩成 `-`——无法可靠从 slug 重建路径；有损 slug 解码仅作最后兜底）。`codex` 为单一**全局** task-grouped 文档，位于 `<config_dir>/memories/MEMORY.md`，其中每个 `# Task Group` 块带一行 `applies_to: cwd=…` 把它路由到一个或多个项目工作目录；扫描把它解析成「每个不同 cwd 一行」，`item_count` 为路由到此 cwd 的 Task Group 数、`path` 为该 cwd（`memory_dir` 为所有行共享的那个全局 store）。没有原生记忆布局的 agent 类型、没有 `projects/` 目录、或没有 `memories/MEMORY.md`，都返回空列表。扫描是只读的，一切在读取时从磁盘派生（不存储），并——遵循 FR-011 的「工作区列表只读，均不发出 audit 事件」——MUST NOT 发出任何 audit 事件。它绝不写入 agent 的 store。
- **FR-041**: 用户 MUST 能把一个原生记忆 store **导入（收编）**进 Coffer。`claude_code`：给定一个 store 的 `memory_dir`，系统读取其事实文件（跳过 `MEMORY.md`，或当无事实文件时解析内联 `MEMORY.md`），解析出真实项目路径——存在于磁盘时用解码后的 slug，否则用兄弟 transcript `.jsonl` 中记录的 `cwd`（slug 解码有损）。`codex`：其全局 store 被所有行共享，故请求另带所选行的 `project_path`，系统只导入路由到该 cwd 的 Task Group 块。两种情况都把每条目写成项目作用域的 Coffer memory 事实，进入该项目 store 的 `knowledge/inbox/` 通道（如同一批 `remember`；一次受信任的导入 MAY 写到 32768 字符的领域上限）。随后把 spec 007 的 organizer 作为**后台**任务触发，因为一次批量导入是数十次顺序的内部 LLM 调用，MUST NOT 阻塞请求。结果上报 `imported`、`skipped`、`store`（项目无法映射到 Coffer store 时为 null）、`project_path` 与 `organized`。任何 git 项目之外的 store（无可映射的 Coffer 项目）产出 `imported=0`、`store=null`、`project_path=null`、`organized=false`——它不污染任何 inbox，也不是错误。导入的 memory 写入经 spec 007 既有的 memory 事件审计；导入不新增任何 004 audit 事件。

- **FR-043**（Slice 6）：用户 MUST 能一键**安装 Coffer 的生命周期 hook** 到某个 agent，并能卸载与查询状态。安装会按该 agent manifest 的 `HookInjectionSpec` 把一条 `coffer-hook` 命令条目写入其 hooks 文件——`claude_code` 为 `settings.json`，`codex` 为 `hooks.json`——命令是 `coffer-hook` 二进制的绝对路径（解析顺序同 shim：`COFFER_HOOK_PATH` 覆盖 → `PATH` → 解释器的 scripts 目录 → 内置）外加 `--agent <name>` 参数，因为外部 hook 负载不携带 Coffer 的 agent 身份。`claude_code` 安装 SessionStart **与** SessionEnd；`codex` **仅**安装 SessionStart（它没有会话结束事件）。安装 MUST 幂等（原位替换 Coffer 自己的条目，按 `coffer-hook` basename 识别，绝不触碰用户自建的 hook）；卸载仅移除 Coffer 的条目。若二进制无法解析，或该 agent 类型不支持 hook，则拒绝安装（`HOOK_INSTALL_UNSUPPORTED`，422）且不写入任何内容。两个事件都审计（`agent_hook_installed` / `agent_hook_uninstalled`）。
- **FR-044**（Slice 6）：在 SessionStart 时，已安装的 hook MUST 能拉取一份**规则 bundle** 作为附加上下文注入：系统从会话的 `cwd` 解析召回作用域（若是 git 项目则有 project，再加 global），按顺序拼接各 store 的规则（先 project 后 global），并**始终**附加两条内置种子规则——一条*恢复*规则（引导 agent 在用户要求继续此前工作时调用 `coffer__resume()`），一条*软引导*规则（优先 `coffer__remember` / `coffer__recall` 而非 agent 自身的原生记忆）。bundle 仅运行时存在（不写入 agent 的任何文件），上限 ≤10000 字符；当任何地方都没有用户规则时仍返回种子规则。通过 `GET /agents/{name}/session-context?cwd=` 暴露。
- **FR-045**（Slice 6）：在 SessionEnd 时（仅 Claude Code——Codex 没有会话结束事件，降级到 FR-046 的补扫），已安装的 hook MUST 能触发对**单个会话**的固化（写入 journal 通道），复用 FR-046 的幂等账本，使某会话绝不会被补扫重复固化。该操作幂等且始终成功（2xx）：无内部引擎、未知会话、已固化或非 git 项目的会话都是被容忍的 no-op。通过 `POST /agents/{name}/sessions/{session_id}/end` 暴露。
- **FR-046**（Slice 6）：用户 MUST 能通过 agent 上的 `disable_native_memory`（默认 false）选择**禁用 agent 的原生写侧记忆**。切换它会同步驱动持久化字段与磁盘变换——Claude Code 在 `settings.json` 置 `autoMemoryEnabled=false`；Codex 在 `config.toml` 置 `features.memories=false` + `memories.generate_memories=false`——使 Coffer 成为唯一的共享记忆 store。切回 false 会恢复 agent 的原生记忆（移除 Coffer 添加的键）。它不会阻止 agent 读取其指令文件（CLAUDE.md / AGENTS.md）。两种切换都审计（`agent_native_memory_disabled` / `agent_native_memory_restored`）。

**界面**

- **FR-009**: 每一个管理操作——注册/列出/查看/更新/移除、配置文件列出/读取/写入（含目录子文件）、Coffer-MCP 安装/卸载/状态、MCP 条目列出/移除/切换/收编、插件列出/切换/卸载、原生记忆扫描/导入（FR-040/FR-041）——MUST 同时通过 (a) REST API 与 (b) `coffer agent ...` CLI 提供。原生记忆命令为 `coffer agent native-memory <name>`（读取，`--json`）与 `coffer agent import-native-memory <name> <memory_dir>`（收编；`--project-path` 为 Codex 共享全局 store 选择 cwd）。桌面 Agents 页面 MUST 暴露以上全部，**除配置文件内容写入之外**（单文件与目录子文件）：在 UI 中，配置文件与目录子文件是**只读**的，带「在外部编辑器中打开 / 在文件管理器中显示」操作（FR-038），而 REST API 与 CLI 保留程序化的写入/创建/删除路径。agent 的 Memory tab 展示 Coffer 受管记忆链接，外加这张原生表格（**只读**，按 FR-038 提供打开 / 显示），并带一个收编某个 store 的导入按钮（FR-041）。
- **FR-010**: CLI MUST 在每个读取类操作上支持 `--json` 以提供机器可读输出。
- **FR-038**: 对每个配置文件（及每个目录条目子文件），UI MUST 提供针对该文件的**在外部编辑器中打开**与**在文件管理器中显示**操作，使用 FR-014/FR-015 的 `path`。打开与显示在**两个**界面上都执行真实的 OS 动作：打包桌面应用（Tauri）直接用 OS opener;Web 用 daemon 的文件系统动作端点（FR-039）——因为环回 daemon 始终在用户自己的机器上（ADR-033）。没有 copy-path 回退。用于「在外部编辑器中打开」的编辑器引用 spec 002-ui-shell 定义的用户「首选外部编辑器」偏好（此处不再重新规定）。

**可观测性**

- **FR-011**: 系统 MUST 为每一个生命周期事件写入一条 audit 条目：agent 创建、更新、移除；配置文件写入/删除（`agent_config_file_written` / `agent_config_file_deleted`）；Coffer MCP 安装/卸载；MCP 条目移除/收编（`agent_mcp_entry_removed` / `agent_mcp_entry_adopted`）；插件切换/卸载（`agent_plugin_toggled` / `agent_plugin_uninstalled`）。（agent 没有启用/禁用的概念；发现与全部工作区列表——含原生记忆扫描 FR-040——都是只读的，均不发出任何 audit 事件。原生记忆导入 FR-041 不新增任何 004 audit 事件：每条导入的事实经 spec 007 既有的 memory 写入事件审计。）
- **FR-012**: 系统 MUST 暴露一个只读的发现操作，把已安装但未注册的 agent 列为候选项，可通过 REST API（`GET /api/v1/agents/candidates`）、`coffer agent detect` CLI 与桌面 Agents 页面访问。

**配置目录选择器**

- **FR-023**: 选择自定义 `config_dir` 时，桌面应用 MUST 提供一个文件夹选择器，而非要求用户手动输入路径。在打包桌面应用中，它 MUST 使用 OS 原生目录对话框；在 Web 上，它 MUST 使用 daemon 原生目录对话框（FR-042），仅当宿主没有原生对话框工具时才退回 daemon 支撑的文件夹浏览器（FR-024）。两者都产出一个绝对路径，随后在注册前按 FR-007 校验。
- **FR-024**: 系统 MUST 暴露一个只读的文件系统浏览操作（`GET /api/v1/fs/browse`），给定一个目录路径（默认用户主目录），返回该路径、其父目录与其直接子目录。它 MUST NOT 返回文件内容，且 MUST 与所有其它 daemon 路由一样受同样的 loopback + token 鉴权保护。
- **FR-042**: 系统 MUST 通过环回 daemon 暴露原生 OS 选择器对话框（ADR-036），让 Web 界面打开宿主的真实对话框，而非要求手输路径：`POST /api/v1/fs/pick-folder`（选目录）、`POST /api/v1/fs/pick-file`（选一个已存在的文件来打开）、`POST /api/v1/fs/save-file`（选目标位置，可带 `suggested_name`）。每个都打开宿主原生对话框（macOS 用 `osascript`；Linux 用 `zenity`/`kdialog`），以固定参数向量调用（无 shell 插值），返回 `{ available, path }`：宿主无原生对话框工具时 `available=false`；用户取消时 `available=true` 且 `path=null`；否则为所选绝对路径。当 `available=false` 时调用方降级——文件夹选择退回应用内浏览器（FR-024），选文件与存文件退回手输路径。三者都不创建任何东西，且与每条 daemon 路由一样受同样的 loopback + token 鉴权保护。

**文件系统打开/显示**

- **FR-039**: 系统 MUST 暴露文件系统动作操作,让 Web 界面经环回 daemon 执行真正的 open/reveal（FR-038）——daemon 始终与 Web 客户端同处用户机器上（ADR-033）:`POST /api/v1/fs/open`(在某个应用里打开一个已存在的绝对路径——一个 `with` 编辑器偏好,或 OS 默认)与 `POST /api/v1/fs/reveal`(在 OS 文件管理器中选中/显示一个已存在的绝对路径)。两者在动作前都 MUST 校验路径为绝对且存在,MUST 以固定参数向量调用 OS 启动器(无 shell 插值),MUST 不创建任何东西,且 MUST 与所有其它 daemon 路由一样受同样的 loopback + token 鉴权保护。非绝对或不存在的路径被拒绝(`FS_PATH_NOT_OPENABLE`,400)。在没有可移植「选中文件」原语的平台(Linux),reveal 降级为打开所在文件夹。系统还 MUST 暴露 `GET /api/v1/fs/editors`,枚举主机上检测到已安装的常见 GUI 编辑器(macOS 返回 `open -a` 用的 app 名;Linux/Windows 返回 PATH 上的命令),以便 spec 002-ui-shell 的首选编辑器设置提供一个选择框而非盲填文本框。它返回每个编辑器的显示标签与 `/fs/open` 的 `with` 所接受的启动 `value`,除应用是否存在外不读取任何内容,并受同样的 loopback + token 鉴权保护。

### Key Entities

- **Agent**：一个 kind 为 `agent` 的 Resource。代表一份本地安装的 AI agent。Config: `type`（受支持的 enum）、`config_dir`（可选的绝对路径覆盖；默认回退到该类型的标准位置）。skill 投递到 `<config_dir>/skills`。标识为 `agent:<name>`。
- **Agent Type**：一个 enum 值，标识一个已知 agent 产品（`claude_code`、`codex`、`opencode`，以及后续 slice 的 `hermes`、`cursor`）。每个值映射到**能力清单**（`AGENT_DESCRIPTORS`）中的一条记录，携带其默认 `config_dir`、显示名、用于发现的安装标记、精选的**配置文件 allowlist**、**MCP 注入形态**，以及可选的 生命周期 hook / provider 投影 / 原生记忆 facet——某产品在上游缺失的 facet 留空（FR-003a 下的能力矩阵），界面隐藏对应操作。
- **Agent Candidate（候选项）**：一个被发现的、已安装但尚未注册的 agent——`type`、`display_name`、`config_dir`（该类型的默认配置目录）、`default_skill_dir` 与 `suggested_name`。在扫描时派生，从不存储；用户确认某个候选项即可注册它。
- **Config File（配置文件）**：属于某个 agent 类型、在 allowlist 内的精选文件，以稳定的 `key` 标识。携带显示名、解析后的绝对路径、其所在文件夹的绝对路径（`folder_path`）、`format`（`json` / `toml` / `markdown` / `text`），以及（存在时）大小与修改时间。在 UI 中只读呈现（查看其内容、在外部编辑器中打开该文件 / 其文件夹）；按 key 读取并程序化写入（REST/CLI），绝不按任意路径。不持久化到 SQLite——磁盘上的文件即为事实来源。
- **Coffer MCP Install Status（安装状态）**：某个 agent 的派生（非存储）状态：其 MCP 配置文件中是否存在 `coffer` MCP-server 条目。
- **Agent MCP Entry（agent MCP 条目）**：agent 自己文件中所配置的一个 MCP server 的派生（绝不存储）视图——名称、来源文件、传输方式、`enabled`（Codex）、`is_coffer`、`matches_resource`。文件是事实来源；Coffer 读取、编辑、移除或收编条目，但不保留副本。
- **Agent Plugin（agent 插件）**：一个已安装插件的派生（绝不存储）视图——id（`<name>@<marketplace>`）、marketplace、启用状态、`cache_present`。启用状态存在于各 agent 的文档化配置面；Claude Code 的清单文件是只读输入。
- **Directory Config Entry（目录型配置条目）**：解析到一个文件目录而非单个文件的 allowlist 配置条目。子文件以校验过的条目相对路径寻址；磁盘上的目录是事实来源。
- **Native Memory Store（原生记忆 store）**：coding agent 自己的某个原生记忆 store 的派生（绝不存储）视图——`claude_code` 为逐项目目录（`<config_dir>/projects/<slug>/memory`），`codex` 为单一全局 task-grouped `<config_dir>/memories/MEMORY.md` 的某个路由 cwd 切片。携带 `project` 标签与 `path`（**真实**项目 cwd）、真实的 `memory_dir`，以及 `item_count`（Claude Code 事实文件 / 内联 `MEMORY.md` / 路由到该 cwd 的 Codex Task Group 数）。只读；agent 的 store 绝不被写入。收编其中一个（FR-041）会把其条目导入匹配的 Coffer 项目记忆的 `knowledge/inbox/` 通道，并交给 spec 007 的 organizer。

## Success Criteria

### Measurable Outcomes

- **SC-001**：在一台至少存在两种受支持 agent 安装路径的机器上，运行发现恰好把这些 agent 作为候选项呈现，用户对每个只需一次确认即可添加——无需手动输入类型标识或路径。
- **SC-002**：从一份全新安装开始，用户能在 60 秒内用自定义 `config_dir` 注册一个额外 agent，并在 `coffer agent list --json` 中看到它，期间最多查阅一次文档。
- **SC-003**：本 spec 中每一个 Acceptance Scenario 至少被一个带 `acceptance(spec="004-agent-registry", scenario="…")` 标记的测试覆盖；`make verify-acceptance` 报告零未覆盖 scenario。
- **SC-004**：完整 `make verify` 套件在本地与 CI 中通过；`make verify-all`（额外包含 e2e）在 macOS 与 Linux 上通过。
- **SC-005**：任何 `config_dir` 值都不允许写到该目录之外（path-traversal 检查），由一个专门的安全测试验证。
- **SC-006**：用户能在 Coffer 中只读打开 agent 的 `settings.json`（Claude Code）或 `config.toml`（Codex），并从桌面应用在其外部编辑器中打开它；程序化保存（REST/CLI）仍会校验内容（畸形的保存会被拒绝且文件保持不变），并在成功保存时保留上一版本的 `.bak`。
- **SC-007**：用户能一键把 Coffer 的 MCP 安装到一个新注册的 agent，重启该 agent 后它能列出 Coffer 聚合的工具；重复安装绝不产生重复条目，卸载将其移除。
- **SC-008**：MCP tab 恰好列出 agent 真实配置文件中存在的条目；收编一条直连条目即完成完整回路——资源已注册、网关在服务它、直连条目已消失——只需一次用户操作加至多一次确认。
- **SC-009**：插件开关只改动文档化配置面：测试断言每次切换前后 agent 的内部状态文件逐字节一致。
- **SC-010**：任何目录条目操作都无法读写其条目目录之外的路径；由覆盖 `..` 穿越、绝对路径、symlink 逃逸与不允许扩展名的专门安全测试验证。

## Assumptions

- 用户在自己的机器上运行 Coffer；不存在多租户或远程访问需求。
- 多种 agent 类型已在能力清单（`AGENT_DESCRIPTORS`）中接线——`claude_code`、`codex` 与 `opencode`（`hermes` 与 `cursor` 随后跟进）——每种都是一个 `AgentType` 枚举值加一条记录（安装标记、配置文件 allowlist、MCP 注入形态，以及它支持的任何可选 facet）。再增加一个产品也是同样的一条记录变更，外加当其 wire 协议是新的时一个 chat-provider 适配器，并在某 facet 于上游不存在时把该 facet 留空（能力矩阵，FR-003a）。从早先的两类型状态重新加宽即 [ADR-040](../../docs/decisions/ADR-040-re-widen-agent-registry.zh.md)。
- 每个受支持 agent 的 CLI 与 app/IDE 形态读取同一个共享配置目录（`~/.claude/` 与 `~/.codex/`），因此 Coffer 对每个 agent 管理一份配置集合。
- 配置文件以原始文本方式只读呈现，供用户查看；编辑发生在用户的外部编辑器中（从查看器打开），而程序化写入路径（REST/CLI）保留校验 + 原子写入 + `.bak` 兜底。只读查看器加上「在外部编辑器中打开」是长尾需求的兜底入口；反复出现的结构化需求按工作区增补「毕业」为 facet（MCP 条目、插件）。凭据/状态文件 `~/.codex/auth.json` 被有意排除在 allowlist 之外。
- agent 的内部状态文件（`~/.claude.json` 中 `mcpServers` 映射之外的部分、`~/.claude/plugins/*.json`、Codex 的 `[marketplaces.*]` / `[hooks.state.*]` / `[projects.*]` 表）在需要时作为输入读取，工作区 facet 绝不写入它们；唯一的写目标是按各厂商文档核实过的文档化配置面。实际情况（已在真实机器上验证）：Claude Code 的 user 级 MCP server 存在于 `~/.claude.json` 的 `mcpServers`，也可能出现在 `settings.json` 的 `mcpServers`——两处都解析。
- 工作区 facet 遵循收编 → 主库 → 投递原则：在 agent 工作区发现的可共享内容收编进 Coffer 的中枢（此处是 MCP 网关；skill 主库经由 spec 005 的配套增补），而非作为各 agent 的一次性配置来管理。中枢本身的跨机器共享属于未来 spec（需修宪）；这些 facet 的设计保证其状态在那一天到来时可直接序列化为声明式清单。
- agent 把自己的 skill 库存放在本地文件系统的 `<config_dir>/skills` 之下。仅 Web 形态的 agent（例如 claude.ai）超出 v1 范围，需要后续 spec 通过 API 同步加入。
- 由 spec 001-mcp-gateway 定义的 kind-agnostic Resource 框架、audit 日志与 `<kind>:<name>` 标识方案已就绪。
- 来自 spec 002-ui-shell 的应用外壳——侧栏 IA、布局、路由骨架与设计系统——已就绪。桌面 Agents 页面渲染在该外壳内的 `/agents`，作为一个**独立的顶级导航项**（与 Resources、System 分组平级，**不**嵌套在 Resources 之下——agent 是 vault 资产的消费者，而非资产本身）。agent 资源不出现在 kind-agnostic 的资源/MCP 浏览页中，该页只列出注册了资源卡片 UI 的 kind。
- Skill bindings（agent 与某个 skill 之间的关系）由 spec 005-skill-manager 引入和管理；spec 004 不定义 skill 操作，只暴露一个用于级联清理的 `on_delete` 钩子。
