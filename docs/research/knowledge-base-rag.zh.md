# 竞品调研 —— 面向 Agent 的本地优先知识库 / RAG

> 中文版：本文件 · English: [knowledge-base-rag.md](./knowledge-base-rag.md)
>
> 面向 Coffer 知识库（spec 006，ADR-012）的内部竞品调研报告。**日期：** 2026-06-16。
> **方法：** deep-research harness（本轮还读了 Coffer 自身 KB 代码以核对对比）。
>
> **✓ 覆盖缺口已补齐。** 第一轮深入了 txtai、Open WebUI Knowledge、RAGFlow、Cognee 和两个
> SQLite-FTS5+sqlite-vec 同构项目；一次针对性补跑随后覆盖了它漏掉的五个工具——**AnythingLLM、
> Onyx（Danswer）、Khoj、Morphik、LlamaIndex**——并进下文 §5。

## 1. 全景速览

本地优先 RAG 按**真相源在哪**和**采集管线多重**分类：

| 类别                        | 真相在                          | 例子                                        |
| --------------------------- | ------------------------------- | ------------------------------------------- |
| **文件为真相 + 可重建索引** | 原始/markdown 文件；DB 可丢弃   | **Coffer**、obsidian-hybrid-search、AIngram |
| **DB 为真相**               | 一份解析后的语料 / 向量库是权威 | RAGFlow、Cognee、txtai                      |
| **应用托管的集合**          | 应用工作区拥有文档              | Open WebUI Knowledge、AnythingLLM、Onyx     |

### 各玩家（第一轮）

- **txtai**（`neuml/txtai`，OSS）—— 一体化本地优先 embeddings DB（稀疏 + 稠密 + 图 + SQL）；
  检索经 BM25 / 混合 / SQL / 图（openCypher）；默认 embedding `all-MiniLM-L6-v2`；agent 经
  REST / **MCP** / Python 访问。[3-0 确认]
- **Open WebUI Knowledge** —— **5 个内容抽取引擎**（Tika、Docling、Azure、Mistral OCR、自定义）；
  混合检索 = BM25 + 向量 + **cross-encoder 重排**；原生工具 `query_knowledge_files` /
  `grep_knowledge_files` / `view_file` / `kb_exec`；哈希引用。[确认]
- **RAGFlow**（`infiniflow/ragflow`，OSS）—— 最深的采集：默认 **DeepDoc 视觉 OCR + 表结构 +
  文档版面**识别 + 可插拔解析器（四个 _Experimental_）。混合检索（关键词阈值 0.2，向量权重 0.3）。
  **关键：embedding 在分块后按 dataset 锁定。** [3-0 确认]
- **Cognee**（`topoteretes/cognee`，Apache-2.0）—— **可写**的向量 + 知识图记忆；更偏记忆而非 KB。
- **镜像 Coffer 精确技术栈的 SQLite-FTS5 + sqlite-vec 同构项目** —— **obsidian-hybrid-search**
  （文件权威、可重建；BM25 加权 标题 10× / 别名 5× / 正文 1× + 向量 + 模糊，经 **RRF** 融合；
  MCP `search`/`read`/`reindex`/`status`）和 **AIngram**（一个 SQLite 文件即真相；FTS5 +
  sqlite-vec + 图经 RRF 融合；本地 `nomic-embed` ONNX 768 维，**无外部 embedding API**）。
  [3-0 确认] FTS5 `bm25()` rank 是**负数**；sqlite-vec 做 KNN 但**不做** embedding；两个同构
  项目都用 **Coffer 没有的加权 RRF**。

## 2. 能力对比（第一轮）

