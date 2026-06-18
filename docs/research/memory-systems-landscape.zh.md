# 记忆系统全景 —— 主流 AI Agent 记忆是怎么实现的

> English: [memory-systems-landscape.md](./memory-systems-landscape.md)

**类型**:调研笔记(竞品横向)
**日期**:2026-06-17
**目的**:把 Coffer 的记忆设计([spec 007](../../specs/007-memory/spec.md)、[ADR-012](../decisions/ADR-012-files-as-truth-sqlite-retrieval.md)、[ADR-013](../decisions/ADR-013-agent-native-shared-memory.md))放到业界做法里对照,判断 Coffer 的取舍是否站得住,以及它"共享一份记忆 + 投射进各自原生位置"的新颖性主张是否成立。
**方法**:`deep-research` 工作流,三轮。**第一轮**(广义全景)—— 5 角度、23 源、核实 25 条(确认 23 / 驳回 2)。**第二轮**(聚焦新颖性)—— claude-mem **已投票核实**;Letta / agentmemory / Zep 抽取到了但被限流。**第三轮**(复核被限流的三者)—— Letta(18 条 3-0 全票)与 `jayzeng/agentmemory`(6 条全票)**已投票核实**;`rohitg00/agentmemory` 与 Zep/Graphiti 本轮**未被投票覆盖**(被 budget 丢弃),停在第二轮的一手来源级别。下文置信度标注带上这些区分。

---

## 一句话结论

业界干净地分成**两大阵营**,而 Coffer 是有意为之的**混合体**:

- **A 阵营 —— 框架/库类记忆服务**(mem0、Letta、Zep/Graphiti、Cognee、LangMem):**向量库(或知识图谱)是 source of truth**;**写入路径跑 LLM**,做事实抽取 + 去重/冲突消解(add / update / delete / noop);检索是**向量语义检索**;作用域按**标识符命名空间**(`user_id` / `agent_id` / `run_id` / `block_id`);人工审阅**弱**(基本全自动)。
- **B 阵营 —— 产品内置文件式记忆**(Claude Code、Cursor、Windsurf、ChatGPT):**本地纯文件(markdown)是 source of truth**,没有向量库/SQL;写入路径是**直写**(用户手写,或 agent 写 plain notes —— **没有抽取/去重流水线**);检索是**加载文件/遍历目录,不是语义检索**;作用域是**显式文件分层**(managed-policy > user > project > local);人工审阅**强**(文件可编辑、可 git diff)。

**Coffer 的位置**:Coffer 取了 B 阵营的脊梁——_文件即真相 + 写时不用 LLM + 人可纠错_,再栓上 **A 阵营级别的检索**(FTS5/BM25 + sqlite-vec 语义检索——这恰恰是 B 阵营*缺*的),并加上**一份跨 agent 共享的记忆、投射进每个 agent 的原生位置**。

**新颖性裁决(已拍实 —— high)。** 把这个主张拆成三块,因为它们的新颖度完全不同:

1. _**多个 agent 共享同一份 store**_ —— **不新颖。** Letta 的 shared memory blocks、官方 MCP memory server、mem0 平台、claude-mem、agentmemory 都暴露一个供多个 agent 读写的共享中心库。
2. _**把记忆投射进一个原生文件**_ —— **存在,但只是单目标(只 Claude)。** claude-mem 自动生成一个通用的 `CLAUDE.md` 时间线文件;`rohitg00/agentmemory` 据称有一个单目标的 "Claude bridge"。两者都不会 fan-out 到第二个 agent 的原生格式。
3. _**多目标原生 fan-out**_ —— 一份 canonical 库投射进*每个异构 agent 各自的原生记忆位置*(格式吻合处 symlink、不吻合处托管块,并关掉该 agent 自带记忆以防发散)—— **三轮调研下来哪都没找到。**

所以 Coffer 的新颖性精确地收窄到第 3 块:**多目标原生投射 fan-out** —— *不是*共享(很常见),*也不是*原生投射本身(单目标先例存在)。_置信度:**high。** 三个最强候选先例现已全部投票核实为中心库 / 注入 / 拉取模型,而非 fan-out:**claude-mem**(第二轮)、**Letta**(第三轮 18 条全票)、**`jayzeng/agentmemory`**(第三轮 6 条全票)。剩下两个系统 —— `rohitg00/agentmemory` 与 Zep/Graphiti —— 第三轮未被投票覆盖(注意事项 1),但都低风险:只 Claude 的桥仍是单目标,Zep 架构上就是个中心 KG 服务(与 fan-out 正相反)。_

