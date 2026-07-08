# 功能规格：Channels

> English: [spec.md](./spec.md)

**Feature Branch**: `feature/channels`
**Created**: 2026-06-12
**Status**: Accepted
**Input**: 用户描述: "Coffer needs messaging channels — Telegram and
SeaTalk first — so the owner can talk to any agent on the chat platform from
the IM apps they already use and
receive notifications pushed by Coffer. The architecture must stay uniform:
more channels and more agents will be added, so a new channel never touches
agent code and a new agent never touches channel code."

channel 是一种已注册的资源（`channel:<name>`），它把一个 IM 账号接到
Coffer 的聊天平台（spec 008）。来自已配对 owner 的消息成为一段普通对话
(conversation) 中的 turn；agent 的回复送回 IM 聊天。channel 层与 agent 层
只在聊天平台既有的接缝处相遇 —— 对话创建、turn 事件流 —— 因此 N 个
channel 与 M 个 agent 的成本是 N + M，而永远不是
N × M。

> **注（[ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.zh.md)）。**
> 下文把 `builtin` agent 当作可路由 channel 目标的提及，反映的是本 spec 落地时已交付的
> 行为。ADR-024 让内置 agent 退出聊天人格，因此 channel **只**路由到**受管** agent
> （Claude Code、Codex……）；内置模型现在是内部 `coffer__*` 能力，而非聊天目标。channel
> 旁观在共享接缝上的机制不变。

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

### User Story 9 — 从 chat 切换 agent 与 model（优先级：P2）

owner 不离开 IM app 就能操控入口。`/agent codex` 把会话切到 Codex；`/model
opus` 改 model。切换 agent 会开一个 pin 到新选择的新会话（agent 对会话终身固
定），且选择对后续消息与 `/new` 粘性保留；切换 model 在同会话下条 turn 生效。
每个命令无参时报告当前值与可选项。

**为何此优先级**：channel 是入口*管理者*，不是一根固定线。路由到所选 agent、
用所选 model，才让一个已配对的 chat 成为通往 vault 暴露的每个 agent 的交换机。

**Independent Test**：用一个已配对 channel 和两个脚本化 provider，发
`/agent <second>` 观察一个 pin 到它的新会话且下条消息由它回答；发
`/model <name>` 观察下条 turn 用它。

**Covering scenarios**:

- /agent switches the agent and sticks
- /agent rejects an unknown agent
- /model switches the model for the next turn

---

### User Story 10 — 知道谁驱动了什么、以及一个 turn 何时完成（优先级：P2）

因为入口可远程触达，channel 消息驱动的每个 turn
都连同 channel、peer、agent 记入审计日志——回答「谁经哪个 channel 驱动了哪个
agent」。当一个 turn 异常结束时，会推一条紧凑摘要到 chat：失败、停止、或达到
工具迭代上限，带工具数、耗时、token。干净成功在任何 channel 上都不发摘要——回复
本身就是信号，那条 fact 行只会是噪音。

**为何此优先级**：入口管理者的两个无人认领的差异化点是一等 auth/审计与可靠的
完成信号；二者必须在每个 channel 上为真，包括沉默的那些。

**Independent Test**：从已配对 channel 驱动一个 turn，观察一条带 channel、peer、
agent 的 turn-started 审计记录；观察干净成功不发完成摘要、而失败的 turn 会发。

**Covering scenarios**:

- a channel-driven turn is audited with channel, peer, and agent
- a clean success sends no completion summary
- a turn that does not end normally sends a completion summary
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
- 入站图片和文件 → 下载并交给 agent 处理本回合（图片为视觉 agent 内联、任何
  agent 都能拿到文件路径）。一条没有可下载内容的空消息（贴纸、位置）→ channel
  回复说明需要文本、图片或文件。

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
  service、turn orchestrator。
- **FR-005**: 回复按 channel 能力渲染：Telegram 把 markdown 转成 Telegram
  HTML（带纯文本回退），按段落边界以 4000 字符分块，并把工具进度以节流
  方式流式写入一条可编辑的状态消息，每行从调用的输入描述它在做什么
  （如 `⏳ Bash · list the desktop`、`✅ Read · wedding.json`）；SeaTalk 发送
  markdown，按 4096 字节
  分块，用 typing indicator 表示进行中。能力由 adapter 声明，内核不做
  特判。
