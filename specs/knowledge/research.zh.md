# 研究 — 知识层

> English: [research.md](./research.md)

这一层必须回答的那些问题，以及每个问题被定成了什么。原本的研究里大部分——
mem0 与共享 store 之争、FTS5/sqlite-vec 检索栈、embedding provider 选型、由
agent 的 cwd 解析 scope、把内容投影进 agent 自己的记忆文件——描述的都是已不
存在的机制。存活下来的记在这里；2026-09-12 那次精简的推理（包括促成它的、对
本机实际安装的审计）在
[Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md)。

## 1. 写入时不跑 LLM

**问题**：写入时要不要像 mem0 那样用模型抽取事实？

**决定**：**不。** 当消费方本身就是一个能判断什么值得记、并能自己写出干净笔记
的模型时，写入时跑 LLM 就是摩擦。mem0 默认的 `llm_provider="none"` 让它的
`add_memory` 直接返回 503——这个功能开箱即不可用。一次写入就是一次普通的文件写。
mem0、chroma、LlamaIndex 都不在代码库里，并由一条 importlinter 契约封死，防止
它们回来。

依然成立。模型触及知识的唯一场合是 tidy：显式触发、有界、归档它替换掉的每个
版本，且默认关闭。

## 2. 一个共享 store，而不是逐 agent 的孤岛

**问题**：agent 的知识存在哪？

**决定**：存在**一个所有 agent 共享的 store** 里，而不是各自的记忆目录里。
逐 agent 的私有孤岛会漂移：同一条项目事实会被抄进 Claude 的记忆目录、Codex 的
memories 等等，然后各自跑偏。Coffer 只留一份，所有 agent 经 MCP 读写它。

依然成立，而且精简还强化了它：中间没有索引之后，人的编辑器和 agent 的 `write`
触及的是同一批字节。

## 3. 带 YAML frontmatter 的单文件 Markdown 就是事实

**问题**：磁盘格式是什么？

**决定**：一条笔记一个 Markdown 文件，带一个 `---` 围栏的 YAML frontmatter 块
承载元数据。

这个格式熬过了每一次重设计；字段表没有。frontmatter 现在恰好只有 `title`、
`description`、`actor`、`created_at`、`updated_at`——没有 `id`，因为路径就是
身份，也没有任何描述索引、lane 或外部来源的字段。所有派生索引也随之消失：
`MEMORY.md` 在 files-as-truth 重设计时移除，`INDEX.md` 在 2026-09-11 的两条 lane
重设计时移除，数据库索引本身在 2026-09-12 移除。取代它们的目录是在调用时遍历
目录生成的，因此不存在第二份需要保持同步的副本。

## 4. 共享只走 MCP

**问题**：这一个 store 怎么抵达每个 agent？

**决定**：经 Coffer 的 MCP 网关，此外别无他途。更早的设计还会把规范内容投影进
agent 的原生位置——给 Claude Code 一个目录符号链接，给 Codex 在 `AGENTS.md` 里
写一个带标记围栏的块——那一半已被移除
（[Memory via MCP](../../docs/decisions/memory-via-mcp-not-native-projection.md)）：
Coffer 绝不写入 agent 自己的记忆文件，不禁用任何东西，也不往会话里注入任何东西。

**这留下的开放问题是投递。** 知识只有在 agent 主动伸手时才会抵达会话，而
2026-09-12 的审计发现：工具自己的描述并不能让模型记住这个工具存在——一个月里
每一次知识调用都发生在某个 agent 建语料的那一天。尝试的答案是**投递一个 skill**
——Coffer 渲染一个描述这一层的 skill，经那条已经把十五个 `coffer-*` skill 送进
每个受管 agent 的通道投递，它的名字与描述从此原生地待在上下文里。这是一个有
证据支撑的假设，而不是被证明的修复；调用日志会在一周日常工作内给出答案。

## 5. 检索：为什么干脆不要索引

**问题**：拿什么取代 FTS5 + sqlite-vec？

**决定**：**一份生成的目录加 ripgrep，别无其它。**

索引能提供而 ripgrep 不能的唯一能力是概念性召回——用*鉴权*去命中一篇写着*认证*
的文档。那需要 embedding，而本机安装上 embedding 从未被配置过（`embedding_config`
是空表）。去掉 embedding 之后，FTS5 相对 ripgrep 多出来的只是 BM25 排序和分块
粒度，而这两件事 agent 自己都会做：它读命中行、判断哪个文件相关，然后反正要把
整个文件读一遍。在本机语料上实测（51 篇、1.4 MB），一次 ripgrep 查询给出与 FTS5
相同的答案集，耗时 **27 ms**，且不需要分词器就能命中中文。

这里没有好的中间态：要么上完整的语义栈，要么不要索引。在这个区间里，只有 FTS5
是性价比最差的一档。当语料涨到目录塞不进上下文时——每条约 40 tokens，所以几百篇
很从容——答案是一个为那个需求而建的真正语义栈，而不是重新启用那个从未被打开过
的部件。

## 6. 摄入：文件系统

**问题**：一份文档怎么进来？

**决定**：由人把一个 Markdown 文件放进目录。没有上传端点，也没有格式转换。
在此之前的任意格式流水线经 MarkItDown 转换、把原件留在 `.raw/` lane 里以便
再转换、并追踪外部来源；而在本机安装上，**50 篇里 50 篇**都带着
`converter: passthrough`，那 50 个 `.raw/` 文件与转换结果逐字节相同。手工添加
知识的代价是复制一个文件，比任何上传界面都便宜。

## 7. 边界：只有一种，而且它存在就是为了被授权

**问题**：知识靠什么隔开？

**决定**：靠 **collection**，别无其它。一个 collection 是人有意创建的顶层文件夹，
而它是 Resource，正是为了让框架的 per-agent scope 能授权它
（[Per-Agent Resource Scope](../../docs/decisions/per-agent-resource-scope.md)）。

更早的 `global` ÷ `project-<ULID>` ÷ collection 这条轴想说的是「这份知识是关于
什么的」，而那是内容的属性，却为此付了物理结构的全额代价：migration、被只读
检索顺手开通出来的空壳、以及查询时的跨边界融合。检索必须靠 reciprocal rank
横跨 scope 融合才有用，这本身就是破绽——隔离从来就不是重点。现在没有任何东西
从 cwd 推导，没有任何东西自动开通，agent 的读取覆盖它被授权的每一个 collection。

授权只在 MCP 工具面执行。握有 shell 或文件读取工具的 agent 可以直接读
`~/.coffer/knowledge/` 下的任何东西：scope 防的是误召回，不是有意访问，系统
如实这么讲，而不是暗示一种它并不提供的隔离。

## 8. 原子性

文件写入走同目录临时文件再 `replace`，所以读者永远看不到写到一半的文件，崩溃
也永远不会把文件截断。这是当初为共享文件助手一次性定下的，此后未变；那个助手
本身就是记录。

## 9. 这一层刻意不做的事

- 读取时的 rerank、HyDE、multi-query 或 LLM 综述——综述由 agent 做。
- 把某个专有的 agent 记忆格式反解回规范格式（业界未解；改为经 MCP 共享来规避）。
- 监听文件系统。没有任何东西是派生的，也就没有任何东西需要失效。
- 跨机器收敛（章程约束；导出、导入与单向备份属于 vault-export-import spec）。
- 在文件自己的 `title` 与 `description` 之外再做分类。
