# ADR-025 — 移除工具审批系统；owner 配对即门禁

> English: [ADR-025-remove-tool-approval.md](./ADR-025-remove-tool-approval.md)

- **Status:** Accepted
- **Date:** 2026-06-18
- **Deciders:** Yuxing Wu
- **Spec:** [008-agent-chat](../../specs/008-agent-chat/spec.zh.md) 与 [009-channels](../../specs/009-channels/spec.zh.md)（移除——不开新 spec 号；两个 `spec.md` 随本 ADR 一起更新）
- **Supersedes:** [ADR-021](./ADR-021-chat-as-vault-console.zh.md) 的**「审批席位」**职责；移除 Spec 008 引入、Spec 009 桥接到 IM 的逐工具审批中继（[ADR-014](./ADR-014-channel-adapter-framework.zh.md)、[ADR-023](./ADR-023-channel-entrypoint-differentiation.zh.md)）

## Context

Spec 008 给聊天平台加了逐工具的**人工审批**能力：agent 想跑某个工具时发出
`ApprovalRequest`，turn 停在 `ApprovalGate` 上，由人来允许/拒绝——可从 web 的
`ApprovalCard`（ADR-021 的「审批席位」），或在 Spec 009 之后从 IM 的交互式
按钮/卡片。claude SDK 经 `can_use_tool` 中继，Codex 经其 `requestApproval`
JSON-RPC。

如今有两点让这个形态不再成立：

1. **它与 owner 配对冗余。** 一个 channel 只听命于唯一已配对的 owner，非
   owner 消息被忽略；web 控制台也是本人。agent 执行的每一条指令都是 owner
   刚刚下达的。逐工具弹窗只是在重复确认 owner 已经授权的事——是摩擦，不是
   安全。这正是从聊天面驱动的同类 agent（Claude Code、Codex、OpenClaw、
   Hermes）不对单个工具调用设防的原因：人已经在回路里了。

2. **该中继从未端到端跑通过。** claude SDK 的 `can_use_tool` 路径在运行时报
   `Stream closed`（控制流在 Coffer 的运行方式下没建立起来）；只有白名单内
   被自动放行的工具能跑。交互式审批只在 fake 上测过，生产里实际是死的——
   「看起来有、实际不能用」。

留着一个坏掉又冗余的能力要付出真实的面积成本：`ApprovalGate` 域 + channel、
`ApprovalRequest` 事件、`can_use_tool`/`requestApproval` 中继、SeaTalk/Telegram
审批卡片 + 回调处理、web `ApprovalCard` 与审批席位、HTTP `/approvals` 路由、
`CHANNEL_APPROVAL_RESOLVED` 审计事件，以及它们的测试和文档。

## Decision

**移除整套交互式工具审批系统。** agent 始终以全权运行：

- claude SDK / claude CLI → `permission_mode = bypassPermissions`。
- Codex app-server → `approvalPolicy = "never"`、`sandbox = "danger-full-access"`。

没有 `permission_mode` 配置面、没有审批中继、web 和 IM 都没有审批 UI、没有
审批审计事件。web 控制台保留对 channel 驱动会话的**旁观**职责；不再占审批
席位。owner 配对（配对码 + 公网回调的签名校验）是信任边界。

删除：`ApprovalGate`/`ApprovalChannel`/`ApprovalRequest`/`ApprovalDecision`/
`ApprovalClick`/`ApprovalNotFound`、`submit_approval`、`can_use_tool`、Codex 审批
处理器、channel 的 `send_approval_prompt`/`resolve_approval_prompt`/
`on_approval_click` 与 `supports_buttons`、web `ApprovalCard`、
`/conversations/{id}/approvals` 路由 + `ApprovalSubmit` schema，以及
`CHANNEL_APPROVAL_RESOLVED` 审计事件。Spec 008 的 User Story 6/11、Spec 009 的
User Story 5 及其 FR/SC/场景一并移除。

## Consequences

- **平台更简单，面积更诚实。** turn 接缝变成 `run_turn(*, history)`，不带审批
  通道；`AgentEvent` 联合与 channel capabilities 收缩。不再有一个其实拦不住
  任何东西的「审批」假象。
- **安全压在唯一一道门上。** 没有逐工具弹窗后，全部安全性在于 owner 配对与
  回调签名校验。IM 入口公网可达，所以这两者必须保持正确——但它们本来就是
  真正的门禁；逐工具弹窗对 owner 自己并不提供任何额外保护。
- **默认全量文件系统/执行权限。** channel/web 的 agent 可在其工作目录里（对
  Codex 还可在沙箱外）跑任意命令。这与用户本地已经在用这些 CLI 的方式一致，
  是「owner 驱动的无人值守助手」可接受的取舍。
- **以后可重新引入。** 若将来某个场景需要设防（如共享或低信任 channel），可
  在一个设置后面把接缝加回来；它今天不为任何东西承重，所以现在移除将来要回
  退成本很低。

## Alternatives considered

- **保留中继、修 `Stream closed`、加一个权限等级设置**（全局 只读 / 可读写带
  审批 / 绕过 三档，审批转发给 channel）。否决：这是在投入精力重复确认 owner
  自己的指令，还要背上复活一个坏掉的传输层的成本，去做一件 owner 配对已经
  覆盖的事。YAGNI；真出现多信任场景再加回。
- **默认绕过、保留机制处于休眠。** 否决：留下死代码和一个「看起来有、实际
  不能用」的审批 UI——两头不讨好。
