# 功能规范：Memory（跨 agent 共享记忆）

> English: [spec.md](./spec.md)

**Feature Branch**: `feature/kb-memory-redesign`
**Created**: 2026-05-22
**Status**: Accepted (redesign — in development)
**Input**: Coffer memory feature 的重设计 —— 与 knowledge base（spec 006）共用同一套统一底座（unified substrate）的 **memory 面**。memory 不再是「写入时调 LLM 的 mem0 向量库」；它变成 **跨 agent 的单一真相源**（没有各 agent 间互相漂移的副本）。规范化存储 = 每条记忆一个 markdown 文件，放在每个作用域的 `knowledge/` lane 下（新记住的条目落在 `knowledge/inbox/`），位于 `~/.coffer/memory/`，带两层作用域（global + per-project），并 **不再生成任何派生索引文件**（此前的 `MEMORY.md` 投影已移除 —— 检索里没人读它）。agent **只通过 Coffer 的 MCP 网关读写记忆**（`coffer__recall`/`remember`/`list_memory`）；编辑与删除是用户面（REST/CLI/外部编辑器），不是 MCP 工具。Coffer 保留自己的规范化格式，不触碰各 agent 的原生记忆文件（原生投影已移除 —— 见 ADR-026）。用户在 Coffer UI 里做完整 CRUD。检索复用与 knowledge base 相同的引擎（grep / keyword FTS5+BM25 / vector sqlite-vec）。完整设计依据见 [ADR-012](../../docs/decisions/ADR-012-files-as-truth-sqlite-retrieval.md)。

## 用户场景与测试

### User Story 1 —— 一份记忆，所有 agent 共享（优先级 P1）

开发者上午用 Claude Code、下午用 Codex 在同一个项目上工作。用 Claude Code 时 agent 学到「这个 repo 通过 `make release` 发版，绝不直接 `git push --tags`」，并通过 Coffer 的 `coffer__remember` 工具记下来。下午 Codex —— 另一个 agent —— 召回了同一条事实，因为两个 agent 读写的是 **同一个共享 store**。没有任何副本漂移。

**为什么是这个优先级**：这是本次重设计的核心。各 agent 之间互相漂移的私有 silo 正是要解决的问题；没有单一真相源就没有这条 feature。

**独立可测**：从全新安装开始，在一个 git 项目里跑 MCP 客户端，调 `coffer__remember` 写一条项目事实，再用第二个 MCP 客户端（不同 agent 身份）在同一项目里调 `coffer__recall`，看到该事实被召回。确认该事实作为一个每条记忆的 markdown 文件出现在项目 store 的 `knowledge/inbox/` lane 下。

**代表性场景**：

- agent 记住一条项目事实
- agent 召回一条项目事实
- recall 跨 project 与 global 两个作用域
- 记住的条目存入 knowledge lane
- 内置记忆工具出现在客户端工具列表
- embedding 未配置时 vector recall 回退

---

### User Story 2 —— 全局与每项目记忆（优先级 P1）

有些事实是关于开发者本人、到处都成立的（「偏好 tabs 而非 spaces」）；有些只关乎某个 repo（「这个服务的 API base path 是 `/api/v2`」）。开发者希望全局事实在每个项目都可用、项目事实只限本项目，而 `recall` 默认两者都返回。

**为什么是这个优先级**：把个人偏好和项目专属事实混在一起会污染 recall，还会把 repo 细节泄露到别的项目。两层作用域是这个共享 store 可信的前提。

**独立可测**：用 `scope=global` 记一条、用 `scope=project` 记一条。从另一个项目 recall 只返回全局那条；在原项目 recall 两条都返回。

**代表性场景**：

- 在 global 作用域 remember
- agent 记住一条项目事实
- project 作用域由 agent 的工作目录解析得到
- recall 跨 project 与 global 两个作用域

---

### User Story 4 —— 用户在 Coffer 里维护记忆（优先级 P2）

开发者要看见并纠正 agent 记下的东西：在一个 **只读** 视图里按作用域浏览事实，然后 **在自己的外部编辑器里**（或经 API/CLI）改一条漂移的、手动加一条、删掉一条错的。Coffer UI 从不在应用内编辑事实内容；相反，每条事实及其所在文件夹都提供「在外部编辑器中打开」「在文件管理器中显示」（Web 上经 daemon,桌面上为原生），任何带外的纠正都会被既有的 lazy reindex-on-read 拾取（FR-010）。

**为什么是这个优先级**：没有人工维护的记忆让人不放心；agent 偶尔会记错。能维护，这条 feature 才足够安全到可以一直开着 —— 而把编辑路由到用户自己的编辑器，使 markdown 文件保持唯一真相源，无需再维护第二个编辑界面。

**独立可测**：agent 写了若干事实后，打开记忆视图（只读），确认事实内容能渲染但在应用内不可编辑。在外部编辑器里（或用 `coffer memory edit`/PATCH）打开一条事实、在 Coffer 之外纠正其文本，观察下一次 `recall` 返回纠正后的版本（lazy reindex-on-read）。经 CLI/API 加一条事实（actor=user），再删另一条，观察它从磁盘和 recall 中消失。

**代表性场景**：

- 用户添加一条事实
- 用户带外纠正一条事实
- 用户删除一条事实
- 只读视图提供打开/显示的能力

---

### User Story 6 —— 将 agent 历史对话中的洞察提炼进共享 memory（优先级 P2）

开发者已用 Claude Code 在某个项目上工作了数周。那些会话中讨论并确定了大量工程决策、失败路径和项目约定，但从未被显式记录为 memory 事实。开发者运行 `coffer transcript distill claude_code --project /repo`（或在 Coffer UI 中点击「提炼进 memory」）。Coffer 读取本地 `.jsonl` 对话记录文件，清洗工具调用载荷和密钥，请 LLM 提取耐久性洞察，并将它们写为项目作用域的 memory 事实。此后，任何 agent —— 包括第二台机器上的 Codex —— 都能通过 `coffer__recall` 召回这些事实，因为 memory 是共享的（Spec 007）且已同步（Spec 010）。原始对话内容从不被存储或传输。当对话记录的工作目录能解析到某个 git 项目时，提取的事实写入该项目作用域的记忆 store；若路径不在任何 git 工作树内，则回退写入全局记忆 store。

**为什么是这个优先级**：agent 在本地对话记录中积累了机构知识，这些知识原本孤立于每个会话、对其他 agent 不可见。提炼是挖掘这些知识最无侵入性的机制：它产出标准 memory 事实，免费继承跨 agent 共享和多机同步能力。它是 P2 而非 P1，因为核心共享 memory 流程（Story 1–2）必须先就位 —— 提炼是在其之上叠加的能力。完整决策依据和被否决的备选方案见 [ADR-020](../../docs/decisions/ADR-020-transcript-distillation.zh.md)。

**支持的对话记录读取器**：提炼通过版本化、防御式的 per-agent 读取器读取每个 agent 的原生本地存储。**Claude Code** 与 **Codex** 读取 agent 配置目录下每会话一个的 `.jsonl` 文件；**OpenCode** 读取 XDG data 目录下的多文件 JSON 存储树（`~/.local/share/opencode/storage/{project,session,message,part}`），将记录拼接成会话，工作目录取自 project 记录。**Cursor**、**OpenClaw**、**Hermes** 的读取器被推迟：它们的格式当前无法可靠地用于项目作用域提炼 —— Cursor 的 `agent-transcripts/*.jsonl` 是临时的（重启即清空），耐久状态在内部 `vscdb` SQLite 中；OpenClaw 的会话格式无文档；Hermes 的会话是跨平台 chat 会话、不记录工作目录，无法按项目作用域归类。对这些 agent 提炼会返回明确的「不支持的 agent」错误，而非臆测。

**独立可测**：在某个项目里、其原生存储中至少有一条 Claude Code、Codex 或 OpenCode 对话记录，运行 `coffer transcript distill <agent> --project <path> --dry-run`，观察到至少一条洞察被打印出来，但没有任何事实被写入磁盘。然后不带 `--dry-run` 再运行，通过 `coffer memory recall <store> "<topic>"` 确认：至少一条提炼事实现在可被召回，携带 `actor="agent"` 和非空的 `origin_session_id`，且不包含工具调用载荷、文件内容或疑似密钥的字符串。

**代表性场景**：

- distill transcript to memory

---

### User Story 5 —— 查看、命名并重置记忆（优先级 P3）

开发者想知道每个作用域累积了多少记忆，想在 store 的来源文件夹未知时给它起个可读的名字，并能在不删除 store 的前提下清空某个作用域。

**为什么是这个优先级**：卫生级别；不挡核心流程。

**独立可测**：查看 per-store 度量（事实条数、磁盘字节）。重命名一个文件夹未知的 store，确认所选名字出现在列表里并在重载后仍在。清空 project 作用域；确认所有事实都没了但 store 保留下来、随时可装新事实。

**代表性场景**：

- 清空一个记忆作用域
- 用户重命名一个记忆 store

（per-store 度量的 HTTP 路由由独立可测覆盖，但其专属 acceptance 测试延后 —— 见场景后的说明。）

---

### User Story 7 —— 跨 agent、跨机器接续同一份工作（优先级 P2）

开发者用 Claude Code 工作到一半暂停 —— 停在某个已知步骤、有明确的下一步、有打开中的文件
—— 之后从另一个 agent（Codex）或第二台机器接续。暂停前 agent 调 `coffer__set_handoff`，
传入当前的工作状态（「现场」）：正在做什么、下一步是什么、哪些文件在手、还有哪些未决问题。
Coffer 按 **(项目 × git 分支)** 给这份现场记账，并写成项目记忆 store 下的一个文件，于是它随
既有 git 同步镜像一起流转。恢复工作时，agent 调 `coffer__resume`，返回当前分支保存的现场
（带上它可能有多旧的标注）—— 或在全新分支上告知没有任何现场。

