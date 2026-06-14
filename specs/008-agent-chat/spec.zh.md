# 功能规格：Agent Chat

> English: [spec.md](./spec.md)

**Feature Branch**: `feature/agent-chat`
**Created**: 2026-05-22
**Status**: Draft
**Input**: 用户描述："Coffer needs a chat platform. A first-class chat
page where the user holds many conversations, and a stable seam so that more
than one kind of agent can be reached from that page without re-architecture.
Coffer ships one agent on the platform out of the box — a general-purpose
built-in agent that uses every resource in the vault (MCP tools, skills,
memory, knowledge bases) through Coffer's own MCP gateway, on a user-chosen LLM
provider. The platform also carries the capabilities an agent needs that the
built-in agent's own gating makes optional — a human-approval channel for tool
calls — and the controls every conversation needs: streamed turns, one
in-flight turn at a time, and user interruption."

本规格把 Coffer 从一个*存储* AI 资产的 vault 变成一个*使用*它们的 vault，而且
它以一个**平台**的方式实现，而非一个单一的硬接功能。它一次交付两件事：

1. **一个聊天平台。** 一个一等的聊天界面、持久化的多对话历史、一个流式回合协议、
   人在环中的工具审批，以及用户中断 —— 全部针对一个 **agent-provider 注册表**
   表达。一个 agent 只通过该注册表被触达，因此新增另一种 agent 是一个新的注册表
   条目，而非对聊天页面、持久化层或 REST/SSE 契约的改动。
2. **该平台上的 agent。** Coffer 的内置通用 agent，"Coffer Assistant" —— 一个
   进程内的 agentic 循环，由用户自己的 MCP server、skills、memory 与知识库通过
   Coffer 的 MCP gateway 驱动，运行在一个用户配置的 LLM provider 上 ——
   **外加**两个 CLI 支持的 agent，**Claude Code** 与 **Codex**，每个都由它安装的
   命令行工具在一个用户按对话挑选的工作目录中驱动。这些 CLI agent 是保持接缝
   诚实的东西：它们是真实的第二与第三个 provider，而非一个承诺，并且它们证明了
   新增一个 agent 是一个注册表条目，无需改动聊天界面、持久化或 wire 契约。

平台的各部分与它的 agent 被共同交付，因为一个没有 agent 的平台无法被演练，而一个
没有平台的 agent 无法被触达。每一个内置 agent 自身并不需要的平台能力 ——
最重要的是审批通道 —— 仍然完整交付并被端到端证明，因此接缝在它落地的那一天就是
真实的，而非一个承诺。

## 定位 —— Vault Console（金库控制台，[ADR-021](../../docs/decisions/ADR-021-chat-as-vault-console.zh.md)）

交付之后，本界面从"一个通用的多 agent 聊天客户端"重定位为 **Vault Console（金库
控制台）**：用来*使用与检视金库*的地方，而非一个在浏览器里、与 agent 自己的 UI 或
IM 竞争的日常编码聊天。它的两个耐久职责是：

1. **对金库说话。** 通过内置 agent（Coffer 自有网关的进程内 MCP 客户端），用户与
   自己的 memory、skills、knowledge、聚合 MCP 工具对话并检视它们。每个回合 surface
   它碰了哪些金库资源，让控制台同时成为"查看一个 agent 能从金库拿到什么"的地方。
2. **旁观并审批 channel 驱动的会话。** Channels（Spec 009）创建会话、转发工具审批走
   的是与本界面**同一套** `ConversationPort` / `TurnPort` 接缝。控制台是
   human-in-the-loop 审批席：它呈现会话来源（网页草稿 vs channel peer），让用户为 IM
   peer 正在驱动的回合接管审批席。

CLI agent（Claude Code、Codex）**不**被重定位为日常编码聊天；它们仍然是 (a) 让
provider 接缝保持诚实的 test-drive 目标，(b) IM peer 驱动、用户在这里旁观/审批的
会话。**移出范围：** 把 Coffer 当作主力的浏览器内编码聊天；只对那个定位才有意义的
能力保持在范围外，除非未来某个 spec 重开它。

## 再次定位 —— 内置 agent 是内部能力（[ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.zh.md)）

[ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.zh.md)
部分取代了上面的 Vault Console 定位。`builtin`「Coffer Assistant」**退出聊天人格**：
它不再是注册的聊天 agent，并从 agent 选择器中移除。聊天**只**与 Coffer 受管 agent
（`claude_code`、`codex`，及将来的受管 agent）对话，界面从 _Vault Console（金库控制
台）_ 改回 **Chat（聊天）**。"通过内置 agent 与金库对话"这一职责被去掉；本地模型重塑
为**仅内部**能力，只能通过 `coffer__*` MCP 工具触达——即对 `coffer__search_tools` 的
语义升级，与一个对知识/记忆的新 `coffer__ask` agentic-RAG 工具（见 ADR-024）。**旁观
并审批 channel 驱动会话**这一职责（ADR-021 职责 2）原样存续，走同一套
`ConversationPort` / `TurnPort` / `submit_approval` 接缝。

下文用户故事、验收场景与功能需求中仍把内置 agent 描述为可选聊天 agent 的部分（它的
model 选择器、它在聊天里的金库工具调用、对它的 `coffer chat`），应读作 ADR-024 从聊天
面移除的历史已交付行为；LLM/agentic-loop 机器保留但被重塑到 `coffer__ask` 之后，而非
作为聊天人格呈现给用户。

