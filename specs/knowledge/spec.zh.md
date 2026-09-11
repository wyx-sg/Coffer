# 功能规范：Knowledge Layer（知识层）

> English: [spec.md](./spec.md)

**Feature Branch**: `feature/kb-memory-redesign`
**Created**: 2026-05-22（当时名为 *Memory*）· **与 spec knowledge（Knowledge Base）合并**：2026-09-10
**Status**: Accepted —— 已交付
**目录名说明**：本规范位于 `specs/knowledge/`，这是**历史遗留**。目录名就是 spec id：所有入链以及 `scripts/audit_acceptance.py`（按目录名匹配验收标记）都依赖它，因此功能改名时刻意没有改目录。请把 `knowledge` 读作「Knowledge Layer 规范」。

**Input**: Coffer 只存一样东西 —— **知识（knowledge）** —— 并把它提供给用户运行的每一个 agent。知识有两个来路：agent **写入**（一条事实、一个决定、一项值得跨会话存活的偏好），或人 **摄取**（任意格式的文件，转换为 Markdown）。它以每条一个 Markdown 文件的形式存放在磁盘上，是**唯一真相源**；SQLite（`documents`、`chunks`、FTS5、sqlite-vec）只是可重建的派生索引（[Files as Truth](../../docs/decisions/files-as-truth-sqlite-retrieval.md)）。一个资源 kind `knowledge`，三种 scope（`global`、`project-<ULID>`、用户命名的集合），每个 scope **两条 lane** —— `notes/` 装谁写下的、`docs/` 装谁上传的 —— 一套检索引擎且其模式对外不可见（[Retrieval Mode Is Internal](../../docs/decisions/retrieval-mode-is-internal.md)），以及六个 `coffer__*` MCP 工具。Coffer 保留自己的规范化格式，绝不写入 agent 的原生记忆文件（[Memory via MCP](../../docs/decisions/memory-via-mcp-not-native-projection.md)）；知识只在 agent 经 MCP **主动索取**时才到达会话 —— 没有任何东西被推进去。

## 为什么它是一层（2026-09-10 的合并）

这份规范曾经是两份中的一份。spec knowledge 拥有 `knowledge_base` kind（上传文件 → Markdown → 搜索），spec knowledge 拥有 `memory` kind（agent 记住事实 → 召回）。它们被描述为**同一基底的两张面**，而这在代码里是字面为真的：`documents`、`chunks`、FTS5 索引与 sqlite-vec 索引从一开始就是共享的（006 FR-009），`infrastructure/knowledge/paths.py` 也早就同时拥有两套磁盘布局。分裂只存在于门面（facade）。

它没有挣回自己的成本：

- **知识库是个空壳。** 它创建于 2026-06-22，两个半月后仍然是零文档。`documents` 表里全部 78 行都是 `kind='memory'`。它的 embedding 配置从未被设置过。
- **memory 早就把写下的知识存成文档。** 整理流程存在的意义正是把零散笔记整理成主题文档。知识在 memory *内部*早已是一等公民。
- **工具面逼调用方猜。** agent 必须先判断「这是 memory 还是 knowledge？」才能在 `coffer__recall` 与 `coffer__search_knowledge` 之间做选择 —— 而这个区分对调用方毫无意义，基底本身也并不遵守它。
- **检索工具的错误率就是症状。** `coffer__grep_knowledge` 12 次调用失败 9 次（ripgrep 指向一个不存在的目录），`coffer__read_document` 3 次全败，`coffer__search_knowledge` 12 次失败 3 次 —— 而 `coffer__list_knowledge_bases` 4 次全成。搜索一个空知识库会失败，列举它不会。

于是两个 kind 变成一个 kind，十二个工具变成六个，两套 REST/CLI/UI 面各自合成一套。从 006 存活下来的，是真正关于*摄取文件*的一切：任意格式转换、chunking、源文件跟踪、重建索引。从 007 存活下来的，是关于*agent 写入*的一切：notes，以及整理它们的那一趟流程。

**既有数据被清空**（迁移 `0051`），理由值得直说而不是埋起来。`memory:global` 与 `knowledge_base:global` 同时存在，而 `resources` 以 `(kind, name)` 为键 —— 两者都转换必然撞键，任何自动改名都是在猜用户指的是哪一个。而所有 `documents` 行索引的都是 **journal lane**，它已随上一次改动（连同 transcript distillation）被移除；索引指向的文件不复存在。重新积累靠显式的 `coffer__write` 与文件摄取，而这正是「文件即真相」本就假定的：索引是派生物，永远不是系统记录。

## 两条 lane（2026-09-11 重新设计）

那次合并留下了一个 kind，却留下了七条存储 lane，详情页还把其中五条并列成同等份量的 tab。它们是存储 lane，不是人认得出的分类。有两个目录都叫 inbox。rules lane 的投递通道已在 2026-09-10 删除，此后没有任何东西读它。变更记录 tab 展示的是一趟整理的副产物，而页面根本没提供跑那趟整理的入口。

人真正会区分的只有两类材料：**谁写下的**和**谁上传的**。因此一个 scope 现在只有两条 lane —— `notes/` 与 `docs/` —— 外加两条为安全而非为阅读存在的隐藏 lane：`.history/`（整理覆盖前的旧版本）与 `.raw/`（上传的原件）。`rules`、`handoff`、`superseded` 与整理变更日志一并消失，`knowledge/inbox/` 到主题文档的梯度也一并消失：一条 note 就是一条 note，不管它是刚写下的还是已经被整理过。

取代 organizer 的是**定期整理**（FR-033–FR-035）：一趟对 `notes/` 的有界 agentic 流程，合并重复、把多条 note 重写成主题文档，动任何内容之前先归档旧版本，并且按定时器运行，而不是只在有人想起来去敲 CLI 时才跑。

## 用户场景与测试

### User Story 1 —— 一层知识，所有 agent 共享（优先级 P1）

开发者上午用 Claude Code、下午用 Codex 在同一个项目上工作。用 Claude Code 时 agent 学到「这个 repo 通过 `make release` 发版，绝不直接 `git push --tags`」，用 `coffer__write` 记下来。下午 Codex —— 另一个 agent —— 用 `coffer__search` 找到同一条事实，因为两个 agent 读写的是**同一个共享 scope**。没有任何副本漂移。

**为什么是这个优先级**：这是核心。各 agent 之间互相漂移的私有 silo 正是要解决的问题；没有单一真相源就没有这条 feature。

**独立可测**：从全新安装开始，在一个 git 项目里跑 MCP 客户端，调 `coffer__write` 写一条项目事实，再用第二个 MCP 客户端（不同 agent 身份）在同一项目里调 `coffer__search`，看到该事实被返回。确认它作为一个 Markdown 文件出现在项目 scope 的 `notes/` lane 下。

**代表性场景**：

- agent 记住一条项目事实
- agent 召回一条项目事实
- 检索跨 project 与 global 两个 scope
- 写入的条目存入 knowledge lane
- 内置知识工具出现在客户端工具列表
- embedding 未配置时向量检索回退

---

### User Story 2 —— 三种 scope：global、project 与命名集合（优先级 P1）

有些知识到处都适用（「偏好 tab 而非空格」）；有些只属于一个 repo（「这个服务的 API base path 是 `/api/v2`」）；还有些属于开发者刻意创建的集合（`design-notes`，装着一次设计评审的 PDF 与 ADR）。三者是同一种东西，有同样的两条 lane、同样的检索 —— 只有**名字**区分它们是哪一种。

`global` 与 `project-<ULID>` 在首次使用时**自动创建**，因为想写点东西的 agent 不该先申请许可。命名集合**不会**：它存在是因为有人决定它该存在，从一个拼错的名字里悄悄变出一个来，比报错更糟。

**为什么是这个优先级**：把个人偏好与项目事实混在一起会污染检索、并让 repo 细节跨项目泄漏；而把一份刻意整理的语料塞进「memory」里则让它无从可见。scope 这条轴是共享层可信的前提。

**独立可测**：在 git 项目里写一条 `scope=global` 和一条不带 scope 的条目。从另一个项目检索只返回 global 那条；从原项目检索两条都返回。显式创建命名集合 `design-notes` 并摄取一个文件；再去检索一个不存在的名字，观察到报错而不是新建出一个空 scope。

**代表性场景**：

- 在 global scope 写入
- agent 记住一条项目事实
- project scope 从 agent 的工作目录解析
- 检索跨 project 与 global 两个 scope
- 创建一个知识库
- 项目知识跨检出路径跟随仓库

---

### User Story 3 —— 用任意格式的文件构建一个 scope（优先级 P1）

开发者手上有设计笔记、ADR、内部 wiki、论文 PDF、一份表格和几个 HTML 页面。他们不管格式，全部丢进一个 scope。Coffer 把每个转换成干净的 Markdown 放进该 scope 的 `docs/` lane，把原件留在隐藏的 `.raw/` lane 作为出处，并索引结果 —— 让 agent 通过返回其自身 notes 的同一个 `coffer__search` 检索到它们。

**为什么是这个优先级**：摄取是这一层所存内容的一半。没有它，Coffer 只有 agent 碰巧打进去的知识。

**独立可测**：创建 scope `design-notes`，摄取一个 `.md`、一个 `.pdf`、一个 `.docx` 和一个 `.csv`；观察每个都成为 `~/.coffer/knowledge/design-notes/docs/` 下的 Markdown 文件、原件在 `.raw/` 下，并在 `documents` 中有一行 `lane='docs'`。

**代表性场景**：任意格式摄取转 markdown；列出知识库中的文档；按标题过滤文档；删除单个文档；删除知识库同时清理文件与索引；重新上传更新后的文件就地更新文档；重新上传完全相同的文件是 no-op。

---

### User Story 4 —— 一个检索面覆盖两个 lane（优先级 P1）

