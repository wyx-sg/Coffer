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
  Activity         /activity          — 改了什么、调了什么、哪里坏了
  Settings         /settings
```

**RESOURCES 里每个带列表 UI 的 resource kind 恰好一项，这个对应关系就是规则** ——
五个 kind（`mcp_server`、`skill`、`knowledge`、`provider`、`channel`），五个入口。
其中两个曾经漂出了这条规则，2026-09 被放回：**Model providers** 是唯一一个被塞在
Settings 下的 kind（当时叫「LLM connections」），而那个旧名字描述的是一个页面而不是
它所管理的东西——一个 `provider` 是 `{protocol, base_url, credential_ref}`，即厂商端点
加密钥；模型既不存在那里，也不在那里选，而是在使用现场选。**Channels** 曾在 AGENTS 组
下，但一个 channel 是金库拥有的、带凭据的传输，不是金库的消费者；它该和其他资产并列，
而不是和恰好在它上面应答的 agent 并列。它的名字就是**「消息渠道 / Channels」**，别无其他
——侧栏、页头、欢迎面板、对话框都说同一组词，因为一个用户能从两处到达的界面，不该有两个名字。

于是 AGENTS 组只剩一项。这个不对称是有意的：agent 是这个产品里唯一**使用**金库、
而不是住在金库里的东西，为省一行而合并掉这个分组会丢掉这个区分。

应用的 index (`/`) 重定向到 `/agents`，因此首次访问者落在 Agents 界面。它分组为 **Agents**（消费者）、**Resources**（resource kind）与 **System**（横切工具：Activity 与 Settings），这样导航在 Coffer 成长时保持稳定。agent 住在 `/agents`（列表）与 `/agents/:name`（详情），不出现在 `/mcp-servers` 的 kind 浏览器里。（`/resources` 保留为指向 `/mcp-servers` 的 legacy 重定向，兼容旧书签。）agent 详情页是一个简单的 **Overview + Config files** 详情页：一个 Overview tab 汇总 agent 已注册的配置，一个 Config files tab 只读地呈现其已知配置文件，没有创建 / 编辑 / 删除 / 启用。

所有列表界面（agents、MCP servers、skills、knowledge、model providers、消息渠道、Activity 的每个 tab）共用同一个可搜索、可过滤、可分页的表格：点击一行打开该项的详情页，行内操作是图标加文字标签——不用光秃秃的图标，那读起来会像是另一种不同的操作。卡片只保留给欢迎 / 空态。

每个列表界面都带一列**生效范围（reach）**——这一列以它承载的东西命名，而不是沿用它取代掉的那个开关：一个按钮，上面写着它此刻已经持有的那个答案——「所有 agent」「2 个 agent」「已禁用」，以及被收窄到一个都不剩时的「未选中 agent」——点开是一个面板，「这项资源对谁生效？」在那里是一次单选：已禁用 / 所有 agent / 只限选中的，最后一项展开 scope 的 agent 列表。每个详情页也在页头上带同一个按钮。按钮把生效范围写在脸上，读的人读一眼就知道，而不必去比并排三段里哪一段看起来被按下；不声明 scope 的 kind 拿到同一个按钮，只是面板变成已禁用 / 启用两选一。面板把它的 agent 列表暂存起来，只在关闭时写入一次——两个整值选项会自己把面板关掉——因此一个打开又关掉的面板什么都不写，也就不会有哪次写入去重取列表、把面板锚住的那一行挪走。它只写一份，挂在三处（行内、详情页头、多选栏），因此三者不可能对同一个问题漂成三个不同的答案。多选时把同一个选择应用到整份选区：批量写入是一次新的意图，所以它的按钮读作「设置生效范围…」，面板打开时什么都没选中，而不是从某一行的现值开始；批中失败的行会在唯一的一条汇总里被报出来，而不是被静默跳过。删除仍然是它旁边独立的按钮。

**Observability**（系统健康 / 指标）已规划但今天不展示；它只在自己上线时才进入侧栏。Activity 不是它：一份「发生了什么」的记录，不等于一份「系统状况如何」的度量。反过来这条规则同样成立——一个入口在它的功能被删掉时也要被删掉，Machines 就是这样离开的。

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

已经在用 Coffer 做 MCP gateway 聚合的开发者希望日常流程——注册服务器、看健康、浏览工具、切换能力——看起来、用起来像一个真正的产品，而不是一坨脚手架。标题在字体上有区分；间距统一；每台服务器页面在 per-tool 开关之前先有一个"这台服务器在干嘛"的总览视图；空 / 错 / 加载态都是一等公民。Tools、Resources、Prompts 三个 tab 保持统一——各自带相同的搜索框、状态过滤和逐行启用开关，即使上游没有该类型的任何条目也保留这套外壳（空态渲染在表格内部，而不是一张光秃秃的卡片）。服务器列表带搜索框、状态过滤、客户端分页，让一个大 vault 也能浏览。它的生效范围列不是一个开关：一项资源的生效范围是三态的——已禁用 / 所有 agent / 只限选中的——所以列表里放的就是详情页头部的那一个按钮，它写明这台服务器当下的生效范围，并且可以就地设置；该列的过滤同样给出这几个状态，而不是单纯的启用／停用。列名、过滤与按钮都叫「生效范围」，因为它们问的是同一个问题。技能列表出于同样的理由，做法一致。

**Invocations** tab 列出 gateway 为这台服务器代理过的每一次调用，从新到旧，
可按状态与时间范围过滤，每一行都能展开成该次调用的原始 JSON 记录。它曾经被删过一次，
理由是「上面的流量不是用户的」——每一行都是某个 agent 在调一个工具，人想知道某次调用
为什么失败时该去问那个 agent。这个理由成立，直到坏掉的正是那个 agent；那时候这张表
就是它做过什么的唯一账本。这个 tab 读的还是 gateway 一直在写的那份记录；它和 Activity
的 **MCP 调用** tab（User Story 3）是同一张表，只是把范围收到一台服务器，而不是另起
一张要跟着对方一起维护的表。

"Add MCP server" 是一个对话框，用户把标准的 `mcpServers` JSON 块粘进去（一次一台或多台都行）——就是每台 MCP server README 给的那块。Review 一步让他们确认哪些 `env` 是 secret；这些值会被提到加密凭据存储（config 里只保留它们的 ref），而不是以明文写在 config 里。

**Why this priority**: spec mcp-gateway 把后端正确性交付了，但 UI 是裸 tailwind 默认值。"MCP gateway 完成了"的用户可见标杆是：UI 能在真人手里走通（不是只能在 Playwright fixture 里跑）。

**Independent Test**: 在真实浏览器里把 MCP 流程走一遍：开 `/mcp-servers`（欢迎或列表），点 "Add MCP server"，填表，提交，落到详情页，依次切 Overview / Tools / Resources / Prompts tabs，切换一个工具，回到列表，把语言在英文与 中文 之间切换。每一步都呈现打磨过的内容；没有任何视图死在一个 generic error。

**Representative scenarios** (完整 Given/When/Then 见 `## Acceptance Scenarios`):

