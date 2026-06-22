# ADR-037：规则经运行时 SessionStart 注入；handoff 按需拉取

> English: [ADR-037-rules-runtime-injection.md](ADR-037-rules-runtime-injection.md)

**Status**: Accepted
**Date**: 2026-06-22
**Deciders**: Yuxing Wu
**Related**: spec `007-memory`（FR-049–FR-052）；基于 [ADR-026](ADR-026-memory-via-mcp-not-native-projection.md)（记忆经 MCP，而非原生投射）；参考 [`docs/research/memory-systems-landscape.zh.md`](../research/memory-systems-landscape.zh.md)

## Context

[ADR-026](ADR-026-memory-via-mcp-not-native-projection.md) 移除了 Coffer 的原生投射层：
Coffer 用自己的格式管理记忆，绝不写入、symlink 进、或关闭 agent 的原生记忆。它接受了一项代价 ——
失去 session 启动时的**环境式**加载 —— 并明确点名了补救：一个 **session 启动 hook**，把当前项目 +
全局记忆注入 agent 上下文（stdout / 上下文注入，绝不写文件），正是 `claude-mem` 与 Letta 的
`claude-subconscious` 走的路。那被延后到「后续一片」。这就是那一片。

竞品调研（`docs/research/memory-systems-landscape.zh.md`）确认了业界默认：共享记忆系统在运行时触达
一个中心库 —— 经 MCP/API 查询，或**经 session hook 注入** —— 绝不写另一个 agent 的原生文件。
Coffer 已交付 MCP 底座（`recall`/`remember`）与一条过程性 **rules lane**（`rules/rules.md`，FR-036），
后者被**有意排除在 `recall` 之外**，因为 rules 本就该**环境式交付**，而非靠一个想起来搜索的模型去发现。
没有注入机制，rules lane 就只写不读：agent 永远不读它。

两个外部事实决定了机制：

1. **Claude Code 与 Codex 都有 SessionStart hook**，且共用同一套 JSON schema（顶层 `hooks` 键；
   Claude Code 在 `~/.claude/settings.json`，Codex 在 `~/.codex/hooks.json`）。hook 打印
   `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": …}}`，不能阻塞
   agent，且在 resume/clear/compact 时重跑。这正是一个不碰任何记忆或指令文件的环境式上下文通道。
2. **只有 Claude Code 有 SessionEnd hook。** Codex 不发 session-end 事件（只有每轮的 `Stop`）。
   故即时的关闭即蒸馏对 Claude Code 可用、对 Codex 不可用 —— 这是设计必须吸收而非对抗的不对称。

## Decision

**Coffer 在运行时把 rules lane 交付到每个受管 agent：安装一个 SessionStart hook，注入一个
只作为上下文的规则 bundle —— 绝不原生写文件（ADR-026）。handoff 不被注入；它经 `coffer__resume`
按需拉取。**

具体：

- **SessionStart 注入（FR-049）。** Coffer 把自己的条目装进 agent 顶层 `hooks` 键（Claude Code
  `settings.json`；Codex `hooks.json` —— 同一套 JSON schema），只按命令 basename 识别它的
  `coffer-hook` 条目、不动用户 hook；安装/卸载幂等且原子（`.bak`），并审计
  `AGENT_HOOK_INSTALLED`/`UNINSTALLED`。SessionStart 时 `coffer-hook` 控制台脚本（agent 名烤进
  其参数）回调 daemon —— `GET /api/v1/agents/{name}/session-context?cwd=<cwd>` —— daemon 组装
  bundle：**全局规则（始终）** + **当前项目规则（cwd 解析到 git 项目时）**，先项目后全局。hook 把它
  作为 `additionalContext` 输出并退出 0。**它绝不阻塞 agent**：无 hook、daemon 不可达、超时或报错
  → 不注入、仍退出 0。它在 resume/clear/compact 时重跑。
- **播种的内置规则（FR-050）。** bundle 始终携带两条 Coffer 播种的规则（即便 rules lane 为空也在场）：
  (a) 调 `coffer__resume()` 接续此前工作，(b) 一条软引导，优先用 `coffer__remember`/`coffer__recall`
  而非 agent 的原生记忆。**handoff 正文本身不被注入** —— 它经 `coffer__resume`（FR-025）按需拉取，
  于是 bundle 保持精简、陈旧现场绝不被硬塞进上下文。