同一个 scope 在底层有几种查法：`grep`（对 Markdown 文件做精确/正则匹配，零索引）、`keyword`（SQLite FTS5 + BM25，trigram 分词器，所以 CJK 与标识符都能命中）、`vector`（sqlite-vec 配合已配置的 embedding provider）、`hybrid`（keyword + vector 的倒数排名融合）。这些是**内部引擎细节**（[Retrieval Mode Is Internal](../../docs/decisions/retrieval-mode-is-internal.md)）：外部调用方不选模式 —— 一次搜索自动解析该 scope 的默认策略（启用 vector 则 `hybrid`，否则 `keyword`）。未配置 embedding provider 时 vector/hybrid 在内部回退到 keyword —— 从不阻塞，也不逐次查询打标（降级只报一次，通过 `documents_degraded`）。

关键在于**检索横跨两个 lane**。对一个 scope 的搜索会同时返回 agent 写入的条目*和*人摄取的文档，一起排名。统一搜索正是合并两个 kind 的目的；按 lane 分开搜只会把分裂原样下沉一层。

**为什么是这个优先级**：检索就是产品。内部模式覆盖了从离线零配置到语义搜索的全谱，而外部面始终是「一次查询 → 一个答案」。

**独立可测**：在同时含一条写入条目与一个摄取文档的 scope 上跑一次 `coffer__search`，观察两个 lane 的命中。在没有 embedding 配置的情况下跑 grep。配置 embedding provider、给 scope 启用 `vector` 后再搜；移除配置再搜，结果仍返回且无报错。

**代表性场景**：关键词搜索返回排名段落；关键词搜索命中 CJK（中文）内容；grep 返回文件/行匹配；向量搜索返回排名段落；embedding 未配置时 vector 回退 keyword；hybrid 通过 RRF 融合 keyword 与 vector；主题文档以段落粒度被召回。

---

### User Story 5 —— agent 通过 MCP 网关既读又写（优先级 P1）

开发者的编码 agent 连上 Coffer 的 MCP 端点，拿到**六个**内置工具：`coffer__search`、`coffer__grep`、`coffer__read`、`coffer__list`、`coffer__write`、`coffer__delete`。六个都接受可选的 `scope`，默认取 cwd 所在项目的 scope，在项目之外回退到 `global`。`coffer__write` 从 `text` 归档一条 note，给了 `filename` 就存一份 Markdown 文档，给了 `id` 就就地重写两者之一 —— 调用方永远不需要知道东西住在哪个 lane。每次 agent 写入都以 agent 为 actor 记入审计（F01），并走与 REST 面相同的服务路径。

**为什么是这个优先级**：agent 侧检索让这一层在编码时有用；agent 侧写入让它成为活的存储而非静态库。六个读起来像动词的工具，正是消除「这是 memory 还是 knowledge？」这一猜测的手段。

**独立可测**：在一个有内容的 scope 上，MCP 客户端恰好看到这六个工具；带 `text` 调 `coffer__write` 创建出可搜索的 note，带 `filename` 调它创建出可搜索的文档，`coffer__read` 按 id 都能读回。

**代表性场景**：内置 KB 工具出现在客户端工具列表；内置知识工具出现在客户端工具列表；agent 搜索知识库；agent grep 知识库；agent 读取文档；agent 经 MCP 添加文档；agent 经 MCP 编辑文档；agent 经 MCP 删除文档。

---

### User Story 6 —— 用户维护积累下来的内容（优先级 P2）

开发者想看见并纠正积累下来的东西：在**只读**查看器里逐 lane 浏览一个 scope，在**自己的外部编辑器**里（或经 API/CLI）修正一条漂移的条目或一处转换瑕疵，手工添加一条，删掉错的那条。Coffer UI 从不在应用内编辑内容；每个文件及其所在文件夹提供「在外部编辑器中打开」与「在文件管理器中显示」，由本机 daemon 执行（[Daemon Proxies File Actions](../../docs/decisions/daemon-proxies-os-file-actions.md)）。任何带外修改都由读时惰性重建索引（FR-010）拾起。一旦文档被手工编辑过（`source_mode = edited`），从原件重新转换即被阻止，编辑永不被覆盖。

**为什么是这个优先级**：没有人工维护的知识层让人不安 —— agent 有时会记错，转换器有时会把表格搞乱。把编辑路由到用户自己的编辑器，让 Markdown 文件保持唯一真相源，也不用再维护第二个编辑面。

**独立可测**：在 agent 写过条目、文件被摄取之后打开 Knowledge 页（只读），确认内容可渲染但不能在应用内编辑。在 Coffer 之外改一个文件，观察下一次搜索返回修正后的版本。经 CLI/API 添加一条、删掉另一条，观察它从磁盘与搜索中消失。

**代表性场景**：用户添加一条事实；用户带外修正一条事实；用户删除一条事实；只读查看器提供打开/显示入口；编辑文档并重建索引；外部编辑经读时重建索引被拾起；编辑后禁止重新转换；修改 chunk 参数触发重建索引；修改 embedding 模型触发重新嵌入；check sources 检出变更/未变/缺失的原件；update from source 就地刷新变更文档；update from source 拒绝已编辑文档；auto_update_sources 在检查时刷新变更源。

---

### User Story 7 —— 查看、命名与重置 scope（优先级 P3）

开发者想知道每个 scope 积累了多少，想给来源文件夹未知的 scope 一个可读名字，也想在不删除 scope 的前提下清空它。

**为什么是这个优先级**：卫生问题；不阻塞主流程。

**独立可测**：查看每个 scope 的指标（条目数、文档数、chunk 数、磁盘字节）。给来源文件夹未知的 scope 重命名，确认所选名字出现在列表中并在刷新后仍在。清空一个 project scope；确认条目全部消失但 scope 仍在。

**代表性场景**：清空一个知识 scope；用户重命名一个 scope；KB 指标报告计数与磁盘占用；降级的嵌入暴露 documents_degraded 并在不重新 chunk 的前提下重试；测试一个 embedding 模型。

---

### User Story 8 —— 读完整个 scope 的两条 lane（优先级 P2）

开发者在 Coffer 里打开一个 scope，想看清它装了什么：agent 或自己写下的 **Notes**，以及别人摄取的**文档**。Knowledge 详情页恰好呈现这两个 tab。每个都是「树 + 内容」，**只读**，经统一文件预览渲染，并对底层文件提供「在外部编辑器中打开 / 在文件管理器中显示 / 复制路径」。树上方有一个过滤框，输入即按文件名收窄这棵树 —— **纯本地**：没有按钮，不发请求，这个页面上也没有服务端搜索（agent 走 `coffer__search`，命令行走 `coffer knowledge recall`）。

Notes 与文档分成两个 tab、各自计数，正是因为它们出处不同、维护动作也不同 —— 但这两个 tab 是*呈现*上的切分，不是存储或检索上的切分。`coffer__search` 依然横跨两者。

**为什么是这个优先级**：一个 scope 的两条 lane 装着这一层知道的全部，而这个页面是人检查积累了什么、并加以纠正的地方。它是 P2，因为它是覆盖在其他 story 已经填充的 lane 之上的只读投影；它增加可见性，从不新增写入路径。

**独立可测**：给一个 project scope 填入一条写入的 note 与一个摄取文档。打开详情页，确认两个 tab、均只读、均经统一文件预览渲染、均提供打开 / 显示 / 复制路径。在过滤框里输入，确认这棵树收窄且不发任何网络请求。确认 header 只有**上传**与**整理**两个按钮，设置 / 检查源文件 / 重建索引收在溢出菜单里。

**代表性场景**：reorg 流程合并重复主题文档；reorg 从不销毁内容 —— 被取代的主题仍可找回；未配置内部模型时 reorg 是 no-op；整理 worker 在开机与按间隔各跑一趟；主题文档以段落粒度被召回。

---

### Edge Cases

- **不存在的 scope 名**：`global` 与格式正确的 `project-<26 位 ULID>` 惰性创建。其他任何名字都是**命名集合**，**不**自动创建 —— 未知名字返回 404，因此拼写错误不会悄悄造出一个此后每次读都失败的空 scope。
- **向量不可用、embedding 未配置**：搜索在内部回退到 keyword 并返回结果；从不阻塞，也不设置逐次查询的标志。默认（`keyword` + `grep`）零配置且可离线。
- **不支持的格式**：没有转换器的文件以 `IngestRejected("unsupported_type")` 拒绝；不落任何持久化。
- **转换器库缺失**：某格式的转换引擎未安装时，该格式的摄取返回 `EngineUnavailable` 并指名缺失依赖；daemon 保持运行，其他格式仍可摄取。
- **转换结果为空**：转换后为空/仅空白的文件以 `IngestRejected("empty")` 拒绝。转换后为空的 **PDF** 以更具体的 `IngestRejected("scanned_pdf")` 拒绝（同为 415），使 UI 能给出「看起来是扫描件/纯图像 —— 请先 OCR」这样可操作的提示。
- **文件过大**：超过 `max_document_bytes`（默认 25 MB）的文件在 API 边界即被拒绝，不进入任何转换。
- **重新上传，字节完全相同**：幂等 no-op —— 返回既有文档，不重写、不重复审计。
- **重新上传，同名但内容变化**：**就地更新同一个文档**（复用 ULID，`docs/` 与 `.raw/` 覆盖且只保留最新原件，`source_mode` 重置为 `converted`）—— 但只有带 `replace=true` 才行；否则以 `duplicate` 拒绝，让覆盖始终是显式的。
- **编辑后重新转换**：对 `source_mode == edited` 的文档重新转换会被拒绝；带 `replace=true` 重新上传变更后的源会就地更新并把它重置为 `converted`。
- **直接改磁盘**：下一次读会按内容哈希惰性扫描差异并重建索引，因此带外编辑无需 watcher 也能被拾起。对未变内容重建索引是 no-op。
- **条目正文为空或过长**：在 API 边界拒绝（`max_entry_chars`，默认 8192，硬上限 32768）；不落任何持久化。
- **grep 与隐藏 lane**：`.raw/` 与 `.history/` 都以点号开头，ripgrep 会跳过它们。否则每个摄取文档都会产生两条 grep 命中 —— Markdown 与它转换自的原件 —— 而每条被整理过的 note 会在正文旁边再产生每个归档版本一条命中。
- **agent 从不索取**：什么也不会发生。没有任何东西被推进 agent 会话；一个不调 `coffer__search` / `coffer__grep` / `coffer__read` 的 agent 就是永远看不到这个 scope 里有什么。这是被接受的后果，不是 bug —— 见「投递 —— 已删除」。
- **被跟踪的源文件移动或删除**：`check-sources` 报告 `missing`，从不崩溃。`source_path` 是本机局部的，因此在另一台机器上得到 `missing` 是预期且良性的。
- **并发搜索**：对同一 scope 的多次搜索独立运行；没有按 scope 的锁拖慢读延迟。

