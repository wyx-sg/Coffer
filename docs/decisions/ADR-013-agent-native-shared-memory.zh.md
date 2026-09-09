# ADR-013：跨 agent 共享的单一知识 store

> English: [ADR-013-agent-native-shared-memory.md](./ADR-013-agent-native-shared-memory.md)

**Status**: 部分被 [ADR-026](ADR-026-memory-via-mcp-not-native-projection.md) 取代（2026-06-18）—— 下文决策中「原生投影」那一半已移除；Coffer 绝不写 agent 自己的原生记忆文件。「共享单一 store」那一半依然成立，也正是本 ADR 现在所记录的内容。2026-09-10 以知识层词汇重新表述（见修订历史）。
**Date**: 2026-06-09（2026-09-10 修订；见修订历史）
**Deciders**: Yuxing Wu
**Related**: spec `007-memory`（知识层 spec）、[ADR-012](ADR-012-files-as-truth-sqlite-retrieval.md)、[ADR-007](ADR-007-everything-is-a-resource-kind.md)、[ADR-009](ADR-009-cross-platform-skill-delivery.md)、[ADR-026](ADR-026-memory-via-mcp-not-native-projection.md)、[ADR-035](ADR-035-adopt-native-memory.md)、[ADR-037](ADR-037-rules-runtime-injection.md)

## Context

第一版记忆设计（ADR-011）把每个 store 当成一个通过 MCP 查询的私有孤岛。但现实中，
开发者会在同一个项目上跑不止一个编码 agent（Claude Code、Codex …）。每个 agent
各有自己的原生记忆位置 —— Claude Code 的 auto-memory 目录、Codex 的 `memories`
等等。于是同一条项目事实（「我们用 squash-merge」「API base URL 是 X」）被每个
agent 各写一份，并**分叉**：每份副本被独立编辑，agent 们对这个项目各执一词。

修复方案受两股力量塑形：

1. **关于项目的事实是关于项目的，而非关于 agent 的。** 它应当只存在一份，并对在
   该项目上工作的每个 agent 都可见。
2. **agent 是「环境式」地加载原生文件，而「有意地」调用 MCP 工具。** 原生文件
   （agent 的记忆目录、`CLAUDE.md`、`AGENTS.md`）在会话开始时被自动读入上下文；
   MCP 工具只在 agent 主动选择调用时才被查询。我们造的东西必须回应这个落差，
   否则一个共享 store 会严格劣于每个 agent 已经免费拥有的能力。

本决策建立在 [ADR-012](ADR-012-files-as-truth-sqlite-retrieval.md) 之上：底下已
有一个单一、规范、markdown 文件即事实的基底。待解的问题是：这一个 store 如何在不
重新引入分叉副本的前提下触达多个 agent。

## Decision

**Coffer 持有一个共享 store，每个 agent 都通过 Coffer 自己的工具读写它。一条事实
只写一次，写进 Coffer 的 `knowledge` 层，并对该 scope 下的每个 agent 可见。Coffer
不保留任何逐 agent 的副本；自 [ADR-026](ADR-026-memory-via-mcp-not-native-projection.md)
起，也不写入任何 agent 的原生记忆文件。**

今天的具体形态：

- **一个资源 kind：`knowledge`。** 一个存储根 `~/.coffer/knowledge/<scope>/`，
  lane 为 `knowledge/`（agent 写下的条目）、`inbox/`（导入的文档）、`rules/`、
  `handoff/`、`superseded/`，外加一个隐藏的 `.raw/` 存放导入文档的原件。文件即
  事实；SQLite 是其上一份可重建的索引（ADR-012）。
- **三种 scope，由资源名读出。** `global`（跨项目）与 `project-<ULID>`（由 cwd 的
  git 根解析）在首次使用时自动开通；其余任何名字都是用户有意创建的集合，绝不自动
  开通 —— 因为从一个拼写错误里悄悄造出一个 scope，会比报错更糟。这就是原决策里的
  两层作用域，再加上第三层：为不属于前两者的语料而设、需显式创建。
- **规范格式。** 一条 entry 是 `<scope>/knowledge/` 下带 YAML frontmatter
  （`name`、`description`、`metadata.type`、`origin_session_id`）+ markdown 正文的
  `.md` 文件。一份导入文档是 `<scope>/inbox/` 下归一化后的 markdown，其原件保留在
  `<scope>/.raw/`，以便日后重新转换。两条 lane 索引进同一套 `documents` /
  `chunks` / FTS5 / sqlite-vec 基底，检索横跨两者。
- **一套工具界面，对每个 agent 都相同。** 八个 MCP 工具 —— `coffer__search`、
  `coffer__grep`、`coffer__read`、`coffer__list`、`coffer__write`、
  `coffer__delete`、`coffer__set_handoff`、`coffer__resume`。每个都带可选的
  `scope`，默认取由 shim 上报的 cwd 解析出的项目 scope，回退到 `global`。调用方
  再也不必在能搜之前先判定一条事实属于哪个 store。**新加一个 agent，知识层零代码**
  —— 这些工具本就与 agent 无关。
- **不碰 agent 文件也能做环境式交付。** Context 里点出的那个落差（原生免费加载、
  MCP 不会）由 [ADR-037](ADR-037-rules-runtime-injection.md) 补上：`rules` lane
  在 SessionStart 注入会话，handoff 经 `coffer__resume` 按需拉取。注入是运行时
  状态，因此既达到环境式效果，又不写任何归 agent 所有的文件。
