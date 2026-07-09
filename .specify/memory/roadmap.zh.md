# Coffer 路线图

> English: [roadmap.md](./roadmap.md)

> 仅列出真正进入承诺状态的规范。我们不在这里登记尚未承诺要做的规范；
> 路线图条目反映的是已经作出的决定，而非愿望。未来的条目要等到对应规范
> 写出来之后才会出现在这里，不提前预留。

## 进行中 (Active)

| #   | Spec                                                                          | 状态                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| --- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 001 | **MCP Gateway** ([spec](../../specs/001-mcp-gateway/spec.md))                 | 已采纳 — 代码已随 PR #14 合并；新增 `coffer__search_tools` 工具检索以应对聚合过载 ([ADR-018](../../docs/decisions/ADR-018-tool-retrieval-for-overload.zh.md)) · `coffer__search_tools` 获得带 BM25 回退的语义（嵌入）排序，并新增对知识/记忆的 `coffer__ask` agentic 检索（[ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.zh.md) 修订 ADR-018）                                                               |
| 002 | **UI Shell 与视觉语言** ([spec](../../specs/002-ui-shell/spec.md))            | 已采纳 — 代码已随 PR #23 合并                                                                                                                                                                                                                                                                                                                                                                                                              |
| 003 | **MCP Gateway Desktop** ([spec](../../specs/003-mcp-gateway-desktop/spec.md)) | 已采纳 — 代码已随 PR #28 合并                                                                                                                                                                                                                                                                                                                                                                                                              |
| 004 | **Agent Registry** ([spec](../../specs/004-agent-registry/spec.md))           | 已采纳 — 代码已合并 · **重定位：** `builtin` agent 退出注册的聊天 agent，重塑为 Coffer 内部能力；注册表只列受管 agent（[ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.zh.md)）· **重新加宽（[ADR-040](../../docs/decisions/ADR-040-re-widen-agent-registry.zh.md)）：** 重新加回 `opencode` / `hermes` / `cursor`；`openclaw` 已作为第六个受管 agent 交付（[ADR-044](../../docs/decisions/ADR-044-openclaw-managed-agent.zh.md)，推翻 ADR-040 的「对等网关、留在外面」结论）；三种注入 mode（`SHELL_COMMAND`/`PLUGIN_DROP`/`INSTRUCTIONS_BLOCK`）已横跨六个类型交付                                                                                                                                                                                                                                |
| 005 | **Skill Manager** ([spec](../../specs/005-skill-manager/spec.md))             | 已采纳 — 代码已合并                                                                                                                                                                                                                                                                                                                                                                                                                        |
| 006 | **Knowledge Base** ([spec](../../specs/006-knowledge-base/spec.md))           | 已采纳 — 代码已随 PR #55 合并 (知识基底的 KB 面，[ADR-012](../../docs/decisions/ADR-012-files-as-truth-sqlite-retrieval.md))                                                                                                                                                                                                                                                                                                               |
| 007 | **Memory** ([spec](../../specs/007-memory/spec.md))                           | 已采纳 — 代码已随 PR #55/#58 合并 (跨 agent 共享、原生的 memory，[ADR-012](../../docs/decisions/ADR-012-files-as-truth-sqlite-retrieval.md) + [ADR-013](../../docs/decisions/ADR-013-agent-native-shared-memory.md)) · **扩展进行中：** transcript distillation —— 只读摄取本地 agent 对话记录 → LLM 提炼 → memory 事实；不分配新 spec 编号（[ADR-020](../../docs/decisions/ADR-020-transcript-distillation.zh.md)）                       |
| 008 | **Agent Chat** ([spec](../../specs/008-agent-chat/spec.md))                   | 已采纳 — 代码已随 PR #57 合并 · **重定位：** Agent Chat → Vault Console（对金库说话 + 旁观/审批 channel 驱动的 turn）；移出浏览器内日常编码聊天（[ADR-021](../../docs/decisions/ADR-021-chat-as-vault-console.zh.md)） · **再次重定位：** 内置 agent 退出聊天人格；聊天只与受管 agent 对话、页面改回「聊天」，渠道旁观/审批职责存续（[ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.zh.md) 部分取代 ADR-021） |
| 009 | **Channels** ([spec](../../specs/009-channels/spec.md))                       | 已接受 — 代码已随 PR #59 合并 ([ADR-014](../../docs/decisions/ADR-014-channel-adapter-framework.md))                                                                                                                                                                                                                                                                                                                                       |
| 010 | **多机同步** ([spec](../../specs/010-sync/spec.md))                           | 已接受 — 通过用户自有 git 仓库同步仓库状态 ([ADR-016](../../docs/decisions/ADR-016-multi-machine-sync.md))；由章程 0.3.0 对原则 1 的修订解禁                                                                                                                                                                                                                                                                                               |

## 明确不做的事 (当前规范范围内)

下面列出 `001-mcp-gateway` **不**会随首版交付的能力，明确写在这里，是
为了避免评审者把这些缺席当成疏漏。

- **macOS Apple 公证 (notarisation)** — 需要付费的 Apple Developer 账号；
  当前用户首次启动时手动解除 quarantine。等账号到位再补。
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
- [ADR-018：面向聚合过载的工具检索](../../docs/decisions/ADR-018-tool-retrieval-for-overload.zh.md) — 修订 spec 001 的 `coffer__search_tools` 检索原语。
- [ADR-024：内置 agent 是内部能力，不是聊天人格](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.zh.md) — 让内置聊天人格退场（聊天只面向受管 agent）；把本地模型重塑为内部能力：语义化的 `coffer__search_tools`（修订 ADR-018）与新的对知识/记忆的 `coffer__ask` agentic 检索。

## 本文件如何生长

每当一份新规范被写出 (在 Coffer 的流程中由 `/speckit-specify` 触发)，
就在 **Active** 表中追加一行，写明编号、标题与状态。规范交付后，更新
其状态。**不**为还没写出来的 feature 预占编号、预起名字。