## Acceptance Scenarios

每条场景至少对应一个打了 `@pytest.mark.acceptance(spec="knowledge", scenario="…")`（Python）或 `acceptance("knowledge", "…")`（TypeScript）标记的测试。部分标题沿用合并前两份规范的措辞 —— 「fact」「memory store」「knowledge base」—— 因为标题文本本身就是 `scripts/audit_acceptance.py` 匹配的标记键。请把它们读作历史标签；正文描述的是今天的行为。

### Scenario: project memory follows the repository across checkout paths

- **Given** 同一仓库（相同 `origin` remote）检出在不同路径 —— 例如两台用户名不同的已同步机器
- **When** 每个检出解析其项目知识 scope
- **Then** 两者解析到同一个 scope（相同项目 ULID）
- **And** 旧的路径派生 scope 在首次解析时被收编到可移植 id 之下，条目、根映射与标签保留

### Scenario: agent remembers a project fact

- **Given** 一个跑在 git 项目内的 MCP 客户端，
- **When** 它以 `text` 调 `coffer__write` 且不带 `scope`，
- **Then** 一个每条一文件的 Markdown（YAML frontmatter `title`/`description`/`metadata.actor`/`origin_session_id` + 正文）被写入项目 scope 的 `notes/` lane，该文件以 `lane='notes'` 索引进 `documents`，并记录一条审计。

### Scenario: agent recalls a project fact

- **Given** 一个含条目的 project scope，
- **When** MCP 客户端带查询调 `coffer__search`，
- **Then** 在惰性重建索引扫描拾起带外差异之后，返回带 id、正文、分数、来源与时间的排名命中。

### Scenario: recall spans project and global scope

- **Given** global 与 project 两个 scope 都有知识，
- **When** MCP 客户端不带 scope 调 `coffer__search`，
- **Then** 结果同时来自 project scope 与 global scope。

### Scenario: remembered items are stored in the knowledge lane

- **Given** 一个跑在 git 项目内的 MCP 客户端，
- **When** 它以 `text` 调 `coffer__write`，
- **Then** 该条目作为 Markdown 文件写入项目 scope 的 `notes/` lane（绝不在 scope 根目录），以 `notes` lane 索引进 `documents`，随后 `coffer__search` 能返回它。

### Scenario: remember at global scope

- **Given** 一个 MCP 客户端，
- **When** 它带 `scope=global` 调 `coffer__write`，
- **Then** 条目写入 `global` scope（键为 `project_id = WORKSPACE_GLOBAL_PROJECT_ID`），从任何项目检索都能返回它。

### Scenario: project scope resolves from the agent's working directory

- **Given** coffer-mcp-shim 在会话握手时上报其启动 cwd，
- **When** daemon 解析项目知识 scope，
- **Then** 它计算该 cwd 的 git-root，并解析（不存在则惰性创建）该项目的 `project-<ULID>` scope。

### Scenario: out-of-band fact-file edits are visible on recall

- **Given** 一个含条目的 project scope，
- **When** 某条目文件在磁盘上被带外编辑（frontmatter 保留），
- **Then** 下一次 `coffer__search` 返回编辑后的内容（读时惰性重建索引），且没有任何文件系统 watcher 在跑。

### Scenario: user adds a fact

- **Given** 一个知识 scope，
- **When** 用户经 Coffer UI 或 CLI 添加一条条目，
- **Then** 规范化 Markdown 以 `metadata.actor = "user"` 写入该 scope 的 `notes/` lane，该行以 `notes` lane 索引，并记录一条审计。

### Scenario: user corrects a fact out-of-band

- **Given** 存在一条条目，
- **When** 用户在应用内查看器之外修正其正文 —— 经 REST/CLI 写入面（`PATCH /api/v1/knowledge/{scope}/entries/{id}` / `coffer knowledge edit-entry`），或直接在外部编辑器里改规范化 Markdown，
- **Then** 规范化 Markdown 被重写，该行被重建索引（REST/CLI 路径立即生效；直接改文件则在下一次读时经惰性重建索引生效），搜索反映新正文。

### Scenario: user deletes a fact

- **Given** 存在一条条目，
- **When** 用户删除它，
- **Then** Markdown 文件与其索引行被移除，搜索不再返回它。

### Scenario: read-only viewer offers open/reveal affordances

- **Given** 在 Knowledge 页查看某一项，
- **When** 用户查看该项（及其所在文件夹），
- **Then** 内容只读渲染（不在应用内编辑内容），读响应暴露该项的绝对 `.md` 路径与其所在文件夹的绝对路径，UI 对文件与文件夹都提供「在外部编辑器中打开」+「在文件管理器中显示」，经 loopback daemon 执行（spec agent-registry FR-039）—— 没有复制路径兜底；打开哪个编辑器由全局首选编辑器偏好决定（见 ui-shell）。

### Scenario: clear a memory scope

- **Given** 一个含条目的知识 scope，
- **When** 用户清空它，
- **Then** `notes/` lane 下的每一项被移除、索引行被丢弃，但 scope 这个 Resource 被保留。

### Scenario: user renames a memory store

- **Given** 一个知识 scope（例如来源文件夹从未被记录、否则只会显示为 `project-<ULID>` 的那种），
- **When** 用户经 `PATCH /api/v1/knowledge/{scope}/label` 设置显示标签，
- **Then** 标签被 trim、回显，并在 scope 读取与列表中作为可读名字呈现；空白标签清除它（回退到 FR-017a 的派生）；给不存在的 scope 打标签是 404，而不是自动创建。

### Scenario: built-in memory tools appear in client tool list

- **Given** 一个 MCP 客户端连上 Coffer 网关，
- **When** 客户端列举工具，
- **Then** `coffer__search`、`coffer__grep`、`coffer__read`、`coffer__list`、`coffer__write`、`coffer__delete` 与其他内置及上游工具一同出现。

### Scenario: vector recall falls back when embedding is unconfigured

- **Given** 一个知识 scope，且全局未配置 embedding provider，
- **When** 引擎解析到向量策略但没有可用 embedder，
- **Then** 该调用改跑 keyword 搜索并返回结果、不报错；降级**不**以逐次查询的响应标志形式暴露。

### Scenario: a topic document recalls at passage granularity

- **Given** 一个已整理的知识 scope，其 `notes/` lane 持有一份含两个不同标题小节、各讲不同主题的主题文档，且已建索引，
- **When** 用只出现在第二小节的词去 `coffer__search`，
- **Then** 返回命中的正文是该小节的**段落** —— 而非整篇文档 —— 因此第一小节的特征措辞不出现在命中里，证明主题文档是**按段落**（感知标题与块结构）分块，而非一文件一块。

### Scenario: the reorg pass consolidates duplicate topic documents

- **Given** 一个知识 scope 的 `notes/` lane 有两条重叠的 note（同一主题，其一含额外细节），且已配置内部模型，
- **When** 整理流程运行 —— 来自后台 worker、详情页的**「整理」**按钮、`POST /api/v1/knowledge/{scope}/organize` 或 `coffer knowledge organize <scope>` —— 内部 agentic 循环读取两条 note、把合并内容写入其一并移除冗余的另一条，
- **Then** 单一 note 持有合并后的内容，冗余 note 不再出现在搜索中，随后的搜索返回合并内容，且这趟整理被记入 Coffer 的审计日志。

### Scenario: reorg never destroys content — a superseded topic stays recoverable

- **Given** 一个知识 scope 有一条持有内容 X 的 note（可能是人的编辑），
- **When** 整理流程覆盖该 note 或把它合并掉，
- **Then** 先前内容 X 先被复制进 `.history/`（因此**可恢复**，绝不硬删），该归档**不参与检索、也不参与 grep**（`.history/` 以点号开头），且这趟整理被记入 Coffer 的审计日志 —— 该循环是增量编辑，绝非从零重生成。

### Scenario: reorg is a no-op when no internal model is configured

- **Given** 一个有 notes 但未配置内部模型的知识 scope，
- **When** 触发整理流程，
- **Then** 返回 `status="no_model"`，不写、不合并、不归档任何 note，不抛错。

### Scenario: the tidy worker runs on boot and on an interval

- **Given** 已配置内部模型，且某 scope 的 `notes/` lane 有值得整理的材料，
- **When** daemon 启动并持续运行，
- **Then** 开机时跑一趟补齐整理，之后按配置的间隔继续跑，无需任何显式触发；失败的一趟只记日志，绝不打死循环、也绝不阻塞 daemon 关停；未配置内部模型时该 worker 空转而不报错。

### Scenario: the two-lane migration flattens the old lanes

- **Given** 一套仍是重新设计之前布局的安装 —— 条目在 `knowledge/inbox/` 与 `knowledge/*.md`，摄取文档在 `inbox/`，外加 `rules/`、`handoff/`、`superseded/`、`consolidation-log.md` 与 `knowledge/INDEX.md`，
- **When** 执行升级，
- **Then** 写入的条目被拍平进 `notes/`，`inbox/` 变成 `docs/`，`.raw/` 不动，rules / handoff / superseded 三条 lane 与两个日志文件被**直接删除**（按决定做破坏性迁移，不设缓冲区），并由一条 Alembic migration 把 `documents.lane` 由 `knowledge`/`inbox` 改写为 `notes`/`docs` —— 不留任何 load-time 兼容垫片。

