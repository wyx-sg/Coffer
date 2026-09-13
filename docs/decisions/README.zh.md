# 架构决策记录 (Architecture Decision Records, ADR)

> English: [README.md](./README.md)

Coffer 将每一项重大的技术或架构决策都记录为一份 ADR。ADR 关注的是
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

- 文件名：`short-kebab-case-title.md` —— 就是标题的 kebab-case 形式，不带编号。
  之所以去掉编号：删除一份 ADR 会在序号里留下一个洞，而把这些洞压紧，会让所有
  仍然指向某个已退役编号的引用，悄无声息地指到一份毫不相干的现行决策上 ——
  这种事已经发生过一次。名字不会这样错位，而时间顺序由每份 ADR 自己的 `Date`
  承载。
- 本目录记录的是**当前生效**的设计，而非编年档案。读者必须能通过阅读现存 ADR
  直接得到今天的答案，而不必回放一条取代链。因此：
  - 决策发生变更时，**直接改写拥有该决策的那份 ADR**。
  - 当某份 ADR 所决定的东西被**整体移除**时，删除该 ADR。
  - 仅当被取代的设计仍能解释当前设计所继承的某项约束时，才保留
    `Superseded by <标题>` 标记。
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
| `Superseded by <标题>`  | 已不再是当前结论；链接到其替代者。 |
| `Deprecated`            | 已废弃且无替代（罕见）。           |

## 模板 (Michael Nygard 格式)

