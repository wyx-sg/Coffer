# ADR-031 —— 聊天是属主的单属主实时镜像

> English: [ADR-031-chat-single-owner-live-mirror.md](./ADR-031-chat-single-owner-live-mirror.md)

- **状态：** Accepted
- **日期：** 2026-06-20
- **决策者：** Yuxing Wu
- **Spec：** [008-agent-chat](../../specs/008-agent-chat/spec.md)（重定位 + 回合生命周期改动——不新增 spec 编号；实现前先更新 `spec.md`）
- **收窄：** [ADR-021](./ADR-021-chat-as-vault-console.md) 职责 2（channel 观测）—— 从*观测*收窄为*观测 + 中断 + 注入*
- **构建于：** [ADR-024](./ADR-024-builtin-agent-is-internal-capability.md)（聊天只与受管 agent 对话）、[ADR-025](./ADR-025-remove-tool-approval.md)（全权运行，无审批席）、[ADR-014](./ADR-014-channel-adapter-framework.md)（channel 回合接缝）、Spec [009-channels](../../specs/009-channels/spec.md)

## 背景

聊天（Spec 008）已被两次重定位、并被移除了它的核心概念，每次都基于同一条论据
——*Coffer 是金库，不是行动者；一个与各 agent 自己的 UI 和 IM 竞争的浏览器聊天
没有持久使用场景*：

- **ADR-021** → *Vault Console（金库控制台）*（对金库说话 + 观测/审批 channel
  回合）。
- **ADR-024** 退役了内置聊天人格；聊天只与受管 agent（`claude_code`、`codex`）
  对话；界面改回 *Chat（聊天）*。
- **ADR-025** 移除了工具审批；channel 职责从*观测 + 审批*缩到只剩*观测*。

结果是一个半截肢的界面，没人决定过要保留还是砍掉。代码也显示了这一点：约 600 行
"仅供测试"保留的遗留 CLI 适配器、一个无类型的 `agent_config` JSON blob，以及一份用
散文式免责声明粉饰 ADR-024 漂移、而非重写的 `spec.md`。

本 ADR 选定聊天唯一不可替代的职责并对它做出承诺。

决定性的约束，是在审视 channel 桥接时浮现的：Coffer 的 channel 是
**owner-paired（属主配对）** 的（Spec 009 ——"一个配对的 **owner** 从 IM 应用里
……聊天"）。因此"IM peer"就是*同一个人*——手机上的属主——而非第三方。所以"接管一个
IM 会话"是**一个属主的跨界面连续性**，而非多人协作。这去掉了整个多人维度：没有
peer 身份模型、没有"谁可以打断谁"、没有消息可见性规则。

## 决策

**聊天是属主同样从手机（IM）驱动的那些会话的桌面界面。** 一个属主、一条会话时间
线、两块屏幕。一个会话背后是一个真实的 agent session（一个 `--resume` session、
一个工作目录），所以手机上发起的回合和桌面上继续的回合命中**同一个** session。

在桌面上属主可以实时**观测**任何会话（包括从手机发起的回合，逐 token），**中断**
一个正在运行的回合，并通过自由输入来**注入 / 继续** —— 消息会排队，永不阻塞。

### 1. 一条实时会话总线（唯一的新能力）

在观测 / 中断 / 注入之中，今天真正缺失的只有**观测**。中断已经能跨界面工作（进程
全局的 `_ACTIVE_TURNS` 就在那个唯一的守护进程里）。注入是前端的缺口
—— `POST /conversations/{id}/messages` 本就接受任何会话 id。观测才是缺口：网页只能
实时流式它自己发起的回合；一个从 IM 发起的回合只能通过对持久化行的 2 秒轮询看到。

所以把**发起一个回合**和**消费它的事件**解耦。每个会话获得一个 **broadcaster**
（广播器），它 (a) 把每个 `AgentEvent` 追加到当前回合事件的**环形缓冲区**，并
(b) 把它扇出给每一个已挂接的订阅者队列。两个端点：

