# 内置 agent 是内部能力，不是聊天人格

> English: [builtin-agent-is-internal-capability.md](./builtin-agent-is-internal-capability.md)

- **状态：** Accepted
- **日期：** 2026-06-14
- **决策者：** Yuxing Wu
- **Spec：** [channels](../../specs/channels/spec.zh.md) 与 [agent-registry](../../specs/agent-registry/spec.zh.md)（重新定位 + 能力迁移——不新增 spec；实现前更新两份 `spec.md`）
- **取代：** 那份已被移除、把 Agent Chat 重定位为金库控制台的 ADR 中"通过 `builtin` agent 与金库对话"这一半；**修订** [Tool Retrieval](./tool-retrieval-for-overload.md)（search-tools 排序）
- **相关：** [knowledge](../../specs/knowledge/spec.md)（知识层 spec）、[Files as Truth](./files-as-truth-sqlite-retrieval.md)

## 背景

Coffer 曾交付一个 `builtin`「Coffer Assistant」——本地 LLM（Qwen via Ollama，
LangGraph ReAct 循环），与 `claude_code`、`codex` 并列注册为三个**聊天** agent
之一。一份此后已被移除的 ADR 把聊天面重新定位为*金库控制台*，
并把"通过 `builtin` agent 与金库对话"作为其第一职责。

这个定位站不住。在做渠道桥接时收敛的方向是：**Coffer 是金库/底座，不是行动者**——
宪法把它定义为"任何 AI agent 通过同一个安全接口读取与贡献"的地方。一个面向用户的
聊天人格偏离了这条线：它和"Claude Code + Coffer MCP"重复，对着各 agent 自己的 UI 和
IM 没有持久使用场景，还悄悄重新打开了那次重定位自己想关掉的"日常主力"蔓延。

而且 `builtin` 模型**唯一独占的消费者**就是这个聊天人格。盘点真正用到本地 LLM 机器的地方：

- **`coffer__search_tools`**（ADR：tool-retrieval-for-overload）——纯 BM25-lite 排序，**不用 LLM**。
- **记忆重组与记忆库合并**（spec knowledge）——用单轮 LLM 补全（`LangchainLlmCompletion`）对*任意*
  配置模型，不走聊天循环。
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
- 那次重定位的**第二**职责原样保留：聊天页仍是观测渠道/IM 驱动会话的
  席位，走同一套 `ConversationPort` / `TurnPort` 接缝。"聊天"命名的是
  会话集合——无论由谁驱动——所以名字仍贴切。

  _2026-09-10 修订，2026-09-12 再修订：_ 页面在 10 日因未被使用而删除，12 日又恢复，
  因此这里描述的观测席位依然成立——而且被拓宽了，因为这个页面还能中断并接手它所旁观的
  东西（[Chat 是单属主的实时镜像](chat-single-owner-live-mirror.zh.md)）。这里点名的
  `ConversationPort` / `TurnPort` 接缝落在 spec channels FR-043…FR-055，页面本身落在
  FR-072…FR-078。前两条——只面向受管 agent、注册表里没有 `builtin`——仍然成立，
  现在正是 agent provider 列表所返回的内容。

### 2. "内置 agent"概念离开 UI

- `/agents` 列表去掉内置 agent 卡片；`/agents` 纯粹是受管 agent。
- 删除 `/agents/builtin` 详情页。其中唯一仍有意义的部分——本地模型配置——迁入
  **Settings → Models**，从"Coffer Assistant 使用的模型"重构为**「Coffer 内部模型」**，
  驱动检索与记忆重组。

### 3. 本地模型成为内部能力的引擎

LLM 机器**保留但重新定位**，永不面向用户：

- **保留**模型工厂（`langchain_models.py`）和单轮补全（`llm_completion.py`）——记忆重组与
  记忆库合并已依赖它们。
- **移除**面向聊天的部分：`builtin` 聊天 provider、其注册表条目、聊天事件映射。
- **保留** ReAct 循环作为仅内部的引擎（记忆重组，spec knowledge），永不作为聊天 agent 暴露。

本次改动交付一项能力：