**为何此优先级**：连续性是本次重设计的北极星，但它建立在共享记忆内核（Story 1–2）之上：handoff
是一条附加的工作记忆 lane，而非 recall 的前置条件。按分支记账意味着并行分支 / worktree 各自保有
独立现场、互不覆盖；不存在全局 handoff（全局的「当前任务」没有意义），因此不在任何 git 项目里的
cwd 没有可恢复的现场。

**独立测试**：从 git 项目内、分支 `work` 上的某 MCP 客户端调 `coffer__set_handoff` 传入一段
正文，再从第二个客户端（不同 agent 身份）在同一项目 + 分支调 `coffer__resume`，观察返回相同的
正文、分支与一条新鲜度标注。在没有先前 handoff 的全新分支上，`coffer__resume` 报告
`found=false`。

**覆盖场景**：

- agent saves and resumes a working-state handoff
- resume reports no handoff for a fresh branch

---

### User Story 8 —— 规则在每次会话开始时环境式到达（优先级 P2）

开发者在 Coffer 里积累了行为规则（全局「push 前总是先跑 verify 步骤」、项目「这个 repo 通过
`make release` 发版」），希望它们在**每次会话开始时自动**出现在 agent 面前 —— 上午的 Claude
Code、下午的 Codex 都一样 —— 无需 agent 记得去调 `recall`，且 **Coffer 绝不写入 agent 自己的
记忆或指令文件**（ADR-026）。会话开始时，Coffer 安装的 **SessionStart hook** 向 Coffer 索取一个
规则 bundle（始终开启的全局规则，加上 cwd 解析到 git 项目时的当前项目规则），并把它作为**纯上下文**
注入会话。bundle 还携带两条 Coffer 播种的内置规则：调 `coffer__resume()` 接续此前工作，以及
优先用 `coffer__remember`/`coffer__recall` 而非 agent 的原生记忆。工作结束时，一个 SessionEnd
hook（仅 Claude Code）立即把刚结束的会话蒸馏进 journal；Codex —— 没有 session-end 事件 ——
退回到 FR-046 的补扫。想要彻底隔离的开发者可以选择启用 `disable_native_memory`，它把 agent
自己的原生记忆关掉（卸载时恢复）。

**为何此优先级**：agent 从不读规则，规则就毫无用处。环境式 session-start 注入是（ADR-026 预期的
路径）让 Coffer 的过程性记忆不靠 `recall` 纪律、不碰原生文件就在场的非侵入方式。它是 P2（非 P1），
因为它建立在 rules lane（FR-036）与共享记忆内核（Story 1–2）之上：注入交付的是已存在的规则，且
无 hook 或注入失败时绝不阻塞 agent。

**独立测试**：注册一个 Claude Code agent，安装其 hook，写一条全局规则与一条项目规则，然后在该
git 项目里开一个会话，观察注入的 `additionalContext` 含这两条规则加上两条播种的内置规则 ——
且未写入 `~/.claude/CLAUDE.md` 或 agent 的原生记忆。对 Codex（`~/.codex/hooks.json`）重复；
确认同一 bundle 在 SessionStart 到达，且 Codex 不安装 SessionEnd hook。停掉 daemon 再开会话：
hook 什么都不打印并退出 0，agent 正常启动。打开 `disable_native_memory` 确认 agent 的原生记忆
开关被写成关闭；关掉它（或卸载）确认该设置被恢复。

**覆盖场景**：

- rules bundle is injected at session start as context only
- the bundle carries the two seeded built-in rules
- session-end distils the closed session into the journal
- a failed or hook-less injection never blocks the agent
- disable_native_memory turns native memory off and restores it

---

### User Story 9 —— 逐 lane 读完整个 store（优先级 P2）

开发者在 Coffer 里打开一个 memory store，想看见 store 里**持有的全部内容**，而不只是
扁平的事实列表：语义 **Knowledge** 事实、过程性的 **Rules** 文档、按时间排序的情景
**Journal** 条目、按分支的 **Handoff** 现场，以及 organizer 的**整合 changelog**。memory
store 详情页把 store 呈现为四个 lane 区块（Knowledge / Rules / Journal / Handoff）外加一个
整合 changelog 视图。每个 lane 都有一个形状贴合的视图：Knowledge 保留事实/主题列表 + 内容
（且仍是 recall 操作的对象），Rules 是单一文档，Journal 是时间排序列表（最新优先），Handoff
是按分支列表。每个视图都**只读**，都经**统一文件预览**渲染（无手写 `<pre>`），都为底层 lane
文件提供**在外部编辑器中打开 / 在文件管理器中显示 / 复制路径** —— files-as-truth（FR-017、
FR-021），于是开发者在自己的编辑器里纠正内容，变更经 lazy reindex-on-read（FR-010）被拾取。

**为何此优先级**：扁平事实列表隐藏了四个 lane 中的三个 —— rules 在 recall 之外、journal 是
情景性的、handoff 现场是工作状态 —— 因此 store 的过程性、情景性与连续性记忆即便都在磁盘上，在
UI 里也不可见。把每个 lane 以贴合其形状的方式呈现，让整个 store 可读。它是 P2（非 P1），因为它是
对 lane 的只读投影，而这些 lane 已由共享记忆内核（Story 1–2）、journal（Story 6）、handoff
（Story 7）以及 rules/organizer lane 写入 —— 它只增加可见性，绝不新增写入路径。

**独立可测**：给一个项目 store 填入一条事实、一条 rule、一条 journal 条目、一个 handoff 现场，
并跑一次写出整合 changelog 的 organizer。打开 store 详情页，确认五个视图：Knowledge lane 显示
该事实，Rules 显示 rules 文档，Journal 列出该条目（最新优先），Handoff 列出该分支现场，changelog
视图显示固化日志 —— 每个都只读、每个都经统一文件预览渲染、每个都为其 lane 文件提供打开/显示/复制
路径。确认 recall 仍只在 Knowledge lane 上操作。

**覆盖场景**（lane 视图所消费的读端点）：

- journal lane entries are readable for a store
- handoff scenes are listed per branch for a store
- the consolidation changelog is readable for a store

（四-lane 页面的渲染本身由前端测试验证；与其它桌面视图项一样，其桌面验收延后到 e2e。上面三条
场景钉住 lane 视图所消费的读端点。）

---

### Edge Cases

- **vector 不可用但 embedding 未配置**：当 store 解析出的策略需要向量但未配置 embedding provider 时，`recall` 在内部回退到 keyword 并返回结果；它从不阻塞。回退**不**作为查询期响应标志暴露。默认检索是 keyword+grep（零配置、离线）。
- **直接在磁盘上编辑事实文件**：下一次 `recall` 会惰性扫描这个小事实目录、找出增量并重建索引，因此带外编辑会被拾取，无需 watcher。
- **空事实文本**：在 API 边界被拒；不写任何内容。
- **事实文本过长**：在 API 边界按 `max_fact_chars`（默认 8192）约束；写入前即被拒。
- **project 作用域无法解析**：若 agent 的工作目录不在某个 git 项目里，`scope=project` 被拒并给出清晰错误；`scope=global` 仍然可用。
- **在全新分支上 resume**：当前（项目 × 分支）没有保存过 handoff 时，`coffer__resume` 返回 `found=false` 而非报错；不编造任何内容。
- **不在 git 项目里的 handoff**：不在某个 git 项目里的 cwd 没有 project 作用域、也没有分支，故 `coffer__resume` 返回 `found=false`，`coffer__set_handoff` 被拒（不存在全局 handoff）。
- **daemon 关停时的注入**：当 SessionStart hook 无法触达 daemon（未运行、超时或任意错误）时，它什么都不打印并退出 0 —— 会话不带注入 bundle 启动，绝不被阻塞。
- **不在 git 项目里的注入**：bundle 仍携带全局规则与两条播种的内置规则；不含项目规则（没有 project 作用域可解析）。
- **Codex 上的 SessionEnd**：Codex 不发 session-end 事件，故不为它安装 SessionEnd hook；它的会话改由 FR-046 补扫蒸馏，补扫仍是写入保证。
- **关闭 / 卸载 disable-native-memory**：把 `disable_native_memory` 关掉（或卸载）会把 agent 的原生记忆设置恢复到先前状态；默认（关闭）完全不碰原生记忆（ADR-026）。

## Acceptance Scenarios

每条场景至少对应一个被 `@pytest.mark.acceptance(spec="007-memory", scenario="…")` 打了标记的测试。

### Scenario: agent remembers a project fact

- **Given** 一个跑在 git 项目内的 MCP 客户端，
- **When** 它用一条事实加 `scope=project` 调 `coffer__remember`，
- **Then** 在项目记忆目录的 `knowledge/inbox/` 子目录下写出一个每条记忆的 markdown 文件（YAML frontmatter `title`/`description`/`metadata.actor`/`origin_session_id` + 正文），将该文件索引进 `documents`，并写入一条审计。

### Scenario: agent recalls a project fact

- **Given** 一个有事实的项目记忆 store，
- **When** 某 MCP 客户端用一条 query 调 `coffer__recall`，
- **Then** 返回排序后的事实，每条带 id、text、score、source、time，且在搜索前已惰性扫描事实目录、拾取任何带外增量。

### Scenario: recall spans project and global scope

- **Given** global 与 project 两个作用域都存在事实，
- **When** 某 MCP 客户端不带 scope 调 `coffer__recall`，
- **Then** 结果同时取自项目 store 与 global（sentinel）store。

### Scenario: remembered items are stored in the knowledge lane

