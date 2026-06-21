# ADR-034 — 收编原生记忆：读取 Agent 自己的逐项目记忆，导入 Coffer

> English: [ADR-034-adopt-native-memory.md](./ADR-034-adopt-native-memory.md)

- **状态：** 已接受
- **Spec:** [004-agent-registry](../../specs/004-agent-registry/spec.md)（FR-040 原生记忆扫描、FR-041 导入/收编）、[007-memory](../../specs/007-memory/spec.md)（整理导入事实的 organizer）
- **关联：** [ADR-020](./ADR-020-transcript-distillation.md)（读取对话记录 → 写入 memory 事实——同样的「读外部、写 Coffer」形态）、[ADR-026](./ADR-026-memory-via-mcp-not-native-projection.md)（Coffer 绝不写 agent 的原生记忆文件）、[ADR-013](./ADR-013-agent-native-shared-memory.md)（agent 原生共享 memory）、Spec 004（agent 注册表——只读工作区不变量）

## 背景

coding agent（Claude Code）在磁盘上保有自己的逐项目原生记忆——`<config_dir>/projects/<slug>/memory/*.md` 下的 markdown 笔记——这区别于 Spec 004 FR-013 已经呈现的人写指令文件（CLAUDE.md / AGENTS.md）。在 agent 原生 store 中积累了记忆的用户，没有办法把它带进 Coffer——而在 Coffer 中它会成为跨 agent 的单一事实来源（Spec 007）并跨机器同步（ADR-016）。这个 store 还是不可见的：用户无法从 Coffer 内部看到自己的 agent 为哪些项目写过记忆。

我们希望 (a) 只读地呈现这些 store，并 (b) 让用户把其中一个收编进 Coffer，同时避免：

- 写入 agent 自己的原生记忆 store（Coffer 不应拥有或破坏它——Spec 004 的只读工作区不变量，ADR-026 再次确认），或
- 引入新的顶层规范（扫描是 agent-registry 的工作区 facet；导入的输出是 Spec 007 memory 事实，由 Spec 007 既有的 organizer 整理）。

slug 到路径的映射是关键：Claude Code 通过替换分隔符把项目的绝对路径编码进目录 slug，这是**有损的**——含分隔符字符的路径段与真实边界无法区分，因此仅凭 slug 不总能重建真实路径。

## 决策

新增一个**原生记忆扫描**与一个**导入（收编）**动作，作为 agent-registry 工作区 facet（Spec 004 FR-040 / FR-041），复用 Spec 007 的 organizer 做「转换」。

1. **扫描（只读）。** `GET /api/v1/agents/{name}/native-memory` 在读取时为每个 `<config_dir>/projects/<slug>/memory` 目录派生一个 store：从 slug 得到的可读 `project` 标签、尽力解码的 `path`（有损 slug 无法重建时为 null）、真实的 `memory_dir`，以及排除 `MEMORY.md` 的 `.md` 文件 `item_count`。没有原生布局的 agent 类型（`codex`）与没有 `projects/` 目录的 agent 返回空列表。不存储、不写入、不发 audit 事件（遵循 FR-011 的只读列表规则）。

2. **导入 = 批量 remember → inbox → 后台 organize。** `POST /api/v1/agents/{name}/native-memory/import` 带 `{memory_dir}`，读取该 store 的事实文件（跳过 `MEMORY.md`），解析真实项目路径，并把每条事实写成项目作用域的 Coffer memory 事实，进入该项目 store 的 `knowledge/inbox/` 通道——如同一批 `remember`。对用户自己已有记忆的一次受信任批量导入可写到 32768 字符的领域上限（store 较小的默认值约束的是普通 agent `remember` 写入，而非这次导入）。随后把 Spec 007 的 organizer 作为**后台**任务调度并立即返回。

3. **复用 Spec 007 的 organizer 做转换。** 导入的 inbox 项由 Spec 007 既有的 organizer 整理进 Coffer 主题文档——无新转换逻辑。因为一次批量导入会播下数十个 inbox 项，整理它们是数十次顺序的内部 LLM 调用（数分钟），所以 organize MUST 作为后台任务运行；内联运行会挂起或超时请求，并在客户端断开时死掉。

结果上报 `imported`、`skipped`、`store`、`project_path` 与 `organized`。跨 agent 共享与跨机同步是自然后果：memory 事实已通过 MCP `recall` 网关共享（Spec 007）并经 git 同步（ADR-016）。

