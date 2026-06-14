# 功能规格：Channels

> English: [spec.md](./spec.md)

**Feature Branch**: `feature/channels`
**Created**: 2026-06-12
**Status**: Accepted
**Input**: 用户描述: "Coffer needs messaging channels — Telegram and
SeaTalk first — so the owner can talk to any agent on the chat platform from
the IM apps they already use, approve tool calls without leaving the chat, and
receive notifications pushed by Coffer. The architecture must stay uniform:
more channels and more agents will be added, so a new channel never touches
agent code and a new agent never touches channel code."

channel 是一种已注册的资源（`channel:<name>`），它把一个 IM 账号接到
Coffer 的聊天平台（spec 008）。来自已配对 owner 的消息成为一段普通对话
(conversation) 中的 turn；agent 的回复送回 IM 聊天。channel 层与 agent 层
只在聊天平台既有的接缝处相遇 —— 对话创建、turn 事件流、审批门 (approval
gate) —— 因此 N 个 channel 与 M 个 agent 的成本是 N + M，而永远不是
N × M。

> **注（[ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.zh.md)）。**
> 下文把 `builtin` agent 当作可路由 channel 目标的提及，反映的是本 spec 落地时已交付的
> 行为。ADR-024 让内置 agent 退出聊天人格，因此 channel **只**路由到**受管** agent
> （Claude Code、Codex……）；内置模型现在是内部 `coffer__*` 能力，而非聊天目标。channel
> 旁观/审批在共享接缝上的机制不变。

## User Scenarios & Testing

### User Story 1 — Register a channel (Priority: P1)

用户用 BotFather 创建一个 Telegram bot（或在 SeaTalk Open Platform 上创建
一个 SeaTalk app），把它的 secret 存进 Coffer 的凭据存储 (credential
store)，再注册一个引用它的 channel 资源。该 channel 连同启用状态出现在
Channels 页面和 CLI 中；凭据引用无法解析的 channel 会被校验拒绝。

**Why this priority**: 在 channel 存在之前，其余一切都无从谈起。注册同时
也端到端验证了与资源框架的集成（生命周期、审计、凭据探测）。

**Independent Test**: 在某个凭据 ref 下存入一个 bot token，注册指向它的
`channel:my-telegram`，确认它在 REST、CLI 与 Channels 页面中均可见；再用
一个悬空 (dangling) 的 ref 尝试注册，确认被拒绝且没有任何行被持久化。

**Covering scenarios**:

- register a telegram channel
- reject a channel with a missing credential
- register and list channels from the command line

---

### User Story 2 — Pair the owner (Priority: P1)

Coffer 是单用户的 vault，因此每个 channel 只听命于一个人。用户向 Coffer
索取一个配对码 (pairing code)（UI 按钮或 CLI），用自己的 IM 账号把这串码
发给 bot，该账号就成为 channel 的 owner。其他任何人的消息都被静默忽略
—— bot 永远不会向陌生人暴露自己的存在。重新签发配对码并再次配对，会把
channel 重新绑定到新的发送者。

**Why this priority**: 配对是安全边界。一个接在个人 vault 上、可被触达的
bot，必须在任何消息流动之前就 fail closed。

**Independent Test**: 签发一个配对码，从一个伪造的 IM 账号发送它，观察到
确认回复且 peer 被记录；再从第二个账号发消息，观察到既没有回复也没有
turn 启动。

**Covering scenarios**:

- issue a pairing code
- pair by sending the code
- ignore messages from strangers
- an expired or wrong code does not pair

---

### User Story 3 — Chat with an agent from the IM app (Priority: P1)