- **Given** 一个跑在 git 项目内的 MCP 客户端，
- **When** 它用一条事实调 `coffer__remember`，
- **Then** 该条目作为一个 markdown 文件写入项目 store 的 `knowledge/inbox/` 子目录（从不落在 store 根目录、也不生成任何 `MEMORY.md`），被索引进 `documents`，且随后的 `coffer__recall` 能返回它。

### Scenario: remember at global scope

- **Given** 一个 MCP 客户端，
- **When** 它用 `scope=global` 调 `coffer__remember`，
- **Then** 该事实写入由 `project_id = WORKSPACE_GLOBAL_PROJECT_ID` 标识的 global store，且从任何项目 recall 都能返回它。

### Scenario: project scope resolves from the agent's working directory

- **Given** coffer-mcp-shim 在会话握手时上报其启动 cwd，
- **When** daemon 解析项目记忆 store，
- **Then** 它计算该 cwd 的 git-root，并解析（缺失则惰性置备）由该项目 ULID 标识的 per-project store。

### Scenario: out-of-band fact-file edits are visible on recall

- **Given** 一个有事实的项目记忆 store，
- **When** 直接在磁盘上带外编辑某个事实文件（保留 frontmatter），
- **Then** 下一次 `coffer__recall` 返回编辑后的内容（惰性 reindex-on-read），且没有任何文件系统 watcher 在跑。

### Scenario: user adds a fact

- **Given** 一个记忆 store，
- **When** 用户经 Coffer UI 或 CLI 添加一条事实，
- **Then** 在 store 的 `knowledge/inbox/` 子目录下写出 `metadata.actor = "user"` 的规范化 markdown，索引该文档，并写入一条审计。

### Scenario: user corrects a fact out-of-band

- **Given** 一条事实已存在，
- **When** 用户在应用内只读视图之外纠正其文本 —— 经 REST/CLI 写入面（`PATCH …/facts/{id}` / `coffer memory edit`），或在外部编辑器里直接编辑规范化 markdown，
- **Then** 规范化 markdown 被重写、文档被重建索引（REST/CLI 路径立即重建；直接改文件则在下一次 `recall` 经 lazy reindex-on-read 重建），且 recall 反映新文本。

### Scenario: user deletes a fact

- **Given** 一条事实已存在，
- **When** 用户删除它，
- **Then** markdown 文件与其索引行被移除，且 recall 不再返回它。

### Scenario: read-only viewer offers open/reveal affordances

- **Given** 在 Coffer UI 中查看一条事实，
- **When** 用户检视该事实（及其所在文件夹），
- **Then** 内容只读渲染（应用内不编辑事实内容），读响应携带该事实的绝对 `.md` 磁盘路径及其所在文件夹的绝对路径，且 UI 在**两个**界面上都为文件与文件夹提供「在外部编辑器中打开」+「在文件管理器中显示」——桌面（Tauri）经 OS opener,web 经环回 daemon（spec 004 FR-039）——没有 copy-path 回退;打开哪个编辑器由全局首选编辑器偏好决定（见 002-ui-shell）。

### Scenario: clear a memory scope

- **Given** 一个有事实的记忆 store，
- **When** 用户清空该作用域，
- **Then** `knowledge/` 下的每条记忆条目被移除、其索引行被丢弃，但 store 这个 Resource 保留。

### Scenario: user renames a memory store

- **Given** 一个记忆 store（例如来源文件夹从未被记录、否则会显示为 `project-<ULID>` 的那种），
- **When** 用户通过 `PATCH /memory_stores/{name}/label` 设置显示标签，
- **Then** 标签被去除首尾空白、原样回显，并在 store 读取 + 列表中作为可读名呈现；空 / 纯空白标签会清除它（退回 FR-017a 推导）；重命名一个不存在的 store 返回 404，而非自动创建。

### Scenario: built-in memory tools appear in client tool list

- **Given** 一个 MCP 客户端接入 coffer 网关，
- **When** 客户端列出 tools，
- **Then** `coffer__recall`、`coffer__remember`、`coffer__list_memory`、`coffer__set_handoff`、`coffer__resume` 与其它内置工具及上游工具一起出现。

### Scenario: vector recall falls back when embedding is unconfigured

- **Given** 一个未配置 embedding provider 的记忆 store，
- **When** 引擎解析为向量策略但无可用 embedder，
- **Then** 调用改跑 keyword 检索并返回结果、不报错；降级**不**作为查询期响应标志暴露（内部 keyword 回退，与 KB 面一致）。

### Scenario: agent saves and resumes a working-state handoff

- **Given** 一个在 git 项目内、某分支上运行的 MCP 客户端，
- **When** 它调 `coffer__set_handoff` 传入正文，之后（可能换成另一个 agent）调 `coffer__resume`，
- **Then** `set_handoff` 在项目 store 的 `handoff/` 子目录下写出一个按 `(项目 × 分支)` 命名的 markdown 文件（frontmatter `branch`/`updated_at` + 自由正文）—— 覆盖该分支此前的现场，并记一条 `handoff_set` 审计；`resume` 返回 `found=true`，带上保存的 branch、body、`updated_at` 与一条新鲜度 `note`；该 handoff 绝不会被 `coffer__recall` 返回。

### Scenario: resume reports no handoff for a fresh branch

- **Given** 一个在 git 项目内、某分支上没有保存过 handoff 的 MCP 客户端（或一个不在任何 git 项目里的 cwd），
- **When** 它调 `coffer__resume`，
- **Then** 调用返回 `found=false`（绝不报错、也不编造任何内容）。

### Scenario: distill-transcript-to-memory

- **Given** 一个已注册的 agent（Claude Code、Codex 或 OpenCode），且其原生存储中至少有一条含自然语言对话轮次的对话记录，
- **When** 调用 `POST /api/v1/agents/{name}/transcripts/distill`（或 CLI 中的 `coffer transcript distill <agent>`），且 `dry_run=false`，
- **Then** 对话记录被读取，工具调用载荷和密钥在 LLM 调用前被清洗，LLM 返回结构化洞察(每条仅含 `name` / `description` / `body` —— 蒸馏不再为每条洞察分类 type),每条洞察被**追加为项目作用域的 journal 条目**(情景记忆,`actor="agent"` 记录在 `journal_append` 审计里)—— 绝不写为扁平 knowledge 事实;路径不在 git 项目内的会话被跳过(没有全局 journal);任何已持久化条目中均不出现原始对话内容;`coffer__recall` 此后返回这些新 journal 条目(FR-043);当 `dry_run=true` 时,洞察被返回但不向磁盘写入任何内容。

### Scenario: browse an agent's transcript history with title, search, and sort

- **Given** 一个已注册的 agent，其本地有跨多个项目的若干对话记录，
- **When** 以一个搜索词、一个项目筛选和一个排序键（`started_at` 或 `last_activity_at`）调用 `GET /api/v1/agents/{name}/transcripts`，
- **Then** 每条返回的会话摘要携带派生标题、消息数、`started_at`、`last_activity_at` 以及会话文件的绝对源路径；仅返回标题或项目路径匹配搜索、且项目匹配筛选的会话，按所请求的排序键与方向排列，并以 `limit`/`offset` 分页连同匹配总数返回。

### Scenario: the organizer drains the inbox into a topic document

- **Given** 一个 memory store，其 `knowledge/inbox/` 中有两条新记住的条目，且已配置内部模型，
- **When** 调用 `POST /api/v1/memory_stores/{name}/organize`（或 `coffer memory organize <name>`），
- **Then** 内部 LLM organizer 排空 inbox（不再有条目），至少存在一个持有合并后内容的 `knowledge/<topic>.md` 主题文档，`knowledge/INDEX.md` 列出了该主题，记下一条 `memory_organized` 审计，且随后的 `recall` 返回主题文档（而非现在已空的 inbox）的内容。

### Scenario: organizing merges a note into an existing topic without clobbering it

- **Given** 一个 memory store，已存在一个含内容 X 的人工编辑过的主题文档，且其 `knowledge/inbox/` 中有一条相关的新条目，
- **When** 调用 `organize`，organizer 把新条目合并进该主题，
- **Then** 该主题文档仍含原始内容 X，并并入了新整合的信息，inbox 条目已被移除，整合 changelog（`consolidation-log.md`）记下了这次合并 —— organizer 绝不从零重生、绝不覆盖人工编辑。

### Scenario: organize is a no-op when no internal model is configured

- **Given** 一个 memory store，其 `knowledge/inbox/` 中有条目但未配置内部模型，
- **When** 调用 `organize`，
- **Then** 调用返回 `status="no_model"`，inbox 原封不动，不写出任何主题文档，也不报错。

### Scenario: a topic document recalls at passage granularity

- **Given** 一个已整理的 memory store，其 `knowledge/` lane 中有一份含两个不同标题
  小节（各描述不同主题）的主题文档，并已建立 recall 索引，
- **When** 用只出现在第二个小节中的词去查询 `coffer__recall`，
- **Then** 返回命中的文本是该小节的**段落（passage）**——而非整篇文档——因此第一个
  小节的特征措辞不会出现在命中中，证明主题文档是**按段落分块**的（标题与块结构感知），
  而不是每文件一块。

### Scenario: the reorg pass consolidates duplicate topic documents

- **Given** 一个 memory store，含两份重叠的主题文档（同一主题、其中一份带额外细节），
  且已配置内部模型，
- **When** `POST /api/v1/memory_stores/{name}/reorg`（或 `coffer memory reorg <name>`）
  运行，内部 agentic 循环读取两份文档、把合并后的内容写入其中一份、并 supersede
  那份现已冗余的另一份，
- **Then** 单一主题文档持有合并后的内容，冗余文档不再出现在 `recall` 或 `INDEX.md` 中，
  随后的 `recall` 返回合并后的内容，并记下一条 `memory_reorganized` 审计。