## 用户场景与测试

### 用户故事 1 —— 在首次聊天前配置一个模型 provider（优先级：P1）

内置 agent 没有自己的 LLM。首次访问 Chat 时，用户被引导至 **Settings → Models**,
在那里他们注册至少一个模型：选择一个 provider（Anthropic、OpenAI，或一个本地的
Ollama 端点），提供凭据（云端 provider）或 base URL（Ollama），并命名一个
model id。一旦存在一个模型，内置 agent 就可被选择且聊天被解锁。

**为何此优先级**：没有一个配置好的模型，内置 agent 根本无法回答。这是使用它的
每一个其它场景的入口。

**独立测试**：在全新安装下，打开 Settings → Models，添加一个带凭据的 Anthropic
模型，保存；观察它被列出并标记为默认；Chat 页面不再显示 "no model configured"
状态。

**覆盖的场景**：

- 用一个凭据注册一个云端模型
- 用一个 base URL、无凭据注册一个本地 Ollama 模型
- 拒绝一个缺少必需凭据或 base URL 的模型
- 第一个被注册的模型成为默认模型
- 从命令行注册并列出模型

---

### 用户故事 2 —— 通过选择一个 agent 开始一个对话（优先级：P1）

用户从 Chat 页面开始一个新对话。一个**新对话对话框**询问该对话应与哪个 agent
交谈：它列出该平台提供的每一个 agent，每个 agent 标记为可用或不可用，并显示一个
内容取决于所选 agent 的配置区域。对内置 agent 而言该配置区域是模型选择。该对话
记录它所属的 agent，并在该 agent 的配置被校验并存储后被创建。

**为何此优先级**：这是平台接缝被可视化的体现。一个无法命名其 agent 的对话无法被
路由到一个 agent，而一个硬编码单一 agent 的聊天页面不是一个平台。

**独立测试**：打开 Chat，点击 "New conversation"；该对话框列出内置 agent；选择它,
确认；一个对话被创建，其记录的 agent 是内置那一个，且立即可用。

**覆盖的场景**：

- 新对话对话框列出每一个已注册 agent 及其可用性
- 创建一个对话记录所选 agent 并校验其配置
- 一个未知 agent 或一个无效的 agent 配置被拒绝，不持久化任何东西
- agent 列表可从 REST API 触达

---

### 用户故事 3 —— 与一个 agent 聊天并看它流式输出（优先级：P1）

用户打开一个对话，输入一条消息，并收到一个流式回复 —— 文本逐 token 出现，工具
调用在发生时出现，且对话保持可交互。每个对话同一时间只跑一个回合；在一个回合
流式输出时 composer 被锁定。

**为何此优先级**：这是核心交付物。一个无法承载一个流式对话的聊天页面不是一个产品。

**独立测试**：在内置 agent 与一个模型配置好的情况下，发送
"Explain what Coffer is in two sentences"，观察一个流式助手回复无错误地完成，且
在 reload 后仍然可见。

**覆盖的场景**：

- 发送一条消息并收到一个流式助手回复
- 该回复被持久化并在页面 reload 与守护进程重启后保留
- composer 在一个回合流式输出时被禁用、在它结束时重新启用
- 一个 LLM/provider 错误在对话中浮现而不致页面崩溃

---

### 用户故事 4 —— 内置 agent 与 vault 协作（优先级：P1）

用户向内置 agent 询问需要他们自己数据的东西（"what do my notes say about
OAuth?"）。agent 通过 Coffer 的 MCP gateway 调用工具 —— 上游 MCP server 工具、
`coffer__recall`、`coffer__search_knowledge`、`coffer__load_skill` —— 且每次调用
在消息流中以一张内联、可展开的卡片出现，展示工具名、状态、输入与结果。

**为何此优先级**：这是让内置 agent 成为 _Coffer 的_ agent 而非一个通用聊天框的
东西 —— 它 dogfood 了 vault。

**独立测试**：在一个 memory store 持有一条已知记录的情况下，向 agent 询问一个只能
从该记录回答的问题；观察流中一张 `coffer__recall` 工具调用卡片以及一个植根于该
记录的回答。

**覆盖的场景**：

- agent 发现 gateway 聚合的每一个工具（上游 MCP + 内置）
- 一次工具调用渲染为一张内联可展开卡片，默认折叠
- skills 可通过 `coffer__list_skills` / `coffer__load_skill` 触达
- 一次失败的工具调用渲染一张失败卡片，且 agent 继续或报告它
- 一个达到工具迭代上限的回合干净地结束，而非作为一个错误
- 当 vault 没有 MCP server、memory 或 KB 时 agent 正常回答

---

### 用户故事 5 —— 保留多个对话（优先级：P1）

用户运行不止一条工作线索。他们创建新对话、在历史列表中切换、重命名它们、并删除
他们不再需要的那些。一切都在守护进程重启后保留。

**为何此优先级**：一个只有单一短暂线索的聊天会丢失工作，且不符合 Coffer 的
local-first、SQLite-as-record 立场。

**独立测试**：创建两个对话，在每个中发送一条消息，重命名一个，重启守护进程，
重新打开 Chat —— 两个对话及其消息都仍然存在并带新名称；删除一个并确认它已消失。