- **FR-006**: `/new`、`/stop`、`/status`、`/help` 命令在任何已配对的聊天里
  可用。`/stop` 与 `/new` 即使在 turn 运行中也立即生效；其他消息排队
  （FIFO，上限 10）并按序运行。
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
  列出合法 keys；不为任何 agent 增加 channel 侧代码。在 `supports_buttons` 的
  传输上（FR-018），`/agent` 无参时把候选渲染成一张交互式选择卡片而非文本列表；
  点选某个按钮执行同一次切换。
- **FR-014**: owner gate 校验发送者身份，而非只看会话身份。每条 inbound 信封
  携带 `sender_id`（Telegram `from.id`、SeaTalk `employee_code`）；pairing 把它
  记到 peer，一条 inbound 消息只有在 `chat_id` 匹配且（当 peer 有已存
  `sender_id` 时）发送者匹配时才被接受。本要求之前配对的 peer（无已存
  `sender_id`）退化为 chat-id-only 闸。在 FR-012 之外审计一个 channel 驱动事件：
  一条 inbound 消息驱动的 turn（channel、peer、agent、conversation）。
- **FR-015**: 一个**异常结束**的 turn 之后，channel 发一条紧凑的完成摘要作为新
  消息：失败报告错误、中断报告停止、达到工具迭代上限报告上限，每条都带工具数、
  耗时、token 用量。干净成功在**任何** channel 上都**不**发摘要——回复本身就是完成
  信号，那条 fact 行只会是噪音（无论传输能否编辑消息，都如此）。
- **FR-017**: owner 从 chat 切换 model。`/model` 无参时报告当前 model；
  `/model <name>` 对 builtin agent 把名字对 model registry 解析并设会话的 model
  覆盖，对桥接 agent 则存原始上游 model 串透传给 CLI。model 切换在同会话下条 turn
  生效（model 每 turn 重读，不同于 agent 与工作目录）。非法 builtin model 对
  registry 校验被拒；坏的桥接 model 串会以 CLI 自己的错误回传到 chat。在
  `supports_buttons` 的传输上（FR-018），`/model` 无参时把尽力而为的快捷选项
  —— 受管 agent 的 active provider profile 的 model/fast_model（ADR-032）——
  渲染成选择卡片（自由文本 `/model <name>` 仍可用）；没有建议时回退到文本报告。
- **FR-018**: 在声明了 `supports_buttons` 能力的传输上，内核 MAY 把一个命令的
  候选列表渲染成一张**交互式选择卡片**（Telegram inline keyboard、SeaTalk
  interactive message）。按钮点选作为一个规范化回调到达，携带一个不透明的值；
  内核**像对消息一样 owner-gate 它**（chat + 发送者身份，FR-014），再路由到与
  文本命令相同的切换。点选从不配对；不支持的传输静默保持文本路径。这兑现了
  [ADR-014](../../docs/decisions/ADR-014-channel-adapter-framework.zh.md) 的
  `ChannelCapabilities` 已预想的交互按钮能力（「show buttons?」）。
- **FR-019**: 一个 channel 发起的 turn 会告诉 agent 它是被桥接到聊天 channel、
  而非终端：agent 收到一条简短的 system-prompt 注记，携带 channel 名与移动聊天
  指引——回复要简短，且它无法点击用户电脑上的权限/确认弹窗（用户可能不在电脑旁）。
  这避免了终端尺寸的长回复和在无法点击的弹窗上无声干等。网页 UI 的 turn 不受
  影响——注记只搭乘 `channel_name` 已设置的会话。
- **FR-020**: 入站图片和文件驱动一个 turn。传输层把每个附件下载到 Coffer 管理的
  媒体目录；bytes 绝不进 chat DB（持久化的用户消息保留 caption，没有则一条简短
  注记）。本回合每个附件交给 agent adapter，由它按自己的原生形态物化——视觉 agent
  （Claude Code）把图片内联为它直接看到的 base64 内容块、PDF 为 document 块；路径
  原生 agent（Codex）与任何非视觉文件收到磁盘路径去打开。这保持历史精简、适配任意
  文件类型、并可推广到未来模态（新类型是新 mime，不是新 schema）。见
  [ADR-038](../../docs/decisions/ADR-038-channel-media.zh.md)。
