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
Coffer 的聊天平台（见下文 E 节）。来自已配对 owner 的消息成为一段普通对话
(conversation) 中的 turn；agent 的回复送回 IM 聊天。channel 层与 agent 层
只在聊天平台既有的接缝处相遇 —— 对话创建、turn 事件流 —— 因此 N 个
channel 与 M 个 agent 的成本是 N + M，而永远不是
N × M。

> **注（[Built-in Agent Is Internal](../../docs/decisions/builtin-agent-is-internal-capability.zh.md)）。**
> 下文把 `builtin` agent 当作可路由 channel 目标的提及，反映的是本 spec 落地时已交付的
> 行为。该 ADR 让内置 agent 退出聊天人格，因此 channel **只**路由到**受管** agent
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
分块 (chunk)。bot 在 turn 运行期间通过让**同一条**消息就地生长来展示进度
——Telegram 编辑它的状态消息，SeaTalk 流式重渲染一条消息——于是答案不再
以一串碎片的形式抵达。同一段对话连同完整历史都记在 vault 里。

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
- 活跃对话被删除 → peer 的下一条消息会用默认 agent 创建一段
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
  HTML（带纯文本回退），按段落边界以 4000 字符分块；SeaTalk 把同一份 markdown
  转成 SeaTalk 自己的 markdown（`format: 1` —— 粗体、斜体、行内 code、code
  fence、有序与无序列表；标题转粗体、链接转 `label (url)`，因为二者都不被支持，
  而作为字面量的标记字符用**单反斜杠**转义——两个就多转了一次，SeaTalk 会吃掉第一个、
  把第二个当字面量渲染出来），按 4096 字节分块。两者都把一个 turn
  的进度流式写进**同一个**就地生长的界面（FR-037），其中每行从调用的输入描述它在
  做什么（如 `⏳ Bash · list the desktop`、`✅ Read · wedding.json`）。能力由
  adapter 声明，内核不做特判。
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
  点选某个按钮执行同一次切换。卡片在支持标题元素的传输上（SeaTalk；Telegram 则取为
  加粗首行）带一个**标题元素**，使其主题一眼可辨而不必挤占正文。点按生效之后，声明
  `supports_card_update` 的传输 MUST **就地改写这张卡片**，把勾标移到新的选择上 ——
  一张仍在推荐用户刚刚选过的选项的卡片，只会诱发一次什么都不做的再点按。改写是尽力
  而为：切换本身已经完成并在会话中确认过，因此传输不具备该能力、或平台拒绝这次改写
  （SeaTalk 的更新只作用于交互卡片、只在 7 天内、且只允许原发送 bot），都不会影响
  用户所依赖的任何结果。
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
  `supports_buttons` 的传输上（FR-018），`/model` 无参时把候选渲染成选择卡片。
  选项取自该 agent 的 model catalogue（与网页 picker 同一份列表），当本 channel 设了
  允许范围时按该范围收窄（FR-071），否则**整份** catalogue 都可选，只是**一次一页**
  （FR-018）：`claude_code` 的 catalogue 有 29 个
  model，这么长的卡片在手机上根本读不了，SeaTalk 也会直接拒收，所以卡片是这份列表
  的一个窗口，而不是列表本身。卡片打开时停在当前生效 model 所在的那一页，因此新渲染
  的卡片总能看见自己的勾标。自由文本 `/model <name>` 仍然是触达一个你已经叫得出名字
  的 model（包括 catalogue 里没有的）最快的路，卡片正文也这么写着；但在设了允许范围的
  channel 里，它只能触达该范围内的 model（FR-071）。没有建议时回退到文本报告。
- **FR-018**: 在声明了 `supports_buttons` 能力的传输上，内核 MAY 把一个命令的
  候选列表渲染成一张**交互式选择卡片**（Telegram inline keyboard、SeaTalk
  interactive message）。按钮点选作为一个规范化回调到达，携带一个不透明的值；
  内核**像对消息一样 owner-gate 它**（chat + 发送者身份，FR-014），再路由到与
  文本命令相同的切换。点选从不配对；不支持的传输静默保持文本路径。这兑现了
  [Channel Adapter Framework](../../docs/decisions/channel-adapter-framework.zh.md) 的
  `ChannelCapabilities` 已预想的交互按钮能力（「show buttons?」）。

  卡片载荷必须遵循各平台公布的结构。SeaTalk 的结构是一个扁平的 `elements` 数组，
  其中**按钮本身就是一个 element**（`{"element_type": "button", "button": {...}}`），
  而不是与之并列的一个 `buttons` 数组。Coffer 在 2026-09-10 之前发出的是后者——
  那是 API 文档处于登录态不可达时猜出来的结构——因此一张 SeaTalk 选择卡片要么渲染
  不出按钮，要么被平台直接拒收。

  每类元素的数量上限同样在文档处于登录态时无从得知，只能靠试探逼近：已知 2 个按钮
  被接受、29 个被拒收，中间没有任何确证，于是卡片就凭着这段空白把按钮数封在了六个。
  现在公布出来的上限是：一张卡片最多 **3 个标题、5 个描述、5 个按钮、3 个按钮组和
  3 张图片**，标题最多 120 字符、描述最多 1000 字符——这就使得那张六按钮的卡片，正好
  比裸按钮的上限多出一个。因此按钮不再各占一个 element，而是排进**按钮组**（一个
  element 容纳同一行上最多三个按钮）：六个按钮占掉三个组位中的两个，按公布的规则合法，
  读起来是两行而不是六层高的一摞。标题与描述文本也被夹到各自文档规定的长度，于是过长
  的正文降级成一张被截断的卡片，而不是一张被拒收的卡片。

  平台拒收一张卡片并不等于命令到此为止：handler 回退到它本来就有的纯文本答复，
  于是被拒的卡片降级成一条能用的消息，而不是让用户什么也收不到。该拒收会被记日志，
  以便事后可诊断。

  一张卡片携带的按钮数有**上限**——含导航共六个。SeaTalk 的真实上限没有文档
  （已知 2 个被接受、29 个被拒收），所以这个上限取的是 Coffer 已经发出去过的最大
  数量，而不是对极限的猜测。超出上限的候选列表会**分页**：卡片显示四个候选，外加
  `← Prev` / `Next →`，一次导航点按沿着与「应用某个选择」相同的 `supports_card_update`
  路径**改写同一条消息**到下一个窗口。两张卡片共用同一条规则——`/agent` 的两个候选
  在上限之内，因此完全不带任何导航元素。

  导航载荷有自己的 callback 命名空间（`page:<kind>:<index>`），与候选所用的
  `agent:` / `model:` 值互不相交，且长度固定、远在 64 字节预算之内。正是这份隔离
  保证了那条不变量：**翻页什么都不改。**它只重读当前生效值并重新渲染；它永远不可能
  被误当成一次选择，而格式不合法的导航值会被丢弃，而不是被放行去走应用选择的代码路径。
  由于当前所在页未必装着生效中的那个选项，卡片正文始终写明什么在生效、它在第几页，
  于是一张没有勾标的页面永远不会被读成「什么都没选」。

  与选择之后那次纯装饰性的改写不同，翻页是用户主动要看的东西，因此它降级而不丢弃：
  当那条消息无法就地改写时——传输没有 `supports_card_update`，或平台拒绝了这次更新
  （卡片超过了 SeaTalk 的 7 天窗口，或我们被限流）——所请求的那一页会作为一张新卡片
  发出；若新卡片也被拒收，则以纯文本发出。
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
  [Channel Media](../../docs/decisions/channel-media.zh.md)。
- **FR-021**: agent 通过显式选择把文件发回给用户：回复里单独一行的行锚定 sentinel
  `MEDIA:/absolute/path`（可选 `MEDIA:/absolute/path | caption`），由 FR-019 的 system
  注记告知。在声明了 `supports_media` 的传输上，channel 上传该文件（图片扩展名作为内联
  照片、否则作为文档）并从投递文本里移除该行；普通正文——包括仅用于引用文件的合法
  markdown 图片 `![alt](path)`——不是此语法、绝不上传，而文件缺失、相对路径或过大的
  sentinel 则作为文本保留。这个无歧义的 sentinel 让出站发文件是刻意的、而非猜测，且绝不
  与普通 markdown 冲突。
- **FR-022**: 入站语音消息以转写文本驱动一个 turn。内置 agent（Claude Code、Codex）
  听不见音频，因此 adapter 先把音频转写成文本、折进这个 turn 的 prompt。转写是一条
  按 agent 的接缝（ADR: channel-media）；将来若有原生听得见音频的 agent，其 adapter 直接转发音频
  而不转写。

  转写走**远程**，落在用户指定为 Coffer `internal_default` 的那条连接上——也就是跑
  knowledge merge / organize / reorg 的同一条（spec provider-switching）。因此语音不引入新概念，
  也不引入第二处配置。端点是 OpenAI 形状的
  （`POST <base_url>/audio/transcriptions`）；协议本身没有这个端点的连接
  （`anthropic`、`ollama`）不会被用于转写。

  **这是 Coffer 里唯一一处用户内容可能离开本机的地方，且默认关闭。** 没有指定内部连接、
  协议不支持、或凭据解析不出来时，什么都不会上传：语音以音频文件的形式交给 agent，
  而不是丢失——与本地引擎缺席时的行为完全一致。请求失败或过慢也以同样方式降级：
  转写出问题绝不允许让一个 turn 失败。

  这不违反 constitution。Principle I 明确允许云服务作为 **LLM 与工具 provider**，
  而转写端点就是一个工具 provider；音频是过路数据而非金库状态，转写结果与任何其他
  turn 文本一样落在本机。

  _2026-09-10 之前是本地的：_ 冻结构建随包一个在 CI 里从源码编译的 `whisper.cpp`
  sidecar，外加源码运行时的 `mlx-whisper` 回退。那是整个项目最重的构建依赖——每次发布
  都要 `git clone` 加一次 cmake 编译——而它撑的这个能力，远程端点做得至少一样好。
  它与「随包 sidecar」那条决策、`whisper-cli` 二进制、以及 `[voice]` / `[voice-mlx]` extra 一并删除。

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
  SeaTalk 消息里的图片——直接发的图，或转发记录里（递归）嵌套的任意图片——还会用
  app token 下载下来（SeaTalk 文件链接需鉴权，光有 URL 对 agent 没用）并作为附件挂到
  turn，让多模态 agent 看到真实图片而不只是链接。
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
- **ChannelCapabilities** — adapter 声明自己能做什么（经 `supports_live_text`
  的可持续更新界面、经 `supports_edit` 的改写已投递消息——二者相互独立，见
  FR-037——经 `supports_buttons` 的交互按钮、typing indicator）；内核据此选择
  渲染策略。
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

