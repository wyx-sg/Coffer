# 修订 2026-07-10 — 同项目记忆库的 AI 辅助合并

> English: [amendment-2026-07-10-ai-store-merge.md](./amendment-2026-07-10-ai-store-merge.md)

状态：**已接受**（随本修订的 PR 一并实现）
修订对象：[spec 007 — Memory](./spec.md) · 不占用新 spec 编号（与转录蒸馏扩展一致）
新增：`spec.md` 的 **FR-056 – FR-059**、四个验收场景、两个 REST 端点、两个 CLI 子命令、一个记忆库列表 UI 操作。
范围轴不变：lane 模型、文件即事实（ADR-012/013）、可携带项目身份（FR-004a）完全保持原样。本修订只增加一条**用户显式触发、由内部引擎判断**的合并路径，处理确定性合并器无法证明等同的库。

## 动机

多机同步（spec 010）与可携带身份之前的时代，会让记忆库列表里出现多个实为**同一个**项目的 `project-<ULID>` 库：

1. **没有 `origin` remote** 的 checkout 以路径哈希取得 id——同一个仓库在每台机器（每个路径）上各得一个 id。
2. 另一台机器在**可携带身份（FR-004a）之前**铸造的库经同步过来，带着旧 id；本机则以可携带 id 持有同一项目。resolve 时的收养（adoption）只在旧库的 root 本机可解析时才能治愈——同步过来的库的 root 通常不可解析。
3. **remote URL 变更**（fork 改名、迁移托管方）的仓库会铸出第二个身份。

确定性合并器（启动扫描 + resolve 时收养）只会折叠 root **重新解析到同一规范 id** 的库——它无从得知两个*不同的*身份意味着同一个项目。「是不是同一个项目？」靠标签、路径与内容做判断——这正是 Coffer 内部引擎（FR-033 模式）的用武之地。用户确认后，由既有的增量合并机制完成事实的归并。

## 范围之外

- **不做自动 / 后台合并**——扫描与合并都是显式的用户操作（`POST` 端点 / CLI / UI 按钮），与 FR-033 的 reorg 一致。
- **不持久化被拒绝的提议**——被忽略的一对库下次扫描会再次出现（YAGNI，痛了再说）。
- **不做跨机编排**——合并在一台机器上执行；结果经正常同步区传播（被裁撤库的资源墓碑、幸存库的 lane 文件与 config）。
- **不合并全局库**——仅限项目库。
- **不新增 DB schema**——身份别名寄存在幸存库的 `config_json`（`MemoryStoreConfig.merged_identities`）里，无需迁移。

## 变更 A — 合并扫描（FR-056）

`POST /api/v1/memory_stores/merge_scan`（及 `coffer memory merge-scan`）检查项目库两两组合，返回**合并提议**。

- **每库证据**（服务端收集，除配置的内部引擎外不发往任何地方）：库名、显示标签（FR-017c）、记录的 `project_root`、root 本机可读时的**规范化 origin remote**（`normalize_remote_url`，FR-004a）、事实数量、有界采样的事实标题与主题 slug。
- **确定性层优先**：两库的本机可读 root 规范化到**同一非空 remote URL** 时，直接以 `confidence="certain"`、`judged_by="remote"` 提议——不动用 LLM。
- **引擎层**：其余组合逐对送内部引擎（FR-033 的 internal-default 连接）做**一次单发补全**——严格 JSON 裁决 `{same_project, confidence, reason}`；响应格式不合法则跳过该对（organizer 的跳过语义——绝不崩溃、绝不瞎猜）。
- **干净降级**：未配置内部引擎时响应为 `engine="no_model"`，只携带确定性层的提议。
- **有界**：引擎层每次扫描最多裁决 50 对（触顶时响应置 `truncated=true`）；证据采样有上限，大库不会撑爆上下文窗口。
- **建议方向**：每条提议给出建议的 `target`（幸存库）——root 本机可解析者优先，其次事实数多者，再次名字字典序小者（确定性）。

## 变更 B — 合并执行（FR-057）

`POST /api/v1/memory_stores/merge` 传 `{source, target}`（及 `coffer memory merge <source> <target>`），用**既有的增量合并机制**（`merge_store_dir`——启动合并 / 收养同款原语）归并两个项目库：

