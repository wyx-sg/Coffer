# Research —— 006 Knowledge Base Manager

> English: [research.md](./research.md)

本规范中几项关键技术选择的背景与理由。每节末尾给出 **决策**，并列出未选方案，让后续读者知道走过哪些岔路（以及为何不走），不必重复评估。

## 1. RAG 引擎库

**问题**：用哪个 Python 库做 Coffer 的切块、embedding、索引、检索骨干？

**评估候选**：

| 库                               | 类型           | 优点                                                      | 对 Coffer 的风险                                                                                                  |
| -------------------------------- | -------------- | --------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| **LlamaIndex**                   | 重型 RAG 框架  | 业界主流（约 37k stars）、文档最全、loader 最多、可换后端 | 2024 年重构两次（`Document/Node/Index/ServiceContext → Settings`）；抽象容易渗到 application 代码里，必须显式围墙 |
| Haystack 2.x                     | 重型 RAG 框架  | Pipeline / Component 模型比 LlamaIndex 干净               | 社区更小，开箱 loader 更少                                                                                        |
| LangChain RAG                    | 多用途框架     | 与 LangGraph（未来的 agent）同生态                        | 比 LlamaIndex 还重；被批过度抽象                                                                                  |
| txtai                            | 轻量一体化     | 一行 import、hybrid 内置、API 稳定                        | 偏小众 —— 资源 / 简历信号弱                                                                                       |
| LanceDB + fastembed              | 库组合         | 依赖最小；绕开框架锁定                                    | Coffer 要自己写 retriever、chunker、loader 胶水（约 200+ LOC）                                                    |
| ChromaDB + sentence-transformers | 库组合         | 流行的嵌入式向量 DB                                       | 不带内置 hybrid（BM25 + 向量）                                                                                    |
| sqlite-vec + FTS5                | 纯 SQLite 扩展 | 仅引入一个扩展，无新依赖                                  | 我们自己写得最多；loader 与编排全归我们                                                                           |

**决策**：**LlamaIndex（`llama-index-core`）**。用户明确把「业界主流」放在「抽象最少」之前，让项目对外部读者更直观。锁定风险的缓解：

1. 引擎限定在 `coffer.infrastructure.knowledge_base.llamaindex_store.py` 单一文件，由 Importlinter Contract 7 强制。
2. `KnowledgeBaseStore` 端口按 _Coffer 的需要_ 来表达（摄入一个文档、列文档、按 top-k 检索），不暴露 LlamaIndex 类型。未来换到 Haystack / txtai / 自家栈，只需重写这一个文件。
3. 锁到 `llama-index-core`（不引 meta-package），依赖面保持最小。

## 2. Embedding 模型

**问题**：默认 embedding 模型选哪个？怎么配置？

**候选**：

| 模型                     | 提供者                                  | 体积    | 备注                                                          |
| ------------------------ | --------------------------------------- | ------- | ------------------------------------------------------------- |
| `BAAI/bge-small-en-v1.5` | HuggingFace via `sentence-transformers` | ~130 MB | 英文检索质量好、CPU 成本低；2025 年很多 local RAG 的默认选项  |
| `BAAI/bge-m3`            | HuggingFace via `sentence-transformers` | ~570 MB | 多语言 + 多功能（dense + sparse + multi-vector）—— MVP 用不上 |
| `nomic-embed-text-v1.5`  | HuggingFace                             | ~270 MB | 长上下文（8k）；Apache 2.0；表现接近第一档                    |
| `text-embedding-3-small` | OpenAI API                              | n/a     | 云端 —— 与 Coffer local-first 默认不变量冲突                  |
| `mxbai-embed-large-v1`   | HuggingFace                             | ~670 MB | 质量更高、体积也大                                            |

**决策**：默认 = **`BAAI/bge-small-en-v1.5`**。理由：

- 在「广泛认为可用的检索质量」中体积最小、最快。
- Apache 2.0；与 sentence-transformers 同捆，无额外许可弹窗。
- CPU 上跑得轻松；首次加载从 HF Hub 下载。

embedding 模型 **逐 KB** 设置，记在 `KnowledgeBaseConfig.embedding_model` 中。一旦设定即不可变 —— 换模型会让既有 chunk 失效。需要换模型的用户应新建 KB。

我们允许用户指定 _任何_ sentence-transformers 接受的 HuggingFace 模型 id，不做白名单；校验器仅检查非空 + 形如 `org/name`。

## 3. 切块策略