## 渠道在哪里运行

渠道的平台身份（被轮询的 bot、webhook 端点）只容许一个消费者。Coffer 每台机器
只有一个仓库，且从不复制一个正在运行的仓库
（[Vault Export and Import](../../docs/decisions/vault-export-import.zh.md)），因此没有
任何需要仲裁的东西：**启用的渠道就在本机运行它的适配器**——即持有它的守护进程
所在的那台机器——被禁用的渠道则在任何地方都不运行。不存在机器绑定，没有亲和性
字段，也没有 per-machine override。

`channel` kind 不声明 `scope`
（[Per-Agent Resource Scope](../../docs/decisions/per-agent-resource-scope.zh.md)）：非
null 值在校验阶段被拒绝（422）。是否启动适配器，唯一的控制手段就是启用与否。

如果用户把一个 bundle 带到第二台机器（spec vault-export-import），该渠道在那里也会被注册——配对
状态随 bundle 的 `channel-peers` 状态区一同带过去，因此无需重新配对——而在两边
同时启用，就会让两个适配器指向同一个 bot 身份。那是用户的一次刻意操作，而不是
Coffer 需要仲裁的状态——导出/导入模型里没有任何后台复制能自行造成这种局面。

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

### Scenario: a tapped selection card is rewritten with the new choice

- **Given** 一个已配对的 channel，其传输声明 `supports_card_update`，正显示一张 `/agent`
  选择卡片
- **When** 属主点按另一个 agent 的按钮
- **Then** 该卡片被就地改写，勾标移到刚选中的 agent 上；在不具备该能力的传输上不发生任何改写
  而切换照常成功；平台拒绝这次改写时，切换及其确认消息也都完好无损

### Scenario: a long selection card is browsed page by page in place

- **Given** 一个已配对、支持按钮的 channel，正显示一张由远超单卡容量的 catalogue
  构建的 `/model` 卡片
- **When** 属主点按 `Next →`
- **Then** 同一条卡片消息被改写为下一页 model——不发第二张卡片、不切换任何 model，
  正文仍写明生效中的 model 及其页码；最后一页不再提供 `Next →`；平台不肯就地应用的
  那次翻页，会以一张新卡片（或纯文本）送达，而不是变成沉默

### Scenario: a non-owner selection-card tap is ignored

- **Given** 一个 peer 已存 `sender_id` 的已配对 channel
- **When** 该 chat 里的另一个成员点选一个选择卡片按钮
- **Then** 该点选被忽略，owner 的 agent/model 不变

### Scenario: a group selection-card tap replies in the group/thread

- **Given** 一个在支持按钮的传输上、带有群 peer、且注册了第二个 agent 的已配对
  channel
- **When** owner 在群的某个 thread 里点选 `/agent` 选择卡片按钮
- **Then** 切换被应用到该群 thread，且"已切换"的确认消息被路由回该群/thread
  （绝不发到 DM）；非 owner 的点选会收到一条被路由的"未授权"拒绝回复且不发生切换

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

### Scenario: reply text streams into the editable status message as it arrives

- **Given** 一个在可编辑消息的 adapter 上的已配对 channel
- **When** agent 的回复文本在一个 turn 中以增量到达
- **Then** 那条唯一的状态消息先显示工具进度行，随后就地被编辑为不断累积的回复文本
  （纯文本，非 HTML），让用户看着答案逐渐成形；结束时删除该状态消息并只发一次最终
  回复（HTML 渲染并按段落分块）

### Scenario: the streamed reply preview is clipped to the platform limit

- **Given** 一个在可编辑消息的 adapter 上的已配对 channel
- **When** 累积的回复文本增长超过平台的单条消息上限
- **Then** 每次中途编辑都被裁剪到该上限（保留最近文本，前面加省略号），使编辑不会
  失败，而最终回复携带完整文本

### Scenario: a slow text-only reply streams into a status message

- **Given** 一个在可编辑消息的 adapter 上的已配对 channel
- **When** 一个纯文本 turn（没有工具调用）持续产出回复文本、超过节流间隔
- **Then** 打开一条状态消息装载流式回复文本，并随答案增长就地编辑，结束时删除该消息
  且只发一次最终回复

### Scenario: a fast text-only reply opens no status message

- **Given** 一个在可编辑消息的 adapter 上的已配对 channel
- **When** 一个纯文本 turn 在节流间隔内就完成
- **Then** 不打开任何状态消息（没有 create→delete→resend 抖动）——只发那一条最终回复

### Scenario: a supports_typing-only DM keeps the typing indicator alive during a long turn

- **Given** 一个在能显示打字但不能编辑（SeaTalk）的 adapter 上、私聊中的已配对 channel
- **When** 一个长 turn 运行
- **Then** 打字提示在该 turn 期间被周期性重发（一个短暂动作，无聊天噪声），并在 turn
  结束时停止

### Scenario: a transport with no live-text surface posts no interim status message

- **Given** 一个在既不能编辑也不能流式的 adapter 上、群组/线程中的已配对 channel
  （那里也用不上只对私聊生效的打字信号）
- **When** 一个 turn 运行
- **Then** 完全不发任何中途信号——只有最终分块回复落在发起的群组/线程里

### Scenario: a reply grows in place on a transport that streams but cannot edit

- **Given** 一个在不能编辑或删除消息、但能流式一条消息（SeaTalk）的 adapter 上、
  群组/线程中的已配对 channel
- **When** 一个 turn 先跑工具再写回复
- **Then** 聊天里只出现**一条**消息并就地生长——先是工具进度，随后是累积中的回复——
  且它带着最终回复结束，于是没有任何内容被发两遍，答案也不再一段段蹦出来

### Scenario: each seatalk stream update carries the full reply so far

- **Given** 一个正在流式回复的 SeaTalk channel
- **When** 回复文本以增量到达
- **Then** stream 只被打开一次，每次更新都携带**全量**累积文本（绝不是增量）并带一个
  单调递增的序号，且只有最后一次更新结束该 stream

### Scenario: a terminated seatalk stream is never reused

- **Given** 一个已被平台终止的 SeaTalk stream（出错，或间隔超过 30 秒上限）
- **When** 该 turn 继续产出文本并结束
- **Then** 之后没有任何请求再指名那个 stream id，也不会另开一个替代 stream，回复改由
  普通发送路径投递

### Scenario: a reply past the stream budget finishes the stream and sends the rest

- **Given** 一条超出单个 stream 承载上限（4096 字符）的 SeaTalk 回复
- **When** 该 turn 结束
- **Then** stream 在预算处按段落边界结束，余下部分以普通分块消息投递

### Scenario: seatalk markdown escapes a literal marker character

- **Given** 一条正文里含有并非标记语法的 SeaTalk 格式字符的回复（如 `snake_case`
  中间的下划线）
- **When** 它为 SeaTalk 渲染
- **Then** 该字符用**单反斜杠**转义从而原样保留，而真正的粗体/斜体/code/列表标记
  仍按 SeaTalk markdown 保留

### Scenario: a refused selection card falls back to the text reply

- **Given** 一个支持按钮、但会直接拒收选择卡片的传输
- **When** owner 发 `/agent` 或 `/model`
- **Then** 该命令改以纯文本报告作答，并把这次拒收记入日志——
  "什么也不回"是一个命令绝不能产生的结果

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

### Scenario: a Telegram album is handled as one turn

- **Given** 一个已配对的 Telegram channel
- **When** owner 发送一个多图相册（作为共享同一 `media_group_id` 的多条独立消息投递，
  caption 只在第一条上）
- **Then** 这些条目被去抖并合并成一条入站消息，携带它们全部的附件与相册的 caption
  —— 一个 turn，而非每张图一个 turn；而一张没有 `media_group_id` 的单图仍立即驱动其
  turn

### Scenario: an inbound image reaches a vision agent as an inline block

- **Given** 一个携带图片附件的 turn
- **When** Claude adapter 构建该 turn 的内容
- **Then** 图片是一个 base64 `image` 内容块（非视觉文件则变成路径指针），因此
  bytes 仅在本回合内联发送、绝不存进 chat 数据库

### Scenario: the agent sends a file to the user via a reply marker

- **Given** 一个支持媒体的 channel，且 agent 回复中含一行 `MEDIA:/absolute/path`
  sentinel（可选 `| caption`）指向一个存在的文件
- **When** 投递该 turn 的回复
- **Then** 文件被上传（图片作为照片、否则作为文档）、该 sentinel 行从文本中移除；
  普通正文——包括 markdown 图片 `![alt](path)`——不是此语法、不会被上传

### Scenario: an inbound voice message is transcribed for a text-only agent

- **Given** 一个给无法听音频的 agent 的 turn 上带一个语音附件
- **When** adapter 准备该 turn
- **Then** 音频被转写成文字并折进 prompt，且音频不再作为文件发送（未来音频原生
  agent 则会直接转发它）

### Scenario: a PDF reaches a path-native agent as extracted text

- **Given** 一个给路径原生 agent（Codex）的 turn 上带一个
  PDF（或 office 文档）附件
- **When** adapter 准备该 turn
- **Then** 文档被抽取成文字并以带标签的 `[Document: <name>]` 块折进 prompt，且该
  文档不再作为二进制路径提示发送；当没有可用的抽取引擎时，文档退化为文件路径而不
  会卡住该 turn

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

### Scenario: an empty sender_id in a group cannot bypass the owner gate