**覆盖的场景**：

- 创建、列出、切换、重命名并删除对话
- 一个新对话从它的首条消息收到一个自动生成的标题
- 对话与消息在守护进程重启后保留
- 对话历史列表可折叠

---

### 用户故事 6 —— 批准或拒绝一个 agent 的工具调用（优先级：P2）

一些 agent 在用户说可以之前不得运行一个工具。当一个 agent 到达一个需要权限的
工具调用时，该回合暂停，且聊天界面显示一张命名该工具及其输入的**审批卡片**。
用户点击 **Allow** 或 **Deny**；agent 收到该决策并继续 —— 在 allow 时运行该工具,
或在 deny 时把拒绝当作该工具的结果对待。Coffer 的内置 agent 依赖 gateway 自己的
能力门控，不为每次调用的审批而暂停；审批通道是一个为任何确实使用它的 agent 完整
交付的平台能力。

**为何此优先级**：一个能在用户机器上行动的 agent 只有在用户能介入时才安全。把该
通道建进平台 —— 而非建进某个 agent —— 正是保持接缝诚实的东西。不阻塞核心循环。

**独立测试**：用一个为工具调用请求审批的 agent 驱动一个回合；观察审批卡片；
点击 Allow；观察工具运行且回合结束。用 Deny 重复；观察 agent 收到拒绝。

**覆盖的场景**：

- 一个 agent 回合暂停并发出一个界面渲染的审批请求
- allow 一个请求让 agent 运行该工具并结束回合
- deny 一个请求把拒绝作为工具结果返回给 agent
- 一个针对未知或已决请求的审批决策被拒绝
- SDK 驱动的 Claude Code 的逐工具审批中转正常工作

---

### 用户故事 7 —— 停止一个正在运行的回合（优先级：P2）

一个回合耗时过长或走错了方向。用户点击 **Stop**。回合立即结束；agent 已经产生的
一切 —— 部分文本、已完成的工具调用 —— 被保留为助手的消息，因此对话展示发生了
什么并保持可用。这与删除对话不同，后者会整个丢弃一个进行中的回合。

**为何此优先级**：没有一个停止控制，一个缓慢或被误导的回合会挟持对话直到它结束。
不阻塞核心循环。

**独立测试**：开始一个回合，在流中点击 Stop；回合结束，一条持有部分输出的助手
消息被持久化，且对话接受下一条消息。

**覆盖的场景**：

- 停止一个正在运行的回合结束它并持久化部分助手消息
- 一个被停止的对话立即接受一个新回合
- 在没有回合运行时停止是一个无害的 no-op
- 删除一个有活跃回合的对话丢弃它并不留下孤儿行

---

### 用户故事 8 —— 按对话切换模型（优先级：P2）

用户配置了不止一个模型，并从线索顶栏的一个模型选择器中挑选一个给定对话的内置
agent 使用哪一个。

**为何此优先级**：不同的工作想要不同的模型（一个用于快速草稿的本地模型，一个用于
困难推理的前沿模型）。不阻塞核心循环。

**独立测试**：在配置了两个模型的情况下，在顶栏选择器中改变一个对话的模型，发送
一条消息，并确认该回合运行在所选模型上（记录在结果消息上）。

**覆盖的场景**：

- 除非被覆盖，一个对话使用默认模型
- 改变模型选择器只影响后续回合
- 每条助手消息记录产生它的模型

---

### 用户故事 10 —— 看 agent 做了什么以及花了多少（优先级：P3）

每个回合在结果消息上记录 token 用量，而内置 agent 调用的每个工具流经 gateway 的
现有审计轨迹。

**为何此优先级**：建立信任并支持调试与成本意识。不阻塞核心聊天运行。

**独立测试**：运行一个调用至少一个工具的回合；确认助手消息显示 token 用量且审计
日志以 actor `agent` 记录该已完成回合。

**覆盖的场景**：

- 一条助手消息记录 prompt/completion token 用量
- 一个已完成回合以 actor `agent` 记录在审计日志中

---

### 用户故事 11 —— 旁观并审批 channel 驱动的会话（优先级：P2）

一个 IM peer（Spec 009）正在驱动一个针对某 agent 的会话。在 Vault Console 里，用户
在历史列表中看到该会话**带有来源与 peer 身份标记**，看它的回合流式推进，并在 agent
因工具审批暂停时**从网页接管审批席**，与 IM 按钮等价。

**为何此优先级**：Channels 已经把审批走平台的审批通道；给人一个在网页旁观并审批的
席位，才让控制台的第二个角色变真。不阻塞核心循环。

**独立测试**：配对一个 IM peer，让它发起一个请求审批的回合；打开 Vault Console，看到
该会话带着 channel 来源与 peer 标记；点 Allow；观察工具运行、IM peer 收到结果。

**覆盖的场景**：

- 会话列表标记每个会话的来源（网页 vs channel），并对 channel 会话标记 peer 身份
- channel 驱动回合上的待审批可从网页审批卡片解决，与 IM 按钮等价（两者解决同一审批
  通道）
- 旁观一个 channel 驱动回合，流式收到与网页 composer 相同的回合事件

---

### 边界情况

