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
provider. The platform also carries the controls every conversation needs:
streamed turns, one in-flight turn at a time, and user interruption."

本规格把 Coffer 从一个*存储* AI 资产的 vault 变成一个*使用*它们的 vault，而且
它以一个**平台**的方式实现，而非一个单一的硬接功能。它一次交付两件事：

1. **一个聊天平台。** 一个一等的聊天界面、持久化的多对话历史、一个流式回合协议，
   以及用户中断 —— 全部针对一个 **agent-provider 注册表** 表达。一个 agent 只通过
   该注册表被触达，因此新增另一种 agent 是一个新的注册表条目，而非对聊天页面、
   持久化层或 REST/SSE 契约的改动。
2. **该平台上的 agent。** Coffer 的内置通用 agent，"Coffer Assistant" —— 一个
   进程内的 agentic 循环，由用户自己的 MCP server、skills、memory 与知识库通过
   Coffer 的 MCP gateway 驱动，运行在一个用户配置的 LLM provider 上 ——
   **外加**两个 CLI 支持的 agent，**Claude Code** 与 **Codex**，每个都由它安装的
   命令行工具在一个工作目录（默认是 Coffer 托管的工作目录）中驱动。这些 CLI agent 是保持接缝
   诚实的东西：它们是真实的第二与第三个 provider，而非一个承诺，并且它们证明了
   新增一个 agent 是一个注册表条目，无需改动聊天界面、持久化或 wire 契约。

平台的各部分与它的 agent 被共同交付，因为一个没有 agent 的平台无法被演练，而一个
没有平台的 agent 无法被触达。agent 以完整权限运行；owner-pairing（属主配对）是安全
闸门。接缝在它落地的那一天就是真实的，而非一个承诺。

## 定位 —— Vault Console（金库控制台，[ADR-021](../../docs/decisions/ADR-021-chat-as-vault-console.zh.md)）

交付之后，本界面从"一个通用的多 agent 聊天客户端"重定位为 **Vault Console（金库
控制台）**：用来*使用与检视金库*的地方，而非一个在浏览器里、与 agent 自己的 UI 或
IM 竞争的日常编码聊天。它的两个耐久职责是：

1. **对金库说话。** 通过内置 agent（Coffer 自有网关的进程内 MCP 客户端），用户与
   自己的 memory、skills、knowledge、聚合 MCP 工具对话并检视它们。每个回合 surface
   它碰了哪些金库资源，让控制台同时成为"查看一个 agent 能从金库拿到什么"的地方。
2. **观测 channel 驱动的会话。** Channels（Spec 009）通过与本界面**同一套**
   `ConversationPort` / `TurnPort` 接缝创建会话。控制台呈现会话来源（网页草稿 vs
   channel peer），让用户观看 IM peer 正在驱动的回合。

CLI agent（Claude Code、Codex）**不**被重定位为日常编码聊天；它们仍然是 (a) 让
provider 接缝保持诚实的 test-drive 目标，(b) IM peer 驱动、用户在这里旁观的
会话。**移出范围：** 把 Coffer 当作主力的浏览器内编码聊天；只对那个定位才有意义的
能力保持在范围外，除非未来某个 spec 重开它。

## 再次定位 —— 内置 agent 是内部能力（[ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.zh.md)）

[ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.zh.md)
部分取代了上面的 Vault Console 定位。`builtin`「Coffer Assistant」**退出聊天人格**：
它不再是注册的聊天 agent，并从 agent 选择器中移除。聊天**只**与 Coffer 受管 agent
（`claude_code`、`codex`，及将来的受管 agent）对话，界面从 _Vault Console（金库控制
台）_ 改回 **Chat（聊天）**。"通过内置 agent 与金库对话"这一职责被去掉；本地模型重塑
为**仅内部**能力，只能通过 `coffer__*` MCP 工具触达——即对 `coffer__search_tools` 的
语义升级，与一个对知识/记忆的新 `coffer__ask` agentic-RAG 工具（见 ADR-024）。**观测
channel 驱动会话**这一职责（ADR-021 职责 2）原样存续，走同一套
`ConversationPort` / `TurnPort` 接缝。

