# 检索栈 —— markdown 文件即事实源，SQLite FTS5 + sqlite-vec，可配置 embedding

> English: [files-as-truth-sqlite-retrieval.md](./files-as-truth-sqlite-retrieval.md)

**Status**: Accepted
**Date**: 2026-06-09（2026-09-11 修订；见修订历史）
**Deciders**: Yuxing Wu
**Supersedes**: LlamaIndex RAG 引擎与 mem0 memory 引擎这两项决策 —— 两份 ADR 均已作为废弃文档移除
**Related**: spec `knowledge`（知识层 spec）、[Layer-First Code Layout](code-layout-layer-first.md)、[Everything Is a Resource Kind](everything-is-a-resource-kind.md)、[One Shared Knowledge Store](agent-native-shared-memory.md)

## Context

`knowledge_base`（跑 LlamaIndex RAG 引擎）与 `memory`（跑 mem0 memory 引擎）的
第一版都以「一个你通过 MCP 查询的 store」形态交付，两者近乎对称，各自背着一套
重型引擎：

- **KB** 通过一个 `DispatchingKnowledgeBaseStore` 在手搓的关键词后端与
  LlamaIndex 语义后端之间路由。LlamaIndex 在原始文档旁边另外持久化它自己的
  落盘索引。
- **Memory** 用 `mem0ai`，写入时必须调一个 LLM 做事实抽取。默认
  `llm_provider="none"` 会让 `add_memory` 返回 503，且文本被双写到 SQLite 与
  chroma 两处。

两个 kind 一旦同时投入使用，三个结构性问题就浮现出来：

1. **双事实源。** mem0/chroma 把事实文本存进 chroma *又*存进 SQLite；
   LlamaIndex 存一份派生索引，会与原始文档悄悄分叉。没有一份权威副本可供备份、
   diff 或据以重建。
2. **引擎泛滥。** 两套 RAG/memory 框架（LlamaIndex、mem0）、一个向量 DB
   （chroma）、一个手搓关键词 store，再加一个 dispatcher —— 四个重型零件外加
   胶水 —— 而它本质上只是「在 markdown 上做检索」。
3. **memory 写入时调 LLM 是摩擦**，而它的消费方本身就是一个能自己决定该记什么、
   并写出干净事实的 LLM。

已退役的 LlamaIndex 决策明确把 `sqlite-vec + FTS5` 搁置（「等规模或零依赖策略
真的要求时再回头评估」），mem0 那份沿用了同一套理由。本次重设计恰恰回到这一
点：可配置 embedding 的需求与 files-as-truth 的需求叠加在一起，改变了这道算术
题的结果。

## Decision

**砍掉 LlamaIndex、mem0、chroma、手搓关键词 store 与 dispatcher。让落盘的
markdown 文件成为唯一事实源，所有派生的索引/元数据经由 SQLite FTS5
（关键词/BM25）与 sqlite-vec（向量）统一保存在 `coffer.db` 里。embedding 来自
一个 OpenAI 兼容、用户可配置的 provider。任意格式的导入都走一个可插拔的
`MarkdownConverter` 端口（默认 MarkItDown）。**

具体形态：

- **文件即事实，SQLite 是可重建索引。** KB 文档以归一化的
  `docs/<doc-id>.md`（外加 `raw/<doc-id>.<ext>` 作为出处）落盘；memory 事实以
  逐条 `<slug>.md` + 一份重新生成的 `MEMORY.md` 落盘。SQLite 里的一切
  （`documents`、`chunks`、`documents_fts`、`vec_chunks`）都能由
  `coffer reindex` 从文件重建。这从根上消除了双事实源 bug。
- **三种检索模式**，全部跑在同一份文件/索引上：
  - `grep` —— ripgrep 扫 `docs/`（直接扫原始文件，零索引，语言无关）。
  - `keyword` —— SQLite FTS5 `MATCH … ORDER BY bm25()`。常规 FTS5 表把 chunk
    文本存一份在索引内部（仍可由 markdown 文件重建；文件始终是事实源）。
  - `vector` —— sqlite-vec 对 chunk embedding 做 KNN。
  - 可选 hybrid，用 reciprocal rank fusion 融合。默认检索是
    `keyword`+`grep`（零配置、离线）。vector 为 opt-in；若请求了 vector 但
    embedding 未配置，检索回退到 keyword 并在响应中标注 —— 永不阻塞。