- **没有配置模型**：Chat 页面渲染一个链接到 Settings → Models 的可操作空状态；
  它不显示一个通用错误或一个失效的输入框。在没有模型配置的情况下选择内置 agent
  会以 no-model 状态使回合失败，而非崩溃。
- **未知 agent / 无效 agent 配置**：用一个平台不提供的 agent，或用一个该 agent
  拒绝的配置创建一个对话，会以一条命名问题的消息失败；不持久化任何东西。
- **无效或被吊销的凭据**：回合以一条命名 provider 的消息失败；对话保持可用；不
  留下一条处于"永远流式"状态的部分助手消息。
- **工具调用失败**（上游 MCP server 宕机、内置工具抛出）：工具卡片显示一个失败
  状态，失败作为一个工具结果返回给 agent，且 agent 可以重试、绕过它，或报告它。
- **失控的工具循环**：一个回合由一个工具迭代上限约束；达到它时回合作为一个正常
  回合完成干净地结束（携带 stop reason `max_iterations`），而非作为一个错误。
- **没有匹配请求的审批决策**：一个为不存在的 request id、或一个已决请求发布的
  决策被拒绝；回合不受影响。
- **一个回合在等待审批时被中断**：待决的审批等待随回合一并被取消；agent 在暂停
  之前产生的一切按下面的中断规则被保留。
- **对话长于模型上下文窗口**：内置 agent 发送适配进一个上下文预算（由一个字符
  预算近似，约 4 字符/token）的最近历史；较旧的回合带一个标记从模型输入中省略，
  而完整对话仍被存储。
- **在一个回合流式输出时发送第二条消息**：被拒绝；composer 在进行中回合期间被
  禁用。
- **流式客户端在回合中断连**（页面关闭、导航离开）：回合在服务器端完成且助手
  消息被持久化；下次加载显示已完成的消息。
- **回合被用户中断**：回合立即停止且部分助手消息被持久化（用户故事 7）。
- **一个对话在其回合流式输出时被删除**：进行中回合被取消并丢弃；不留下孤儿消息行。
- **一个 frontmatter 畸形的 skill**：从暴露给内置 agent 的 skill 目录中排除；它
  不会破坏工具列表或回合。
- **守护进程在有一个被中断回合时重启**：没有对话被留下一条半写的流式消息；一个
  被中断的回合被标记为 failed。

## 验收场景

按 `agents/sdd.md` 与 `agents/testing.md`，本节中每个场景都被至少一个标记
`@pytest.mark.acceptance(spec="008-agent-chat", scenario="…")`（Python）或
`acceptance("008-agent-chat", "…", …)`（TypeScript）的测试引用。

### 场景：注册一个模型 provider

- **Given** 一个没有配置模型的运行中守护进程，
- **When** 用户用一个 provider、model id 以及其 provider 所需的凭据或 base URL
  注册一个模型，
- **Then** 该模型被持久化，第一个这样的模型被标记为默认，且 Chat 页面不再报告
  "no model configured"。

### 场景：拒绝一个不完整的模型

- **Given** 一个运行中守护进程，
- **When** 用户注册一个无凭据的云端模型，或一个无 base URL 的 Ollama 模型，
- **Then** 注册以一条命名缺失字段的消息被拒绝且不持久化任何东西。

### 场景：列出可用的 agent

- **Given** 一个运行中守护进程，
- **When** 用户询问平台它提供哪些 agent，
- **Then** 受管 agent（`claude_code`、`codex`）被列出，各带一个显示名与一个可用性
  标志，`builtin` agent **不**在其中（[ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.zh.md)），
  且该列表可从 REST API 触达。

### 场景：开始一个对话时选择一个 agent

- **Given** 一个运行中守护进程，
- **When** 用户创建一个对话，命名一个 agent 并提供该 agent 的配置，
- **Then** 该对话被持久化并记录该 agent，该 agent 的配置被校验并存储，且该对话
  就绪可用。

### 场景：拒绝一个未知 agent 或无效 agent 配置

- **Given** 一个运行中守护进程，
- **When** 用户创建一个对话，命名一个平台不提供的 agent，或提供一个该 agent
  拒绝的配置，
- **Then** 该请求以一条命名问题的消息被拒绝且没有对话被持久化。

### 场景：发送一条消息并收到一个流式回复

- **Given** 一个对话与至少一个配置好的模型，
- **When** 用户发送一条消息，
- **Then** 助手回复增量地流式输出、完成，并作为该对话上的一条消息被持久化。

### 场景：回复在重启后保留

- **Given** 一个带一条已完成助手回复的对话，
- **When** 守护进程重启且用户重新打开该对话，
- **Then** 每条消息都存在且未改变。

### 场景：skills 作为工具可触达

- **Given** vault 中至少一个有效的 skill，
- **When** agent 列出可用工具，
- **Then** `coffer__list_skills` 与 `coffer__load_skill` 存在，且
  `coffer__load_skill` 返回该 skill 的内容。

### 场景：一个 agent 回合为人工审批而暂停

- **Given** 一个其回合在运行一个工具前请求审批的 agent，
- **When** 回合到达该工具调用，
- **Then** 流携带一个聊天界面渲染为卡片的审批请求，回合等待，且在用户 allow 它时
  agent 运行该工具且回合完成。

### 场景：一次被拒绝的工具调用被报告给 agent

