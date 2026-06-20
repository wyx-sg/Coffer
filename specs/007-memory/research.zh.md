# Research —— 007 Memory（跨 agent 共享记忆）

> English: [research.md](./research.md)

## 1. 为何放弃 mem0（与每 agent 的 silo 模型）

**问题**：memory 应继续用 mem0（写入时调 LLM 做事实抽取 + 向量库）吗？

**决定**：**不。** 三个问题驱动了重设计：

1. **写入时调 LLM 是摩擦** —— 当消费者本身已是能自己决定记什么、并写出干净事实的 LLM 时。mem0 默认 `llm_provider="none"` 让 `add_memory` 返回 503 —— 这条 feature 开箱即不可用。
2. **KB 与 memory 是近重复代码**，但它们是同一光谱上的两点（「agent 检索的 markdown」）。现在共用一套底座。
3. **memory 是会漂移的每 agent 私有 silo** —— 同一条项目事实最终被复制并在 Claude 记忆目录、Codex memories 等之间漂移。

**替代**：memory = **跨 agent 的单一真相源**，在格式匹配处做到 agent 原生。mem0 / chroma / LlamaIndex 全部移除。

## 2. 规范化格式 —— 每条事实 markdown + `MEMORY.md`

**问题**：落盘的真相是什么？

**决定**：每条事实一个 markdown 文件，带 YAML frontmatter（`name`、`description`、`metadata.type`、`metadata.actor`、`origin_session_id`）+ markdown 正文，加一个 `MEMORY.md` 索引（`- [name](file.md) — description`）。这就是 **Claude Code 的 auto-memory 格式**，采用它作为规范化格式，使 Claude 投影为原生目录 symlink。文件是真相源；SQLite 是可重建的索引。`MEMORY.md` 是 Coffer 重生的派生索引 —— 任何写入者都触发幂等重生，因此 Claude 自己对 `MEMORY.md` 的写入会被无害覆盖。

## 3. 两层作用域

**问题**：个人事实与 repo 事实如何分离？

**决定**：两种作用域。

- **Global** —— `project_id = WORKSPACE_GLOBAL_PROJECT_ID`（既有 sentinel `00000000000000000000000000`；复用、不重铸）。一个 store 在 `~/.coffer/memory/global/`。
- **Per-project** —— `project_id = <项目 ULID>`。每项目一个 store 在 `~/.coffer/memory/projects/<ulid>/`。

`remember(scope=project)` → 项目 store；`scope=global` → sentinel store；`recall` 默认 → 两者。

## 4. 从 agent 的 cwd 解析作用域

**问题**：daemon 怎么知道某次会话在哪个项目里？

**决定**：coffer-mcp-shim 在 agent 的 cwd 中启动，并在 **会话握手时上报 cwd**。daemon 计算 git-root（与 Claude 项目 slug 同一依据）并解析（缺失则惰性置备）per-project 记忆 store。若 cwd 不在某个 git 项目里，`scope=project` 被拒（`ScopeUnresolved`），`scope=global` 仍可用。**实现期需验证**：Claude Code 与 Codex 上的 MCP server cwd 传播（设计 open item #1）。

## 5. 共享机制 —— 混合式（MCP + 原生投影）

**问题**：这个单一 store 如何真正共享进每个 agent？

**决定**：混合式。

- **所有 agent 用 MCP** —— 每个 agent 经 Coffer 网关工具读写。
- **原生投影** —— 一个 `AgentMemoryAdapter`（随 agent driver、而非 memory kind）把规范化内容落进原生位置：
  - **Claude Code** = 把规范化项目记忆目录作为目录 **SYMLINK** 投进 `~/.claude/projects/<slug>/memory/`（原生、双向；保持 auto-memory 开启 —— 它 _就是_ 规范化内容）。
  - **Codex** = 把一个带标记栅栏的 managed block（`<!-- coffer:memory:start -->…<!-- coffer:memory:end -->`）**RENDER** 进 `<project>/AGENTS.md`（project 层）与 `~/.codex/AGENTS.md`（global 层）；禁用 Codex 原生 `memories`，使第二份副本不累积。

投影引擎按 `projection_mode`（`SYMLINK` | `RENDER` | `NONE`）分派。**新增一个 agent = 一个 adapter，不改核心。** adapter 执行所有原生文件改动；memory 底座只提供规范化文件 + 已渲染 markdown，保持 memory 与 agent 无关、L1 config 边界干净。

**首次投影时的迁移**：若 Claude 的记忆目录已有真实文件，先把它们合并进规范化，再替换为 symlink —— 绝不静默覆盖。managed-block 重渲染是幂等的。