> **一个很说明问题的数据点。** Letta —— 一个成熟玩家 —— 自家出的 Claude Code 集成(`claude-subconscious`)**刻意走 stdout 注入上下文、明确"never writes to `CLAUDE.md`"**,甚至主动把 `CLAUDE.md` 里遗留的 `<letta>` 内容清掉。业界默认是*运行时注入*,"写进用户的原生文件"是别人考虑过、然后**避开**的路。这让 Coffer 的投射确实独特 —— 但也是一面需要想清楚的黄旗(见"把业界格局映回 Coffer"第 4 点)。

---

## 两大阵营,逐维度拆解

### 1. 存储模型 —— 谁是 source of truth

| 阵营            | source of truth                                                                                                                                                                                            | 备注                                                                                                                                      |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| **A(框架)**     | **向量库**(mem0 基础版:dense embeddings);变体用**图库**(Mem0^g:Neo4j;Zep/Graphiti:时序 KG);Letta 用**关系库**(blocks 存 Postgres/pgvector,运行时编译进 prompt)。                                           | 官方 **MCP memory server** 是例外:单一本地 **JSONL 知识图谱文件**(`memory.jsonl`),完全没有向量/SQL。                                      |
| **B(产品内置)** | **本地纯 markdown 文件**,无向量/SQL。Claude Code:`CLAUDE.md` / `CLAUDE.local.md` + auto-memory(`MEMORY.md` + topic 文件)。Cursor:`.cursor/rules/*.mdc`。Windsurf Cascade:`~/.codeium/windsurf/memories/`。 | 这些 agent 的所有向量/SQLite 增强(MemSearch、claude-mem、Vector Memory MCP)都明确是*叠加在原生文件之上*的第三方层——反证原生文件才是基线。 |

_置信度:high(3-0)。_

### 2. 写入路径 —— LLM 抽取+去重,还是直写

- **A 阵营:写时用 LLM。** mem0 的 add 流水线:(a) 从一对消息 + 滚动会话摘要 + recency window 里抽取 salient facts,然后 (b) 对每条 fact 检索 top-_s_ 语义近似的已有记忆,经 function-call 让 LLM 把操作分类为 **ADD / UPDATE / DELETE / NOOP**——"latest truth wins"。这受 **`infer=True`(默认)控制**;若 `infer=False` 则原样逐字存,**重复会累积**。_业界注脚:_ mem0 issue #4896 显示在语义相近但矛盾的事实上,去重会退化为 MD5 hash 匹配、两条都 ADD——所以即便 LLM 路径在边缘场景也不 robust。
- **B 阵营:直写,无抽取/去重。** 两条子路径:**用户手写**规则(`CLAUDE.md`、Cursor rules、Windsurf rules——无 LLM)和 **agent 自动写**的 auto-memory(Claude Code 写 "notes …… 依据信息是否对未来对话有用";Cascade "遇到它认为有用的上下文就自动生成并存储记忆")。**两条自动路径写的都是 plain markdown notes——没有 embedding/去重流水线。** MCP memory server 同样只做**精确字符串去重**(`create_entities` / `add_observations` 用 `===`/`includes`),零 LLM。
- **ChatGPT** 是产品层混合体:"Saved memories"(用户主动请求记的事实,经 bio 工具基本逐字存)+ "reference chat history"(LLM 从过往对话构建隐式画像,非逐字),并有自动 LLM curation,按 recency/话题频率权衡,以"减少陈旧或矛盾的 saved memory"。

_置信度:high(3-0)证明机制存在;但"用户写 vs LLM 抽取"的二分有灰色地带——两条断言"干净二分"的 claim 被驳回(ChatGPT saved memory 也能由 LLM 自动加;Cursor rules 也能后台生成)。_

### 3. 检索方式

- **A 阵营:向量/图语义检索。** mem0 基础版 = dense-embedding 相似;Mem0^g 与 Zep/Graphiti 加实体中心图遍历 + 语义匹配;Letta 按 `block_id` 把 block 编译进 prompt。即便 mem0 较新的 v3 hybrid(BM25 + entity)也只把它们当 **re-rank booster**——向量仍是唯一的候选生成路径。
- **B 阵营:无语义检索。** Claude Code 启动时**全量加载**作用域内 `CLAUDE.md`,子目录文件**按需**加载,auto-memory 只加载 `MEMORY.md` 的**前 200 行 / 25 KB**(其余按需读)。MCP server 做**大小写不敏感子串 + 精确名**查找(`search_nodes` / `open_nodes`)。**B 阵营原生路径里哪都没有 embedding。**

_置信度:high(3-0)。_

### 4. 作用域与命名空间