- **Given** 一个已知 owner 的已配对 channel 和一个群聊
- **When** 一条被寻址的群消息到达，却带不出可解析的 `sender_id`（传输没能供出一个）
- **Then** bot 像拒绝一个非 owner 发送者那样拒绝它——不启动任何 turn，也不创建
  peer 行

### Scenario: require_mention on drops an un-addressed group message

- **Given** 一个 `require_mention` 打开（默认）的已配对 channel
- **When** 一条未指向 bot（无 @mention/回复 bot）的群消息到达，即便来自 owner
- **Then** 它在 mention 闸处被丢弃——无回复、无 turn、也不建 peer 行

### Scenario: require_mention off admits an un-addressed owner group message

- **Given** 一个 `require_mention` 关闭的已配对 channel
- **When** 一条未指向 bot 的群消息来自 owner
- **Then** 它通过 mention 闸并驱动一个 turn（仍受 owner 门控：非 owner 会被闸下方的发送者校验拒绝）

### Scenario: ignore_other_mentions drops a message that also @mentions a human

- **Given** 一个 `ignore_other_mentions` 打开的已配对 channel
- **When** 一条群消息 @ 了 bot，但同时也 @ 了另一个用户
- **Then** 它被静默丢弃——无回复、无 turn——于是 bot 不会插进面向人的对话

### Scenario: ignore_other_mentions off still answers when @mentioned alongside a human

- **Given** 一个 `ignore_other_mentions` 关闭（默认）的已配对 channel
- **When** 一条群消息在 @ bot 的同时也 @ 了另一个用户
- **Then** turn 仍然运行——额外的人类 @mention 不会抑制它

### Scenario: a group slash-command reply routes to the group/thread

- **Given** 一个已配对的 channel，以及一个 owner 在其中发过消息的群聊/线程
- **When** owner 在那个群/线程里发出一条斜杠命令（例如 `/status`）
- **Then** 该命令的回复以与触发消息相同的 `chat_kind`/`thread_id` 路由，而不是退回
  私聊的默认值

### Scenario: the owner @mentions the bot inside a thread

- **Given** 一个已配对的 channel 和一个带线程的群聊，运行在能拉取线程历史的传输上
- **When** owner 在该线程内 @mention bot
- **Then** 该线程自身的消息被读取并折进该 turn，回复也被路由回同一线程

### Scenario: a forwarded chat record reaches the agent

- **Given** 一个已配对的 channel
- **When** owner 向 bot 转发一条聊天记录
- **Then** 该 turn 的消息文本携带一个 `[Forwarded chat record]` 块，列出每条被
  转发的记录

### Scenario: thread-history images reach a vision agent

- **Given** 一个已配对的 channel 和一个群线程，其自身消息中包含图片（一张直接发送
  的，以及一张嵌在转发记录里的）
- **When** owner 在该线程内 @mention bot
- **Then** 该线程的图片被下载并作为附件加入该 turn——以真实字节抵达视觉 agent，而
  不是一个失效的、需鉴权的文件链接

### Scenario: each group thread is an independent conversation

- **Given** 一个已配对的 channel 和一个群，其线程共享同一个 `chat_id`
- **When** owner 在线程 A 驱动一个 turn，并在其结束前又在线程 B 驱动一个 turn
- **Then** 这两个线程解析到两个不同的会话，两个 turn 并发运行，且都不会被以
  "a turn is already running" 拒绝

### Scenario: one bot runs different agents in different threads

- **Given** 一个已配对的 channel 和一个群
- **When** owner 把线程 A 切换到另一个 agent，而线程 B 保持 channel 默认
- **Then** 线程 A 的会话驱动被切换后的 agent，线程 B 的会话驱动默认 agent——一个
  bot 在不同线程运行不同 agent

### Scenario: SeaTalk outbound media is delivered into the originating thread

- **Given** 一个已配对的 SeaTalk channel，以及一次群线程 turn，其回复中包含指向真实
  文件的一行 `MEDIA:/absolute/path` sentinel
- **When** 该 turn 的回复被投递
- **Then** SeaTalk 把文件上传（图片作为 `image` 消息，否则作为 `file` 消息）到同一个
  群和同一个线程——而不是群主聊天——因为 `supports_media` 现已为真，且 `send_media`
  依据该 turn 的 chat_kind 与 thread_id 路由；任何 caption 作为一条线程内文本消息随后发送

### Scenario: a redelivered event is processed once

- **Given** 一个已配对的 channel，且它已处理过某条入站事件
- **When** 平台在一次缓慢的 ack 或网络抖动后重投同一条事件（相同 id）
- **Then** 该重投被丢弃，turn 恰好只运行一次——没有重复回复或重复工作——而一条真正
  的新事件仍然驱动其自身的 turn

### Scenario: an inbound SeaTalk file drives a turn

- **Given** 一个已配对的 SeaTalk channel
- **When** owner 直接发送一个文件（一条 `file` 消息，其 `file.content` 是一个鉴权
  文件 URL，`file.filename` 是原始文件名）
- **Then** 用 app token 下载字节，并作为附件挂在入站消息上，保留其真实文件名和一个
  非图片 mime，因此该文件像照片一样驱动一次 turn，而不是命中"发送文本、图片或文件"
  的回复

### Scenario: an inbound attachment is persisted as a reference on the user message

- **Given** 一个已配对的 channel，用一张图片附件驱动一次 turn
- **When** 该 turn 开始
- **Then** 持久化的用户消息在其文本之后携带一个 `AttachmentBlock` 引用（path、mime、
  filename——绝不含 bytes），因此该附件留存在历史里

### Scenario: a later turn re-materialises the attachment from history

- **Given** 一条携带附件引用的持久化用户消息
- **When** turn 任务运行（包括守护进程重启后、没有任何参数被向下线程传递时）
- **Then** adapter 收到一个带该引用 path/mime 的 `Attachment`，从历史里最后一条用户
  消息重新物化——单一事实来源

### Scenario: the message API exposes an attachment block without leaking the path

- **Given** 一条带附件引用的用户消息
- **When** 客户端读取该会话的消息
- **Then** 内容块为 `type=attachment`，带 `filename` 与 `mime`，线上不出现 `path` 字段

### Scenario: the media dir prune deletes stale files and keeps fresh ones

- **Given** 媒体目录里有一个超过 30 天的文件和一个较新的文件
- **When** 保留清扫运行
- **Then** 陈旧文件被删除，较新的文件被保留

### Scenario: the management surface lists each Coffer-hosted channel with status, owner, agent, and health

- **Given** 一个已注册且运行中的 Coffer-hosted channel，带有一个已配对的 owner
  和一个路由到的 agent
- **When** 管理面读取该 channel
- **Then** 它报告该 channel 的启用状态、实时健康（适配器运行中）、已配对的
  owner 以及路由到的 agent——与 MCP-server / memory / skill 的管理面保持一致

### Scenario: receipt and completion are acked with reactions where supported

- **Given** 一个已配对渠道，其 adapter 支持 reaction（Telegram）
- **When** owner 发来一条消息并驱动了一个干净完成的 turn
- **Then** 在收到时立即在 owner 自己的消息上设置 👀 reaction，完成时设置 ✅ reaction，二者
  都指向该入站消息 id

### Scenario: a transport without reaction support attempts no reaction

- **Given** 一个已配对渠道，其 adapter 不支持 reaction（SeaTalk，其收到与进度提示是 typing
  信号）
- **When** owner 发来一条消息并驱动一个 turn
- **Then** 不尝试任何 reaction，而 turn 仍正常运行并回复

### Scenario: a failed reaction never breaks the turn

- **Given** 一个支持 reaction 的 adapter，其 set_reaction 会失败
- **When** owner 发来一条消息并驱动一个 turn
- **Then** 回复仍被送达——尽力而为的 reaction 被吞掉

### Scenario: a group turn names the group it came from

- **Given** 一个已配对的 channel，其 owner 在某个群的线程里 @ 了 bot
- **When** 该 turn 被驱动
- **Then** turn 文本以一个 `[Message origin]` 块开头，写明平台、会话 kind 与标题、
  chat id、thread id 和发送者

### Scenario: a DM turn names its own chat

- **Given** 一个已配对的 channel 与来自其 owner 的私聊消息
- **When** 该 turn 被驱动
- **Then** origin 块以 id 指明平台与该私聊会话，并省略私聊无意义的 thread 行

### Scenario: every turn carries its origin

- **Given** 一个已跑过一个 turn 的已配对 channel
- **When** owner 发出第二条消息
- **Then** 该 turn 的文本同样以自己的 origin 块开头——来源不是只出现在首个 turn 的头部

### Scenario: a slash command keeps its leading slash

- **Given** 一个已配对的 channel
- **When** owner 发送 `/help`
- **Then** 它仍按命令处理（不会被前置 origin 块，也不会创建会话）

### Scenario: list available agents

- **Given** 一个运行中的守护进程
- **When** 询问平台它提供哪些 agent
- **Then** 受管 agent（`claude_code`、`codex`）被列出，各带显示名与可用标志，
  `builtin` agent **不**在其中
  （[Built-in Agent Is Internal](../../docs/decisions/builtin-agent-is-internal-capability.zh.md)），
  且该列表可从 REST API 取到

### Scenario: choose an agent when starting a conversation

- **Given** 一个运行中的守护进程
- **When** 为某个受管 agent 带工作目录创建一段会话
- **Then** 该会话记下这个 agent 和它的配置

### Scenario: reject an unknown agent or invalid agent configuration

- **Given** 一个运行中的守护进程
- **When** 用没有任何 agent 提供的 `agent_key`、或用一个并不存在的目录作为工作目录
  创建会话
- **Then** 两者都作为领域错误被拒绝，且什么都没有被持久化。*缺省*工作目录不算无效
  ——它回落到 Coffer 托管的工作区

### Scenario: send a message and receive a streamed reply

- **Given** 一段绑定到已注册 agent 的会话
- **When** 启动一个 turn
- **Then** turn 事件按序流出——开始、文本增量、完成——且 assistant 回复被持久化

### Scenario: observe a turn started from another surface

- **Given** 某段会话上已有一个 turn 在跑
- **When** 第二个订阅者接入该会话的事件总线
- **Then** 它从头收到当前 turn 的事件，然后转为实时跟随，因此中途接入的订阅者
  不会漏掉任何东西