- MCP server registration round-trip via JSON import
- capability toggle uses the redesigned tab layout
- language switcher round-trips correctly

---

### User Story 3 —— 三份记录，一个页面，各一张表 (Priority: P2)

Coffer 保留三份「发生了什么」的账本：**审计日志**（金库里改了什么、谁改的）、
**MCP 调用日志**（gateway 代理过的每一次调用）、**守护进程日志**（Coffer 自己做了
什么，包括坏在哪）。审计日志的页面被删掉，理由是没人会专门去浏览「我的金库里改了
什么」；Invocations tab 被删掉，理由是那上面每一行都属于某个 agent。两次删除对各自
那个界面的判断都没错，错在它们背后的需求：东西不对劲的时候，问题从来不是「改了
什么」「调了什么」或「哪里报错了」，而是**发生了什么**；而回答它，意味着手里攥着三份
记录，自己拿手去拼。

于是三份有了同一个家。**Activity**（System 组下，`/activity`）是一个页面，
每份记录一个 tab——**变更**、**MCP 调用**、**守护进程**——各自一张从新到旧的表，
带着那份记录真正拥有的列：一行活动和它的 actor；一次调用的服务器、能力、耗时与结果；
一条日志的级别、logger 与消息。每个 tab 都能按自由文本和时间范围过滤，外加它那份记录
才有的那一个过滤（actor、调用状态、只看错误）；任意一行都能展开成它的原始记录，
以等宽、可滚动的代码块美化打印。

三者曾短暂地被合并成一条时间线，而正是那次合并让列的问题显形：一张表只能承载三份
记录的最小公约数，于是一个「详情」列轮流表示 actor、服务器和 logger，而一次调用的
耗时、一条记录的级别根本无处安放。跨记录的对齐仍然是 `coffer__diagnose` 的活儿——
它返回的就是拼好的两侧，服务于那个问「刚才发生了什么」而不是「把某一类完整给我」
的读者。

只有当前可见的那个 tab 会发请求。某份记录的路由失败时，错误渲染在它自己的 tab 里：
一条泳道挂掉不能把另外两条一起拖下水。页面没有手动刷新控件——切 tab 或改过滤就会
换查询并重新拉取。

`GET /api/v1/audit` 与 `coffer audit` 不变。页面为另外两条泳道新增两条只读路由：
`GET /api/v1/mcp/invocations`（跨服务器，每行点名自己属于哪台）与
`GET /api/v1/daemon/logs`。守护进程日志那条路由把 token 依赖挂在路由自身上——
daemon 的 router 让 `/status` 保持开放，而日志内容不是状态。