- **A 阵营:** 标识符命名空间——mem0 的 `user_id` / `agent_id` / `run_id`(+ 可选 metadata 过滤);Letta 用 `block_id` attach 一个共享 block。
- **B 阵营(分层最显式):** Claude Code 按"最宽 → 最具体"加载:**managed-policy**(org,全员)> **user**(`~/.claude/CLAUDE.md`,跨所有项目)> **project**(`./CLAUDE.md`,经 git 团队共享)> **local**(`CLAUDE.local.md`,gitignore)。Cursor:Project / User / Team rules。Windsurf:global / workspace / system。

_置信度:high(3-0)。_

### 5. 跨 agent 共享与原生投射 —— **对 Coffer 最关键的对照**

- **A 阵营框架**是**通过 API/MCP 查询的中心库**。mem0 的*论文*不讨论跨 agent 共享;mem0 的*平台*支持 `agent_id` 范围和共享实例——**但它不把记忆投射回任何 agent 的原生文件。**
- **MCP memory server** 是*单一共享*的 JSONL 图——但"共享"的意思是*一个中心文件、所有 agent 通过同一工具读*,**不是**"写进每个 agent 自己的原生记忆位置"。
- **B 阵营产品内置**系统各自**只读写自己的原生文件**、**彼此隔离**——Claude Code、Cursor、Windsurf 之间**完全没有跨 agent 共享层**。
- **claude-mem(第二轮已投票核实)。** 它是个**中心库**(SQLite + FTS5 + 可选 Chroma),靠 Claude Code 的 **lifecycle hooks** + worker HTTP 服务(`:37777`)+ MCP 工具注入上下文。它*确实*多 agent——但对每个 agent 走的是**同一套 hook+中心 API**,即一个 agent 们*去读*的中心库,**不是**把每个 agent 各自的原生记忆文件写出来的 fan-out。它唯一写原生文件的动作,是自动生成一个通用的 `CLAUDE.md` 活动时间线。
- **Letta(第三轮已投票核实,18 条全票)。** Letta 的 **shared memory blocks** 让多个 agent 共享一个 block(按 `block_id` attach;一处更新全体可见)——**但只是 Letta _自己的_ API 创建的 agent**,block 持久化在**中心 DB**(Postgres/pgvector,`BlocksAgents`/`BlockHistory` pivot 表),_运行时编译进 prompt 的 XML_,从不写外部文件。Letta 文档甚至直接对比:_"Unlike Claude Code's `CLAUDE.md` approach, Letta blocks are not written to external files."_ 它自家的 Claude Code 集成 `claude-subconscious` **明确从不写 `CLAUDE.md`**(stdout 注入);MemFS 是 Letta 单一内部目录;Context Repositories 只把外部历史*单向读入*做 bootstrap(与 Coffer 向外扇出**正相反**)。→ 是*共享记忆*先例,**绝不**是原生投射先例。
- **agentmemory(`jayzeng` 第三轮已投票核实;`rohitg00` 仅第二轮)。** `jayzeng/agentmemory` 是**中心 canonical markdown 库**(`~/.agent-memory/`)+ 给每个 agent 装*相同的* `SKILL.md` shim、调 `agent-memory` CLI **从中心拉取**。它的 `MEMORY.md` 是工具*自己的* wiki,README 明说它 _"complements static files like `CLAUDE.md`, `AGENTS.md`, `.cursorrules`"_ —— 即**刻意不写入它们**。pull-from-central,与原生扇出正相反。`rohitg00/agentmemory`(第二轮抽取,未复核)是中心服务器(MCP/REST/WebSocket),其唯一的原生桥是**单目标(只 Claude)**。
- **Zep/Graphiti(第二轮 / 背景;第三轮未复核)。** 一个时序知识图谱,作为中心库经 MCP/API 提供。中心库查询模型;无原生文件投射。

**裁决:** *共享库*这半边有很多先例;*单目标原生投射*这半边有两个(claude-mem 的通用 `CLAUDE.md`、`rohitg00` 的 Claude bridge);而**多目标异构原生 fan-out** 这半边三轮下来**一个都没有**。_置信度:high(三个最强候选 —— claude-mem、Letta、`jayzeng/agentmemory` —— 全部投票核实为非 fan-out;两个未复核的尾巴低风险)。_

### 6. 遗忘 / 衰减 / 去重 / 冲突消解