- **只导入，不投影。** 若某个 agent 已经积累了自己的原生记忆，Coffer 读取它，并让
  用户把它一次性接管**进**共享 store（[ADR-035](ADR-035-adopt-native-memory.md)）。
  这条流向是单向、向内的；没有任何东西回流到 agent 的文件里。

**本 ADR 最初选定的机制并非如此，且已被移除。** 它把规范 store *向外*投影到每个
agent 的原生位置 —— 每个 agent 一个 `AgentMemoryAdapter`，`projection_mode` 取值
`SYMLINK | RENDER | NONE`，把规范目录 symlink 到 Claude Code 的 auto-memory 路径，
把一个 marker 围栏的托管块 render 进 Codex 配置文件，并**关闭每个 agent 自己的原生
记忆**，使规范 store 保持为唯一写入者。
[ADR-026](ADR-026-memory-via-mcp-not-native-projection.md) 于 2026-06-18 整体撤回
了它：写入并关闭别的工具的配置是侵入性的；逐 agent 适配器得追踪上游一直在变的
格式；而当初为之付费的那份环境式加载收益，改用注入同样能拿到。存活下来、也是本
ADR 今天被读的理由，是「共享单一 store」这个决策本身。

## Consequences

**正面**

- **一条事实，每个 agent，无分叉。** 一条事实只写一次，该 scope 下每个 agent 读
  的是同一个文件。双份/三份副本的分叉问题被结构性消除 —— 而且是靠「只有一份」，
  而不是靠「让好几份保持同步」。
- **知识层没有逐 agent 代码。** 因为工具界面与 agent 无关、Coffer 也从不碰 agent
  自己的文件，接入一个新 agent 在知识层的成本为零 —— 与原机制所需的逐 agent
  适配器形成对照。
- **干净分层。** 知识（L2）从不撰写 agent 的配置（L1）。原决策靠一个 adapter 维持
  的边界，现在靠「干脆不越界」维持。
- **调用方不必分类。** 只有一个 kind、一套工具，agent 不再需要先判断某样东西是
  「记忆」还是「知识」才能存下或找到它。

**负面**

- **取回是有意的，不是自动的。** agent 只有在调用 `coffer__search`（或 rules lane
  被注入）时才看得见一条事实。只有 rules 与 handoff 两条路径是环境式的；普通
  entry 不会被推进上下文。这是「不写 agent 文件」的代价，我们接受。
- **既有原生记忆需用户显式接管。** 已经躺在 agent 自己 store 里的事实不会自行迁移；
  ADR-035 的导入是一个用户动作。
- **Coffer 的工具是唯一写入路径。** 不会讲 MCP 的 agent 无法向共享 store 贡献内容。

## Alternatives Considered

**每个 agent 一个孤岛，即 ADR-011 的做法。** 被否：它正是本 ADR 要消除的分叉。

**逐 agent 的原生投影（本 ADR 最初的机制）。** 格式已匹配处用 symlink、不匹配处用
托管块，并关闭 agent 自己的原生记忆使副本无法分叉。被 ADR-026 取代：那样 Coffer
就在改动并关闭另一个工具的配置，且每个受支持的 agent 都欠一个手工维护、追着上游
格式跑的适配器。

**渲染进各 agent 自己的记忆格式，双向。** 把规范 store 投影*进*每个 agent 的私有
格式，并在编辑时*反向*解析回来，使每个 agent 都原生地编辑、变更双向流动。被否：
把一个私有、还在演进的 agent 记忆格式无损往返是业内未解难题，且天生有损。

**把知识折进 agent-workspace 配置（让它直接写 `CLAUDE.md`）。** 因分层理由被否：
它会塌掉 L1（配置）/ L2（知识）边界。知识保持与 agent 无关。

**两个 kind、一套基底 —— 一副 `memory` 面孔加一副 `knowledge_base` 面孔。** 这正是
该 store 实际被建成的样子，并已于 2026-09-10 合并掉（见
[ADR-012](ADR-012-files-as-truth-sqlite-retrieval.md) 的修订历史）。基底从一开始
就是共享的，分成两份的只有门面，而它逼着调用方去猜一条事实属于哪副面孔。事后被否：
跨 agent 共享一个 store 才是要点，在同一个 store 上再糊一副面孔，只是多一样要保持
同步的东西，却没有收益。

## 修订历史

- **2026-06-09** —— 初版决定：一个规范的、逐条 markdown 的记忆 store，跨 agent
  共享方式为「MCP 读写 + 逐 agent 原生投影（`SYMLINK | RENDER | NONE`）」的混合
  机制，并关闭每个被投影 agent 自己的原生记忆。作用域为两层：global + per-project。
- **2026-06-18** —— [ADR-026](ADR-026-memory-via-mcp-not-native-projection.md)
  移除了投影那一半：Coffer 绝不写入或关闭 agent 的原生记忆文件。共享 store 那一半
  不受影响。
- **2026-09-10** —— 为知识层合并重新表述。本 ADR 跨 agent 共享的那个 store，现在
  就是单一的 `knowledge` kind（`memory` 与 `knowledge_base` 已合并）；store 名变成
  三种 scope；十二个 `coffer__*` 记忆/KB 工具变成八个。决策本身 —— 一个共享 store，
  而非每个 agent 一个 —— 未变；变的只是它被写下时所用的词汇。