### Scenario: second message queues during a streaming turn

- **Given** 一个 turn 正在流式输出
- **When** 同一段会话上又发来一条消息
- **Then** 它被接受并入队而不是被拒绝，并在当前 turn 结束后作为自己的 turn 运行

### Scenario: editing a queued message re-queues it at the tail

- **Given** 一个流式 turn 后面排着一条或多条消息，一条一行
- **When** 编辑其中一条排队消息
- **Then** 这条消息离开队列、回到草稿区供修改，重发后被排到待处理队列的尾部

### Scenario: a queued message runs after the current turn

- **Given** 一条消息排在运行中的 turn 后面
- **When** 那个 turn 完成
- **Then** 排队的消息被提交为下一条用户消息并跑它的 turn，一条排队消息一个 turn

### Scenario: interrupting a turn pauses the pending queue

- **Given** 一个运行中的 turn，后面排着消息
- **When** 该 turn 被中断
- **Then** 当前 turn 停止，排队的消息被挂起、不自动运行，直到被恢复或丢弃

### Scenario: stop a running turn

- **Given** 一个已流出部分文本、仍在运行的 turn
- **When** 它被中断
- **Then** 流以一个终止的 turn-done 结束，stop reason 为 `interrupted`，
  且部分 assistant 消息以完成状态被持久化

### Scenario: reply survives a restart

- **Given** 一个已完成的 turn
- **When** 守护进程重启后读回该会话
- **Then** assistant 回复还在——事实来源是消息存储，不是实时流

### Scenario: manage conversations

- **Given** 一个运行中的守护进程
- **When** 创建、重命名、删除会话
- **Then** 每个操作都持久化，列表随之反映；被删除的会话及其消息被移除

### Scenario: archive and restore a conversation

- **Given** 一段在活跃列表里的会话
- **When** 它被归档
- **Then** 它离开默认的（活跃）列表、出现在已归档列表里，且没有被销毁；取消归档会把它
  放回活跃列表。归档一段不存在的会话会被拒绝

### Scenario: skills are reachable as tools

- **Given** 一个存有 skill 的 vault
- **When** 某个 agent 跑一个 turn
- **Then** vault 里的 skill 作为网关工具提供给它

### Scenario: model selection is recorded

- **Given** 一段已设定模型的会话
- **When** 一个 turn 完成
- **Then** assistant 消息记下产出它的那个模型

### Scenario: chat runs on the built-in model when no connection

- **Given** 一个运行中的守护进程，且该 agent 没有配置任何 Coffer LLM 连接
- **When** 打开 Chat 页面
- **Then** 草稿区可用、没有挡路的空状态，发出的 turn 跑在 agent 自带的模型与登录上——
  Coffer 的连接是可选的覆盖项，不是前置条件

### Scenario: token usage is recorded on the assistant message

- **Given** 一个会完成的 turn
- **When** 该 turn 结束
- **Then** assistant 消息记下这个 turn 的 token 用量

### Scenario: a group turn is acknowledged by typing in the group

- **Given** 一个在会打字、且没有 reaction 的 adapter
  （SeaTalk）上的已配对群
- **When** owner 在该群的某个线程里 @mention bot
- **Then** 打字提示被发往群打字端点，携带该群的 id 与该线程的 id——而不是发往私聊端点

### Scenario: a quoted message is named in the turn's origin

- **Given** 一个已配对 channel，其入站消息引用了一条更早的消息
- **When** 该 turn 被构建
- **Then** origin 块写明被引用消息的 id，且传输不发起任何取回被引用消息内容的调用

### Scenario: a DM thread grounds its turn in the thread's own messages

- **Given** 一个在支持历史拉取的 adapter 上的已配对私聊，以及一条到达于既有线程内
  的消息
- **When** 该 turn 被构建
- **Then** 该线程自身的消息经私聊线程端点拉取并折入这个 turn，与群线程的做法完全一致

### Scenario: being removed from a group stops that group's sessions

- **Given** 一个带有 live 会话的已配对群
- **When** 平台报告 bot 已被移出该群
- **Then** 该 chat 的会话被停止，且不向该群回发任何内容

### Scenario: a group turning external is announced in the group

- **Given** 一个 bot 仍身在其中的已配对群
- **When** 平台报告该群已被转为外部群
- **Then** 向该群发出一条警告，且该 channel 继续正常工作

### Scenario: 富回复保住它的 markdown 结构

- **Given** 一个平台能渲染富文本的传输，
- **When** 某个 turn 的回复包含标题、列表和表格，
- **Then** 回复以平台的富格式送达且结构完好；平台若拒绝它，则回退到普通渲染器
  且不丢失回复。

### Scenario: 在平台自有控件上按下的停止能结束 turn

- **Given** 一个实时面已声明停止控件的运行中 turn，
- **When** 平台上报用户停止了生成，
- **Then** turn 被中断、待处理队列被暂停，与打字的 `/stop` 完全一致。

### Scenario: 隐私模式与配置矛盾时被报告

- **Given** 一个被配置为响应未点名群消息的渠道，
- **When** 它的 bot 读不到群消息，
- **Then** 该渠道的健康面报告这个矛盾并指出修法。

### Scenario: 超大入站文件会告知用户

- **Given** 一条携带了超出平台允许 bot 下载大小的文件的消息，
- **When** 该消息驱动一个 turn，
- **Then** 用户被告知该文件取不到，而不是文件被静默丢弃。

### Scenario: 命令菜单与实际存在的命令一致

- **Given** 渠道的命令清单，
- **When** 传输层注册它的命令菜单，
- **Then** 渠道处理的每一条命令都被注册。

### Scenario: 通过链接配对会消耗掉配对码

- **Given** 一个以 start 链接形式发放的配对码，
- **When** owner 打开该链接，
- **Then** 渠道与该发送者完成配对，且配对码像手打时一样被消耗。

### Scenario: 群里的回复挂在它所回答的消息上

- **Given** 群里一条点名的消息，
- **When** turn 作出回复，
- **Then** 回复以平台级 reply 的形式送达那条消息。

### Scenario: 群里的回复会 @ 提问的人

- **Given** 群里一条点名的消息，且传输层报出了发送者的身份，
- **When** turn 作出回复，
- **Then** 回复以该成员的平台 mention 标记开头。

### Scenario: 单聊的回复不带 mention

- **Given** 同一个渠道在 1:1 聊天里作答，
- **When** turn 作出回复，
- **Then** 回复不带 mention——那里没有需要消歧的对象。

### Scenario: 流式的群回复在被创建时就已经 @ 上了提问的人

- **Given** 一个群 turn 在还没有任何内容可说之前就打开了 live surface，
- **When** 第一个快照被发出、随后回复就地生长，
- **Then** mention 标记就在这条消息被创建时的内容里，之后每个快照也都带着它，且各只带一次。

### Scenario: @ 通知取决于创建这条消息时带不带 mention

- **Given** 那个把回复创建成一条流、再让它生长的传输层，
- **When** 回复被送达，
- **Then** mention 随「创建」那一次调用出去——因为平台是在那一刻决定 @ 通知的，
  而不是在同一条消息的任何后续更新上。

### Scenario: 中间快照以原样抵达聊天，而不是被当成标记解析

- **Given** 一个在途的回复快照，截在词中间，因而可能结束在一段未闭合的强调标记里，
- **When** 它按「携带 mention」所要求的那样以平台富文本格式发出，
- **Then** 它的格式字符被转义——每个只转义一次——于是读者看到的是 agent 目前写出的文本。

### Scenario: mention 的目标值能原样穿过 markdown 转义

- **Given** 一个 mention，其目标值里含有平台 markdown 转义器本会转义的字符
  （带下划线的 id，或一个 email 地址），
- **When** 回复为该平台渲染，
- **Then** mention 标记逐字节送达，而它周围的文本照旧被转义。

### Scenario: 没有 id 的发送者改用地址来 @

- **Given** 群里一条消息，其成员只被传输层报出了 email，而平台另有按地址 mention 的写法，
- **When** turn 作出回复，
- **Then** 回复按地址 @ 他；当两者都已知时，用 id。

### Scenario: 跨组织的发送者依然能被识别出来以供 mention

- **Given** 一条来自 bot 所属组织之外的发送者的群 @mention，其组织内标识符到达时为空，
- **When** 传输层归一化这条消息，
- **Then** mention 所需的那个平台 id 被保留下来，而不是跟着一起被丢掉。




## Channels as a management plane（北极星）

channel 被管理的方式，与 Coffer 管理 MCP server、memory、skill 的方式一致：在一处
注册、配凭据、配置、并观测用户经聊天触达其 agent 的每一种方式。真正的差异化能力
——任何 agent 原生或官方 channel 都无法提供——是**一个 bot 控制所有 agent**：单个
已配对的 SeaTalk/Telegram bot 驱动*任意*受管 agent 并在它们之间切换，于是用户从一个
chat 里运行整个 agent 舰队。

这个平面下有两类 channel：

- **Coffer-hosted channel（本 spec 的 adapter）。** Coffer 运行 SeaTalk / Telegram
  adapter，规范化每条消息（媒体下载、转发展平、owner-gate、审计、vault），并为一个
  turn 驱动**任意**受管 agent——可按会话切换，且（因为每个线程都是自己的会话，
  FR-032）可按线程切换，于是一个 bot 能在一个线程里跑 Claude Code、在另一个线程里跑
  Codex。这是 Coffer 的护城河：没有自己 channel 的 agent（Claude Code、Codex）**只能**
  经此触达 IM；且 **SeaTalk 对每个 agent 都是 Coffer-hosted，因为
  没有任何外部网关会说 SeaTalk。** 整个 spec channels——包括下方的增强（FR-028…FR-042）
  ——描述的都是这条路径。保持其 agent 无关的那一处接缝：每条入站消息都变成文本加上
  磁盘上的 `Attachment(path, mime, filename)`，每个 agent adapter 按自己的方式物化附件
  （Claude 内联图片/PDF；Codex 收到文件路径；音频在上游被转写）。
  channel 层从不按 agent 分支。