## 6. 检索 —— 共享引擎、lazy reindex-on-read

**问题**：recall 怎么实现、怎么保持新鲜？

**决定**：与 KB 相同的检索引擎：`grep`（ripgrep 扫文件）、`keyword`（SQLite FTS5 + BM25，零配置默认）、`vector`（sqlite-vec + 可配置 embedding provider，可选）。当请求 `vector` 但 embedding 未配置时，回退到 `keyword` 并在响应里标注 —— 绝不阻塞。

memory 用 **lazy reindex-on-read**：`recall` 先按 `content_sha256` 扫描这个小事实目录的增量，并在搜索前对账索引。这使 Claude 的 symlink 编辑与任何直接磁盘编辑对所有 agent 即时可见，**无需文件系统 watcher**。（相比之下 KB 在 Coffer 中介编辑 + 显式 `coffer kb reindex` + 一个默认关闭的可选 watcher 时重建索引。）

**store 列表**的 `fact_count`（KB14，见 006 research §12）读取索引 `count_documents`，而非 `scan_store_dir` 扫描 fact 文件——任何索引-vs-磁盘的过期都会在上述下一次 recall/reconcile 时关闭。每个 store 的 `/metrics` 详情端点仍扫描并遍历磁盘以得到 `disk_bytes`。

## 7. Embedding 配置

**问题**：vector recall 怎么配置？

**决定**：DevPilot 风格的 OpenAI 兼容 provider 抽象（一个 `AsyncOpenAI` 客户端配可换的 `base_url`）：`embedding_provider`、`embedding_model`、`embedding_base_url`、`embedding_credential_ref`（keychain ref，绝不明文）。Provider：OpenAI / OpenRouter / Voyage / Jina / Gemini / Azure / DashScope 与本地 Ollama / LM Studio —— 全经 `.embeddings.create`；外加一个可选的进程内 `local` provider（fastembed）做零服务离线 embedding。默认检索是 `keyword`+`grep`（零配置、离线、语言无关）；vector 为可选项。双语内容推荐本地 `bge-m3` 或某云端 provider（仅英文的小模型对中文嵌入差）。embedding 模型 **可变** —— 改它会重嵌整个 store（文件是真相）。

## 8. 内置 MCP 工具

五个 memory 工具，挂在 `coffer__` 下，以 agent 为中心、低摩擦：

- `coffer__recall(query, scope?, mode?, top_k?)` → `[{id, text, score, source, time}, …]`（默认两个作用域；`mode` ∈ `grep` | `keyword` | `vector`）。
- `coffer__remember(text, scope?, type?)` → `{id, …}`（默认 `scope=project`）。
- `coffer__set_handoff(body)` → `{status, branch, scope}`（工作现场，按 project + 分支）。
- `coffer__resume()` → `{found, branch?, body?, updated_at?, note?}`。
- `coffer__list_memory(scope?)` → 用于浏览的事实。

调用记录进 `mcp_invocations`，方式与 KB 及上游工具相同：只记工具名 + who/when/duration/outcome —— 不记参数也不记返回内容（既有隐私立场）。

## 9. Prior art & novelty

- **managed-block 注入** 进 agent 配置文件已是成熟做法：**Next.js** 把 `<!-- BEGIN:nextjs-agent-rules -->` 写进 `AGENTS.md`；**claude-mem** 在 `CLAUDE.md` 用 `<claude-mem-context>`。
- **把累积记忆多 agent 原生投影是新颖的** —— 每个规范化记忆系统（mem0/OpenMemory、Letta、Zep、Cognee、MCP memory server、MemPalace）都是以 MCP 为中心；唯一的原生文件投影者（claude-mem、agentmemory）只针对 Claude 单目标。截至 2026 年中，Coffer 向多 agent 原生位置扇出在开源里无人主张。

## 10. 本规范不做的事

- recall 上的 reranking / HyDE / multi-query / LLM 合成（由 agent 合成）。
- 把某专有 agent 记忆格式双向解析回规范化（业界未解；用 symlink-where-compatible + 别处 MCP 规避）。
- 多机同步（constitutional）。
- 默认开启文件系统 watcher。
- 超出自由 `metadata.type` 之外的 memory 分类。

## 11. 实现期需验证的 open items

1. Claude Code 与 Codex 上的 MCP shim cwd 传播（§4）。
2. sqlite-vec 在 macOS arm64 与 Linux 上的打包/加载（vector 为可选项；keyword+grep 不需原生扩展）。
3. 中文/多语本地 embedding 模型基准（默认仍是 keyword+grep）。
