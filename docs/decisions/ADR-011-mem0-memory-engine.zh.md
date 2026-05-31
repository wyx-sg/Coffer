# ADR-011：Memory 引擎 —— mem0 藏在 application 端口背后

> English: [ADR-011-mem0-memory-engine.md](./ADR-011-mem0-memory-engine.md)

**Status**: Accepted
**Date**: 2026-05-29
**Deciders**: Yuxing Wu
**Related**: spec `007-memory`（FR-011、FR-012、FR-014、SC-006、research.md §1 §2），[ADR-002](ADR-002-code-layout-layer-first.md)，[ADR-008](ADR-008-everything-is-a-resource-kind.md)，[ADR-010](ADR-010-llamaindex-rag-engine.md)

## Context

Spec `007-memory` 引入了 `memory` 这个资源 kind。每个 memory store 是一个 `Resource`（kind 为 `memory`），承载由编码 agent（通过 Coffer 的 MCP 网关）或用户写入的短小、派生事实，并通过内置的 `coffer__*` 工具回吐给 agent。它与 `knowledge_base`（spec 006）截然不同：KB 装的是用户上传的文档，memory 装的是短的派生事实（≤ 8 KB）。

「长期 agent 记忆」不是小零件。它通常要在写入时调一次 LLM 做事实抽取、再走一次 embedding、维护一个向量索引以便召回、配一套 dedup / merge 策略、还要给「按用户 / 按 actor」分作用域留口子。Coffer 在这里又遇到 ADR-010 同样的两股拉扯：

1. **Local-first + 依赖足迹要小。** 默认安装不能出网；不能拖一个独立的服务进程；不能强迫用户连云端 provider。
2. **能给简历加分的主流方案。** 选的名字要让读者一眼认得出，而不是再扔一个不熟的库给协作者去学。

Memory 比 RAG 引擎多出一条硬约束：**写入时必须调一个 LLM**。所以「选哪个框架」没法跟「LLM provider 怎么配」分开评估。

## Decision

**选 `mem0ai` 做 memory 引擎，关在一个 infrastructure adapter 里，对外只暴露一个 kind 自己拥有的小端口（`MemoryStore`）。LLM provider 在每个 memory store 上由用户自己配；默认值是 `none`（只读）。**

具体形态：

- 端口落在 `coffer.domain.memory.store`，按 _Coffer 的需要_ 来定义：`open(store_name, config)`、`add(store_name, text, actor) -> MemoryRecord`、`get`、`list`、`update`、`delete`、`clear`、`search(store_name, query, top_k) -> Sequence[MemoryHit]`、`drop`、`close`。Protocol 里**不暴露**任何 mem0 的类型。
- 真实 adapter 是 `coffer.infrastructure.memory.mem0_store`。整个代码库里**只有这一个文件**被允许 `import mem0`（含任何子模块）。
- 测试里有一个 `FakeMemoryStore`；整个 `application/` 与 `domain/` 的测试面都跑在 fake 之上。
- 一条新的 importlinter 契约（`backend/pyproject.toml` 中的 Contract 8）强制这条隔离线：`coffer.application.*` 与 `coffer.domain.*` 不得 import `mem0*`。一旦谁打破，CI 立刻挂。
- mem0 每次调用必须传的 `user_id` 被映射成 memory store 的 name（Coffer 单用户、多 store 分作用域）。
- `MemoryStoreConfig.llm_provider` 默认 `"none"`，所以新装的 Coffer 不会向任何云端或本地 LLM 写入；用户按需在每个 store 上把它改成 `"ollama"`（本地）或 `"openai"`（云）。provider / model / endpoint / credential ref 在 store 创建后**不可变** —— 要换 provider 就建新 store（事实一致性，跟 KB 上「embedding 模型不可变」一脉相承）。

## Consequences

**正面**