- journal 文件按时间戳去重逐条内容合并；派生文件跳过；其余同名冲突**两份都保留**（加后缀）——记忆只增不失。
- source 的显示标签在 target 无标签时移交；`project_root` 映射同理。
- target 强制 reconcile 使 recall 反映合并后的事实；source 库裁撤（资源删除级联文档 / 索引 / 目录）；记录一条 `memory_stores_merged` 审计（只含库名与计数）。
- 校验：`source` 与 `target` 必须是**互异、存在的项目库**——全局库永不可合并；违规返回 4xx 且无副作用。
- 合并与 resolve 时收养走同一把锁串行。事实写入**不持有**这把锁,因此合并在裁撤 source 前**再扫一遍 source**(文件合并按内容幂等,补扫只会带上真正新增的文件)——合并期间 remember 进来的内容会被带走;裁撤之后的写入会大声失败,而不是落进注定被删的目录。

## 变更 C — 防复活身份别名（FR-058）

把 `project-X` 合入 `project-Y` 后,身份 `X` 的**后续 resolve** 也必须落到 `Y`——否则铸出 `X` 的那个 checkout 下一次 `remember` 会悄悄重新供给一个空的重复库,下次扫描这对又回来了。

- 幸存库 config 新增 **`merged_identities`**（项目 ULID 列表,系统管理,默认空）。合并时追加 source 的 ULID **以及** source 自己的 `merged_identities`（可传递,链式合并保留全部别名）。
- `ScopeResolver._resolve_project` **仅在未命中时**查询别名：算出的身份没有对应库时,才找 `merged_identities` 含该身份的库改道过去（热路径——库存在——不受影响）。
- 别名住在资源的 `config_json` 里,随资源**同步**（spec 010）：改道在每台机器上都成立,被裁撤库的删除按正常资源墓碑传播。
- **每个身份只有一个在世持有者**:新持有者记录别名时,会从其它所有库的 `merged_identities` 里剥除这些身份,改道永不歧义。
- **启动合并器同样尊重别名**:被合并掉的规范身份改道到其别名持有者,而不是被重新供给——否则幸存库记录的 root 若重新解析到被合并的身份,下次启动会把它「治愈」成一个空重复库,等于反转合并。启动/收养合并同样把被裁撤库的别名(连同被裁撤身份本身)记到规范库上。

## 变更 D — 合并后整理（FR-059）

「合并事实」不止是搬文件：两库重叠的主题文档应当归并。合并端点接受 `organize`（默认 `true`）：合并成功后,若配置了内部引擎,就对 target 库运行既有的 **FR-033 reorg pass**,其结果以 `reorg_status` 写进合并响应（`"reorganized"`、`"no_model"`、`"empty"`、`organize=false` 时为 `"skipped"`,或 `"error: …"`）。整理失败绝不使合并本身失败——先保文件,再谈润色。

## 合同 / API 变更

- `POST /api/v1/memory_stores/merge_scan` → 同步 JSON：`{engine, truncated, proposals: [{source, target, confidence, judged_by, reason, source_evidence, target_evidence}]}`。
- `POST /api/v1/memory_stores/merge` 请求体 `{source, target, organize?}` → `{target, merged_files, label_moved, root_moved, aliases, reorg_status}`。
- `MemoryStoreConfig` 新增 `merged_identities: string[]`（默认 `[]`）。
- 更新 `contracts/api.openapi.yaml` 与合同测试。

## 前端

- 记忆库列表新增 **「查找重复库（AI）」** 工具栏操作 → 运行扫描,在对话框中展示提议（库对、置信度、判定来源、理由）,每条提议带**交换方向**与**合并**按钮；合并后失效 store-list 查询。`engine="no_model"` 时渲染确定性提议,并提示配置内部引擎。

## CLI

- `coffer memory merge-scan [--json]` — 打印提议。
- `coffer memory merge <source> <target> [--no-organize] [--json]` — 执行合并。

## 测试计划

单元：裁决 prompt 构建 / 解析（去 fence、格式不合法 → 跳过）、候选配对与确定性层、方向启发式、别名传递逻辑、`MemoryStoreConfig.merged_identities` 往返。集成：合并端点对真实库端到端（文件增量搬移、journal 去重、标签 / root 移交、source 裁撤、审计落盘）、resolve 别名改道（被合并身份的 checkout 下 `remember` 落进幸存库）、桩引擎端口下的扫描（确定性 + 引擎两层、no_model 降级）、CLI 子命令。合同：OpenAPI 漂移。四个新场景挂验收标记。