已配对的 owner 给 bot 发一条文本消息。channel 把它路由进该 peer 的长生命
周期对话 —— 首次接触时用 channel 配置的默认 agent 创建 —— agent 的回复
回到 IM 聊天，按该平台渲染（Telegram HTML、SeaTalk Markdown），过长时
分块 (chunk)。在 Telegram 上，bot 会在 turn 运行期间展示进度，并把工具
活动流式写进一条可编辑的状态消息；在无法编辑消息的 SeaTalk 上，bot 用
typing indicator 表示已收到，并发送完成后的回复。同一段对话在 Chat 页面
可见，带完整历史。

**Why this priority**: 这就是产品本身：vault 里的 agent，从用户本就常驻的
IM 应用里即可触达。

**Independent Test**: 在已配对、agent 为脚本化 (scripted) 的 channel 上发送
"hello"，在该 turn 内于伪造 IM 中观察到回复，且同一轮交换能通过聊天平台
的 REST API 看到。

**Covering scenarios**:

- a paired message gets an agent reply
- the channel conversation is a normal chat conversation
- a long reply is chunked for the platform
- markdown rendering degrades by channel capability
- a turn error is reported to the IM chat

---

### User Story 4 — Control the conversation with commands (Priority: P2)

owner 不必离开 IM 应用就能管理对话：`/new` 用 channel 的默认 agent 开启
一段全新对话，`/stop` 打断正在运行的 turn，`/status` 报告当前活跃的对话、
agent 与 turn 状态，`/help` 列出命令。turn 运行期间发来的消息会排队并按序
应答；队列有界，溢出会被告知。

**Why this priority**: 没有 `/new` 和 `/stop`，那条单一的长生命周期对话就
会变成陷阱；排队让并发输入变得可预期。

**Independent Test**: 启动一个缓慢的脚本化 turn，发送 `/stop`，观察 turn 以
interrupted 结束；发送 `/new`，观察为该 peer 记录了一段新对话；在 turn
期间灌入大量消息，观察排队执行以及溢出提示。

**Covering scenarios**:

- /new starts a fresh conversation
- /stop interrupts a running turn
- messages during a turn are queued in order
- the queue is bounded and overflow is reported

---

### User Story 5 — Approve a tool call from the IM app (Priority: P2)

当 agent 为等待人工审批而暂停 turn 时，channel 会把该请求投递为交互式
提示 —— Telegram 上是内联的 Approve/Deny 按钮，SeaTalk 上是交互式卡片。
owner 的点按会像在 web UI 里点击一样解决平台的审批门，提示消息也会被
更新以显示决定。非 owner 的点按一律被忽略。

**Why this priority**: 聊天平台带有审批能力；一个无法应答审批的 channel
会让任何用到它的 agent 静默挂起。

**Independent Test**: 用一个会请求审批的脚本化 agent 跑一个 turn，点击伪造
IM 的 Approve 按钮，观察决定送达 agent 且提示被更新；再用 Deny 重复一遍。

**Covering scenarios**:

- an approval prompt is answered from the IM chat
- a denied approval is delivered to the agent

---

### User Story 6 — Receive notifications (Priority: P2)

Coffer 可以在没有任何入站消息的情况下，向 channel 的已配对 owner 推送
消息：`coffer channel notify my-telegram "build finished"` 或对应的 REST
调用会把文本投递到 IM 聊天。这是出站方向的地基 —— 未来任何想提醒用户的
功能都复用它。

**Why this priority**: 通知是 channel 存在意义的一半，而这个接缝（channel
service 上的 notify 入口）必须现在就被验证。

**Independent Test**: 在已配对的 channel 上分别经 CLI 和 REST 调用 notify，
在伪造 IM 中看到消息；再在未配对的 channel 上调用，得到一个干净的报错。

**Covering scenarios**:

- notify delivers to the paired owner
- notify on an unpaired channel fails cleanly

---

### User Story 7 — SeaTalk reaches the local daemon (Priority: P2)