- `POST /conversations/{id}/messages` —— **发起/入队**一个回合并立即返回；它不再
  拥有事件流。
- `GET /conversations/{id}/events`（SSE）—— **订阅**：挂接时回放环形缓冲区
  （补上你挂接之前已经流过的内容），然后实时流式；当没有回合在飞时，以心跳保持
  连接打开，并在下一个回合无论从哪个界面启动时投递它。

**单一事件路径：** 所有事件消费都走订阅流；POST 是 fire-and-return（发后即返）。
"观测我发起的回合"和"观测手机发起的回合"于是走同一段代码——发送方不是特例——而
环形缓冲区保证发送方不会漏掉任何早期事件。

### 2. 自由发送；一个 FIFO 待处理队列（修订 FR-018）

"拒绝第二条消息；锁定 composer"规则（FR-018）被替换：composer **永不锁定**；一条
超发的消息**入队**。每个会话持有一个内存中的**待处理队列**。当当前回合完成时，
orchestrator 把队首出队，把它提交为下一条用户消息，并运行它的回合。每会话一回合的
不变量**保留** —— 处理是顺序的；只是对超发的响应改变了（入队，而非拒绝）。

- **顺序的，非合并的。** 每条排队消息是它自己的回合，FIFO。
- **待处理是未提交的。** 排队的消息不写入已提交的消息序列；它们以可移除的
  "pending chips（待处理标签）"呈现，仅在它们的回合开始时才提交（取下一个
  `seq`）。这让 user/assistant 交替与 `--resume` 喂入保持干净有序。
- **中断 = 停止当前回合 + 暂停队列。** 否则下一条排队消息会立即射入你刚停掉的
  回合。标签仍在；属主移除它们、清空它们，或恢复。
- **跨界面推进。** 待处理队列是网页 composer 的；它在该会话上*任何*回合结束后自动
  推进 —— 包括一个 IM 驱动的回合 —— 所以一条排在手机发起回合之后的桌面消息，会在那个
  回合完成时仍然运行。一条在回合在飞时*从* IM 到达的消息，由 channel 自己的入站缓冲
  （Spec 009）持有，而非这个队列；v1 不把两者合并为一个物理 FIFO，所以跨界面保证是
  "一条桌面发送永不被拒绝且按序运行"，而非"IM 与网页共享一个队列对象"。
- **队列状态搭乘总线。** 一个 `QueueChanged` 事件广播有序的待处理项，让每个订阅者
  —— 第二个标签页、手机 —— 渲染相同的标签，使"两块屏幕，一条时间线"对尚未处理的
  消息也成立。
- **内存中，v1。** 待处理队列在守护进程重启时丢失（从未提交）—— 与"一个在飞的
  回合在重启时被标记为 failed"一致。

### 3. 折叠 origin；保留回邮地址

在单属主前提下 peer 永远是属主，所以网页-vs-channel 的**二分作为一个概念坍缩**：
一个统一的会话列表、一个 composer、一个订阅流 —— 没有基于 `origin` 的分支。但
`channel_name` / `peer_chat_id` 是把 agent 输出推回 IM 应用的**回邮地址**，不能
删除。于是：去掉 `origin` 和 `peer_display_name`；保留 `channel_name` /
`peer_chat_id` 作为一个可选的 `channel_binding`（一个会话"有一个 binding"当且仅当
`channel_name` 被设置）；当存在 binding 时桌面显示一个小小的"also on
Telegram/SeaTalk"指示。

### 4. 清理遗留的死定位

把 Spec 008 的 `spec.md` / `data-model.md` / `contracts/api.openapi.yaml` 重写到与
ADR-024 + 本定位一致，而非那条散文式免责声明（随本次改动交付）。

另有两项清理**从实时镜像改动中推迟**（它们与实时镜像接缝无关、且触碰*活跃*的编码
agent provider，所以把它们排除在那个已经很大的改动之外，以免危及可工作的
`claude_code` / `codex` 适配器）：