- **A 阵营:写时主动做**——mem0 DELETE 掉被矛盾的记忆、UPDATE 增补、"latest truth wins";ChatGPT 自动 curation 减少陈旧/矛盾条目。全部**LLM 驱动**(且据 #4896 **并不完美**)。
- **B 阵营:基本没有,或只做精确去重**——MCP 只做精确字符串去重;Claude Code / Cursor / Windsurf 靠**人工编辑/删除**来防膨胀、重复、矛盾。Claude Code "无论多长"都全量加载 `CLAUDE.md`,所以**没有自动裁剪**——膨胀是个人工问题。

_置信度:medium(机制存在性 3-0;"文件阵营靠人工"是从"无自动去重"+"文件可编辑"综合推断)。_

### 7. 人工审阅与可纠错性

- **B 阵营:结构性地强**——人类可读的 markdown/JSONL,可 git diff,可随时编辑/删除(Claude Code、Cursor、Windsurf、MCP)。
- **A 阵营:弱**——mem0 论文与 MCP server 都没有 human-in-the-loop 审阅,记忆操作全自动。ChatGPT 用户可见可编辑的 saved-memory 列表是部分例外。

_置信度:high(3-0)。_

---

## 横向对比表

| 系统                  | 存储 / 真相                                    | 写入路径                                              | 检索                                         | 作用域                           | 跨 agent + 投射                                                                                | 去重 / 冲突                     | 人工审阅                |
| --------------------- | ---------------------------------------------- | ----------------------------------------------------- | -------------------------------------------- | -------------------------------- | ---------------------------------------------------------------------------------------------- | ------------------------------- | ----------------------- |
| **mem0**(基础)        | 向量库                                         | **LLM** 抽取 + ADD/UPDATE/DELETE/NOOP(`infer=True`)   | 向量语义                                     | `user/agent/run_id`              | API 共享库;**无原生投射**                                                                      | 写时 LLM(不完美,#4896)          | 弱                      |
| **Zep/Graphiti**      | 时序知识图谱                                   | LLM 抽取 → 图                                         | 图遍历 + 向量                                | 图 / 命名空间                    | 中心 KG(MCP/API);**无原生投射**                                                                | 图谱消解                        | 弱                      |
| **Letta**(MemGPT)     | 中心 DB blocks(Postgres/pgvector)              | agent/LLM 改 block;编译进 prompt XML                  | 按 `block_id` attach                         | 每个 block / 每个 agent          | **仅在 Letta _自己的_ agent 间共享 block;无外部原生投射**(已投票核实)                          | agent 自管                      | 经 API/UI               |
| **MCP memory server** | **单一 JSONL 图文件**                          | 直写(agent 写),精确字符串去重                         | 子串 + 精确名                                | 每个图文件                       | 一个共享中心文件;**非**投射                                                                    | 仅精确字符串                    | 强(JSONL 可编辑)        |
| **claude-mem**        | 中心 SQLite + FTS5(+ 可选 Chroma)              | agent 会话蒸馏入库                                    | FTS5 + 向量                                  | 每个项目                         | 经 hooks/MCP 的中心库,多 agent;只有一个通用自动 `CLAUDE.md`,**无按 agent fan-out**             | n/a                             | 强(SQLite/查看器)       |
| **agentmemory**       | 中心 md 库(`jayzeng`)/ 服务器(`rohitg00`)      | agent 经 CLI/工具写                                   | CLI 拉取 / 服务器查询                        | 每个库                           | 中心库;`jayzeng` = 相同 `SKILL.md` shim 从中心拉(**非**投射);`rohitg00` = 单目标 Claude bridge | n/a                             | 强(文件)                |
| **Claude Code**       | **Markdown 文件**                              | 用户手写 + agent 自动 notes(**无抽取**)               | 全量加载 + 按需(**无语义**)                  | managed > user > project > local | 仅原生文件;**隔离**                                                                            | 人工                            | 强                      |
| **Cursor**            | `.mdc` markdown                                | 用户 / 后台生成的 rules                               | 文件加载                                     | Project / User / Team            | 仅原生;隔离                                                                                    | 人工                            | 强(git)                 |
| **Windsurf Cascade**  | Markdown                                       | 用户 rules + LLM 自动记忆(plain notes)                | 文件加载                                     | global / workspace / system      | 仅原生;隔离                                                                                    | 人工                            | 强                      |
| **ChatGPT**           | 不透明画像 + bio 列表                          | LLM curation + 用户 saved                             | 隐式画像                                     | 每个用户账号                     | N/A                                                                                            | LLM 自动 curation               | 部分(saved 列表可编辑)  |
| **Coffer**            | **Markdown 文件即真相** + 可重建的 SQLite 索引 | **直写,写时不用 LLM**(仅批量 transcript 蒸馏才用 LLM) | **grep + FTS5/BM25 + sqlite-vec**(语义,可选) | global + per-project(git-root)   | **一份共享库 → 投射进 N 个 agent 原生位置**(格式吻合则 symlink,否则托管块)                     | **人工 / 人来策展**(无自动去重) | **强**(UI + CLI + 文件) |

---

## 把业界格局映回 Coffer

1. **Coffer"写时不用 LLM"在文件式记忆里是主流,不是逆行。** Claude Code、Cursor、Windsurf 写记忆都不带抽取 LLM。Coffer 砍掉 mem0 的写时 LLM,正好站进 B 阵营,而不是孤身在外。

2. **Coffer 在检索上其实*领先*于 B 阵营。** 原生文件式记忆最大的弱点就是检索是"加载整个文件 / 子串匹配"——**Claude Code 根本没有语义检索**。Coffer 既保留文件即真相、又加上 FTS5/BM25 + sqlite-vec,等于拿到了 A 阵营的检索质量,却不用 A 阵营那种"向量即真相"的有损存储。这是一个真正的两全,而且调研结果给了它扎实支持。

3. **去重/冲突这个缺口是真的,而且整个业界都印证了它。** Coffer 继承了 B 阵营的弱点:砍掉 mem0 也砍掉了自动去重和冲突消解,于是重复/矛盾的 fact 会累积、只能靠**人工策展**。调研显示 B 阵营*所有人*都有同样的缺口——但它也显示 A 阵营的 LLM 去重*并不是*干净的胜利(mem0 #4896 在相近但矛盾的事实上会失败)。所以这个缺口是行业级的,不是 Coffer 独有的缺陷;真正的开放设计问题是:值不值得加一道**轻量、可选的合并/去重 pass**(mem0 式,但批量、opt-in,就像 Coffer 已经在 transcript 蒸馏上做的那样),在不牺牲可审阅性的前提下拿到抗膨胀。**这现在是最有决策价值的开放问题。**

4. **多目标原生投射是真正新颖的那块——现已拍实(high)。** 三轮调研用对抗投票排除了每一个强候选先例:claude-mem(中心库 + 通用 `CLAUDE.md`)、Letta(只共享自有 agent、中心 DB、prompt-XML 注入)、`jayzeng/agentmemory`(中心库 + CLI-shim 拉取)。**把一份 canonical 库扇出投射进*多个异构* agent 各自的原生记忆位置——格式吻合处 symlink、不吻合处托管块、并关掉自带记忆防发散——哪都没找到。** 这个精确机制才是 Coffer 的新颖贡献。**但注意这面黄旗:** 业界其余玩家都*刻意选择运行时注入、而非写原生文件*——Letta 的 `claude-subconscious` 明确拒绝碰 `CLAUDE.md`。Coffer 应该能说清楚:为什么"写/symlink 进原生文件 + 关掉 agent 自带记忆"这条别人避开的侵入式路径值得走——好处是环境式加载、零每会话注入开销、真正的跨 agent 统一;代价正是 `claude-subconscious` 绕开的那种侵入性。

---

## 注意事项(请与结论一起记住)

1. **第三轮覆盖缺口。** 第三轮投票核实了 **Letta**(18 条全票)和 **`jayzeng/agentmemory`**(6 条全票),但**没产出 `rohitg00/agentmemory` 或 Zep/Graphiti 的确认 claim**(来源抓到了,但在 synthesis 前被 budget 丢弃)。这两者停在第二轮的一手来源 / 背景级别 —— 低风险(只 Claude 的桥仍是单目标;Zep 是中心 KG 服务),但未投票确认。Cognee、LangMem、Llama-Index memory 仍未考察。
2. **"论文 vs 平台"漂移。** 多条 mem0 结论严格限定于其论文(arXiv 2504.19413);实际平台/SDK 已演进(v3 multi-signal hybrid 检索;`agent_id` 范围;OSS v2→v3 弃用了独立 Neo4j 图存储)。引用时要区分"论文描述的架构"与"当前产品"。
3. **缺席性证据弱于在场性证据。** "未提及"(无原生投射 / 无跨 agent fan-out)依赖对源文档的全文检索;虽已做针对性对抗搜索,但仍可能有遗漏。
4. **措辞精度。** Cursor `.mdc` 是 _Markdown + YAML frontmatter_,不是严格"纯 markdown"(纯 markdown 变体是 `AGENTS.md`)。ChatGPT 两机制不完全互独。mem0 写时去重在矛盾边缘场景会失败(#4896)。"agentmemory" 至少指两个不同项目(`jayzeng/agentmemory`、`rohitg00/agentmemory`)。DeepWiki(用于佐证 Letta 的 ORM)是源码派生的二手来源,仅作佐证。
5. **时效性。** 这是 2025–2026 的快照(证据访问于 2026-06-17)。Letta Code / MemFS / Context Repositories 都是 2025–2026 期产物;编码 agent 记忆演进很快 —— Letta 的 Context Repositories 已能*单向读入*外部历史,未来若加*写回*能力,将是第一个逼近 Coffer 扇出方向的系统。半年内重新核查。

## 开放问题

1. _(最强候选已关闭。)_ 跑一轮干净复核能把 `rohitg00/agentmemory` 与 Zep/Graphiti 从一手来源升级为投票确认;仅当新颖性主张需要被正式辩护时才值得。即便未核实,二者对 fan-out 主张都低风险。
2. **对文件式存储,业界有没有成熟的*自动*抗膨胀/去重/冲突方案,还是普遍靠人工?** 值不值得叠一道轻量可选的 LLM 合并 pass(mem0 式、批量),以兼得可审阅性与抗膨胀?**对 Coffer 最有决策价值的开放问题。**
3. **Coffer 投射的一致性语义到底是什么**(单向 render vs 双向同步、冲突如何消解、各 agent 本地编辑是否回流)?这才是它相对中心库模式的真正差异点——也是那个新颖之处里最该加固的部分。
4. **业界为什么避开写原生文件(改用运行时注入)?** Letta 的 `claude-subconscious` 刻意从不写 `CLAUDE.md`。Coffer 应该说清楚:为什么它的原生文件投射 + 关闭自带记忆值得别人绕开的那种侵入性,并留意"关掉 agent 自带记忆"这个子机制是否有部分先例(目前没找到,但反向覆盖较薄)。

## 来源

主要来源(除注明外均已投票核实):

- mem0 —— arXiv [2504.19413](https://arxiv.org/pdf/2504.19413)([HTML](https://arxiv.org/html/2504.19413v1));[memory operations / add](https://docs.mem0.ai/core-concepts/memory-operations/add);[issue #4896](https://github.com/mem0ai/mem0/issues/4896)
- 官方 MCP memory server —— [modelcontextprotocol/servers/src/memory](https://github.com/modelcontextprotocol/servers/tree/main/src/memory)
- Claude Code —— [memory 文档](https://code.claude.com/docs/en/memory);issue [#39195](https://github.com/anthropics/claude-code/issues/39195)、[#23750](https://github.com/anthropics/claude-code/issues/23750)
- Cursor —— [rules 文档](https://cursor.com/docs/rules);Windsurf Cascade —— [memories 文档](https://docs.windsurf.com/windsurf/cascade/memories)
- ChatGPT —— [reference saved memories(OpenAI Help)](https://help.openai.com/en/articles/11146739-how-does-reference-saved-memories-work)
- **claude-mem** _(第二轮,已投票核实)_ —— [repo](https://github.com/thedotmack/claude-mem)、[docs](https://docs.claude-mem.ai/introduction)、[hooks 架构](https://docs.claude-mem.ai/hooks-architecture)
- **Letta** _(第三轮,已投票核实,18 条全票)_ —— [multi-agent shared memory](https://docs.letta.com/guides/agents/multi-agent-shared-memory/)、[memory blocks guide](https://docs.letta.com/guides/agents/memory-blocks/)、[shared-memory-blocks 教程](https://docs.letta.com/tutorials/shared-memory-blocks/)、[memory-blocks 博客](https://www.letta.com/blog/memory-blocks)、[context-repositories 博客](https://www.letta.com/blog/context-repositories/)、[`claude-subconscious`](https://github.com/letta-ai/claude-subconscious)
- **agentmemory** —— `jayzeng` _(第三轮,已投票核实)_:[repo](https://github.com/jayzeng/agentmemory)、[SKILL.md](https://raw.githubusercontent.com/jayzeng/agentmemory/main/skills/claude-code/SKILL.md)、[site](https://jayzeng.github.io/agentmemory/) · `rohitg00` _(第二轮,未复核)_:[repo](https://github.com/rohitg00/agentmemory)
- **Zep/Graphiti** _(第二轮 / 背景)_ —— [Graphiti repo](https://github.com/getzep/graphiti)、[Graphiti MCP server](https://help.getzep.com/graphiti/getting-started/mcp-server)、[knowledge-graph MCP](https://www.getzep.com/product/knowledge-graph-mcp/)、Zep 论文 arXiv [2501.13956](https://arxiv.org/abs/2501.13956)

次要来源(博客,权重较低):agentmemory 概览([knightli.com](https://knightli.com/en/2026/05/19/agentmemory-persistent-memory-ai-coding-agents/)、[signalforges](https://signalforges.com/pages/rohitg00-agentmemory-best-practices-2026-05-13/)、[dev.to](https://dev.to/andrew-ooo/agentmemory-review-persistent-memory-for-ai-coding-agents-55g2))、mem0-vs-letta-vs-zep-vs-cognee 对比、Claude Code 记忆分层讲解、mem0 [驱逐/遗忘博客](https://mem0.ai/blog/memory-eviction-and-forgetting-in-ai-agents)。

---

_由 Coffer 的 `deep-research` 工作流跑三轮生成。第一轮:广义全景(25 条 claim)。第二轮:claude-mem 已投票核实。第三轮:Letta + `jayzeng/agentmemory` 已投票核实(24 确认 / 1 驳回);`rohitg00/agentmemory` + Zep 未复核。置信度标签是工作流给的,非人工指定。_

---

## 核查更新（2026-06-19）

> 对照实时来源与 Coffer 自身的代码/规格做了一遍新核查。全部 web 主张都站得住;mem0 移除 Neo4j 比报告所说更彻底,另有三个 A 阵营竞品现已补上刻画。**最大的本地变化:** Coffer 的原生投射层 —— 也就是报告点名为其第 3 块新颖性的那个精确机制 —— 已被**移除**(PR #110 / [ADR-026](../decisions/ADR-026-memory-via-mcp-not-native-projection.md),2026-06-18),因此下面关于投射的条目已按当前现实重写、新颖性裁决也随之修订:这个 fan-out 不再是 Coffer 自己在做的事了。

### ✅ 已确认

- **Coffer 投射的一致性语义(开放问题 3)现已不适用 —— 因为根本不存在投射了。** 自 [ADR-026](../decisions/ADR-026-memory-via-mcp-not-native-projection.md)(2026-06-18,取代 ADR-013)起,Coffer **不再把记忆投射进任何 agent 的原生文件**。整个投射层 —— 带 `projection_mode ∈ {SYMLINK, RENDER, NONE}` 的 `AgentMemoryAdapter` 协议、投射引擎、各 agent 适配器、FS 适配器、绑定持久化/绑定表(由迁移 `0024` 删除)、投射 REST 路由,以及接管/关闭原生记忆的那条路径 —— 都已删除(`projection_service.py` 与 `new_agent_adapters.py` 已不存在)。Coffer 保留它自己的逐事实 markdown canonical 库,**绝不写入、symlink 进、或关掉任何 agent 的原生记忆**。agent **只能通过 MCP 网关工具**(`coffer__recall` / `remember` / `update_memory` / `forget` / `list_memory`)读写 Coffer 记忆;作用域(global + per-project,git-root)由 MCP shim 的 cwd 解析得到。于是"单向 render vs 双向同步、本地编辑是否回流"这个问题自行消解:根本没有原生副本可供回流。(把记忆索引在会话开始时**注入**进上下文、永不写文件的环境式 hook,是 ADR-026 推迟的后续项,**尚未实现**;在它落地前,MCP `recall` 是唯一访问路径。)`repo:docs/decisions/ADR-026-memory-via-mcp-not-native-projection.md`、`repo:specs/007-memory/spec.md`(Input 节;FR-010)、`repo:backend/coffer/application/memory/recall.py`、`repo:backend/coffer/application/memory/builtin_tools.py`
- **投射时的冲突消解 —— 已不再适用。** 既然不碰原生文件,就没有第二个写者、也没有什么要关掉的;canonical 库平凡地成为唯一一份库。Coffer 的逐事实 markdown 依旧是**直写、写时不用 LLM、无自动去重/合并 —— 人工策展**(B 阵营),经 MCP 访问。上一版草稿里描述的 ADR-013"接管—先合并—再 symlink"行为已随投射层一并消失。`repo:backend/coffer/application/memory/writes.py`、`repo:specs/007-memory/spec.md`(US-4 策展)
- **rohitg00/agentmemory 唯一写原生文件的桥确为单目标(只 Claude)** —— "与 MEMORY.md 双向同步"只为 Claude Code 提供(由 `CLAUDE_MEMORY_BRIDGE` 控制);其余 agent 拿到的是 MCP/skill 访问,而非原生文件写入。报告的单目标定性成立。https://github.com/rohitg00/agentmemory/blob/main/README.md
- **被调研的系统里没有谁做原生多目标 fan-out 投射** —— 这条*业界*结论本轮幸存(不过,见下方 ✏️ 已修正:Coffer 自己也不再做了,所以这个设计点如今谁都没占,包括 Coffer)。Letta Context Repositories 的 `/init` 会从既有的 Claude Code 与 Codex 历史里*单向*学习,但记忆随后落在 Letta 自家的 git 后端 MemFS 仓库(内部、按 agent 经 `/memfs`);不会持续写回外部 agent 的原生文件。https://www.letta.com/blog/context-repositories/
- **Zep/Graphiti 仍是经 MCP/API 提供的中心时序知识图谱库** —— 架构上与原生 fan-out 正相反。https://help.getzep.com/graphiti/getting-started/mcp-server

### ✏️ 已修正

- **报告称作 Coffer 新颖性的那套投射模型已被取代并移除(PR #110 / [ADR-026](../decisions/ADR-026-memory-via-mcp-not-native-projection.md),2026-06-18)。** 本核查更新的上一版草稿 —— 以及其上方的报告正文 —— 都是对照 ADR-013 来描述 Coffer 的多目标原生 fan-out(格式吻合处 symlink、不吻合处托管块,并关掉 agent 自带记忆防发散)。**ADR-026 取代 ADR-013,并把这一整层彻底移除:** Coffer 如今保留自己的逐事实 markdown 库,通过 MCP 网关工具触达每个 agent,绝不碰原生记忆文件(`repo:docs/decisions/ADR-026-memory-via-mcp-not-native-projection.md`、`repo:specs/007-memory/spec.md`)。该 ADR 正是引用*本研究*的那面黄旗 —— 整个业界都刻意避开写原生文件(Letta 的 `claude-subconscious` 拒绝碰 `CLAUDE.md`)—— 作为做此反转的理由之一。**对报告论点的诚实结论:** 第 3 块"多目标原生 fan-out 新颖、没人做"这一*关于业界*的发现仍然成立 —— 被调研的系统没有谁做。但它**不再是 Coffer 在做的事**,所以这份新颖性对 Coffer 而言如今已成空谈:Coffer 已经加入了它先前被区分出来的那个业界默认阵营 —— 中心库 + 工具(MCP)访问。这个 fan-out 设计点依旧无人占据;只是 Coffer 出于可读性/侵入性的权衡,选择了不去占它。
- **mem0 移除 Neo4j 被低估。** 旧:"OSS v2→v3 弃用了独立 Neo4j 图存储"。修正:外部图库(Neo4j 等)在 v3 中已被**完全移除(删了约 4000 行,PR #4805,约 2026 年 4 月)**,代之以内置的实体关联图记忆、不再依赖外部图数据库。v3 检索是 multi-signal hybrid:语义(唯一的候选生成路径)+ BM25(仅做 boost)+ 实体匹配,融合成单一分值;`agent_id` 范围现已落进一个 `filters` 字典,使 OSS 与 Platform API 对齐。https://docs.mem0.ai/migration/oss-v2-to-v3
- **rohitg00/agentmemory 的背景注脚低估了它的覆盖面。** 报告把它定性为一个小型中心服务器;它如今还会把 **SKILL shim**(不是记忆内容)扇出装进 50+ 个 agent 的原生技能目录(Claude Code、Cursor、Codex、Gemini CLI、OpenCode、Windsurf 等)。这属于技能分发,不是记忆的原生文件投射 —— 因此不影响 fan-out 的新颖性主张。https://github.com/rohitg00/agentmemory/blob/main/README.md

### ➕ 新增覆盖

- **Cognee** —— memory-first 知识图谱引擎:从数据出发,经 embeddings + 图抽取 + 本体生成,构建自托管 KG(主语-关系-宾语三元组);向量检索作为"提示"定位相关图三元组,再遍历图取得结构化上下文。Custom Graph Model = 抽取用的领域 schema。多后端(图:Neo4j/FalkorDB/KuzuDB/NetworkX;向量:Redis/Qdrant/Weaviate;元数据:SQLite/Postgres)。**A 阵营** —— 图即真相、写时用 LLM/本体、中心库,无原生文件投射。https://github.com/topoteretes/cognee
- **LangMem(LangChain SDK)** —— 给 LangGraph agent 提供三类人类认知式长期记忆:语义(collections + 画像)、情景(few-shot 示例 / 会话摘要)、程序(规则/行为)。后端无关的 store(向量库/KV/Postgres)。自动 consolidation 合并相关事实并消解矛盾(写时用 LLM)。**A 阵营** —— 无原生文件投射。https://www.langchain.com/blog/langmem-sdk-launch
- **LlamaIndex memory 模块** —— 一个 `Memory` 类 = 短期(token 上限内的最近 X 条消息)+ 长期(从短期 flush 出的 Memory Block 对象):StaticMemoryBlock、FactExtractionMemoryBlock(LLM 抽取事实)、VectorMemoryBlock(向量库存取消息批次);按优先级截断。**A 阵营** —— 会话/agent 作用域的对话缓冲 + 向量库,无跨 agent 共享,无原生文件投射。https://developers.llamaindex.ai/python/framework/module_guides/deploying/agents/memory/

三者都强化了报告"A 阵营 = 中心库、写时用 LLM/抽取、向量/图检索、无原生投射"的论点,所以加上它们不削弱 Coffer 第 3 块的新颖性主张。
