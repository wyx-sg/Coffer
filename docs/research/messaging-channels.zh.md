# 竞品调研 —— 面向 Agent 的消息渠道接入与路由

> 中文版：本文件 · English: [messaging-channels.md](./messaging-channels.md)
>
> 面向 Coffer 渠道特性（spec 009，ADR-014）的内部竞品调研报告。**日期：** 2026-06-16。
> **方法：** deep-research harness。A/B/C 三个角度已覆盖；部分 HITL 平台与
> Rasa/Chatwoot/Voiceflow/Sweep 未取证。

## 1. 全景速览

"把 agent 连到消息应用"其实是三个相邻市场：

| 角度                          | 是什么                         | 例子                                                       |
| ----------------------------- | ------------------------------ | ---------------------------------------------------------- |
| **(A) 全渠道 bot 连接器**     | 一个 bot/agent ↔ 多渠道，托管 | Azure Bot Service Channels、Botpress、Twilio Conversations |
| **(B) 编码 agent 的 ChatOps** | 从聊天驱动编码 agent（团队）   | Claude Code Slack、Devin、Cursor、OpenHands                |
| **(C) 聊天内人工审批**        | 从聊天审批 agent 动作          | HumanLayer、Slack Block Kit、n8n / LangGraph HITL          |

### 关键发现

- **连接器把渠道归一化为渠道无关的内核** —— Azure 的 "Activity" 模型、Botpress 的 Telegraf
  层——这在结构上与 Coffer 用的 **N+M** 解耦相同（新渠道不碰 agent 代码）。区别在于它们是
  **托管/团队**；Coffer 自托管一个**签名回调监听器**。Telegram 鉴权是 bot token；Slack 需
  经平台回调的 app 凭证。[3-0 确认 —— learn.microsoft.com Azure Bot Service；Azure Bot SDK
  于 2025-12 归档，Channels GA]
- **Twilio Conversations 是 Coffer 缺失的最清晰的多对多模型：** 号码对路由、入站自动创建、
  经 webhook 绑定的**按会话的 bot**（最多 5 个）。Coffer **每个渠道绑定一个默认 agent。**
  [3-0 确认 —— twilio.com/docs/conversations]
- **编码 ChatOps 与 Coffer 的安全模型相反。** Claude Code（Slack）、Devin、Cursor、OpenHands
  用 **workspace OAuth + 按用户账号关联**，以频道邀请 + 按用户身份门禁——**团队**模型。Coffer
  用**单 owner、一个配对码、陌生人静默忽略**。Cursor 在 N 对 M 路由上领先。[3-0 确认]
- **审批 + 通知是基本盘**（如 `ccgram` 经 hooks 从 Telegram 驱动 Claude Code）。但
  **Coffer 的确切组合——渠道是受管*资源*、隐身配对、被 web 控制台复用的*共享*审批闸、N+M
  签名监听器——没有确切对应物。** [中等置信]
- **与 Coffer 配对/隐身设计最接近的单一对应物是 Anthropic 自己的官方 Telegram 插件**
  （`claude-plugins-official/external_plugins/telegram`），其 README + ACCESS.md 记录了
  配对、owner 白名单、静默忽略——验证了 Coffer 的安全姿态，尽管它是一个插件而非受管多渠道框架。

## 2. 能力对比

| 能力                | Azure Bot Svc | Twilio Conv. | Claude Code Slack / Devin | Anthropic TG 插件 | **Coffer 渠道**                       |
| ------------------- | ------------- | ------------ | ------------------------- | ----------------- | ------------------------------------- |
| 渠道无关内核（N+M） | ✅ Activity   | ✅           | ✅                        | —                 | **✅**                                |
| 支持的渠道          | 多            | SMS/WA/chat  | Slack（+GitHub）          | Telegram          | **Telegram、SeaTalk**                 |
| 托管方式            | 云            | 云           | 云/SaaS                   | 自托管            | **自托管（签名监听器 + 隧道）**       |
| 访问模型            | app/组织      | 按号码       | **团队 OAuth + 按用户**   | owner 白名单      | **单 owner 配对、隐身**               |
| 渠道 = 受管资源     | ❌ 配置       | ❌           | ❌                        | ❌                | **✅ 资源（生命周期/审计/凭证探测）** |
| 按会话绑定 agent    | 部分          | **✅**       | ✅                        | ❌                | **❌ 每渠道一默认 agent**             |
| 聊天内审批          | 经 Block Kit  | —            | ✅                        | ✅                | **✅ 与 web 控制台共享闸**            |
| 通知推送            | ✅            | ✅           | ✅                        | ✅                | **✅**                                |
| 单用户本地优先      | ❌            | ❌           | ❌                        | ✅                | **✅**                                |

## 3. Coffer 对比

**Coffer 独特之处。**

1. **渠道是一等受管资源。** 连接器把渠道当作配置；Coffer 把它做成带生命周期、审计、凭证探测的
   `channel:<name>` 资源——与每个其他 Coffer 资产一致。