### Scenario: reorg never destroys content — a superseded topic stays recoverable

- **Given** 一个 memory store，含一份持有内容 X 的主题文档（可能是人类编辑），
- **When** reorg 循环覆盖或 supersede 该文档，
- **Then** 先前内容 X 先被归档到 store 根的 `superseded/` tombstone（因而**可恢复**、
  绝不硬删除），该 tombstone **排除在 recall 之外**（在 `knowledge/` lane 之外），且整合
  changelog 记录该 supersession —— 循环是增量编辑，绝非从零重生。

### Scenario: reorg is a no-op when no internal model is configured

- **Given** 一个 memory store，有主题文档但未配置内部模型，
- **When** 调用 `reorg`，
- **Then** 调用返回 `status="no_model"`，不写出/不 supersede/不归档任何主题文档，也不报错。

### Scenario: 固化 promotes a recurring journal pattern into a knowledge topic

- **Given** 一个 memory store,其 journal 记忆带有若干跨越一天以上的相似情景条目(且无既有主题文档),
- **When** `reorg` 运行,循环读取 journal 并把复现模式提升,
- **Then** 写出一个捕捉该模式的 knowledge 主题文档并能被 `recall` 返回,提升记入 `consolidation-log.md`,且 journal 条目原样保留(提升是复制,绝不删除)。

### Scenario: 固化 promotes a recurring imperative pattern into the rules lane

- **Given** 一个 memory store,其 journal 记忆带有复现的祈使式("总是做 X")模式,
- **When** `reorg` 运行并经 `append_rule` 提升它,
- **Then** 该规则被追加进 `rules/rules.md`,提升记入 `consolidation-log.md`,`memory_reorganized` 审计报告 `promoted` 计数,且 journal 条目原样保留。

### Scenario: memory is auto-organized after the store goes idle

- **Given** 已启用可选的 auto-organize 触发器、已配置内部模型，且有一条新记住的条目
  进入某 store 的 `knowledge/inbox/`，
- **When** 该 store 静默（无更多 memory 写入）达到保守的去抖延迟，
- **Then** organizer **在后台自动**运行 —— 无显式 `organize` 调用 —— 把 inbox 排空进
  主题文档；且该后台 pass 绝不阻塞：若在其触发前取消挂起的触发器（例如 daemon 关停时），
  只是把未处理的 inbox 原样留给之后的 pass。

### Scenario: the organizer routes a rule-shaped note into the rules lane

- **Given** 一个 memory store，已配置内部模型，且有两条新记住的 inbox 条目 —— 一条是
  行为规则（“推送前总是先跑 verify 步骤”），一条是普通事实，
- **When** `organize` 运行，organizer 把第一条分类为 rule、第二条分类为普通 knowledge，
- **Then** 该 rule 被追加到 store 的过程性 `rules/rules.md` lane（而非写入 `knowledge/<topic>.md`），
  普通事实成为一个主题文档，两条 inbox 条目都被排空，且 `recall` **不**呈现该 rule（`rules/`
  lane 在 `knowledge/` recall glob 之外，与 `handoff/`、`superseded/` 一样）。

### Scenario: the rules read surface returns the stored rules

- **Given** 一个 memory store，其 `rules/rules.md` 持有一条或多条 rule，
- **When** 调用 `GET /api/v1/memory_stores/{name}/rules`（或 `coffer memory rules <name>`），
- **Then** 响应原样返回 rules 文本（供之后 session-start 注入读取的那个面），且无 rule 的
  store 返回空/`null` 正文而非报错。

### Scenario: journal lane entries are readable for a store

- **Given** 一个 memory store，其 `journal/` lane 持有一个或多个
  `journal/<YYYY-MM-DD>.md` 文件，
- **When** 调用 `GET /api/v1/memory_stores/{name}/journal`（按 store 名寻址，而非 cwd），
- **Then** 响应按**最新分片优先**返回时间排序的 journal 文件，每个携带其 `period`、`text`、
  磁盘绝对 `path` 及其所在 `folder_path`；无 journal 的 store 返回**空列表加 HTTP 200**
  （绝非 404）。

### Scenario: handoff scenes are listed per branch for a store

- **Given** 一个 memory store，其 `handoff/` lane 持有一个或多个按分支的现场文件，
- **When** 调用 `GET /api/v1/memory_stores/{name}/handoff`（按 store 名寻址，而非 cwd），
- **Then** 响应**按分支**列出现场，每个携带其 `branch`、`text`、`updated_at`、磁盘绝对
  `path` 及 `folder_path`；无 handoff 现场的 store 返回**空列表加 HTTP 200**（绝非 404）。

### Scenario: the consolidation changelog is readable for a store

- **Given** 一个 memory store，其 organizer 已在 store 根目录写出 `consolidation-log.md`，
- **When** 调用 `GET /api/v1/memory_stores/{name}/consolidation-log`（按 store 名寻址，而非 cwd），
- **Then** 响应返回 changelog 的 `text` 及其磁盘绝对 `path` 与 `folder_path`；无 changelog 的
  store 返回 `text = null` 加 HTTP 200（绝非 404）。

### Scenario: rules bundle is injected at session start as context only

- **Given** 一个受管 agent（Claude Code 或 Codex）已安装 Coffer SessionStart hook，
  且 cwd 所在 git 项目里有一条全局规则与一条项目规则，
- **When** 会话开始、hook 调 `GET /api/v1/agents/{name}/session-context?cwd=<cwd>`，
- **Then** daemon 返回 `additional_context`，先项目规则后全局规则，hook 把它作为 SessionStart
  的 `additionalContext` 注入（纯上下文），且**不**写入 agent 的原生记忆或指令文件（ADR-026）。
  当 cwd 不在 git 项目里时，bundle 只携带全局规则（无项目规则）。

### Scenario: the bundle carries the two seeded built-in rules

- **Given** session-context 端点组装一个 bundle（即便 store 没有任何 rule），
- **When** bundle 被返回，
- **Then** 它始终包含两条 Coffer 播种的内置规则 —— 调 `coffer__resume()` 接续此前工作，以及
  优先用 `coffer__remember`/`coffer__recall` 而非 agent 的原生记忆 —— 且 handoff 正文本身
  **不**被注入（经 `coffer__resume` 按需拉取）。

### Scenario: session-end distils the closed session into the journal

- **Given** 一个 Claude Code agent 已安装 Coffer SessionEnd hook，且已配置内部模型，
- **When** 会话关闭、hook 调 `POST /api/v1/agents/{name}/sessions/{session_id}/end` 携带 cwd，
- **Then** 刚关闭的会话被蒸馏进项目 journal 记忆带，复用 FR-045 蒸馏路径，记录在
  `distilled_sessions` 幂等账本（FR-046）里，故绝不被重复蒸馏；当会话已蒸馏、未配置模型、或 cwd
  不在 git 项目时该调用为 no-op。Codex 不安装 SessionEnd hook，退回到 FR-046 补扫。

### Scenario: a failed or hook-less injection never blocks the agent

- **Given** SessionStart hook 已安装但 daemon 不可达（未运行、超时或任意错误），
- **When** 会话开始，
- **Then** hook 什么都不打印并退出 0，会话不带注入 bundle 启动，agent 绝不被阻塞；未安装 hook
  的 agent 直接没有注入。

### Scenario: disable_native_memory turns native memory off and restores it

- **Given** 一个受管 agent `disable_native_memory=false`（默认），
- **When** 用户设 `disable_native_memory=true`，
- **Then** Coffer 写入 agent 的原生记忆关闭开关（Claude Code `autoMemoryEnabled=false`；
  Codex `features.memories=false` + `memories.generate_memories=false`），而把它设回 `false`
  （或卸载）会恢复先前设置；为 `false` 期间 Coffer 绝不碰 agent 的原生记忆（ADR-026）。

> **Deferred to future test work**（测试随 e2e 基础设施落地；`make verify-acceptance` 不对它们做门禁）：桌面记忆列表按作用域展示、桌面只读事实视图的打开/显示能力、`coffer memory …` CLI 端到端配带 daemon、per-store 度量（HTTP 路由）。

## Requirements

### Functional Requirements

**存储与作用域**

- **FR-001**：系统 MUST 把每条记忆条目存为一个每条记忆的 markdown 文件（YAML frontmatter `title`/`description`/`metadata.actor`/`origin_session_id` + 正文），位于每个作用域的 **`knowledge/` lane** 下 —— 新记住的条目落在 `knowledge/inbox/`，经整理的主题文档（`knowledge/<topic>.md`）加一个 `INDEX.md` 由整合 organizer 维护（后续 memory PR）。markdown 文件是 **唯一真相源**；SQLite 是可重建的索引。**不生成任何 `MEMORY.md` 索引**（此前的派生索引是无用的投影产物，检索里没人读它）。
- **FR-002**：系统 MUST 支持两种记忆作用域：**global**（一个由 `project_id = WORKSPACE_GLOBAL_PROJECT_ID`（既有 sentinel `00000000000000000000000000`）标识的 store）与 **per-project**（每项目一个、由项目 ULID 标识的 store），分别存于 `~/.coffer/memory/global/knowledge/` 与 `~/.coffer/memory/projects/<project-ulid>/knowledge/`。
- **FR-003**：`coffer__remember`（与用户添加）MUST 把一条记忆条目追加进每作用域的 inbox（`knowledge/inbox/`），写入时不调 LLM；整理进主题文档由整合 organizer 异步完成（后续 memory PR），绝不阻塞写入或 `recall`。
- **FR-004**：系统 MUST 从 agent 在会话握手时上报的启动 cwd 解析 per-project store：daemon 计算 git-root，并解析（缺失则惰性置备）该项目 ULID 对应的 store。