- **可配置、OpenAI 兼容的 embedding**（DevPilot 风格：一个 `AsyncOpenAI`
  客户端，`base_url` 可替换）。逐语料配置：`embedding_provider`、
  `embedding_model`、`embedding_base_url`、`embedding_credential_ref`
  （keychain ref，绝不明文）。同一个 `.embeddings.create` 调用即可对接
  OpenAI / OpenRouter / Voyage / Jina / Gemini / Azure / DashScope
  以及本地 Ollama / LM Studio，另有一个可选的进程内 `local` provider
  （fastembed）做零服务端、离线 embedding。embedding 模型是**可变的** ——
  改它会对语料重新 embed（文件即事实），因此没有不可变锁。*形态已被取代、
  实质未变：* 现在它是一份全安装唯一的配置，指名一个 LLM 连接加它的一个
  `embedding` modality 模型（spec knowledge FR-077），端点与密钥只在
  Connections 页面填一次，不再逐语料重述。
- **可插拔的 `MarkdownConverter` 端口**（`can_handle(format)` +
  `convert(bytes) -> (markdown, metadata)`），限定在 infrastructure 内，按格式
  分发。默认引擎是 **MarkItDown**（覆盖面广、面向 LLM、MIT）；可按格式接上
  Docling / pandoc。因为保留了 `raw/`，markdown 日后可用更好的 converter 重新
  生成。
- **一个 store，两副面孔。** 单一的 `knowledge` 检索引擎同时支撑 KB 面
  （任意格式 → markdown，agent 只读）与 memory 面（逐条事实 markdown，跨 agent
  共享）。已退役的 LlamaIndex 决策对 `llama_index*`、mem0 那份对 `mem0*` 施加的
  import 隔离契约，现在被重新指向新的第三方库（sqlite-vec loader、converter
  库、OpenAI 客户端），
  使 `application/` 与 `domain/` 永不直接 import 它们。

## Consequences

**正面**

- **唯一事实源。** markdown 文件是权威；SQLite 完全可重建。备份就是一棵目录树；
  损坏恢复就是 `reindex`；用户可用普通工具 diff/grep/编辑 memory 与 KB 内容。
- **一个 store，更少依赖。** 一切都在 `coffer.db` 里（FTS5 + sqlite-vec）；
  chroma、LlamaIndex 的 persist 层、mem0 的向量路径全部退出 lockfile。关键词
  路径从手搓的词频 JSON 扫描变成 BM25，dispatcher 消失。
- **写 memory 不再需要 LLM。** agent 直接写一条干净事实；默认安装零外发调用。
  embedding（以及由此产生的任何外发调用）严格按语料 opt-in。
- **不靠框架也能配 embedding。** 一个薄薄的 OpenAI 兼容客户端覆盖了每一个主流
  provider 与本地服务端，这正是先前用 LlamaIndex 的 embedding adapter 想要的那
  份灵活性 —— 却不必背框架。
- **廉价的可变性。** 因为文件即事实，改 chunk 参数或 embedding 模型只是一次
  re-chunk/re-embed，而非从一份有损索引里重建 store。这修掉了 mem0 引擎的
  「config 创建后不可变」摩擦。

**负面**

- **比已退役的 LlamaIndex 与 mem0 两份决策接受了更多自家编排。** 我们现在自己
  持有 chunker、FTS5/vec 胶水、检索融合、converter 分发 —— 正是那两份决策当初
  花钱让 LlamaIndex/mem0 替我们省掉的那约 200–300 LOC。我们接受这点：面很小、概念是
  我们自己的，且没有框架变更要追。
- **sqlite-vec 是原生扩展。** 它必须在 PyInstaller 包里于 macOS arm64 与 Linux
  上正常加载（[PyInstaller Distribution](distribution-pyinstaller.md)）；
  打包/加载是一个待验证项。
- **converter 质量现在归我们管。** MarkItDown 的 PDF/Docx 保真度、OCR，以及
  MarkItDown-vs-Docling 的取舍都得我们逐格式验证。保留 `raw/` + 可重新转换是其
  缓解手段。
- **「主流即简历信号」更弱了。** 已退役的 LlamaIndex 与 mem0 两份决策看重用知名
  框架带来的可读性。SQLite FTS5 + sqlite-vec 对读者而言可以说*更*易读（它就是
  SQLite），但丢掉了
  「我用过 LlamaIndex/mem0」这个信号。我们判断架构上的收益占主导。

## Alternatives Considered

**KB 继续用 LlamaIndex。** 留它最强的理由是它的 embedding adapter
与 loader。但可配置 embedding 的需求由一个薄薄的 OpenAI 兼容客户端更直接地满足
（换一个 `base_url` 即可触达每个 provider），而 LlamaIndex 持久化的索引会主动
与 files-as-truth 打架：它想自己持有一份会与 markdown 分叉的派生 store。被否：
单一事实源的要求与一个坚持自己持有索引的框架不相容，而我们从它身上唯一想要的
东西（embedding）只是一个 50 行的客户端。

