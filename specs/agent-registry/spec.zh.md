# 功能规范：Agent Registry

> English: [spec.md](./spec.md)

**Feature Branch**: `feature/agent-registry`
**Created**: 2026-05-22
**Status**: Accepted
**Input**: 用户描述：「管理 Coffer 已知的本地安装 AI agent，让后续功能（skills、memory、knowledge base）能向它们投递资产。每个 agent 都是 kind-agnostic Resource 框架（由 spec mcp-gateway 引入）下 kind 为 `agent` 的一种 Resource。v1 支持两种 agent 类型：Claude Code 与 OpenAI Codex——每种都同时涵盖其 CLI 与桌面/IDE 形态，因为它们共享同一份磁盘配置。除注册 agent 外，用户还能查看并编辑每个 agent 的已知配置文件，也可以在外部编辑器中打开它们，并一键把 Coffer 自己的 MCP server 安装到某个 agent 上。」

> **关于 agent 类型的说明。** 受支持的产品：**Claude Code**（`claude_code`，`~/.claude/`）与 **OpenAI Codex**（`codex`，`~/.codex/`）。每个都同时覆盖其 CLI *与* app/IDE 形态，因为它们读取同一个共享配置目录。每类型的行为存放在能力清单（`AGENT_DESCRIPTORS`）中——新增一个产品是一个枚举值 + 一条描述符记录（配置文件 allowlist、MCP 注入形态等）。独立的 **Claude Desktop** 聊天应用（有它自己的 `~/Library/Application Support/Claude/` 配置）不在范围内。

> **工作区增补（Workspace amendment）。** Story 9–12 把 registry 扩展到 agent 真实的磁盘工作区：agent 自己文件里实际配置的 MCP server、agent 已安装的插件、以及目录型配置条目。指导原则是**收编 → 主库 → 投递（ingest → hub → deliver）**：在 agent 工作区里发现的任何可共享内容，都可以被收编进 Coffer 的中枢（MCP 网关、spec skill-manager 的 skill 主库），再投递给任意 agent，而不是作为各 agent 各自为政的一次性配置存在。所有写操作只经由每个 agent 的文档化配置路径；内部状态文件只读、绝不写入。

> **关于内置 agent（[Built-in Agent Is Internal](../../docs/decisions/builtin-agent-is-internal-capability.zh.md)）。** 本 registry 只持有**受管** agent——本地安装、由 Coffer 投递资产的外部 coding agent（Claude Code、Codex……）。原 `builtin`「Coffer Assistant」**不**是这里注册的 agent：[Built-in Agent Is Internal](../../docs/decisions/builtin-agent-is-internal-capability.zh.md) 让它退出聊天人格，把其本地模型重塑为只能通过 `coffer__*` MCP 工具触达的 Coffer 内部能力。（已退役的 Agent Chat 规范中那个独立的聊天 agent-provider 注册表同样去掉 `builtin` provider，只列受管 agent。）

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

部分用户把 agent 装在非默认位置，或者同时有多个安装（工作、个人）。他们需要按类型添加一个 agent，并可选地覆盖配置目录。名称是可选的——省略时 Coffer 会派生一个稳定的按类型默认名。选择自定义路径时，Web UI 提供一个文件夹选择器——通过本地 daemon 打开宿主的原生目录对话框——使用户挑选一个真实目录，而不是手动输入。

**为什么是这个优先级**：发现覆盖常见情况，手工注册覆盖长尾。没有它，registry 就不完整。

**独立可测**：从命令行用 `--config-dir /custom/path` 注册一个名为 `codex-work` 的 `codex` agent；列出 agent，观察该手工注册条目。从 Web UI 表单添加一个不带名称的 agent，观察它以按类型默认名注册。

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

### User Story 4 —— 在 Web UI 中管理 agent（优先级 P2）

用户打开 Coffer Web UI，看到一个「Agents」页面，列出每个已注册 agent 的类型、名称与 config_dir，并能在表单里添加或编辑。

**为什么是这个优先级**：非 CLI 用户需要一个可视化界面来理解 registry。

**独立可测**：打开 Web UI → Agents → 用默认路径添加 Codex → 在列表里观察 → 点进去 → 修改 config_dir → 保存 → 列表更新。

**代表性场景**：

- agents 页面列出所有已注册 agent
- 通过 Web UI 表单添加一个 agent
- 通过 Web UI 表单编辑一个 agent
- 通过 Web UI 确认对话框移除一个 agent

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

agent 注册之后，用户希望直接在 Coffer 里查看该 agent 自己的配置文件（例如 Claude Code 的 `settings.json`、Codex 的 `config.toml`），无需离开应用去翻找 dotfile。Coffer 展示该 agent 类型的一组精选已知配置文件，让用户打开其中一个、读取当前内容并**就地编辑**。保存时先按格式校验，再以原子方式写入并保留 `.bak`，所以一次坏编辑既会被提前拒绝、也仍可恢复。由于这些文件同时也会在 Coffer 之外被编辑，保存会带上编辑起点那份内容的指纹；一旦文件在此期间被改过，保存会被拒绝而不是覆盖上去（FR-036）。对每个文件，Coffer 同样提供「在外部编辑器中打开」「在文件管理器中显示」，留给那些更适合在真正的编辑器里做的改动。

**为什么是这个优先级**：手工定位 agent 配置意味着要记住每个文件在哪、用什么格式。把这组精选文件集中到一处呈现、一眼可见、一键进入用户自己的编辑器——是让 registry 超越「记账」、真正变得有用的第一个功能。

**独立可测**：注册一个 `claude_code` agent；列出其配置文件；打开 `settings.json`，观察响应给出该文件的 `path`、所在文件夹的 `folder_path`（支撑 打开/显示）以及内容 `fingerprint`；编辑并保存它，观察新内容能读回；打开一个尚未创建的文件（如 `CLAUDE.md`），观察它读为空内容且未被创建。

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

如今 agent 的 MCP 服务器 tab 只能回答「Coffer 自己的 shim 装没装」。用户想看到的是自己的 agent **实际**配置了什么：agent 自己配置文件里的每一条 MCP server 条目——Claude Code 从 `~/.claude.json` 的 `mcpServers` 与 `settings.json` 的 `mcpServers` 双源解析，Codex 从 `config.toml` 的 `[mcp_servers.*]` 解析。每条目显示传输方式（stdio 命令或 HTTP URL）、来源文件，以及（仅 Codex——其格式定义了逐条目开关）启用状态。在同一张表里，用户还可以**删除**一条条目——已经在 Coffer 里有等价物的重复条目，或本来就不该在那儿的条目——写入走的是收编在这些文件上已经在用的那套原子写 + `.bak` 机制。Coffer 不提供的是就地编辑：翻转 Codex 的 `enabled` 开关属于 agent 自己的界面，那里本来就做得到，而 `claude_code` 的格式根本没有逐条目开关。Coffer 自己的 `coffer` 条目特殊呈现，由既有的安装/卸载动作管理。

