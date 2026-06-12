# Coffer 路线图

> English: [roadmap.md](./roadmap.md)

> 仅列出真正进入承诺状态的规范。我们不在这里登记尚未承诺要做的规范；
> 路线图条目反映的是已经作出的决定，而非愿望。未来的条目要等到对应规范
> 写出来之后才会出现在这里，不提前预留。

## 进行中 (Active)

| #   | Spec                                                                          | 状态                                     |
| --- | ----------------------------------------------------------------------------- | ---------------------------------------- |
| 001 | **MCP Gateway** ([spec](../../specs/001-mcp-gateway/spec.md))                 | 已采纳 — 代码已随 PR #14 合并            |
| 002 | **UI Shell 与视觉语言** ([spec](../../specs/002-ui-shell/spec.md))            | 已采纳 — 代码已随 PR #23 合并            |
| 003 | **MCP Gateway Desktop** ([spec](../../specs/003-mcp-gateway-desktop/spec.md)) | 已采纳 — 代码评审中 (PR #28)             |
| 004 | **Agent Registry** ([spec](../../specs/004-agent-registry/spec.md))           | 已采纳 — 代码已合并                       |
| 005 | **Skill Manager** ([spec](../../specs/005-skill-manager/spec.md))             | 已采纳 — 代码已合并                       |
| 006 | **Knowledge Base** ([spec](../../specs/006-knowledge-base/spec.md))           | 已采纳 — 代码已随 PR #55 合并 (知识基底的 KB 面，[ADR-012](../../docs/decisions/ADR-012-files-as-truth-sqlite-retrieval.md))                                                                                     |
| 007 | **Memory** ([spec](../../specs/007-memory/spec.md))                           | 已采纳 — 代码已随 PR #55/#58 合并 (跨 agent 共享、原生的 memory，[ADR-012](../../docs/decisions/ADR-012-files-as-truth-sqlite-retrieval.md) + [ADR-013](../../docs/decisions/ADR-013-agent-native-shared-memory.md)) |
| 008 | **Agent Chat** ([spec](../../specs/008-agent-chat/spec.md))                   | 已采纳 — 代码已随 PR #57 合并            |
| 009 | **Channels** ([spec](../../specs/009-channels/spec.md))                       | 已接受 — 代码已随 PR #59 合并 ([ADR-014](../../docs/decisions/ADR-014-channel-adapter-framework.md)) |

## 明确不做的事 (当前规范范围内)

下面列出 `001-mcp-gateway` **不**会随首版交付的能力，明确写在这里，是
为了避免评审者把这些缺席当成疏漏。

- **macOS Apple 公证 (notarisation)** — 需要付费的 Apple Developer 账号；
  当前用户首次启动时手动解除 quarantine。等账号到位再补。
- **多机同步** — 章程禁止云端事实记录方；如需放开，必须走章程修订。
- **网关侧的流式进度转发 (Streaming progress forwarding through the
  gateway)** — 主流 MCP gateway 都不做这件事；本规范与生态保持一致
  (透传 token + 重置超时，不主动转发)。
- **系统级服务安装** (launchd / systemd / Windows service) — 对
  [ADR-006](../../docs/decisions/ADR-006-daemon-detect-or-spawn.md) 的
  detect-or-spawn 模式只是叠加增强；以后可作为
  `coffer daemon install --system` 增加，不会破坏当前模型。
- **插件市场 / 第三方 kind 创作** — 见
  [ADR-001 / ADR-002 中的备选方案讨论](../../docs/decisions/ADR-001-resource-framework-upfront.md)。
- **工具调用参数或结果的持久化** — 调用日志仅记录「谁 / 何时 / 耗时多久 /
  结果如何」；参数与返回值的内容视为敏感数据，不进数据库。

## 跨规范决策 (Cross-cutting decisions)

- [ADR-007：一切皆 resource kind](../../docs/decisions/ADR-007-everything-is-a-resource-kind.md) — 各 UI 规范共享的侧栏 / IA 架构决策。

## 本文件如何生长

每当一份新规范被写出 (在 Coffer 的流程中由 `/speckit-specify` 触发)，
就在 **Active** 表中追加一行，写明编号、标题与状态。规范交付后，更新
其状态。**不**为还没写出来的 feature 预占编号、预起名字。