**memory 继续用 mem0。** mem0 的价值在于写入时做事实抽取 + dedup，
这预设了一个我们明确要移除的 LLM 调用：agent *就是*那个 LLM，自己写事实。
mem0 还会双写到 chroma —— 正是我们要消除的那个 bug。被否 —— 框架的核心特性恰是
我们要移除的摩擦。

**保留 chroma 作向量 store、FTS5 作关键词。** 可行，但它在 SQLite 之外保留了
第二个数据存储（也是向量的第二个事实源）。sqlite-vec 把向量放进与 FTS5、
documents 表、审计日志同一个 `coffer.db` —— 一个文件备份、一个写入者、一条重建
路径。因 store 统一性而被否：一旦向量可从文件重建，第二个嵌入式 DB 就一无所得。

**保留手搓关键词 store（当前 KB 关键词后端）不动。** 它是一次词频 JSON 扫描 ——
更慢、无 BM25、还要维护一个自家 ranker。FTS5 内建于 SQLite，白送 `bm25()`，且
能删代码。被否；没理由保留一个对 SQLite 自带能力更差的再实现。

**files-as-truth 但不要 SQLite 索引（仅 grep）。** 零基础设施很诱人，且 grep
仍是一等模式。但关键词排序（BM25）与向量召回都需要索引，而在每次查询时从文件
重建索引并不可扩展。作为*唯一*模式被否；作为三种模式之一保留。

## 隔离 / 锁定缓解汇总

已退役的 LlamaIndex 与 mem0 两份决策那套隔离纪律照旧适用，只是重新指向：`MarkdownConverter` 端口与
OpenAI 兼容的 embedding 客户端是唯二触及第三方库的 infrastructure 接缝，藏在
kind 自己持有的端口背后，测试用 fake，importlinter 契约保持 `application/` 与
`domain/` 干净。换 converter、换 embedding provider，乃至换向量扩展，都是一次
单 adapter 改动。关键在于：因为**文件即事实源**，最深的那种锁定 —— 一份你出不来
的私有索引格式 —— 已经不存在了：任何引擎都能从 markdown 重建出来。

## 修订历史

- **2026-06-09** —— 初版决定：markdown 文件是唯一事实源；SQLite FTS5 + sqlite-vec
  持有一份完全可重建的索引；embedding 来自可配置的 OpenAI 兼容 provider；导入走
  可插拔的 `MarkdownConverter` 端口。一个基底、**两副面孔** —— 一个
  `knowledge_base` kind 与一个 `memory` kind。
- **2026-09-10** —— **两副面孔合而为一。** `memory` 与 `knowledge_base` 合并为
  单一资源 kind `knowledge`。基底一动未动，因为本来就没有什么要动：
  `documents`、`chunks`、`documents_fts` 与 `vec_chunks` 从本 ADR 落地那天起就是
  共享的，`infrastructure/knowledge/paths.py` 也早已同时持有两套落盘布局。分成
  两份的只有门面 —— 两套 MCP 工具、两个 REST router、两个 CLI 命令组、两个页面
  —— 而它逼着调用方在能搜之前先猜「这条事实属于哪副面孔」。所以这次合并不是立场
  的改变，而是把这个立场贯彻到底。它对上文的修订：
  - **存储根与 lane。** 一个根 `~/.coffer/knowledge/<scope>/`，lane 为
    `knowledge/`（agent 写下的条目）、`inbox/`（导入的文档）、`rules/`、
    `handoff/`、`superseded/`，外加一个隐藏的 `.raw/` 存放导入原件。因此上文
    Decision 里那对 `docs/<doc-id>.md` + `raw/<doc-id>.<ext>` 现在是
    `<scope>/inbox/<doc-id>.md` + `<scope>/.raw/<doc-id>.<ext>`，逐条 memory
    markdown 则成为 `<scope>/knowledge/` 下的一条 entry。出处保留与可重新转换
    不变；`.raw/` 之所以隐藏，只是为了让 ripgrep 不再对每份导入文档返回两条命中
    —— 转换后的 Markdown 与它的原件。
  - **scope 取代 store 名。** scope 由资源名读出：`global` 与
    `project-<ULID>`（由 cwd 的 git 根解析）在首次使用时自动开通；其余任何名字
    都是用户有意创建的集合，绝不自动开通 —— 因为从一个拼写错误里悄悄造出一个
    scope，比报错更糟。
  - **落库的 lane 判别列。** `documents.lane`（`knowledge` | `inbox`，
    migration `0053`）记录一行归哪个写入方所有，因为两条 lane 的路径在同一个根
    下确实会重叠。计数按 lane 分开；而**检索有意横跨两条 lane** —— 一份索引、
    一次查询 —— 这正是合并的全部意义。
  - **逐语料 embedding 配置消失。** 逐 scope 的 `KnowledgeConfig` 完全不带
    embedding 字段；到合并时，两个旧 config 的这些字段都已无人读取。embedding
    改由安装级配置解析，某个 scope 是否启用向量检索，纯粹由它是否列出该检索
    mode 决定。上文关于可变性的论证不受影响 —— 文件仍是事实，重新 embed 仍然
    只是一次重新派生。