- **FR-021**: agent 通过显式选择把文件发回给用户：回复里一行
  `![caption](/absolute/path)`（由 FR-019 的 system 注记告知）。在声明了
  `supports_media` 的传输上，channel 上传该文件（图片扩展名作为内联照片、否则作为
  文档）并从投递文本里移除该行；正文里顺口提到的路径不是此语法、绝不上传，而文件
  缺失、相对路径或过大的标记则作为文本保留。这让出站发文件是刻意的、而非猜测。
- **FR-022**: 入站语音消息以转写文本驱动一个 turn。内置 agent（Claude Code、Codex）
  无法听音频，所以 adapter 把音频**本地**转写成文字并折进 turn 的 prompt。转写是一个
  按 agent 的接缝（ADR-038）：冻结的桌面 App 用随包、torch-free 的 `whisper.cpp` 引擎
  （Apple Silicon Metal），其小模型首次使用时下载；源码运行则回退到 `mlx-whisper`
  （可选 `[voice-mlx]` extra）。见 ADR-039。未来音频原生 agent 的 adapter 直接转发音频而非
  转写。没有可用引擎时——或模型尚未下载时——语音作为音频文件交出而非丢失。
- **FR-023**: 群聊是一等 peer。当已配对的 owner @mention bot（或消息以带地址的群
  事件形式投递）时，bot 会在那里作答；该群成为一条额外的 `channel_peers` 行，键为
  `(channel, 群聊 chat id)`，继承 owner 的 `sender_id`。无需 schema 迁移——该表的
  `(resource_id, chat_id)` 唯一键本就允许一个 channel 有多个 peer。
- **FR-024**: bot 只在一条带地址的消息（@mention 了 bot）上才在群里行动。未带地址
  的群消息被忽略。一条来自非 owner 的带地址消息会收到一条简短的「未授权」拒绝回复，
  且不启动任何 turn。
- **FR-025**: 转发的聊天记录被展平成可读文本、折进 turn 让 agent 看到——SeaTalk 的
  `combined_forwarded_chat_history` 与 Telegram 的 `forward_origin`。每条记录在
  `[Forwarded chat record]` 标题下渲染为 `<sender>: <text | [image] url | [file] name>`。
- **FR-026**: 线程 (thread) 被原地读取与回复，且群里的回复**永远进线程**——绝不落到
  群主聊天区。在 SeaTalk 上，线程的 id 等于其根消息的 id：在线程内的 @mention 本就带着
  该 id，于是 bot 读取该线程自身的消息作为上下文（SeaTalk 的 `get_thread_by_thread_id`）
  并回复进该线程；在群主聊天区的 @mention 不带线程 id，于是 bot 以这条 @mention 为根
  新建一个线程（回复挂在该 @mention 自身的 message id 下），而由于此时线程内只有这条
  @mention，不读取任何历史。一条在线程内发出的 DM 或群消息，回复也会进入该线程。刻意
  **不**读取*最近的群主聊天*历史（SeaTalk 的群聊历史权限未获批；@mention 消息本身自成
  上下文）。Telegram 完全无法拉取历史（Bot API 的限制），因此 Telegram 上不读取线程
  上下文——bot 仅基于 @mention 消息本身作答，但仍会回复进该 forum topic。一条被引用/
  回复的消息在平台内联该信息处贡献一段 `> sender: …` 上下文前缀。
- **FR-027**: 每个 `(channel, chat, thread)` 都有自己的 turn 队列/会话，因此 DM turn、
  群主聊天 turn 与线程 turn 彼此永不共享状态。

### Key Entities

- **Channel** — 资源 `channel:<name>`；config = 类型、凭据 ref、默认
  agent + 配置。
- **ChannelPeer** — channel 的已配对 owner：`(resource, chat_id)`、显示
  名、配对时间、指向活跃对话的指针、已配对发送者身份（`sender_id`），以及
  粘性首选（所选 agent）。每个 (channel, chat) 一行：已配对 owner 一行，
  加上 owner 曾 @ 过 bot 的每个群聊/thread 各一行；`(resource_id, chat_id)`
  唯一键已支持这一点，无需迁移。