### Scenario: create a knowledge base

- **Given** daemon 正在运行且不存在任何命名集合，
- **When** 用户以唯一名字与一份检索配置创建一个 scope，
- **Then** 该 scope 作为 `knowledge` 资源持久化，`~/.coffer/knowledge/<name>/` 及其 lane 被创建，列举 scope 时可见。命名集合是**显式**创建的 —— 不同于 `global` 与 `project-<ULID>`，它绝不会因一次读而自动创建。

### Scenario: ingest converts any format to markdown

- **Given** 存在一个知识 scope，
- **When** 用户上传一个非 Markdown 文件（如 `.pdf`、`.docx`、`.csv`、`.html`），
- **Then** Coffer 把它转换为 `docs/<doc-id>.md`（带 YAML frontmatter），把原件保留在 `.raw/<doc-id>.<ext>`，插入一行 `documents`（`kind="knowledge"`、`lane="docs"`、`source_mode="converted"`），并把它切块进 FTS5。

### Scenario: list documents in a knowledge base

- **Given** 已摄取若干文档，
- **When** 用户列举文档，
- **Then** 每个摄取文档一行，带稳定 doc id、标题、原始文件名与时间戳，分页返回 —— 且**只有**文档：该列举是按 lane 限定的，因此 agent 写入同一 scope 的条目不会混进来。

### Scenario: filter documents by title

- **Given** 一个含多个文档的 scope，
- **When** 用户带标题查询 `q` 列举文档，
- **Then** 只返回标题包含 `q`（不区分大小写）的文档，`total` 反映过滤后的数量，结果仍按 `limit`/`offset` 分页。

### Scenario: keyword search returns ranked passages

- **Given** 文档已建索引，
- **When** 用户搜索（不带模式；Coffer 使用该 scope 解析出的默认策略），
- **Then** 收到按 `bm25()` 排名的段落，各自带来源 doc id、标题、片段与分数 —— 来自**两个** lane，因为对一个 scope 的搜索同时覆盖写入的与摄取的内容。

### Scenario: keyword search matches CJK (Chinese) content

- **Given** 一个知识 scope 中有一份 Markdown 正文为中文（无词边界空格）的文档，
- **When** 用户用 CJK 查询做关键词搜索，
- **Then** 多字查询（如 `向量检索`）经 FTS5 trigram 索引命中，短于 3 字的查询（如 `向量`）经子串兜底命中 —— 都不会像旧的 `unicode61` 分词器那样返回空。

### Scenario: grep returns file/line matches

- **Given** 文档在磁盘上，
- **When** 用户用某个模式 grep 该 scope，
- **Then** Coffer 对 scope 目录跑 ripgrep（受 max-matches 与超时约束），返回 `{path, line_number, line}` 命中，不涉及索引。隐藏的 `.raw/` 与 `.history/` lane 被跳过，因此一个摄取文档只产生其 Markdown 的一条命中而非两条，一条被整理过的 note 也只产生其当前版本的一条命中，而非每个归档版本一条。

### Scenario: vector search returns ranked passages

- **Given** 全局已配置 embedding provider，且该 scope 列出了向量检索模式、其文档已嵌入，
- **When** 引擎跑向量搜索（启用向量的 scope 的解析默认），
- **Then** Coffer 嵌入查询、跑 sqlite-vec KNN，返回带相似度分数的 top-k 段落。

### Scenario: vector falls back to keyword when embedding unconfigured

- **Given** 全局未配置 embedding provider，
- **When** 引擎解析到向量策略但没有可用 embedder，
- **Then** Coffer 改跑 keyword 搜索并返回结果、不报错；降级不以逐次查询标志暴露（它经 `documents_degraded` 报告）。

### Scenario: hybrid search fuses keyword and vector via RRF

- **Given** 一个启用向量且文档已嵌入的 scope，
- **When** 引擎为该启用向量的 scope 融合 keyword+vector（其解析默认），
- **Then** Coffer 同时跑 keyword 与 vector 搜索并以倒数排名融合（`K = 60`，按 `(document_id, position)` 去重），使同时被两个列表排名的段落胜过单列表命中，并返回融合后的 top-k。

### Scenario: edit a document and reindex

- **Given** 存在一份已转换的文档，
- **When** 用户经编辑 API 替换其 Markdown 正文，
- **Then** `source_mode` 变为 `edited`，单一重建索引例程删除旧的 chunks/FTS5/vec 行并重新切块（启用向量则重新嵌入），随后的搜索反映该编辑。

### Scenario: external edit picked up by reindex-on-read

- **Given** 一份 Markdown 文件在用户外部编辑器里被带外编辑（没有 API 调用）的文档，
- **When** 用户下一次读取或搜索该文档，
- **Then** 读时惰性重建索引扫描检出漂移的 `content_sha256`，经单一幂等例程重建索引，读/搜索反映该编辑 —— 且没有任何文件系统 watcher 在跑。

### Scenario: re-conversion blocked once edited

- **Given** 一份 `source_mode == edited` 的文档，
- **When** 用户请求从原件重新转换，
- **Then** Coffer 以明确错误拒绝；重新上传一个新的源文件会把 `source_mode` 重置为 `converted`。

### Scenario: changing chunk params re-indexes

- **Given** 一个已建索引的 scope，
- **When** 用户修改 `chunk_size` 或 `chunk_overlap`，
- **Then** Coffer 重新切块并重建该 scope 的索引（启用向量则重新嵌入）—— chunk 参数可变，不被锁定。

### Scenario: changing embedding model re-embeds

- **Given** 一个列出了向量检索模式的 scope，且全局已设置 embedding 模型，
- **When** 用户更换 embedding 模型，
- **Then** Coffer 把语料重新嵌入 sqlite-vec —— embedding 模型可变，不被锁定。该模型位于全局配置而非 scope 上，因此一次更改会让每个要求向量的 scope 重新嵌入；UI 会在应用前确认。

### Scenario: delete a single document

- **Given** 一个 scope 有文档，
- **When** 用户按 id 删除其中一个，
- **Then** `docs/<doc-id>.md` 与 `.raw/<doc-id>.<ext>` 文件被移除，其 chunks/FTS5/vec 行被删除，`documents` 行被移除，记录审计 `KB_DOCUMENT_DELETED`，搜索不再返回它。

### Scenario: delete a knowledge base cleans up files and index

- **Given** 一个 scope 有内容与索引，
- **When** 用户经通用资源删除（`DELETE /api/v1/resources/knowledge/{name}`）删除该 scope，
- **Then** 它的所有 `documents`/`chunks`/FTS5/vec 行被移除，`~/.coffer/knowledge/<name>/` 被移除，Resource 行被删除。刻意**没有** `DELETE /api/v1/knowledge/{scope}`：scope 生命周期与 kind 无关，属于 Resource 框架。

### Scenario: built-in KB tools appear in client tool list

- **Given** 一个 MCP 客户端连上 Coffer 网关，
- **When** 它列举工具，
- **Then** 六个知识工具都在 —— `coffer__search`、`coffer__grep`、`coffer__read`、`coffer__list`、`coffer__write`、`coffer__delete` —— 不再有「文档 vs 记忆」两套家族，且每一个都接受可选的 `scope`。

### Scenario: agent searches a knowledge base

- **Given** 一个已建索引的 scope，
- **When** 客户端调 `coffer__search(query, scope?, top_k?)`，
- **Then** Coffer 返回为 LLM 消费而结构化的排名段落（段落 + 来源 id + 分数），横跨两个 lane。

### Scenario: agent greps a knowledge base

- **Given** 一个磁盘上有文件的 scope，
- **When** 客户端调 `coffer__grep(pattern, scope?)`，
- **Then** Coffer 返回文件/行匹配。

### Scenario: agent reads a document

- **Given** scope 中存在某一项，
- **When** 客户端调 `coffer__read(id, scope?)`，
- **Then** Coffer 返回该项的 Markdown 正文与 frontmatter —— 自动解析条目 id 或文档 id —— 或在 id 未知时给出明确错误。

### Scenario: agent adds a document via MCP

- **Given** 存在一个知识 scope，
- **When** 客户端以 Markdown 内容调 `coffer__write(text, filename, scope?)`，
- **Then** Coffer 像处理人工上传一样摄取它（`docs` lane 下一个新的 ULID id 文档，写入 `docs/` 与 `.raw/`，建索引），该文档可被搜索。

### Scenario: agent edits a document via MCP

- **Given** 存在一份已转换的文档，
- **When** 客户端调 `coffer__write(text, id, scope?)` 指向该文档，
- **Then** 正文被替换，`source_mode` 变为 `edited`，该 scope 被重建索引。

### Scenario: agent deletes a document via MCP

- **Given** scope 中存在一份文档，
- **When** 客户端调 `coffer__delete(id, scope?)`，
- **Then** 该文档的文件与索引行被移除，以 agent 为 actor 记录审计 `KB_DOCUMENT_DELETED`，搜索不再返回它。

### Scenario: re-upload of an updated file updates the document in place

- **Given** 一份从 `report.md` 摄取的文档，
- **When** 用户带 `replace=true` 重新上传变更后的 `report.md`，
- **Then** **同一个** doc id 被就地更新（`.raw/` 与 Markdown 被覆盖、只保留最新原件、`source_mode` 重置为 `converted`），且不产生第二个文档。

### Scenario: re-upload of an identical file is a no-op

- **Given** 一份从 `report.md` 摄取的文档，
- **When** 用户重新上传字节完全相同的 `report.md`，
- **Then** 这是幂等 no-op：返回既有文档，且不产生第二个文档。

### Scenario: KB metrics report counts and disk usage