- **2026-09-10，关于清空索引。** migration `0051` 在合并两个 kind 的同时
  **清空了派生索引**。这是本 ADR 立场的落实，而非对它的例外。`memory:global` 与
  `knowledge_base:global` 同时存在，而 `resources` 以 `(kind, name)` 为键，两边
  都转换会在 `knowledge:global` 上撞车，任何自动改名都只是猜测。代价也很小：
  `documents` 里每一行都是 `kind='memory'` —— 一份指向 journal lane 的 memory
  侧索引，而那条 lane 已在此前的改动中移除 —— 所以索引早就指着不存在的文件，
  而知识库那副面孔更是从未存过一份文档。**文件即事实，SQLite 是可重建索引**：
  清掉一份文件能重建的索引不会丢失任何权威内容，因为索引从来就不是事实源。
  重新累积靠显式的 `coffer__write` 与文件导入。
- **2026-09-11** —— **两条 lane。** 一个 scope 的存储 lane 收敛为人真正会区分的
  两类材料：谁写下的，和谁上传的。files-as-truth 一动未动；动的只是这些文件被
  分进几个盒子。它对上文的修订：
  - **lane 布局。** 一个 scope 就是 `~/.coffer/knowledge/<scope>/`，下有 `notes/`
    （agent 或用户写下的内容 —— `coffer__write` 直接落这里）与 `docs/`（上传的
    文档，已归一为 markdown），外加一个隐藏的 `.history/` 与隐藏的 `.raw/`
    （存放上传的原件）。因此上文 Decision 里那对「`docs/<doc-id>.md` + 原件」重新
    字面成立：`<scope>/docs/<doc-id>.md` + `<scope>/.raw/<doc-id>.<ext>`，逐条
    markdown 则是 `<scope>/notes/` 下的一条 note。2026-09-10 那条列出的 lane ——
    `knowledge/` 及其 `knowledge/inbox/` 梯度、`rules/`、`handoff/`、
    `superseded/` —— 全部删除；本 ADR 最初称作 `MEMORY.md`、后来叫
    `knowledge/INDEX.md` 的那份重新生成的索引文件同样删除：不再有任何东西去生成
    一个索引文件。`superseded/` 原本承担的角色现由 `.history/` 承担 ——
    它存的是整理覆盖前的旧版本，而非墓碑。`.history/` 加点前缀的理由与 `.raw/`
    相同 —— ripgrep 默认跳过隐藏项，因此 `coffer__grep` 永远不会在正文旁边又返回
    一个归档旧版。
  - **lane 判别列的取值。** `documents.lane` 改为 `notes` | `docs`。计数仍按 lane
    分开，检索仍横跨两条 lane。这次迁移按明确要求做破坏性处理 —— 不设缓冲区 ——
    且不留 load-time 垫片：数据在库里改干净，兼容分支在同一次改动里删掉。这正是
    本 ADR 立场的再一次落实：文件即事实，一份文件能重建的索引从来就不是被冒险的
    那个东西。
  - **针对 `notes/` 的定期整理。** 一趟有界的 agentic 流程合并重复的 note，并把它们
    重写成主题文档。任何覆盖或合并之前，先把旧版本复制进 `.history/`，因此
    无人值守的重写始终可以捞回来。它由一个形状照抄现有 `RetentionWorker` 的后台
    worker 驱动 —— 开机跑一趟补齐，之后按间隔执行 —— 未配置 internal model 时
    空转，也可手动触发。每趟整理写进 Coffer 已有的审计日志；per-scope 的
    `consolidation-log.md` 删除且不设替代物。整理重写的是文件，而文件仍是记录；
    索引照旧由它们重新派生。
  - **检索不受影响。** FTS5 + `bm25()`、sqlite-vec、各检索 mode 及其融合、安装级
    embedding 与 `MarkdownConverter` 端口，全部照当初决定原样成立。创建集合对话框
    去掉向量检索开关，去掉的是一个抛给用户的**提问**，不是能力本身：新建集合照旧
    带 keyword + grep + vector。