SeaTalk 只通过 webhook 投递事件，因此 Coffer 自带一个回调监听器 (callback
listener)：一个独立的小进程，在任何 SeaTalk channel 处于启用状态时由
daemon 拉起，只在一个本地端口上服务带签名的回调路径。用户把一条隧道
(tunnel)（cloudflared、ngrok）指向该端口，并在 SeaTalk Open Platform 上
登记公网 URL。监听器应答平台的验证握手，校验每个事件的签名，并把合法
事件经 loopback 转发给 daemon。签名不合法的事件被拒绝，永远到不了
daemon。

**Why this priority**: 没有 ingress 就完全没有 SeaTalk 入站。「独立进程」
这一形态是章程对公网可达 surface 的硬性要求。

**Independent Test**: 用已知的签名 secret 启动监听器，POST 验证 challenge
并看到它被回显；POST 一个签名正确的事件并看到它被转发；POST 一个被篡改
的事件并看到 401 且什么都没被转发。

**Covering scenarios**:

- the callback listener answers the verification handshake
- a signed seatalk event reaches the channel
- a tampered seatalk event is rejected
- the listener runs only while a seatalk channel is enabled

---

### User Story 8 — Operate channels day to day (Priority: P3)

停用 (disable) 一个 channel 会停止它的 adapter（轮询停止、事件被拒收）；
启用则重新拉起；删除 channel 会停止 adapter 并移除其 peer 绑定。Channels
页面和 `coffer channel status` 会显示 adapter 是否在运行、谁已配对，以及
—— 对 SeaTalk —— 隧道应当指向的回调端口和路径。

**Why this priority**: 生命周期的诚实（如实反映的 status、真正切断流量的
disable）是这个 feature 可运维的根基。

**Covering scenarios**:

- disable stops the adapter and enable restarts it
- deleting a channel cleans up its runtime and peer
- channel status reports runtime, pairing, and callback details

---

### User Story 9 — 从 chat 切换 agent、workspace 与 model（优先级：P2）

owner 不离开 IM app 就能操控入口。`/agent codex` 把会话切到 Codex；`/cwd
my-project` 把编码 agent 指向一个预授权 workspace；`/model opus` 改 model。切换
agent 或 workspace 会开一个 pin 到新选择的新会话（这两者对会话终身固定），且
选择对后续消息与 `/new` 粘性保留；切换 model 在同会话下条 turn 生效。每个命令
无参时报告当前值与可选项。owner 只能挑 operator 预先定义的 workspace——消息里
的裸文件路径从不被采纳。

**为何此优先级**：channel 是入口*管理者*，不是一根固定线。路由到所选 agent、在
所选安全目录里、用所选 model，才让一个已配对的 chat 成为通往 vault 暴露的每个
agent 的交换机——而 workspace allowlist 是那道边界，防止可远程触达的入口把 agent
指向任意目录。

**Independent Test**：用一个已配对 channel 和两个脚本化 provider，发
`/agent <second>` 观察一个 pin 到它的新会话且下条消息由它回答；为已配置
workspace 发 `/cwd <name>` 观察在该目录建的新会话；发 `/cwd /etc` 观察被拒；发
`/model <name>` 观察下条 turn 用它。

**Covering scenarios**:

- /agent switches the agent and sticks
- /agent rejects an unknown agent
- /cwd selects a configured workspace and refuses a bare path
- /model switches the model for the next turn

---

### User Story 10 — 知道谁驱动了什么、以及一个 turn 何时完成（优先级：P2）

因为入口可远程触达，channel 消息驱动的每个 turn、owner 从 chat 回答的每个审批，
都连同 channel、peer、agent 记入审计日志——回答「谁经哪个 channel 驱动了哪个
agent、批准了什么」。又因为某些平台不能编辑消息、长桥接 turn 运行期间什么都不
显示，每个 turn 都以一条推到 chat 的紧凑摘要收尾：done + 工具数、耗时、token，
或错误，或停止。

**为何此优先级**：入口管理者的两个无人认领的差异化点是一等 auth/审计与可靠的
完成信号；二者必须在每个 channel 上为真，包括沉默的那些。