### 架构 —— 组合根边界，与 `distill` 一致

导入切片是 `agent`、`memory`、`organizer` 三个 kind 交汇的边界站点。`application.agent` 不得 import memory kind（import-linter Contract 5b），因此 memory 写入 / organize / store 名解析的管线只能经由在 `native_memory_import_wiring.py` 中连线的组合根 sink 适配器触达（镜像 `distill_wiring.py`）。连线必须在 `wire_organize` **之后**运行，使 organizer 可达。

### 不变量

- **绝不写 agent 自己的原生记忆 store。** Coffer 读取 `<config_dir>/projects/<slug>/memory`，但绝不写入它。Spec 004 的只读工作区不变量（与 ADR-026）完全保留。
- **slug 解码有损——经 transcript cwd 解析真实路径。** 仅当解码出的路径在磁盘上存在时才据其重建；否则从兄弟 transcript `.jsonl` 中记录的 `cwd` 恢复真实项目路径。两者都无法解析时，导入映射不到任何 Coffer store。
- **非 git 项目跳过。** 解析路径不在 git 工作树内的 store 无法映射到 Coffer 项目 store；导入返回 `imported=0`、`store=null`、`project_path=null`、`organized=false`——不污染任何 inbox，也不是错误。
- **无新 004 audit 事件。** 扫描只读（无 audit）。每条导入事实经 Spec 007 既有的 memory 写入事件审计；导入不新增任何 agent-registry audit 事件。
- **后台 organize、非阻塞导入。** organize 被调度而非 await；导入响应在内部 LLM 调用运行之前返回。

## 考虑过的备选方案

### 备选方案 A —— 把 Coffer 的事实写回 agent 的原生记忆 store

把已收编（及未来）的 Coffer memory 投影进 agent 自己的 `projects/<slug>/memory` 目录，使 coding agent 原生「看见」它。

**已否决。** 这违反 Spec 004 只读工作区不变量，以及 ADR-026 的决策——Coffer 经 MCP `recall` 网关而非原生投影触达 agent。它还需要拥有 agent 无文档的原生写入格式，并有损坏用户真实记忆的风险。正确的注入通道是已就位的 `recall`。

### 备选方案 B —— 在导入请求内同步 organize

在返回导入响应前把 inbox 排空进主题文档，使调用方看到一个已完全整理的 store。

**已否决。** 一次批量导入是数十个 inbox 项；整理它们是数十次顺序的内部 LLM 调用（数分钟）。让 HTTP 请求挂这么久会挂起或超时调用方，且客户端断开时 organize 会死掉。把它作为后台任务调度并上报 `organized=true`（已调度）使导入保持响应性；用户可按需显式重跑 `organize`（Spec 007）。

### 备选方案 C —— 为原生记忆引入新的顶层 spec / 资源 kind

把原生记忆 store 建模为一等 Coffer 资源 kind，带自己的 CRUD、UI 与契约。

**已否决。** 扫描是只读的 agent-registry 工作区 facet（与 MCP 条目、插件 facet 同形），导入的输出是 Spec 007 memory 事实。两者都不需要新 kind、迁移，或超出此处两条路由的契约面。新 kind 相较 `recall` 已呈现的事实并无额外用户价值。

## 后果

- agent 面新增两条 HTTP 路由：`GET /api/v1/agents/{name}/native-memory`（扫描）与 `POST /api/v1/agents/{name}/native-memory/import`（收编）。契约声明在 `specs/004-agent-registry/contracts/api.openapi.yaml`（`NativeMemoryStore`、`NativeMemoryListResponse`、`NativeMemoryImportRequest`、`NativeMemoryImportResult`）。
- 新增两条 CLI 子命令：`coffer agent native-memory <name>`（读取，`--json`）与 `coffer agent import-native-memory <name> <memory_dir>`（收编）——FR-009 REST+CLI 等价。
- agent 的 Memory tab 展示 Coffer 受管记忆链接，外加这张原生表格（只读，按 FR-038 提供打开 / 显示 / 复制路径），并带一个收编某个 store 的导入按钮。
- 不分配新 spec 编号，不新增 audit 事件。Spec 004 的 FR 与验收场景就地扩展（FR-040 / FR-041）；导入复用 Spec 007 的 organizer 与 memory 写入事件。
- slug 编码与 transcript `.jsonl` 格式无文档；路径解析适配器为防御性实现，当 Claude Code 改变其磁盘布局时需重新审视。