2. **单 owner 隐身配对是团队工具没有的安全姿态。** 全渠道/ChatOps 工具假定可信组织（workspace
   OAuth）；Coffer 对个人金库失败即关闭——一个配对码，bot 从不向陌生人暴露自己活着。只有
   Anthropic 自己的 Telegram 插件能匹配这一点，这验证了该设计。
3. **共享审批闸。** 聊天内审批跑在与 web 控制台*相同*的接缝上（一条审批路径，两个界面）。
   HumanLayer 做聊天内审批但是独立 SaaS；Coffer 把它折进金库。
4. **自托管签名监听器**置于用户自跑隧道之后——本地优先，对比托管连接器。

**Coffer 落后之处。**

1. **仅 Telegram + SeaTalk。** 无 Slack/WhatsApp/Teams/Discord——而 Slack 正是编码 agent
   ChatOps 所在地。
2. **每渠道一默认 agent；无按会话绑定。** Twilio 的按会话 bot 是要抄的模型：单个渠道把不同
   会话路由到不同 agent。
3. **单 owner、无团队路由**——有意之选，但让出了整个团队段。
4. **审批之外无丰富交互 UI**（Slack Block Kit 按钮）。

## 4. 给 Coffer 的关键结论

1. **渠道即资源 + 隐身配对 + 共享审批的组合确有差异化**——Anthropic 自己的 Telegram 插件是
   唯一接近的对应物，这是验证而非竞争。作为头条。
2. **借鉴按会话 agent 绑定**（Twilio 模型），让单个渠道把不同会话路由到不同 agent——最清晰的
   功能缺口。
3. **下一步加 Slack 适配器。** ChatOps 重心在 Slack；你的 N+M 架构让新渠道只是一个适配器而非重写。
4. **把单 owner 作为有意识的范围决策保留**——团队路由是另一个产品；别不小心漂进去。
5. **考虑按平台的交互控件**（按钮）做审批，在平台支持处（Slack Block Kit、Telegram 内联键盘）。

## 5. 来源

一手：

- learn.microsoft.com/azure/bot-service —— manage-channels、connect-telegram、connect-slack
- twilio.com/docs/conversations —— inbound-autocreation、conversations-webhooks
- botpress.com/integrations/telegram
- code.claude.com/docs/en/slack · docs.devin.ai/integrations/slack · cursor.com/docs/integrations/slack · docs.openhands.dev（slack）
- github.com/anthropics/claude-plugins-official —— external_plugins/telegram（README、ACCESS.md）
- github.com/jsayubi/ccgram · dev.to（从 Telegram/Discord/Slack 控制 Claude Code）
- docs.slack.dev/interactivity · docs.n8n.io/advanced-ai/human-in-the-loop-tools · docs.langchain.com（deepagents HITL）· github.com/humanlayer/humanlayer

## 核查更新（2026-06-19）

> 复核一轮。本地那条两段式论断现已部分过时：渠道即受管资源、单 owner 隐身配对仍成立，
> 但"被 web 控制台复用的共享审批闸"已被提交 `165f0e6`（PR #101，2026-06-18 合入）删除
> ——这比本报告 2026-06-16 的日期晚两天——该提交移除了整个工具审批系统。三条 web 论断
> （Anthropic Telegram 插件、Twilio"最多 5 个"webhook、Azure Bot SDK 已归档）均对照一手
> 来源确认无误。

### ✅ 已确认

- **渠道 = 受管资源。** ADR-014 §决策第 1 条把渠道做成一种资源类型（`channel:<name>`，
  ADR-007），跑在通用的生命周期/审计/凭证引用机制上；`kind.py` 在注册时探测 `*_ref`
  凭证字段。（`repo:docs/decisions/ADR-014-channel-adapter-framework.md`、
  `repo:backend/coffer/application/channel/kind.py`）
- **单 owner 隐身配对。** `pairing.py` 实现每渠道一个待用配对码（8 位、1 小时 TTL、限次、
  失败即关闭、仅内存）；`inbound.py` 是 owner 门禁桥，对错误成员/陌生人消息静默忽略
  （165–202 行）；spec.md User Story 2 明文规定"bot 从不向陌生人暴露自己活着"。
  （`repo:backend/coffer/application/channel/pairing.py`、
  `repo:backend/coffer/application/channel/inbound.py`）
- **Anthropic 官方 Telegram 插件**与 Coffer 的配对/隐身姿态吻合：私聊 bot 取一个 6 位配对码；
  默认 `pairing` 策略，随后切到 `allowlist`，使"陌生人收不到配对码回复"；访问状态存于
  `~/.claude/channels/telegram/access.json`。如报告所言，它是一个自托管插件，而非受管多渠道
  框架。（https://github.com/anthropics/claude-plugins-official/blob/main/external_plugins/telegram/README.md）
- **Twilio Conversations"最多 5 个"按会话 webhook** 精确无误：每个 Conversation 最多可挂
  5 个会话作用域 webhook，第 6 个会被 50361 错误"Too many conversation webhooks"拒绝。
  作用域 webhook 正是按会话 bot 的文档化机制。
  （https://www.twilio.com/docs/conversations/api/conversation-scoped-webhook-resource、
  https://www.twilio.com/docs/api/errors/50361）