**Independent Test**：从已配对 channel 驱动一个 turn，观察一条带 channel、peer、
agent 的 turn-started 审计记录；回答一个审批提示，观察一条 approval-resolved
审计记录；在不能编辑消息的 channel 上观察 turn 后的完成摘要消息。

**Covering scenarios**:

- a channel-driven turn is audited with channel, peer, and agent
- an approval resolved from chat is audited
- a completion summary is sent after every turn
- a group member who is not the paired sender is ignored

---

### Edge Cases

- 一条恰好在上一个 turn 结束瞬间到达的消息会进入队列，而不是制造竞态：
  同一对话的 turn 永不重叠（平台保证）。
- IM 平台拒收带格式的消息 → channel 先用纯文本重试同一内容，之后才报告
  失败。
- daemon 在 turn 进行中重启 → 平台的启动清扫 (startup sweep) 把孤儿 turn
  标记为 failed；channel 对话在下一条消息上自然继续。
- 配对码过期（1 小时）或被反复猜错 → 该码作废；必须重新签发一个新码。
- 活跃对话在 Chat 页面被删除 → peer 的下一条消息会用默认 agent 创建一段
  新对话。
- Telegram long polling 失去连接 → adapter 指数退避后恢复；重连后没有任何
  入站消息被重复处理（update offset 只在分发完成后提交）。
- SeaTalk 发送端被限流（HTTP 429）→ 出站发送退避并重试。
- 非文本的入站内容（图片、文件、语音）→ channel 回复说明本版本只支持
  文本。

## Requirements

### Functional Requirements

- **FR-001**: 存在一个 `channel` resource kind，带按类型区分的配置
  （Telegram：bot token 引用；SeaTalk：app id、app secret 引用、签名
  secret 引用）、一个默认 agent key，以及可选的默认 agent 配置。secret
  只存在于凭据存储；配置里只放引用，引用在注册时被探测。
- **FR-002**: channel 的生命周期（register、enable、disable、update、
  delete）搭乘通用资源框架，每次状态变迁都有审计。
- **FR-003**: 配对：daemon 为每个 channel 签发一个 8 字符的一次性配对码
  （无歧义字母表、1 小时 TTL、有界的猜错次数）；内容恰为该码的消息会把
  其发送者绑定为该 channel 的唯一 peer，并替换任何先前的 peer；其他所有
  发送者都被静默忽略。
- **FR-004**: 来自已配对 peer 的入站文本路由到该 peer 的活跃对话，首次
  使用时经聊天平台标准的对话创建路径创建（默认 agent 由 agent registry
  校验）。channel 层只通过聊天平台的接缝触达 agent：conversation
  service、turn orchestrator、approval gate。
- **FR-005**: 回复按 channel 能力渲染：Telegram 把 markdown 转成 Telegram
  HTML（带纯文本回退），按段落边界以 4000 字符分块，并把工具进度以节流
  方式流式写入一条可编辑的状态消息；SeaTalk 发送 markdown，按 4096 字节
  分块，用 typing indicator 表示进行中。能力由 adapter 声明，内核不做
  特判。
- **FR-006**: `/new`、`/stop`、`/status`、`/help` 命令在任何已配对的聊天里
  可用。`/stop` 与 `/new` 即使在 turn 运行中也立即生效；其他消息排队
  （FIFO，上限 10）并按序运行。
- **FR-007**: turn 流中的 `approval_request` 事件变成一条交互式提示
  （Telegram 内联按钮、SeaTalk 交互式卡片）；owner 的响应解决平台审批
  门；提示随结果更新；非 owner 的点按被忽略。
- **FR-008**: 一个 notify 入口（REST + CLI）把任意文本投递给 channel 的
  已配对 peer，与任何对话无关。