| 能力            | txtai         | Open WebUI       | RAGFlow             | obsidian/AIngram | **Coffer KB**                                          |
| --------------- | ------------- | ---------------- | ------------------- | ---------------- | ------------------------------------------------------ |
| 真相源          | embeddings DB | 应用集合         | 解析 DB             | **文件**         | **`docs/<id>.md` 文件 + `raw/`**                       |
| 可重建索引      | 部分          | —                | 需重分块            | ✅               | **✅ `coffer reindex`**                                |
| 采集 / OCR      | 基础          | 5 引擎含 OCR     | DeepDoc 视觉 OCR    | 仅 markdown      | **仅 MarkItDown**                                      |
| 关键词（BM25）  | ✅            | ✅               | ✅                  | ✅ FTS5          | **✅ FTS5 bm25()**                                     |
| 向量            | ✅            | ✅               | ✅                  | ✅ sqlite-vec    | **✅ sqlite-vec（可选）**                              |
| 混合融合（RRF） | ✅            | ✅               | ✅                  | **✅ RRF**       | **❌ 各模式分离**                                      |
| 重排            | —             | ✅ cross-encoder | ✅                  | —                | **❌**                                                 |
| 换 embedding    | 容易          | 容易             | **按 dataset 锁定** | 重新嵌入         | **✅ 经 reindex 轻松**                                 |
| agent 访问      | REST/MCP/Py   | 原生工具         | REST                | MCP              | **只读 MCP 工具（list/search/grep/read）+ 自主 `ask`** |
| agent 可写      | 是            | 是               | 是                  | 否               | **否（只读）**                                         |

## 3. Coffer 对比

**Coffer 有竞争力或领先之处。**

1. **文件为真相 + 索引可轻松重建是真实优势。** RAGFlow、Cognee、txtai 让解析后的 DB 成为权威；
   RAGFlow 甚至**在分块后锁定 embedding 模型**。Coffer 的 `docs/<id>.md` + `raw/` 真相 + 可丢弃
   SQLite 索引让换 embedding 或重建索引变得轻松（`coffer reindex`）。
2. **只读 + 经 MCP 访问是金库的正确安全姿态。** Coffer 暴露细粒度只读 MCP 工具，并在其上叠加自主
   `ask`（ADR-024）；agent 从不写 KB。（相比之下 Cognee 可写。）
3. **SQLite-FTS5+sqlite-vec 同构项目验证了整套架构。**

**Coffer 落后 —— 具体借鉴。**

1. **无混合融合（RRF）。** Coffer 把 grep / 关键词 / 向量当作*分离*模式；每个认真的同类
   （Open WebUI、RAGFlow、obsidian-hybrid-search、AIngram——以及下文的 LlamaIndex + Onyx）
   都用**倒数排名融合**融合关键词 + 向量。价值最高、成本最低的借鉴。
2. **无重排。** Open WebUI 和 RAGFlow（以及下文 Khoj/Onyx/AnythingLLM）在检索后加 cross-encoder
   重排；Coffer 没有。
3. **采集偏浅。** Coffer 仅 MarkItDown；RAGFlow 的 DeepDoc、Open WebUI 的 5 引擎、以及（下文）
   Morphik/LlamaParse 做真实 OCR/版面抽取。Coffer 的 `MarkdownConverter` port 已存在——把引擎
   做成可插拔挂其后。
4. **单一 embedding client。** 一个本地 ONNX 选项能移除对 OpenAI 兼容 API 的依赖，做到完全离线。

## 4. 给 Coffer 的关键结论

1. **加入 RRF 混合融合** —— 最清晰的单一缺口；LlamaIndex 的
   `QueryFusionRetriever(mode="reciprocal_rerank")` 是具体参考。
2. **加入可插拔重排器**（cross-encoder）—— Khoj/Onyx 默认就带。
3. **把采集/OCR 做成可插拔挂在既有 `MarkdownConverter` port 后**（DeepDoc/Docling/Mistral-OCR/
   ColPali 级引擎）。
4. **提供本地 embedding 选项**（ONNX）—— 受访的*全部十个*同类都有；这是最强、最普遍的信号。
5. **保留文件为真相 + reindex** —— 相对 DB-为真相/锁定-embedding 的竞品这是真实优势，作为头条。

## 5. 补跑 —— 另外五个本地 RAG 系统（缺口补齐）

一次针对性补跑覆盖了第一轮漏掉的五个主流工具。五者**2026 年均活跃维护**，且**五者都提供真正的
本地 embedding 选项**。

