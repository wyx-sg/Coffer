# Research：Channels

> English: [research.md](./research.md)

设计前收集的背景：成熟的开源 agent 如何集成消息 channel，以及 Telegram
与 SeaTalk 平台到底要求什么。来源：OpenClaw 文档与 channel-plugin SDK、
NousResearch hermes-agent 文档与源码、SeaTalk 官方 `cs-bot` 仓库与开放
平台文档镜像。

## 先例 —— OpenClaw 与 Hermes

两款产品收敛到了同一种架构，本 spec 即采用之：

- **薄 adapter，共享内核。** adapter 只实现生命周期（connect/
  disconnect）、出站发送，以及把入站消息规范化成标准信封 (envelope)。
  会话路由、命令解析、配对/安全与渲染策略都放在共享内核。
  Hermes 的 `BaseAdapter` 恰好只有三个方法；OpenClaw 的 `ChannelPlugin`
  从 `id` + `setup` 起步，再加可选的能力 surface。
- **声明能力而非特判。** OpenClaw 的 adapter 声明传输层支持什么（编辑、
  原生流式、媒体）；内核自动降级。正是这一点让 Telegram 通过编辑一条
  消息来流式展示进度，而 SeaTalk 回退到「先确认、后给最终回复」，内核
  里没有任何 `if telegram` 分支。
- **配对是默认的私聊策略。** 两者都默认拒绝。Hermes 和 OpenClaw 都使用
  无歧义字母表的 8 字符码、1 小时 TTL；Hermes 还加了按用户限流与失败
  锁定，并且有一次因 fail-open 的初始化路径而记录在案的安全事故 ——
  channel 必须 fail closed。
- **会话映射。** 以 `(channel, account, chat)` 为键的、按 peer 的长生命
  周期会话，配 `/new` 式重置；OpenClaw 警告任何更粗的粒度都会把上下文
  在用户间共享。
- **长 turn 的体验分三层。** 立即确认（typing/reaction）、一条复用的可
  编辑进度消息（缓存 `(chat_id, status_key) → message_id`，编辑节流）、
  最终回复单独成一条消息，且只有最终消息带通知。
- **渲染。** 不要输出 Telegram MarkdownV2（转义地雷阵）。OpenClaw 把
  markdown 渲染成 Telegram 安全的 HTML，被平台拒收时改用纯文本重试。
  表格做归一化处理（转成列表或代码块）。
- **turn 忙时的输入。** turn 进行中到达的消息排队；控制命令（`/stop`、
  `/new`）绕过队列。
- **轮询 vs webhook。** 两者面向 local-first 部署时都默认 Telegram 用
  long polling；webhook 是面向云端托管的可选项。

## Telegram Bot API 事实

- `getUpdates` long polling 不需要任何公网 ingress；offset 用来确认已处理
  的 update，因此只在分发完成后提交 offset，就能在重连之间获得
  at-least-once 处理。
- `sendMessage` 配 `parse_mode: "HTML"`；每条消息 4096 字符硬上限（我们
  在 4000 处按段落边界分块）。
- `editMessageText` 支撑进度消息模式；编辑有速率限制，因此把编辑节流到
  间隔 ≥ 1.5 s。
- 内联键盘（`InlineKeyboardMarkup`）会送来带按钮 `callback_data` 的
  `callback_query` update；`answerCallbackQuery` 确认这次点按。
- `setMyCommands` 注册原生命令菜单；`sendChatAction` 显示 typing
  indicator。

## SeaTalk Open Platform 事实

已对照官方 `seatalk-io/cs-bot` 仓库与官方文档镜像核实（文档站需要开发者
登录）。

- **入站只有 webhook。** 没有轮询或 websocket。事件以 `POST` JSON 到达：
  `{event_id, event_type, timestamp, app_id, event}`。单聊消息是
  `event_type: "message_from_bot_subscriber"`；发送者由 `employee_code`
  标识。