- **FR-009**: SeaTalk 回调监听器是只服务 `POST /seatalk/{channel}` 的独立
  进程：它用回显的 challenge 应答 `event_verification`，校验
  `sha256(body + signing_secret)` 签名，把合法事件携带 daemon token 经
  loopback 转发给 daemon，并拒绝其他一切。daemon 在至少一个 SeaTalk
  channel 处于启用状态时拉起它，否则停止它。
- **FR-010**: Telegram 入站使用 long polling，update offset 只在分发完成后
  提交；adapter 以指数退避重连，且永不让 daemon 崩溃。
- **FR-011**: Channels 页面列出 channel、注册新 channel（secret 经凭据存储
  保存）、显示状态（adapter 运行中、已配对 peer、回调端点）、签发配对
  码、切换启用/停用。CLI 对等：`coffer channel list / register / pair /
status / notify`。
- **FR-012**: channel 事件都被审计：配对码签发、配对完成、通知已发送
  —— 与自动的资源生命周期审计并列。
- **FR-013**: owner 从 chat 切换会话的 agent。`/agent` 无参时报告当前 agent
  与注册表里可选的 agent key；`/agent <key>` 对 agent 注册表校验该 key，成功后
  把它记为 peer 的粘性首选并开一个 pin 到它的新会话（已存在会话的 agent 不可
  改），此后的消息与 `/new` 都用所选 agent，直到再次切换。未知 key 被拒绝并
  列出合法 keys；不为任何 agent 增加 channel 侧代码。
- **FR-014**: owner gate 校验发送者身份，而非只看会话身份。每条 inbound 信封
  携带 `sender_id`（Telegram `from.id`、SeaTalk `employee_code`）；pairing 把它
  记到 peer，一条 inbound 消息只有在 `chat_id` 匹配且（当 peer 有已存
  `sender_id` 时）发送者匹配时才被接受。本要求之前配对的 peer（无已存
  `sender_id`）退化为 chat-id-only 闸。在 FR-012 之外审计两个 channel 驱动事件：
  一条 inbound 消息驱动的 turn（channel、peer、agent、conversation），与从 chat
  解决的审批（channel、peer、工具、决定）。
- **FR-015**: 每个 turn 后，channel 发一条紧凑的完成摘要作为新消息，与消息
  编辑能力无关：成功时报告 done 标记 + 工具数、耗时、token 用量；失败的 turn
  报告错误；被中断的 turn 报告停止。在不能编辑消息、且长桥接 turn 运行期间什么
  都不显示的平台上，这就是 turn 结束信号。
- **FR-016**: 一个 channel 声明一组命名 workspace（`{name, path}`），注册时各
  校验为已存在目录，外加一个可选默认 workspace。`/cwd` 无参时列出 workspaces
  与当前那个；`/cwd <name>` 选一个 workspace 并在其中开一个新会话（会话的工作
  目录不可改），把它记为 peer 的粘性首选。channel 永不接受来自 inbound 消息的
  裸文件路径——workspace 列表是从 channel 选取 agent 工作目录的唯一权威。路由到
  桥接 agent 时用 peer 的粘性 workspace，无则默认 workspace；两者皆无时告知
  owner 未配置 workspace。builtin agent 不需要 workspace。
- **FR-017**: owner 从 chat 切换 model。`/model` 无参时报告当前 model；
  `/model <name>` 对 builtin agent 把名字对 model registry 解析并设会话的 model
  覆盖，对桥接 agent 则存原始上游 model 串透传给 CLI。model 切换在同会话下条 turn
  生效（model 每 turn 重读，不同于 agent 与工作目录）。非法 builtin model 对
  registry 校验被拒；坏的桥接 model 串会以 CLI 自己的错误回传到 chat。

### Key Entities

- **Channel** — 资源 `channel:<name>`；config = 类型、凭据 ref、默认
  agent + 配置、命名 workspaces + 可选默认 workspace。