- **SessionEnd 蒸馏，仅 Claude Code（FR-051）。** Coffer 为 Claude Code 安装一个 SessionEnd hook，
  关闭时调 `POST /api/v1/agents/{name}/sessions/{session_id}/end`；daemon 把刚关闭的会话蒸馏进
  journal 记忆带，复用 slice-3b 蒸馏路径与 FR-046 `distilled_sessions` 幂等账本（绝不重复蒸馏，
  已蒸馏 / 无模型 / 非 git 项目时为 no-op）。**Codex 不安装 SessionEnd hook**，退回到 FR-046 补扫
  —— 补扫仍是写入保证；hook 只降低延迟。
- **可选 `disable_native_memory`（FR-052）。** 一个 per-agent 配置，**默认 `false`**（Coffer 绝不碰
  原生记忆 —— ADR-026 姿态）。打开时 Coffer 原子写入 agent 的原生记忆关闭开关（Claude Code
  `autoMemoryEnabled=false`；Codex `features.memories=false` + `memories.generate_memories=false`），
  并在关闭/卸载时**恢复**。这是一个**洁净选项**（避免第二份发散的记忆副本），不是写入保证的必要条件。

## Consequences

**Positive**

- **环境式 rules 而不碰原生文件。** rules 在 session 启动时免费加载，正是 ADR-026 延后的那项收益 ——
  由业界默认机制（session-hook 上下文注入）交付，而非原生投射。
- **不侵入（仍是 ADR-026）。** 注入的 bundle 是上下文而非写文件；hook 条目可逆且只识别 Coffer
  自己那行。只有用户显式启用 `disable_native_memory` 时才碰原生记忆。
- **结构性稳健。** 无 hook 或注入失败绝不阻塞 agent（退出 0）；无论 `disable_native_memory` 开关如何，
  规则 bundle 与 session-end 蒸馏都照常工作。
- **Claude Code 上更低延迟的捕获**（经 SessionEnd hook），而 FR-046 补扫为两个 agent 守住写入保证。

**Negative**

- **per-agent hook 形态维护。** Coffer 现在要跟踪每个 agent 的 hooks 配置形态与原生记忆关闭开关 ——
  一个会随上游格式演进而漂移的小面（缓解：幂等、按 basename 限定的安装；两个 agent 今天共用 SessionStart
  JSON schema）。
- **Codex 不对称。** Codex 没有关闭即蒸馏；其会话只由周期性补扫捕获，故捕获延迟高于 Claude Code。
  接受 —— 补扫是保证；hook 是延迟优化，不是正确性要求。
- **bundle 大小上限。** `additionalContext` 有界（约 10k 字符）；超大 rules lane 可能被截断。暂时接受
  （rules 本就该少而持久；organizer 让 lane 保持精简）。

## Alternatives Considered

**把 handoff 正文也注入（而不仅是一条 resume 规则）。** 否决：handoff 是按分支记账、可能陈旧的工作
现场；把它硬塞进每个会话的上下文有误导 agent 的风险并使 bundle 臃肿。经 `coffer__resume`（带新鲜度
标注）按需拉取既精确又小。

**把 rules render 进原生文件（托管块、不 symlink）。** ADR-026 已否决的更软投射 —— 它仍写用户的
配置文件（业界避开的动作）、仍需 per-agent 适配器。session 启动注入不碰任何文件就达到同样的环境式效果。

**纯 MCP —— 让 agent 按需 `recall` 规则。** 对 rules 特别地否决：rules 是必须在 agent 动作前在场的
祈使性引导，而非只在它想起来搜索时才取回。这正是 rules lane 被排除在 `recall` 之外、改由注入交付的原因。

**用每轮 `Stop` 事件在 Codex 上近似 SessionEnd。** 否决：`Stop` 每轮都触发、不在会话关闭时触发，
故要么过度蒸馏、要么需要自己的 settle/debounce 逻辑 —— 重复 FR-046 补扫，而后者已干净地解决
「已结束、尚未蒸馏、幂等」。Codex 复用补扫。