- **Callback URL**：http 或 https，必须公网可达（内网 IP 通不过校验）。
  隧道可用。保存时 SeaTalk 会 POST 一条包含 `event.seatalk_challenge` 的
  `event_verification`；服务端必须在 5 秒内回显
  `{"seatalk_challenge": ...}`。非 200 响应的事件最多重试 3 次。
- **签名**：每条回调都带一个 `Signature` header，等于
  `sha256(raw_body + signing_secret)` 的十六进制摘要。signing secret 按
  app 配置，在开发者门户中可见、可重置。
- **发送侧鉴权**：`POST /auth/app_access_token` 携带 app id + secret →
  token 有效期 7200 s（该端点限 600 次/小时）。API 调用使用
  `Authorization: Bearer`。错误码 100 = token 过期（刷新后重试），
  101 = 被限流。
- **发送单聊**：`POST /messaging/v2/single_chat`，按 `employee_code`
  寻址；`tag: "text"` 配 `format: 1` 即 Markdown；约 300 条/分钟的速率
  限制；内容上限 4096 字节。
- **交互式卡片**：`tag: "interactive_message"`，按钮用
  `button_type: "callback"` 并携带自定义 `value`；点按以
  `interactive_message_click` 事件回传，带 `value`、`message_id` 与
  `employee_code`。
- **Typing indicator**：单聊是 `single_chat_typing`——群聊还有
  `group_chat_typing`，这一行当初的漏写曾让我们以为群聊没有这个端点。
  详见下方的输入中提示一节。
- **组织审批**：自建 app 的 scope（Send Message to Bot User 等）需要组织
  管理员审批；出站 IP allowlist 是可选项，动态 IP 的机器应保持留空。

## 群聊、线程与富内容（2026-07-08）

在构建群聊/@mention/线程/转发支持（feature/channel-group-mention-rich）时，对着一个
真实的 SeaTalk app 和一个真实的 Telegram bot 现场核实过。

- **SeaTalk 入站 tag/事件（现场核实）：**
  - DM 的 `combined_forwarded_chat_history` = `{tag,
    combined_forwarded_chat_history:{content:[{tag, sender:{email},
    message_sent_time, text:{content}|image:{content:url}|file:{filename}}]}}`。
  - DM 引用 (quoted) = `tag:"text"` + `quoted_message_id`。
  - DM 线程 = `tag:"text"` + `thread_id`。
  - 群事件：`bot_added_to_group_chat`（`event.group.group_id` + 邀请人）；
    `new_mentioned_message_received_from_group_chat`（**只有** bot 被 @mention 时才
    触发；`event.group_id` +
    `message.{thread_id, sender, text:{plain_text, mentioned_list:[{username,
    seatalk_id}]}}`）；`new_message_received_from_thread`（非 @ 的线程闲聊——被
    忽略，因为 bot 从不在没有 @mention 的情况下行动）。
  - **群聊文本落在 `text.plain_text`，而非 `text.content`**——DM 与群事件的形状在
    这一点上分道扬镳，很容易读错字段。
  - 在某个线程*内*对 bot 的 @mention，到达的仍是
    `new_mentioned_message_received_from_group_chat`，只是带上了 `thread_id`——
    并不存在一个单独的「线程内被 @」事件类型。

- **用到的 SeaTalk Open API 端点：**
  - 群发送：`POST /messaging/v2/group_chat {group_id, message}`。要回复进某个
    线程，`thread_id` 要放在 **`message` 体内**（`message.thread_id`），**不是**放
    在顶层——真机验证：顶层 `thread_id` 会被静默忽略、回复落到群主聊天区，而
    `message.thread_id` 才会进线程，且目标线程不存在时会以该 id 为根**自动建线程**
    （所以群主聊天区的 @mention 回复会挂在该 @mention 下成线程）。
  - 线程读取：`GET /messaging/v2/group_chat/get_thread_by_thread_id
    {group_id, thread_id, page_size}` → 响应 `{code, next_cursor,
    thread_messages:[…]}`——列表键是 `thread_messages`，不是 `messages` 或
    `content`。
  - `GET /messaging/v2/get_message_by_message_id` 用于解析某条被引用的单条消息
    （quote）。
  - 群聊**历史**端点（拉取最近的群主聊天消息，区别于某一个线程）被刻意未使用——
    对应的 SeaTalk 权限没有授予 Coffer 的 app，所以「最近的群主聊天」上下文从不
    被读取；@mention 消息本身加上它自己的线程（如果有）就是整个上下文窗口。