**事实生命周期**

- **FR-005**：agent 与用户 MUST 能直接写入一条事实（写入时不调 LLM）。事实文本 MUST 至少 1 个字符、至多 `max_fact_chars`（默认 8192）；空或超长在 API 边界被拒，不持久化任何内容。
- **FR-006**：用户与 agent MUST 能列出事实（按作用域）、按 id 取单条、改一条事实的文本、删除单条事实、清空某作用域全部事实。事实**编辑/删除**经 REST/CLI 写入面（`PATCH/DELETE …/facts/{id}` / `coffer memory edit/delete`）与外部编辑器 files-as-truth —— Coffer UI 只读渲染事实内容、不在应用内编辑它；MCP 的 `update_memory`/`forget` 工具已**移除**（agent 的写入面是 `remember` + 内部 organizer）。清空保留 store 这个 Resource。
- **FR-007**：每条事实带 `metadata.actor`（`agent` | `user`），由写入者设定。**没有自由格式的 `type` 字段** —— `Lane` 是唯一的分类轴（FR-048），由内部路由（organizer / 蒸馏）决定，绝不由写入者提供。

**检索**

- **FR-008**：recall MUST 使用与 knowledge base 共享的统一检索引擎：`grep`（ripgrep 扫该 store 的事实文件；对 FTS5 无法分词的内容必不可少，如 CJK）、`keyword`（FTS5 BM25，默认）、`vector`（sqlite-vec 配可配置的 embedding provider）。这些引擎模式是**内部细节** —— recall **不**接受外部 `mode`；引擎自动解析该 store 的默认策略。当解析出的策略需要向量但未配置 embedding provider 时，recall MUST 在内部回退到 `keyword` —— 绝不阻塞，且回退**不**作为查询期响应标志暴露（`fallback` 字段已从 recall 响应移除）。
- **FR-009**：`coffer__recall` MUST 默认跨 project 与 global 两个 store（显式给出 `scope` 时收窄到单个 store：`project` = 仅项目 store，`global` = 仅 global store）；跨 store 的结果用倒数排名融合（reciprocal rank fusion）合并（逐 store 的分数跨模式/跨 store 不可比；每条命中保留其逐 store 分数，只有合并后的顺序来自融合）。结果带 id、text、score、source、time —— `time` 是事实的 `updated_at`，`source` 是 `<scope>:<fact file path>`。默认 `top_k` 为 5；调用方 MAY 指定 1–20。
- **FR-010**：memory MUST 用 **lazy reindex-on-read**：`recall` 先按内容哈希扫描事实目录的增量（新增/变更/删除文件）并对账索引，再搜索，使带外编辑 —— 人类在自己外部编辑器里做的纠正，或任何直接在磁盘上的编辑 —— 即时可见，无需文件系统 watcher。这正是让外部纠正得以显现的机制，于是 UI 可以保持为只读视图（FR-017），而维护在用户的编辑器里完成。

**通过 MCP 集成 agent**

- **FR-015**：Coffer 的 MCP 网关 MUST 暴露内置工具 `coffer__recall(query, scope?, top_k?)`（无 `mode` 参数 —— 检索模式是内部的）、`coffer__remember(text, scope?)`（无 `type` 参数 —— 已按 FR-048 废弃）、`coffer__list_memory(scope?)`、`coffer__set_handoff(body)`、`coffer__resume()`，挂在保留前缀 `coffer__` 下。`remember` 默认 `scope=project`；`recall` 默认两个作用域。没有 MCP `update_memory`/`forget` 工具 —— 事实编辑/删除是用户面（REST/CLI/外部编辑器），见 FR-006。
- **FR-016**：这些内置 memory 工具调用 MUST 共用既有调用日志面（`mcp_invocations` 一行：工具名 + who/when/duration/outcome，不记参数也不记返回内容）。

**工作状态 handoff（连续性）**

- **FR-023**：系统 MUST 提供一条按 **(项目 store × git 分支)** 记账的**工作状态 handoff** lane：每分支一个文件，位于 `~/.coffer/memory/projects/<project-ulid>/handoff/<branch-slug>.md`，含 YAML frontmatter（`branch`、`updated_at`）加自由 markdown 正文。分支从 agent 上报的 cwd（其 repo 的当前分支）解析。handoff **仅限项目级** —— 不存在全局 handoff。
- **FR-024**：`coffer__set_handoff(body)` MUST **覆盖**当前分支的 handoff 文件（不累积；每分支一份现场），更新 `updated_at`，并记一条 `handoff_set` 审计。handoff 正文以磁盘文件为准（随 git 同步镜像流转，与其它 memory 文件一致），且 MUST NOT 被 `coffer__recall` 返回（它在 `handoff/` 子目录里，在 recall 的 glob 之外）。
- **FR-025**：`coffer__resume()` MUST 返回当前分支保存的 handoff —— `found=true`，带 `branch`、`body`、`updated_at` 与一条标注现场可能已过期的新鲜度 `note` —— 或当该分支没有 handoff（全新分支）或 cwd 不在 git 项目里时返回 `found=false`。它 MUST 在缺失 handoff 时绝不报错，且 MUST NOT 编造内容。
- **FR-026**：当 agent 的 cwd 解析不到 git 项目（无 project 作用域、无分支）时，`coffer__set_handoff` MUST 被拒（没有可写的 store，也没有全局 handoff），`coffer__resume` MUST 返回 `found=false`。

**整合 —— 内部 organizer**

