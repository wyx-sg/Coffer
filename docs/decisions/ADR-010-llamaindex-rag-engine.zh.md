# ADR-010：RAG 引擎 —— LlamaIndex 藏在 application 端口背后

> English: [ADR-010-llamaindex-rag-engine.md](./ADR-010-llamaindex-rag-engine.md)

**Status**: Accepted
**Date**: 2026-05-29
**Deciders**: Yuxing Wu
**Related**: spec `006-knowledge-base`（FR-014、SC-006、research.md §1），[ADR-002](ADR-002-code-layout-layer-first.md)，[ADR-008](ADR-008-everything-is-a-resource-kind.md)

## Context

Spec `006-knowledge-base` 引入了 `knowledge_base` 这个资源 kind：每个 KB 持有用户明确加入的文档，按落盘的 chunk / embed / index 处理，并通过 top-k 检索调用提供搜索。Agent 经由 Coffer 的 MCP 网关（三个内置 `coffer__*` 工具）触达这份语料，因此 daemon 实际上要带一份小型 RAG 引擎上路。

一个 RAG 引擎不是小零件：它持有切块策略、embedding adapter、索引数据结构（内存或磁盘）、retriever、持久化，以及把它们串起来的生命周期。Coffer 在这一选择上有两股互相拉扯的压力：

1. **Local-first + 依赖足迹要小。** Constitution 禁止云端事实记录方。默认安装必须能在开发者笔记本上端到端跑通：不出网、不要 GPU、依赖面要紧。会拖进十几个可选子包的「重型框架」SDK 并不合适。
2. **能给简历加分的主流方案。** Coffer 是一个个人 fit / 开源项目；挑一个小众库虽然技术上更简单，但读代码或评估这个项目的人需要额外学习一个不熟的库，可读性掉得很快。

任何一股压力单独看都有显而易见的答案；两股压力放在一起就互相打架。

## Decision

**选 `llama-index-core` 做 RAG 引擎，把它关在一个 infrastructure adapter 里，对外只暴露一个 kind 自己拥有的小端口（`KnowledgeBaseStore`）。**

具体形态：

- 端口落在 `coffer.domain.knowledge_base.store`，按 _Coffer 的需要_ 来定义：`open(kb_name, config)`、`ingest(kb_name, document, text) -> int`、`delete_document`、`search(kb_name, query, top_k) -> Sequence[Passage]`、`drop`、`close`。Protocol 里**不暴露**任何 LlamaIndex 的类型。
- 真实 adapter 是 `coffer.infrastructure.knowledge_base.llamaindex_store`。整个代码库里**只有这一个文件**被允许 `import llama_index.*`。
- 测试里有一个 `FakeKnowledgeBaseStore`；整个 `application/` 与 `domain/` 的测试面都跑在 fake 之上，未来换引擎不会动到测试金字塔。
- 一条新的 importlinter 契约（`backend/pyproject.toml` 中的 Contract 7）强制这条隔离线：`coffer.application.*` 与 `coffer.domain.*` 不得 import `llama_index*`。一旦谁打破，CI 立刻挂。
- 依赖锁定到 `llama-index-core`（不引 meta-package）；默认 embedding integration 是 `llama-index-embeddings-huggingface` + `sentence-transformers` + 本地模型 `BAAI/bge-small-en-v1.5`。

## Consequences

**正面**

- Coffer 用上主流 RAG 栈，又不必维护自家的 chunker/retriever 胶水。
- 未来要升级（或换到 Haystack / txtai / sqlite-vec）只动**一个文件**。契约保证不会有隐性耦合悄悄长出来。
- 依赖面是有界的：只引 `llama-index-core` + 一个 embedding 集成包。LlamaIndex 那堆可选子包（LLM adapter、云检索、ingestion-as-a-service）都不会进 lockfile。
- 引擎挂了不会拖垮 daemon：如果引擎或其模型加载失败，daemon 仍然能起；只有 ingest 与 search 接口返回 503（FR-015）。

**负面**

- LlamaIndex 历史上动过核心 API（2024 年两次 refactor：Document/Node/Index/ServiceContext → Settings）。未来每次升级都可能动 adapter 文件。我们靠 (a) adapter 是单文件、(b) 端口形状由我们定、(c) `pytest.importorskip("llama_index.core")` 守护的集成测试在 CI 时就能抓住兼容性问题来兜底。
- 首次 `coffer kb ingest` 要从 HuggingFace Hub 下载约 130 MB 的 embedding 模型。这一点写在 quickstart 里，并提供 `coffer kb warmup` 给离线 / 安装器场景做预热。
- LlamaIndex 本身体量不小，依赖树比手搓方案大。我们接受这个代价，换来开箱即用的 loader、retriever 与 reranker hook。

## Alternatives Considered

[`specs/006-knowledge-base/research.md` §1](../../specs/006-knowledge-base/research.md) 评估了五条备选路线，被否的理由概述如下：

**Haystack 2.x** —— Pipeline 模型比 LlamaIndex 更干净，但社区更小，开箱可用的 loader 也明显更少。从「主流 / 简历信号」角度看，技术上的优雅不抵这一项。

**LangChain RAG** —— 跟 LangGraph（Coffer 未来很可能用到的 agent runtime）出自同一个生态，听起来诱人。最终被否：LangChain 的 RAG 子模块比 LlamaIndex 还重，且业内对它的「过度抽象」名声更响。Constitution 的「能少抽一层就少抽」原则把它压下。

**txtai** —— 轻量、内置 hybrid 检索、一行 import 全搞定。被否的理由跟 Haystack 一样：太小众，新读者和潜在协作者得额外学一个不熟的库才能在 `infrastructure/knowledge_base/` 下导航。

**LanceDB + fastembed** —— 库组合，依赖最小。代价是 Coffer 要自己写 retriever / chunker / loader 胶水（约 200+ LOC 的内部编排）。省下的依赖体积不值得拿来再实现一遍 LlamaIndex 已经送给我们的东西。

**ChromaDB + sentence-transformers** —— 流行的嵌入式向量 DB，但缺内置的 hybrid（BM25 + 向量）检索。MVP 我们不需要 hybrid，但缺一条连贯的端到端 pipeline 意味着编排层还是得自己拼。

**sqlite-vec + FTS5** —— 除一个 SQLite 扩展外不引入任何新依赖。被否的理由是：所有东西都得自己写 —— loader、chunker、retriever、持久化 —— 一份原本一周的规范会被拖成数周。等规模或「零依赖」策略真的要求时再回头评估。

## 隔离 / 锁定缓解汇总

importlinter 的 Contract 7 + kind 自己持有的端口 + 全部跑在 fake 上的测试金字塔 + 单文件 adapter，构成了对 LlamaIndex 锁定的缓解组合。换引擎的成本被限定在「重写一个文件 + 更新 `pyproject.toml` 里一行 embedding 集成依赖」。application 与 domain 代码不变。