- Coffer 用上主流 memory 栈，又不必维护自家的抽取 / 检索 / dedup 胶水。
- 未来要升级（或换到 LangMem / Letta / 自家实现）只动**一个文件**。Contract 8 保证不会有隐性耦合悄悄长出来。
- 引擎挂了不会拖垮 daemon：如果 mem0 或其 embedding 模型加载失败，daemon 仍然能起；只有 memory 读写接口返回 503（FR-012）。
- `none` 作为 LLM provider 的默认值守住了 local-first：新装的 Coffer 不会因为这条 feature 自动产生任何外发调用，除非用户显式配（FR-013 / FR-014）。

**负面**

- mem0 在 2024 年间多次动过 API。未来每次升级都可能动 adapter 文件。我们靠 (a) adapter 是单文件、(b) 端口形状由我们定、(c) `pytest.importorskip("mem0")` 守护的集成测试在 CI 时就能抓住兼容性问题来兜底。
- mem0 会传递性拖进可选的 LLM 客户端包（默认带上 OpenAI 客户端）。换它的框架能力（事实抽取、dedup 逻辑）值这个代价。
- 「写入时必须调 LLM」对首次用户是真实的摩擦。这一点写在 `quickstart.md` 里，并把 `--llm-provider ollama` 推荐为零成本的本地默认。
- `llm_provider` 不可变意味着用户必须新建一个 store 才能换 provider；本规范不实现 export-import。这一点写在 `spec.md` 的 FR-001 与 `quickstart.md` 里。

## Alternatives Considered

[`specs/007-memory/research.md` §1](../../specs/007-memory/research.md) 评估了六条备选路线，被否的理由概述如下：

**LangMem** —— LangChain 官方 memory 库；如果整体已经在 LangChain 上，会非常合身。被否的理由是：会把 Coffer 提前锁进 LangChain 生态（agent runtime 的选型还没定），而它在 LangChain 之外的独立使用度比 mem0 低得多。

**Letta（前身 MemGPT）** —— 研究背景很硬，但 Letta 是一个完整的 agent 框架，不止是 memory。采用它等于提前替未来的 agent runtime 选型做决定，会跟我们倾向的 LangGraph 方向打架。

**Zep（self-host）** —— 生产级、自带 UI。被否的理由是：要 Postgres、要单独跑一个服务进程 —— 对一个本地优先、单用户的桌面 app 来说运营面太重。

**LangGraph checkpointer** —— 跟我们倾向的未来 agent runtime 同生态。被否的理由是：它是为「会话内状态」设计的（给一次图遍历打 checkpoint），不是为跨会话的、持久的事实记忆。

**自研（向量库 + facts 表）** —— 最大控制权；约 300 LOC 的内部编排（抽取 prompt、dedup、retriever、持久化）。被否的理由跟 ADR-010 里否掉 LanceDB 那条一样：省下的依赖体积不值得拿来再实现一遍 mem0 已经送给我们的东西，且一人团队没法在 Coffer 的其它面上之外再扛起一份自研记忆逻辑。

**不做引擎（砍掉这条 feature）** —— 显式评估过：Coffer 干脆不做 memory，让 agent 自己靠 in-context 记忆。被否的理由是：跨会话召回**就是** `memory` 这条 feature 的全部用户价值；没它，这条 feature 相对 agent 已经能做的事就什么都不剩（见 spec.md User Story 1 「Why this priority」）。

## 隔离 / 锁定缓解汇总

importlinter 的 Contract 8 + kind 自己持有的端口 + 全部跑在 fake 上的测试金字塔 + 单文件 adapter，构成了对 mem0 锁定的缓解组合。换引擎的成本被限定在「重写一个文件 + 更新 `pyproject.toml` 里一行 `mem0ai` 依赖」。application 与 domain 代码不变。`llm_provider` 的枚举也刻意保持收窄（`none` / `ollama` / `openai`）；加 `anthropic` 或任何新 provider 都是一次有意为之的后续，需要同时改 adapter 与 schema。