- **Azure Bot SDK 于 2025-12 归档，渠道仍 GA。** Microsoft Learn 写明 Bot Framework SDK
  计划不晚于 2025 年 12 月底归档，新工作转向 Microsoft 365 Agents SDK，而渠道基础设施
  （V3）保持兼容、无 EOL/中断计划。
  （https://learn.microsoft.com/en-us/azure/bot-service/what-is-new?view=azure-bot-service-4.0）

### ✏️ 已修正

- **"被 web 控制台复用的共享审批闸"——已移除，不再存在。** 旧（报告 2026-06-16）：聊天内审批
  跑在与 web 控制台相同的接缝上（一条审批路径、两个界面），被列为差异化特性——关键发现条目、
  能力表"聊天内审批——与 web 控制台共享闸"一行、§3 第 3 条、§4 第 1 条结论。修正（当前代码树，
  在 `165f0e6` / PR #101，2026-06-18 16:48 +0800 合入之后）：整个工具审批系统被删除——
  `ApprovalGate`/`ApprovalChannel`/`ApprovalRequest`/`ApprovalDecision`、渠道
  `send`/`resolve_approval_prompt` + `on_approval_click` 中继、web `ApprovalCard` + 审批席位、
  `/conversations/{id}/approvals` 路由、以及 `CHANNEL_APPROVAL_RESOLVED` 审计事件均被删除；
  `backend/coffer/application/chat/approvals.py` 已不存在；`backend/coffer/` 与
  `specs/009-channels/` 下不再有 `ApprovalGate`/"审批闸"相关符号；agent 现以全权限运行。
  该提交的理由恰是报告自己的说法反过来：该中继"与 owner 配对冗余（只有配对的 owner 能驱动
  渠道，而 web 控制台也是 owner）"。本地论断 #1 的另两条腿（渠道 = 资源；单 owner 隐身配对）
  仍是承重的差异化点；审批闸这一条应删除或改写为历史。（git 提交 `165f0e6`）
- **"Azure Bot SDK"** —— 准确产品名是 **Bot Framework SDK**（Azure Bot Service 背后的 SDK）。
  （同上 Microsoft Learn 来源）

### ➕ 新增覆盖

- **Rasa** —— 与 Coffer 的 N+M 解耦在结构上最接近的开源对应物。把 `InputChannel`（接收）与
  `OutputChannel`（发送）分开；自定义连接器继承 `rasa.core.channels.channel.InputChannel`。
  内置连接器（Slack、Messenger、Telegram、Twilio、web 聊天），可接任意数量渠道而不改对话模型
  ——与"新渠道不碰 agent 代码"是同一性质。区别：它是服务器/团队托管框架，没有单 owner 隐身配对
  的安全姿态，访问控制留给部署方。（https://rasa.com/docs/reference/channels/custom-connectors/、
  https://rasa.com/docs/reference/channels/messaging-and-voice-channels/）
- **Chatwoot** —— 开源全渠道客服台（约 2.2 万星），把在线聊天、邮件、WhatsApp、Instagram、
  Messenger、Telegram 统一进一个收件箱。渠道绑定是按收件箱的：一个 AgentBot 接到某个收件箱，
  配合按可用性/语言/地区的自动分配路由及 SLA 升级；内置 AI agent "Captain"。这是团队/CX 全渠道
  模型——与 Coffer 单 owner 个人金库姿态相反。（https://www.chatwoot.com/features/channels、
  https://github.com/chatwoot/chatwoot/wiki/Connecting-Agent-Bot-to-an-Inbox）
- **Voiceflow** —— 无代码平台，构建并"跨任意渠道"部署聊天与语音 agent：web 组件、电话
  （Twilio 语音）、移动端（API）、原生 WhatsApp、经连接器接 Instagram/Messenger/Telegram。
  一个 agent、经连接器接多渠道——但完全托管 SaaS，没有自托管签名监听器或 owner 配对模型；
  面向的是客户侧 bot 而非个人金库。（https://www.voiceflow.com/integrations/whatsapp、
  https://docs.voiceflow.com/docs/welcome）
- **HumanLayer（+ n8n）HITL 审批** —— 工具层人工审批，作为独立平面。HumanLayer 的
  `@hl.require_approval()` 装饰器在人工批准前阻塞调用，回复经 Slack/邮件/Discord 收集，与框架
  无关；n8n 以"发送消息并等待回复"工作流节点（Slack/Telegram/Teams 等）提供同形态，按工具强制。
  二者都是叠加在 agent 之上的外部审批平面——对比 Coffer 此前折进金库的闸（已在 PR #101 移除）；
  这些 HITL 工具仍是聊天内审批的活样本。（https://pypi.org/project/humanlayer/、
  https://docs.n8n.io/advanced-ai/human-in-the-loop-tools/）