**守护进程日志不是一种格式，而 Daemon tab 的那几列取决于把它们全都读懂。**
`daemon.log` 里同时躺着 Coffer 自己的 structlog JSON、迁移跑过之后 root logger
继承来的标准库 formatter、uvicorn 的默认格式、上游 MCP 服务器的 rich 输出，以及
守护进程重新拉起的 cloudflared 子进程写下的 zerolog——其中一些还带着颜色转义，
因为一个往管道里写的子进程并不总是相信自己不在终端里。只认得 structlog 的读取器
会让几乎每一行的级别、logger 与时间都空着，并把整行原文倒进消息列，那等于没有列。
所以每一种写入方的格式在抵达页面之前都被归一到同一组字段上、转义序列被剥掉，
traceback 跟着抛出它的那条记录走，而不是变成一串什么都没有的行。哪种格式都对不上的
一行仍然整行保留而不是丢掉——它往往正是有意思的那一行。

事件类型重新渲染成口语化的活动行（"Enabled demo-fs"），因此它们的译文在两个 locale
里一并回来，并像错误码那样被守住：新增一个没有译文的事件类型会让 CI 失败，而不是
让中文读者在某一行上看到生的 `resource_enabled`。

**Why this priority**：P2 —— 一个界面，覆盖三份已经存在的记录；不新采集任何数据。

**Independent Test**：打开 `/activity` —— 渲染出三个 tab，每个用自己的列展示自己那份
记录；展开一行看到它的原始记录；某个 tab 的路由不可用时错误只出现在它自己里面、
另外两个照常工作；旧的 `/audit` 地址重定向到这里。

**Representative scenarios**（完整列表见 `## Acceptance Scenarios`）：

- activity gives each record its own tab
- the daemon tab reads every writer in the log
- activity row expands to its raw record
- a failing record shows its error inside its own tab
- legacy /audit redirects to activity
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

### Scenario: activity gives each record its own tab

- **Given** Coffer 已记录过一条审计条目、一次 MCP 调用与一条守护进程日志
- **When** 用户打开 `/activity` 并依次走过它的三个 tab
- **Then** 每个 tab 用那份记录自己的列渲染出自己那张从新到旧的表——一行活动和 actor；一次调用的服务器、能力、耗时与结果；一条日志的级别、logger 与消息
- **And** 一条变更读作口语化的一行，而不是生的事件码

### Scenario: the daemon tab reads every writer in the log

- **Given** `daemon.log`里同时有好几种写入方的行——Coffer 自己的 structlog JSON、标准库 formatter、uvicorn、rich，以及 cloudflared 子进程的 zerolog——其中一行带颜色转义，另有一段 traceback 写在抛出它的那条记录下面
- **When** 用户打开 Daemon tab
- **Then** 每一行都带着它自己那一行声明过的时间、级别与 logger，且没有任何一行声称自己有没说过的时间或级别
- **And** 没有任何消息把终端转义序列当文本渲染出来
- **And** traceback 跟着抛出它的那条记录走，而不是自己变成若干行
- **And** errors-only 过滤按每一行自己的级别判断，而不是把所有非 JSON 行都当成错误

### Scenario: activity row expands to its raw record

- **Given** 某个 Activity tab 至少有一行
- **When** 用户点击（或在该行上按 Enter/Space）
- **Then** 展开区域渲染出它的原始记录——完整的底层 JSON，以等宽、可滚动的代码块美化打印

### Scenario: a failing record shows its error inside its own tab

- **Given** 三条路由中的一条不可用（比如一个还没有这条路由的旧 daemon）
- **When** 用户打开 `/activity`
- **Then** 失败的那份记录在它自己的 tab 里渲染出可读的错误
- **And** 另外两个 tab 照常渲染出各自的行

### Scenario: legacy /audit redirects to activity

- **Given** 用户跟着旧书签访问 `/audit`
- **When** 路由解析
- **Then** 应用重定向到 `/activity`，且不出现 "page not found" 视图

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
- **And** 侧栏列出 Coffer 的运营界面——Agents、MCP servers、Skills、Knowledge、Model providers、Channels、Activity、Settings——分组在 "Agents"、"Resources"、"System" 标题下

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
- 侧栏只展示运营界面（Agents、MCP servers、Skills、Knowledge、Model providers、Channels、Activity、Settings），按角色分组；没有任何功能以"敬请期待"的死占位项出现。
- Coffer 保留的三份记录——审计日志、MCP 调用日志、守护进程日志——对人经由 `/activity` 这一个页面抵达，一份记录一个 tab、一张表，对 agent 经由 `coffer__diagnose` 这一次调用抵达，它返回的是拼好的；`/audit` 与 legacy `/observability` 重定向到那里，而不是 404。脚本仍然有 `GET /api/v1/audit` / `coffer audit` 与 `coffer mcp invocations`。Observability（系统健康 / 指标）是预留的未来界面，不是这个。
- Settings 把数据控件（retention 与 prune）归到 Data tab；daemon 永不作为用户可见概念出现，任何 tab 都不暴露 shutdown 或 token-rotation。
- `make verify` + `make verify-e2e` 绿。