- **Given** 一个 scope 持有条目与文档，
- **When** 用户打开其详情视图（UI 或 `coffer knowledge describe`），
- **Then** 他们看到按 lane 限定的 `entry_count` 与 `document_count`、chunk 数、已建索引的检索模式、向量嵌入待重试的文档数（`documents_degraded`），以及 `~/.coffer/knowledge/<scope>/` 的磁盘字节数。两个计数分开是因为两个 lane 来路不同；chunk 数横跨两者，因为检索横跨两者。

### Scenario: degraded embed surfaces documents_degraded and retries without re-chunking

- **Given** 一个启用向量的 scope，其 embedding provider 在文档摄取时不可用，
- **When** 该文档仅以关键词建索引，之后用户在 provider 仍宕机时读取该 scope（列举 / 搜索 / 指标），再在其恢复后读一次，
- **Then** 该文档带着真实的 `content_sha256` 与一个持久化的 `embed_pending` 标志，降级读时 `documents_degraded` 报 `1`，下一次协调**只**重试嵌入（不重新切块 / 不重写 FTS —— chunk 行不变），成功后清除 `embed_pending`，`documents_degraded` 回到 `0`。

### Scenario: check sources detects changed, unchanged, and missing originals

- **Given** 若干从外部文件摄取的文档（其绝对 `source_path` 记录在 metadata 中），
- **When** 用户在其中一个原件被磁盘上编辑、一个未动、一个被删除之后运行 `check-sources`，
- **Then** 报告分别把它们归类为 `changed`、`unchanged`、`missing`（通过对每个外部文件重新哈希并与存储的 `source_sha256` 比对），且检测本身不重建索引、不记审计。

### Scenario: update from source refreshes a changed document in place

- **Given** 一份已转换文档，其外部 `source_path` 原件在磁盘上已变更，
- **When** 用户对该文档运行 `update-source`，
- **Then** Coffer 从被跟踪文件就地重新摄取它（同一 ULID id，`source_mode` 保持 `converted`），新内容可搜索、旧内容消失。

### Scenario: update from source refuses an edited document

- **Given** 一份 `source_mode == edited` 的文档，
- **When** 用户对它运行 `update-source`，
- **Then** Coffer 以「禁止重新转换」错误拒绝（手工编辑绝不被覆盖），且 `check-sources` 把该文档报告为 `edited` 而非覆盖它。

### Scenario: auto_update_sources refreshes changed sources on check

- **Given** 一个启用 `auto_update_sources` 的 scope，且某文档的外部原件已变更，
- **When** 用户运行 `check-sources`，
- **Then** 变更文档被就地自动刷新（报告 `updated`），而手工编辑过的变更文档会被跳过（报告 `edited`）。

### Scenario: test an embedding model

- **Given** 一个 embedding provider、模型 id，以及（必要时）凭据引用，
- **When** 用户测试该 embedding 模型，
- **Then** Coffer 请求一次嵌入并报告成功及返回的向量维度，或给出人类可读的失败信息，且不持久化任何东西。

> **推迟到后续测试工作**（随 e2e 基础设施落地；`make verify-acceptance` 不对其设卡）：按 scope 的 Knowledge 列表视图、只读查看器的「在外部编辑器中打开 / 显示」端到端验证、带运行中 daemon 的 `coffer knowledge …` 端到端、以及经 HTTP 路由的按 scope 指标。

## Requirements

### Functional Requirements

> **编号说明。** `FR-001`–`FR-059` 保留它们还叫 *Memory* 规范时的编号 —— 代码注释、其他规范与 ADR 都在引用它们，重新编号带来的破坏大于整洁。从 spec knowledge（Knowledge Base）折叠进来的需求另起一段编号 `FR-060`–`FR-075`，每条标注它来自 006 的哪个编号；`FR-076` 是两 lane 迁移。序列中的空缺是被更早改动退役的需求 —— transcript distillation 与 `journal` lane，以及 2026-09-11 的两 lane 重新设计：它退役了 handoff lane（`FR-023`–`FR-026`）、排空 inbox 的 organizer 及其目录与变更日志（`FR-027`–`FR-031`）、流程性 `rules` lane（`FR-036`）与跨 scope 的 AI 合并（`FR-056`–`FR-059`）。存活的需求从不重新编号，所以空缺就留着。

**存储与 scope**

- **FR-001**：系统必须把每条写入项存为一个 Markdown 文件（YAML frontmatter `title`/`description`/`metadata.actor`/`origin_session_id` + 正文），位于该 scope 的 **`notes/` lane** 下 —— 一条扁平 lane，无论该文件是刚写下的还是此后被整理流程（FR-033）重写过。这些 Markdown 文件是**唯一真相源**；SQLite 是可重建的索引。检索不读取任何派生索引文件，也不生成任何目录文件。
- **FR-002**：系统必须支持**一个资源 kind `knowledge`**，含**三种 scope**，仅由资源名区分：`global`、`project-<ULID>`，以及其他任意名字（**命名集合**）。`global` 与 `project-<ULID>` 必须在首次使用时自动创建；命名集合必须**不**自动创建 —— 未知名字返回 404，使拼写错误无法变出一个空 scope。scope 种类是从名字*派生*的（`domain/knowledge/scope.scope_kind_of`），从不存储，因此两者永不矛盾。
- **FR-002a**：系统必须把每个 scope 存在唯一的根 `~/.coffer/knowledge/<scope>/` 下，**恰好两条可见 lane，别无其他**：`notes/`（agent 或用户写下的一切）与 `docs/`（摄取文档的归一化 Markdown）。另有两条为安全而非为阅读存在的隐藏 lane：`.history/`（整理流程覆盖前的旧版本，FR-034）与 `.raw/`（摄取原件）。两者都必须以点号开头：grep 跑遍整个 scope 目录而 ripgrep 会跳过隐藏项，因此摄取原件永远不会作为第二条命中与它转换出的 Markdown 一同出现，归档旧版本也永远不会与正文一同出现。必须不存在 `knowledge/`、`inbox/`、`rules/`、`handoff/` 或 `superseded/` lane，scope 根也不得有目录文件或日志文件。路径构造必须只存在于一个模块（`infrastructure/knowledge/paths.py`），且每个成为路径片段的名字都必须过穿越防护。
- **FR-003**：`coffer__write`（以及用户添加）必须把该项**直接落进 scope 的 `notes/` lane**，写入时不调 LLM，也不经过任何中转 inbox。该项立即可检索；此后不存在向另一条主题文档 lane 的晋升。整理流程（FR-033）之后可以就地合并与重写 notes，且必须从不阻塞写入或读取。
- **FR-004**：系统必须在会话握手时从 agent 上报的启动 cwd 解析 per-project scope：daemon 计算 git-root，并解析（不存在则惰性创建）该项目 ULID 对应的 scope。
- **FR-004a**（spec vault-export-import 修订）：项目 ULID 必须**跨机器可移植** —— 仓库有 `origin` remote 时由其归一化 URL 派生（同一仓库的 ssh/https/scp 形式归一化结果一致），没有 remote 时回退到绝对 git-root 路径哈希。因此同一仓库在每台已同步机器上都解析到同一个 scope，无论检出路径为何。以旧的路径派生 id 创建的 scope 在首次解析时被**一次性**收编到可移植 id：文件迁移到新 id 的目录，资源以新名字重新注册，根映射与显示标签一并带过去。

**条目生命周期**

- **FR-005**：agent 与用户必须能够直接写入条目（写入时不调 LLM）。条目正文至少 1 字符、至多 `max_entry_chars`（每 scope 默认 8192，硬上限 32768）；空或超长在 API 边界拒绝且不落任何持久化。每 scope 的默认值约束普通 agent 写入；对用户自有笔记的可信批量导入可放宽到上限，使长笔记永不被静默截断。
- **FR-006**：用户与 agent 必须能够按 scope 列举条目、按 id 获取一条、编辑其正文、删除一条，以及清空一个 scope。清空保留 scope 这个 Resource。Coffer UI 只读渲染条目内容、不在应用内编辑；人通过 REST/CLI 写入面或自己的外部编辑器维护。
- **FR-007**：每条 note 携带 `metadata.actor`（`agent` | `user`），由写入方设置。**没有自由形式的 `type` 字段** —— `Lane` 是唯一分类轴（FR-048），由该项如何到达（写入还是摄取）决定，绝不由写入方提供。

**检索**

- **FR-008**：检索必须在整个 scope 上使用同一套引擎：`grep`（对 scope 文件跑 ripgrep；对 FTS5 无法分词的内容如 CJK 至关重要）、`keyword`（FTS5 BM25 + trigram 分词器，默认）、`vector`（sqlite-vec 配合全局 embedding provider）、`hybrid`（keyword + vector 的倒数排名融合）。这些模式是**内部细节**（[Retrieval Mode Is Internal](../../docs/decisions/retrieval-mode-is-internal.md)）—— 任何外部面都不接受 `mode`；引擎自动解析该 scope 的默认策略（scope 列出 vector 则 `hybrid`，否则 `keyword`）。当解析出的策略需要向量但没有可用 embedder 时，检索必须在内部回退到 `keyword` —— 从不阻塞，也从不暴露逐次查询的 `fallback` 标志。
- **FR-008a**：检索必须横跨一个 scope 的**两个 lane**。一次搜索同时返回 agent 写入的条目与人摄取的文档，一起排名。按 lane 限定的读（文档列举、`entry_count`/`document_count`）只服务于呈现与维护；它们不得分割检索。统一搜索正是两个 kind 合并的理由，把它在下一层重新拆开会让这次改动落空。
- **FR-009**：三个检索工具 —— `coffer__search`、`coffer__grep` 与 `coffer__read` —— 默认必须横跨当前项目 scope 与 `global`（显式 `scope` 收窄到其一，且一律按字面理解）。`search` 与 `grep` 同时查询两个 store；`read` 先在项目 scope 解析，解析不到再回落 `global`。三者必须一致：`search` 从 global store 返回的 id 必须能直接读回，`grep` 拿到的 pattern 也不能仅仅因为 agent 的 cwd 在某个项目里就漏掉 global。跨 scope 结果以倒数排名融合合并 —— 各 scope 的分数不可比，因此每条命中保留自己的分数，只有合并后的顺序来自融合。结果携带 id、正文、分数、来源与时间。`top_k` 默认 5，调用方可指定 1–20。
- **FR-010**：这一层必须使用**读时惰性重建索引**：读或搜索先按内容哈希扫描差异（新增/变更/删除的文件）并在服务前协调索引，因此带外编辑 —— 人在自己编辑器里的修正，或任何直接的磁盘编辑 —— 无需文件系统 watcher 也立即可见。正是它让 UI 得以保持只读查看器（FR-017），而维护发生在用户自己的编辑器里。