- **InboundMessage / InboundCallback / OutboundMessage** — 每个 adapter 生产与
  消费的规范化信封 (envelope)；内核永远看不到平台原始载荷。inbound 为 owner gate
  携带发送者身份（`sender_id`）。`InboundCallback` 是一次选择卡片按钮点选（携带一个
  不透明的 `data` 值而非文本，FR-018）；出站文本 MAY 携带 `ChoiceButton`，支持按钮的
  传输把它渲染成选择卡片。
- **ChannelCapabilities** — adapter 声明自己能做什么（编辑消息、经
  `supports_buttons` 的交互按钮、typing indicator）；内核据此选择渲染策略。
- **PairingCode** — 内存态、一次性、按 channel；从不持久化。

## Success Criteria

### Measurable Outcomes

- **SC-001**: 从全新安装出发，用户按照 quickstart 在 10 分钟内即可注册一个
  Telegram channel、完成配对并得到一条 agent 回复。
- **SC-002**: 陌生人给 bot 发消息产生零可观察响应、零 turn，而 owner 的
  流量不受影响。
- **SC-003**: 新增一个假想的第三种 channel 类型，只需实现一个 adapter +
  一份配置 schema，不触碰任何 agent 或对话代码（由测试套件使用的
  test-only 假 channel 演示）。
- **SC-004**: 任何注册在聊天平台上的 agent 都能从任何 channel 触达，
  channel 侧无需任何代码改动（通过在测试里用一个脚本化的第二 provider
  驱动 channel 来演示）。
- **SC-005**: 下方每个 acceptance scenario 至少被一个测试覆盖；
  `make verify` 通过。
- **SC-006**: 从一个已配对 chat，owner 能触达每个已注册 agent、用一个所选
  model（通过在测试里驱动两个脚本化 provider 来演示）。
- **SC-007**: 每个 channel 驱动的 turn 都能按 channel、
  peer、agent 在审计日志里查到；干净成功在任何 channel 上都不发完成摘要，而异常
  结束（失败、中断、达工具上限）的 turn 会发一条报告结果的摘要。

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

### Scenario: /model switches the model for the next turn

- **Given** 一个处于活跃会话的已配对 channel
- **When** peer 发 `/model <name>` 然后发一条消息
- **Then** 下条 turn 在同会话里以所选 model 运行

### Scenario: a selection-card tap switches the agent

- **Given** 一个在支持按钮的传输上、且注册了第二个 agent 的已配对 channel
- **When** owner 发 `/agent`（渲染为选择卡片）并点选第二个 agent 的按钮
- **Then** 一个 pin 到第二个 agent 的新会话变为活跃，如同 owner 键入了
  `/agent <second>`

### Scenario: a non-owner selection-card tap is ignored

- **Given** 一个 peer 已存 `sender_id` 的已配对 channel
- **When** 该 chat 里的另一个成员点选一个选择卡片按钮
- **Then** 该点选被忽略，owner 的 agent/model 不变

### Scenario: a channel-driven turn is audited with channel, peer, and agent

- **Given** 一个已配对 channel
- **When** peer 发一条驱动 turn 的消息
- **Then** 一条审计记录写下 channel、peer、agent 与 conversation

### Scenario: a turn that does not end normally sends a completion summary

- **Given** 一个已配对 channel
- **When** 一个 turn 失败、被中断、或达到工具迭代上限
- **Then** 一条紧凑完成摘要被发到 chat 报告结果（错误/停止/上限），带工具数、
  耗时、token

### Scenario: a clean success sends no completion summary

- **Given** 一个已配对 channel（无论传输能否编辑消息）
- **When** 一个 turn 成功完成
- **Then** 不发任何完成摘要——回复本身就是 turn 结束信号

### Scenario: channel progress lines describe each tool call from its input

- **Given** 一个在可编辑消息的 adapter 上的已配对 channel
- **When** agent 在一个 turn 中调用一个工具
- **Then** 进度状态行给出工具名和从其输入取的简短描述（如 Bash 的 description、
  Read 的文件名）

### Scenario: a group member who is not the paired sender is ignored