- **SeaTalk 出站 @mention（2026-09-12 从文档读得）：** 这两半信息本仓库此前**一条都
  没有**，而一个没被记下来的 SeaTalk 线上细节，已经在另一个端点上让这个项目付出过
  好几天的排查代价——所以两半都写在这里，哪怕其中一半是推断。
  - **标记本身。**「Send Message to Group Chat」给出的富文本样例是
    `"content":"Kindly note there's **no meeting** today <mention-tag
    target=\"seatalk://user?id=0\"/>."`——一个 mention 就是放在消息 content 里的
    自闭合 `<mention-tag target="seatalk://user?id=ID"/>`。它自身不携带任何可见文本
    （客户端渲染出被 @ 者的名字），所以构造它只需要一个 id，不需要显示名查询。
  - **文档给了三种目标值，以下照抄「Send a Message with Formats」。** 本仓库此前只记下了
    中间那一种：
    - 按 email：`<mention-tag target="seatalk://user?email=xxxx@xxx.com"/>`
    - 按 SeaTalk id：`<mention-tag target="seatalk://user?id=xxxxxxx"/>`
    - @ 群里所有成员：`<mention-tag target="seatalk://user?id=0"/>`
    - 最后一种还带一条注意事项：只有当该群打开了「Notify all members with @All」设置时，
      @ 全体成员才真的会**通知**到人。Coffer 从不构造它——一条在多数群里静默、在其余群里
      等于喊话的回复，不算回复。email 只作为**兜底**来构造：入站的群 @mention 事件总是
      带着 `sender.seatalk_id`，而文档警告 `email`（以及 `employee_code`）在发送者不属于
      bot 所在组织时会是空。
  - **@ 通知是在消息被「创建」的那一刻决定的——这一条花掉了一轮线上排查。** mention 最初
    只放在**最终**那个流快照上，依据就是下面那条 format 规则。在真实客户端里它渲染得完美
    无缺——蓝色、可点、名字正确——而被 @ 的人一条通知都没收到。平台是在消息创建
    （`init_stream`）时从内容里读出 mention 的，而不是从后续每一次 `update_stream` 里读，
    于是标签确实在客户端显示的内容里，但通知早已在没有它的情况下被决定了。所以流式回复
    必须把 mention 放进 `init_stream` 发出的那份内容里。
  - **它是 markdown，这一点框定了整段流要怎么发。** 只有在 `format: 1` 的消息里，
    这个标签才会以名字的形态抵达读者；在 `format: 2`（纯文本）的消息里它会显示为那串
    字面源码。中间快照过去刻意用 `format: 2`——截在词中间的回复可能结束在未闭合的 `*`
    或 `_` 里，让客户端去解析那个只会渲染出噪音。既然 mention 现在必须从创建那一刻起
    一直在（否则它会出现、消失、再回来），每个快照就都是 `format: 1`，半截文本改为
    **转义**：在标记字符前加一个反斜杠，也就是 SeaTalk 自己的渲染器用的那个转义。两个
    反斜杠会让其中一个在聊天里露出来——这个 bug 本项目已经修过一次。
  - **用哪个 id——这是推断，以及它所依据的证据。** 是 `seatalk_id`，**不是**
    `employee_code`。没有任何一句话直说这件事。真正指向它的是：「Event: New
    Mentioned Message From Group Chat」把 `mentioned_list` 的每一项写成
    `{username, seatalk_id}`，并把「Mention all」记为 `seatalk_id: "0"`——正是上面
    发送样例所指向的那个 `0`，于是入站与出站的 id 空间对上了。
  - **该事件上的 `sender` 是 `{seatalk_id, employee_code, email, sender_type}`，
    而只有第一个总是存在。** 文档警告：当发送者不在 bot 所属组织内时，
    `employee_code` 与 `email` 会是**空**。Coffer 此前留下了 `employee_code`
    （作为 `sender_id`，供 owner gate 使用）与 `email or seatalk_id`
    （作为 `sender_display`），却**丢掉**了 `seatalk_id`——丢掉的正是 mention 所需
    的那个 id，也是跨组织发送者唯一携带的 id。现在它作为独立的 envelope 字段被带上，
    刻意不并入 `sender_id`——后者是 owner gate 用另一个值去比对的。
  - **标签是被「暂存」出每一道转义之外的，而不是假定它天生安全。** 这里原本写的是：它能
    原样穿过渲染器，因为标签里不含该渲染器会转义的那四个字符。对两种真实的目标值来说这是
    错的：id 可以含 `_`（一个 `abc_def` 的 id 曾以 `...id=abc\_def..."/>` 抵达——是可见的
    源码而不是名字），而标签的 email 形态更是动不动就含（`first_last@example.com`）。所以
    渲染器在转义之前把 mention 标签取出、转义之后再放回，和它一直以来对行内代码的做法
    一样。`seatalk://` 仍然不会被它的裸 URL 规则命中——后者只认 `http`/`https`。这些都在
    适配器测试里对着线上 body 断言，而不是听天由命。

