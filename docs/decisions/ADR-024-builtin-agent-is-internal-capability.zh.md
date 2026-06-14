# ADR-024 — 内置 agent 是内部能力，不是聊天人格

> English: [ADR-024-builtin-agent-is-internal-capability.md](./ADR-024-builtin-agent-is-internal-capability.md)

- **状态：** Accepted
- **日期：** 2026-06-14
- **决策者：** Yuxing Wu
- **Spec：** [008-agent-chat](../../specs/008-agent-chat/spec.md) 与 [004-agent-registry](../../specs/004-agent-registry/spec.md)（重新定位 + 能力迁移——不新增 spec 编号；实现前更新两份 `spec.md`）
- **取代：** [ADR-021](./ADR-021-chat-as-vault-console.md) 中"通过 `builtin` agent 与金库对话"这一半；**修订** [ADR-018](./ADR-018-tool-retrieval-for-overload.md)（search-tools 排序）并 un-defer 其 Capability B
- **相关：** [007-memory](../../specs/007-memory/spec.md)、[006-knowledge-base](../../specs/006-knowledge-base/spec.md)、[ADR-012](./ADR-012-files-as-truth-sqlite-retrieval.md)、[ADR-020](./ADR-020-transcript-distillation.md)

## 背景

Coffer 曾交付一个 `builtin`「Coffer Assistant」——本地 LLM（Qwen via Ollama，
LangGraph ReAct 循环），与 `claude_code`、`codex` 并列注册为三个**聊天** agent
之一。[ADR-021](./ADR-021-chat-as-vault-console.md) 把聊天面重新定位为*金库控制台*，
并把"通过 `builtin` agent 与金库对话"作为其第一职责。

这个定位站不住。在做渠道桥接时收敛的方向是：**Coffer 是金库/底座，不是行动者**——
宪法把它定义为"任何 AI agent 通过同一个安全接口读取与贡献"的地方。一个面向用户的
聊天人格偏离了这条线：它和"Claude Code + Coffer MCP"重复，对着各 agent 自己的 UI 和
IM 没有持久使用场景，还悄悄重新打开了 ADR-021 自己想关掉的"日常主力"蔓延。

而且 `builtin` 模型**唯一独占的消费者**就是这个聊天人格。盘点真正用到本地 LLM 机器的地方：

- **`coffer__search_tools`**（ADR-018）——纯 BM25-lite 排序，**不用 LLM**。
- **转写蒸馏**（ADR-020）——用单轮 LLM 补全（`LangchainLlmCompletion`）对*任意*配置模型，
  不走聊天循环。
- **`builtin` 聊天 agent**——唯一需要 LangGraph ReAct 循环的东西，也是唯一把模型当人格
  摆到用户面前的东西。

所以问题不是表面的（"给页面改名"），而是结构性的：**内置 agent 是内部实现细节，不是产品
概念。** 它正确的形态正是项目方向记录里早就命名的——一个通过 Coffer MCP 接口调用的*辅助
能力*，"像 RAG 里的 embedding 模型：不是用户拿来聊天的，而是主 agent 调用、帮它把活干得
更好的子组件。"

## 决策

**让内置 agent 退出聊天人格，重塑为 Coffer 内部能力。** 三步。

### 1. 聊天只面向受管 agent；页面改回「聊天」

- 聊天面**只**与 Coffer 受管 agent（`claude_code`、`codex`，及将来的受管 agent）对话。
  `builtin` provider 从聊天 agent 注册表和选择器中移除。
- 侧边栏标签从*金库控制台 / Vault Console* 改回 **聊天 / Chat**。
- ADR-021 的**第二**职责原样保留：聊天页仍是观测/审批渠道/IM 驱动会话的 human-in-the-loop
  席位，走同一套 `ConversationPort` / `TurnPort` / `submit_approval` 接缝。"聊天"命名的是
  会话集合——无论由谁驱动——所以名字仍贴切。

### 2. "内置 agent"概念离开 UI

- `/agents` 列表去掉内置 agent 卡片；`/agents` 纯粹是受管 agent。
- 删除 `/agents/builtin` 详情页。其中唯一仍有意义的部分——本地模型配置——迁入
  **Settings → Models**，从"Coffer Assistant 使用的模型"重构为**「Coffer 内部模型」**，
  驱动检索、agentic RAG 与蒸馏。

### 3. 本地模型成为内部能力的引擎

LLM 机器**保留但重新定位**，永不面向用户：

- **保留**模型工厂（`langchain_models.py`）和单轮补全（`llm_completion.py`）——蒸馏已依赖
  它们，(b) 也将依赖。
- **移除**面向聊天的部分：`builtin` 聊天 provider、其注册表条目、聊天事件映射。
- **重塑** ReAct 循环为内部 agentic-RAG 引擎，置于一个新内置工具 (b) 之后，复用既有的
  in-process gateway 会话（`coffer-builtin-agent`）访问知识/记忆。