- **Externally-hosted channel 是非目标（non-goal）。** 一个 agent 原生网关（独立运行的
  OpenClaw、Hermes）或一个官方厂商集成（Claude-in-Slack、Codex-in-Slack、
  Cursor-in-Slack、Claude Code 官方的 Telegram/Discord/iMessage 插件）拥有自己的传输、
  只驱动它自己的 agent。Coffer 既不代理它们、也不代管它们：把 Coffer 的 channel 架在
  前面会与它们自己的运行时冲突；把一个 token 存下来又写进外部进程自己的配置文件，等于
  作废了 vault（密钥必须加密到用时才解密）；而官方云端集成根本没有本地凭据可托管。用户
  想用其中之一时，就走那个工具自己的流程——Coffer 的文档给个指引，仅此而已。一个
  原生/官方 channel 不支持某平台（如 SeaTalk）时就单纯不在那里运行；**Coffer 不会把它
  桥接到 SeaTalk 上。** Coffer 的 channel 管理面只管理 Coffer 自己 host 的东西。

因为对多数 agent 而言官方 Telegram/Slack 集成要么不存在（Codex/Gemini/OpenCode 没有
官方 Telegram；SeaTalk 没有任何官方东西），要么是单 agent、且常常仅云端，所以
Coffer-hosted channel 与它们并不冗余——它是通往统一、本地、多 agent 控制的唯一路径，
而下方的增强正是官方个人桥所缺的 group/thread/voice/media 能力。

### E. Unified channel management and one-bot-all-agents

- **FR-040**: 一个 bot 控制所有 agent。单个已配对的 Coffer-hosted bot 驱动任意受管
  agent，经 `/agent` 与选择卡片切换；agent 选择按会话生效，且因为每个线程都是自己的
  会话（FR-032），一个 bot 能在不同线程里并发运行不同 agent。
- **FR-041**: Coffer-hosted channel 有一个统一的管理面。一个管理视图列出每个
  Coffer-hosted channel——连同其 status、已配对 owner、agent 与 health，与 MCP-server /
  memory / skill 的管理面一致；每个 channel 的凭据（bot token、app secret）都存在 Coffer
  vault 里。externally-hosted channel 不在范围内（non-goal）。

### A. Media pipeline completeness

- **FR-028**: SeaTalk 入站媒体覆盖所有类型，而不只是图片。`handle_event` 用 app token
  下载文件/文档、视频、语音/音频——每个都成为一个 `Attachment`——就像它已对图片所做的
  那样。一个直接发的 PDF 或语音备忘录像照片一样驱动一个 turn；只有一条既无文本也无
  可下载内容的消息才仍然得到「发文本、图片或文件」的回复。
- **FR-029**: 线程历史里的媒体被下载，而非展平成一个失效链接。当 owner 在一个线程内
  @mention bot 时，`fetch_thread` 下载该线程自身消息携带的图片/文件（递归其中嵌套的
  转发记录）并挂到 turn，与既有的展平文本并列。（此前线程媒体只作为 agent 无法打开的、
  需鉴权的 `[image] <url>` 出现。）
- **FR-030**: PDF 与 office 文档以抽取文本触达每个 agent，而非作为视觉输入。一个文档
  附件被文本抽取进一个上下文块，于是路径原生 agent（Codex）与视觉
  agent 都能看到其内容；图片对支持它的 agent 仍保持视觉内联。
- **FR-031**: SeaTalk 出站媒体被投递且线程感知。`send_media` 接到 SeaTalk 的文件上传 API
  （`supports_media` 为 true）；一个 agent 的 `MEDIA:/path` sentinel 把文件发回该 turn
  来源的**同一** chat **与**线程——一张生成的图表回到群线程，而非主聊天区（补上了此前
  SeaTalk agent 根本无法回文件、以及出站媒体忽略线程的缺口）。

### B. Conversation model

- **FR-032**: 每个群线程是自己的会话。会话身份以 `(channel, chat_id, thread_id)` 为键，
  而非只按 peer。一个 DM（`thread_id=""`）是一个会话；群里的每个线程都是独立的——各有
  历史、各有 turn 锁。一个群里不同线程的并发 turn 不再冲突在单一会话上（那个「a turn is
  already running」错误）。配对/owner 身份仍留在 peer 行上。
- **FR-033**: 入站附件在后续 turn 上仍可见。持久化的用户消息把附件*引用*记为一个
  `AttachmentBlock`（path、mime、filename；bytes 留在媒体目录、绝不进 chat DB）——单一
  事实来源。turn 任务通过从历史里最后一条用户消息读回引用来为当前 turn 重新物化附件（而
  非向下线程传递一个参数），因此物化能在守护进程重启后存活、并与网页所见保持一致；作用域
  限于会话内（无跨会话／切换 agent 的全历史重放）。path 留在守护进程内部：只有必须读取
  bytes 的 agent 适配器见得到它。媒体目录由保留节奏上的 30 天 mtime
  清扫界定大小（bytes 可重新下载；无大小上限）。见
  [Persisted Attachment Reference](../../docs/decisions/persisted-attachment-reference.zh.md)。
- **FR-042**: 每个 turn 都带上自己的来源。turn 文本以一个 `[Message origin]` 块开头，
  写明平台、会话（kind、平台白送时的会话标题，以及始终存在的 chat id）、线程和发送者
  （显示名**以及**稳定的平台 id——SeaTalk `employee_code`、Telegram `from.id`；平台工具调用要的是它，
  而在群里它无处可寻，因为 `chat_id` 是群的）——
  于是被问到「这是哪个群」的 agent 直接从收到的 turn 作答，而不是列出 bot 所在群再去推断；
  平台工具调用（发群消息、查群信息）也有了明确的 chat id 可用。该块在命令识别之后（加了前缀的
  `/help` 会不再是命令）、空信封检查之后折入，并像线程上下文（FR-029）一样持久化在用户消息
  上——单一事实来源（FR-033）仍是一个字符串。它出现在**每一个** turn 上，而不只是会话的第一个：
  `/agent` 可以在会话中途切换 agent（FR-040），resume 的 session 否则会丢掉它。标题与发送者
  名字可由群成员设置，因此两者在进入 prompt 前都被压成一行并截断——改名无法伪造出额外的
  origin 行。平台白送会话标题时就带上（Telegram `chat.title`）；不给时（SeaTalk 群事件只带
  `group_id`）就只用 id 指名该会话，agent 可以通过平台自己的工具把 id 解析成名字。

### C. Group UX and gating

- **FR-034**: 群里的选择卡片点选路由到该群/线程。`InboundCallback` 携带
  `chat_kind`/`thread_id`，并由该群的 peer 做 owner-gate（`get_by_chat`，而非单 peer 的
  `get`）；一次按钮点选的回复落到同一群/线程，而非 DM。
- **FR-035**: 按群的入站门控可配置。一个 channel 可以设置 require-mention（群里默认开——
  bot 只在被 @mention 或被回复时才作答），以及 ignore-messages-that-@-someone-else（选择性开启——
  一条 @ 了任何非 bot 用户的群消息被静默丢弃，即便它同时也 @ 了 bot）——于是一个坐在繁忙群里的
  bot 只在它应当作答时才作答。两者都是普通的配置布尔值；无论如何 channel 始终由 owner 门控，
  所以这管的是「何时作答」，而非「谁能驱动 turn」。

### D. Platform polish

- **FR-036**: 收到与进度被确认，按能力（而非按 transport 类型）门控。在支持 reaction 的
  transport（Telegram）上，一个 ack reaction（👀）立即在用户自己的消息上标记收到，一个 ✅
  在干净完成时标记完成（出错/被打断的 turn 只保留收到标记）。不支持 reaction 的 transport
  （SeaTalk）改用它的 typing/working 信号作为收到与进度的提示。全部尽力而为——一次失败的
  ack 绝不打断 turn。
