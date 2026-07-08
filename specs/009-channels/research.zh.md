# Research：009 —— Channels

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
- **Typing indicator**：存在 `single_chat_typing` 端点。
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