- **两条值得记录的平台限制：**
  - SeaTalk 根本不会把 emoji 表情回应或非 @ 的群主聊天消息投递给 bot——两者都没有
    对应的事件，所以「读取最近的群主聊天历史」不只是尚未实现，而是在 SeaTalk 没有
    授予自建 app 相应权限的前提下根本无法实现。
  - Telegram 的 Bot API 完全无法拉取聊天历史（没有类似
    `get_thread_by_thread_id` 的等价物），所以 Telegram 的群聊/线程上下文从不被
    读取；adapter 仍会从入站 update 本身解析 @mention、回复与转发，并回复进正确的
    forum topic。两条已披露的 Telegram 解析注意事项，均在 `telegram_parse.py` 的
    调用点处有记录：mention 实体的 offset 是对着纯 Python 的 code-point 索引匹配
    的，尽管 Telegram 自己的 offset 是 UTF-16 code unit——这是一个被接受的简化，
    只有当一个代理对 (surrogate-pair) 字符（例如某些 BMP 之外的 emoji）出现在
    mention 之前时才会漂移；并且目前只解析纯文本消息上的 `entities` 来找 mention
    —— 带 caption 的媒体（图片/文件）上的 `caption_entities` 尚未解析，因此媒体
    caption 里的 @mention 不会被识别。

## 由调研得出的决策

| 决策          | 选择                                                    | 理由                                                                                                     |
| ------------- | ------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| Telegram 传输 | 用裸 httpx 做 long polling                              | local-first、无需 ingress；用到的 API 面只有 7 个小方法 —— 引入 SDK 毫无收益，还要多一条 import 限界契约 |
| SeaTalk 传输  | webhook → 独立监听器进程 + 用户自行运行的隧道           | webhook 是唯一选项；章程要求公网可达 surface 必须是独立进程、只服务带签名的回调路径                      |
| SeaTalk SDK   | 不用（裸 httpx）                                        | 官方仓库本身就是一个薄 httpx 等价物；token 缓存约 20 行                                                  |
| 配对参数      | 8 字符、排除 `0O1I`、1 h TTL、有界猜测次数、fail closed | 与两个先例一致，并对齐 Hermes 事故后的加固                                                               |
| Telegram 渲染 | markdown → HTML，被拒收时用纯文本重试                   | OpenClaw 验证过的路线；MarkdownV2 的转义是著名的 bug 农场                                                |
| 进度体验      | 一条可编辑状态消息、节流；先确认；最终回复单独发        | 两个先例皆如此；在 SeaTalk 上经能力标志自然降级                                                          |
| turn 中输入   | 有界 FIFO 队列，控制命令绕行                            | 可预期；避免 Hermes「默认打断」带来的意外                                                                |
| 会话范围      | 每个 `(channel, chat)` 一段长生命周期对话，`/new` 重置  | 匹配 1:1 的产品决策；群聊将来作为新行加入                                                                |