**经 MCP 的 agent 集成**

- **FR-015**：Coffer 的 MCP 网关必须在保留前缀 `coffer__` 下暴露**六个**内置知识工具：
  - `coffer__search(query, scope?, top_k?)` —— 横跨两条 lane 的排名片段
  - `coffer__grep(pattern, scope?, max_matches?)` —— 字面/正则的文件+行匹配
  - `coffer__read(id, scope?)` —— 完整读取一项，note 或文档自动解析
  - `coffer__list(scope?, all?, limit?)` —— 一个 scope 的内容，或全部 scope 的目录
  - `coffer__write(text, title?, description?, filename?, id?, scope?)` —— 从 `text` 归档一条 note，给 `filename` 则存文档，给 `id` 则就地重写两者之一
  - `coffer__delete(id, scope?)` —— 删除一条 note 或一份文档
  六个都必须接受可选的 `scope`，默认取 cwd 所在项目的 scope，在项目之外回退到 `global`；三个检索工具在隐式 scope 下还会额外横跨 `global`（FR-009）。没有任何工具接受检索 `mode`。调用方必须永远不需要先把一样东西归类为「memory」还是「knowledge」才能选工具。必须不存在 `coffer__set_handoff` 与 `coffer__resume`：它们随 handoff lane 一同退役。
- **FR-016**：内置工具调用必须共用既有的调用日志面（一行 `mcp_invocations`：工具名 + 谁/何时/耗时/结果，不含参数或返回内容）。写工具在文档层面的效果另以 agent 为 actor 记入 F01 审计。

**整理 —— 定期整理流程**

- **FR-032**：协调器必须用共享 Markdown 分块器（`infrastructure/knowledge/chunking.chunk_markdown` —— 按标题小节切分、保持围栏代码/表格原子、把结构块打包到固定窗口）把文件正文切成**段落粒度、感知结构的块**，使一份多小节的 note 浮现**最相关的段落**而非整篇正文。短的单段落项仍切成一块：这改变的是**粒度**，绝不改变检索包含或排除*什么*。
- **FR-033**：系统必须为一个 scope 的 `notes/` lane 提供**定期整理**：一趟由 Coffer 的内部 LLM 连接（标记为 internal-default 的连接；Model providers，spec provider-switching）驱动的**有界 agentic 流程**，在这一条扁平 lane 内**合并重复的 note、把多条 note 重写成连贯的主题文档**，就地完成。它的固定工具面是对 `notes/` 的 list / read / write / delete，且**绝不面向 agent**；langchain/langgraph 代码必须限制在 `infrastructure.llm` 内（importlinter Contract 9a），`application/knowledge` 只经注入的端口触达它。未配置内部连接时该流程必须是干净的 no-op（`status="no_model"`）；没有 note 的 scope 同样是 no-op（`status="empty"`）。之后该流程协调索引。每一趟都必须记入 Coffer**已有的审计日志** —— 不存在按 scope 的变更日志文件。
- **FR-034**：整理流程必须**可找回**。任何覆盖或合并之前，它必须先把受影响 note 的旧版本复制进 **`.history/`**，使无人值守的重写始终可以捞回来。`.history/` 以点号开头，因此**不参与检索、也不参与 grep**；它是可找回的历史，不是内容。note 写入仍必须**原子**。这是数据不丢的保证，也是全部的安全网：这趟流程无人值守地运行，没有复核环节，落地之前也没有 diff 可供批准（见 Assumptions）。
- **FR-035**：整理必须由**后台 worker** 运行，而不只是显式触发：daemon 启动后不久跑一趟补齐，之后按间隔继续跑，形态照抄现有的保留期 worker。它必须非阻塞且不致命 —— 失败的一趟只记日志、绝不打死循环，待执行的一趟也必须**绝不**阻塞或弄坏 daemon 关停（不丢东西：未整理的 notes 本就在检索范围内，且该流程幂等）。未配置内部连接时是干净的 no-op。同一趟流程还必须可**手动**触发：详情页的**「整理」**按钮，以及 `coffer knowledge organize <scope>`（及其 REST 等价物）。除此之外不引入其他 REST/CLI 面。

**Lane 分类法**

- **FR-048**：自由形式的 `type` 字段**已退役** —— `Lane`（`notes` / `docs`）是**唯一分类轴**，且恰好只有这两个取值。系统必须不在 note 实体、文件 frontmatter（`metadata.type`）、`documents.metadata` JSON、`coffer__write` 工具 schema，或 REST/CLI 写入面中携带 `type` 字段。一项的 lane 由**它如何到达**（写入还是摄取）决定，绝不由写入方提供。

**投递 —— 已删除**

这一层有**进**的一半，没有**出**的一半。知识照样进得来 —— agent 写入、整理流程
合并、文件参与同步 —— 但没有任何东西再自动把它送回一个会话。

2026-09-10 之前是有的。**FR-049** 通过 Coffer 安装的 `coffer-hook` SessionStart
hook 投递一份会话开始包（`GET /api/v1/agents/{name}/session-context?cwd=` →
`additionalContext`，绝不写原生文件）；**FR-050** 往那个包里加两条 Coffer
内置种子规则；**FR-052** 提供可选的 per-agent `disable_native_memory`
整洁性开关；**FR-055** 追加一份仅标题的项目知识索引，让 agent 一开始就知道项目里
有什么。四条全部**删除**，连同那个二进制、hook 安装/卸载面、`session-context`
路由、规则包组装器与摘要渲染器。

**代价，直说。** 这删掉的是跨 agent 记忆中**投递**的那一半。agent 现在必须自己调
`coffer__search`；除非它主动问，否则**不会**有人告诉它这个项目知道些什么，用户
积累的内容就躺在磁盘上，直到有东西去找它们。搜索自觉 —— 恰恰是
环境式注入当初为了不依赖它才存在的东西 —— 现在变成了承重结构。

**为什么接受。** 那个 hook 是上线了，但它从未真正安装到这位用户的机器上，因此这条
注入路径在实践中一次都没跑过。被删掉的是一项纸面能力，没有任何会话真正用过它；而
保留它意味着要为它继续养着第二个冻结二进制、两种 agent 格式的 hooks 文件写入器、
一个 agent 维度的 HTTP 路由，以及一个受预算约束的规则包组装器。重新引入环境式投递
是将来的一个主动决定，不是遗漏。

**各类面（Surfaces）**