```markdown
# <short title in title case>

**Status**: Proposed | Accepted | Superseded by [<标题>](<文件名>.md)
**Date**: YYYY-MM-DD
**Deciders**: <names / roles>
**Related**: [<ADR 标题>](<文件名>.md), spec/…, issue/PR/…

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

| ADR | 标题 | 状态 |
| --- | --- | --- |
| [`resource-framework-upfront`](resource-framework-upfront.zh.md) | 提前设计资源框架 | Accepted |
| [`code-layout-layer-first`](code-layout-layer-first.zh.md) | 代码布局 —— 分层优先，按 kind 分子目录 | Accepted |
| [`resource-identifier-format`](resource-identifier-format.zh.md) | 资源标识符格式 —— `<kind>:<name>`，而非 URN | Accepted |
| [`capability-state-model`](capability-state-model.zh.md) | MCP 能力状态 —— 偏好持久化于 DB，列表实时查询上游 | Accepted |
| [`session-subprocess-model`](session-subprocess-model.zh.md) | 每个下游客户端会话一套独立的上游子进程 | Accepted |
| [`daemon-detect-or-spawn`](daemon-detect-or-spawn.zh.md) | Daemon 探测或拉起模式 | Accepted |
| [`daemon-serves-the-token-in-the-page`](daemon-serves-the-token-in-the-page.zh.md) | 由 daemon 把 token 放进它提供的页面里，并以 Host 请求头把守 | Accepted |
| [`everything-is-a-resource-kind`](everything-is-a-resource-kind.zh.md) | 信息架构 —— 一切皆 resource kind | Amended（2026-05-30、2026-06-11） |
| [`distribution-pyinstaller`](distribution-pyinstaller.zh.md) | 分发 —— 用 PyInstaller 打包 daemon、shim 与 CLI | Accepted |
| [`cross-platform-skill-delivery`](cross-platform-skill-delivery.zh.md) | 跨平台 skill 投递 —— Symlink / Junction / Copy-Fallback | Accepted |
| [`files-as-truth-sqlite-retrieval`](files-as-truth-sqlite-retrieval.zh.md) | 检索栈 —— markdown 文件即事实源，SQLite FTS5 + sqlite-vec，可配置 embedding | 已被 [Knowledge Is Plain Files](knowledge-is-plain-files.zh.md) 取代 |
| [`knowledge-is-plain-files`](knowledge-is-plain-files.zh.md) | 知识层是一个文件目录，不是一个索引 | Accepted |
| [`agent-native-shared-memory`](agent-native-shared-memory.zh.md) | 跨 agent 共享的单一知识 store | Accepted —— 投影那一半被 [Memory via MCP](memory-via-mcp-not-native-projection.zh.md) 取代 |
| [`channel-adapter-framework`](channel-adapter-framework.zh.md) | Channel Adapter 框架 | Accepted |
| [`envelope-encrypted-credential-store`](envelope-encrypted-credential-store.zh.md) | 信封加密的凭据存储 | Accepted |
| [`vault-export-import`](vault-export-import.zh.md) | 仓库导出与导入 | Accepted |
| [`industrial-grade-harness-in-layers`](industrial-grade-harness-in-layers.zh.md) | 工业级 Harness，分层建设 | Proposed |
| [`tool-retrieval-for-overload`](tool-retrieval-for-overload.zh.md) | 面向聚合过载的工具检索 | Accepted —— 被 [Built-in Agent Is Internal](builtin-agent-is-internal-capability.zh.md) 与 [Budget-Driven Tool Tiering](budget-driven-tool-tiering.zh.md) 修订 |
| [`close-the-eval-flywheel`](close-the-eval-flywheel.zh.md) | 闭合 Eval 飞轮（Loop Engineering） | Accepted |
| [`channel-entrypoint-differentiation`](channel-entrypoint-differentiation.zh.md) | Channel 入口差异化层 | Accepted |
| [`builtin-agent-is-internal-capability`](builtin-agent-is-internal-capability.zh.md) | 内置 agent 是内部能力，不是聊天人格 | Accepted |
| [`remove-tool-approval`](remove-tool-approval.zh.md) | 移除工具审批系统；owner 配对即门禁 | Accepted |
| [`memory-via-mcp-not-native-projection`](memory-via-mcp-not-native-projection.zh.md) | 记忆经 MCP 访问，而非原生投射 | Accepted |
| [`skill-content-trust-layer`](skill-content-trust-layer.zh.md) | Skill 内容信任层（启发式扫描，警告而非拦截） | Reverted（2026-06-20） |
| [`consume-official-mcp-registry`](consume-official-mcp-registry.zh.md) | 消费官方 MCP Registry 做服务器发现 | Reverted（2026-06-20） |
| [`chat-single-owner-live-mirror`](chat-single-owner-live-mirror.zh.md) | Chat 是单属主的实时镜像 | Accepted |
| [`provider-switching`](provider-switching.zh.md) | Provider Switching | Proposed |
| [`daemon-proxies-os-file-actions`](daemon-proxies-os-file-actions.zh.md) | 本地 daemon 代理 OS 文件动作 | Accepted |
| [`retrieval-mode-is-internal`](retrieval-mode-is-internal.zh.md) | 检索 mode 是引擎内部细节；外部界面只暴露「查询→答案」 | 已被 [Knowledge Is Plain Files](knowledge-is-plain-files.zh.md) 取代 |
| [`channel-media`](channel-media.zh.md) | Channel 媒体 —— DB 只存引用，发送时按 agent 物化 | Accepted —— 其中 v1「推迟持久化附件块」的决定被 [Persisted Attachment Reference](persisted-attachment-reference.zh.md) 取代 |
| [`persisted-attachment-reference`](persisted-attachment-reference.zh.md) | 把 channel 附件持久化为引用块，从历史重新物化 | Accepted |
| [`per-agent-resource-scope`](per-agent-resource-scope.zh.md) | 按 agent 的资源 scope | Accepted |
| [`budget-driven-tool-tiering`](budget-driven-tool-tiering.zh.md) | 网关侧的预算驱动工具分层 | Accepted |
| [`seatalk-websocket-inbound`](seatalk-websocket-inbound.zh.md) | SeaTalk 入站走 WebSocket，SDK 由 operator 提供 | Accepted |