- **Given** 一个暂停在审批请求上的 agent 回合，
- **When** 用户 deny 它，
- **Then** 拒绝作为该工具的结果被递交给 agent 且回合在不运行该工具的情况下完成。

### 场景：SDK 驱动的 Claude Code 的逐工具审批中转

- **Given** 一个由 SDK 支持的 Claude Code provider 驱动的回合，其中工具调用请求审批，
- **When** `can_use_tool` 回调触发，且用户通过平台审批通道提交 allow 或 deny 决策，
- **Then** 在 allow 时 SDK 回调解析为 `PermissionResultAllow` 且回合以 `TurnDone`
  完成；在 deny 时回调解析为 `PermissionResultDeny`（携带拒绝消息），且回合也以
  `TurnDone` 干净完成。

### 场景：app-server 驱动的 Codex 的逐工具审批中转

- **Given** 一个由 app-server 支持的 Codex provider 驱动的回合，其中 Codex 在回合
  进行中发送 `item/commandExecution/requestApproval` 或
  `item/fileChange/requestApproval` 请求，
- **When** 平台发出一个 `ApprovalRequest` 事件，且用户通过平台审批通道提交 allow
  或 deny 决策，
- **Then** 在 allow 时 adapter 向 Codex 写回 `{decision: "accept"}`，回合继续并以
  `TurnDone` 完成；在 deny 时 adapter 向 Codex 写回 `{decision: "decline"}`，回合
  也以 `TurnDone` 干净完成。

### 场景：停止一个正在运行的回合

- **Given** 一个正在流式输出的回合，
- **When** 用户停止它，
- **Then** 回合立即结束，一条持有迄今所产生内容的助手消息被持久化，且对话立即
  接受一个新回合。

### 场景：管理对话

- **Given** 一个运行中守护进程，
- **When** 用户创建、重命名、切换并删除对话，
- **Then** 每个操作都持久化且历史列表反映它；一个被删除的对话及其消息被移除。

### 场景：归档并恢复一个对话

- **Given** 一个在活跃历史列表中的对话，
- **When** 用户归档它，
- **Then** 它离开默认（活跃）列表，出现在已归档列表中，且不被销毁；恢复它把它
  返回到活跃列表。归档一个不存在的对话被拒绝。

### 场景：在一个流式回合期间 composer 被锁定

- **Given** 一个回合正在流式输出，
- **When** 用户尝试在同一对话中发送另一条消息，
- **Then** 该发送在回合结束前被拒绝。

### 场景：模型选择被记录

- **Given** 两个配置好的模型，
- **When** 用户设置一个对话的模型并发送一条消息，
- **Then** 回合运行在所选模型上且助手消息记录产生它的模型。

### 场景：no-model 空状态

- **Given** 一个没有配置模型的运行中守护进程，
- **When** 用户打开 Chat 页面，
- **Then** 一个链接到 Settings → Models 的可操作空状态被显示且无消息可被发送。

### 场景：token 用量与审计

- **Given** 一个完成的回合，
- **When** 回合结束，
- **Then** 助手消息记录 token 用量且审计日志包含该已完成回合，actor 为 `agent`。

### 场景：list a provider's models

- **Given** 用户在新增/编辑模型并填好了 provider（以及该 provider 需要的 base URL / 凭证 ref），
- **When** 拉取该 provider 的模型，
- **Then** Coffer 返回该 provider 暴露的模型 id 供选择；若列不到则返回空列表 + 提示，用户仍可手填 model id。

### 场景：test a model connection

- **Given** 一个模型的 provider、model id 以及（需要时的）凭证 ref，
- **When** 用户测试连接，
- **Then** Coffer 向 provider 发一个最小请求并报告成功或人性化的失败信息，且不持久化任何内容。

### 场景：channel 驱动的会话可从控制台旁观与审批

- **Given** 一个 IM peer 驱动的会话，其回合因工具审批而暂停，
- **When** 用户打开 Vault Console，
- **Then** 该会话带着 channel 来源与 peer 身份标记出现，且从网页审批卡片提交
  allow/deny 解决的是与 IM 按钮相同的那个待审批。

## 需求

### 功能需求

**聊天平台与 agent-provider 接缝**

- **FR-001**：聊天界面 MUST 只通过一个 **agent-provider 注册表** 触达一个 agent：
  一个回合被运行、一个对话被初始化、一个对话的 agent 状态被拆除，都是通过向注册表
  询问对话上命名的 agent。聊天页面、持久化层与 REST/SSE 契约 MUST NOT 依赖任何
  特定 agent。
- **FR-002**：向平台新增另一个 agent MUST 仅是一个新的注册表条目 —— 它 MUST 不
  需要改动聊天 REST/SSE 契约、对话/消息 schema、回合 orchestrator 或聊天页面。
- **FR-003**：每个对话 MUST 通过一个 `agent_key` 记录它所属的 agent。创建一个
  对话 MUST 接受一个 `agent_key`（默认为内置 agent）与一个不透明的、agent 特定的
  配置；被命名的 agent MUST 校验并持久化该配置，把一个无效配置作为一个领域错误
  拒绝。一个没有 agent 提供的 `agent_key` MUST 被拒绝。
- **FR-004**：平台 MUST 通过 REST API 与 GUI 的新对话对话框暴露已注册 agent 的
  列表 —— 每个带一个稳定的 key、一个显示名与一个当前可用性标志。