下文用户故事、验收场景与功能需求中仍把内置 agent 描述为可选聊天 agent 的部分（它的
model 选择器、它在聊天里的金库工具调用、对它的 `coffer chat`），应读作 ADR-024 从聊天
面移除的历史已交付行为；LLM/agentic-loop 机器保留但被重塑到 `coffer__ask` 之后，而非
作为聊天人格呈现给用户。

## 再次定位 —— 单属主实时镜像（[ADR-031](../../docs/decisions/ADR-031-chat-single-owner-live-mirror.zh.md)）

[ADR-031](../../docs/decisions/ADR-031-chat-single-owner-live-mirror.zh.md) 把本界面
锁定到一个不可替代的职责，并把 ADR-021 职责 2 从*观测***收窄**为*观测 + 中断 +
注入*。因为 Coffer 的 channel 是 **owner-paired（属主配对）** 的，"IM peer"就是手机
上的**同一个属主** —— 所以聊天是**属主同样从 IM 驱动的那些会话的桌面界面**：一个
属主、一条会话时间线、两块屏幕、一个底层 agent session。在桌面上属主可以实时**观测**
任何会话（包括从手机发起的回合，逐 token）、**中断**一个正在运行的回合，并通过自由
输入来**注入/继续** —— 消息**排队**，永不阻塞。没有多人模型。

由此衍生三个结构性动作，refine 下文需求：

1. **一条实时会话总线。** 回合事件被发布到一个每会话的 broadcaster（带一个用于回放
   的环形缓冲区），任何界面通过 `GET /conversations/{id}/events` 订阅它；
   `POST .../messages` 变为 fire-and-return（发后即返）。这是唯一的新能力 —— 三者
   中真正缺失的只有观测（FR-018 → FR-019b）。
2. **自由发送；一个 FIFO 待处理队列。** composer 永不锁定；一条超发的消息入队并按
   序处理（修订 FR-018）。
3. **折叠 origin。** 网页/channel 二分坍缩为一个会话模型；`channel_name`/
   `peer_chat_id` 作为一个可选的 `channel_binding`（回邮地址）存续；`origin`/
   `peer_display_name` 被去掉（修订 FR-034）。

下文用户故事、验收场景与 FR 中仍描述回合期间 composer 锁定，或描述一个 `origin`/
`peer` 字段的部分，应读作被此处的 ADR-031 措辞与下文修订后的 FR 取代。

## 再次定位 —— 受管 agent 的按对话模型就是它自己的模型（[ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.zh.md) → [ADR-032](../../docs/decisions/ADR-032-provider-switching.zh.md)）

[ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.zh.md)
退役了内置聊天人格，这**重新奠定**了按对话的模型覆盖（FR-025/FR-026、用户故事 8）。
对一个受管 agent，对话的模型**不是**一个 Coffer 注册的 `Model`（`Conversation.model_id`
注册表列）：它是该 agent **自己**的模型，以自由文本 `agent_config.model` 承载，并透传给
agent 的 CLI（Claude Code `--model`、Codex `model`），与 channel `/model` 命令今天所做的
完全一致。Coffer 不校验该名字 —— 坏模型名由 agent 的 CLI 在下一回合自行报错。

两层，一个覆盖：

1. **全局默认。** Provider Switching（[ADR-032](../../docs/decisions/ADR-032-provider-switching.zh.md)、spec 011）
   把 active provider profile 的 `model`（对 Claude，还有 `fast_model`）投影进 agent 的原生
   配置。这是对话未覆盖模型时回合所跑的模型。