## Channel 作为管理面 —— 自建 vs 借用 & 现状（2026-07-08）

在决定"扩展 Coffer 自己的 SeaTalk/Telegram 适配器（FR-028…FR-041）"还是"整体借用某个 agent 原生网关"时调研。

- **自建 vs 借用的决定。** **不** fork OpenClaw 或 Hermes 的 channel 代码。两者都是 TypeScript/Node 单体仓库（MIT），其 channel 层与各自的 agent/session/MCP/memory 运行时耦合；把 transport 抽出来、重接到 Coffer 的 Python agent，再加上跑一个 Node 进程 + 背 fork 维护，成本高于增量改进 Coffer 自己的 SeaTalk/Telegram 适配器——尤其两者都不支持 SeaTalk（Coffer 的主渠道），而 Telegram Coffer 已经有了。决定：把好的模式（相册去抖、编辑式流式、ack reaction、事件去重）**参考并移植**进 Coffer 自己的干净适配器，而不是搬代码。

- **官方 channel 现状（2026-07）。** Claude Code "Channels" 是官方**本地**插件（Telegram/Discord/iMessage），但属**研究预览**、仅个人（无群）、会话得一直开着、且听不懂语音（[code.claude.com/docs/en/channels](https://code.claude.com/docs/en/channels)）。Claude-in-Slack、Codex-in-Slack、Cursor-in-Slack 是官方但**仅 Slack**、**云端**、单 agent（[Claude Slack](https://code.claude.com/docs/en/slack)、[Codex Slack](https://developers.openai.com/codex/integrations/slack)、[Cursor Slack](https://cursor.com/docs/integrations/slack)）。Codex/Gemini/OpenCode **没有**官方 Telegram；Gemini CLI 完全没有官方 IM channel。**SeaTalk 谁都不支持（对任何 agent 都零官方竞争）。**

- **单 track 的 channel 管理面模型。** Coffer 的 channel 管理面只管理 Coffer 自己 host 的东西——即 **Coffer-hosted channel**(SeaTalk 永远,加上官方桥接覆盖不到的 agent/用例的 Telegram),这是"一个 bot 控所有 agent"的护城河,管理方式与管理 MCP server、memory、skill 一致。**Externally-hosted channel——agent 原生网关(OpenClaw/Hermes 独立)与官方集成(Claude/Codex/Cursor-in-Slack、Claude Code 官方插件)——是非目标(non-goal):** Coffer 既不代理也不代管(叠网关与其运行时冲突;把 token 交给外部进程配置等于作废 vault;官方云端集成没有本地凭据可托管)。用户走那个工具自己的流程即可,Coffer 文档给指引。(早先设想过第二条"管理外部 channel"的 track,作为过度设计/YAGNI 已删。)

- **北极星。** 一个已配对的 bot 驱动任意 managed agent,可**按会话、按 thread** 切换(每个 thread 是独立会话,FR-032)。

## SeaTalk 流式消息（2026-09-11 重新查阅）

FR-037 的 SeaTalk 流式实现当初是照着这份文档写的，但从未对着真实 API 验证过，
这里也没有留下任何摘要——于是一个缺了两个必填字段的请求体就这么发了出去，
单元测试钉住的是我们臆想的形状，而平台对每一次开流都只回一个光秃秃的
`code=102`。写下这一节，是为了让下一个读代码的人能对照契约本身，
而不是对照我们对它的记忆。

来源：Send Streaming Messages，open.seatalk.io（需登录）。

- **两个端点都要带目标。** `init_stream` 与 `update_stream` 都需要
  `employee_code`（单聊）或 `group_id`（群聊）。光有 `stream_id` 不足以
  确定发往哪个会话。
- **`init_stream` 的 `message` 是必填的。** 它会向会话真实投递一条占位消息并
  返回 `stream_id`。该 message 用 `tag` 指明类型：`"text"` 或
  `"interactive_message"`——也就是说流式载体可以是**卡片**，不限于文本。
- **`update_stream` 的 message 只带内容** —— `text` 或 `interactive_message`，
  没有 `tag`。类型在开流时就已经定死。
- `seq` 从第一次 `update_stream` 起算 1，每次加一；`init_stream` 不占用序号。
- 每次更新都携带**全量累积内容**，绝不是增量；客户端渲染它收到的最新快照。
- `format` 为 `1` 表示 Markdown（默认），`2` 表示纯文本。Coffer 对每一个快照都用 `1`，
  开场那个也一样，这样消息从被创建起就能携带 @mention（见上文 mention 部分）；在途的
  快照靠转义来保持字面。
- `thread_id` 与 `quoted_message_id` 放在 message **内部**，与普通发送已验证的
  位置一致。`quoted_message_id` 仅群聊可用。
- **不需要额外权限。** 流式复用与普通回复相同的 Send Message to Bot User /
  Send Message to Group Chat 授权；应用需具备 bot 能力且状态为 Online。
- 限制：相邻 `update_stream` 间隔不得超过 30 秒，否则流被终止；总长 4096 字符；
  流一旦结束（完成、超时、出错），任何引用该 `stream_id` 的请求都会被拒。
  文档建议按约每 200 毫秒一次做缓冲，而不是每个 token 调一次。
  - **打字机效果完全由更新频率决定，没有别的。** 文档说客户端「renders progress by
    displaying the latest snapshot received」——它是**替换**文本，而不是朝目标做动画。
    对真实 Claude SDK 实测：文本增量约每 25 毫秒到达一次、每次约 4 个字符，因此按建议的
    200 毫秒缓冲会把大约八个增量折叠成一次约 30 字符的可见跳变——一次一句话，读起来
    是一段一段而不是在打字。Coffer 改为按 100 毫秒缓冲（`COFFER_SEATALK_STREAM_INTERVAL`
    可在不重新打包的情况下重新调整）。平台**完全没有**为 `update_stream` 公布任何限频，
    只有那句「approximately every 200 ms」的建议，所以这是拿一份未公开的额度换一个明显
    更好的回复；平台若真要回推，会返回 429/code=101，transport 会退避并记录日志。
- 3.67 以下版本的接收方只会在流关闭后看到最终那一条消息。
- 文档未解决的疑问：参数表把 `thread_id` 标为可选，但群聊请求示例的注释写着
  「thread_id required」。群主频道（线程之外的 @ 提及）不带 `thread_id` 开流
  是否被接受，尚未验证。

### 输入中提示，两种会话都有（2026-09-11）

是两个端点而不是一个 —— `messaging/v2/single_chat_typing` 收 `employee_code`，
`messaging/v2/group_chat_typing` 收 `group_id` 加**可选**的 `thread_id`。
Coffer 曾因「群聊没有这个端点」的判断而屏蔽了群内提示；实际上是有的。

- 提示只显示 4 秒，所以一次 turn 运行期间要按心跳重发。限频 300/分钟。
- 群聊里传入本次 turn 所回复的 thread，提示就出现在那里；不传则显示在主频道。
  若要对一条未开线程的根消息显示输入中，把该消息的 id 作为 `thread_id` 传入 ——
  根消息必须在 7 天以内。
- 需要 SeaTalk 3.55 及以上。
- 错误码 7003「群聊过大」指成员超过 200 人，此时平台根本不提供该提示。
  无解，进度改由本次 turn 的流式载体承担。
