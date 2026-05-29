# 架构决策记录 (Architecture Decision Records, ADR)

> English: [README.md](./README.md)

Coffer 将每一项重大的技术或架构决策都记录为带编号、不可变的 ADR。ADR 关注的是
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
- ADR 仅追加。若需变更某项决策，应新写一份 ADR 用以 **Supersedes** 旧的决策；
  并把旧的标记为 `Status: Superseded by ADR-NNN`。
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

| ADR                                                      | 标题                                                      | 状态     |
| -------------------------------------------------------- | --------------------------------------------------------- | -------- |
| [001](ADR-001-resource-framework-upfront.md)             | 提前设计资源框架，而非等到第二个功能再做                  | Accepted |
| [002](ADR-002-code-layout-layer-first.md)                | 代码布局：分层优先，按 kind 分子目录                      | Accepted |
| [003](ADR-003-resource-identifier-format.md)             | 资源标识符格式：`<kind>:<name>`，而非 URN                 | Accepted |
| [004](ADR-004-capability-state-model.md)                 | MCP 能力状态：偏好持久化于 DB，列表实时查询上游           | Accepted |
| [005](ADR-005-session-subprocess-model.md)               | 每个下游客户端会话一套独立的上游子进程                    | Accepted |
| [006](ADR-006-daemon-detect-or-spawn.md)                 | Daemon 探测或拉起模式；daemon 生命周期长于任何单个客户端  | Accepted |
| [007](ADR-007-everything-is-a-resource-kind.md)          | 信息架构：每个被管理的实体都是一种 resource kind          | Accepted |
| [008](ADR-008-distribution-pyinstaller-tauri-sidecar.md) | 分发：用 PyInstaller 打包 daemon + shim，作为 Tauri sidecar | Accepted |