**为什么是这个优先级**：当前 tab 对每个 agent 显示同一份 Coffer 全局列表，具有误导性。呈现 agent 的真实配置是收编的前提——用户得先看见某个 server 在 hub 之外，才谈得上把它收进来。

**独立可测**：注册一个 `config.toml` 带若干 `[mcp_servers.*]` 条目的 `codex` agent；打开 MCP tab；观察恰好这些条目连同传输方式与来源文件被列出；删除其中一条，观察它从文件中消失，且保留了改动前内容的 `.bak`。

**代表性场景**：

- list an agent's real MCP entries
- remove a direct MCP entry
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

**为什么是这个优先级**：插件是真实、持久的 agent 配置，而这个 tab 正是用户在一处看齐 agent 全部配置面的地方。它提供的写操作都是便宜又安全的那一类——切换一个文档化的开关，以及当安装状态落在 Coffer 不该亲手改写的文件里时，把卸载委派给 agent 自己的 CLI。安装与 marketplace 管理留在它们本来就好用的地方。

**独立可测**：注册一个配置了插件的 `codex` agent；打开插件 tab；观察插件连同其 marketplace 与启用状态被列出；禁用一个并观察 `config.toml` 中写入 `enabled = false`；卸载一个并观察其配置条目与缓存目录都消失。

**代表性场景**：

