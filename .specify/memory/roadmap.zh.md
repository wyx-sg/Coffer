# Coffer 路线图

> English: [roadmap.md](./roadmap.md)

> 仅列出真正进入承诺状态的规范。我们不在这里登记尚未承诺要做的规范；
> 路线图条目反映的是已经作出的决定，而非愿望。未来的条目要等到对应规范
> 写出来之后才会出现在这里，不提前预留。

## 进行中 (Active)

| #   | Spec                                                                          | 状态                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| --- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 001 | **MCP Gateway** ([spec](../../specs/001-mcp-gateway/spec.md))                 | 已采纳 — 代码已随 PR #14 合并；新增 `coffer__search_tools` 工具检索以应对聚合过载 ([ADR-018](../../docs/decisions/ADR-018-tool-retrieval-for-overload.zh.md)) · `coffer__search_tools` 获得带 BM25 回退的语义（嵌入）排序（[ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.zh.md) 修订 ADR-018） · **桌面外壳退役（2026-09-09）：** spec 003（MCP Gateway Desktop）退役，目录已删除；daemon 现在自己在它的 loopback origin 上提供构建好的 Web UI，`coffer open` 铸造一个一次性短时效 code 把已鉴权的会话交给浏览器，冻结态 daemon 在启动时把同目录二进制部署到 `~/.coffer/bin/`，发布形态收敛为单一 `coffer-cli-<triple>.tar.gz` 层级加一份聚合的 `SHA256SUMS`（spec 001 FR-022–FR-026、[ADR-008](../../docs/decisions/ADR-008-distribution-pyinstaller.zh.md)）                                                                                                   |
| 002 | **UI Shell 与视觉语言** ([spec](../../specs/002-ui-shell/spec.md))            | 已采纳 — 代码已随 PR #23 合并                                                                                                                                                                                                                                                                                                                                                                                                              |
| 004 | **Agent Registry** ([spec](../../specs/004-agent-registry/spec.md))           | 已采纳 — 代码已合并 · **重新定位：** `builtin` agent 不再作为注册的 chat agent，改为 Coffer 的内部能力；registry 只列受管 agent（[ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.zh.md)） · **收窄为两个类型：** registry 只支持 `claude_code` 与 `codex`。`opencode`、`hermes`、`cursor`、`openclaw` 已移除——它们都没装在维护者机器上，其 facet 全部照文档与一次性探针写成，本地无法回归验证。移除它们把三种上下文注入机制收敛回一种 shell hook，并退役了逐 facet 能力矩阵（spec 004 FR-003a） |
| 005 | **Skill Manager** ([spec](../../specs/005-skill-manager/spec.md))             | 已采纳 — 代码已合并                                                                                                                                                                                                                                                                                                                                                                                                                        |
| 006 | **Knowledge Base** ([spec](../../specs/006-knowledge-base/spec.md))           | 已采纳 — 代码已随 PR #55 合并 (知识基底的 KB 面，[ADR-012](../../docs/decisions/ADR-012-files-as-truth-sqlite-retrieval.md))                                                                                                                                                                                                                                                                                                               |
| 007 | **Memory** ([spec](../../specs/007-memory/spec.md))                           | 已采纳 — 代码已随 PR #55/#58 合并 (跨 agent 共享、原生的 memory，[ADR-012](../../docs/decisions/ADR-012-files-as-truth-sqlite-retrieval.md) + [ADR-013](../../docs/decisions/ADR-013-agent-native-shared-memory.md)) · **2026-09-09 移除：** transcript distillation（记忆闭环里自动摄取的那一半）及其写入的 `journal` 记忆带；写入改为完全显式 —— `coffer__remember` 写入、`coffer__recall` 取回，落在 `knowledge` / `rules` / `handoff` 三条记忆带上 · **修订 2026-07-10：**同项目记忆库的 AI 辅助合并——内部引擎判断 + 增量归并 + 防复活身份别名（[修订文档](../../specs/007-memory/amendment-2026-07-10-ai-store-merge.md)） |
| 008 | **Agent Chat** ([spec](../../specs/008-agent-chat/spec.md))                   | 已采纳 — 代码已随 PR #57 合并 · **重定位：** Agent Chat → Vault Console（对金库说话 + 旁观/审批 channel 驱动的 turn）；移出浏览器内日常编码聊天（[ADR-021](../../docs/decisions/ADR-021-chat-as-vault-console.zh.md)） · **再次重定位：** 内置 agent 退出聊天人格；聊天只与受管 agent 对话、页面改回「聊天」，渠道旁观/审批职责存续（[ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.zh.md) 部分取代 ADR-021） |
| 009 | **Channels** ([spec](../../specs/009-channels/spec.md))                       | 已接受 — 代码已随 PR #59 合并 ([ADR-014](../../docs/decisions/ADR-014-channel-adapter-framework.md))                                                                                                                                                                                                                                                                                                                                       |
| 010 | **仓库导出与导入** ([spec](../../specs/010-sync/spec.md))                     | 已接受 — **从持续多机同步降级而来。** Coffer 现在把仓库导出到用户选定的目录，并能把这样一个目录导入回来；没有远程、没有 git 工作区、没有后台 worker、没有机器注册表，也没有墓碑（[ADR-016](../../docs/decisions/ADR-016-vault-export-import.zh.md)）。把目录在机器之间搬运是用户自己的事，因此该特性无需对原则 1 做任何例外——章程 0.4.0 修订案移除了 0.3.0 的“用户掌控介质”例外 · **作用域塌缩为单轴：** 资源的 `scope` 是一个 agent 名字列表，而不是机器 × agent 矩阵；顶层的 Machines 舰队视图连同它所渲染的机器身份一并移除（[ADR-045](../../docs/decisions/ADR-045-per-agent-resource-scope.zh.md)） |

## 明确不做的事 (当前规范范围内)

下面列出 `001-mcp-gateway` **不**会随首版交付的能力，明确写在这里，是
为了避免评审者把这些缺席当成疏漏。

- **macOS Apple 公证 (notarisation)** — 需要付费的 Apple Developer 账号；
  当前用户对解压出来的发布二进制手动解除 quarantine。等账号到位再补。
- **桌面外壳** — 已于 2026-09-09 退役。每一次桌面端更新都要重新构建加重新
  安装，构建出的制品还会不断偏离源码；由 daemon 提供的 Web UI 只需重启
  daemon 并强制刷新。
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
- [ADR-024：内置 agent 是内部能力，不是聊天人格](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.zh.md) — 让内置聊天人格退场（聊天只面向受管 agent）；把本地模型重塑为内部能力：语义化的 `coffer__search_tools`（修订 ADR-018）。

## 本文件如何生长

每当一份新规范被写出 (在 Coffer 的流程中由 `/speckit-specify` 触发)，
就在 **Active** 表中追加一行，写明编号、标题与状态。规范交付后，更新
其状态。**不**为还没写出来的 feature 预占编号、预起名字。