- **FR-017**：用户必须能够通过（a）**`/api/v1/knowledge`** 下的 REST API（scope 作为路径片段，`entries` / `documents` 为子资源）与（b）**`coffer knowledge`** CLI 组（取代原先的 `coffer memory` 与 `coffer kb`）完成完整的知识 CRUD。该组必须不携带 `rules`、`handoff`、`consolidation-log`、`merge-scan` 或 `merge` 子命令 —— 那些 lane 与那趟流程都已不存在；`organize` 保留，作为整理流程（FR-035）的手动触发入口。用户写入设置 `metadata.actor = "user"`、写出规范化 Markdown、重建索引并审计。Web UI **只读**呈现内容；人在自己的外部编辑器里维护（由读时惰性重建索引拾起，FR-010）或经 REST/CLI 维护。只读查看器必须以舒适的阅读**最大宽度**（居中）渲染内容，详情页列表必须是单一**可滚动**列表、无 UI 内分页器（UI 以最大 `limit` 取一页；API 仍按 `limit`/`offset` 分页）。这些面上的 scope 名按 FR-002 校验：格式正确的 `global` 或 `project-<26 位 ULID>` 惰性创建；其他名字必须已存在，否则请求返回 404。
- **FR-017a**：各类面必须以从 `project_root` **派生的人类可读身份**呈现 per-project scope —— 根目录 basename 作为主标签、绝对根路径作为次要细节 —— 而不是只给不透明的 `project-<ULID>` 名字。根未知时回退到 scope 名；`global` 与命名集合本就可读。这是**显示**层面的关注点，底层名字仍是 `project-<ULID>`。
- **FR-017c**：用户必须能给任意 scope 设置**显示标签**，优先于 FR-017a 的派生。设置空白标签即清除。标签是显示元数据：不改变 scope 名或 `project_id`，经 `PATCH /api/v1/knowledge/{scope}/label` 设置。标签存放在本机局部的 `knowledge_scope_labels` 表中（迁移 0051 从 `memory_store_labels` 改名，其键列 `store_name` → `scope_name`）。
- **FR-017d**：`PATCH /api/v1/knowledge/{scope}` 必须把提交的字段**合并**进该 scope 现有配置（`exclude_unset`），而非替换。只发送 `chunk_size` 的调用方不该静默地重置 `retrieval_modes`。（这推翻了 spec knowledge 早先「后端是替换而非深合并」的立场 —— 合并后的实现并不那样做。）
- **FR-017e**：**不得**存在 `DELETE /api/v1/knowledge/{scope}`。删除 scope 走与 kind 无关的 Resource 框架（`DELETE /api/v1/resources/knowledge/{name}`），由它级联删除文档、chunk、索引行与磁盘目录。scope 生命周期是 Resource 的关注点；knowledge 路由只拥有知识特有的部分。
- **FR-021**：只读查看器必须对文件及其所在文件夹都提供（a）**在外部编辑器中打开**与（b）**在文件管理器中显示**，经 loopback daemon 的文件系统动作端点执行（spec agent-registry FR-039）—— daemon 就在用户自己的机器上（[Daemon Proxies File Actions](../../docs/decisions/daemon-proxies-os-file-actions.md)）。没有复制路径兜底。打开哪个编辑器由全局首选编辑器偏好决定（ui-shell）。
- **FR-022**：读响应必须暴露磁盘真相：条目与文档的读端点必须包含各自文件的绝对 `.md` 路径与所在文件夹的绝对路径，scope 读端点必须包含该 scope 的绝对磁盘目录。
- **FR-053**：Knowledge 详情页必须把一个 scope 呈现为**两个 tab** —— **Documents** 与 **Notes** —— 别无其他。每个都是树 + 内容、**只读**、经**统一文件预览**渲染（不用手写 `<pre>`），并对底层文件提供**在外部编辑器中打开 / 在文件管理器中显示 / 复制路径**。Documents/Notes 的划分是呈现层面的（FR-008a）：检索仍横跨两者。树上方必须提供**一个文件名过滤框**，输入即收窄这棵树 —— **纯本地**：没有按钮、不发服务端请求，这个页面上也没有服务端搜索（agent 走 `coffer__search`，命令行走 `coffer knowledge recall`）。页面 header 必须保留标题、重命名铅笔与项目路径，并以**上传**与**整理**（FR-035）作为**仅有的两个按钮**；设置、检查源文件与重建索引必须收进溢出菜单。header 必须不再携带原先那排徽标（分块数、字节数、Grep、关键词，以及树标题已经给出的 note 数与文档数）；**降级文档的警告保留，且必须只在真的出现时显示**。每条 lane 顶上的说明文案、以及任何与树标题重复的计数都必须不出现。
- **FR-053b**：Knowledge **列表页**必须不携带「作用域」列 —— 名称列已经显示 `global`、项目的绝对路径或集合名，这个徽标只是把同一行已经说过的话再说一遍。条目列改名为 **Notes**。必须不存在 AI 合并入口。**新增集合对话框必须不询问向量检索**：新集合创建时向量即为启用，一个 scope 带哪种索引是实现细节，而不是创建时该拿去问用户的问题。
- **FR-053a**：Web UI 必须把这一层路由在 **`/knowledge`** 与 **`/knowledge/:scope`**，且必须以重定向保持合并前的 URL 可用：`/memory` 与 `/knowledge-bases` → `/knowledge`；`/memory/:name` 与 `/knowledge-bases/:name` → 对应的 `/knowledge/:scope`。书签早于这次合并，弄坏它们是无谓的代价。
- **FR-054**：系统暴露的 lane 读端点只有**详情页需要的那两个** —— 两个 tab 各自背后的列举与读取（即 FR-017 的 `entries` 与 `documents` 子资源）。它们**只读**、**按 scope 名寻址**（而非 cwd），且对空 scope 必须返回 **HTTP 200 加空列表**，绝不是 404。`GET /api/v1/knowledge/{scope}/handoff`、`…/rules` 与 `…/consolidation-log` 必须不存在。

**摄取与转换** *（从 spec knowledge 折叠而来）*

- **FR-060** *(原 006 FR-004/FR-005)*：用户与 agent 必须能够添加任意受支持格式的文件；系统必须检测格式、经可插拔的 `MarkdownConverter` 端口转成 Markdown、清洗输出、加上 YAML frontmatter、写入 `docs/` 与 `.raw/`，并建索引。转换必须经限制在 `infrastructure/` 内的按格式转换器注册表分发：Markdown/文本/源码文件原样通过，`csv` 有专用转换器，其余一切（pdf / docx / pptx / xlsx / xls / html / epub / …）走默认的 MarkItDown 引擎（`markitdown[docx,pdf,pptx,xls,xlsx]`）。MarkItDown 没有转换器的格式（旧式二进制 `.doc`/`.ppt`、`.rtf`、`.odt`）以 `unsupported_type` 拒绝，且不对外宣称支持。为某格式换更高保真的引擎是在注册表里加一个转换器，而非改动基底。
- **FR-061** *(原 006 FR-006)*：系统必须拒绝超过 `max_document_bytes`（默认 25 MB，可按 scope 配置）的文件、不支持类型的文件，以及转换后 Markdown 为空的文件 —— 转换后为空的 PDF 特别以 `scanned_pdf` 拒绝，使 UI 能给出可操作的提示。
- **FR-062** *(原 006 FR-007)*：每个摄取文档必须由首次摄取时铸造的**稳定 ULID** 标识（不是内容哈希）。系统必须计算原件的 `source_sha256`（作为出处保存在 `metadata` 中），并在 scope 内按 `original_filename` 把重新上传匹配到既有文档：**字节完全相同**的重新上传是幂等 no-op；**内容变化**的同名重新上传仅在 `replace=true` 时**就地更新同一文档**（复用 id），否则以 `duplicate` 拒绝；**新文件名**是新文档。同一文件摄取到两个 scope 会得到两个独立文档 —— 文档不跨 scope 去重。
- **FR-063** *(原 006 FR-010a)*：文档列举必须支持可选的**不区分大小写标题过滤 `q`**，在分页**之前**于服务端应用；`total` 反映过滤后的数量。
- **FR-064** *(原 006 FR-011/FR-011b)*：关键词索引必须使用 FTS5 **trigram** 分词器，使 CJK 与子串查询能命中 —— `unicode61` 不切分 CJK 文本，因此像 `向量检索` 这样的查询会返回空；没有任何 ≥ 3 字符 token 的查询回退到有界的子串（LIKE）扫描而非返回空。grep 响应携带 `truncated` 标志，在存在超过 `max_matches` 的匹配、或服务端超时截断扫描时为真（超时的 grep 返回零命中且 `truncated=true`，并杀掉 `rg` 进程）。`hybrid` 必须同时跑 keyword 与 vector 搜索并以**倒数排名融合**合并：每个段落的融合分为 `Σ 1/(K + rank)`，`K = 60`、`rank` 为其在该列表中的 0 起始位置；段落按 chunk 身份 `(document_id, position)` 去重，因此同时出现在两个列表的段落累加两份贡献并胜过单列表命中。
- **FR-065** *(原 006 FR-014)*：chunk 参数必须可按 scope 修改；修改会重新切块并重建索引。embedding 模型在全局层面可修改；修改会让每个列出向量模式的 scope 重新嵌入。这些字段没有不可变锁。
- **FR-066** *(原 006 FR-015/FR-016)*：每个摄取文档必须携带 `source_mode`：`converted`（Markdown 由原件派生，可重新转换）或 `edited`（禁止重新转换）。所有写入路径 —— 重新上传、编辑 API、agent `coffer__write`、外部编辑、重建索引扫描 —— 必须汇入**同一个幂等重建索引例程**，在磁盘 `content_sha256` 漂移时于读取路径上惰性触发：未变则 no-op；已变则删除旧的 chunks/FTS5/vec 行、重新切块、（启用向量时）重新嵌入并更新 `documents` 行。文档由人与 agent 共管：双方都可添加、编辑与删除。只有**删除**会审计（`kb_document_deleted`）—— 摄取与更新的结果都落在磁盘上，重跑这个例程什么都不会变，因此文件本身就是记录。
- **FR-067** *(原 006 FR-021)*：**基于路径**的摄取（CLI，以及 Web UI 的原生文件选择器）必须把外部原件的**绝对路径**记入文档自由形式的 `metadata` 的 `source_path` —— 无需 schema 迁移，它搭在既有 JSON 上。字节上传与 agent 的 `coffer__write` 必须**不**设置或推断 `source_path`（不可信面绝不能填入任意服务端路径）。`source_path` 是本机局部的。
- **FR-068** *(原 006 FR-022)*：`check-sources` 必须对每个被路径跟踪的文档重新做 sha256 —— 分块流式读取，使多 GB 原件永不整体读进内存 —— 并与存储的 `source_sha256` 比对，归类为 `unchanged`、`changed` 或 `missing`。检测**仅按需**（没有文件系统 watcher）；纯检测不改动、不审计。
- **FR-069** *(原 006 FR-023)*：`update-source` 必须从文档的 `source_path` 就地重新摄取 —— 复用 `replace=true` 的重新摄取路径，因此稳定 ULID 得以保留，该 scope 被重新切块与重建索引。`source_mode == edited` 的文档必须被拒绝，使手工编辑永不被覆盖；源文件消失或未被跟踪则经 `IngestRejected` 报告。
- **FR-070** *(原 006 FR-024)*：按 scope 的 `auto_update_sources` 开关（默认 **false**）决定 `check-sources` 行为：为 false 时检测只归类；为 true 时每个 `source_mode != edited` 的 `changed` 文档被就地自动刷新（报告 `updated`），而手工编辑过的 `changed` 文档被跳过（报告 `edited`）。切换该开关必须不触发重新切块或重新嵌入 —— 它不是触发重建索引的字段。
- **FR-071** *(原 006 FR-025)*：当嵌入因 embedding provider 不可用（`EngineUnavailable`）而降级时，文档必须仅以关键词建索引，其重试状态必须记录在专用的持久化 `embed_pending` 标志上 —— 与 `content_sha256` 解耦，后者必须始终是真实的正文哈希。scope 必须在指标中以 `documents_degraded` 暴露此类文档的数量，且该计数由持久化标志计算，因此它反映**任何**一次读取中观察到的降级。下一次协调对正文未变的待重试文档必须**只**重试嵌入 —— 在内存中重新切块、只 upsert 向量，成功后清除 `embed_pending`。

**合并后的模型本身** *（2026-09-10 合并带来的新增）*