- **Given** 一个带已存发送者身份的已配对 peer
- **When** 一条消息以相同 chat id 但不同 sender id 到达
- **Then** 不发回复，也不启动 turn

### Scenario: the channel-driven agent is told it is on a chat channel

- **Given** 一个 channel 发起的会话
- **When** 从 channel 驱动一个 turn
- **Then** agent 收到一条 system-prompt 注记，说明 channel 名、要求回复简短、
  并告知它无法点击用户的系统弹窗；而网页 UI 会话不会收到这条注记

### Scenario: an inbound photo is downloaded and drives a turn

- **Given** 一个已配对的 Telegram channel
- **When** owner 发送一张图片（可带 caption）
- **Then** 最大尺寸的图片被下载到媒体目录、作为附件挂在入站消息上，caption
  成为消息文本

### Scenario: an inbound image reaches a vision agent as an inline block

- **Given** 一个携带图片附件的 turn
- **When** Claude adapter 构建该 turn 的内容
- **Then** 图片是一个 base64 `image` 内容块（非视觉文件则变成路径指针），因此
  bytes 仅在本回合内联发送、绝不存进 chat 数据库

### Scenario: the agent sends a file to the user via a reply marker

- **Given** 一个支持媒体的 channel，且 agent 回复中含 `![caption](/absolute/path)`
  指向一个存在的文件
- **When** 投递该 turn 的回复
- **Then** 文件被上传（图片作为照片、否则作为文档）、标记从文本中移除；正文里
  顺口提到的路径不会被上传

### Scenario: an inbound voice message is transcribed for a text-only agent

- **Given** 一个给无法听音频的 agent 的 turn 上带一个语音附件
- **When** adapter 准备该 turn
- **Then** 音频被转写成文字并折进 prompt，且音频不再作为文件发送（未来音频原生
  agent 则会直接转发它）

### Scenario: an un-addressed group message is ignored

- **Given** 一个已配对的 channel 和一个 bot 所在的群聊
- **When** 一条群消息到达、没有 @mention bot
- **Then** 不发送任何回复，也不为该群创建任何 turn 或 peer 行

### Scenario: the owner @mentions the bot in a group main chat

- **Given** 一个已配对的 channel 和一个没有活跃线程的群聊
- **When** owner 在群的主聊天里 @mention bot
- **Then** 一个 turn 运行，回复被投递进以该 @mention 为根新建的线程（绝不落到群主
  聊天区），不读取任何线程历史，且为该群聊创建一条 `channel_peers` 行、继承 owner 的
  `sender_id`

### Scenario: a non-owner @mention in a group is refused

- **Given** 一个已知 owner 的已配对 channel
- **When** owner 以外的人在群聊里 @mention bot
- **Then** bot 回复该发送者未获授权，且不启动任何 turn

### Scenario: the owner @mentions the bot inside a thread

- **Given** 一个已配对的 channel 和一个带线程的群聊，运行在能拉取线程历史的传输上
- **When** owner 在该线程内 @mention bot
- **Then** 该线程自身的消息被读取并折进该 turn，回复也被路由回同一线程

### Scenario: a forwarded chat record reaches the agent

- **Given** 一个已配对的 channel
- **When** owner 向 bot 转发一条聊天记录
- **Then** 该 turn 的消息文本携带一个 `[Forwarded chat record]` 块，列出每条被
  转发的记录

## Assumptions

- 用户能创建 Telegram bot（BotFather）和 SeaTalk Open Platform app，并能
  通过其组织的审批流程获得 SeaTalk 的 scope（Send Message to Bot User
  等）。
- 对 SeaTalk，用户自行运行一条隧道（cloudflared、ngrok 或等价物）把公网
  URL 通到本地回调端口；Coffer 在 quickstart 中给出做法，但不管理隧道。
- channel 承载文本以及入站的图片和文件（FR-020）：媒体被下载并交给 agent，而一条
  没有可下载内容的空消息会收到礼貌的「发文本、图片或文件」回复。出站是文本、加上
  agent 选择发送的文件（FR-021，在 `supports_media` 的传输上），以及作为富例外的
  **命令选择卡片**：在 `supports_buttons` 的传输上，`/agent` 与 `/model` 可以把候选
  渲染成交互按钮（FR-018）。