- **FR-005**：一个 agent 通过一个**agent adapter**为一个回合被寻址，该 adapter
  是自包含的：仅给定对话历史与一个审批通道，它产出一个类型化回合事件的流。adapter
  携带它自己的模型、工具与配置；orchestrator MUST NOT 注入它们。平台在此接缝背后
  交付三个 agent —— 内置 agent 加两个 CLI 支持的 agent（Claude Code、Codex）——
  因此接缝由真实的额外 provider 验证，而非一个单一占用者。
- **FR-005a**：System MUST 交付面向 Claude Code 与 Codex 的子进程支持的 agent provider。
  每个由一个工作目录（其 `agent_config.cwd`）按对话配置，该目录 MUST 是一个存在的
  目录，否则配置被拒绝。一个 CLI agent 的可用性 MUST 反映其命令行二进制是否可在
  守护进程的 PATH 上解析；一个不可用的 agent 被列出但不可选。一个 CLI 回合 MUST
  在该目录中运行该工具、把它的行分隔 JSON 输出流式映射到平台的回合事件，并持久化
  上游 session id 以便下一个回合延续同一 session。Claude Code 通过 Claude Agent
  SDK 驱动：每个 `can_use_tool` 权限回调都桥接至平台的人工审批通道
  （`can_use_tool` → `ApprovalRequest` 事件 → allow/deny 决策 → SDK 结果），
  从而每次调用的工具审批对 SDK 支持的 Claude Code 端到端工作。Codex 通过
  `codex app-server`（stdio 上的 JSON-RPC 2.0，NDJSON 帧）驱动：服务端→客户端
  审批请求（`item/commandExecution/requestApproval` 与
  `item/fileChange/requestApproval`）桥接至同一人工审批通道（allow → `"accept"`
  决策，deny → `"decline"` 决策），从而逐工具审批对 app-server 支持的 Codex 通过
  与 Claude Code 相同的平台通道端到端工作。

**内置 agent 与 agentic 循环**

- **FR-006**：System MUST 交付一个内置通用 agent，"Coffer Assistant"，在代码中
  定义（身份、system prompt、默认行为）。agent 在代码中定义并在启动时注册；不存在
  通过 API 创建、编辑或删除 agent。
- **FR-007**：System MUST 把内置 agent 作为一个进程内 agentic 循环运行：调用所选
  LLM、执行任何被请求的工具、把结果反馈，并重复直到模型产出一个最终答案或一个边界
  被触及。
- **FR-008**：System MUST 用一个可配置的工具迭代上限约束每个内置 agent 回合，并把
  一个超限回合作为一个正常回合完成（stop reason `max_iterations`）干净地结束，
  而非作为一个错误。
- **FR-009**：内置 agent 的 system prompt MUST 确立它作为 Coffer 助手的身份，并
  包含一个 vault 的 skills 目录（name + description）。
- **FR-010**：内置 agent MUST 在它的 adapter 为一个回合被构建时解析对话的模型；
  一个为内置 agent 在没有模型配置的情况下开始的回合 MUST 在任何消息被流式输出之前
  以 "no model configured" 条件失败。

**Vault 能力表面（内置 agent）**

- **FR-011**：System MUST 给内置 agent Coffer MCP gateway 聚合的每一个工具 ——
  上游 MCP server 工具与 `coffer__` 前缀的内置工具 —— 通过进程内消费该 gateway,
  不经过一个网络或子进程传输。
- **FR-012**：System MUST 把 vault 的 skills 作为 gateway 内置工具
  `coffer__list_skills` 与 `coffer__load_skill` 暴露给 agent，遵循现有的每 kind
  `application/<kind>/builtin_tools.py` 模式。
- **FR-013**：当内置 agent 调用一个工具时，System MUST 把它路由通过 gateway，
  以便 gateway 的现有能力门控与调用日志生效。
- **FR-014**：一个工具失败 MUST 作为一个描述错误的工具结果返回给 agent；它 MUST
  NOT 中止回合。

**对话与持久化**

- **FR-015**：System MUST 把对话及其消息持久化在 SQLite 中作为 system of record；
  它们不被建模为 kind-agnostic Resource 框架的 Resource。
- **FR-016**：用户 MUST 能够创建、列出、打开、重命名并删除对话；一个新对话 MUST
  收到一个从它的首条消息派生的自动生成标题；删除一个对话 MUST 也通过注册表拆除
  它的 agent 的每对话状态。
- **FR-016a**：用户 MUST 能够归档一个对话并恢复它。一个已归档对话从默认（活跃）
  列表中排除，可通过一个已归档列表检索，且不被销毁；归档是可逆的且区别于删除。
  对话历史 MUST 可按标题搜索，且活跃/已归档视图 MUST 可从一个列表内过滤器切换。
- **FR-016b**：对话 MUST 遵循一个两阶段、保留管理的生命周期，两个窗口都在
  Settings → Data 下可配置：(1) 保留 worker 自动归档在自动归档窗口（默认 7 天）
  内没有新消息的对话，且 (2) 在已归档对话被归档后配置的天数（默认 30 天）删除它们
  （及其消息）。任一窗口都可被设为永久保留以禁用该阶段；自动归档是可逆的（用户
  可以恢复）且只有删除是破坏性的。
