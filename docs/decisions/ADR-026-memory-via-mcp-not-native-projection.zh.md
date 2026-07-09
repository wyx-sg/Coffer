# ADR-026：记忆经 MCP 访问，而非原生投射（取代 ADR-013）

> English: [ADR-026-memory-via-mcp-not-native-projection.md](ADR-026-memory-via-mcp-not-native-projection.md)

**Status**: Accepted
**Date**: 2026-06-18
**Deciders**: Yuxing Wu
**Related**: spec `007-memory`，取代 [ADR-013](ADR-013-agent-native-shared-memory.md)；基于 [ADR-012](ADR-012-files-as-truth-sqlite-retrieval.md)；参考 [`docs/research/memory-systems-landscape.zh.md`](../research/memory-systems-landscape.zh.md)

## Context

[ADR-013](ADR-013-agent-native-shared-memory.md) 让 Coffer 的那一份 canonical 记忆库通过**原生投射**触达多个 agent：把 canonical 的 per-project 记忆目录 symlink 进 Claude Code 的 auto-memory 位置，把 marker 围栏的托管块 render 进 Codex / OpenCode / OpenClaw / Hermes 的配置文件，并**关掉每个 agent 自带的原生记忆**以防出现发散的第二份副本。MCP `recall`/`remember` 是通用底座，投射是让记忆在 session 启动时「环境式」加载的额外一层。

一轮竞品调研（`docs/research/memory-systems-landscape.zh.md`）把这个选择放进业界做法里，并亮出一面**黄旗**：受访的每一个共享记忆系统（mem0、Letta、Zep/Graphiti、官方 MCP memory server、claude-mem、agentmemory）**都不写入另一个 agent 的原生记忆文件**。它们用一个在运行时触达的中心库 —— 经 MCP/API 查询，或经 session hook 注入上下文。Letta 自家的 Claude Code 集成（`claude-subconscious`）**刻意从不写 `CLAUDE.md`**，甚至清掉遗留块。多目标原生 fan-out 是 Coffer 真正新颖的贡献 —— 但也正是业界其余玩家考虑过、然后**避开**的那条路。

三个因素让投射层在实践中得不偿失：

1. **可读性。** 为了让 Claude 投射能是 symlink 而采用 Claude Code 的 auto-memory 格式，意味着 per-project store 以不透明的 `project-<ULID>` 目录来 key 和呈现。用户根本认不出某个 store 属于哪个项目（这正是本次反转的触发点）。
2. **侵入性。** 投射写入并关闭用户自己的 agent 配置 —— 正是业界避开的动作。它不易干净回滚、带跨平台 symlink 隐患、还需要一个跟踪各 agent 不断演进的原生记忆形态的 per-agent 适配器。
3. **成本 vs 收益。** 投射相对纯 MCP 唯一买到的，是 session 启动时的**环境式**加载。这一点无需碰原生文件即可拿回 —— 用 session 启动 hook 把记忆索引注入上下文（claude-mem 和 `claude-subconscious` 走的就是这条路），这是个更小、不侵入、且日后可按 agent 增量添加的机制。

## Decision

**Coffer 用自己的 per-fact-markdown 格式管理记忆，绝不操作 agent 的原生记忆文件。agent 只经 MCP 网关工具（`coffer__recall` / `remember` / `update_memory` / `forget` / `list_memory`）读写记忆。原生投射层整体移除。**

具体：

- **移除：** `AgentMemoryAdapter` 协议 + `ProjectionEngine` + 各 per-agent 适配器（SYMLINK/RENDER/NONE）、投射 FS 适配器、`memory_projection_bindings` 表（由 migration `0023` drop）、投射 REST 端点（`/memory_stores/{name}/projections…`）、原生记忆发现/接管路由、`coffer memory bind/unbind/projections` CLI 命令、以及 `memory_projected` 审计事件。Coffer 不再关闭任何 agent 的原生记忆。
- **保留（不变）：** 文件即真相的 per-fact markdown + 重新生成的 `MEMORY.md`（[ADR-012](ADR-012-files-as-truth-sqlite-retrieval.md)）；两层作用域（global + per-project，从 MCP shim 的 cwd → git-root 解析）；共享检索引擎（grep / FTS5 关键词 / sqlite-vec 向量）+ 惰性 reindex-on-read；transcript 蒸馏（ADR-020）；以及经 UI/CLI 的完整人工策展。
- **可读性（FR-017a）：** 因为 Coffer 拥有自己的格式，per-project store 以从 `project_root` 推导的可读身份（目录 basename + 路径）呈现，而非 `project-<ULID>` 名。
- **环境式加载（~~延后的后续项~~ —— 已交付，spec 007 FR-055）：** session 启动 hook 现在会把项目记忆摘要（近期 journal + knowledge 索引）注入 agent 上下文（经 `session-context` 端点的上下文注入，绝不写文件），使 agent 一开工就带上记忆、无需主动调 `recall`；正文仍经 `recall` 按需取。经 per-agent SessionStart hook（ADR-042 `ContextInjectionSpec`）投递给凡装了该 hook 的 agent（Claude Code、Codex、Cursor）。它不碰原生文件即恢复了投射层原本提供的环境式自动加载。

## Consequences

**Positive**

- **不侵入。** Coffer 绝不写入、symlink 进、或关闭 agent 自己的记忆。agent 的原生记忆归它自己，Coffer 的归 Coffer，经工具触达。这就是业界默认姿态。
- **可读 + 可策展。** 项目 store 以名字/路径呈现；不再有被采用的原生格式逼出来的不透明 ULID 目录。
- **代码大幅减少、活动部件更少。** 砍掉约 1.7k 行投射引擎/适配器/FS/持久化/路由/wiring 和一张 DB 表；上游格式变化时少一个 per-agent 面要跟踪。
- **不再关闭原生记忆。** 不再翻转 agent 配置去关掉它自带的记忆 —— 这是 ADR-013 自己也点出的「可逆但侵入」步骤。

**Negative**

- **在注入 hook 落地前失去环境式自动加载。** 纯 MCP 访问下，agent 只有在调用 `recall` 时才看见记忆；原生文件则在 session 启动时免费载入上下文。这正是 ADR-013 做投射的核心理由。缓解：上面的 session 启动注入 hook 不写原生文件即可恢复环境式在场；它是下一片。
- **放弃新颖性主张。** 多目标原生 fan-out 据调研是 Coffer 的独特贡献；中心库 + 经工具访问的模型成熟但不出奇。这是有意的取舍：简单、可读、不侵入，在此处胜过新颖。

## Alternatives Considered

**保留原生投射（ADR-013）。** 否决：可读性与侵入性代价真实且反复出现，而它唯一的收益（环境式加载）可由运行时注入拿回。这个新颖性不值得去写入并关闭用户的 agent 配置。

**只把记忆索引 render 进原生文件（只托管块、不 symlink、不关原生记忆）。** 一种更软的投射。否决：仍写入用户配置文件（业界避开的动作）、仍需 per-agent 适配器，而 session 启动上下文注入不碰任何文件就能达到同样的环境式效果。

**纯 MCP、完全没有环境式机制。** 可行且最简单，但只在模型「想起来调 recall」时才加载的记忆会被低用。经 session hook 的运行时注入是计划中的、不侵入的补救 —— 所以纯 MCP 是我们现在交付的底座，注入作为已立项的后续。