- **FR-037**: 回复就地生长，用平台各自具备的 live-text 机制——该机制由 adapter
  声明的能力（而非其类型）决定。内核真正要问的能力是 `supports_live_text`（「有没有
  一个我能在 turn 运行期间持续更新的界面？」），而**不是** `supports_edit`（「一条
  已投递的消息能否被改写？」）。Telegram 用编辑同一条状态消息回答「有」；SeaTalk 则
  用它的消息**流式**（streaming）API（`init_stream` / `update_stream`）回答「有」——
  尽管它依然完全不能编辑任何消息。这个标志的含义之所以要改，是因为把策略挂在
  `supports_edit` 上，等于悄悄剥夺了 SeaTalk 本就支持的实时体验：它的回复只能在 turn
  结束后以若干条分块消息、一段一段地蹦出来。`supports_edit` 现在只表示它字面的意思
  ——在 SeaTalk 上 `edit_text` 仍然抛错——两个标志各自独立声明。
  一个 turn 只保留**一个** live 界面。它**何时**打开，取决于这个界面究竟会变成回复本身，
  还是只是收尾时丢弃的脚手架——由 adapter 以 `live_text_persists` 声明。会留存的（SeaTalk：
  被流式出来的那条消息**就是**答案），在 turn 一开始就打开并说明自己已收到——这是用户
  看得见的致意，因为否则从发出消息到拿到答案之间的这段等待就是他们得到的全部，在长
  turn 上会被读成机器人根本没收到。这条致意不额外占一条消息：回复就是同一条，就地改写。
  而只是脚手架的（Telegram：一条在真正回复发出前被删掉的状态消息），仍然只在 turn 跑
  过更新间隔后才打开——要么由工具活动打开，要么由回复文本打开——于是更早结束的回复
  根本不打开界面，避免 create→delete→resend 抖动，何况它的 👀 回执反应已经表明消息被
  收到了。
  更新的**节奏归 transport 所有**，因为只有它知道自己的限速：内核把每一份快照都递过去，
  各个界面按自己能承受的频率做缓冲（SeaTalk 约 200 毫秒，正是它自己的文档为打字机效果
  给出的间隔；Telegram 则慢得多，因为它编辑的是一条真实消息）。内核若在上面再加一层
  节流，会把这层缓冲完全盖住，让流式变成一段一段地蹦出来。中途快照会裁剪到单条上限，
  并把其中的格式字符**转义**，因此过长或半成品 markdown 的预览既不会撑破平台解析器也不会
  超上限。之所以是转义而不是改发纯文本：这条消息从被创建起就必须能携带 @mention
  （FR-070），而 mention 只有在富文本里才是名字。
  界面如何**收尾**则是 transport 自己的事：Telegram 的状态消息只是脚手架——收尾时删除
  它，最终回复以 HTML 渲染并按段落分块发送；而 SeaTalk 的 stream **本身就是**那条回复
  ——它带着按 SeaTalk markdown 渲染的最终文本结束，于是没有任何内容被发两遍。完全没有
  live 界面的 transport 则不发任何中途信号，最终回复就是它的全部信号。
  SeaTalk 的流式约束属于契约，而非实现细节：每次更新携带的都是**全量**累积文本，绝不是
  增量（客户端渲染最新快照）；两次更新的间隔必须小于 30 秒，否则平台会终止该 stream，
  因此最后一份快照会在这个窗口内以 keep-alive 重发；单个 stream 最多承载 4096 个字符，
  超出预算的回复会在上限处按段落边界结束该 stream，余下部分以普通分块消息发送（回复
  的长度在它结束之前无从得知，若因为「可能」超长就干脆不流式，等于为了罕见情形剥夺
  每一个 turn 的实时回复）；以及，一个已经结束的 stream——正常完成、超时或出错——永不
  复用，因为平台会拒绝任何之后再指名它 id 的请求：该界面就地判定失效，不会另开一个
  替代 stream，改由普通发送路径完整投递这条回复（平台留下的那条半截消息就停在原处
  ——看得出是残留，但用户仍能拿到完整答案）。低于 3.67 的客户端只会在 stream 关闭时看到那条完成后的消息。
  能显示打字但**没有 reaction 可用来确认收到**的 transport（SeaTalk）另外维持一条
  周期性打字心跳（一个短暂动作，零聊天噪声），覆盖第一次 live 更新落地之前的那段
  窗口。它在 turn 所在的地方都跑，私聊与群线程一视同仁：SeaTalk 在
  直聊端点之外原来还有第二个打字端点（`group_chat_typing`，按线程作用域），此前这条
  心跳只限私聊，纯粹是因为相信不存在这样的端点。
  这个判据是「用什么确认收到」，不是「能不能编辑」：支持 reaction 的 transport
  （Telegram）已经用 👀 确认过了（FR-036），因此 `supports_edit` 现在不再决定任何行为。
  全部尽力而为——一次失败的更新、收尾或心跳绝不打断 turn。
- **FR-038**: Telegram album 是一个 turn。共享同一 `media_group_id` 的消息被去抖成携带
  它们全部附件的单个 turn，而非每张图一个 turn。
- **FR-039**: 入站事件被去重。一个被重投的平台事件（相同 message id）只被处理一次。
- **FR-056**: 被引用的消息只被点名，不被解析。用户以引用方式回复时，SeaTalk 的两类
  入站消息事件都携带 `quoted_message_id`；信封保留它，origin 块（FR-042）写明它，于是
  一个读到「如我上面所说」的 agent 能判断那个*上面*指的是某个具体的东西，而不是只能从
  可见文本里猜。传输刻意在这个 id 处止步。取回被引用消息的正文是一次有文档的调用
  （`get_message_by_message_id`），而平台自己的 MCP server 早已把它作为一个工具暴露
  出来——这使它成为一次由 agent 自行按需发起的查询，而不是无论有没有人要都得在每个
  turn 上做一遍的传输工作。这个 id 的作用域限于本 bot：平台刻意对不同 app 给同一条
  消息不同的 id，因此它是一个句柄，而非一个持久标识符。
- **FR-057**: 线程在私聊里同样为它的 turn 提供地基，而不只是在群里。FR-029 的线程
  上下文拉取，写于 SeaTalk 只有群聊才有线程的时候；如今与 bot 的私聊也能开线程，平台
  在群那个端点之外，把私聊线程放在了它自己的端点下
  （`single_chat/get_thread_by_thread_id`，以 employee code 为键）。adapter 按会话种类
  分流，其上的一切都没变——同样的展平、同样的媒体下载、同样在任何失败时降级为空。它
  消除掉的那处不对称是真实而不可见的：一个私聊线程本就已经被原地回复（FR-026），可驱动
  那条回复的 turn 却看不见该线程里的其他任何东西。群*主聊天区*的闲聊仍然从不拉取——那
  依旧是不想要的，权限也依旧没有获批。
- **FR-058**: bot 自己在一个群里的身份状态被跟踪。有两个平台事件改变的是一条绑定
  **是什么**，而不是驱动一个 turn——`bot_removed_from_group_chat`（被踢，或该群被解散）
  与 `group_chat_converted_to_external_group`——它们到达一条与消息、卡片点选分开的
  生命周期回调，于是后两者的任何消费方都不必再把它们过滤掉。被移除会停掉该 chat 的
  每一个 live 会话；不回发任何内容，因为 bot 已经不在那里、发不出去了。转为外部群意味着
  其他组织的人从此可以读到一个 owner 配对过的会话，这是一次与安全相关的变化，因此它被
  公告在那个群里，而不是只写进日志——owner 按定义就在场，而这个群是唯一能让这条警告
  有上下文的地方。两者都像其他每个事件一样去重（FR-039）：一次被重投的移除绝不能触发
  两遍。Telegram 把同一次离开报告为 bot 自身成员身份的变化（`my_chat_member`，平台在
  订阅的更新类型里没点名它时不会下发），而不是一个专门事件；它归一到同一条生命周期
  信封上，于是这条规则是一条规则，而不是一个平台一条。被**加入**刻意不算事件：谁都能
  把 bot 拉进群，而配对（FR-005）才是那道门。

### E. Turn 平台

自已退役的 Agent Chat 规范并入。这些需求描述的是**每个 channel turn 底下**那层机制——
注册表、适配器、会话存储与 turn 生命周期。它们原本独占一个 spec，是因为当时
Web 端 Chat 页面是它们的另一个客户端。那个页面又回来了（见下方 G 节），但描述仍留在
这里：一层平台，一份文档，好让「IM 消息 → turn → 回复」以及「同一个 turn 在浏览器里
被看着」这条完整链路在一处读完，而不是跨两个 spec。

- **FR-043**: 一个 turn 触达 agent 只能经由 **agent provider 注册表**：跑 turn、
  初始化会话、拆除会话的 agent 状态，都是拿会话上记的那个 agent 名字去问注册表。
  再加一个 agent 只能是加一条注册表条目——不得改动会话/消息 schema、turn 编排器
  或 channel 层。channel 层永远不按 agent 分支。
- **FR-044**: 每段会话必须用 `agent_key` 记下它属于哪个 agent，外加一份不透明的、
  agent 专属的配置，由被点名的那个 agent 校验并持久化。没有任何 agent 提供的
  `agent_key` 必须被拒绝，agent 拒绝的配置必须作为领域错误被拒绝——两者都发生在
  写入任何东西之前。channel 绑定在 peer 的第一条消息上解析的就是这个。
- **FR-045**: 平台必须通过 REST API 暴露它注册了哪些 agent——每个带稳定 key、
  显示名和当前可用标志——好让 channel 编辑器只提供真实存在的 agent，并标出那些
  CLI 不在本机上的。它同样必须按 agent 暴露该 agent 可以被切到的模型。
- **FR-046**: 一个 agent 通过**agent 适配器**被寻址来跑一个 turn；适配器是自足的：
  只给它会话历史，它产出一串类型化的 turn 事件。适配器自带模型、工具和配置，
  编排器不得注入这些。
- **FR-047**: 系统必须提供由子进程支撑的 Claude Code 与 Codex agent provider。
  每个都在一个工作目录里运行（它的 `agent_config.cwd`）；turn 没给工作目录时，
  provider 必须回落到 Coffer 托管的工作区 `~/.coffer/workspace`（首次使用时创建）
  而不是拒绝该 turn——这样一个没配工作区的 channel 开箱即用。显式给出的 cwd 必须
  是一个已存在的目录，否则配置被拒。可用性必须反映该 agent 的二进制在守护进程的
  PATH 上是否可解析；不可用的 agent 会被列出但不可选。turn 必须把工具的行分隔
  JSON 输出映射为平台的 turn 事件，并持久化上游 session id，使下一个 turn 接着
  同一个 session 跑。Claude Code 走 Claude Agent SDK，Codex 走 `codex app-server`
  （stdio 上的 JSON-RPC 2.0，NDJSON 分帧）；两者都以完整权限运行——owner 配对
  （FR-005）才是安全闸门。两者都必须在回复**写出的同时**以文本增量发出，而不是在
  turn 结束时整块给出——否则 FR-037 的实时面板没有东西可以生长，channel 里的回复
  会在长时间静默后一次性落地。Claude Agent SDK 只在被要求时才这么做
  （`include_partial_messages`），而且开启后它会同时给出增量和最终那条完整的
  assistant 消息，所以适配器必须扣掉已经发过的部分，让回复只发一次。
- **FR-048**: 系统必须把会话及其消息持久化在 SQLite 里作为事实来源；它们不建模为
  kind-agnostic Resource 框架里的 Resource。一条消息必须存下它的 role 和一个有序的
  content block 列表，类型为 `text`、`tool_use`、`tool_result` 和 `attachment`
  （FR-033）；assistant 消息在 agent 报告时还必须存下 token 用量与产出它的模型。
- **FR-049**: 会话必须遵循两段式、由保留策略管理的生命周期，两个窗口都在
  Settings → Data 下可配：保留 worker 先把超过自动归档窗口（默认 7 天）没有新消息
  的会话自动归档，再在归档若干天后（默认 30 天）删除已归档会话及其消息。任一窗口
  都可设为永久保留以禁用该段。自动归档可逆；只有删除是破坏性的。