2. **按对话覆盖。** `agent_config.model` 作为一个显式的 per-turn 选项传入，CLI 会用它压过
   配置默认。**空**的按对话模型继承全局默认；设置它只覆盖该对话的后续回合，并保留该对话
   的其余 agent 配置（`cwd`、`session_id`）。

`Conversation.model_id`（FR-026 的 `Model` 注册表覆盖）**不被受管 agent 的回合路径读取**
—— 两个受管 provider 都从 `agent_config.model` 构建其 adapter，从不读 `model_id`。它仍是
Coffer 内部引擎模型的注册表（设置 → 模型），且**不在**聊天模型选择器范围内；重接线或退役
它是另一件事（见 Non-Goals）。

Web Chat 界面 MUST 让属主在**开始**一个对话时（draft，紧邻 agent 选择器）与
**对话进行中**（agent bar）都能设置 `agent_config.model`，镜像 `/model`。该控件是一个
自由文本 combobox，带**尽力而为**的建议 —— 来自该 agent 的 active provider profile 的
`model`/`fast_model`（[ADR-032](../../docs/decisions/ADR-032-provider-switching.zh.md)），
并由 provider 模型 introspection 尽力增补 —— 空值则继承全局默认。

下文 FR-025/FR-026、用户故事 8 与"模型选择被记录"场景中描述内置 agent 的 Coffer 注册
`Model`（`model_id`）覆盖之处，应读作在此被重新定位：对受管 agent，按对话模型即
`agent_config.model`，由下文 FR-026a/FR-026b 规范。

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
- composer 在一个回合流式输出时保持可用；一条在回合期间发送的消息入队而非被拒绝
  （[ADR-031](../../docs/decisions/ADR-031-chat-single-owner-live-mirror.zh.md)，取代原先的 composer 锁定）
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
- **对话长于模型上下文窗口**：内置 agent 发送适配进一个上下文预算（由一个字符
  预算近似，约 4 字符/token）的最近历史；较旧的回合带一个标记从模型输入中省略，
  而完整对话仍被存储。
- **在一个回合流式输出时发送第二条消息**：被接受并在待处理队列上入队（composer 永不
  锁定）；它在当前回合结束后作为它自己的回合运行（FR-018/FR-018a）。中断则改为暂停
  队列（FR-018b）。
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
- **When** 用户发送一条消息并订阅该对话的事件流，
- **Then** 助手回复在该订阅上增量地流式输出、完成，并作为该对话上的一条消息被持久化。

### 场景：观测一个从另一界面发起的回合

- **Given** 一个已有一个回合在飞的对话（例如从 IM channel 发起），
- **When** 一个客户端订阅 `GET /conversations/{id}/events`，
- **Then** 该在飞回合迄今的事件被回放、然后实时流式直到完成，而该客户端并未发起
  该回合。

### 场景：一条排队消息在当前回合之后运行

- **Given** 一个回合在飞，
- **When** 用户发送第二条消息，
- **Then** 它被接受（而非拒绝）、作为一个待处理项保留，并在该在飞回合结束后作为它
  自己的回合运行。

### 场景：中断一个回合暂停待处理队列

- **Given** 一个回合在飞，且有一条或多条待处理消息已排队，
- **When** 用户中断该回合，
- **Then** 当前回合停止并保留其部分输出，待处理消息被保留（不自动运行），直到属主
  恢复或丢弃它们。

### 场景：回复在重启后保留

- **Given** 一个带一条已完成助手回复的对话，
- **When** 守护进程重启且用户重新打开该对话，
- **Then** 每条消息都存在且未改变。

### 场景：skills 作为工具可触达

- **Given** vault 中至少一个有效的 skill，
- **When** agent 列出可用工具，
- **Then** `coffer__list_skills` 与 `coffer__load_skill` 存在，且
  `coffer__load_skill` 返回该 skill 的内容。

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

### 场景：在一个流式回合期间第二条消息入队

- **Given** 一个回合正在流式输出，
- **When** 用户在同一对话中发送另一条消息，
- **Then** 该消息被接受并入队（composer 不锁定），并在当前回合结束后作为它自己的
  回合运行。

