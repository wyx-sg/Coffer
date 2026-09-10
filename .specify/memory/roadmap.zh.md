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
| 004 | **Agent Registry** ([spec](../../specs/004-agent-registry/spec.md))           | 已采纳 — 代码已合并 · **重新定位：** `builtin` agent 不再作为注册的 chat agent，改为 Coffer 的内部能力；registry 只列受管 agent（[ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.zh.md)） · **收窄为两个类型：** registry 只支持 `claude_code` 与 `codex`。`opencode`、`hermes`、`cursor`、`openclaw` 已移除——它们都没装在维护者机器上，其 facet 全部照文档与一次性探针写成，本地无法回归验证。移除它们把三种上下文注入机制收敛回一种 shell hook，并退役了逐 facet 能力矩阵（spec 004 FR-003a） · **2026-09-10 facet 收窄：** 最后那种 shell hook 也一并去掉 —— `coffer-hook` SessionStart 二进制、hook 安装面与 `session-context` 路由全部删除，随之删除的还有原生记忆扫描/导入、plugin 的开关/卸载、MCP entry 的移除/开关这些写操作。Coffer 读别的工具的配置、并从中 adopt；但不再往里写 |
| 005 | **Skill Manager** ([spec](../../specs/005-skill-manager/spec.md))             | 已采纳 — 代码已合并                                                                                                                                                                                                                                                                                                                                                                                                                        |
| 007 | **知识层 (Knowledge Layer)** ([spec](../../specs/007-memory/spec.md))            | 已采纳 — 代码已随 PR #55/#58 合并（[ADR-012](../../docs/decisions/ADR-012-files-as-truth-sqlite-retrieval.md) + [ADR-013](../../docs/decisions/ADR-013-agent-native-shared-memory.md)） · **2026-09-10 合并：** spec 006（Knowledge Base）被吸收进本规范，其目录已删除。memory 与知识库从一开始就是同一个基底的两副面孔——`documents`、`chunks`、FTS5 与 sqlite-vec 一直是共用的——因此二者塌缩成单一 resource kind `knowledge`：单一存储根 `~/.coffer/knowledge/<scope>/`，下分 `knowledge/`（agent 写入的条目）、`inbox/`（摄取进来的文档）、`rules/`、`handoff/`、`superseded/` 几条 lane；scope 直接从资源名读出（`global` 与 `project-<ULID>` 会自动开通，其他名字则是用户刻意创建的集合）；MCP 工具从 12 个收敛到 8 个；CLI 只剩 `coffer knowledge` 一个命令组；路由统一到 `/api/v1/knowledge`；页面统一到一个 **Knowledge** 页。目录名刻意保留为 `specs/007-memory/`——它既是验收审计的 spec id，也是所有入链的落点——因此这个目录名从此只具历史含义 · **2026-09-09 移除：** transcript distillation（记忆闭环里自动摄取的那一半）及其写入的 `journal` lane；写入改为完全显式——`coffer__write` 写入、`coffer__search` 取回 · **2026-09-10 移除：** rules lane 的投递通道 —— FR-049（SessionStart hook）、FR-050（两条内置种子规则）、FR-052（`disable_native_memory`）、FR-055（环境式项目知识索引）。规则照样被写入、分类、存储与同步；但没有任何东西再把它们推进会话，agent 必须自己去调知识层的工具——该层暴露的八个 `coffer__` 工具是 `search`、`grep`、`read`、`list`、`write`、`delete`、`set_handoff`、`resume`。这确实丢掉了跨 agent 记忆中投递的那一半，之所以接受，是因为那个 hook 虽然上线过，却从未真正安装到维护者的机器上，注入路径一次都没跑过 · **修订 2026-07-10：**同项目 knowledge scope 的 AI 辅助合并——内部引擎判断 + 增量归并 + 防复活身份别名，现已并入 spec 的 FR-056…FR-058 |
| 009 | **Channels** ([spec](../../specs/009-channels/spec.md))                       | 已采纳 — 代码已随 PR #59 合并（[ADR-014](../../docs/decisions/ADR-014-channel-adapter-framework.zh.md)） · **并入 spec 008（Agent Chat），2026-09-10：** Web 端 Chat 页面删除 —— 它从未被当作聊天界面用过，库里每一条会话都来自 channel —— 因此它与 channels 共用的那层 turn 平台（agent provider 注册表、适配器、会话存储、turn 生命周期）改在这里描述为 FR-043…FR-055，`specs/008-agent-chat/` 整个目录删除。ADR-021（chat 作为 Vault Console）与 ADR-031（chat 是单属主实时镜像）一并删除 · **语音转写移出本机，2026-09-10：** FR-022 改为经用户的 `internal_default` 连接转写，不再随包 `whisper.cpp` sidecar。这退役了 ADR-039、`whisper-cli` 二进制及其从源码 cmake 构建的整条链（本项目最重的构建依赖），以及 `[voice]` / `[voice-mlx]` 两个 extra。这是唯一一处用户内容可能离开本机的地方，且默认关闭：没有指定内部连接时，音频以文件形式交给 agent，与本地引擎缺席时完全一致 |
| 010 | **仓库导出与导入** ([spec](../../specs/010-sync/spec.md))                     | 已接受 — **从持续多机同步降级而来。** Coffer 现在把仓库导出到用户选定的目录，并能把这样一个目录导入回来；没有远程、没有 git 工作区、没有后台 worker、没有机器注册表，也没有墓碑（[ADR-016](../../docs/decisions/ADR-016-vault-export-import.zh.md)）。把目录在机器之间搬运是用户自己的事，因此该特性无需对原则 1 做任何例外——章程 0.4.0 修订案移除了 0.3.0 的“用户掌控介质”例外 · **作用域塌缩为单轴：** 资源的 `scope` 是一个 agent 名字列表，而不是机器 × agent 矩阵；顶层的 Machines 舰队视图连同它所渲染的机器身份一并移除（[ADR-045](../../docs/decisions/ADR-045-per-agent-resource-scope.zh.md)） · **2026-09-10 密钥引导改传材料、不传路径：** `POST /sync/key/export` 返回 `{material}`，`POST /sync/key/import` 接收它；文件 I/O 各表面自己做（CLI 自己写/读文件，Web UI 用浏览器下载与 `<input type="file">`），守护进程从此不打开任何由调用方指定的路径，也不再执行 `osascript`/`zenity` 保存/打开对话框 |
| 011 | **Provider 切换** ([spec](../../specs/011-provider-switching/spec.md))        | 草案 — 共享的 provider profile 注册表；配置一次，原子地切进 Claude Code / Codex 的原生配置；凭据隔离经由 apiKeyHelper / env_key；Fernet 保险库 + 完整审计 + 同步（[ADR-032](../../docs/decisions/ADR-032-provider-switching.zh.md)） |

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
