# 架构决策记录 (Architecture Decision Records, ADR)

> English: [README.md](./README.md)

Coffer 将每一项重大的技术或架构决策都记录为带编号的 ADR。ADR 关注的是
**为什么** —— 代码体现*做了什么*，而本目录回答*我们为什么做出了这样的选择*。

## 何时写一份 ADR

凡是符合以下任一条件的决策都应写一份 ADR：

- 日后难以更改，除非破坏兼容性或大面积重写。
- 影响多个模块，或对未来工作施加结构性约束。
- 存在并不显而易见的取舍，未来的工程师（或未来的你）会产生疑问。
- 偏离了默认做法、流行约定，或项目规则（章程条款、既有 ADR）。

以下情况**不**需要写 ADR：

- 不改变 API 表面的库版本升级。
- 例行的 bug 修复。
- 属于规约 (spec) 的 `## Assumptions` 或 `## Out of Scope` 中的范围决策。
- 命名或格式偏好。

## 文件命名与生命周期

- 文件名：`ADR-NNN-short-kebab-case-title.md` —— NNN 是补零的序号
  (`ADR-001-…`, `ADR-002-…`, …)。不得重新编号。
- 本目录记录的是**当前生效**的设计，而非编年档案。读者必须能通过阅读现存 ADR
  直接得到今天的答案，而不必回放一条取代链。因此：
  - 决策发生变更时，**直接改写拥有该决策的那份 ADR**。
  - 当某份 ADR 所决定的东西被**整体移除**时，删除该 ADR。
  - 仅当被取代的设计仍能解释当前设计所继承的某项约束时，才保留
    `Superseded by ADR-NNN` 标记。
  历史由 git 保存：`git log --follow docs/decisions/` 可以找回本目录不再陈述的
  任何决策。
- 一份文件只承载一个决策。
- 保持每份 ADR 精简 —— 通常不超过 200 行。如果你需要更多篇幅，那说明你在写
  实现细节而非决策本身。

## 状态取值

| 状态                    | 含义                               |
| ----------------------- | ---------------------------------- |
| `Proposed`              | 已草拟，尚未采纳。                 |
| `Accepted`              | 已生效。                           |
| `Superseded by ADR-NNN` | 已不再是当前结论；链接到其替代者。 |
| `Deprecated`            | 已废弃且无替代（罕见）。           |

## 模板 (Michael Nygard 格式)

```markdown
# ADR-NNN: <short title in title case>

**Status**: Proposed | Accepted | Superseded by ADR-NNN
**Date**: YYYY-MM-DD
**Deciders**: <names / roles>
**Related**: ADR-…, spec/…, issue/PR/…

## Context

<What forces are at play? What problem are we solving? Existing constraints,
related ADRs, relevant constitutional clauses.>

## Decision

<The choice, in one or two clear sentences. Then the supporting reasoning.>

## Consequences

<What becomes easier? What becomes harder? What new obligations or follow-ons?>

## Alternatives Considered

<Each rejected option with a one-paragraph reason for rejection. This is the
section that future readers most often want — don't skip it.>
```

## 索引

| ADR                                                      | 标题                                                                      | 状态                                                                                                      |
| -------------------------------------------------------- | ------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| [001](ADR-001-resource-framework-upfront.md)             | 提前设计资源框架，而非等到第二个功能再做                                  | Accepted                                                                                                  |
| [002](ADR-002-code-layout-layer-first.md)                | 代码布局：分层优先，按 kind 分子目录                                      | Accepted                                                                                                  |
| [003](ADR-003-resource-identifier-format.md)             | 资源标识符格式：`<kind>:<name>`，而非 URN                                 | Accepted                                                                                                  |
| [004](ADR-004-capability-state-model.md)                 | MCP 能力状态：偏好持久化于 DB，列表实时查询上游                           | Accepted                                                                                                  |
| [005](ADR-005-session-subprocess-model.md)               | 每个下游客户端会话一套独立的上游子进程                                    | Accepted                                                                                                  |
| [006](ADR-006-daemon-detect-or-spawn.md)                 | Daemon 探测或拉起模式；daemon 生命周期长于任何单个客户端                  | Accepted                                                                                                  |
| [007](ADR-007-everything-is-a-resource-kind.md)          | 信息架构：每个被管理的实体都是一种 resource kind                          | Accepted                                                                                                  |
| [008](ADR-008-distribution-pyinstaller.md)               | 分发：用 PyInstaller 打包 daemon、shim 与 CLI                    | Accepted                                                                                                  |
| [009](ADR-009-cross-platform-skill-delivery.md)          | 跨平台 skill 投递：symlink / junction / copy-fallback                     | Accepted                                                                                                  |
| [012](ADR-012-files-as-truth-sqlite-retrieval.md)        | 检索栈：markdown 文件即事实源，SQLite FTS5 + sqlite-vec，可配置 embedding | Accepted                                                                                                  |
| [013](ADR-013-agent-native-shared-memory.md)             | 跨 agent 共享的单一知识 store                                             | Accepted —— 投影那一半被 [026](ADR-026-memory-via-mcp-not-native-projection.md) 取代                      |
| [014](ADR-014-channel-adapter-framework.md)              | Channel adapter 框架：薄 adapter 架在聊天平台接缝之上                     | Accepted                                                                                                  |
| [015](ADR-015-envelope-encrypted-credential-store.md)    | 信封加密的凭据存储（Fernet 密文存于 SQLite，主密钥默认文件）              | Accepted                                                                                                  |
| [016](ADR-016-vault-export-import.md)                     | 仓库导出与导入                                                               | Accepted                                                                                                  |
| [017](ADR-017-industrial-grade-harness-in-layers.md)     | 工业级 Harness，分层建设                                                  | Proposed                                                                                                  |
| [018](ADR-018-tool-retrieval-for-overload.md)            | 面向聚合过载的工具检索（`coffer__search_tools`）                          | Accepted —— 被 [024](ADR-024-builtin-agent-is-internal-capability.md) 修订                                |
| [019](ADR-019-close-the-eval-flywheel.md)                | 闭合 eval 飞轮（loop engineering）                                        | Accepted                                                                                                  |
| [021](ADR-021-chat-as-vault-console.md)                  | 把 Agent Chat 重定位为 Vault Console（金库控制台）                        | Accepted —— 部分被 [024](ADR-024-builtin-agent-is-internal-capability.md) 取代                            |
| [023](ADR-023-channel-entrypoint-differentiation.md)     | Channel 入口区分层                                                        | Accepted                                                                                                  |
| [024](ADR-024-builtin-agent-is-internal-capability.md)   | 内置 agent 是内部能力，不是聊天人格                                       | Accepted                                                                                                  |
| [025](ADR-025-remove-tool-approval.md)                   | 移除工具审批系统；owner-pairing 即关卡                                    | Accepted                                                                                                  |
| [027](ADR-027-skill-content-trust-layer.md)              | Skill 内容信任层（启发式扫描，警告而非拦截）                              | Accepted                                                                                                  |
| [029](ADR-029-consume-official-mcp-registry.md)          | 消费官方 MCP Registry 做服务器发现                                        | Reverted                                                                                                  |
| [034](ADR-034-retrieval-mode-is-internal.md)             | 检索 mode 是引擎内部细节；外部界面只暴露「查询→答案」                     | Accepted                                                                                                  |
| [037](ADR-037-rules-runtime-injection.md)                | 规则经运行时 SessionStart 注入；handoff 按需拉取                          | Accepted                                                                                                  |