### 场景：编辑一条排队消息使其重新入队到队尾

- **Given** 一个流式回合后排着一条或多条消息，按一行一条展示，
- **When** 用户编辑某条排队消息，
- **Then** 该消息被从队列取出并载回 composer 以修改，重新发送后入队到待处理队列的
  队尾。

### 场景：模型选择被记录

- **Given** 两个配置好的模型，
- **When** 用户设置一个对话的模型并发送一条消息，
- **Then** 回合运行在所选模型上且助手消息记录产生它的模型。

### 场景：按对话设置一个受管 agent 的模型

- **Given** 一个带受管 agent 与一个 active provider profile 的对话，
- **When** 属主把对话的 agent 模型设为一个自由文本 id（从 draft 或 agent bar），
- **Then** 该值被持久化为 `agent_config.model`，对话的 `cwd` 与 `session_id` 被保留，
  且后续回合把该模型传给 agent 的 CLI；清空它则回退到 provider profile 投影的默认。

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

### 场景：channel 驱动的会话可从控制台观测

- **Given** 一个带有 channel binding 的会话（属主正从一个 IM channel 驱动它），
- **When** 用户打开 Chat，
- **Then** 该会话带着它的 channel binding 标记出现，且它的回合在订阅上流式输出与一个
  网页发起的回合相同的回合事件。

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
  是自包含的：仅给定对话历史，它产出一个类型化回合事件的流。adapter
  携带它自己的模型、工具与配置；orchestrator MUST NOT 注入它们。平台在此接缝背后
  交付三个 agent —— 内置 agent 加两个 CLI 支持的 agent（Claude Code、Codex）——
  因此接缝由真实的额外 provider 验证，而非一个单一占用者。
- **FR-005a**：System MUST 交付面向 Claude Code 与 Codex 的子进程支持的 agent provider。
  每个在一个工作目录（其 `agent_config.cwd`）中运行。当某个回合未提供 cwd 时，
  provider MUST 默认回落到 Coffer 托管的工作目录 `~/.coffer/workspace`（首次使用时
  创建），而不是拒绝该回合——这样聊天草稿（无每回合目录选择器）与未配置 workspace
  的渠道都能开箱即用。一个显式提供的 cwd MUST 是一个存在的目录，否则配置被拒绝。
  一个 CLI agent 的可用性 MUST 反映其命令行二进制是否可在
  守护进程的 PATH 上解析；一个不可用的 agent 被列出但不可选。一个 CLI 回合 MUST
  在该目录中运行该工具、把它的行分隔 JSON 输出流式映射到平台的回合事件，并持久化
  上游 session id 以便下一个回合延续同一 session。Claude Code 通过 Claude Agent
  SDK 驱动，Codex 通过 `codex app-server`（stdio 上的 JSON-RPC 2.0，NDJSON 帧）
  驱动；两者都以完整权限运行（owner-pairing 是安全闸门）。

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

**回合生命周期：流式、中断**

- **FR-018**：System MUST 每个对话最多处理一个进行中回合，但 MUST NOT 拒绝一条在
  某个回合运行时发送的消息（修订原先的拒绝并锁定规则，[ADR-031](../../docs/decisions/ADR-031-chat-single-owner-live-mirror.zh.md)）。
  一条在某个回合期间发送的消息被**入队**到一个每对话的**待处理队列**；composer
  永不锁定。
- **FR-018a**：当进行中回合结束时，System MUST 把待处理队列的队首出队、把它提交为
  对话的下一条用户消息，并运行它的回合 —— 顺序 FIFO，每条排队消息一个回合（不
  合并）。一条待处理消息在它的回合开始前**不**被提交到消息序列；它以一个可移除的
  待处理项呈现，属主可以在它运行前丢弃它。待处理队列在内存中；它在该会话上任何回合结束
  后自动推进（包括一个 IM 驱动的回合），所以一条排在手机发起回合之后的桌面消息，会在那个
  回合完成时仍然运行。（一条在回合在飞时从某个 IM channel 到达的消息，由 channel 自己的
  入站缓冲——Spec 009——持有，而非这个队列；v1 不把两者合并为一个物理 FIFO。）一次守护
  进程重启会丢弃尚未提交的待处理消息。