本次改动交付两项能力：

**(a) `coffer__search_tools` 获得语义排序（修订 ADR-018）。** BM25-lite 排序有真实召回缺
口：纯词法匹配，意图"notify someone"会漏掉 `send_message` 工具，跨语言 query 会漏掉英文工
具名。ADR-018 *自己引用的证据*里，赢的选择器是**嵌入**索引（Copilot：embedding 94.5% >
LLM 87.5%）——是嵌入，不是关键词。于是 `coffer__search_tools` 现在**在配置了 embedder 时
走语义排序、未配置时回退 BM25-lite 排序**——和知识库已有的 `vector → keyword` 降级一致
（ADR-012）。这保住了零配置、离线、确定性的路径（仍由 `tool_search` eval 守护），同时为有
embedder 的用户修掉召回。注意这**并不**推翻 ADR-018 对工具选择用 _LLM router_ 的否决：下游
agent 仍负责 select-and-call，我们只改善它看到的候选集。

**(b) `coffer__ask` —— 对金库的 agentic 检索（un-defer ADR-018 Capability B）。** 一个新内置
MCP 工具，对用户的**知识库 + 记忆**跑一个有界的"检索-综合"循环，返回带引用的答案。ADR-018
defer Capability B 是*针对工具选择*的——那里下游 frontier 模型本就擅长从排序结果里挑。知识/记
忆综合是另一个问题：跨文档的多步检索 + 阅读 + 摘要，本来需要调用方做大量手工
`search_knowledge` / `read_document` 往返。`coffer__ask` 正是"RAG 里的 embedding 模型"这个
比喻的字面形态——主 agent 调用的内部子组件，绝非聊天对象。

### 不变量

- **没有面向用户的内置人格。** 本地模型只能作为 `coffer__*` 工具（及蒸馏等内部流程）触达，
  绝不作为聊天 agent，也绝不被 UI 当作助手呈现。
- **附加的、可审计的工具。** `coffer__ask` 与升级后的 `coffer__search_tools` 像任何 `coffer__`
  内置工具一样在 `tools/list` 中通告，记入调用日志（who/when/how-long/outcome，无参数/结果），
  并优雅降级（搜索回退 BM25；未配置模型时给出明确错误而非崩溃）。
- **审批/接缝对等性保留。** 移除 `builtin` 聊天 provider 不触碰渠道与受管 agent 聊天共享的
  `ConversationPort` / `TurnPort` / 审批机器。

## 备选方案

### A — 保留内置聊天人格（现状 / ADR-021）

**否决。** 偏离使命（Coffer 是金库，不是行动者）、与"Claude Code + Coffer MCP"重复、无持久使
用、重新打开日常主力蔓延。

### B — 现在就移除内置 agent *并*删掉所有 LLM 机器

**否决。** 蒸馏已依赖模型工厂 + 单轮补全，agentic RAG (b) 又给 ReAct 底座提供了真实内部消费
者。删掉会让蒸馏失依赖，并迫使 (b) 从零重建。我们只删聊天外壳。

### C — `coffer__search_tools` 保持纯 BM25、不加 embedder 路径

**否决。** 词法召回缺口是真的，而这正是 ADR-018 引用的证据说嵌入能修的。`vector → keyword`
回退保住了零配置默认值，所以对没有 embedder 的用户加语义路径零成本。

### D — 把 `/agents/builtin` 保留为只读的"Coffer 内部"可观测页

**暂否（YAGNI）。** 把内部模型/工具在做什么透明化可以作为日后专门的特性；复用一个 _agent 详情_
页来承载它，反而保留了本 ADR 要去掉的"内置 agent 是个东西"的框架。

## 后果

- Spec 008（`spec.md`、验收场景）与 Spec 004（agent registry）更新：聊天只列受管 agent；内置
  agent 不再是注册的聊天 agent。
- ADR-021 标记为**部分被取代**：渠道观测/审批职责存续；"通过 builtin agent 与金库对话"职责移除。
- ADR-018 被**修订**：`coffer__search_tools` 获得带 BM25 回退的语义排序路径；Capability B 针对
  知识/记忆 un-defer 为 `coffer__ask`。
- UI：`/chat` 改回「聊天」；移除 `/agents/builtin` 路由与内置卡片；Settings → Models 重构为
  Coffer 内部模型。
- CLI：移除 `coffer chat` 命令（内置 agent 的终端聊天）；`coffer model` 及其余 CLI 不变。
- LangGraph/LangChain 作为**内部**依赖保留（蒸馏 + `coffer__ask`）；删除聊天事件映射与 `builtin`
  聊天 provider。
- 除 Settings → Models 已存储的内容外无新增持久状态；无迁移。