- **FR-050**: 系统必须做到每个会话同时最多一个进行中的 turn，且不得拒绝在 turn
  运行期间发来的消息：这样的消息进入该会话的**待处理队列**。进行中的 turn 结束时，
  系统必须从队首出队、把它提交为下一条用户消息并跑它的 turn——顺序 FIFO，
  一条排队消息一个 turn，绝不合并。待处理消息在它的 turn 开始前不会进入消息序列。
  该队列在内存中，因此守护进程重启会丢掉尚未提交的部分。（turn 进行中从 channel
  到达的消息由该 channel 自己的入站缓冲承接，见 FR-027，而不是这个队列。）
- **FR-051**: 中断一个 turn 必须同时**暂停**待处理队列：当前 turn 停止并保留其部分
  输出，排队的消息被挂起、不自动运行，直到属主恢复它们。`/stop`（FR-011）触达的
  就是这里。
- **FR-052**: 系统必须把一个 turn 表达为一串类型化事件，至少覆盖 turn 开始、
  文本增量、工具调用、工具结果、turn 完成、turn 错误和待处理队列变化。
- **FR-053**: 系统必须把这些事件发布到每会话的进程内事件总线上，任意数量的订阅者
  都可以接入。接入时若有 turn 正在进行，总线必须重放当前 turn 的事件让迟到的订阅者
  跟上，然后转为实时流。turn 作为脱离任务运行，因此发起它的订阅者离开后它仍然存活
  ——这就是为什么 peer 的连接在 turn 中途断掉，回复依然跑完并被持久化。
- **FR-054**: 被中断的 turn——用户中断、适配器失败或守护进程重启——必须留下已持久化
  且标记为完成的部分 assistant 消息，而不是丢弃它。停止一个 turn 与丢弃会话不同，
  后者会把这个 turn 扔掉。
- **FR-055**: 每个完成的 turn 必须以 actor、agent、会话和该 turn 的 token 用量记入
  审计日志，使「哪个 agent 做了什么、由谁驱动」事后可查（channel 专属字段见 FR-030）。


### F. Telegram 平台能力对齐（Bot API 10.x）

Telegram 的 Bot API 10.1–10.3（2026 年 6–8 月）新增了一整族正好为这种形态的
bot 而造的接口面：一条随 agent 生成而流式增长的消息、平台自己绘制的停止控件、
结构化富文本，以及群里只有一个成员看得见的回复。前三项 Coffer 此前都有手工近似
实现——用编辑一条消息冒充流式、用打字的 `/stop`、用五个标签的 HTML 子集冒充
markdown——第四项则完全没有对应。下列要求把每一项迁到平台自己的机制上，同时保留
手工路径作为回退，因为用户实际连到的 Bot API server 不保证足够新。

- **FR-059**: 平台能力靠探测，不靠假设。传输层启动时读取平台对自身的描述
  （`getMe`），保留会改变它可做什么的字段——bot 身份，以及隐私模式是否还允许它读
  群消息。晚于用户实际连到的 Bot API server 才引入的能力（富消息、消息草稿、临时
  消息）只尝试一次，并在平台自己拒绝时**对该进程闩死**，回退到它所取代的机制。因此
  跑在旧 Bot API server 上的 Coffer 只在排版和实时性上降级，永远不在送达上降级。
- **FR-060**: 群可读性要被诊断出来，不能悄悄失效。Telegram bot 默认开启隐私模式，
  该模式使 bot 完全收不到普通群消息。一个被配置为响应未点名群消息
  （`require_mention = false`，FR-035）、但其 bot 根本读不到这些消息的渠道，在
  Coffer 里看起来是对的，在聊天里却什么都不做。渠道的健康面（FR-041）必须报告这个
  状态并指出修法（在 BotFather 关闭隐私模式，然后把 bot 重新拉进群）。
- **FR-061**: 回复在平台自有的富格式上渲染。agent 用 markdown 作答——标题、列表、
  表格、引用、围栏代码。Telegram 富消息原生承载全部这些，因此回复作为富消息发出，
  而不是被压平成 HTML 子集（那会把标题降成粗体、把项目符号降成一个字形、把表格原样
  当作竖线吐出）。原有渲染器保留为 FR-059 选择的回退。
- **FR-062**: 实时回复使用平台自有的流式接口面——**在平台对那种会话确实提供了一个的
  前提下**。当平台能在消息生成期间流式发送其局部内容时，live-text 句柄（FR-037）驱动
  它，而不是改写一条已送达的消息：没有要删的状态消息、不改写已送达的消息，进度显示
  频率也不再受编辑限流的天花板约束。若某个流式接口面平台只在部分会话里提供（Telegram
  的消息草稿面向私聊，没有群的形态），就只在那里用它；其余场合传输层保留原有机制，而
  不是每帧快照都去换一个被拒的调用、什么也显示不出来。超出该接口面所能承载长度的快照
  按尾部裁剪——被盯着看的是最新的字——因为一次被拒的快照会让进度指示在回复中途死掉。
- **FR-063**: 平台自有的停止控件能结束 turn。流式草稿可以声明一个由平台绘制的停止
  按钮；用户按下后平台上报被停止的草稿，Coffer 必须把它路由到与 `/stop` 相同的中断
  路径——同样的 turn 取消、同样的队列暂停（FR-051）、同样的用户可见结果。一个看得见
  却停不掉任何东西的停止按钮比没有更糟，因此只在这条路已接通的传输上声明该按钮。
- **FR-064**: 不是答案的絮语在群里保持私有。命令输出和错误是说给某一个成员听的，不是
  说给整个房间的。当平台能投递一条只有该成员客户端会显示的消息（Telegram 临时消息）
  时，Coffer 对这些使用它；agent 真正的回复始终是群可见的普通消息。这是 FR-024 的群
  噪音另一半：那条要求管住 bot 不对什么都**行动**，这条管住它不把什么都**说出声**。
  **选择卡刻意排除在外。** 卡片是唯一一种用过之后必须被**改写**的接口面（FR-018），
  而私密投递的消息走的是另一套寻址——Telegram 改写普通卡片用 `chat_id` + `message_id`，
  改写临时消息用 `chat_id` + `receiver_user_id` + `ephemeral_message_id`，且文档明写
  这次编辑不保证能送达用户。一张无法被可靠改写的卡片会继续提供已经被选走的选项，而这
  正是 FR-018 要防的事，所以在改写和发送一样可靠之前，卡片保持为普通消息。
- **FR-065**: bot 要做自我介绍。它的命令菜单从 Coffer 自己的命令清单注册到平台上，
  它的文字简介（描述、简短描述）**在为空时被填上**，于是第一次打开 bot 的用户看到的
  是它是什么、接受什么，而不是一个空聊天。注册的菜单必须列出渠道实际处理的每一条
  命令——帮助文本提供而菜单遗漏的命令是漂移 bug，不是设计取舍。owner 已经写好的文案
  以及 bot 的名称属于他们的品牌决定，不得覆盖。
- **FR-066**: 配对只需一次点击。当平台支持带参数的 start 链接时，配对码（FR-005）以
  承载它的链接形式发放，于是 owner 通过打开链接完成配对，而不是在手机上誊抄八个字符。
  手打配对码继续有效——链接只是额外的入口，两者适用同一套一次性、TTL 受限、尝试次数
  受限的门禁。
- **FR-067**: 每种入站媒体类型都能驱动 turn，否则说明为什么不能。平台能挂在消息上的
  一切——照片、文档、语音、音频、视频、动图、贴纸、圆形视频——都会被下载并成为
  `Attachment`（FR-020）。当平台对 bot 可下载的大小设上限时，超限文件必须产生一条
  告知用户的消息，而不是静默的空操作：要修的失败模式是「用户发了个文件，却得到一个
  从头到尾没提这个文件的回答」。
- **FR-068**: 回复要挂在它所回答的那条消息上。在群里，bot 的回复必须以平台级 reply
  的形式发给触发它的那条消息，于是热闹的房间能分辨每个回答属于哪个问题。
- **FR-069**: 选择卡使用平台的按钮词汇。当平台提供超出标签之外的按钮语义——禁用态、
  意图色——卡片就用上它们，于是已经选过的选项显示为禁用而不是再次提供。
- **FR-070**: 群里的回答要点名它是给谁的，并且要真的把对方叫醒。在群里，bot 的回复必须
  以 @mention 驱动该 turn 的那位成员开头，使用平台自己的 mention 标记——于是回答会提醒
  正在等它的那个人，热闹的房间也能一眼看出它属于谁。在单聊里则必须不这么做：1:1 的会话
  没有需要消歧的对象，在那里 @ 只是在喊。四条约束框住它。
  - **mention 必须位于这条回复被「创建」时的内容里**，不能事后补上。平台是在消息创建的
    那一刻决定 @ 通知的；一个在同一条消息的后续更新里才到达的 mention，会渲染成名字却
    通知不到任何人——这是两头最差的结果：满屋子都看见一个 @，而被 @ 的人从未收到。对流式
    回复而言，这意味着开场那一帖就要带上它，于是中间的每一个快照也必须带：一个在创建时
    出现、在整段流里消失、最后又回来的 mention，是肉眼可见的故障。
  - 既然每个快照都带上了标记，每个快照就都必须以平台的富文本格式发出。纯文本格式过去为
    「截在词中间的回复」提供的那层保护——客户端会把未闭合的强调标记渲染成噪音——必须改由
    **转义** agent 的半截文本来提供，而 mention 标记本身不得被转义。
  - mention 由**平台**用来寻址成员的那个 id 构造，而它未必等于 owner gate 比对的那个 id
    （SeaTalk 用 `employee_code` 把关、用 `seatalk_id` 做 mention，而当发送者不在 bot
    所属组织内时 `employee_code` 会是空）——所以传输层两个都要带。当平台另有一种寻址成员
    的写法时（SeaTalk 也支持按 email 做 mention），它只是「id 缺失时」的**兜底**，绝不是
    首选：id 才是那个总是存在的标识符。
  - 并且它静默降级：没有 id 也没有可用的兜底，或传输层无法仅凭 id 做 mention，就发一条
    普通的、不带 mention 的回复——绝不发出一个破碎的标签。
