# ADR-018：面向聚合过载的工具检索

**状态**：Accepted
**日期**：2026-06-14
**决策者**：Yuxing Wu
**关联**：`.specify/memory/constitution.md`、[spec `001-mcp-gateway`](../../specs/001-mcp-gateway/spec.zh.md)、[ADR-007](ADR-007-everything-is-a-resource-kind.zh.md)、[ADR-012](ADR-012-files-as-truth-sqlite-retrieval.zh.md)

## 背景

Coffer 是一个 local-first 的 MCP 聚合器：它把许多上游 MCP 服务器的工具合并起来，作为一个带命名空间的统一工具面，重新暴露给一个 coding agent（Claude Code / Codex）。这正是 spec 001 的全部要点——注册一次，处处可用。但这种聚合有一个随成功而增长的失败模式：一旦用户注册了许多服务器，合并后的目录动辄超过 **150 个工具**，而一个 coding agent 的工具选择准确率在目录大约超过 **30–50 个工具**之后就会急剧下降。

代价有两方面。其一是**上下文**：把 150+ 个完整工具 schema 塞进每一次请求，会在 agent 还没干任何活之前就烧掉一大笔固定的 token 预算。其二是**准确率**：模型要在越多近乎重复、相互重叠的工具上推理，就越频繁地选错或臆造出一个调用。聚合这个功能，反而成了让 agent 变差的东西。

已发表的证据一致且有力（见下方「证据」）：

- Anthropic 的 **Tool Search Tool** 记录了同样的 30–50 工具悬崖，并显示：让模型去**搜索**目录、而不是把整份目录递给它，能把工具选择准确率从 **49% → 74%**（Opus 4）、**79.5% → 88.1%**（Opus 4.5）提升，同时工具定义所耗 token 减少约 **85%**。
- **RAG-MCP** 报告：基于检索的工具选择准确率为 **43%**，而把所有工具一股脑塞入时仅 **13.6%**——3 倍多——且 prompt token 约为其一半。
- **GitHub Copilot** 把工具集从 40 个收到 13 个，且关键地发现：基于 embedding/检索的选择器在挑工具上胜过基于 LLM 的选择器——**94.5% > 87.5%**——检索索引在选择上胜过 LLM 路由器，且更便宜更快。

Coffer 需要一种办法，让聚合在规模化后仍是净收益：让 agent 找出与当前意图匹配的少数几个工具并直接调用它们，而不是在整张合并列表上推理。

## 决策

新增一个 Coffer 内置 MCP 工具 **`coffer__search_tools`**，它是一个**向主 agent 返回真实上游工具 schema 的检索原语 (retrieval primitive)**——而不是一个代替 agent 去选择并调用的 LLM 子 agent。

契约 (Contract)：

```
coffer__search_tools(query: string [required], top_k?: int = 5, max 20)
  -> { tools: [{ name, description, inputSchema, score }], total_searched: N }
```

- **对实时聚合目录排序。** 它把当前聚合的上游工具按意图 `query` 打分并返回 top-k。agent 随后用返回工具已有的 `<server>__<tool>` 名称直接调用；路由与 spec 001 完全一致。
- **返回真实 schema，而非一次调用。** 其形态对齐 Anthropic 认可的「custom tool search implementation」——后者返回 `tool_reference` 块，由 API 展开成真实工具定义。主 agent（本就是顶尖模型）保留选择与调用的决定权。
- **纯粹、确定、本地的排序器。** 在每个工具的 name + description 上做 BM25-lite 关键词排序，name token 权重更高。无 LLM、无 embedding、无网络——契合 local-first、信任为中心的 vault，且在网关内运行免费。
- **结果仅含上游。** Coffer 自己的 `coffer__` 内置工具被排除；只对上游能力——过载的来源——排序。
- **叠加式 (additive)。** `coffer__search_tools` 始终与其他 `coffer__` 内置工具一起在 `tools/list` 中通告。Coffer 继续一如既往地通告完整上游目录；服务端不隐藏任何东西。工具的延迟加载 (deferral)（若有）仍是客户端的选择。

这次调用像任何其他网关调用一样被记入 invocation 日志（谁 / 何时 / 耗时多久 / 结果如何，不含参数和返回内容——遵循 spec 001）。

## 后果

- 聚合在规模化后仍是净收益：agent 能搜索越过 30–50 工具悬崖，以极小的上下文代价调到正确的工具。
- 调用路径保持**可审计且不变**——被搜出的工具就是 agent 本就能调用的那些真实、带命名空间的工具，因此路由、curation（启用/禁用）和 invocation 日志全部照常适用，无需特殊处理。
- 新增的本地排序器对选择质量是承重的；它由 `tool_search` eval 套件覆盖（在排序器上做 recall@k / MRR——确定、本地，属于默认的 `python -m evals.run`），因此排序器改动不能悄悄回归。
- 无持久化设置、无迁移：让网关保持叠加式（而非加一个服务端 advertise/defer 模式）避免了在 `coffer.db` 中引入新状态。
- agent 必须*选择*去调用 `coffer__search_tools`（或客户端使用原生 tool-search）。对忽略它的 agent，完整目录依然在——这是优雅的、叠加式的兜底，而非硬依赖。

## 备选方案

- **一个 LLM 路由器（`coffer_use(intent)`，既选择*又*调用）。** 否决：它使成本和时延翻倍（每次工具使用都被一次二级模型调用包裹）；一个上下文匮乏的路由器在选择上弱于主模型——Copilot 自己的数据显示检索 **94.5% > 87.5%** 的 LLM 选择；它在调用路径里插入一个不透明、不可审计的跳；并且它破坏了 agent 自己的 ReAct 循环。对一个调用路径必须可读的 local-first、信任为中心的 vault 而言是错配。
- **服务端 defer-load / advertise-mode（在被搜索前对 `tools/list` 隐藏上游工具）。** 暂时否决：延迟加载本应是*客户端*的选择——例如 Claude Code 的 `tool_search_tool` 配 `defer_loading`——而服务端模式会需要一个持久化设置加一次迁移。让 Coffer 保持叠加式可以避免这些。只在缺少原生 tool-search 的客户端上才重新考虑。
- **仅靠静态命名空间 / 手动 curation。** 否决为不够：前缀和按工具的启用/禁用（spec 001）已存在且有帮助，但一个精挑过的集合仍可能超过 30–50 工具悬崖，且要求用户为每个任务手工修剪并不可扩展。检索是 curation 做不到的、按请求级的答案。
- **能力 B —— 一个 agentic 检索子 agent**，以及 **能力 C —— 对目录的 LLM memory curation。** 延后。它们的基准胜绩是相对「朴素地塞入所有工具」测出来的，而非相对「一个有能力的 agent 拿到一个小而排序过的结果集」。Coffer 的消费方本就是顶尖的 agentic 模型，且本地 vault 很小，所以那些胜绩尚不转移；若目录或消费方发生变化再重新考虑。

## 证据 / 参考 (Evidence / References)

- Anthropic —— Tool Search Tool：<https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool>
- Anthropic —— Advanced tool use（准确率 + token 缩减数据、custom tool search）：<https://www.anthropic.com/engineering/advanced-tool-use>
- RAG-MCP: Mitigating Prompt Bloat in LLM Tool Selection via Retrieval-Augmented Generation —— arXiv:2505.03275：<https://arxiv.org/abs/2505.03275>
- GitHub Copilot —— How we're making GitHub Copilot smarter with fewer tools（40→13；embedding 94.5% > LLM 87.5%）：<https://github.blog/ai-and-ml/github-copilot/how-were-making-github-copilot-smarter-with-fewer-tools/>