- **ChannelPeer** — channel 的已配对 owner：`(resource, chat_id)`、显示
  名、配对时间、指向活跃对话的指针、已配对发送者身份（`sender_id`），以及
  粘性首选（所选 agent 与 workspace）。目前每个 channel 一个；以 chat 为键，
  使群聊将来可以直接成为新的 peer 行而无需改 schema。
- **Workspace** — channel 上一个命名、预授权的工作目录（`{name, path}`）；从
  该 channel 选取 agent 运行目录时的 allowlist。裸路径从不被 chat 接受。
- **InboundMessage / OutboundMessage** — 每个 adapter 生产与消费的规范化
  信封 (envelope)；内核永远看不到平台原始载荷。inbound 为 owner gate 携带
  发送者身份（`sender_id`）。
- **ChannelCapabilities** — adapter 声明自己能做什么（编辑消息、交互
  按钮、typing indicator）；内核据此选择渲染与审批策略。
- **PairingCode** — 内存态、一次性、按 channel；从不持久化。

## Success Criteria

### Measurable Outcomes

- **SC-001**: 从全新安装出发，用户按照 quickstart 在 10 分钟内即可注册一个
  Telegram channel、完成配对并得到一条 agent 回复。
- **SC-002**: 陌生人给 bot 发消息产生零可观察响应、零 turn，而 owner 的
  流量不受影响。
- **SC-003**: 新增一个假想的第三种 channel 类型，只需实现一个 adapter +
  一份配置 schema，不触碰任何 agent、对话或审批代码（由测试套件使用的
  test-only 假 channel 演示）。
- **SC-004**: 任何注册在聊天平台上的 agent 都能从任何 channel 触达，
  channel 侧无需任何代码改动（通过在测试里用一个脚本化的第二 provider
  驱动 channel 来演示）。
- **SC-005**: 下方每个 acceptance scenario 至少被一个测试覆盖；
  `make verify` 通过。
- **SC-006**: 从一个已配对 chat，owner 能触达每个已注册 agent，每个都在一个
  所选预授权 workspace 里、用一个所选 model，且一条 chat 消息绝不能把 agent
  指向 operator 未预授权的目录（用驱动两个脚本化 provider 与一次被拒裸路径来
  演示）。
- **SC-007**: 每个 channel 驱动的 turn、每个从 chat 回答的审批，都能按 channel、
  peer、agent 在审计日志里查到；且每个 turn——包括在不能编辑消息的 channel 上
  ——都以一条 chat 里的完成摘要收尾（用不能编辑的假 adapter 来演示）。

## Acceptance Scenarios

### Scenario: register a telegram channel

- **Given** 一个 bot token 已存于某个凭据 ref 下
- **When** 用户以 telegram 类型和该 ref 注册 `channel:tg`
- **Then** 该 channel 连同其配置和启用状态出现在列表中
- **And** 这次注册被审计

### Scenario: reject a channel with a missing credential

- **Given** 被引用的名字下没有存任何凭据
- **When** 用户注册一个指向它的 channel
- **Then** 注册以凭据错误失败，且没有任何东西被持久化

### Scenario: register and list channels from the command line

- **Given** 一个运行中的 daemon 和一条已存的凭据
- **When** 用户运行 `coffer channel register` 与 `coffer channel list`
- **Then** channel 被创建并出现在列表中

### Scenario: issue a pairing code

- **Given** 一个已注册的 channel
- **When** 用户请求一个配对码
- **Then** 返回一个带过期时间的 8 字符码，并被审计

### Scenario: pair by sending the code

- **Given** 一个已签发的配对码
- **When** 某个发送者给 bot 发来恰为该码的消息
- **Then** 该发送者成为 channel 的 peer 并收到确认
- **And** 这次配对被审计，且该码无法再次使用

### Scenario: ignore messages from strangers

- **Given** 一个已配对的 channel
- **When** 另一个账号给 bot 发消息
- **Then** 不发送任何回复，也不创建任何 turn 或对话

