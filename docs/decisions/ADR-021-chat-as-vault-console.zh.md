# ADR-021 — 把 Agent Chat 重定位为 Vault Console（金库控制台）

> English: [ADR-021-chat-as-vault-console.md](./ADR-021-chat-as-vault-console.md)

- **状态：** 已接受
- **Spec:** [008-agent-chat](../../specs/008-agent-chat/spec.md)（重定位 —— 不分配新 spec 编号；实现前先更新 Spec 008 `spec.md`）
- **关联：** [009-channels](../../specs/009-channels/spec.md)（[ADR-014](./ADR-014-channel-adapter-framework.md)，共享 turn/审批 seam）、[007-memory](../../specs/007-memory/spec.md)（控制台对话的金库）

## 背景

Spec 008 Agent Chat 以一个完整的多 agent 聊天客户端形态交付：三个 agent
（`builtin` Coffer Assistant、走 Python SDK 的 `claude_code`、走 `codex
app-server` 子进程的 `codex`）、agent 选择器、工作目录选择器、model 选择器、
会话历史、逐工具审批卡片。

但真正用来和 coding agent 对话的界面是：(a) agent **自己**的 UI —— 你专注写代码
的现场；(b) **IM** —— 异步、移动、离开键盘的场景。一个在浏览器里和这两者竞争的
聊天客户端没有耐久使用场景，也偏离使命：Coffer 的价值是金库（memory、skills、
knowledge、聚合 MCP、同步），不是又一个聊天前端。"一个没有真实使用的 chat 页"
同样不满足本项目的交付门槛（每个交付的界面都要有真实使用）。

但有两个角色是 **Coffer 独有、别处没有**的：

1. **对着金库本身说话。** `builtin` agent 本来就是 Coffer 自有网关的进程内 MCP
   客户端（memory / KB / skills / 聚合 MCP 工具，session id
   `coffer-builtin-agent`）。这是金库的控制台 / playground，不是编码聊天。
2. **为 channel/IM 驱动的会话提供 human-in-the-loop 审批席。** Channels（Spec
   009）创建会话、转发工具审批走的是和网页 UI **同一套** `ConversationPort` /
   `TurnPort` seam；agent 分不清一个 turn 是来自 channel 还是来自 UI。网页 UI 正是
   **旁观**这些会话、并**接管审批席**的天然位置。

## 决策

把 Agent Chat 界面重定位为 **Vault Console（金库控制台）**。它的职责是：

1. 通过 `builtin` agent **与金库对话**；
2. **旁观并审批** channel/IM 驱动的会话。

明确**移出范围**："把 Coffer 当成日常的浏览器内编码聊天"。三个具体动作：

1. **builtin agent → 金库控制台 / playground。** 把命名、空状态、CTA 从"通用助手"
   改成"问问你的 memory / skills / KB"。每个 turn 显式 surface 它实际碰了哪些
   memory 事实 / KB 文档 / skill / 聚合 MCP 工具，让控制台同时成为**检视**"一个
   agent 能从金库拿到什么"的地方。
2. **来源感知的会话列表 + 审批席。** 会话列表区分来源（网页草稿 vs channel
   peer），对 channel 来源的会话显示 peer 身份，并把待审批顶到显眼位置。从网页
   `ApprovalCard` 审批等价于在 IM 点审批按钮 —— 两者都落到同一个
   `submit_approval`。
3. **CLI agent 重定位，而非删除。** `claude_code` / `codex` 仍保留，但重新定位：
   不是"你的日常编码聊天"，而是 (a) 可 **test-drive** 的目标，(b) **IM 驱动、你在
   这里旁观/审批**的会话。

按宪法原则 II，实现**之前**先把 Spec 008 `spec.md` 及其验收场景更新到这个定位；
本 ADR 记录方向。

### 不变量

- **同一套 seam，不另起并行路径。** Vault Console 驱动 turn 和审批只走
  `ConversationPort` / `TurnPort`，与 channels 完全一致。它不引入任何特权 turn 或
  审批路径；agent 分不清控制台 turn 和 channel turn。
- **审批对等。** 一个待审批工具调用可以从网页 `ApprovalCard` **或** IM 按钮任一处
  解决；两者都调 `submit_approval`。控制台没有特殊审批权。
- **不向"日常主力"蔓延。** 只对"把 Coffer 当主力编码聊天"才有意义的能力（与原生
  客户端竞争的丰富编码 UX）保持在范围之外，除非未来某个 spec 有意重开这个定位。

## 被考虑的替代方案

### A —— 继续把它定位为完整的多 agent 聊天客户端

**拒绝。** 对 agent 自己的 UI 和 IM 没有耐久使用；偏离使命（Coffer 是金库，不是
聊天客户端）；不满足真实使用的交付门槛。

### B —— 完全砍掉 chat 界面

**拒绝。** 这会丢掉两个真正独有的角色（金库控制台 + 审批席）以及已建好的共享
turn/审批 seam。Channels 始终需要在某处有一个人工审批席；控制台是最省的归宿。

### C —— 拆成两个独立页面（控制台页 + channels 审批页）

**暂时拒绝。** 两者依赖同一套会话 / turn / 审批机制和同一个 thread UI。一个来源
感知的界面更简单，也避免重复 thread 组件；若两个角色将来分化，可再议。

## 后果

- Spec 008 `spec.md`、UI 文案、builtin-agent 详情页 CTA 更新到 Vault Console
  定位。
- channel 来源的会话在会话列表中成为一等公民（来源徽标、peer 身份、待审批
  提示）。
- 外部 agent 会话的 `continue`/`resume` 保持在范围外。
- 这是定位 + 前端呈现；后端的 turn / 审批 / channel 机制原样复用。
