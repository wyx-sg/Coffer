# Research —— 007 Memory Manager

> English: [research.md](./research.md)

## 1. Memory 框架

**问题**：哪个 Python 库做 Coffer 长期 agent 记忆的脊梁？

**候选**：

| Library                   | Strengths                                                                                   | Risks for Coffer                                                    |
| ------------------------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| **mem0**                  | 业界主流（~24k stars）；专为 agent memory 而生；干净的 `add/search/delete` API；与 LLM 解耦 | 默认配置指向 OpenAI；用户得显式选本地 Ollama；版本之间 API 抖过几次 |
| LangMem                   | LangChain 官方 memory 库；整体在 LangChain 上就特别合身                                     | 把 Coffer 提前锁进 LangChain 生态；独立使用度比 mem0 低             |
| Letta（前身 MemGPT）      | 研究背景硬                                                                                  | 是完整的 agent 框架，不止是 memory；会跟未来 LangGraph 选型打架     |
| Zep self-host             | 生产级、自带 UI                                                                             | 要 Postgres；对本地优先的单用户 app 来说运营面太重                  |
| LangGraph checkpointer    | 跟未来 agent runtime 同生态                                                                 | 为「会话内状态」设计，不是「跨会话持久记忆」                        |
| 自研（向量库 + facts 表） | 最大控制权                                                                                  | 等于把 mem0 已经做的事再做一遍                                      |

**Decision**：**mem0**（`mem0ai`）。它是专为 agent memory 而生、最主流的框架，匹配项目层面的「业界主流」原则。锁定风险通过下面三件事兜底：

1. mem0 关在 `coffer.infrastructure.memory.mem0_store.py`；importlinter Contract 8 强制。
2. `MemoryStore` 端口暴露 `add / search / list / get / update / delete / clear`。返回类型是 Coffer 的 `MemoryRecord` / `MemoryHit`，不是 mem0 的 `Memory`。

## 2. LLM provider

mem0 在写入时要调一个 LLM 来抽取事实。Coffer 的 local-first 不变式要求默认值不能是云端 API。

**Decision**：

- 按 memory store 配置（`MemoryStoreConfig.llm_provider`）：
  - `none`（默认）—— 读路径可用，`add_memory` 返回 503 并指向配置文档。
  - `ollama` —— 本地；默认端点 `http://localhost:11434`；模型名可配。
  - `openai` —— 云端；从 OS keychain 经 Coffer 既有 credentials 机制取 `OPENAI_API_KEY`。
- 创建后切换 provider 不允许，理由跟 KB 上「embedding 模型创建后不可变」一致（事实一致性）。

## 3. Embedding 模型

mem0 也会给 memory 做 embedding 以便检索。我们沿用 KB 的默认（`BAAI/bge-small-en-v1.5`），保持风格一致并共享 HF 缓存。mem0 默认的向量存储后端是 `qdrant` / `chroma`；我们显式配 mem0 用本地文件向量存储（mem0 的 `vector_store` 配置支持 SQLite + faiss / chromadb-in-memory 模式）。

**Decision**：embedding 模型 = `BAAI/bge-small-en-v1.5`（默认；按 store 可配）。向量后端 = mem0 内置的 `chromadb`，配成持久化到 `~/.coffer/memory/<store-name>/chroma/`。这样每个 memory store 在磁盘上自给自足。

## 4. Per-store 作用域（mem0 的 `user_id`）

mem0 的 API 在每次调用时都要传 `user_id`。在 Coffer（单用户）里，我们把这个字段映射成 memory store 的 name。每次对 store `<name>` 发起 `add` / `search` / `delete`，内部都给 mem0 传 `user_id=<name>`。端口完全隐藏这一切；对外只暴露 `MemoryStore.add(memory_store_name, text, actor)`。

## 5. 编辑 memory

mem0 支持 `Memory.update(memory_id, data=...)`。Coffer 端口暴露 `update(store_name, memory_id, new_text)`；adapter 调 mem0 的 update 并重算 embedding。审计记录改之前 / 改之后的文本。

## 6. 内置 MCP 工具

四个工具，挂在 `coffer__` 前缀下：

- `coffer__list_memory_stores()` → `[ {name, description, memory_count, embedding_model}, ... ]`
- `coffer__add_memory(store: str, text: str)` → `{ memory_id, text, status }`
- `coffer__search_memory(store: str, query: str, top_k: int = 5)` → `[ {id, text, score, created_at}, ... ]`
- `coffer__delete_memory(store: str, memory_id: str)` → `{ deleted: bool }`

调用被记录在 `mcp_invocations` 里，跟 KB 工具及上游 server 工具同一套；`resource_name` 用哨兵值 `"coffer"`。

## 7. 本规范**不**做的事

- memory 的 consolidation 运行（mem0 的「process」一步）。
- 跨 store 搜索。
- memory 的类别 / tag。
- 时间衰减打分。
- 超过 `actor in {"agent", "user"}` 的多 actor 作用域。

每一项都是一份干净的未来规范。