- **FR-072**：一个资源 kind `knowledge` 必须在每一个面上取代原先的 `memory` 与 `knowledge_base`：Resource 框架、REST、CLI、Web UI 以及 MCP 工具列表。任何面都不得重新引入「这是哪个 kind？」的问题。
- **FR-073**：`documents` 表必须携带一个存储的 **lane 判别列** `documents.lane`，恰好两个取值 —— **`notes`** 表示写入方归档的项，**`docs`** 表示摄取的文档 —— 并在 `(kind, resource_name, lane)` 上建索引。它必须**存储而非从路径派生**：以 scope 目录为锚会把知识层的 lane 布局推进服务于所有 kind 的、与 kind 无关的仓储里。`entry_count` 与 `document_count` 必须按 lane 限定；检索必须不限定（FR-008a）。lane 是内部存储关注点，**不**出现在线上协议里：调用方用的端点本身已经隐含了它，把它放进文档负载只会引诱客户端去按它过滤。
- **FR-074**：按 scope 的配置（`KnowledgeConfig`）必须持有 `retrieval_modes`、`default_mode`、`max_entry_chars`、`chunk_size`、`chunk_overlap`、`max_document_bytes` 与 `auto_update_sources`，且必须**完全不含 embedding 字段**、也**不含 `merged_identities`**（该字段只为已退役的跨 scope 合并别名而存在）。原先两份配置都有 embedding 字段，而到合并之时**两者都已无人读取**：embedding 经全局配置解析，一个 scope 想要向量搜索只需列出该检索模式。死字段直接丢弃而非搬过来。启用 `vector` 时必须同时启用 `hybrid` 并使其成为默认，除非调用方显式选了别的。
- **FR-075**：迁移 `0051` 必须把两个 kind 合并为 `knowledge`、**清空**派生索引而不是转换它，并重命名两张本机局部的旁表（`memory_store_project_roots` → `knowledge_scope_project_roots`，`memory_store_labels` → `knowledge_scope_labels`，键列 `store_name` → `scope_name`）。迁移 `0052` 必须新增 `documents.lane` 及其索引，并按条目 lane 特有的 `knowledge/inbox/` 嵌套回填（匹配裸的 `knowledge/` 片段是错的 —— 存储根本身就包含它）。清空而非转换是必需而不只是省事：`memory:global` 与 `knowledge_base:global` 同时存在而 `resources` 以 `(kind, name)` 为键，两者都转换必然撞键、任何自动改名都是在猜；而所有 `documents` 行索引的都是上一次修订移除的 journal lane，索引指向的文件不复存在。两个迁移都必须做好防护，使缺少其中任何一项的数据库仍能升级。

- **FR-076**：迁向两条 lane 必须做迁移，且**按明确决定做破坏性迁移 —— 不设缓冲区**。磁盘上，逐 scope：`knowledge/inbox/*.md` 与 `knowledge/*.md` 拍平进 `notes/`；`inbox/` 变成 `docs/`；`.raw/` 不变；`rules/`、`handoff/`、`superseded/`、`consolidation-log.md` 与 `knowledge/INDEX.md` **直接删除** —— 不搬进任何 `.retired/` 暂存区，因为那些 lane 要么已经没有读者（rules），要么装的是副产物而非内容（日志与目录）。数据库里，必须由**一条 Alembic migration** 把 `documents.lane` 由 `knowledge`/`inbox` 改写为 `notes`/`docs`。数据必须在库里改干净，兼容分支必须在**同一次改动**里删掉：**不得有任何 load-time 垫片在这次迁移后存活**，也不得有任何面继续接受或产出旧的 lane 名。该 migration 必须做好保护，使缺少其中任一项的数据库仍能升级。

**基底隔离与迁移**

- **FR-018**：检索/索引引擎（FTS5、sqlite-vec、embedding provider、转换器）必须限制在 infrastructure。domain 与 application 层必须不直接 import 索引/引擎类型；交互经共享检索端口。mem0、chroma 与 LlamaIndex 必须在任何地方都不被 import。
- **FR-019**：预发布版本遗留的磁盘引擎目录（chroma/LlamaIndex）就地废弃 —— 无人读取 —— 而不是删除。lane 化之前遗留在 scope 根的每条一文件同样就地废弃：读时惰性重建索引会协调 `notes/` lane，因此陈旧索引行会在下一次读时被协调掉。

### Key Entities

- **Knowledge Scope**（kind 为 `knowledge` 的资源）：`global`、`project-<ULID>` 或一个命名集合之一 —— 种类由名字派生。配置 = `retrieval_modes`、`default_mode`、`max_entry_chars`、`chunk_size`、`chunk_overlap`、`max_document_bytes`、`auto_update_sources`。没有 embedding 字段。
- **Document**（一个 Markdown 文件 = 一行 `documents`，`kind="knowledge"`）：id（稳定 ULID）、scope 资源名、`lane`（`notes` | `docs`）、磁盘路径、标题、描述、`content_sha256`（始终是真实正文哈希）、`embed_pending`（索引派生的重试标志，非文件真相）、`source_mode`、`project_id`、按写入方的 `metadata`（摄取：`original_filename`、`original_format`、`source_sha256`、`converted_at`、`conversion_engine`、可选的 `source_path`；条目：`actor`、`origin_session_id`）、时间戳。
- **Chunk**（一行 `chunks`）：文档内的位置。块文本只存在 FTS5 索引里一份，不复制进基表；它始终可从 Markdown 文件重建。
- **Passage**（检索结果，不持久化）：段落文本、来源 id、标题、分数、位置。
- **Grep hit**（检索结果，不持久化）：路径、行号、行内容。

## Success Criteria

### Measurable Outcomes

- **SC-001**：一个 agent 经 `coffer__write` 写入的条目，能在同一项目、同一会话内被另一个 agent 经 `coffer__search` 找到，且没有任何 per-agent 副本漂移。
- **SC-002**：对同时含一条写入条目与一个摄取文档的 scope 做一次 `coffer__search`，返回两者的命中 —— 无需 lane 参数、无需第二次调用。
- **SC-003**：一个 scope 含 200 项时，典型关键词查询的搜索延迟在开发者笔记本上 ≤ 300 ms；50 文档（≤ 50 MB）的 scope 上，REST 面的关键词搜索 ≤ 200 ms、grep ≤ 500 ms。
- **SC-004**：默认检索零配置可离线工作（keyword + grep）；向量是可选加入的，未配置时降级为 keyword —— 从不报错。
- **SC-005**：`coffer knowledge reindex <scope>` 能纯粹从 Markdown 文件重建全部 SQLite 索引状态（删掉行、重建、搜索返回相同结果）。
- **SC-006**：每条 Acceptance Scenario 至少被一个标记 `acceptance(spec="knowledge", scenario="…")` 的测试覆盖；`make verify-acceptance` 报告零未覆盖场景、零孤立标记。
- **SC-007**：基底隔离由 importlinter 强制：`coffer.application.*` 与 `coffer.domain.*` 下没有模块 import 索引引擎、`markitdown`、`sqlite_vec` 或 embedding provider SDK，且 `mem0`/`chroma`/`llama_index` 在任何地方都不被 import。
- **SC-008**：删除一个 scope 会移除其 100% 的磁盘占用与 100% 的 SQLite 行。
- **SC-009**：MCP 客户端恰好看到六个知识工具，且没有一个要求调用方在选择之前先把一项归类为「memory」或「knowledge」。
- **SC-010**：`make verify` 在本地与 CI 均通过。

## Assumptions

- 用户在自己的机器上运行 Coffer；知识数据留在本地。为可选的向量检索调用已配置的云端 embedding provider 是允许的（local-first ≠ 不发远程 API 调用）。
- 规范化格式是位于 `~/.coffer/knowledge/<scope>/` 下的每项一个 Markdown 文件（YAML frontmatter + 正文）；不存在供检索读取的派生索引文件。
- coffer-mcp-shim 在受支持的 agent 上于会话握手时把启动 cwd 传给 daemon。
- keyword + grep 零配置且可离线；向量检索会触达已配置的 embedding provider，它**可以**是第三方 API。
- 受支持平台（macOS arm64、Linux）上有 `ripgrep`；sqlite-vec 能作为 SQLite 扩展加载。
- 单用户并发量很小。
- **已接受的风险：** 整理流程无人值守、按定时器运行，由 LLM 重写用户与其 agent 写下的文字。`.history/`（FR-034）就是全部的安全网；没有复核环节，落地之前也没有 diff 可供批准。

## Notes for reviewers

- **这份规范是 006 与 007 的合并。** `specs/006-knowledge-base/` 在其存活内容落到这里后即被删除。它的验收场景标题被原样搬过来，使既有测试标记继续匹配；只有 `spec=` 参数从 `"006-knowledge-base"` 改成 `"knowledge"`。
- **目录名是历史遗留。** `specs/knowledge/` 是 `scripts/audit_acceptance.py` 所依赖、且所有入链所使用的 spec id。改名会同时弄坏两者且毫无收益。
- **检索模式保持内部**（[Retrieval Mode Is Internal](../../docs/decisions/retrieval-mode-is-internal.md)）。这里的任何内容都不重开该议题。
- **「文档共管」与「逐项目 KB scope + 软删除」两项决策已删除**，被本规范吸收：共管就是这一个 knowledge kind 的工作方式，逐项目 scope 如今就是 scope 模型本身。文档的可恢复软删除仍未构建 —— 删除是带 F01 审计痕迹的硬删除；`.history/`（FR-034）只覆盖整理流程自己的重写。
- **embedding 默认值**：向量可选加入；零配置默认是 `keyword` + `grep`（离线、语言无关）。双语语料推荐本地 `bge-m3` 或云端 provider。
- **推迟**：检索上的重排 / HyDE / 多查询 / LLM 综述；文档的可恢复软删除；应用内 Markdown 编辑器（查看器保持只读 + 外部编辑器入口）；默认开启的图片 OCR；默认开启的文件系统 watcher。