- **(a) 删除遗留 CLI 适配器**（`cli_agent.py`、`cli_providers.py`），并先把活跃
  适配器仍 import 的共享 helper（`ParseState`、`SessionSink`、`last_user_text`）
  抽到一个小模块 `adapter_support.py`。—— **已交付**（后续 PR）。
- **(b) 用一个有类型的 `AgentConfig { cwd, session_id, model }`** 替换无类型的
  `agent_config` blob（一个 frozen 的领域 dataclass：provider 把原始输入校验进它，
  持久化层把它序列化到/从 JSON 列；不改动线协议）。—— **已交付**（后续 PR）。

### 不变量

- **同一套接缝，不另起并行路径。** 桌面只通过既有的 `ConversationPort` /
  `TurnPort` / orchestrator 驱动回合；一个 agent 分不清一个桌面回合和一个手机
  回合。订阅流是只读的观测 + 既有的中断；它不引入任何特权回合路径。
- **`_ACTIVE_TURNS` 保持进程全局。** 单用户、单守护进程；水平扩展是 YAGNI。
  broadcaster 与待处理队列住在同一个进程里。
- **没有多人模型。** 单属主前提是承重的；peer 身份与消息可见性规则被明确排除在
  范围外。
- **只与受管 agent。** ADR-024 存续 —— 没有内置聊天人格；本地模型仍只在
  `coffer__*` 之后作内部使用。

## 被考虑的替代方案

### A —— 保持只观测；不加中断/注入

**拒绝。** 属主明确想从桌面抢方向盘（停下一个失控回合、继续输入）。只观测会让手机
发起的会话从桌面无法操控 —— 而这正是桌面席位存在的意义。

### B —— 只做实时总线；跳过清理与 origin 折叠

**拒绝。** 功能上可行，但留下 ADR 反复造成的残渣（遗留适配器、无类型配置、spec
漂移、无意义的网页/channel 分裂）。Coffer 的姿态是删除优先于新增；清理是价值的大
部分，而新代码很小。

### C —— 保留 POST 回流*并*再加一条订阅流

**拒绝。** 两条事件路径，冗余。单一订阅路径让发送方不再是特例并移除一类竞态；环形
缓冲区覆盖发送方的早期事件。

### D —— 把所有待处理消息合并成一个组合的下一回合

**为 v1 拒绝**（保留为一行开关）。属主要求"一条一条"处理；顺序 FIFO 是可预测的
默认。合并（更完整的 agent 上下文、更少的回合）若返工搅动证明烦人可再议。

### E —— 跨重启持久化待处理队列

**为 v1 拒绝（YAGNI）。** 守护进程重启罕见；尚未提交的消息在重启时丢失与"在飞回合
被标记为 failed"的叙事一致。作为 `queued` 行持久化是后续的加固。

## 后果

- Spec 008（`spec.md`、`spec.zh.md`、`data-model.md`、
  `contracts/api.openapi.yaml`）被重写：一个新的 `GET .../events` 订阅端点；POST
  messages 变为 fire-and-return；FR-018 修订（入队，而非拒绝）；`origin` 折叠；新增
  `QueueChanged` 事件；移除内置人格漂移。
- 会话 schema 去掉 `origin` + `peer_display_name`（Alembic 迁移，SQLite
  `batch_alter_table`）；`channel_name` / `peer_chat_id` 作为 `channel_binding`
  保留。Spec 009 channel 层在它写这些字段处被更新。
- 前端用一条持久的 `GET .../events` 订阅流替换每回合的 POST SSE + 2 秒轮询；
  composer 永不锁定并渲染 pending chips。
- 遗留 CLI 适配器删除（第 4a 部分）与 `agent_config` 类型化（第 4b 部分）均已在
  后续 PR **交付**（动作 3、第 4 部分）。
- ADR-021 被**收窄**（非取代）：它的 channel 观测职责被拓宽为观测 + 中断 + 注入；
  它的多人"审批席"框架已经消失（ADR-025）。
- 无内置人格改动（ADR-024 存续）；无凭据处理改动。
