# ADR-013：agent 原生的共享 memory 投影

> English: [ADR-013-agent-native-shared-memory.md](./ADR-013-agent-native-shared-memory.md)

**Status**: Accepted
**Date**: 2026-06-09
**Deciders**: Yuxing Wu
**Related**: spec `007-memory`、[ADR-012](ADR-012-files-as-truth-sqlite-retrieval.md)、[ADR-007](ADR-007-everything-is-a-resource-kind.md)、[ADR-009](ADR-009-cross-platform-skill-delivery.md)

## Context

第一版 `memory` 设计（ADR-011）把每个 memory store 当成一个通过 MCP 查询的私有
孤岛。但现实中，开发者会在同一个项目上跑不止一个编码 agent（Claude Code、Codex
…）。每个 agent 各有自己的原生 memory 位置 —— Claude Code 的 auto-memory 目录、
Codex 的 `memories` 等等。于是同一条项目事实（「我们用 squash-merge」「API base
URL 是 X」）被每个 agent 各写一份，并**分叉**：每份副本被独立编辑，agent 们对这个
项目各执一词。

修复方案受两股力量塑形：

1. **关于项目的事实是关于项目的，而非关于 agent 的。** 它应当只存在一份，并对在
   该项目上工作的每个 agent 都可见。
2. **agent 是「环境式」地加载原生 memory，而「有意地」查询 MCP memory。** 原生
   文件（Claude 的 memory 目录、`CLAUDE.md`、`AGENTS.md`）在会话开始时被自动读入
   上下文；MCP 工具只在 agent 主动选择调用 `recall` 时才被查询。丢掉原生加载会让
   memory 严格劣于 agent 已经免费拥有的能力。

本决策建立在 [ADR-012](ADR-012-files-as-truth-sqlite-retrieval.md) 之上：现在已有
一个单一、规范、逐条 markdown、文件即事实的 memory store。待解的问题是：这一个
store 如何在不重新引入分叉副本的前提下触达多个 agent。

## Decision

**保留一个规范的、逐条 markdown 的 memory store，并通过一套混合机制跨 agent
共享：对每个 agent 都提供 MCP 读写，再叠加逐 agent 的原生投影 —— 由一个
`AgentMemoryAdapter` 负责，其 `projection_mode` 取值 `SYMLINK | RENDER | NONE`。
当某个 agent 被投影时，关闭该 agent 自己的原生 memory，使规范 store 成为唯一写
入者，副本无法分叉。memory 作用域分两层：global（跨项目）+ per-project。**

具体形态：

- **规范格式。** 逐条 `.md` 文件，YAML frontmatter（`name`、`description`、
  `metadata.type`、`origin_session_id`）+ markdown 正文，外加一份重新生成的
  `MEMORY.md` 索引。这就是 Claude Code 的 auto-memory 格式，*正是为了*让 Claude
  投影能是一个原生目录 symlink（无渲染、无有损往返）才把它选作规范格式。
- **两层作用域。** global 事实存在 `WORKSPACE_GLOBAL_PROJECT_ID` 哨兵 store 里
  （即既有哨兵 `00000000000000000000000000` —— 不新造）；per-project 事实存在
  `projects/<project-ulid>/`。`remember(scope=project)` 经 MCP shim 上报的
  cwd → git-root 解析到对应项目 store；`recall` 默认查两层。
- **投影矩阵。**

  |            | Claude Code                                                                                                   | Codex                                                                         |
  | ---------- | ------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
  | **项目层** | `SYMLINK` 规范目录 → `~/.claude/projects/<slug>/memory/`（原生、双向，auto-memory 保持 ON —— 它*就是*规范源） | 把一个 marker 围栏块 `RENDER` 进 `<project>/AGENTS.md`；禁用 Codex `memories` |
  | **全局层** | 把块 `RENDER` 进 `~/.claude/CLAUDE.md`                                                                        | 把块 `RENDER` 进 `~/.codex/AGENTS.md`                                         |

- **托管块（managed block）** 用于 `RENDER` 模式（幂等，memory 变更时重新渲染）：

  ```
  <!-- coffer:memory:start (managed, do not edit) -->
  … rendered facts …
  <!-- coffer:memory:end -->
  ```

- **`AgentMemoryAdapter`** 随 agent driver 落地（即那个已经持有 L1 配置文件 ——
  `CLAUDE.md` / `AGENTS.md` / rules —— 的 agent 层），而**不**随 memory kind：

  ```
  memory_location(project) -> path | None
  projection_mode          -> SYMLINK | RENDER | NONE
  disable_native_memory(agent_config)   # 仅当原生 memory 会成为另一份副本时
  render(facts) -> bytes                # RENDER 模式
  ```

  投影引擎按 `projection_mode` 分发；adapter 执行全部文件改动。memory 基底只提供
  规范文件 + 渲染好的 markdown，从而保持它与 agent 无关、L1/L2 边界干净（memory
  从不撰写配置；是 agent 自己的 adapter 注入托管块）。**加一个新 agent = 一个
  adapter，不动内核**（[ADR-009](ADR-009-cross-platform-skill-delivery.md) 的
  逐 agent 投递形态在此重现）。