- **FR-027**：系统 MUST 提供一个**内部 memory organizer**，它**仅在显式触发时**（`POST /api/v1/memory_stores/{name}/organize` 与 `coffer memory organize <name>`；本 PR 不做任何自动/后台触发）运行，使用 Coffer 的**内部 LLM connection**（被标记为内部默认的 connection；在 Settings → LLM Connections 配置，spec 011）通过**每条目一次 one-shot completion**，把 store 的 `knowledge/inbox/` 中新记住的条目排空、整合进一小组连贯的**主题文档**（`knowledge/<topic-slug>.md`，YAML frontmatter `title`/`description`/`updated_at` + markdown 正文）—— 绝不是面向 agent 的工具。organizer MUST 顺序处理各条目，且单个条目的 LLM/解析失败 MUST NOT 中止整轮（其余条目仍照常整理）。
- **FR-028**：对每个 inbox 条目，organizer MUST (a) 经共享检索引擎取回至多 top-K（K=3）最相关的**既有主题文档**（此步不用 LLM）作为合并候选，(b) 发起**一次 LLM 调用**，要么把该条目 MERGE 进最契合的候选 —— **保留全部既有内容与人工编辑**、整合新信息、去除完全重复 —— 要么在没有契合者时 CREATE 一个新主题，(c) 把返回的完整文档正文写入 `knowledge/<topic-slug>.md`。organizer MUST 是**对既有文档的增量 MERGE，绝不从零重生**：把完整既有主题内容交给 LLM 去合并，使人工纠正得以存续。organizer MUST NOT 硬删除既有主题文档（只创建或用合并后内容覆盖；git 历史即审计轨迹）。
- **FR-029**：inbox 条目 MUST **仅在**其内容成功写入主题文档**之后**才被删除。畸形或不可解析的 LLM 响应（缺失/空的必填键、不安全的 `topic_slug`、或非 JSON）MUST 导致该条目被**跳过** —— 留在 inbox，不写出也不损坏任何主题文档 —— 并继续整轮；结果中报告被跳过的条目数。对空 inbox 调 `organize` 是 no-op（`status="empty"`）；当未配置内部 connection 时，`organize` 是干净的 no-op（`status="no_model"`，inbox 原封不动、不写任何内容）而非报错。
- **FR-030**：排空后，organizer MUST 从所有主题文档的 frontmatter 重新生成 store 的 `knowledge/INDEX.md` 审阅目录（`- [<title>](<slug>.md) — <description>`），对账索引（丢弃被删的 inbox 行、(重)索引新/更新的主题文档，使 `recall` 返回主题文档的内容而非被排空的 inbox），并记一条 `memory_organized` 审计（仅 store + 计数 —— 无条目内容）。`recall` MUST 呈现已整理的主题文档内容，且 MUST NOT 呈现 `INDEX.md`。
- **FR-031**：organizer MUST 在 store 根目录维护一份**非阻塞的整合 changelog**（`<store>/consolidation-log.md`，只追加、人类可读：每条合并/创建的主题一行，带时间戳与来源 inbox 条目）。该 changelog 可审计、绝不是闸门，且**排除在 recall 之外**（它在 `knowledge/` lane 之外）与**排除在同步镜像之外**（机器本地，与 `INDEX.md` 一样；主题文档本身作为真相源 DO 同步）。
- **FR-032**：memory 对账器 MUST 用检索基座共享的 markdown 分块器（`infrastructure/knowledge/chunking.chunk_markdown` —— 按标题小节切分、保持 fenced code/表格原子、把结构块打包进固定窗口）把事实文件正文切成**段落粒度、结构感知的分块**，并使用**固定的 memory 分块 size/overlap 参数**（不是 `MemoryStoreConfig` 的 per-store 字段），从而让一份多小节的已整理主题文档在 `recall` 时呈现**最相关的段落**，而非把整篇正文作为单一分块。短的单段落事实（如 inbox 条目）仍只切成一块 —— 因此这只改变大/已整理主题文档的**粒度**，绝不改变 `recall` *包含/排除什么*：`INDEX.md`、inbox 与主题文档之分、以及 `handoff/` 的 recall 隔离（FR-024/030/031）和遗留根目录事实的废弃（FR-019）全部不变。
- **FR-033**：系统 MUST 提供一个**内部 agentic 重组 pass**，仅在**显式触发**时运行（`POST /api/v1/memory_stores/{name}/reorg` 与 `coffer memory reorg <name>`；本 PR 无自动/后台触发），由 Coffer **内部 LLM connection**（被标记为内部默认的 connection；在 Settings → LLM Connections 配置，spec 011）驱动一个有界的 **langgraph `create_react_agent` 循环**，在 store 既有的主题文档上保持其连贯 —— 合并重复/重叠的文档、拆分过长的文档。循环获得一个小而固定的工具面：**list** 主题、**read** 主题、**write**（创建/覆盖）主题、**supersede**（退役）主题,外加 FR-047 的 journal 提升工具（**read journal**、**append rule**）,且**绝非 agent 可见工具**（它是内部的，与 organizer 一样）。langchain/langgraph 代码 MUST 限制在 `infrastructure.chat`（importlinter Contract 9）；`application/memory` 只通过注入的 memory-local 端口触达它。未配置内部 connection 时该 pass 是干净的 no-op（`status="no_model"`，不写/不 supersede/不归档）而非报错；**既无主题文档也无 journal 条目**的 store 同样 no-op（`status="empty"`）。循环结束后该 pass MUST 重新生成 `INDEX.md`、对账索引（使 `recall` 反映整合后的文档）、并记一条 `memory_reorganized` 审计（仅 store + 计数 —— 无文档内容）。
- **FR-034**：reorg pass MUST **非破坏且增量 —— MUST NOT 硬删除或从零重生主题文档**。任何移除或替换既有主题文档内容的变更，MUST 先把当前版本**归档**到 store 根的 `superseded/` tombstone（`<store>/superseded/<slug>-<timestamp>.md`）：覆盖既有主题的 `write` 在写新内容前先归档旧版本，`supersede` 把文档**移动**到那里（绝不 unlink 入虚空）。`superseded/` tombstone **排除在 recall 之外**（在 `knowledge/` lane 之外，与 `handoff/`、`consolidation-log.md` 一样），且作为可恢复的真相源历史 **DO 同步**（不同于机器本地的 `INDEX.md`/changelog）。主题文档写入保持**原子**，每次 write/supersede 追加到 `consolidation-log.md` changelog。这就是数据不丢保证：没有任何字节在未被可恢复归档前离开 `knowledge/` lane，因此人类编辑永不会被不可恢复地覆盖。
- **FR-035**：系统 MUST 提供一个**自动 session-end organize 触发器**，在某 memory store 静默时**自动、在后台**触发 `organize` pass（FR-027）—— 在没有 per-agent 断连信号的情况下近似“session end”。它由 memory 写入通知钩子驱动：每次 memory 写入都会（重新）武装一个**去抖（debounced）**定时器；当配置的静默延迟在无更多写入下走完，organizer 作为后台任务对发生变化的 store 运行。该触发器 MUST **保守且非阻塞**：(a) 它**默认开启** —— 写入→organize→固化 整合流水线自动运行（无手动原则，§4.4），由环境**关闭**开关控制；手动 `coffer memory organize` 仍是特例覆盖；(b) 后台 pass MUST 绝不阻塞或破坏 daemon 关停 —— 关停时任何挂起的定时器被**取消**（未触发的 inbox 原样留给之后的静默 pass 或显式触发；不丢任何东西，因为 `recall` 本就覆盖 inbox 且 `organize` 幂等）；(c) 后台 pass 的失败 MUST 被吞掉并记录日志，绝不上抛给写入方或中断 daemon；(d) 未配置内部 connection 时该 pass 是干净 no-op（FR-027）。它**不引入新的 REST/CLI 面**（是对既有 organizer 的内部触发），并复用 `memory_organized` 审计。langchain/langgraph 限制（Contract 9）不变：触发器位于 `application`/`surfaces`，只通过已接线的 organizer 触达 LLM。
- **FR-036**：系统 MUST 提供一个**过程性 `rules` lane** —— 每个 memory store（全局 + 每项目）一份 `rules/rules.md`，持有“要这样做 / 别那样做”的行为规则。**amendment 2026-06-22（自主拆分）：** 内容少时维持单一 `rules/rules.md`；任一 `rules/*.md` 超过 **100 条**后，organizer 的 reorg/organize pass 经一次 one-shot LLM 按主题分类，把它重分布到 per-topic `rules/<slug>.md`（递归 —— 超阈值的类别再拆成更细的 slug）。新规则仍追加到 `rules/rules.md`；读取面拼接**全部 `rules/*.md`**。rules lane 是**由 organizer 分类写入的，绝非 agent 显式参数**：在 `organize`（FR-027/028）期间，organizer 每条目的单次 LLM 调用 MAY 额外把某 inbox 条目分类为 **rule**；rule 条目被**追加**到 `rules/rules.md`（仅在追加成功后才排空该 inbox 条目），而不是合并进 `knowledge/<topic>.md` 主题文档，且 `organize` 的结果/审计报告一个 `rules_appended` 计数。`rules/` lane 位于 store 根目录（`knowledge/` 的同级，与 `handoff/`、`superseded/` 一样），因而**自动排除在 `recall` 之外**（recall glob 与对账器只下探 `knowledge/`；grep 守卫只保留 `knowledge/` 命中）—— rules 由**环境式 session-start 注入**交付，而非 `recall`。该 lane 是**真相源、DO 同步**（与 `handoff/`/主题文档一样；它不是派生/机器本地文件）。系统 MUST 把存储的 rules 只读暴露给注入面：`GET /api/v1/memory_stores/{name}/rules` 与 `coffer memory rules <name>` 返回 rules 文本（无 rule 时返回空/`null` 正文，绝不报错）。把这些 rules 作为上下文注入到每个受管 agent 的 **session-start 注入**（ADR-026：只注入、绝不原生写文件）在 FR-049–FR-052（slice 6）规范 —— 本 rules-lane PR 落地 lane、分类与供注入消费的读取面。

**Journal 记忆带（情景 / episodic）**

### Journal 记忆带(情景 / episodic)

- **FR-040:** Coffer SHALL 提供按项目的 `journal` 记忆带,把情景事件以追加式、按时间分片的 markdown 文件存储(`projects/<ulid>/journal/<YYYY-MM-DD>.md` —— **每天一个文件;amendment 2026-06-22**)。当天无条目则不建文件。没有全局 journal。
- **FR-041:** Journal 文件 SHALL 纳入同步镜像作为真相源历史(同 `rules/`、`superseded/`)。与 `rules/`、`handoff/` 不同,journal 记忆带还参与 `recall`(FR-043)。
- **FR-042:** Coffer SHALL 暴露内部 `JournalService.append(cwd, body, actor)` 与 `read_recent(cwd, limit)`。在 git 项目外 append 抛 `ScopeUnresolved`;项目外读取返回空列表。`read_recent` 按最新优先返回,数量上限为 `limit`;`limit=0` 返回空列表(不隐式表示“全部”)。空/纯空白正文将被**跳过** —— `append` 返回 `None`,不写文件、不记审计(amendment 2026-06-22)。`journal_append` 审计条目只记录 `char_size`,绝不记录正文。
- **FR-043:** Journal 记忆带 SHALL 参与 `recall`。记忆 reconciler MUST 扫描每个 `journal/<YYYY-MM-DD>.md` 文件并把它索引为一个记忆文档(`kind=memory`),用与主题文档(FR-032)相同的共享 markdown 分块器与固定参数分块,并纳入懒惰的读时重建索引(FR-010),使外部编辑或新的 `JournalService.append` 在下一次 `recall` 时即可被检索到。grep recall 守卫(原本只保留 `knowledge/` 命中)MUST 额外保留 `journal/` 命中,并按 journal 文件而非 fact 文件解析它们。Journal 文档 MUST NOT 计入 store 的 `fact_count`(该计数只统计 `knowledge/` 记忆带)。`rules/`、`handoff/`、`superseded/` 记忆带仍排除在 `recall` 之外。
- **FR-044:** 来自 journal 记忆带的 `recall` 命中 MUST 能与 `knowledge/` 命中区分:与所有 recall 命中一样,其 `source` 携带被命中文件的磁盘路径(同 FR-022),而 journal 命中的路径是 `journal/<YYYY-MM-DD>.md` 文件(含 `journal/` 记忆带片段),因此 agent 能区分情景事件与语义事实。
- **FR-045:** 对话记录蒸馏(用户故事 6)SHALL 把每条提取出的洞察写入 **journal** 记忆带(情景),而**不是**扁平的 `knowledge/` 事实。蒸馏保持“笨”:只提取 `name` / `description` / `body`,MUST NOT 为每条洞察分类 type —— 旧的 `InsightType`(`decision` / `gotcha` / `convention` / `todo`)被废弃(蒸馏洞察、蒸馏 prompt、蒸馏响应里都不再有 `type` 字段)。每条洞察经 `JournalService.append` 追加到会话所属项目的 journal;路径不解析为 git 项目的会话被跳过(没有全局 journal)。蒸馏响应报告写入的 journal 条目(`fact_ids` 字段重命名为 `journal_entries`)。把复现的 journal 模式固化进 `knowledge`/`rules` 是 organizer 的职责(后续固化切片),绝非蒸馏的。
- **FR-046:** 记忆记录 MUST 是**自动**的,不依赖人去运行 `coffer transcript distill`。系统 SHALL 运行一个**自动蒸馏补扫(catch-up sweep)**—— 一个后台 worker,在 daemon 启动时及之后周期性地扫描每个受管 agent 的对话记录会话,把任何**已结束、尚未蒸馏**的会话蒸馏进 journal 记忆带(FR-045)。一个会话仅当其 `last_activity_at`(a)**已结束**(早于一个 settle 阈值 —— 绝不处理进行中的会话)且(b)在一个**新近窗口**内(补抓近期漏掉会话的兜底网,而**非**全量历史回填)时才合格;每轮最多蒸馏有上限数量的会话(其余后续轮次补上,并记日志)。已蒸馏会话按 `(agent, session_id, content_sha256)` 记录在机器本地账本里,使会话**绝不被重复蒸馏**(仅当内容实质变化才重蒸);该账本就是未来 SessionEnd hook(slice 6)共享的幂等键。该 sweep **默认开启**(它就是写入保证),并带环境开关可关闭;它**非阻塞且抑制失败**(单个会话的 LLM/解析失败绝不中止 sweep 或 daemon,同 FR-035),未配置内部连接时为干净**空操作**,关停时 worker 直接停止不触发。它**不引入新的 REST/CLI 面**,复用 FR-045 蒸馏路径 + journal 记忆带。(即时的 SessionEnd hook 属于 slice 6;本 sweep 是独立的保证。)
- **FR-047:** 重组 pass(FR-033)SHALL 额外执行**固化(consolidation)**—— 把 **journal** 记忆带里**复现、持久**的情景模式提升进语义带。agentic 循环在主题工具之外再获得两个内部工具:**读取近期 journal** 条目、**追加 rule**(`rules/rules.md`)。它把在 journal 中复现的模式 —— 保守地,大致**≥3 条相似条目、跨 ≥2 个不同日期**(由 LLM 判断;绝非一次性)—— 提升为一个 **knowledge 主题**(经 `write_topic`),或当模式明显是**祈使/行为性**的(“总是做 X”)时提升进 **rules** 带(经 `append_rule`)。**一次性**事件**留在 journal 里**(由 prune 按龄淘汰,后续切片),绝不自动提升。提升是把持久模式**复制**进语义带 —— **不**删除 journal 条目。每次提升都追加到 store 根的 `consolidation-log.md` changelog,`memory_reorganized` 审计报告一个 `promoted` 计数。固化是**保守的** —— 拿不准时把条目留在 journal(避免固化噪声)。
- **FR-048:** 自由格式的事实 `type` 字段被**废弃** —— `Lane`（`knowledge` / `rules` / `journal` / `handoff`）是**唯一的分类轴**。系统 MUST NOT 在 `MemoryFact` 上、在事实文件 frontmatter（`metadata.type`）里、在 `documents.metadata` JSON 里、在 `coffer__remember` 工具 schema 里、或在 REST/CLI 事实写入面（`FactCreate`/`FactUpdate`/`FactOut`、`coffer memory add --type`）携带 `type` 字段。事实的 lane 由**内部路由**（organizer / 蒸馏）决定，绝不由写入者提供。既有磁盘记忆为**丢弃重建**（Coffer 未发布）：**没有 Alembic 迁移** —— `type` 存在 `metadata` JSON 里而非列里,旧事实文件里残留的 `metadata.type` 键解析时被直接忽略、并在下一次 reindex-on-read 时丢弃;全新安装(或清空 `~/.coffer/memory/`)即从无 type 开始。