### Scenario: an expired or wrong code does not pair

- **Given** 一个已签发的配对码
- **When** 某个发送者反复提交错误猜测，或该码已过期
- **Then** 配对失败，发送者收不到任何回复，且该码作废

### Scenario: a paired message gets an agent reply

- **Given** 一个已配对、默认 agent 可用的 channel
- **When** peer 发送一条文本消息
- **Then** 在该 peer 的对话里运行一个 turn，回复被投递到 IM 聊天

### Scenario: the channel conversation is a normal chat conversation

- **Given** 一段由首次接触创建的 channel 对话
- **When** 用户打开聊天平台的对话 API
- **Then** 这段对话及其消息像任何其他对话一样被列出

### Scenario: a long reply is chunked for the platform

- **Given** 一条超过平台上限的脚本化 agent 回复
- **When** turn 完成
- **Then** 回复按段落边界拆成多条消息、按序到达

### Scenario: markdown rendering degrades by channel capability

- **Given** 同一条 markdown 回复
- **When** 分别经 telegram 和一个不支持富文本的 channel 投递
- **Then** telegram 收到 HTML（被拒收时回退到纯文本），另一个 channel
  收到它声明的格式

### Scenario: a turn error is reported to the IM chat

- **Given** 一个会在 turn 中途失败的脚本化 agent
- **When** peer 发送一条消息
- **Then** IM 聊天收到一条简短的错误提示，且 channel 保持运行

### Scenario: /new starts a fresh conversation

- **Given** 一个已配对、带活跃对话的 channel
- **When** peer 发送 `/new`
- **Then** 一段使用默认 agent 的新对话成为活跃对话，旧对话仍留在历史中

### Scenario: /stop interrupts a running turn

- **Given** 一个进行中的 turn
- **When** peer 发送 `/stop`
- **Then** 该 turn 以 interrupted 结束，聊天恢复响应

### Scenario: messages during a turn are queued in order

- **Given** 一个进行中的 turn
- **When** peer 又发来两条消息
- **Then** 它们在第一个 turn 结束后，按到达顺序作为连续的 turn 运行

### Scenario: the queue is bounded and overflow is reported

- **Given** 一个已满的消息队列
- **When** peer 再发一条消息
- **Then** 这条消息被丢弃，并告知 peer 该 channel 正忙

### Scenario: an approval prompt is answered from the IM chat

- **Given** 一个会请求工具审批的脚本化 agent
- **When** peer 在投递来的提示上点按 Approve
- **Then** 审批门解析为 allow，turn 继续，提示显示出该决定

### Scenario: a denied approval is delivered to the agent

- **Given** 一条待处理的审批提示
- **When** peer 点按 Deny
- **Then** agent 收到 deny 决定，提示显示该结果

### Scenario: notify delivers to the paired owner

- **Given** 一个已配对的 channel
- **When** 分别经 REST 和 CLI 调用 notify
- **Then** 文本两次都到达 IM 聊天，并被审计

### Scenario: notify on an unpaired channel fails cleanly

- **Given** 一个没有已配对 peer 的 channel
- **When** 调用 notify
- **Then** 调用以清晰的错误失败，且什么都没发出

### Scenario: the callback listener answers the verification handshake

- **Given** 一个为某 channel 配置好、运行中的回调监听器
- **When** SeaTalk POST 一条 `event_verification` 回调
- **Then** 监听器以 HTTP 200 回显 challenge

### Scenario: a signed seatalk event reaches the channel

- **Given** 一个用某 channel 的签名 secret 配置的监听器
- **When** POST 一条签名正确的消息事件
- **Then** 它被转发给 daemon 并作为入站消息处理

### Scenario: a tampered seatalk event is rejected

- **Given** 一个运行中的回调监听器
- **When** POST 一条签名不合法的事件
- **Then** 监听器响应 401，且没有任何东西到达 daemon