- **FR-071**: 模型归 channel 管，不归 agent 管。channel 必须带自己的 `default_model`
  （在本 channel 上**新开**的会话所用的模型）和自己的 `models` 允许范围，并且这必须是
  施加在它身上的**唯一**策展：agent 资源只管一个人直接打开那个 agent 时用什么，而
  channel 是另一个地方、另一批受众。三条推论。本 channel 新开的会话在设了
  `default_model` 时就开在它上面，抵达 agent config 的路径与 `default_agent` /
  `default_agent_config` 相同；为 `None` 则什么都不钉，agent 的 CLI 默认生效。当允许
  范围非空时，`/model` 卡片恰好只提供这个范围，顺序就是用户排的顺序，于是卡片绝不会
  出现一个下一条就会被拒的选项。以及 `/model <id>` 落在非空允许范围之外时**必须**被
  拒绝，并在消息里点名允许的 id，而不是把会话悄悄带去卡片从未提供过的地方。范围为**空**
  意味着**未策展**——bound agent 提供的每个模型都允许——绝不是「没有模型」，于是没人
  配过的 channel 的行为与本条要求存在之前完全一致。id 保持不透明：它原样交给 CLI，绝不
  对照 agent 的 catalogue 校验，因为后者随每次 CLI 升级而变。**在网页界面上**，这两个字段
  位于 channel 的新建 / 编辑对话框里，紧挨着所绑定的 agent：一个「默认模型」下拉框，永远
  提供一个显式的「不指定」选项，选项来自所绑定 agent 的 model catalogue——一旦设了允许范围
  就收窄到该范围，于是表单拼不出后端会拒绝的组合；以及一份覆盖同一份 catalogue 的「可选范围」
  勾选清单，在什么都没勾时明说「未限制」，而不是读起来像「没有模型」。表单必须镜像本条要求
  自己的规则（非空范围之外的默认模型在发请求之前就被拒绝；取消勾选被钉住的模型会同时取消钉住），
  并且在重新绑定 `default_agent` 时必须把两者清空——那些 id 属于上一个 agent。

### G. Web 端 Chat 页面

Turn 平台有第二个接口面：Web UI 里的一个 **Chat 页面**，对着的正是 channel 驱动的那些
会话。它随 Agent Chat 规范交付，2026-09-10 因未被使用而删除，2026-09-12 又恢复——因为
它能做而任何 channel 都做不到的那件事，是让属主在电脑上旁观、接手并继续一段正用手机
驱动的会话。它所依据的决策记在
[Chat 是单属主实时镜像](../../docs/decisions/chat-single-owner-live-mirror.zh.md)。

- **FR-072**: Web UI 必须承载一个 **Chat 页面**：两栏，左边是会话列表，右边是所选会话的
  消息线程与它的草稿区。列表必须列出库里的每一段会话，不论它由什么打开——由 IM channel
  创建的会话同样被列出、可读、可实时旁观、可从页面继续，并带一个标明它同时可从哪个
  channel 触达的徽标。不存在「只属于 Web 的会话」这种类别：页面与 channel 是同一条时间线
  上的两扇窗，由同一个属主驱动，agent 无从分辨一个 turn 从哪扇窗进来。
- **FR-073**: 会话列表必须支持新建、重命名、归档、取消归档与删除。归档把一段会话移出默认
  的（活跃）列表、放进已归档列表，**但不销毁它**；取消归档把它放回活跃列表。删除会移除
  该会话及其消息，并取消其上进行中的 turn——有破坏性的是删除，归档没有。指向一段不存在
  的会话的操作必须被拒绝。
- **FR-074**: 从页面发送必须是**发完即返回**：`POST .../messages` 接下消息、启动或让它入队，
  然后立刻返回（202），不携带这个 turn 的任何输出。Turn 输出只从一个地方消费——
  `GET .../events` 这条 SSE 订阅——于是「我发起的 turn」与「我手机发起的 turn」走同一段代码，
  发送方从来不是特例。接入时该订阅必须从当前 turn 的开头重放它的事件，然后转为实时跟随
  （FR-053），因此中途接入的客户端不会漏掉任何东西；没有 turn 在跑时，它必须保持打开，
  并在下一个 turn 开始时把它送出来——不论这个 turn 由哪个接口面发起。
- **FR-075**: 有 turn 在跑时草稿区**不得**锁定。turn 期间发出的消息加入待处理队列（FR-050），
  并按队列顺序各自显示为一行，一条消息一行。队列中的一行必须可移除，也必须可编辑——编辑
  的做法是把它从队列里取出、放回草稿区去改；改完重发则把它排到队列**尾部**，因为这是一次
  新的发送，而排在它后面的那些是先入队的。`PUT .../pending` 整体替换队列，替换后的队列
  必须走事件流（FR-052），好让第二个标签页、以及手机，渲染出同一份行。
- **FR-076**: 页面必须能中断它正在旁观的那个 turn——不论由哪个接口面发起——走
  `POST .../interrupt`，语义即 FR-051：turn 停止并保留、持久化其部分输出，待处理队列被
  **挂起**，而不是自动推进到刚被停掉的那个 turn 里去。
- **FR-077**: 消息线程必须把一个 turn 的工具调用渲染成各自的卡片，而不是揉进正文：每张卡片
  点名工具、显示它被传入了什么、并在结果到达后显示结果，好让读者看见 agent **做**了什么，
  而不只是它说了什么。文本块与工具调用块按 turn 发出它们的顺序排列，结果尚未到达的卡片
  读起来就是还在跑。
- **FR-078**: 页面必须让属主经 `GET|PATCH .../agent-config` 读取与设置会话的 agent 配置——
  它跑在哪个 agent 上、那个 agent 被放在哪个模型上——持久化模型的同时保住会话的工作目录与
  上游 session id，清空则回落到 agent 自己的默认。缺少 Coffer 的 LLM 连接**不得**挡住这个
  页面：一个都没配时，草稿区照样接受消息，turn 跑在 agent 自带的模型与登录上，因为 Coffer
  的连接是可选的覆盖项，不是前置条件（见
  [Provider Switching](../../docs/decisions/provider-switching.zh.md) 的 2026-06-22 修订）。

## Deliberately out of scope

**复制到剪贴板按钮。** Telegram 的 inline 按钮可以带 `copy_text`，那样 agent 就能把一条
命令作为可点击的东西交出去，而不是让用户手工框选文本。不采纳，因为按钮是容易的那一半：
`ChoiceButton` 目前只由 agent 卡和 model 卡构造，agent 根本没有途径去**请求**一个。要给它
这条途径，就得在 `MEDIA:` 之外再加一个面向 agent 的 sentinel——那是一个有自己的解析、自己
的误判风险（普通散文里的误触发）、自己的 spec 的功能，而不是在既有按钮上加一个字段。
记在这里，免得把它当成遗漏。

**私密投递的选择卡。** 见 FR-064：卡片是唯一一种用过之后必须被改写的接口面，而临时消息的
改写走的是另一套寻址，且平台不保证送达。要做的工作是整套临时消息编辑方法
（`editEphemeralMessageText` / `editEphemeralMessageReplyMarkup`），外加在已投递的卡片上
携带 `ephemeral_message_id` 的办法，而且做完之后改写仍然不如发送可靠。只有在平台把那次编辑
做得和普通编辑一样可靠时才值得重开。

**Coffer 没有采用的两项 SeaTalk 卡片能力。** 平台的卡片格式还提供 `redirect` 按钮
（带 `mobile_link` / `desktop_link`）与按语言分版的卡片正文
（`{"default": …, "zh-Hans": …}`）。两者都未采用。redirect 按钮需要一个可去之处，
而 Coffer 的 Web UI 绑在 loopback 上——从属主手机点过去什么也到不了。按语言分版的卡片
前提是 Coffer 的 channel 文案存在多个语言版本；后端目前只有英文，而且这张卡片会成为
整段会话里唯一被翻译的界面——其余每一行都来自 agent，用的是属主当时写下的那种语言。
之所以写在这里而不是默默略过，是因为发现它们的那次调研，正是卡片这部分工作得以成立的
前提。

**SeaTalk 的 WebSocket 事件投递。** 平台现在提供了第二种接收事件的方式：bot 不再验证
一个公网 callback URL，而是与 SeaTalk 保持一条长连的 WebSocket，只需要出网连通性。
对一个 local-first 的金库来说，这显然是那个对的传输——它会把属主今天必须自己搭起来的
隧道（cloudflared/ngrok）、终结这条隧道的监听进程，以及那套只因为 callback 从公网可达
才存在的签名校验，统统删掉。它没有被采用，理由有两条，而且都不在本项目的掌控之内。
其一，线路协议（wire protocol）完全没有文档——公开材料只讲了怎么调用一个厂商 SDK；
其二，那个 SDK（Go 与 Python）从一个内部企业 GitLab 分发，在公共 PyPI 上根本不存在。
Coffer 是 MIT、受 OSS 约束，因此它既不能依赖这个 SDK，也不能去重新实现一个无人公开的
协议。写在这里而不是留作一次沉默的省略：一旦该协议被公开、或该 SDK 上了 PyPI，这就会
成为首选的入站路径，隧道也随之变成可选。


**挂在 chat 前缀下的 agent 注册表。** agent 注册表列表与按 agent 的模型清单曾经答在
`/api/v1/chat/agents` 与 `/chat/agents/{key}/models`，页面被撤下时它们搬去了
`GET /api/v1/agent-providers` 与 `/agent-providers/{key}/models`。页面回来了，它们仍留在
那里。这两者从来就与「会话」无关——channel 编辑器调第一条来列可绑定的 agent，agent 详情页
调第二条来提供模型——一个页面恰好要用它们，并不能把它们变成 chat 路由。Chat 页面就从它们
所在的地方读。

**Chat 作为「Vault Console」。** 更早的一次定位，把这个页面做成「对金库说话」的席位，
以及逐条审批 agent 工具调用的席位。两者都不随它回来。内置模型是内部的 `coffer__*` 能力，
而不是一个聊天人格（[Built-in Agent Is Internal](../../docs/decisions/builtin-agent-is-internal-capability.zh.md)），
工具审批则被整体删除，属主配对才是那道门
（[Remove Tool Approval](../../docs/decisions/remove-tool-approval.zh.md)）。G 节恢复的是
实时镜像，也只有实时镜像。

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