- **FR-017**：一条消息 MUST 存储它的 role 与一个 `text`、`tool_use` 与
  `tool_result` 类型的有序内容块列表；助手消息 MUST 在 agent 报告时也存储 token
  用量与产生它们的模型。

**回合生命周期：流式、审批、中断**

- **FR-018**：System MUST 每个对话只允许一个进行中回合并在当前回合结束前拒绝
  第二条消息。
- **FR-019**：System MUST 把一个回合作为一个类型化事件序列流式给客户端，至少覆盖
  文本增量、工具调用、工具结果、审批请求、回合完成与回合错误。
- **FR-020**：平台 MUST 提供一个**人工审批通道**：一个 agent 回合可以发出一个
  暂停该回合的审批请求；用户通过一个专用端点提交一个 allow/deny 决策；该决策被
  递交给等待中的回合。一个针对未知或已决请求的决策 MUST 被拒绝。该通道 MUST 交付
  并被端到端验证，即便内置 agent 不使用它。
- **FR-021**：System MUST 让用户中断一个正在运行的回合：回合立即停止且部分助手
  消息（已产生的任何文本与工具块）MUST 被持久化。中断区别于对话删除，后者丢弃
  进行中回合。
- **FR-022**：一个被中断的回合（用户中断、客户端断连、守护进程重启、对话删除）
  MUST NOT 把一个对话留下一条永久"流式"的消息；这样的回合 MUST 被最终化或标记为
  failed。

**模型 provider 与凭据**

- **FR-023**：用户 MUST 能够注册、列出、编辑并移除已配置的模型；v1 MUST 支持
  provider 类型 `anthropic`、`openai` 与 `ollama`，且新增另一个 provider 类型
  MUST 是配置，而非重构。
- **FR-024**：一个已配置的模型 MUST 仅作为一个在运行时通过凭据模块解析的凭据引用
  携带它所需的凭据；没有秘密材料与模型行一同存储或以明文到达数据库。
- **FR-025**：System MUST 恰好标记一个已配置模型为默认，并把它用于任何不覆盖模型
  的对话。
- **FR-026**：一个对话 MUST 能够覆盖模型；该覆盖只影响该对话的后续回合。

**界面**

- **FR-027**：System MUST 在桌面应用中提供一个 Chat 页面：一个可折叠的对话历史
  列表、一个带 agent picker 与一个每 agent 配置区域的新对话对话框、一个带流式
  文本的消息线索、内联可展开工具调用卡片与审批卡片、一个模型选择器、一个 composer,
  以及一个用于进行中回合的停止控制。
- **FR-028**：System MUST 把一个 "Chat" 条目作为主（最顶部）导航项加入应用侧边栏;
  现有的 002-ui-shell IA 在其余方面不变。
- **FR-029**：System MUST 提供一个覆盖每个模型注册操作的 Settings → Models 页面。
- **FR-030**：GUI 中可用的每个聊天与模型操作 MUST 通过 REST API 可用，且模型操作
  MUST 作为 CLI 命令可用；CLI 读操作 MUST 支持 `--json`。（`coffer chat` CLI 随内置
  聊天 agent 的退役一并移除，ADR-024。）

**可观测性**

- **FR-031**：System MUST 记录每条消息的 token 用量并在 GUI 与 CLI `--json` 输出
  中呈现它。
- **FR-032**：System MUST 以 actor `agent` 把每个已完成回合记录在审计日志中；内置
  agent 进行的工具调用记录在 gateway 的调用日志中，归属于该 agent 的 gateway
  session。

**Chat 界面：来源呈现（[ADR-021](../../docs/decisions/ADR-021-chat-as-vault-console.zh.md)，被 [ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.zh.md) 修订）**

- **FR-033**：Chat 界面（标签为 **Chat（聊天）**，按 [ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.zh.md)
  从 _Vault Console_ 改回）MUST **只**与 Coffer 受管 agent 对话，并 MUST 呈现、让用户
  旁观/审批 channel 驱动的会话。`builtin` agent MUST NOT 作为聊天 agent 提供；其模型是
  仅内部能力，只能通过 `coffer__*` 工具触达（ADR-024），而非聊天人格。Chat 界面 MUST
  NOT 把自己定位为主力的浏览器内编码聊天；受管 agent 仍作为 provider 接缝验证、以及
  channel 驱动会话的目标而保留。
- **FR-034**：会话历史 MUST 呈现每个会话的来源（网页草稿 vs channel peer），并对
  channel 来源的会话呈现 peer 身份；任一会话上的待审批工具调用 MUST 可从网页审批
  卡片解决，与 channel 自身的审批控件等价（两者解决 FR-020 的同一 human-approval
  通道）。

### 关键实体

- **Agent Provider**：平台的扩展单元。一个 provider 拥有一个 agent 类型：它有一个
  稳定的 `agent_key`，在对话创建时校验并存储一个对话的 agent 特定配置，为每个回合
  构建一个配置好的 agent adapter，在删除时拆除每对话状态，并报告它当前是否可用。
  provider 被持于 **agent-provider 注册表** 中；聊天界面只知道注册表。
- **Agent Adapter**：一个 agent 对一个回合的处理。给定对话历史与一个审批通道，
  它产出一个 agent 事件流。它是自包含的 —— 它携带它自己的模型、工具与配置，由它
  的 provider 在 adapter 被构建时提供。