**问题**：如何把文本切成 chunk 再 embed？

**决策**：用 LlamaIndex 的 `SentenceSplitter`，默认 `chunk_size=512` token、`chunk_overlap=64` token。两项均可逐 KB 配置。

理由：

- 默认模型 512-token 最大窗口下，512 token 的 chunk 既有语义完整性又有界。
- 64-token overlap 减少「事实跨边界丢失」。
- splitter 行为可解释、可重复，LlamaIndex 文档也推荐用于通用摄入。

语义 / 层级 / 源码感知切块器对 MVP 体量不划算 —— 引入模型调用成本与复杂度，与预期 corpus 规模不匹配。

## 4. 磁盘布局

**问题**：原始文件与索引落在哪？

**决策**：

```
~/.coffer/
  kb/
    <kb-name>/
      raw/
        <document_id>.<original_ext>   # 由 SHA-256 推导的 id；保留原始扩展名
      index/
        ... (LlamaIndex persist 目录)
      meta.json                         # 可选的人类可读 manifest
```

理由：

- 宪法要求「批量用户内容存为本地文件系统上的文件」，原始文件直接落地满足这条。
- 索引就近落在 raw 旁，使得每个 KB 是一个自包含目录 —— 容易备份、容易删除（一次 `rmtree`）。
- 逐 KB 目录让磁盘审计变简单（`du -sh kb/<name>`）。
- LlamaIndex 把索引落成 JSON + 一个向量存储文件；默认 `SimpleVectorStore` 写到 persist 目录，无须外置向量 DB 进程。

## 5. 文档标识符

**问题**：document id 用什么？

**决策**：内容 SHA-256 哈希的前 16 个十六进制字符（与去重判断使用的同一个值）。示例：

- 文件 `notes/design.md` 含 4 KB markdown → `document_id = "8a3f…1c2b"`（16 字符）。
- 重新摄入 _相同字节_ → 同 id → 默认拒绝，除非加 `--replace`。

理由：

- 内容寻址：相同字节 → 相同 id，与文件名无关。
- 满足「不做意外持久化」：id 是派生出来的，不是序列分配的。
- 16 字符在预期 KB 规模（≤ 500 篇）下不会碰撞。

原始文件名以 metadata 列（`filename`）存着；document_id 才是 join 键。

## 6. PDF 抽取

**决策**：`pypdf`（BSD-3）。纯 Python，无需 JVM 依赖（不像 Apache Tika），覆盖典型 PDF 的 90%+，是 Python 生态里推荐的入门 PDF 工具。抽取失败 → 明确拒绝；用户自行转文本后再摄入。

OCR 不在范围内。

## 7. 内置 MCP 工具面

**问题**：Coffer 的 MCP 网关如何把 KB 能力暴露给已接入的 MCP 客户端？

**决策**：三个工具，挂在保留前缀 `coffer__` 下：

- `coffer__list_knowledge_bases() -> [ {name, description, document_count, embedding_model}, ... ]`
- `coffer__search_knowledge_base(kb: str, query: str, top_k: int = 5) -> [ {text, document_id, filename, score, position}, ... ]`
- `coffer__get_document(kb: str, document_id: str) -> { document_id, filename, text, size_bytes }`

它们出现在 **每个** MCP 客户端的 `tools/list` 返回中，与上游 MCP server 工具并列。`coffer__` 是保留前缀（mcp_server 注册时若 server name 为 `coffer` 会被明确拒绝）；上游工具命名形如 `<server_name>__`，不可能产生 `coffer__` 开头。

内置工具调用与上游工具调用一样写入 `mcp_invocations` 表，`resource_name` 列填入哨兵值 `"coffer"`。保留与审计逻辑统一适用。

## 8. 逐 KB asyncio 锁

同一 KB 的并发摄入会在 LlamaIndex 写索引阶段相互竞争。决策：每个 KB 一个 `asyncio.Lock`（懒创建、在 store adapter 中弱引用），仅在摄入 / 删除的索引变更阶段持有。检索是只读的，不加锁 —— LlamaIndex 的内存 store 能处理并发读。

## 9. 这里明确未决的事

- 未来是否换到本地 Qdrant 向量存储。plan 中已列入 out of scope；待 corpus 规模真有需要时再评估。
- 源码感知切块器。
- 增量重建索引开关。
- 「监听某个文件夹」的自动摄入源。

每一项都可以是后续清爽的独立规范；当前端口面已设计成不需要为它们重新建模。