**规则运行时注入与原生记忆（session hooks）**

- **FR-049：** 系统 MUST 通过一个 **SessionStart hook** 把 rules lane（FR-036）交付到每个受管 agent，该 hook 注入一个**只作为上下文的规则 bundle —— 绝不原生写文件**（ADR-026）。Coffer 把 hook 安装进 agent 自己的 hooks 配置（**Claude Code** → `~/.claude/settings.json` 顶层 `hooks`；**Codex** → `~/.codex/hooks.json` 顶层 `hooks` —— 同一套 JSON schema），只识别自己的条目（`coffer-hook` 命令 basename）、不动用户 hook；安装/卸载幂等且原子（`.bak` 备份），并审计 `AGENT_HOOK_INSTALLED`/`AGENT_HOOK_UNINSTALLED`。在 SessionStart 时 hook 回调 Coffer —— 携 daemon token 调 `GET /api/v1/agents/{name}/session-context?cwd=<cwd>` —— daemon 返回 bundle = **全局规则（始终）** 加上 **当前项目规则（cwd 解析到 git 项目时）**，先项目后全局。hook 把 bundle 作为 SessionStart 的 `additionalContext` 输出并退出 0。hook MUST **绝不阻塞 agent**：未安装 hook、或 daemon 不可达/超时/报错时，**不注入**且 hook 仍退出 0。hook 在 **resume/clear/compact** 时重跑（matcher 覆盖 `startup|resume|clear|compact`）。
- **FR-050：** 注入的 bundle（FR-049）MUST 额外携带**两条 Coffer 播种的内置规则**，即便 store 的 `rules/rules.md` 为空也在场：(a) 当用户想接续此前工作（「continue」「where were we」「resume」）时，调 `coffer__resume()` 拉取本项目 + 分支保存的工作状态 handoff；(b) 一条**软引导**，优先用 `coffer__remember`（记录持久事实）与 `coffer__recall`（取回它们）而非 agent 自己的原生记忆，因为 Coffer 是用户各 agent 间的共享 store。**handoff 正文本身不被注入** —— 它经 `coffer__resume`（FR-025）**按需拉取**，于是 bundle 保持精简、陈旧现场绝不被硬塞进上下文。
- **FR-051：** 系统 MUST **仅为 Claude Code 安装一个 SessionEnd hook**，它**立即把刚关闭的会话自动蒸馏进 journal 记忆带**，降低记忆捕获的延迟。会话结束时 hook 调 `POST /api/v1/agents/{name}/sessions/{session_id}/end` 携带 cwd；daemon 复用 FR-045 蒸馏路径与 `distilled_sessions` 幂等账本（FR-046）—— `is_distilled? → distill → mark_distilled` —— 故会话**绝不被重复蒸馏**，且当会话已蒸馏、未配置内部模型、或 cwd 不在 git 项目时该调用为干净 no-op。**Codex 没有 session-end 事件**，故不为它安装 SessionEnd hook；Codex 会话由 **FR-046 补扫**捕获，补扫**仍是写入保证** —— 本 hook 只降低延迟、绝不取代补扫。
- **FR-052：** 系统 MUST 提供一个**可选的 per-agent `disable_native_memory` 配置（默认 `false`）**。**关闭**（默认）时 Coffer **绝不碰 agent 的原生记忆**（ADR-026）。用户**打开**它时，Coffer 写入 agent 配置以关闭其原生记忆 —— **Claude Code** `autoMemoryEnabled=false`（`~/.claude/settings.json`）；**Codex** `features.memories=false` + `memories.generate_memories=false`（`~/.codex/config.toml`）—— 原子写入（`.bak` 备份）并审计该关闭；**再次关掉它、或卸载**会**恢复** agent 先前的原生记忆设置（审计）。这是一个**洁净选项**（避免第二份发散的记忆副本），**不是写入保证的必要条件**：无论该开关如何，规则 bundle 照样注入、会话照样蒸馏。

**Transcript history（对话历史）**

- **FR-037**：对话记录读取器 MUST 解析每种受支持 agent 的*真实*磁盘会话格式。**Codex** rollout 文件（`~/.codex/sessions/**/*.jsonl`）把每个事件包在 `payload` 信封里：工作目录与会话 id 来自 `session_meta.payload.cwd`/`payload.id`，对话轮次是 `response_item` 事件且其 `payload.type == "message"`（role + 带类型的 `*_text` 内容块）。读取器 MUST 仅按这些 `response_item` 消息计数轮次 —— 并行的 `event_msg` 的 `user_message`/`agent_message` UI 事件 MUST NOT 被重复计数 —— 并 MUST 保持防御性（跳过无法识别/非 JSON 的行，绝不因单行坏数据抛错）。**Claude Code** 的扁平顶层格式不变。（本切片之前，Codex 解析器读取真实格式从不携带的顶层字段，导致每个 Codex 会话都列为 0 条消息、无项目。）
- **FR-038**：每条对话会话摘要 MUST 携带可读的**标题**、**最后活动时间**（`last_activity_at`）以及会话文件的绝对**源路径**。标题在存在时取 agent 自己的会话标题（Claude Code 的 `ai-title`，最新者胜），否则取第一条*真实*用户消息 —— 跳过非对话性前导（环境/指令块、shell 命令回显、斜杠命令）—— 截断为单行；当无法派生时 MAY 为 null。`started_at` 是第一个事件时间戳，`last_activity_at` 是最后一个。源路径经共享 `FileActions` 组件驱动只读的“在文件管理器中显示”操作（桌面端 reveal / web 端复制路径），与 memory 事实的 FR-021/FR-022 一致 —— 不引入新的后端 open/reveal 端点。
- **FR-039**：对话列表面（`GET /api/v1/agents/{name}/transcripts`）MUST 暴露该 agent 的**全部**会话（而非仅最近窗口），支持服务端**搜索**（对标题或项目路径匹配的查询）、**筛选**（按精确项目路径、按 `started_at` 时间范围）与**排序**（按 `started_at`、`last_activity_at` 或 `message_count`，升序或降序），以 `limit`/`offset` 分页并返回匹配 `total`。读取器 MUST 用进程内、按 mtime 键控的缓存支撑它，使含数千会话的 agent 的重复列表保持响应 —— 仅在某会话文件 mtime 变化时才重新解析它。

**Surfaces**