- **Built-in Agent**：Coffer 单一的、代码定义的通用 agent（"Coffer Assistant"），
  作为一个 agent provider + adapter 交付。身份、system-prompt 模板、默认模型选择,
  与工具迭代上限。v1 中不可由用户编辑。`agent_key` = `builtin`。
- **Conversation**：一个持久化的聊天线索。字段：id、`agent_key`、title、可选的
  模型覆盖、时间戳。不是一个 Resource。
- **Message**：一个对话中的一条条目。字段：id、对话引用、ordering、role
  （`user` | `assistant`）、有序内容块、token 用量与产生模型（仅助手）、时间戳。
- **Content Block**：一个消息内容的单元 —— `text`、`tool_use`（工具名 + 输入），
  或 `tool_result`（工具名 + 输出或错误）。
- **Model**：一个用户配置的、内置 agent 可运行其上的 LLM。字段：id、显示名、
  provider 类型（`anthropic` | `openai` | `ollama`）、model id、凭据引用（云端）、
  base URL（Ollama / 自定义）、默认标志。
- **Agent Event**：一个流式回合中的一个类型化事件 —— 文本增量、工具调用、工具
  结果、审批请求、回合完成，或回合错误。
- **Approval Request / Approval Decision**：人工审批通道的两半。一个请求命名一个
  等待权限的工具调用；一个决策是用户携带回等待中回合的 allow/deny 答复。

## 成功标准

### 可度量的结果

- **SC-001**：从一个全新安装，一个用户能够注册一个模型、与内置 agent 开始一个
  对话，并在一个真实浏览器中通过 `make dev` 进行一个流式多回合对话，无需阅读源码。
- **SC-002**：一个只能从用户的 memory 或知识库回答的问题被正确回答，对应的工具
  调用在线索中可见。
- **SC-003**：在 GUI 或 CLI 中创建的对话与消息在另一界面中可见且一致，并在守护
  进程重启后保留。
- **SC-004**：本规格中每个验收场景都被至少一个标记
  `acceptance(spec="008-agent-chat", scenario="…")` 的测试覆盖，且
  `make verify-acceptance` 报告零未覆盖场景。
- **SC-005**：完整的 `make verify` 套件在本地与 CI 中通过；`make verify-all`
  （加 e2e）在 macOS 与 Linux 上通过。
- **SC-006**：没有 LLM-provider 凭据曾以明文写入数据库或日志；由一个专用安全测试
  验证。
- **SC-007**：新增一个第二 agent provider 不需要改动聊天 REST/SSE 契约、对话/消息
  schema、回合 orchestrator 或聊天页面 —— 通过针对 agent-provider 注册表、
  `AgentProvider` / `AgentAdapter` 接口与 `agent_key` 字段的评审验证，并由一个
  仅在测试中使用的第二 provider 演示。
- **SC-008**：人工审批通道端到端工作 —— 一个发出审批请求的 agent 回合暂停，决策
  端点递交用户的答复，且回合继续 —— 且一个正在运行的回合可被停止并保留其部分输出;
  两者都由验收测试证明。审批通道额外由一个真实 provider（SDK 支持的 Claude Code）
  而非仅脚本化假对象来行使，确认每次调用的工具审批对生产 agent adapter 端到端工作。

## 假设

- 用户在他们自己的机器上运行 Coffer；没有多租户或远程访问需求。远程通道
  （Telegram 等）不在范围内。
- kind-agnostic Resource 框架、审计日志、凭据模块，以及带它的
  `BuiltinToolRegistry` 与 `coffer__` 内置工具的 MCP gateway —— 来自 specs
  001–006 —— 已就位于本分支的基底上。
- 来自 spec 002-ui-shell 的应用 shell —— 侧边栏 IA、布局、路由、设计系统，与
  Settings 布局 —— 已就位；Chat 页面与 Settings → Models 页面在该 shell 内渲染。
- Memory 与知识库工具（`coffer__recall`、`coffer__search_knowledge`，与同类）已
  作为来自 specs 005–006 的 gateway 内置工具存在；本规格消费它们且不重新定义它们。
- 内置 agent 的 agentic 循环用 LangGraph 框架实现，LLM 客户端通过 LangChain 的
  provider 抽象触达；这些是开源依赖，且分层架构规则被遵守 —— 那些 SDK 保持限制在
  `infrastructure/chat/`，回合编排与 agent-provider 注册表是 `application/`，且
  `domain/chat/` 两者都不 import。
- 交互模型是顺序的：每个对话同一时间一个回合，回合运行时 composer 被锁定。一个
  对话内的并发回合不在范围内。
- agent-provider 注册表在启动时由代码填充；v1 注册一个 provider（内置 agent）。
  注册表是接缝 —— 从用户管理的配置填充它不在本规格内。
- 以下被明确**列为不在范围**：用户创建或用户编辑的 agent；一个管理 agent 注册表的
  GUI；超出 gateway 现有门控与审批通道的每 agent 能力作用域；对话摘要与导出；过去
  外部 agent 会话的恢复/继续；以及任何跨 agent 的原始 transcript 浏览/搜索界面（跨
  agent 的共享由蒸馏后的 memory 承担，[ADR-020](../../docs/decisions/ADR-020-transcript-distillation.zh.md)）。
  远程通道由 Spec 009 单独交付。