- **FR-018b**：中断一个回合（FR-021）MUST 也**暂停**待处理队列：当前回合停止并保留
  其部分输出，排队的消息被保留（不自动运行），直到属主恢复或丢弃它们。
- **FR-019**：System MUST 把一个回合表达为一个类型化事件序列，至少覆盖回合开始、
  文本增量、工具调用、工具结果、回合完成、回合错误，与**待处理队列变更**
  （`queue_changed`，携带有序的待处理项，让每个订阅者渲染相同的待处理状态）。
- **FR-019a**：System MUST 在 `GET /conversations/{id}/events`（SSE）暴露一个每对话
  的**实时事件订阅**，任意数量的客户端都可挂接它。挂接时，若一个回合在飞，它 MUST
  回放当前回合的事件（让一个迟到的订阅者 —— 例如回合中途打开的桌面，或观看一个手机
  发起的回合 —— 赶上进度），然后实时流式；当没有回合在飞时，它 MUST 保持连接打开，
  并在下一个回合无论从哪个界面启动时投递它的事件。
- **FR-019b**：`POST /conversations/{id}/messages` MUST 发起（或入队）一个回合并
  立即返回（fire-and-return）；它 MUST NOT 是事件流。所有回合事件消费都流经 FR-019a
  订阅（单一事件路径），因此观测一个客户端自己发起的回合与观测另一个界面发起的回合
  走同一段代码。
- **FR-019c**：System MUST 在 `PUT /conversations/{id}/pending` 暴露待处理队列以供
  管理，它替换有序的待处理文本（一个原语覆盖恢复、丢弃与重排序）：该替换会取消暂停
  队列并在没有回合在飞时启动下一个回合，并向所有订阅者广播 `queue_changed`。
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
- **FR-026a**：对一个**受管 agent**，对话的模型覆盖 MUST 是该 agent 自己的模型，以
  自由文本 `agent_config.model` 承载并透传给 agent 的 CLI（而非一个 Coffer 注册的
  `Model`/`model_id`）。设置它 MUST 保留对话的其余 agent 配置（`cwd`、`session_id`）
  且只影响后续回合；空值 MUST 继承 Provider Switching（[ADR-032](../../docs/decisions/ADR-032-provider-switching.zh.md)）
  投影进 agent 原生配置的全局默认。受管 agent 的回合路径 MUST NOT 读取
  `Conversation.model_id`。
- **FR-026b**：REST API MUST 暴露读取与设置一个对话的 `agent_config.model`，且创建
  对话 MUST 接受一个初始 `agent_config.model`。GUI MUST 在开始对话时（紧邻 agent
  picker）与对话进行中都呈现它，作为一个自由文本 combobox，其尽力而为的建议来自该
  agent 的 active provider profile 的 `model`/`fast_model`，并由 provider 模型
  introspection 尽力增补（FR-030 REST 对等）。

**界面**

- **FR-027**：System MUST 在桌面应用中提供一个 Chat 页面：一个可折叠的对话历史
  列表、一个带 agent picker 与一个每 agent 配置区域的新对话对话框、一个带流式
  文本的消息线索（由 FR-019a 实时订阅驱动，而非轮询）、内联可展开工具调用卡片、
  一个模型选择器、一个随多行输入**自适应增高**（封顶后框内滚动）且**永不锁定**的
  composer（一条在某个回合期间发送的消息入队并按一行一条渲染为可移除、可编辑的
  待处理项；编辑会把它载回 composer 并重新入队到队尾，FR-018/FR-018a），以及一个
  用于进行中回合的停止控制。
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