### Scenario: the listener runs only while a seatalk channel is enabled

- **Given** 一个带有一个已启用 seatalk channel 的 daemon
- **When** 该 channel 被停用
- **Then** 监听器进程停止；再次启用会重新拉起监听器

### Scenario: disable stops the adapter and enable restarts it

- **Given** 一个已启用、adapter 运行中的 telegram channel
- **When** 用户停用又重新启用该 channel
- **Then** 停用期间轮询停止，启用后恢复

### Scenario: deleting a channel cleans up its runtime and peer

- **Given** 一个已启用、已配对的 channel
- **When** 用户删除该 channel 资源
- **Then** adapter 停止，peer 绑定被移除

### Scenario: channel status reports runtime, pairing, and callback details

- **Given** 处于各种状态的 channel
- **When** 用户经 REST 和 CLI 查询 status
- **Then** adapter 运行状态、已配对 peer，以及（对 seatalk）回调端口和
  路径都被准确报告

### Scenario: /agent switches the agent and sticks

- **Given** 一个已配对 channel，并注册了第二个脚本化 agent
- **When** peer 发 `/agent <second>` 然后发一条消息
- **Then** 一个 pin 到第二个 agent 的新会话成为活跃会话，该消息由它回答，且
  `/new` 复用它直到再次切换

### Scenario: /agent rejects an unknown agent

- **Given** 一个已配对 channel
- **When** peer 发 `/agent nope`
- **Then** channel 回复该 agent 未知并列出合法 keys，活跃会话不变

### Scenario: /cwd selects a configured workspace and refuses a bare path

- **Given** 一个配置了名为 `proj` 的 workspace 的已配对 channel
- **When** peer 发 `/cwd proj`
- **Then** 用该 workspace 的目录建一个新会话，且选择粘性保留
- **And** 当 peer 发 `/cwd /etc` 时，channel 拒绝它，不在该目录建任何会话

### Scenario: /model switches the model for the next turn

- **Given** 一个处于活跃会话的已配对 channel
- **When** peer 发 `/model <name>` 然后发一条消息
- **Then** 下条 turn 在同会话里以所选 model 运行

### Scenario: a channel-driven turn is audited with channel, peer, and agent

- **Given** 一个已配对 channel
- **When** peer 发一条驱动 turn 的消息
- **Then** 一条审计记录写下 channel、peer、agent 与 conversation

### Scenario: an approval resolved from chat is audited

- **Given** 一个请求审批的脚本化 agent
- **When** peer 回答审批提示
- **Then** 一条审计记录写下 channel、peer、工具与决定

### Scenario: a completion summary is sent after every turn

- **Given** 一个在不能编辑消息的 adapter 上的已配对 channel
- **When** 一个 turn 完成
- **Then** 一条紧凑完成摘要被发到 chat 报告结果，且失败的 turn 报告错误

### Scenario: a group member who is not the paired sender is ignored

- **Given** 一个带已存发送者身份的已配对 peer
- **When** 一条消息以相同 chat id 但不同 sender id 到达
- **Then** 不发回复，也不启动 turn

## Assumptions

- 用户能创建 Telegram bot（BotFather）和 SeaTalk Open Platform app，并能
  通过其组织的审批流程获得 SeaTalk 的 scope（Send Message to Bot User
  等）。
- 对 SeaTalk，用户自行运行一条隧道（cloudflared、ngrok 或等价物）把公网
  URL 通到本地回调端口；Coffer 在 quickstart 中给出做法，但不管理隧道。
- channel 承载文本对话；富媒体会收到一条礼貌的「只支持文本」回复。
- 内置 agent 今天经 MCP 网关给工具调用把关，因此实时审批提示只出现在
  使用平台审批门的 agent 上；channel 侧的能力用脚本化 provider 验证，
  与 spec 008 验证平台接缝的方式相同。