**`coffer__search_tools` 获得语义排序（修订 [Tool Retrieval](./tool-retrieval-for-overload.zh.md)）。** BM25-lite 排序有真实召回缺
口：纯词法匹配，意图"notify someone"会漏掉 `send_message` 工具，跨语言 query 会漏掉英文工
具名。Tool Retrieval *自己引用的证据*里，赢的选择器是**嵌入**索引（Copilot：embedding 94.5% >
LLM 87.5%）——是嵌入，不是关键词。于是 `coffer__search_tools` 现在**在配置了 embedder 时
走语义排序、未配置时回退 BM25-lite 排序**——和知识库已有的 `vector → keyword` 降级一致
（ADR：files-as-truth-sqlite-retrieval）。这保住了零配置、离线、确定性的路径（仍由 `tool_search` eval 守护），同时为有
embedder 的用户修掉召回。注意这**并不**推翻 Tool Retrieval 对工具选择用 _LLM router_ 的否决：下游
agent 仍负责 select-and-call，我们只改善它看到的候选集。

### 不变量

- **没有面向用户的内置人格。** 本地模型只能作为 `coffer__*` 工具（及记忆重组等内部流程）触达，
  绝不作为聊天 agent，也绝不被 UI 当作助手呈现。
- **附加的、可审计的工具。** 升级后的 `coffer__search_tools` 像任何 `coffer__` 内置工具一样
  在 `tools/list` 中通告，记入调用日志（who/when/how-long/outcome，无参数/结果），并优雅降级
  （未配置 embedder 时回退 BM25，而非崩溃）。
- **接缝对等性保留。** 移除 `builtin` 聊天 provider 不触碰渠道与受管 agent 聊天共享的
  `ConversationPort` / `TurnPort` 机器。

## 备选方案

### A — 保留内置聊天人格（现状 / 那次金库控制台重定位）

**否决。** 偏离使命（Coffer 是金库，不是行动者）、与"Claude Code + Coffer MCP"重复、无持久使
用、重新打开日常主力蔓延。

### B — 现在就移除内置 agent *并*删掉所有 LLM 机器

**否决。** 记忆重组与记忆库合并已依赖模型工厂 + 单轮补全，记忆重组（spec knowledge）又是 ReAct 底座
的真实内部消费者。删掉会让两者都失依赖。我们只删聊天外壳。

### C — `coffer__search_tools` 保持纯 BM25、不加 embedder 路径

**否决。** 词法召回缺口是真的，而这正是 Tool Retrieval 引用的证据说嵌入能修的。`vector → keyword`
回退保住了零配置默认值，所以对没有 embedder 的用户加语义路径零成本。

### D — 把 `/agents/builtin` 保留为只读的"Coffer 内部"可观测页

**暂否（YAGNI）。** 把内部模型/工具在做什么透明化可以作为日后专门的特性；复用一个 _agent 详情_
页来承载它，反而保留了本 ADR 要去掉的"内置 agent 是个东西"的框架。

## 后果

- Agent Chat 规范（`spec.md`、验收场景）与 Agent Registry 规范更新：聊天只列受管 agent；内置
  agent 不再是注册的聊天 agent。
- 那次金库控制台重定位标记为**部分被取代**：渠道观测职责存续；"通过 builtin agent 与金库对话"职责移除。
- Tool Retrieval 被**修订**：`coffer__search_tools` 获得带 BM25 回退的语义排序路径。
- UI：`/chat` 改回「聊天」；移除 `/agents/builtin` 路由与内置卡片；Settings → Models 重构为
  Coffer 内部模型。
- CLI：移除 `coffer chat` 命令（内置 agent 的终端聊天）；`coffer model` 及其余 CLI 不变。
- LangGraph/LangChain 作为**内部**依赖保留（记忆重组 + 记忆库合并）；删除聊天事件映射与
  `builtin` 聊天 provider。
- 除 Settings → Models 已存储的内容外无新增持久状态；无迁移。

## 修订历史

- **2026-09-09** —— 移除 transcript 蒸馏。它曾是本 ADR 用以论证「聊天人格离场后仍保留 LLM 机器」
  的两个内部消费者之一；上文列出的其余消费者（记忆重组、记忆库合并，以及 ReAct 重组引擎）
  自身即可支撑该论证，因此**决定本身不变**，变的只是举例。
- **2026-09-09** — 移除 `coffer__ask`。本 ADR 作为能力 (b) 交付的 agentic-RAG 能力已删除：
  ReAct 循环只保留为本 ADR 同时描述的内部记忆重组引擎。`coffer__ask` 的调用方是
  Claude Code 与 Codex，它们本身就是很强的 ReAct agent；让 Coffer 的内部小模型代替
  它们跑一个有界的 16 步检索循环，是把职责搞反了，而且用的还是比提问者更弱的模型。
  使用数据印证了这一点——30 天内 4 次调用，其中 1 次失败。该循环所包装的检索工具
  仍可直接调用，因此失去的只是这层包装。