- **投影时禁用原生 memory。** 凡是 `RENDER` 的 agent 自带可写原生 memory
  （Codex `memories`），就把它关掉，使唯一写入者是规范 store。`SYMLINK` 的 agent
  保持原生 memory ON，因为被 symlink 的目录*就是*规范 store（同 inode → 不分叉）。
- **惰性建立。** 在会话开始时按上报的 cwd 建立。若某个 agent 的原生 memory 目录
  里已有真实文件，**先合并进规范 store，再**替换为 symlink —— 绝不静默覆盖。

## Consequences

**正面**

- **一条事实，每个 agent，无分叉。** 一条项目事实只写一次，被 Claude（活的
  symlink）、Codex（重新渲染的块）以及任何未来 agent 读取。双份/三份副本的分叉
  问题被结构性消除。
- **保住环境式原生加载。** agent 仍在会话开始时从原生位置读入 memory；MCP
  `recall` 是叠加而非唯一路径。memory 严格优于逐 agent 原生 memory，不是平替。
- **干净分层。** memory（L2）从不撰写配置（L1）；是 agent 的 adapter —— 它本就持
  有该 agent 的 L1 文件 —— 这一个组件去碰它们。加一个 agent 不动 memory kind。
- **廉价的新鲜度。** symlink 是活的（同 inode）；托管块在 memory 变更时幂等重渲；
  `recall` 对小小的事实目录做惰性 reindex-on-read，因此 Claude 的 symlink 编辑
  对所有 agent 立即可见，无需文件系统 watcher。

**负面**

- **逐 agent adapter 的维护成本。** 每个 agent 的原生 memory 形态、用于禁用它的
  配置开关、文件位置都得追踪，且上游可能变。靠「一个 agent 一个 adapter」的隔离
  来缓解。
- **`RENDER` 是单向的。** 对 `RENDER` 的 agent，编辑只从规范 → 原生单向流动；
  agent 不能靠改它的 `AGENTS.md` 块来编辑 memory（下次渲染会覆盖）。这些 agent
  改为通过 MCP 写。这是为避免有损往返而有意做的取舍（见 Alternatives）。
- **禁用原生 memory 是侵入性的。** Coffer 会改动一个 agent 自己的配置去关掉它的
  原生 memory。这必须显式、可逆、绝不静默 —— 且在这么做之前必须先把任何既有原生
  事实迁移进规范 store。
- **symlink 可移植性。** 目录 symlink 与
  [ADR-009](ADR-009-cross-platform-skill-delivery.md) 的 skill 投递有相同的跨平台
  注意点（Windows junction / copy-fallback 的考量），须遵循同一策略。

## Alternatives Considered

**仅 MCP（无原生投影），即 ADR-011 的做法。** 可行且最简：一个规范 store，每个
agent 都通过 `recall`/`remember` 读写。作为*唯一*机制被否，因为它丢掉了环境式
原生加载 —— agent 只有在记得调工具时才看得见 memory，而原生文件在会话开始时免费
加载进上下文。我们把 MCP 留作通用底座，并在其上叠加投影。

**逐 agent 渲染进各自的原生 memory 格式，双向。** 把规范 store 投影*进*每个 agent
的私有 memory 格式，并在编辑时*反向*解析回来，使每个 agent 都原生地编辑 memory、
变更双向流动。被否：把一个私有、还在演进的 agent memory 格式无损往返是业内未解
难题，且天生有损。我们绕开它 —— 格式已匹配处用 symlink（Claude）、别处用单向托管
块、写入走 MCP —— 而不去造一个脆弱的双向翻译器。

**把 memory 折进 agent-workspace 配置（让 memory 直接写 `CLAUDE.md`）。** 因分层
理由被否：它会塌掉 L1（配置）/ L2（知识）边界。memory 保持与 agent 无关；只有
agent 自己的 adapter 注入一个 marker 围栏块，它可逆且界限分明。

## 先例与新颖性

把托管块注入 agent 配置文件是已有先例：**Next.js** 会把一个
`<!-- BEGIN:nextjs-agent-rules -->` 块写进 `AGENTS.md`，**claude-mem** 会把一个
`<claude-mem-context>` 块注入 `CLAUDE.md`。Coffer 在 `RENDER` 模式中复用这个已被
验证的模式。

**新颖**的是「把累积的 memory 多 agent 原生投影」。我们调研过的每个规范 memory
系统（mem0/OpenMemory、Letta、Zep、Cognee、MCP memory server、MemPalace）都以
MCP 为中心；唯二做原生文件投影的（claude-mem、agentmemory）都只针对 Claude、单
目标。Coffer 把一个规范 store 扇出到*多个* agent 的原生位置（格式匹配处 symlink、
不匹配处托管块、处处 MCP）—— 截至 2026 年中，这在开源界尚无人认领。新机制的风险
靠 adapter 隔离来缓解，也靠 MCP 始终作为通用兜底（若某 agent 的投影尚未实现）。
