# 功能规格：UI Shell 与视觉语言

> English: [spec.md](./spec.md)

**Feature Branch**: `feature/002-mcp-gateway-web` (PR #23，建立在 `feature/mcp-gateway` 之上)
**Status**: Accepted
**Input**: mcp-gateway 的 UI 以功能骨架的形式交付：裸 tailwind 默认值、ad-hoc 间距、没有首次使用引导。本 spec 把这个骨架升级为一个真正的产品壳——一套连贯的视觉语言、一个建立在单一统一概念（每一种被管理的实体都是一种 _resource kind_）之上的信息架构，以及让首次访客（而不是绕过鉴权的 Playwright fixture）就能用上 gateway 的端到端流程。

**Scope note**: Coffer 的 spec 按后端/前端切分。`mcp-gateway` 拥有 daemon、MCP gateway、REST API 与 CLI。**本 spec 拥有 web UI**——视觉语言、信息架构、国际化。**这是一份在 001 之上的纯 UI 重设计**：不新增任何后端，所以数据模型仍住在 `specs/mcp-gateway/data-model.md`，本目录不另设 `tasks.md` 追踪。配套文档见 [`plan.md`](./plan.md) 与 [`quickstart.md`](./quickstart.md)。

## Information Architecture

侧栏按**角色 (role)** 分组，而不是单一一条轴。两个概念并列：**agent** 是*消费者*（你使用的 agent），**resource** 是这些 agent 所依赖的*资产*——一个有名字、有配置、有生命周期的被管理实体，背后是一个 kind-agnostic 框架。`mcp_server` 是今天交付的 resource kind，通过 per-kind registry 暴露，使导航与 resources 页面不带任何 kind 专属分支。agent **不是**一种 resource kind，所以它独占一组，不归在 Resources 下。

**侧栏只展示 Coffer 当下能做什么。** 它不列出"尚未实现"的占位项：一个写满"敬请期待"的侧栏读起来是未完成的脚手架，不是产品。

当下侧栏交付的四个界面是：

```
 AGENTS
  Agents           /agents            — 消费者（Bot 图标）
 RESOURCES
  MCP servers      /mcp-servers       — 被聚合的上游 server
  Skills           /skills            — Coffer 投递给 agent 的东西
  Knowledge        /knowledge         — 每个知识 scope 一页
  Model providers  /model-providers   — 带凭据的厂商端点
  Channels         /channels          — agent 应答所在的 IM 传输
 SYSTEM
  Settings         /settings
```

**RESOURCES 里每个带列表 UI 的 resource kind 恰好一项，这个对应关系就是规则** ——
五个 kind（`mcp_server`、`skill`、`knowledge`、`provider`、`channel`），五个入口。
其中两个曾经漂出了这条规则，2026-09 被放回：**Model providers** 是唯一一个被塞在
Settings 下的 kind（当时叫「LLM connections」），而那个旧名字描述的是一个页面而不是
它所管理的东西——一个 `provider` 是 `{protocol, base_url, credential_ref}`，即厂商端点
加密钥；模型既不存在那里，也不在那里选，而是在使用现场选。**Channels** 曾在 AGENTS 组
下，但一个 channel 是金库拥有的、带凭据的传输，不是金库的消费者；它该和其他资产并列，
而不是和恰好在它上面应答的 agent 并列。

于是 AGENTS 组只剩一项。这个不对称是有意的：agent 是这个产品里唯一**使用**金库、
而不是住在金库里的东西，为省一行而合并掉这个分组会丢掉这个区分。

应用的 index (`/`) 重定向到 `/agents`，因此首次访问者落在 Agents 界面。它分组为 **Agents**（消费者）、**Resources**（resource kind）与 **System**（横切工具：Settings），这样导航在 Coffer 成长时保持稳定。agent 住在 `/agents`（列表）与 `/agents/:name`（详情），不出现在 `/mcp-servers` 的 kind 浏览器里。（`/resources` 保留为指向 `/mcp-servers` 的 legacy 重定向，兼容旧书签。）agent 详情页是一个简单的 **Overview + Config files** 详情页：一个 Overview tab 汇总 agent 已注册的配置，一个 Config files tab 只读地呈现其已知配置文件，没有创建 / 编辑 / 删除 / 启用。

所有列表界面（agents、MCP servers、skills、knowledge、model providers、channels）共用同一个可搜索、可过滤、可分页的表格：点击一行打开该项的详情页，行内操作是紧凑的图标。卡片只保留给欢迎 / 空态。

**Observability**（系统健康 / 指标）已规划但今天不展示；它只在自己上线时才进入侧栏。反过来这条规则同样成立——一个入口在它的功能被删掉时也要被删掉，Chat、Machines 与 Audit log 就是这样离开的。

侧栏可折叠到只剩图标的轨道再展开；选择跨会话持久化（localStorage）。

详见 [Everything Is a Resource Kind](../../docs/decisions/everything-is-a-resource-kind.zh.md)（2026-05-30 已修订），记录了这种基于角色的 IA 背后的架构决策（agent 作为独立的消费者轴；被拒绝的备选：独立的"surface"概念；侧栏策略：不放"敬请期待"占位项）。

## User Scenarios & Testing

### User Story 1 — 首次访客落入一个可用的 app (Priority: P1)

某位开发者第一次打开 web UI。他从未注册过服务器。页面立刻出内容——没有"unexpected error"卡片，没有空白页加不知道下一步做什么。他看到一个欢迎视图，介绍 Coffer 是什么，并给出一个明确的下一步："添加你的第一台 MCP 服务器。"

**Why this priority**: 这是通往其它一切流程的门。如果第一屏看起来坏了或对下一步沉默，用户关掉标签页，产品其它部分都没机会出现。

**Independent Test**: 清掉 `localStorage`，`make dev` 之后打开 `http://localhost:5173/`。页面通过 dev 专用的 token 注入插件 (`frontend/vite.config.ts`) 自动鉴权；index 重定向到 `/agents`，用户看到 Agents 欢迎卡片，主行动是 "Add agent"。"Add MCP server" 欢迎卡片在 `/mcp-servers`，一步可达。

**Representative scenarios** (完整 Given/When/Then 见 `## Acceptance Scenarios`):

- cold-start renders authenticated content
- token-missing renders an actionable empty state (not generic error)
- empty resources list renders a welcome view

---

### User Story 2 — 日常 MCP 操作有产品质感，不再像脚手架 (Priority: P1)

已经在用 Coffer 做 MCP gateway 聚合的开发者希望日常流程——注册服务器、看健康、浏览工具、切换能力——看起来、用起来像一个真正的产品，而不是一坨脚手架。标题在字体上有区分；间距统一；每台服务器页面在 per-tool 开关之前先有一个"这台服务器在干嘛"的总览视图；空 / 错 / 加载态都是一等公民。Tools、Resources、Prompts 三个 tab 保持统一——各自带相同的搜索框、状态过滤和逐行启用开关，即使上游没有该类型的任何条目也保留这套外壳（空态渲染在表格内部，而不是一张光秃秃的卡片）。服务器列表带搜索框、状态过滤、客户端分页，让一个大 vault 也能浏览。它的状态列不是一个开关：一项资源的触达范围是三态的——停用 / 所有 agent / 指定 agent——所以列表里放的就是详情页头部的那个控件，可以就地设置；状态过滤同样给出这三个状态，而不是单纯的启用／停用。技能列表出于同样的理由，做法一致。

没有 **Invocations** tab，Overview 上也不再有"Last invocation"那一行。这个 tab
曾经上线过——一张带过滤、分页的表格，列出 gateway 代理过的每一次调用，每一行都能
展开成该次调用的原始 JSON 记录——而它和下一个故事里审计日志那个页面的毛病是同一个：
上面的流量不是用户的。每一行都是某个 agent 在通过 gateway 调一个工具；人想知道某次
调用为什么失败时，是去问那个 agent，而不是趴在 gateway 肩膀上读它的表格。

记录本身没有任何变化。gateway 依然把每一次调用写进 invocation 日志，
`GET /api/v1/resources/mcp_server/{name}/invocations` 与 `coffer mcp invocations`
依然能读回来——给能调这个路由的 agent，也给脚本。消失的是那个页面。

"Add MCP server" 是一个对话框，用户把标准的 `mcpServers` JSON 块粘进去（一次一台或多台都行）——就是每台 MCP server README 给的那块。Review 一步让他们确认哪些 `env` 是 secret；这些值会被提到加密凭据存储（config 里只保留它们的 ref），而不是以明文写在 config 里。

**Why this priority**: spec mcp-gateway 把后端正确性交付了，但 UI 是裸 tailwind 默认值。"MCP gateway 完成了"的用户可见标杆是：UI 能在真人手里走通（不是只能在 Playwright fixture 里跑）。

**Independent Test**: 在真实浏览器里把 MCP 流程走一遍：开 `/mcp-servers`（欢迎或列表），点 "Add MCP server"，填表，提交，落到详情页，依次切 Overview / Tools / Resources / Prompts tabs，切换一个工具，回到列表，把语言在英文与 中文 之间切换。每一步都呈现打磨过的内容；没有任何视图死在一个 generic error。

**Representative scenarios** (完整 Given/When/Then 见 `## Acceptance Scenarios`):

- MCP server registration round-trip via JSON import
- capability toggle uses the redesigned tab layout
- language switcher round-trips correctly

---

### User Story 3 —— 审计日志由 agent 来读，而不是由人来浏览 (Priority: P2)

审计日志曾经有一个页面：System 组下 `/audit` 处一张带过滤、分页的活动行表格。
**它已被删除。** 实际上没人打开过它。人不会专门坐下来浏览「我的金库里改了什么」——
人是发现有东西坏了，然后去问那个帮他的角色，而那个角色是 agent。

于是这份日志保住了它的读者，丢掉了它的页面。`coffer__diagnose` 一次给 agent 两份
记录——审计日志（改了什么、谁改的）与守护进程自己的日志（发生了什么，包括失败）——
放在同一条从新到旧的时间线上。agent 手里本来就有这个工具，不需要知道文件路径，
拿到的是已经对齐好的两侧，而不是两样还要自己拼起来的东西。

REST 路由与 `coffer audit` 保留，供脚本使用。消失的是那个页面、它那套口语化渲染，
以及那 39 条翻译好的事件字符串——它们当初存在，是为了让中文读者不会在某一行上看到
生的 `event_type`。现在没有任何东西再渲染一行了，而 agent 要的正是线上原值。

**Why this priority**：P2 —— 这是一次删除加一个工具，不是一个新界面。

**Independent Test**：`/audit` 不再有路由，侧边栏也没有任何入口指向它；agent 调用
`coffer__diagnose` 会在一个响应里拿回最近的变更与最近的日志记录。

**Representative scenarios**（完整列表见 `## Acceptance Scenarios`）：

- an agent reads recent changes and failures in one call

---

### User Story 4 — Settings 按用户角度组织，不是按 daemon 内部 (Priority: P2)

开发者打开 Settings，看到的 tab 是按"他在管什么"分组，不是按"Coffer 怎么搭的"：**General**（显示偏好——列表表格的默认每页条数，以及打开受管文件所用的首选外部编辑器）、**Data**（retention 策略与手动清理）与 **About**（版本、许可证、源代码）。Settings 打开时落在 General tab。daemon 是实现细节——没有 "Daemon" tab，没有只读的 daemon 状态面板。用户永远不需要知道 Coffer 跑了一个后台 daemon。

**General** tab 必须暴露默认每页条数偏好（每个列表表格据此初始化的 rows-per-page），持久化在 `localStorage`。它还必须暴露一个**首选外部编辑器**偏好——当用户从只读文件查看器中打开一个受管文件（或其所在文件夹）时，Coffer 用来打开它的应用。默认是操作系统的默认应用；用户可以通过**从 daemon 检测到的已安装编辑器中挑选**（经 `GET /api/v1/fs/editors` 枚举，spec agent-registry FR-039——浏览器无法列出已安装应用），或填入自定义的应用 / 启动命令来覆盖。与其他显示偏好一样，所选值持久化在 `localStorage`，绝不发送给 daemon（仅在打开文件时作为目标短暂传递）。

**Why this priority**: P2——底层控件已能工作；本故事是重新组织 + 删除，不是新能力。一个没组织好的 Settings 页恰是 US2 反对的"像脚手架"信号，用户也明确反馈过它令人困惑。

删除的——下列都不是用户需要操作或看到的：

- **Shutdown daemon** — 从 web 点它会杀掉你正在看的那页；要恢复还得回终端。daemon shutdown 属于 CLI。
- **Token rotation** — 一个单用户本地 app 一辈子可能只需要一次的安全操作；`coffer daemon rotate-token` 在 CLI 已覆盖。
- **只读的 daemon 状态面板** (status / version / port) — 实现细节；一个健康的 daemon 不需要 UI，失败情形归 offline banner 管。
- **重复的语言选择器与 "Installed resource kinds" dump** — 侧栏已经有语言切换，kind 列表是开发细节。

剩余术语改成口语（例如 "prune" 改写成"清理过期数据"）。

**Independent Test**: 开 `/settings`——落在 General。tab 列表是 General / Data / About。没有 "Daemon" tab，没有 daemon 状态面板；任何 tab 都不暴露 "Shutdown" 或 "Rotate token"。

**Representative scenarios** (完整 Given/When/Then 见 `## Acceptance Scenarios`):

- settings layout uses the redesigned tabbed sidebar
- settings drops the confusing controls
- the General tab persists a preferred-editor choice

---

## Acceptance Scenarios

### Scenario: an agent reads recent changes and failures in one call

- **Given** Coffer 已记录过审计条目并写过守护进程日志
- **When** 某个 agent 调用 `coffer__diagnose`
- **Then** 它在一个响应里拿回两条时间线，都是从新到旧——审计条目在 `changes`，
  日志记录在 `log`——且两侧都不含任何密钥值

### Scenario: cold-start renders authenticated content

- **Given** 用户从未打开过 Coffer (localStorage 空，HOME 下还没有 daemon.json)
- **And** `coffer daemon start` 正在跑（HOME 下有 daemon.json）
- **When** 他们在真实浏览器里访问 `http://localhost:5173/`
- **Then** index 重定向到 `/agents`，页面在 2 秒内渲染出侧栏 + 主内容区
- **And** 主内容显示 Agents 欢迎视图（不出现 generic error 卡片）
- **And** 侧栏列出 Coffer 的运营界面——Agents、MCP servers、Skills、Knowledge、Model providers、Channels、Settings——分组在 "Agents"、"Resources"、"System" 标题下

### Scenario: token-missing renders an actionable empty state

- **Given** `~/.coffer/daemon.json` 不存在 (daemon 没在跑)
- **When** 用户访问 `http://localhost:5173/`
- **Then** 页面显示一个 "Daemon not running" 视图，给出一个清晰的恢复操作（「重新加载」按钮）
- **And** 侧栏仍然可见，让用户能定位自己
- **And** 任何视图都不会出现字面 "unexpected error" 或 `INTERNAL_ERROR`

### Scenario: empty resources list renders a welcome view

- **Given** daemon 正在跑且尚未注册任何 resource
- **When** 用户打开 `/mcp-servers`
- **Then** 页面渲染一张欢迎卡片，带简短介绍以及主行动 "Add MCP server" 按钮
- **And** 欢迎卡片**不**显示空表格或占位 ghost 行

### Scenario: MCP server registration round-trip via JSON import

- **Given** 用户在 resources 列表打开 "Add MCP server" 对话框
- **When** 他们粘入标准的 `mcpServers` JSON 并确认 review 步骤
- **Then** app 先把每台服务器 POST 到 `/api/v1/resources`，再把任何 secret env 值通过 `/api/v1/credentials` 写入凭据存储（register-first 顺序避免注册失败时遗留 orphan 凭据条目）
- **And** 成功时对话框关闭；只有一台服务器时，app 跳到 `/mcp-servers/mcp_server/<name>` 的 Overview tab
- **And** 新服务器立刻出现在 resources 列表，健康状态先是 "unknown"，10 秒内变为 "healthy"

### Scenario: add-server form navigates to detail then back to list shows card

- **Given** 用户完成了一台新 MCP 服务器的 JSON 导入对话框
- **When** 他们落到服务器详情页，再返回 `/mcp-servers`
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

### Scenario: settings layout uses the redesigned tabbed sidebar

- **Given** 用户访问 `/settings`
- **When** 页面解析
- **Then** 它落在 General tab
- **And** settings 侧栏显示 General、Data 与 About，当前路由高亮
- **And** 点 tab 切换右侧面板内容，不整页刷新

### Scenario: settings drops the confusing controls

- **Given** 用户打开 Settings 各 tab
- **When** 每个 tab 完整渲染
- **Then** 任何 tab 都不暴露 "Shutdown daemon" 或 "Rotate token" 控件
- **And** 没有 "Daemon" tab，也没有只读 daemon 状态面板
- **And** About tab 只展示 version / license / source——没有语言选择器，没有 resource-kind 列表

### Scenario: general tab persists the preferred editor

- **Given** 用户打开 General settings tab
- **When** 他们设置一个首选外部编辑器（挑选一个检测到的编辑器，或填入一条自定义启动命令）
- **Then** 刷新页面后显示同一个首选编辑器值
- **And** 清除覆盖后恢复为操作系统默认应用

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
- **Then** 工作区顶部渲染出 daemon-offline banner，带一个清晰的恢复操作——「重新加载」按钮
- **And** daemon 重新可达后 banner 自动消失，不需要手动刷页

### Scenario: JSON import shows readable error for malformed JSON

- **Given** 用户打开 "Add MCP server" 对话框
- **When** 他们粘入一个 JSON 解析失败（或 JSON 合法但形状不匹配 `mcpServers` 结构）的载荷并提交
- **Then** 对话框保持打开并显示一条可读错误，说明问题在哪（JSON 解析错给出位置，形状不匹配给出失败字段）
- **And** 不向 `/api/v1/resources` 或 `/api/v1/credentials` 发任何请求
- **And** 对话框永不显示字面 "unexpected error" 或 `INTERNAL_ERROR`

---

## Success Criteria

- 上面每一条 scenario 至少有一条覆盖测试（unit / integration / e2e），并且 `audit_acceptance` 同时通过 001 与 002。
- 首次用户能在 app 内注册一台 MCP 服务器并到达一个能工作的 gateway；把 MCP 客户端指向 shim 这一步在项目 README 中记录。
- 侧栏只展示运营界面（Agents、MCP servers、Skills、Knowledge、Model providers、Channels、Settings），按角色分组；没有任何功能以"敬请期待"的死占位项出现。
- 审计日志没有页面：`/audit` 与 legacy `/observability` 都不再解析，侧栏也没有任何入口指向它们。agent 通过 `coffer__diagnose` 读这份日志，脚本通过 REST 路由与 `coffer audit` 读。MCP invocation 日志同样没有页面，理由也一样——它里面的每一行都是某个 agent 在调工具，不是人——所以它保留 REST 路由与 `coffer mcp invocations`，丢掉那个 tab。Observability（系统健康 / 指标）是预留的未来界面，不是审计日志。
- Settings 把数据控件（retention 与 prune）归到 Data tab；daemon 永不作为用户可见概念出现，任何 tab 都不暴露 shutdown 或 token-rotation。
- `make verify` + `make verify-e2e` 绿。