| 工具                | 混合 RRF 融合                                  | 重排                  | 深度 OCR / 视觉解析        | 本地 embedding      | MCP 访问           | 许可证                |
| ------------------- | ---------------------------------------------- | --------------------- | -------------------------- | ------------------- | ------------------ | --------------------- |
| **LlamaIndex**      | ✅ `QueryFusionRetriever`（reciprocal_rerank） | ✅                    | LlamaParse（云锁）         | ✅                  | 经集成             | OSS                   |
| **Onyx**（Danswer） | ✅ BM25+向量                                   | ✅ 可选               | ❌ 连接器抽文本            | ✅ 本地 embed 服务  | 未取证             | OSS                   |
| **Khoj**            | bi-encoder → 重排                              | ✅ 默认 cross-encoder | ❌                         | ✅ 默认 `gte-small` | —                  | OSS                   |
| **Morphik** Core    | —                                              | —                     | ✅ **ColPali（OCR-free）** | ✅                  | ✅ **morphik-mcp** | **BSL 1.1**（源可见） |
| **AnythingLLM**     | —                                              | ✅（仅 LanceDB）      | ❌                         | ✅ ONNX/all-MiniLM  | —                  | OSS                   |

- **LlamaIndex** 是 RRF 的具体参考：`QueryFusionRetriever(mode="reciprocal_rerank")` 融合
  BM25 + 向量——正是 Coffer 缺的融合。**LlamaParse** 加版面感知多模态 markdown（云/企业锁）。[确认]
- **Khoj** 默认两段式 检索→重排（bi-encoder `thenlper/gte-small` → cross-encoder
  `mixedbread-ai/mxbai-rerank-xsmall-v1`，可换；自托管时完全本地）——干净的本地重排模板。[3-0 确认]
- **Onyx** 完全本地 / 可气隙运行，混合 BM25+向量 + 可选重排 + 本地 embedding 服务 + 40 个连接器
  （增量同步，默认 30 分钟刷新）。[3-0 确认]
- **Morphik** Core 在两件 Coffer 相关的事上突出：OCR-free 深度**视觉**解析（ColPali 对 PDF/图/视频
  做页面图像嵌入）和**一等 MCP server（`morphik-mcp`）**——最贴近 Coffer 的"agent 只读经 MCP"KB。
  _注意：_ **BSL 1.1**，非 OSI 开源（发布约 4 年后转 Apache-2.0；年收入 $2K/月以下免费商用）。[3-0 确认]
- **AnythingLLM** 有重排但仅与 LanceDB 耦合；原生 ONNX（all-MiniLM）+ GGUF 本地 embedding。

**这坐实并锐化了四个借鉴：**（a）**RRF 融合**现有具体参考（LlamaIndex）；（b）**重排**在 Khoj/Onyx
默认即带——本地 cross-encoder 是模板；（c）**深度/视觉解析**（Morphik ColPali、LlamaParse）是
可插拔 OCR 借鉴的高端；（d）**本地 embedding 选项**在所有受访系统中普遍存在——Coffer 该加它的最强
信号。**Morphik 的 `morphik-mcp` 也验证了 Coffer 的 agent-只读-经-MCP 的 KB 设计。**

## 6. 来源

第一轮：

- github.com/neuml/txtai · neuml.github.io/txtai/api/mcp
- docs.openwebui.com/features/workspace/knowledge · deepwiki.com/open-webui（内容抽取引擎）
- github.com/infiniflow/ragflow/blob/main/deepdoc/README.md · ragflow.io/docs/select_pdf_parser · …/configure_knowledge_base
- github.com/topoteretes/cognee
- github.com/flowing-abyss/obsidian-hybrid-search · github.com/bozbuilds/AIngram
- alexgarcia.xyz/blog/2024/sqlite-vec-hybrid-search · sqlite.org/fts5.html

补跑：

- github.com/morphik-org/morphik-core · github.com/morphik-org/morphik-mcp · arxiv.org/abs/2407.01449（ColPali）
- docs.onyx.app（连接器、search_configs、自托管数据处理）· github.com/onyx-dot-app/onyx · blog.vespa.ai/why-danswer-users-vespa
- github.com/khoj-ai/khoj（embeddings.py、text_search.py、SearchModelConfig）
- LlamaIndex 文档 —— QueryFusionRetriever（reciprocal_rerank）、LlamaParse
- github.com/Mintplex-Labs/anything-llm

已核对 Coffer 代码：backend/coffer/application/knowledge_base/service.py · builtin_tools.py