**Chat 界面：channel binding（[ADR-021](../../docs/decisions/ADR-021-chat-as-vault-console.zh.md) → [ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.zh.md) → [ADR-031](../../docs/decisions/ADR-031-chat-single-owner-live-mirror.zh.md)）**

- **FR-033**：Chat 界面（标签为 **Chat（聊天）**，按 [ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.zh.md)
  从 _Vault Console_ 改回）MUST **只**与 Coffer 受管 agent 对话，并 MUST 让属主实时
  观测、中断与继续任何会话，包括属主从一个 IM channel 驱动的那些
  （[ADR-031](../../docs/decisions/ADR-031-chat-single-owner-live-mirror.zh.md)）。
  `builtin` agent MUST NOT 作为聊天 agent 提供；其模型是仅内部能力，只能通过
  `coffer__*` 工具触达（ADR-024），而非聊天人格。Chat 界面 MUST NOT 把自己定位为
  主力的浏览器内编码聊天。
- **FR-034**：一个会话 MAY 携带一个可选的 **channel binding**（`channel_name` +
  `peer_chat_id`）—— 把 agent 输出转发回 IM 应用的回邮地址。会话历史 MUST 呈现一个
  会话是否有一个 channel binding（一个会话"有一个 binding"当且仅当 `channel_name`
  被设置）以及它是哪个 channel。原先的 `origin`（网页 vs channel）与
  `peer_display_name` 字段被移除（[ADR-031](../../docs/decisions/ADR-031-chat-single-owner-live-mirror.zh.md)）：
  在单属主前提下 peer 永远是属主，所以没有单独的 peer 身份要显示。

### 关键实体

- **Agent Provider**：平台的扩展单元。一个 provider 拥有一个 agent 类型：它有一个
  稳定的 `agent_key`，在对话创建时校验并存储一个对话的 agent 特定配置，为每个回合
  构建一个配置好的 agent adapter，在删除时拆除每对话状态，并报告它当前是否可用。
  provider 被持于 **agent-provider 注册表** 中；聊天界面只知道注册表。
- **Agent Adapter**：一个 agent 对一个回合的处理。给定对话历史，
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
- **Agent Event**：一个流式回合中的一个类型化事件 —— 回合开始、文本增量、工具调用、
  工具结果、回合完成、回合错误，或待处理队列变更（`queue_changed`，会话级的待处理队列
  快照，[ADR-031](../../docs/decisions/ADR-031-chat-single-owner-live-mirror.zh.md)）。

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
- 交互模型是顺序的：每个对话同一时间一个回合。回合运行时 composer **不**锁定 ——
  回合期间发送的消息会被入队，并在该回合之后运行（FR-018，[ADR-031](../../docs/decisions/ADR-031-chat-single-owner-live-mirror.md)）。
  一个对话内的并发（重叠）回合不在范围内。
- agent-provider 注册表在启动时由代码填充；v1 注册一个 provider（内置 agent）。
  注册表是接缝 —— 从用户管理的配置填充它不在本规格内。
- 以下被明确**列为不在范围**：用户创建或用户编辑的 agent；一个管理 agent 注册表的
  GUI；超出 gateway 现有门控的每 agent 能力作用域；对话摘要与导出；过去
  外部 agent 会话的恢复/继续；以及任何跨 agent 的原始 transcript 浏览/搜索界面（跨
  agent 的共享由蒸馏后的 memory 承担，[ADR-020](../../docs/decisions/ADR-020-transcript-distillation.zh.md)）。
  远程通道由 Spec 009 单独交付。
- 把受管 agent 的回合路径重接线去读 `Conversation.model_id`、以及为聊天退役该注册表
  覆盖，均**不在范围内**：按对话模型选择器只面向 `agent_config.model`（见上文按对话模型
  的重新定位）。`model_id` 仍是设置 → 模型的内部引擎注册表。
