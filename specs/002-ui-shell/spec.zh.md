# 功能规格：UI Shell 与视觉语言

> English: [spec.md](./spec.md)

**Feature Branch**: `feature/002-mcp-gateway-web` (PR #23，建立在 `feature/mcp-gateway` 之上)
**Status**: Draft
**Input**: 001-mcp-gateway 的 UI 以功能骨架的形式交付：裸 tailwind 默认值、ad-hoc 间距、没有首次使用引导。本 spec 把这个骨架升级为一个真正的产品壳——一套连贯的视觉语言、一个建立在单一统一概念（每一种被管理的实体都是一种 _resource kind_）之上的信息架构，以及让首次访客（而不是绕过鉴权的 Playwright fixture）就能用上 gateway 的端到端流程。

**Scope note**: Coffer 的 spec 按后端/前端切分。`001-mcp-gateway` 拥有 daemon、MCP gateway、REST API 与 CLI。**本 spec 拥有每一个面向用户的界面**——web UI、Tauri 桌面壳、视觉语言、信息架构、国际化。用户能看到或点到的任何东西都在这里规定。**这是一份在 001 之上的纯 UI 重设计**：不新增任何后端，所以数据模型仍住在 `specs/001-mcp-gateway/data-model.md`，本目录不另设 `tasks.md` 追踪。配套文档见 [`plan.md`](./plan.md) 与 [`quickstart.md`](./quickstart.md)。

## Information Architecture

Coffer 管理的东西只有一种：**resource**——一个有名字、有配置、有生命周期的被管理实体。`mcp_server` 是今天交付的 resource kind；`skill`、`knowledge_base`、`memory`、`channel`、`agent` 都是规划中的。没有"二等公民"的 surface 概念：

- **channel** (Seatalk、Slack) 是一种 resource——一份已注册、已配置、有自己生命周期的集成。
- **agent** 也是 resource，并且是双重身份的：agent 既 _消费_ 能力（它是一个 gateway 客户端），又能 _被暴露_ 为可被其它 agent 调用的能力（sub-agent / agent-as-tool）。从 gateway 视角看，被暴露的 agent 与上游 MCP 服务器没有区别，都是能力提供方。这种双重性是 agent resource 自身的属性——在它自己的详情页呈现——而不是拆分导航的理由。

**侧栏只展示 Coffer 当下能做什么。** 规划中的 kind 不以"尚未实现"占位项的形式列出来：一个三分之二都写着"敬请期待"的侧栏读起来是未完成的脚手架，不是产品。每一种 kind——以及规划中的内建 **Chat** surface——会在它各自的 feature spec 上线时自己加进导航。上面的 resource 模型是让这些新增很便宜的设计意图；在这里它是文档，不是渲染出来的 UI。

当下的侧栏是：

```
 RESOURCES
  MCP servers      operational
 SYSTEM
  Observability    the audit log
  Settings
```

它从一开始就分组——**Resources**（resource kind）与 **System**（横切工具）——这样未来的一种 kind 落进 Resources 组就行，不必重新设计导航。当内建 agent 上线时，会在两个分组之上挂一个置顶的 **Chat** 入口。规划中的 kind（skill、knowledge base、memory、channel、agent）与 Chat surface 都已记录好以备再次引入，但刻意不提前于它们各自的 feature 上线。

侧栏可折叠到只剩图标的轨道再展开；选择跨会话持久化（localStorage）。

详见 [`ADR-008：一切皆 resource kind`](../../docs/decisions/ADR-008-everything-is-a-resource-kind.md)，记录了这种单轴 IA 背后的架构决策（被拒绝的备选：独立的"surface"概念；侧栏策略：不放"敬请期待"占位项）。

## User Scenarios & Testing

### User Story 1 — 首次访客落入一个可用的 app (Priority: P1)

某位开发者第一次打开 web UI（或 Tauri 桌面窗口）。他从未注册过服务器。页面立刻出内容——没有"unexpected error"卡片，没有空白页加不知道下一步做什么。他看到一个欢迎视图，介绍 Coffer 是什么，并给出一个明确的下一步："添加你的第一台 MCP 服务器。"

**Why this priority**: 这是通往其它一切流程的门。如果第一屏看起来坏了或对下一步沉默，用户关掉标签页，产品其它部分都没机会出现。

**Independent Test**: 清掉 `localStorage`，`make dev` 之后打开 `http://localhost:5173/`。页面通过 dev 专用的 token 注入插件 (`frontend/vite.config.ts`) 自动鉴权；用户落到 `/resources`，看到一张欢迎卡片，主行动是 "Add MCP server"。

**Representative scenarios** (完整 Given/When/Then 见 `## Acceptance Scenarios`):

- cold-start renders authenticated content
- token-missing renders an actionable empty state (not generic error)
- empty resources list renders a welcome view

---

### User Story 2 — 日常 MCP 操作有产品质感，不再像脚手架 (Priority: P1)

已经在用 Coffer 做 MCP gateway 聚合的开发者希望日常流程——注册服务器、看健康、浏览工具、切换能力、看 invocation——看起来、用起来像一个真正的产品，而不是一坨脚手架。标题在字体上有区分；间距统一；每台服务器页面在 per-tool 开关之前先有一个"这台服务器在干嘛"的总览视图；空 / 错 / 加载态都是一等公民。服务器列表带搜索框、状态过滤、客户端分页，让一个大 vault 也能浏览。

"Add MCP server" 是一个对话框，用户把标准的 `mcpServers` JSON 块粘进去（一次一台或多台都行）——就是每台 MCP server README 给的那块。Review 一步让他们确认哪些 `env` 是 secret；这些值会被提到 OS keychain，而不是写在 config 里。

**Why this priority**: spec 001 把后端正确性交付了，但 UI 是裸 tailwind 默认值。"MCP gateway 完成了"的用户可见标杆是：UI 能在真人手里走通（不是只能在 Playwright fixture 里跑）。

**Independent Test**: 在真实浏览器里把 MCP 流程走一遍：开 `/resources`（欢迎或列表），点 "Add MCP server"，填表，提交，落到详情页，依次切 Overview / Tools / Resources / Prompts / Invocations tabs，切换一个工具，回到列表，把语言在英文与 中文 之间切换。每一步都呈现打磨过的内容；没有任何视图死在一个 generic error。

**Representative scenarios** (完整 Given/When/Then 见 `## Acceptance Scenarios`):

- MCP server registration round-trip via JSON import
- capability toggle uses the redesigned tab layout
- invocations table renders the redesigned empty + populated states
- language switcher round-trips correctly

---

### User Story 3 — Observability：审计日志有自己的家 (Priority: P2)

开发者想知道自己的 Coffer vault 里发生了什么——哪些 resource 和能力被加、启用、禁用、删除了，谁干的，什么时候。**Observability** 入口给他这个：一份审计日志，记录每一次生命周期事件，每一行都是一句口语化的活动描述（"Enabled demo-fs"、"Discovered tool write_file on demo-fs"）而不是裸的 `event_type` 代码。它按时间范围与 actor 过滤、客户端分页，展开任意一行可看它的原始记录详情。

**Why this priority**: P2——审计日志在 spec 001 已经交付；本故事是它的重设计过滤 + 表格以及 `Observability` 这个家。跨服务器的 invocation 历史与上游健康 / 指标也规划进 Observability，但每一个都是未来增量，不在上线之前展示（见 Out of Scope）。

**Independent Test**: 开 `/observability`——Observability section 内的审计日志视图以 "Audit log" 标题渲染，带 filter bar (时间范围 / actor) 与分页表格，每一行是一条可读的活动行；点任意一行展开它的原始详情。访问 legacy `/audit` URL——app 重定向到 `/observability`。

**Representative scenarios** (完整 Given/When/Then 见 `## Acceptance Scenarios`):

- observability route renders the audit log
- legacy /audit redirects to Observability

---

### User Story 4 — Settings 按用户角度组织，不是按 daemon 内部 (Priority: P2)

开发者打开 Settings，看到的 tab 是按"他在管什么"分组，不是按"Coffer 怎么搭的"：**Data**（retention 策略、手动清理、备份）与 **About**（版本、许可证、源代码）；桌面端加 **App** tab（开机启动）。daemon 是实现细节——没有 "Daemon" tab，没有只读的 daemon 状态面板。用户永远不需要知道 Coffer 跑了一个后台 daemon。

**Why this priority**: P2——底层控件已能工作；本故事是重新组织 + 删除，不是新能力。一个没组织好的 Settings 页恰是 US2 反对的"像脚手架"信号，用户也明确反馈过它令人困惑。

删除的——下列都不是用户需要操作或看到的：

- **Shutdown daemon** — 从 web 点它会杀掉你正在看的那页；要恢复还得回终端。daemon shutdown 属于 CLI。
- **Token rotation** — 一个单用户本地 app 一辈子可能只需要一次的安全操作；`coffer daemon rotate-token` 在 CLI 已覆盖。
- **只读的 daemon 状态面板** (status / version / port) — 实现细节；一个健康的 daemon 不需要 UI，失败情形归 offline banner 管。
- **重复的语言选择器与 "Installed resource kinds" dump** — 侧栏已经有语言切换，kind 列表是开发细节。

剩余术语改成口语（例如 "prune" 改写成"清理过期数据"）。

**Independent Test**: 开 `/settings`——落在 Data。浏览器里的 tab 是 Data / About（桌面端加 App tab）。没有 "Daemon" tab，没有 daemon 状态面板；任何 tab 都不暴露 "Shutdown" 或 "Rotate token"。

**Representative scenarios** (完整 Given/When/Then 见 `## Acceptance Scenarios`):

- settings layout uses the redesigned tabbed sidebar
- settings drops the confusing controls

---

### User Story 5 — 桌面壳：常驻又不挡路 (Priority: P3)

初次安装之后，开发者期望 Coffer 在任何 MCP 客户端启动时都已经在了——不需要手动启动——并在不主动管理它时藏好。Tauri 桌面 app 监管本地 daemon（拉起 + 透明重连）、跑在系统托盘里、从托盘点击恢复主窗口，并提供可选的开机启动。

**Why this priority**: P3——生活质量的打磨。spec 001 的 daemon 与 shim 不依赖桌面 app；本故事是把 Coffer 变成每天用的桌面产品的便利层。它是从 spec 001 移过来的——后端 / 前端 spec 拆分后，桌面壳是面向用户的界面，归 002。

**Independent Test**: 打开 "launch at login"，注销再登录——daemon 已在跑，托盘图标已在。关掉主窗口——daemon 还活着，托盘图标还在，MCP 客户端依然可用；从托盘恢复窗口看到原状态。

**Representative scenarios** (完整 Given/When/Then 见 `## Acceptance Scenarios`):

- launch at login
- close to tray, not exit

---

## Acceptance Scenarios

### Scenario: cold-start renders authenticated content

- **Given** 用户从未打开过 Coffer (localStorage 空，HOME 下还没有 daemon.json)
- **And** `coffer daemon start` 正在跑（HOME 下有 daemon.json）
- **When** 他们在真实浏览器里访问 `http://localhost:5173/`
- **Then** 页面在 2 秒内渲染出侧栏 + 主内容区
- **And** 主内容显示 resources 欢迎视图（不出现 generic error 卡片）
- **And** 侧栏列出 Coffer 的运营界面——MCP servers、Observability、Settings——分组在 "Resources" 与 "System" 标题下

### Scenario: token-missing renders an actionable empty state

- **Given** `~/.coffer/daemon.json` 不存在 (daemon 没在跑)
- **When** 用户访问 `http://localhost:5173/`
- **Then** 页面显示一个 "Daemon not running" 视图，给出一个清晰的下一步（可复制的 `coffer daemon start` 命令）
- **And** 侧栏仍然可见，让用户能定位自己
- **And** 任何视图都不会出现字面 "unexpected error" 或 `INTERNAL_ERROR`

### Scenario: empty resources list renders a welcome view

- **Given** daemon 正在跑且尚未注册任何 resource
- **When** 用户打开 `/resources`
- **Then** 页面渲染一张欢迎卡片，带简短介绍以及主行动 "Add MCP server" 按钮
- **And** 欢迎卡片**不**显示空表格或占位 ghost 行

### Scenario: MCP server registration round-trip via JSON import

- **Given** 用户在 resources 列表打开 "Add MCP server" 对话框
- **When** 他们粘入标准的 `mcpServers` JSON 并确认 review 步骤
- **Then** app 先把每台服务器 POST 到 `/api/v1/resources`，再把任何 secret env 值通过 `/api/v1/keychain` 写入 keychain（register-first 顺序避免注册失败时遗留 orphan keychain 条目）
- **And** 成功时对话框关闭；只有一台服务器时，app 跳到 `/resources/mcp_server/<name>` 的 Overview tab
- **And** 新服务器立刻出现在 resources 列表，健康状态先是 "unknown"，10 秒内变为 "healthy"

### Scenario: add-server form navigates to detail then back to list shows card

- **Given** 用户完成了一台新 MCP 服务器的 JSON 导入对话框
- **When** 他们落到服务器详情页，再返回 `/resources`
- **Then** 该服务器卡片出现在 resources 列表

### Scenario: capability toggle uses the redesigned tab layout

- **Given** 一台已注册的 MCP 服务器，至少暴露一个工具和一个 resource
- **When** 用户打开服务器详情页并点 Tools tab
- **Then** 每个工具渲染为一行，含名称、描述与启用 / 禁用开关
- **And** 切换某工具的开关会持久化偏好并重拉工具列表
- **And** 同样的流程在 Resources tab 与 Prompts tab 上同样工作

### Scenario: resource capability toggle works via the Resources tab

- **Given** 一台已注册的 MCP 服务器，至少暴露一个 resource URI
- **When** 用户切到 Resources tab，通过其开关禁用一个 resource
- **Then** resource 开关反映出禁用状态

### Scenario: prompt capability toggle works via the Prompts tab

- **Given** 一台已注册的 MCP 服务器，至少暴露一个 prompt
- **When** 用户切到 Prompts tab，通过其开关禁用一个 prompt
- **Then** prompt 开关反映出禁用状态

### Scenario: capability search box narrows the tool list

- **Given** 一台已注册的 MCP 服务器，暴露多个工具
- **When** 用户在 Tools tab 的能力搜索框输入部分名字
- **Then** 只有匹配的工具仍然可见，不匹配的工具被隐藏

### Scenario: invocations table renders the redesigned empty + populated states

- **Given** 一台已注册的服务器，没有 invocation
- **When** 用户在其详情页打开 Invocations tab
- **Then** 空态显示 "No invocations yet" 以及如何触发一次的提示
- **Given** 同一台服务器，DB 中至少有一条 invocation
- **When** Invocations tab 加载
- **Then** 表格渲染 timestamp / type / capability / status / latency 列
- **And** 状态过滤下拉可操作

### Scenario: invocation status filter dropdown exposes selectable options

- **Given** 一台已注册的服务器
- **When** 用户在 Invocations tab 点开状态过滤 combobox
- **Then** 下拉 portal 中至少渲染出 "All" 选项

### Scenario: observability route renders the audit log

- **Given** 至少存在一条审计事件
- **When** 用户打开 `/observability`
- **Then** Observability section 的审计日志视图以 "Audit log" 标题渲染
- **And** 它渲染 filter bar（时间范围、actor）与一个分页表格，每一行是口语化的活动行，不是裸 event 代码
- **And** 点任意一行展开它的原始详情（绝对时间、event 代码、payload）
- **And** filters 实时收窄可见行

### Scenario: audit log row expand shows detail panel

- **Given** 审计日志至少有一行
- **When** 用户在 Observability 页点击一行
- **Then** 展开的详情面板渲染出该行的 event label

### Scenario: audit log free-text filter narrows rows

- **Given** 审计日志包含至少两个不同服务器名的行
- **When** 用户在搜索框输入其中一个服务器名
- **Then** 只有包含该名字的行仍然可见，另一个名字的行消失

### Scenario: audit log pagination controls appear and advance page

- **Given** 审计日志的条数多于默认 page size
- **When** 用户打开 Observability 页并点 Next
- **Then** 页码指示前进到 "Page 2 of …"，Previous 按钮变为可用

### Scenario: legacy /audit redirects to Observability

- **Given** 用户走老书签访问 `/audit`
- **When** 路由解析
- **Then** app 重定向到 `/observability`
- **And** 不出现 "page not found" 视图

### Scenario: settings layout uses the redesigned tabbed sidebar

- **Given** 用户访问 `/settings`
- **When** 页面解析
- **Then** 它落在 Data tab
- **And** settings 侧栏显示 Data 与 About（桌面端再加 App tab），当前路由高亮
- **And** 点 tab 切换右侧面板内容，不整页刷新

### Scenario: settings drops the confusing controls

- **Given** 用户打开 Settings 各 tab
- **When** 每个 tab 完整渲染
- **Then** 任何 tab 都不暴露 "Shutdown daemon" 或 "Rotate token" 控件
- **And** 没有 "Daemon" tab，也没有只读 daemon 状态面板
- **And** About tab 只展示 version / license / source——没有语言选择器，没有 resource-kind 列表

### Scenario: retention period persists across reload

- **Given** 用户打开 Data settings tab
- **When** 他们对一张日志表关闭 "Keep forever"、设置一个具体的天数并点 Save
- **Then** 刷新页面后显示同一个被保存的 retention-days 值

### Scenario: language switcher round-trips correctly

- **Given** UI 当前是英文
- **When** 用户在侧栏的语言切换器选 中文
- **Then** 侧栏标签、页面标题与表单标签在下一次渲染就切到中文（不整页刷新）
- **And** 偏好跨刷新持久化 (localStorage `coffer.language`)

### Scenario: daemon-offline banner appears when daemon is unreachable

- **Given** daemon 没在跑（`~/.coffer/daemon.json` 上的 `127.0.0.1:<port>` 不可达，或该文件不存在）
- **When** 用户保持 app 打开，且任意一次到 daemon 的鉴权请求连不上
- **Then** 工作区顶部渲染出 daemon-offline banner，里面带可复制的 `coffer daemon start` 命令
- **And** daemon 重新可达后 banner 自动消失，不需要手动刷页

### Scenario: JSON import shows readable error for malformed JSON

- **Given** 用户打开 "Add MCP server" 对话框
- **When** 他们粘入一个 JSON 解析失败（或 JSON 合法但形状不匹配 `mcpServers` 结构）的载荷并提交
- **Then** 对话框保持打开并显示一条可读错误，说明问题在哪（JSON 解析错给出位置，形状不匹配给出失败字段）
- **And** 不向 `/api/v1/resources` 或 `/api/v1/keychain` 发任何请求
- **And** 对话框永不显示字面 "unexpected error" 或 `INTERNAL_ERROR`

---

## Deferred Acceptance Scenarios (US5 Desktop Shell)

下面两条 scenario 覆盖 User Story 5（桌面壳——launch-at-login、close-to-tray）。它们超出 web-shell PR 的范围，延后到桌面 spec (`003-mcp-gateway-desktop`)，由后者交付 Tauri 包装与托盘监管。这里列出仅为可追溯性；桌面 spec 的 acceptance 审计会接管。Web PR 已经把仅桌面的 AppSettings React 组件以 `isTauri()` 守护交付，spec 003 接上即可；开机启动开关本身只在 spec 003 里被验证。

<!-- audit-traceability: 003-mcp-gateway-desktop 上线时把这两条 scenario 原样复制进它的 spec.md -->

### Scenario: launch at login

- **Given** 用户在 settings 中开启了 launch-at-login
- **When** 用户重新登录机器
- **Then** Coffer 在后台启动，系统托盘图标出现

### Scenario: close to tray, not exit

- **Given** Coffer 正在跑、主窗口打开
- **When** 用户关闭主窗口
- **Then** 窗口隐藏，daemon 与托盘图标保留，任意 MCP 客户端仍能使用 coffer；从托盘恢复窗口看到原状态

---

## Out of Scope

- skills / knowledge bases / memory / channels / agents 这些 resource kind 的实现——每一种都是独立的未来 spec。它们各自上线之前不在导航中出现。
- **Chat 体验**的实现——与 Coffer 管理的任意 agent 对话，并在一处聚合直接对话 + channel 对话历史——是未来 spec；Chat 入口在它上线前不展示。
- **agent 双重角色的 provider 开关**（把已注册的 agent 暴露为可被其它 agent 调用的能力）——在 IA 一节作为模型的理由说明，但真正落地在未来 `agent` kind 的 spec 中。
- Observability 的 **Invocations**（跨服务器调用视图）与 **Metrics**（健康 / 时延 / 错误率）视图——规划进 Observability，但每一个都是未来增量，在上线之前不展示。服务器详情页的 per-server Invocations tab 不受影响，照常工作。
- in-app "connect a client" 引导——MCP 客户端配置片段（Claude Code / Claude Desktop / Cursor）是静态内容，住在项目 README，不在 UI 里。shim 自己发现 daemon，所以配置片段不需要 per-machine 参数化。
- 主题切换（亮 / 暗）——重设计后的视觉语言刻意只做亮色。深色主题是未来 spec。
- 移动端响应式布局——侧栏在 1024 px 以下会优雅收起，但 mobile-first 设计延后。

## Success Criteria

- 上面每一条 scenario 至少有一条覆盖测试（unit / integration / e2e），并且 `audit_acceptance` 同时通过 001 与 002。
- 首次用户能在 app 内注册一台 MCP 服务器并到达一个能工作的 gateway；把 MCP 客户端指向 shim 这一步在项目 README 中记录。
- 侧栏只展示运营界面（MCP servers、Observability、Settings）；没有任何"敬请期待"的占位项。
- Observability 提供重设计后的审计日志过滤 + 表格；legacy `/audit` URL 仍能解析。
- Settings 把数据控件（retention、prune、backup）归到 Data tab；daemon 永不作为用户可见概念出现，任何 tab 都不暴露 shutdown 或 token-rotation。
- Tauri 桌面壳监管 daemon、跑在系统托盘、支持开机启动。
- `make verify` + `make verify-e2e` 绿。