- **FR-017**：用户 MUST 能通过编程写入面完成完整记忆 CRUD —— (a) `/api/v1/memory_stores/` 下的 REST API 与 (b) `coffer memory …` 子命令。（这些 REST 写入端点也是 agent 经 MCP 网关写入事实的途径。）用户写入设 `metadata.actor = "user"`，把规范化 markdown 写入 store 的 `knowledge/inbox/` 子目录、重建索引并审计。桌面/web UI 以 **只读** 方式呈现事实（不在应用内编辑事实内容）；人类维护时在自己的外部编辑器里编辑规范化 markdown（经 lazy reindex-on-read（FR-010）拾取），或经 REST/CLI 写入面。只读视图 MUST 以舒适的阅读 **最大宽度**（居中）呈现事实内容；详情页的事实**列表** MUST 是单一**可滚动**列表,**不含应用内分页器**（UI 一次按最大 `limit` 取一页;事实 **API** 仍按 `limit`/`offset` 分页）。这些 surface 上的 store 名会被校验：只有 `global` 或 `project-<26 字符 ULID>` 合法 —— 形状合法的名字会惰性 provision 其 store；其余返回 404（`MEMORY_STORE_NOT_FOUND`）。
- **FR-017a**：各 surface MUST 用**从 `project_root` 推导的可读身份**来呈现 per-project store —— 以根目录的 basename 作为主标签、绝对根路径作为次要细节 —— 而**不**只显示不可读的 `project-<ULID>` store 名（项目 ULID 是根路径的单向摘要，人无法辨认）。当根路径未知（store 在记录根路径之前就被 provision）时退回显示 store 名；global store 无需推导（其名 `global` 本就可读）。底层 store 名仍是 `project-<ULID>`（FR-017）—— 这是**展示**层的事。由前端测试验证；桌面验收与其它桌面视图项一样延后到 e2e。
- **FR-017c**：用户 MUST 能为任意 memory store 设置一个**显示标签**——一个用户自选、在所有 surface 中优先于 FR-017a 的 `project_root` 推导的名字。它为来源文件夹从未被记录的 store（FR-017a 否则会退回不可读的 `project-<ULID>` 名）提供可读身份。设置空 / 纯空白标签会清除它，退回 FR-017a 的推导或回退名。该标签是**展示元数据**：不改变 store 名（FR-017）或 `project_id`，通过 `PATCH /memory_stores/{name}/label` 设置。由 HTTP 验收测试验证；桌面重命名视图与其它桌面视图项一样延后到 e2e。
- **FR-021**：只读事实视图 MUST 为「事实文件」与「其所在文件夹」两者各提供以下能力：(a) **在外部编辑器中打开**、(b) **在文件管理器 / Finder 中显示**。两者在**两个**界面上都执行真实的 OS 动作:桌面（Tauri）端经 OS opener,web 端经环回 daemon 的文件系统动作端点（spec 004 FR-039）——因为 daemon 就在用户自己的机器上（ADR-033）。没有 copy-path 回退。打开哪个编辑器由全局首选编辑器偏好决定（在 002-ui-shell 规范，本处不再重复规范）。读响应 MUST 携带这些能力所作用的绝对路径（见 FR-022）。
- **FR-022**：读响应 MUST 携带磁盘真相：事实读端点（`GET …/facts`、`GET …/facts/{id}`）MUST 包含每个事实文件的绝对 `.md` 路径及其所在文件夹的绝对路径，store 读端点（`GET …/{name}`）MUST 包含 store 的绝对磁盘目录。它们驱动 FR-021 的打开/显示能力，并让人类能定位规范化文件以带外纠正。

- **FR-053**：memory store 详情页 MUST 把 store 呈现为**四个 lane 区块**（Knowledge / Rules / Journal / Handoff）外加一个**整合 changelog** 视图，替换扁平事实列表。每个 lane 都有形状贴合的视图：**knowledge** = 事实/主题列表 + 内容；**rules** = 单一文档；**journal** = 时间排序条目（最新优先）；**handoff** = 按分支列表。所有视图都**只读**，都经**统一文件预览**渲染（无手写 `<pre>`），并为底层 lane 文件提供**在外部编辑器中打开 / 在文件管理器中显示 / 复制路径**（files-as-truth，FR-017/FR-021）。recall 仍只在 **Knowledge** lane 上操作（rules/journal/handoff/changelog 视图是只读投影，不是 recall 面）。
- **FR-054**：系统 MUST 为 UI 所需的 lane 暴露读端点：`GET /api/v1/memory_stores/{name}/journal`（时间排序的 journal 文件，最新分片优先）、`GET /api/v1/memory_stores/{name}/handoff`（按分支的 handoff 现场，每个携带其 `branch` 与 `updated_at`）、`GET /api/v1/memory_stores/{name}/consolidation-log`（organizer 的固化 changelog；不存在时为 `null`）。它们**只读**、**按 store 名寻址**（而非 cwd），且对空 store MUST 返回 **HTTP 200 加空列表 / `null`**（绝非 404）。（Rules lane 已有其读面 `GET /api/v1/memory_stores/{name}/rules`，FR-036。）
- **FR-055**：SessionStart 上下文（FR-049）MUST 额外注入一段**环境化的项目记忆索引**——即 ADR-026 推迟的"ambient loading"切片——使 agent 一开工就知道该项目记得些什么，无需主动调 `recall`。`GET /api/v1/agents/{name}/session-context` 的响应在 rules bundle 之后追加一段 **"## Project memory (via Coffer)"**，由 cwd 所属项目 store 构成：一份**仅标题的 knowledge 索引**（"Known topics"——每条 fact 的短标题，不含正文或描述）+ **少量最新 journal 行**（"Recent activity"——最新情景条目，每条一行）。它刻意是**索引而非记忆本体**——一个定位指针，告诉 agent"有什么"、需要正文时调 `recall <query>`，从而让注入很轻。该索引**只读且 best-effort**——cwd 不在 git 项目、store 为空、或任何读取错误都产出**无内容**（绝不报错；hook 绝不能阻塞 agent）——且**受预算约束**：合并后的 bundle 保持在 hook 的 ≤10k 字符契约内，索引取 rules bundle 之后的剩余额度，因此内建种子规则（FR-050）永不被截断。投递复用既有的 per-agent SessionStart hook（ADR-042 `ContextInjectionSpec`），该 hook **per-agent 显式安装、默认不装**，因此它本身就是"Coffer 是否注入"的开关：凡装了该 hook 的 agent（Claude Code、Codex、Cursor）都会收到索引；仅注入、绝不写原生文件。

**底座隔离**

- **FR-018**：检索/索引引擎（FTS5、sqlite-vec、embedding provider、converter）MUST 关在 infrastructure 内。Domain 与 application 层 MUST NOT 直接 import 索引/引擎类型；交互一律经共享检索端口。mem0、chroma、LlamaIndex MUST NOT 在任何地方被 import。

**迁移**

- **FR-019**：本分支未发布；lane 布局**没有新的 schema 迁移**（`documents`/`chunks` schema 不变 —— 只是磁盘上 lane 的位置变了）。单个迁移 MUST 删除 `memory_records` 并创建全新统一 schema。预发布构建遗留在磁盘上的旧引擎目录（chroma/LlamaIndex）原地废弃 —— 没有任何代码再读它们 —— 而非删除；旧的 mem0/chroma 文本不迁移。pre-lane 构建遗留在 store 根目录的旧每条记忆文件同样**原地废弃**（不读、不删）：lazy reindex-on-read 对账 `knowledge/` lane，于是旧根目录事实的陈旧索引行会在下一次 `recall` 时被对账清除，直到这些条目被重新记住或被 organizer 播种。磁盘上既有的 `MEMORY.md` 文件原地留存，不被读取。

### Key Entities

- **Memory Store**（kind 为 `memory` 的 resource）：每个作用域一个 store —— global store（sentinel ULID）或 per-project store（项目 ULID）。config 持有启用的检索模式、embedding 配置与 `max_fact_chars`。
- **Memory Fact**（一个 markdown 文件 = 一行 `documents`）：`id`、`name`、`description`、正文、`metadata`（`actor`、`origin_session_id`）、`path`（绝对 `.md` 路径）、`content_sha256`、`created_at`、`updated_at`。markdown 文件是真相源。读响应还额外携带所在文件夹的绝对路径，供 UI 打开/显示/复制。
- **Memory Hit**（recall 结果，不持久化）：`id`、`text`/passage、`score`、`source`、`time`。

## Success Criteria

### Measurable Outcomes

- **SC-001**：某 agent 经 `coffer__remember` 写入的事实，能在同一项目、同一会话内被另一个 agent 经 `coffer__recall` 召回，且没有任何 per-agent 副本漂移。
- **SC-003**：某作用域 200 条事实下，典型 keyword query 的 recall wall-clock 延迟 ≤ 300 ms（开发者笔记本）。
- **SC-004**：默认检索零配置离线可用（keyword + grep）；vector recall 为可选项，未配置时降级到 keyword（带标注），绝不报错。
- **SC-006**：每条 Acceptance Scenario 至少有一个 `acceptance(spec="007-memory", scenario="…")` 标记的测试覆盖。
- **SC-007**：底座隔离由 importlinter 强制：`coffer.application.*` 与 `coffer.domain.*` 下任何模块都不 import 索引引擎，且 `mem0`/`chroma`/`llama_index` 任何地方都不被 import。
- **SC-008**：`make verify` 本地与 CI 都过。

## Assumptions

- 用户在自己的机器上跑 Coffer；记忆数据留在本地。为可选的 vector recall 调用已配置的云端 embedding provider 是允许的（local-first ≠ 不调远程 API）。
- 规范化格式是每条记忆一个 markdown 文件（YAML frontmatter + 正文），位于每个作用域的 `knowledge/` lane 下；没有派生的 `MEMORY.md` 索引。
- coffer-mcp-shim 在会话握手时把其启动 cwd 传给 daemon（在支持的 agent 上实现期验证）。
- knowledge base（spec 006）与 memory 共用一套统一底座（`documents` 表按 `kind` + JSON `metadata` 区分）；二者是两个面，不是重复代码。
- 单用户并发量很小。