- list an agent's plugins with enabled state
- toggle a plugin's enabled state
- uninstall a Codex plugin
- uninstall a Claude Code plugin via its CLI (Coffer never hand-writes Claude's internal files)
- reject Claude uninstall when its CLI is unavailable
- flag a plugin whose cache is missing

---

### User Story 12 —— 管理目录型配置条目（优先级 P2）

有些 agent 配置不是单个文件而是一个 prose 文件目录——Claude Code 的 `agents/` 目录下每个个人 subagent 一个 Markdown 文件。用户在配置文件 tab 展开这样的条目，看到其中的文件，打开其中某个进行查看与编辑（带对该子文件及其文件夹的「在外部编辑器中打开」「显示」）。新建、写入与删除单个文件通过 REST API / `coffer agent` CLI 以程序化方式提供——校验、原子写入与 `.bak` 兜底与单文件条目完全一致。allowlist 还新增 Codex 的 `hooks.json`；把 `memory` key 改名为 `instructions`（CLAUDE.md / AGENTS.md 是人写的指令，不是 agent 自写的记忆）。

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
- **agent 类型不在受支持列表中**：注册拒绝，给出清晰错误信息与受支持类型列表（清单中的类型——`claude_code`、`codex`）。
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
- **同一 MCP 条目名同时出现在 Claude Code 的两个来源文件中**：两条都列出，各自标注来源文件；收编请求携带来源，确保收编并移除正确的那份。
- **Coffer 自己的 `coffer` MCP 条目**：永不可收编，也不作为普通直连条目列出——它是网关的安装状态，由 Story 8 的安装/卸载管理。
- **对与既有资源等价的条目请求收编**：Coffer 报告匹配（`matches_resource`），并提议移除多余的直连条目，而非创建重复资源。
- **插件已配置但缓存目录缺失**：以 `cache_present=false` 列出，让用户看到漂移；Coffer 不尝试修复（重装——与其他一切插件写操作一样——属于 agent 自己的工具链）。
- **agent 自身进程在 Coffer 读与写之间改写了配置文件**：写入因指纹不匹配被拒绝为过期（409）；用户重新读取后重试。Coffer 每次写入保留的 `.bak` 在相反方向的竞争中保证旧内容可恢复。
- **指令文件包含 spec knowledge 的记忆投影受管块**：编辑器标注该区块由记忆功能管理，让用户知道对它的改动可能被改写。
- **`~/.codex/auth.json` 及其他凭据/状态文件**：永不进入任何 allowlist 或列表；插件与 MCP 解析也绝不读取它们。

## Acceptance Scenarios

按 `agents/sdd.md` 与 `agents/testing.md` 的约定，本节中每一个 scenario 都至少被一个带 `@pytest.mark.acceptance(spec="agent-registry", scenario="…")`（Python）或 `acceptance("agent-registry", "…", …)`（TypeScript）标记的测试引用。

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

- **Given** daemon 正在运行，编辑器正在显示一个受管文件，
- **When** Web 界面请求 daemon 打开一个已存在的绝对路径（可选带首选编辑器）或在文件管理器中显示它，
- **Then** daemon 为该路径启动 OS 应用 / 文件管理器并返回成功；相对路径或不存在的路径被拒绝，且不启动任何进程。

### Scenario: update an existing agent

- **Given** 一个已注册的 agent，
- **When** 用户把它的 `config_dir` 更新到一个新的可写路径，
- **Then** 变更被持久化，写入 audit 条目，后续操作看到新路径。

### Scenario: remove an agent

- **Given** 一个已注册的 agent（任何 binding 清理由 the skill-manager spec 处理），
- **When** 用户移除它，
- **Then** 该 agent 被删除，写入 audit 条目，`coffer agent list` 不再显示它。

### Scenario: desktop app agents page

- **Given** Coffer Web UI 已打开，且至少有一个已注册 agent，
- **When** 用户打开 Agents 页面，
- **Then** 每个已注册 agent 都带有类型、名称与 `config_dir` 出现在列表中。

> Story 4 的 Web UI 表单 add/edit/remove 流程在 e2e 层覆盖；打包的 acceptance 标记见 `e2e/web/specs/shell_agents.spec.ts`。

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
- **When** 用户通过应用内编辑器、REST API 或 `coffer agent` CLI 向该配置文件 key 写入新的、格式良好的内容，
- **Then** Coffer 按文件格式校验内容，原子写入并保留上一版本的 `.bak`，写一条 `agent_config_file_written` audit 条目，下次读取即可读回新内容。

### Scenario: reject malformed config-file content

- **Given** 一个 `settings.json`（`json` 文件）已存在的已注册 agent，
- **When** 用户通过应用内编辑器、REST API 或 `coffer agent` CLI 向该 key 写入畸形内容（如非法 JSON），
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

### Scenario: degrade to read-only when MCP config is unparseable

- **Given** 一个已注册 agent，其承载 MCP 的配置文件包含非法 JSON/TOML，
- **When** 用户列出该 agent 的 MCP 条目，
- **Then** Coffer 报告一个指明文件与解析错误的解析失败状态而非让请求失败，并在该文件恢复可解析之前拒绝对它的条目级写操作。

### Scenario: remove a direct MCP entry

- **Given** 已注册 agent 有一条直连（非 Coffer）MCP 条目，
- **When** 用户删除该条目（`claude_code` 时携带来源文件），
- **Then** 该条目仅从其来源文件中被删除，采用原子写入并保留改动前内容的 `.bak`，记录一条 `agent_mcp_entry_removed` 审计，且下一次列出不再出现它。

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

### Scenario: flag a plugin whose cache is missing

- **Given** 一个 `codex` agent，其 `config.toml` 引用了一个磁盘上没有缓存目录的插件，
- **When** 用户列出该 agent 的插件，
- **Then** 该插件以 `cache_present=false` 列出，且不尝试任何修复。

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

### Scenario: the native memory scan lists an agent's own per-project stores

- **Given** 一个已注册的 `claude_code` agent，其 `<config_dir>/projects/<slug>/memory` 目录含 `.md` 事实文件（外加一个 `MEMORY.md` 索引），
- **When** 用户扫描该 agent 的原生记忆，
- **Then** Coffer 为每个项目返回一个 store，其 `project` 标签与 `path` 为**真实**项目目录（从项目的 session transcript `cwd` 还原，而非有损 slug）、真实的 `memory_dir`，以及排除 `MEMORY.md` 的 `.md` 文件 `item_count`（当某 store 唯一内容是内联 `MEMORY.md` 时为 `1`）——只读，一切在读取时从磁盘派生，且不发出任何 audit 事件。没有原生记忆布局的 agent 类型，或没有 `projects/` 目录的 agent，返回空列表。

### Scenario: the native memory scan lists Codex's global memory by project

- **Given** 一个已注册的 `codex` agent，其 `<config_dir>/memories/MEMORY.md` 含若干 `# Task Group` 块，每块带一行 `applies_to: cwd=…` 把它路由到一个或多个项目工作目录，
- **When** 用户扫描该 agent 的原生记忆，
- **Then** Coffer 把这份全局单文档解析成「每个不同 cwd 一行」——`project`/`path` 为该 cwd，`item_count` 为路由到此 cwd 的 Task Group 数，`memory_dir` 为所有行共享的那个全局 store——只读且不发出任何 audit 事件；没有 `memories/MEMORY.md` 时列表为空。

### Scenario: browse an agent's transcript history with title, search, and sort

- **Given** 一个已注册 agent，其本地会话 transcript 分布在不止一个项目里，
- **When** 列出该 agent 的 transcript 时带上搜索词、项目过滤与排序键（`started_at`、`last_activity_at` 或 `message_count`），
- **Then** 返回的每条会话摘要都携带派生出的标题、消息数、`started_at`、`last_activity_at` 与该会话文件的绝对源路径；只返回标题或项目路径命中搜索、且项目命中过滤的会话，按请求的排序键与方向排序，并以 `limit`/`offset` 分页、连同命中总数一并返回——只读，不发出任何 audit 事件，也不写入任何内容。

### Scenario: list a directory config entry's files

- **Given** 一个已注册 `claude_code` agent，其 `agents/` 目录含 Markdown subagent 文件（可嵌套），
- **When** 用户列出该配置条目，
- **Then** Coffer 返回 `kind=directory` 的条目及其文件（条目相对路径、大小、修改时间）；目录缺失时以 `exists=false`、零文件列出，且读取不创建它。

### Scenario: create a file inside a directory entry

- **Given** 一个带 `agents/` 目录条目的已注册 `claude_code` agent，
- **When** 用户通过应用内编辑器、REST API 或 `coffer agent` CLI 向条目内一个新 `.md` 文件路径写入内容，
- **Then** 文件经原子写入机制创建，写一条 `agent_config_file_written` audit 条目，下次列出包含它。

### Scenario: delete a file inside a directory entry

- **Given** 一个含文件的目录条目，
- **When** 用户通过 REST API 或 `coffer agent` CLI 删除该文件，
- **Then** 文件被移除且其先前内容保留为 `.bak`，写一条 `agent_config_file_deleted` audit 条目，下次列出不再显示它。

### Scenario: reject directory file paths outside the entry

- **Given** 一个带目录配置条目的已注册 agent，
- **When** 用户寻址的子路径包含 `..`、绝对路径或非 `.md` 扩展名，
- **Then** 请求在任何文件系统访问之前被拒绝——越界以 `not_found`（404），不允许的扩展名以 `unprocessable_entity`（422）。

### Scenario: reject stale config-file writes

- **Given** 用户读取了某配置文件（或目录子文件），随后它被另一进程在磁盘上修改，
- **When** 用户携带先前读取的指纹写回内容，
- **Then** 写入以 `conflict`（409）拒绝且磁盘文件不变；重新读取得到允许写入的新指纹。

## Requirements

### Functional Requirements

**Resource 模型**

- **FR-001**: 系统 MUST 将每个已知的本地 agent 注册为 kind 为 `agent` 的 Resource，按 spec mcp-gateway 的 `<kind>:<name>` 约定，标识为 `agent:<name>`。
- **FR-002**: 系统 MUST 用一个 kind 专属 schema 校验 agent 配置，字段包括 `type`（enum）与 `config_dir`（path，可选的绝对路径覆盖；省略时回退到该类型的标准位置——`claude_code` 用 `~/.claude`，`codex` 用 `~/.codex`）。skill 投递到 `<config_dir>/skills`。
- **FR-003**：系统 MUST 支持 `claude_code` 与 `codex` 这两个 agent 类型；注册清单之外的任何类型（例如 `claude_desktop` 聊天应用、某个 Gemini CLI）以 `unprocessable_entity`（422）被拒绝。每类型的行为由能力清单（`AGENT_DESCRIPTORS`）定义，因此新增一个类型 = 一个枚举值 + 一条描述符记录（外加，当该产品的 wire 协议是新的时，一个 chat-provider 适配器）。每个受支持类型都同时覆盖该产品的 CLI 与 app/IDE 形态，二者共享同一个配置目录。

**Agent 能力矩阵（FR-003a）。** 两个受支持类型都支持全部 facet，因此该矩阵记录的是每个产品**如何**实现各 facet，而非它是否存在。agent 界面上不存在逐 facet 的「不支持」状态，wire 上也没有能力布尔量——一个无法支持某 facet 的产品，本身就是不该加进来的产品。

| Agent | 配置目录 | chat provider（spec channels） | Coffer-MCP 注入（FR-019） | provider 投影（spec provider-switching） |
| --- | --- | --- | --- | --- |
| `claude_code` | `~/.claude/` | Claude Agent SDK | `mcpServers` JSON | `apiKeyHelper` |
| `codex` | `~/.codex/` | `codex app-server` | `[mcp_servers]` TOML | `[model_providers]` env_key |

**为什么只有这两个。** registry 一度还携带另外四个产品——`opencode`、`hermes`、`cursor`、`openclaw`。它们已被移除。这四个产品都没有装在维护者自己的机器上，因此每个 facet 都是照着上游文档和一次性探针写出来的，本地永远无法回归验证：每改动一次核心机制，就意味着同时盲改六条代码路径。一个 Coffer 无法真正实操的产品，其承载成本高于它带来的回报。移除它们同时去掉了那四个类型才需要的逐 facet 能力矩阵。重新加回一个产品是一个枚举值加一条描述符记录——等到那个产品真正被使用时再做，而不是提前做。

**发现（检测 = 发现 + 确认）**

- **FR-004**: 系统 MUST 提供一个只读的发现操作，扫描每种受支持 agent 类型的常见安装标记，并把已安装但尚未注册的类型作为**候选项（candidate）**报告（每个携带 `type`、`display_name`、`config_dir`、`default_skill_dir` 与 `suggested_name`）。发现 MUST NOT 自动注册任何内容——由用户审阅候选项并确认要添加哪些。daemon MUST NOT 在启动时自动注册 agent。
- **FR-005**: 只要安装标记仍存在，被移除的 agent MUST 在后续扫描中重新作为发现候选项出现——移除并非永久（可能是误操作）。系统 MUST NOT 保留任何「已抑制类型」列表。

**生命周期**

- **FR-006**: 用户 MUST 能注册、列出、查看、更新（config_dir、description）与移除 agent。agent **没有启用/禁用的概念**——已注册的 agent 就是存在的，agent 层面不存在启用/禁用状态。注册时 agent 名称是可选的——省略时系统 MUST 派生一个稳定的按类型默认名（下划线变连字符，如 `claude_code` → `claude-code`）。
- **FR-007**: 注册时系统 MUST 自动创建 `<config_dir>/skills` 子目录，再验证解析后的 `config_dir` 存在、是目录、可写且不是特权系统路径，方可接受该值。skill 投递到 `<config_dir>/skills`。
- **FR-008**: 系统 MUST 拒绝任何会造成重复 `agent:<name>` 的注册，并 MUST 拒绝为同一个配置目录注册多于一个 agent。`config_dir` 由 agent 类型派生，因此每个受支持类型——也即每个磁盘上的配置目录——至多只能注册一次；第二次尝试以 `conflict`（409）拒绝且不持久化任何内容。

**配置文件**

- **FR-013**：每个受支持 agent 类型 MUST 定义一份精选的配置文件 allowlist（在其能力清单记录中），每个条目携带稳定的 `key`、一个显示名、一个解析后的绝对路径与一个 `format`（`json`、`toml`、`markdown` 或 `text`）。Claude Code → `settings.json`、`settings.local.json`、`~/.claude.json`、`CLAUDE.md`（key 为 `instructions`）与 `agents/` 目录条目（FR-034）；Codex → `config.toml`、`AGENTS.md`（key 为 `instructions`）与 `hooks.json`。Claude Code/Codex 原 `memory` key 改名为 `instructions`——那些文件是人写的指令，区别于 agent 自写的记忆（spec knowledge 的领域）。
- **FR-014**: 用户 MUST 能列出一个 agent 的配置文件，并对每个文件给出其 key、显示名、路径、所在文件夹的绝对路径（`folder_path`）、格式与存在性（文件存在时附带大小与修改时间）。`path`/`folder_path` 这一对支撑 UI 的「在外部编辑器中打开 / 在文件管理器中显示」（FR-038）。
- **FR-015**: 用户 MUST 能读取任一 allowlist 内配置文件的内容。不存在的文件读为空内容、`exists=false`，且读取不会创建它。
- **FR-016**: 系统 MUST 为任一 allowlist 内配置文件的内容暴露一个写入（保存），同时服务于应用内编辑器、REST API 与 `coffer agent` CLI —— 三者共用同一个端点。写入前 MUST 按文件的 `format` 校验内容；畸形的 `json`/`toml` MUST 被拒绝（`unprocessable_entity`，422）且磁盘文件保持不变。`markdown`/`text` 文件接受任意内容。
- **FR-017**: 写入 MUST 是原子的（临时文件 + rename），并 MUST 保留上一版本内容的 `.bak` 副本，使错误编辑可恢复；每次成功写入 MUST 写一条 `agent_config_file_written` audit 条目。Coffer-MCP 安装/卸载操作（FR-022）复用同一套原子写入 + `.bak` 机制。
- **FR-018**: 配置文件的读取与写入 MUST 只能通过 allowlist 内的 `key` 寻址（绝不接受调用方提供的路径）；未知 key 返回 `not_found`（404）且不做任何文件系统访问。

**Coffer MCP 安装**

- **FR-019**: 用户 MUST 能一键把 Coffer 自己的 MCP server 安装到某个 agent。安装把一个 `coffer` stdio MCP-server 条目写进 agent 的 MCP 配置，按该 agent 清单中 `McpInjectionSpec` 声明的形态——`claude_code` 写 `~/.claude.json` 的 `mcpServers`；`codex` 写 `~/.codex/config.toml` 的 `[mcp_servers.coffer]`。`command` 设为 `coffer-mcp-shim` 二进制的绝对路径（先在 `PATH` 中解析，再查找当前解释器的脚本目录——这样即使守护进程的 `PATH` 不含 venv，也能找到装在 venv 里的 shim——最后回退到打包的二进制；环境变量 `COFFER_MCP_SHIM_PATH` 优先于以上全部）。安装还会把 `--agent <name>`（该 agent 的注册名）作为 shim 调用的参数写入——写在条目形态对应的参数位置（command-map 条目写 `args`，typed-array 条目追加到 `command` 数组）——使 gateway 能把会话归属到该 agent，用于按 agent 的 scope 把关（[Per-Agent Resource Scope](../../docs/decisions/per-agent-resource-scope.zh.md)）。若无法解析 shim，安装被拒绝且不写入任何内容。
- **FR-020**: 安装 MUST 幂等——重复安装就地更新已有的 `coffer` 条目，绝不产生重复。系统 MUST 暴露一个状态操作，报告该 agent 当前是否已安装 Coffer 的 MCP。
- **FR-021**: 用户 MUST 能卸载 Coffer 的 MCP，从 agent 的 MCP 配置中移除 `coffer` 条目。未安装时卸载为空操作（no-op）成功。
- **FR-022**: 安装与卸载 MUST 复用 FR-017 的原子写入 + `.bak` 机制，并写一条 audit 条目（`agent_mcp_installed` / `agent_mcp_uninstalled`）。

**Agent MCP 条目（工作区增补）**

- **FR-025**: 系统 MUST 解析并列出 agent 自己文件中配置的 MCP server 条目——`claude_code` 从 `~/.claude.json` 的 `mcpServers` 与 `settings.json` 的 `mcpServers` 双源解析（每条标注来源文件）；`codex` 从 `config.toml` 的 `[mcp_servers.*]` 解析。每条目携带名称、来源、传输方式（stdio 命令或 HTTP URL）、格式定义了的 `enabled` 标志（Codex）、标记 Coffer 自身网关条目的 `is_coffer`，以及在存在等价已注册 `mcp_server` 资源时给出其名称的 `matches_resource`。条目在读取时派生，绝不存储。
- **FR-026**: 用户 MUST 能删除一条直连 MCP 条目。删除只改动该条目的来源文件（`claude_code` 在两个文件同名时由调用方消歧），复用 FR-017 的原子写入 + `.bak` 机制，并记录一条 `agent_mcp_entry_removed` 审计。`coffer` 条目不能经此操作删除——它由 FR-019/FR-021 管理。
- **FR-028**: 用户 MUST 能把直连 MCP 条目收编进 Coffer。收编 (a) 经标准资源流程（schema 校验 + 审计）把条目注册为 `mcp_server` 资源，(b) 验证资源可读回，再 (c) 按 FR-026 移除来源条目——严格按此顺序。任何失败都中止操作、回滚已创建的资源、保持 agent 配置逐字节不变；成功时审计为 `agent_mcp_entry_adopted`。与既有资源的名称冲突以 `conflict`（409）拒绝并附建议替代名；与既有资源等价的条目经 `matches_resource` 报告，让用户改为移除重复条目。`coffer` 条目永不可收编。
- **FR-029**: 收编 MUST NOT 把密钥值持久化进资源配置。当条目的环境变量在疑似密钥的 key（`TOKEN`、`KEY`、`SECRET`、`PASSWORD` 等模式）下携带值时，收编请求 MUST 为每个被标记的 key 提供 keychain 映射，否则以列出未解决 key 的响应拒绝。映射的值经 daemon 存入 OS keychain（遵循凭据不变量）；资源配置只携带引用。
- **FR-030**: 当某个 agent 配置文件无法解析时，受影响的 facet MUST 降级为明确的解析错误状态（文件路径 + 解析器报错）而不拖垮整个视图，且在该文件恢复可解析之前 MUST 拒绝对它的条目级写操作。

**不再提供：切换 Codex 条目的 `enabled` 开关。** Coffer 一度在列表旁提供逐条目的启用切换。它已被删除。对 `claude_code` 而言那从来只会返回 422——该格式根本没有逐条目开关；对 `codex` 而言，它重复了 agent 自己界面本就拥有的一个开关，代价是就地亲手改写另一个工具的私有配置格式。删除（FR-026）与收编（FR-028）留了下来，因为它们是只有 Coffer 才有理由做的写入：把一个 server 从 agent 的私有配置里拿掉，以及把它连同密钥一起映射进 vault 收编进 hub。两者都自始至终拥有自己的那次写入，任何环节失败都会回滚。

**插件（工作区增补）**

- **FR-031**: 系统 MUST 列出 agent 的已安装插件、各自的启用状态，以及它来自哪个 marketplace（作为列表的一列，而不是把列表按 marketplace 分组）。列表本身什么都不写——既不写文档化配置面，也不写任何内部状态文件；写操作是 FR-032 与 FR-033。`codex` 的列表从 `config.toml`（`[plugins."<name>@<marketplace>"]`、`[marketplaces.*]`）加上文档化缓存目录 `~/.codex/plugins/cache/<marketplace>/<plugin>/` 的存在性派生；`claude_code` 的清单从 `~/.claude/plugins/installed_plugins.json` 与 `known_marketplaces.json` 派生，启用状态来自 `settings.json` 的 `enabledPlugins`。已配置但缓存缺失的插件标记 `cache_present=false`；不尝试修复。
- **FR-032**: 用户 MUST 能启用/禁用插件。写操作只触碰文档化位置——Codex 条目的 `enabled` 字段；Claude Code `settings.json` 的 `enabledPlugins` 映射——且 MUST 绝不写 agent 的内部状态文件。审计为 `agent_plugin_toggled`。
- **FR-033**: 用户 MUST 能卸载插件，按每个 agent 的策略分派。`codex`：从 `config.toml` 移除 `[plugins."…"]` 条目并删除该插件的缓存目录。`claude_code`：Coffer 委派给 `claude plugin uninstall <id>`——绝不亲手写 Claude 的内部 `installed_plugins.json`，由该 CLI 拥有这部分状态。当 `claude` CLI 不在 PATH 上时，操作以 `unprocessable_entity`（422）/ `PLUGIN_UNINSTALL_UNSUPPORTED` 拒绝，且应用内卸载入口被隐藏（列表上报 `can_uninstall=false`）；CLI 报错则以 `PLUGIN_UNINSTALL_FAILED`（422）呈现。两条成功路径都审计为 `agent_plugin_uninstalled`。Coffer 不提供插件安装与 marketplace 管理；二者都留给 agent 自己的工具链。

**目录型配置条目（工作区增补）**

- **FR-034**: 配置文件 allowlist 条目 MAY 是**目录条目**（`kind=directory`）：解析到一个目录并列出其文件（条目相对路径、大小、修改时间），而非携带内容。Claude Code 的目录条目是 `agents/`（每个个人 subagent 一个 Markdown 文件，允许嵌套路径）。目录缺失时以 `exists=false`、零文件列出；读取绝不创建它。
- **FR-035**: 用户 MUST 能读取目录条目内的单个文件；该读取支撑 UI 的编辑器。单个文件的写入（写即创建）与删除通过应用内编辑器、REST API 与 `coffer agent` CLI 提供。子路径在任何文件系统访问之前于服务端校验：MUST 解析在条目目录之内（无 `..`、无绝对路径、无 symlink 逃逸）且带 `.md` 扩展名。写入复用 FR-017 机制；删除把先前内容保留为 `.bak`。审计为 `agent_config_file_written` / `agent_config_file_deleted`。
- **FR-036**: 配置文件读取（单文件与目录子文件）MUST 返回内容指纹；写入 MUST 带回该指纹，且当磁盘内容自读取后已变化时以 `conflict`（409）拒绝、文件保持不变。
- **FR-037**: 当指令文件包含由另一个功能定义的受管块——spec knowledge 的记忆投影块——时，编辑器 MUST 标注该区块由那个功能拥有。每个块使用其各自独有的标记并被独立改写；标记格式由定义它的功能拥有。

**agent 自己的原生记忆（工作区增补）**

本需求把 registry 延伸到 coding agent 自己的原生逐项目记忆——区别于 FR-013 的 `instructions` 配置文件（CLAUDE.md / AGENTS.md 是人写的指令；这里是 agent 自写的记忆 store）。Coffer 对它永远**只读**。这次扫描与它旁边的 MCP 条目列表、插件列表一样，是一份列表；它存在的理由是：让用户能从 agent 页面上看到那个 agent 一直在记些什么，并在磁盘上打开它。

- **FR-040**: 系统 MUST 暴露一个只读的**原生记忆扫描**，列出某 agent 类型自己的原生记忆 store。支持两种布局。`claude_code` 为逐项目布局，store 位于 `<config_dir>/projects/<slug>/memory/`：每个含 `memory/` 目录的项目一行，`item_count` 为排除 `MEMORY.md` 的 `.md` 事实文件数——当无事实文件但 `MEMORY.md` 含内联内容（较旧/手写的 hub 文档）时为 `1`。`project` 标签与 `path` 为**真实**项目目录，从该项目的 session transcript `cwd` 还原（slug 编码有损——`/`、`.`、`_` 全部坍缩成 `-`——无法可靠从 slug 重建路径；有损 slug 解码仅作最后兜底）。`codex` 为单一**全局** task-grouped 文档，位于 `<config_dir>/memories/MEMORY.md`，其中每个 `# Task Group` 块带一行 `applies_to: cwd=…` 把它路由到一个或多个项目工作目录；扫描把它解析成「每个不同 cwd 一行」，`item_count` 为路由到此 cwd 的 Task Group 数、`path` 为该 cwd（`memory_dir` 为所有行共享的那个全局 store）。没有原生记忆布局的 agent 类型、没有 `projects/` 目录、或没有 `memories/MEMORY.md`，都返回空列表。扫描是只读的，一切在读取时从磁盘派生（不存储），并——遵循 FR-011 的「工作区列表只读，均不发出 audit 事件」——不发出任何 audit 事件。它绝不写入 agent 的 store。

**不再提供：把原生记忆 store 导入 Coffer。** FR-041 一度读取某个 store 的事实，把它们写进对应 Coffer 项目记忆的 `knowledge/inbox/` 通道，再交给一个 organizer。它没有被恢复，相应的机制也随之删除。知识层如今是一个由用户与 agent 有意写下的 markdown 文件目录（[Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.zh.md)）；把另一个工具的 store 批量拷进去，只会产出没人选择留下、却还得回头去整理的材料。读取这个 store、并在它所在的位置打开它，就是这个 facet 的全部。

**agent 自己的会话历史（工作区增补）**

agent 会把每次会话的 transcript 写进它自己的配置目录——Claude Code 的 `<config_dir>/projects/**/*.jsonl`，Codex 的 `<config_dir>/sessions/**/*.jsonl`。registry 把它们列出来，好让用户能从 agent 页面找到过去的某次会话，并在它所在的位置打开。这只是一个浏览面，仅此而已：Coffer 解析这些文件以派生出摘要，绝不写入它们、绝不存储它们的内容，也绝不把它们发往任何地方。

- **FR-047**: 系统 MUST 暴露一份只读的、agent 本地会话 transcript 的列表。每条会话摘要携带其 `session_id`、派生出的 `title`（该会话的第一个用户回合，已做密钥擦洗）、`project_path`、`message_count`、`started_at`、`last_activity_at`，以及该 transcript 文件的绝对 `source_path`——最后这项支撑 FR-038 的打开 / 显示操作。该列表 MUST 支持对标题与项目路径的大小写不敏感子串搜索、按 `project` 的精确过滤、按 `started_at` / `last_activity_at`（默认）/ `message_count` 双向排序，以及 `limit`/`offset` 分页并附命中的 `total`——因为一个 agent 会累积成千上万次会话，这个界面不可能一次全部加载。解析逐文件进行并按修改时间缓存；解析失败的文件被跳过，而不是让整份列表失败。消息正文不随响应传输，也不驻留在内存里。该列表一切在读取时从磁盘派生、不存储任何东西，并且——与其它工作区列表一样（FR-011）——不发出任何 audit 事件。

**不再提供：把 transcript 蒸馏进记忆。** Coffer 一度读取同一批文件，把持久的事实蒸馏进知识层的 journal 通道。那条路径、它的账本、它的后台扫描以及它写入的那个通道都已删除（见 spec knowledge）；本列表不会把它们复活。留下来的是那一半不需要模型、也不可能损坏任何东西的部分：把有哪些会话展示给用户，并打开其中一次。

**不再提供：生命周期 hook 与会话上下文注入（已删除）**

三条需求一并删除。FR-043 把一条 `coffer-hook` 命令条目安装进 agent 的 hooks 文件（`claude_code` 为 `settings.json`，`codex` 为 `hooks.json`），并可卸载与查询状态。FR-044 经 `GET /agents/{name}/session-context` 向该 hook 提供一份**规则 bundle**——会话的 project 与 global 规则外加两条内置种子规则——供 agent 在 SessionStart 时作为附加上下文注入。FR-046 暴露 `disable_native_memory`，把 agent 自身的写侧记忆与该持久化字段同步关闭（Claude Code 的 `autoMemoryEnabled`，Codex 的 `features.memories`）。随之删除的还有 `coffer-hook` 二进制、它的 PyInstaller target 与 console script、`hook-install` 与 `session-context` 路由、`surfaces/hook/` 入口与 hook 的 service / resolver / install 领域代码、`coffer agent hook …`、能力清单的 `ContextInjectionSpec` facet、`disable_native_memory` 配置字段，以及四个 audit 事件 `agent_hook_installed` / `agent_hook_uninstalled` / `agent_native_memory_disabled` / `agent_native_memory_restored`。SessionStart hook 与规则 bundle 注入那条决策记录也一并删除。

理由与原生记忆相同：它上线了，但从没被安装过。`~/.claude/settings.json` 里只有第三方 hook，构建出来的 `coffer-hook` 二进制躺在 `~/.coffer/bin/` 里，没有任何东西引用它。

**这么做付出了什么，直说。** 这删掉的是跨 agent 记忆的**投递**那一半。知识仍然进得来——`coffer__remember`、organizer、知识库——但再也没有任何东西把它推进一次会话了。想要历史上下文的 agent 必须自己调用 `coffer__recall`（或 `coffer__resume`）；从不调用的 agent，则每次会话都从零开始。这是一项真实的损失，且是被有意接受、而非被忽略的：一条在维护者机器上从未被任何 agent 安装的注入路径，本来就没在投递任何东西；而投递机制值得重建的前提，是先有一个真正装上去的 hook。

**界面**

- **FR-009**: 每一个管理操作——注册/列出/查看/更新/移除、配置文件列出/读取/写入（含目录子文件）、Coffer-MCP 安装/卸载/状态、MCP 条目列出/收编、插件列出/切换/卸载、原生记忆扫描（FR-040）、transcript 列表（FR-047）——MUST 同时通过 (a) REST API 与 (b) `coffer agent ...` CLI 提供。Web UI 的 Agents 页面 MUST 暴露以上全部，**除配置文件内容写入之外**（单文件与目录子文件）：在 UI 中，配置文件与目录子文件是**只读**的，带「在外部编辑器中打开 / 在文件管理器中显示」操作（FR-038），而 REST API 与 CLI 保留程序化的写入/创建/删除路径。agent 详情页有七个 tab——概览、Skill、MCP 服务器、插件、记忆、对话记录与配置文件。其中只有插件 tab 会对 agent 本身产生写操作（启用 / 禁用 / 卸载）；记忆与对话记录是 agent 自有 store 的只读视图，每一行都提供「在外部编辑器中打开 / 在文件管理器中显示」。
- **FR-010**: CLI MUST 在每个读取类操作上支持 `--json` 以提供机器可读输出。
- **FR-038**: 对每个配置文件（及每个目录条目子文件），UI MUST 提供针对该文件的**在外部编辑器中打开**与**在文件管理器中显示**操作，使用 FR-014/FR-015 的 `path`。打开与显示通过 daemon 的文件系统动作端点（FR-039）执行真实的 OS 动作——因为环回 daemon 始终在用户自己的机器上（ADR: daemon-proxies-os-file-actions）。没有 copy-path 回退。用于「在外部编辑器中打开」的编辑器引用 spec ui-shell 定义的用户「首选外部编辑器」偏好（此处不再重新规定）。

**可观测性**

- **FR-011**: 系统 MUST 为每一个生命周期事件写入一条 audit 条目：agent 创建、更新、移除；配置文件写入/删除（`agent_config_file_written` / `agent_config_file_deleted`）；Coffer MCP 安装/卸载；MCP 条目收编（`agent_mcp_entry_adopted`）；插件切换/卸载（`agent_plugin_toggled` / `agent_plugin_uninstalled`）。（agent 没有启用/禁用的概念；发现与全部工作区列表——MCP 条目、插件、配置文件、原生记忆 store、transcript 会话——都是只读的，均不发出任何 audit 事件。）
- **FR-012**: 系统 MUST 暴露一个只读的发现操作，把已安装但未注册的 agent 列为候选项，可通过 REST API（`GET /api/v1/agents/candidates`）、`coffer agent detect` CLI 与 Web UI 的 Agents 页面访问。

**配置目录选择器**

- **FR-023**: 选择自定义 `config_dir` 时，Web UI MUST 提供一个文件夹选择器，而非要求用户手动输入路径。它 MUST 使用 daemon 原生目录对话框（FR-042），仅当宿主没有原生对话框工具时才退回 daemon 支撑的文件夹浏览器（FR-024）。两者都产出一个绝对路径，随后在注册前按 FR-007 校验。
- **FR-024**: 系统 MUST 暴露一个只读的文件系统浏览操作（`GET /api/v1/fs/browse`），给定一个目录路径（默认用户主目录），返回该路径、其父目录与其直接子目录。它 MUST NOT 返回文件内容，且 MUST 与所有其它 daemon 路由一样受同样的 loopback + token 鉴权保护。
- **FR-042**: 系统 MUST 通过环回 daemon 暴露**唯一**一个原生 OS 对话框——**文件夹**选择器 `POST /api/v1/fs/pick-folder`——让 Web 界面打开宿主真实的目录选择框，而非要求手输路径。它打开宿主原生对话框（macOS 用 `osascript`；Linux 用 `zenity`/`kdialog`），以固定参数向量调用（无 shell 插值），返回 `{ available, path }`：宿主无原生对话框工具时 `available=false`；用户取消时 `available=true` 且 `path=null`；否则为所选绝对路径。当 `available=false` 时调用方降级为应用内浏览器（FR-024）。它不创建任何东西，且与每条 daemon 路由一样受同样的 loopback + token 鉴权保护。

**不再提供：原生的选文件与存文件对话框。** `POST /api/v1/fs/pick-file` 与 `POST /api/v1/fs/save-file` 已删除，「由 daemon 代理原生开/存文件对话框」那条决策也一并删除。浏览器本身就有这两种机制：`<a download>` 存文件，`<input type="file">` 选文件——而后者严格优于原生对话框，因为它直接把文件的**内容**交给 Web 界面，而不是交一个还要 daemon 再去读一遍的路径。文件夹是那个例外，也正是 FR-042 得以留存的原因：浏览器刻意不给出绝对路径，而注册一个 agent 恰恰需要它。这次删除同时收窄了 daemon 的攻击面——就这两个操作而言，它不再 shell 出 `osascript` / `zenity`，其环回接口少执行了一类本机程序。

**文件系统打开/显示**

- **FR-039**: 系统 MUST 暴露文件系统动作操作,让 Web 界面经环回 daemon 执行真正的 open/reveal（FR-038）——daemon 始终与 Web 客户端同处用户机器上（ADR: daemon-proxies-os-file-actions）:`POST /api/v1/fs/open`(在某个应用里打开一个已存在的绝对路径——一个 `with` 编辑器偏好,或 OS 默认)与 `POST /api/v1/fs/reveal`(在 OS 文件管理器中选中/显示一个已存在的绝对路径)。两者在动作前都 MUST 校验路径为绝对且存在,MUST 以固定参数向量调用 OS 启动器(无 shell 插值),MUST 不创建任何东西,且 MUST 与所有其它 daemon 路由一样受同样的 loopback + token 鉴权保护。非绝对或不存在的路径被拒绝(`FS_PATH_NOT_OPENABLE`,400)。在没有可移植「选中文件」原语的平台(Linux),reveal 降级为打开所在文件夹。系统还 MUST 暴露 `GET /api/v1/fs/editors`,枚举主机上检测到已安装的常见 GUI 编辑器(macOS 返回 `open -a` 用的 app 名;Linux/Windows 返回 PATH 上的命令),以便 spec ui-shell 的首选编辑器设置提供一个选择框而非盲填文本框。它返回每个编辑器的显示标签与 `/fs/open` 的 `with` 所接受的启动 `value`,除应用是否存在外不读取任何内容,并受同样的 loopback + token 鉴权保护。

### Key Entities

- **Agent**：一个 kind 为 `agent` 的 Resource。代表一份本地安装的 AI agent。Config: `type`（受支持的 enum）、`config_dir`（可选的绝对路径覆盖；默认回退到该类型的标准位置）。skill 投递到 `<config_dir>/skills`。标识为 `agent:<name>`。`agent` kind 不声明 `scope`：非 null 值在校验阶段被拒绝（422）——agent resource 正是其他 kind 的 scope 所指向的对象，而它自己绝不是某个 scope 的目标（[Per-Agent Resource Scope](../../docs/decisions/per-agent-resource-scope.zh.md)）。
- **Agent Type**：一个 enum 值，标识一个已知 agent 产品（`claude_code`、`codex`）。每个值映射到**能力清单**（`AGENT_DESCRIPTORS`）中的一条记录，携带其默认 `config_dir`、显示名、用于发现的安装标记、精选的**配置文件 allowlist**、**MCP 注入形态**，以及其 provider 投影 facet。两个受支持产品都携带全部 facet；一个做不到的产品，本身就不值得加入（FR-003a）。
- **Agent Candidate（候选项）**：一个被发现的、已安装但尚未注册的 agent——`type`、`display_name`、`config_dir`（该类型的默认配置目录）、`default_skill_dir` 与 `suggested_name`。在扫描时派生，从不存储；用户确认某个候选项即可注册它。
- **Config File（配置文件）**：属于某个 agent 类型、在 allowlist 内的精选文件，以稳定的 `key` 标识。携带显示名、解析后的绝对路径、其所在文件夹的绝对路径（`folder_path`）、`format`（`json` / `toml` / `markdown` / `text`），以及（存在时）大小与修改时间。在 UI 中呈现，可读可编辑（也可在外部编辑器中打开该文件 / 其文件夹）；按 key 读取与写入（应用内编辑器、REST、CLI），绝不按任意路径。不持久化到 SQLite——磁盘上的文件即为事实来源。
- **Coffer MCP Install Status（安装状态）**：某个 agent 的派生（非存储）状态：其 MCP 配置文件中是否存在 `coffer` MCP-server 条目。
- **Agent MCP Entry（agent MCP 条目）**：agent 自己文件中所配置的一个 MCP server 的派生（绝不存储）视图——名称、来源文件、传输方式、`enabled`（Codex）、`is_coffer`、`matches_resource`。文件是事实来源；Coffer 读取与收编条目但不保留副本，且只在收编的移除步骤中才编辑条目。
- **Agent Plugin（agent 插件）**：一个已安装插件的派生（绝不存储）视图——id（`<name>@<marketplace>`）、marketplace、启用状态、`cache_present`，外加从插件安装目录尽力读取的清单信息。所有输入都是只读的：Coffer 上报的启用状态就是各 agent 文档化配置面所声明的那个，Coffer 绝不把它写回去。
- **Native Memory Store（原生记忆 store）**：coding agent 自己的某个原生记忆 store 的派生（绝不存储）视图——`claude_code` 为逐项目目录（`<config_dir>/projects/<slug>/memory`），`codex` 为单一全局 task-grouped `<config_dir>/memories/MEMORY.md` 的某个路由 cwd 切片。携带 `project` 标签与 `path`（**真实**项目 cwd）、真实的 `memory_dir`，以及 `item_count`。只读：Coffer 列出这些 store 并打开它们，绝不写入它们。
- **Transcript Session（transcript 会话）**：agent 自己某个会话 transcript 文件的派生（绝不存储）摘要——`session_id`、经擦洗派生出的 `title`、`project_path`、`message_count`、`started_at`、`last_activity_at`，以及该文件的绝对 `source_path`。在读取时从磁盘上的 `.jsonl` 解析，并按修改时间缓存；消息正文既不返回也不驻留。
- **Directory Config Entry（目录型配置条目）**：解析到一个文件目录而非单个文件的 allowlist 配置条目。子文件以校验过的条目相对路径寻址；磁盘上的目录是事实来源。

## Success Criteria

### Measurable Outcomes

- **SC-001**：在一台至少存在两种受支持 agent 安装路径的机器上，运行发现恰好把这些 agent 作为候选项呈现，用户对每个只需一次确认即可添加——无需手动输入类型标识或路径。
- **SC-002**：从一份全新安装开始，用户能在 60 秒内用自定义 `config_dir` 注册一个额外 agent，并在 `coffer agent list --json` 中看到它，期间最多查阅一次文档。
- **SC-003**：本 spec 中每一个 Acceptance Scenario 至少被一个带 `acceptance(spec="agent-registry", scenario="…")` 标记的测试覆盖；`make verify-acceptance` 报告零未覆盖 scenario。
- **SC-004**：完整 `make verify` 套件在本地与 CI 中通过；`make verify-all`（额外包含 e2e）在 macOS 与 Linux 上通过。
- **SC-005**：任何 `config_dir` 值都不允许写到该目录之外（path-traversal 检查），由一个专门的安全测试验证。
- **SC-006**：用户能在 Coffer 中打开 agent 的 `settings.json`（Claude Code）或 `config.toml`（Codex）并编辑保存，也可以改在外部编辑器中打开它；每一次保存都会校验内容（畸形的保存会被拒绝且文件保持不变）、保留上一版本的 `.bak`，并在文件自读取以来已在磁盘上变动时拒绝写入。
- **SC-007**：用户能一键把 Coffer 的 MCP 安装到一个新注册的 agent，重启该 agent 后它能列出 Coffer 聚合的工具；重复安装绝不产生重复条目，卸载将其移除。
- **SC-008**：MCP tab 恰好列出 agent 真实配置文件中存在的条目；收编一条直连条目即完成完整回路——资源已注册、网关在服务它、直连条目已消失——只需一次用户操作加至多一次确认。
- **SC-009**：插件列表什么都不写：一次列出前后，agent 配置目录下的每个文件——包括 agent 的内部插件状态文件——逐字节一致。
- **SC-010**：任何目录条目操作都无法读写其条目目录之外的路径；由覆盖 `..` 穿越、绝对路径、symlink 逃逸与不允许扩展名的专门安全测试验证。

## Assumptions

- 用户在自己的机器上运行 Coffer；不存在多租户或远程访问需求。
- 两种 agent 类型已在能力清单（`AGENT_DESCRIPTORS`）中接线——`claude_code` 与 `codex`——每种都是一个 `AgentType` 枚举值加一条记录（安装标记、配置文件 allowlist、MCP 注入形态，以及它的各 facet）。再增加一个产品也是同样的一条记录变更，外加当其 wire 协议是新的时一个 chat-provider 适配器；一个 Coffer 无法在真实安装上实操其 facet 的产品不会被加入（FR-003a）。
- 每个受支持 agent 的 CLI 与 app/IDE 形态读取同一个共享配置目录（`~/.claude/` 与 `~/.codex/`），因此 Coffer 对每个 agent 管理一份配置集合。
- 配置文件以原始文本呈现，用户可就地读取与编辑；无论从哪个界面保存，都带校验 + 原子写入 + `.bak` 兜底。「在外部编辑器中打开」作为长尾需求的兜底入口保留在旁；反复出现的结构化需求按工作区增补「毕业」为 facet（MCP 条目、插件）。凭据/状态文件 `~/.codex/auth.json` 被有意排除在 allowlist 之外。
- agent 的内部状态文件（`~/.claude.json` 中 `mcpServers` 映射之外的部分、`~/.claude/plugins/*.json`、Codex 的 `[marketplaces.*]` / `[hooks.state.*]` / `[projects.*]` 表）在需要时作为输入读取，工作区 facet 绝不写入它们；唯一的写目标是按各厂商文档核实过的文档化配置面。实际情况（已在真实机器上验证）：Claude Code 的 user 级 MCP server 存在于 `~/.claude.json` 的 `mcpServers`，也可能出现在 `settings.json` 的 `mcpServers`——两处都解析。
- 工作区 facet 遵循收编 → 主库 → 投递原则：在 agent 工作区发现的可共享内容收编进 Coffer 的中枢（此处是 MCP 网关；skill 主库经由 spec skill-manager 的配套增补），而非作为各 agent 的一次性配置来管理。中枢本身的跨机器共享属于未来 spec（需修宪）；这些 facet 的设计保证其状态在那一天到来时可直接序列化为声明式清单。
- agent 把自己的 skill 库存放在本地文件系统的 `<config_dir>/skills` 之下。仅 Web 形态的 agent（例如 claude.ai）超出 v1 范围，需要后续 spec 通过 API 同步加入。
- 由 spec mcp-gateway 定义的 kind-agnostic Resource 框架、audit 日志与 `<kind>:<name>` 标识方案已就绪。
- 来自 spec ui-shell 的应用外壳——侧栏 IA、布局、路由骨架与设计系统——已就绪。Agents 页面渲染在该外壳内的 `/agents`，作为一个**独立的顶级导航项**（与 Resources、System 分组平级，**不**嵌套在 Resources 之下——agent 是 vault 资产的消费者，而非资产本身）。agent 资源不出现在 kind-agnostic 的资源/MCP 浏览页中，该页只列出注册了资源卡片 UI 的 kind。
- Skill bindings（agent 与某个 skill 之间的关系）由 spec skill-manager 引入和管理；spec agent-registry 不定义 skill 操作，只暴露一个用于级联清理的 `on_delete` 钩子。
