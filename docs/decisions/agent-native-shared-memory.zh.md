# One Shared Knowledge Store：跨 agent 共享的单一知识 store

> English: [agent-native-shared-memory.md](./agent-native-shared-memory.md)

**Status**: 部分被 [Memory via MCP](memory-via-mcp-not-native-projection.md) 取代（2026-06-18）—— 下文决策中「原生投影」那一半已移除；Coffer 绝不写 agent 自己的原生记忆文件。「共享单一 store」那一半依然成立，也正是本 ADR 现在所记录的内容。2026-09-10 以知识层词汇重新表述，2026-09-11 收敛为两条 lane（见修订历史）。
**Date**: 2026-06-09（2026-09-11 修订；见修订历史）
**Deciders**: Yuxing Wu
**Related**: spec `knowledge`（知识层 spec）、[Files as Truth](files-as-truth-sqlite-retrieval.md)、[Everything Is a Resource Kind](everything-is-a-resource-kind.md)、[Cross-Platform Skill Delivery](cross-platform-skill-delivery.md)、[Memory via MCP](memory-via-mcp-not-native-projection.md)

## Context

第一版记忆设计（基于 mem0 记忆引擎）把每个 store 当成一个通过 MCP 查询的私有孤岛。但现实中，
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

本决策建立在 [Files as Truth](files-as-truth-sqlite-retrieval.md) 之上：底下已
有一个单一、规范、markdown 文件即事实的基底。待解的问题是：这一个 store 如何在不
重新引入分叉副本的前提下触达多个 agent。

## Decision

**Coffer 持有一个共享 store，每个 agent 都通过 Coffer 自己的工具读写它。一条事实
只写一次，写进 Coffer 的 `knowledge` 层，并对该 scope 下的每个 agent 可见。Coffer
不保留任何逐 agent 的副本；自 [Memory via MCP](memory-via-mcp-not-native-projection.md)
起，也不写入任何 agent 的原生记忆文件。**

今天的具体形态：

- **一个资源 kind：`knowledge`。** 一个存储根 `~/.coffer/knowledge/<scope>/`，
  下有两条 lane —— `notes/`（agent 或用户写下的内容）与 `docs/`（上传的文档，
  已归一为 markdown）—— 外加一个隐藏的 `.history/` 存放整理覆盖前的旧版本，
  以及一个隐藏的 `.raw/` 存放上传的原件。文件即事实；SQLite 是其上一份可重建的
  索引（Files as Truth）。
- **三种 scope，由资源名读出。** `global`（跨项目）与 `project-<ULID>`（由 cwd 的
  git 根解析）在首次使用时自动开通；其余任何名字都是用户有意创建的集合，绝不自动
  开通 —— 因为从一个拼写错误里悄悄造出一个 scope，会比报错更糟。这就是原决策里的
  两层作用域，再加上第三层：为不属于前两者的语料而设、需显式创建。
- **规范格式。** 一条 note 是 `<scope>/notes/` 下带 YAML frontmatter
  （`name`、`description`、`metadata.type`、`origin_session_id`）+ markdown 正文的
  `.md` 文件。一份上传文档是 `<scope>/docs/` 下归一化后的 markdown，其原件保留在
  `<scope>/.raw/`，以便日后重新转换。两条 lane 索引进同一套 `documents` /
  `chunks` / FTS5 / sqlite-vec 基底，检索横跨两者。
- **一套工具界面，对每个 agent 都相同。** 六个 MCP 工具 —— `coffer__search`、
  `coffer__grep`、`coffer__read`、`coffer__list`、`coffer__write`、
  `coffer__delete`。每个都带可选的 `scope`，默认取由 shim 上报的 cwd 解析出的
  项目 scope，回退到 `global`。调用方再也不必在能搜之前先判定一条事实属于哪个
  store。**新加一个 agent，知识层零代码**
  —— 这些工具本就与 agent 无关。
- **不碰 agent 文件也能做环境式交付。** _2026-09-10 撤回。_ Context 里点出的那个
  落差——原生记忆免费加载、MCP 不会——原本要靠一个 SessionStart shell hook 把
  `rules` lane 作为运行时上下文注入来补上。那个机制 ship 了，但从未被安装到任何
  agent 上，因此已删除（spec agent-registry FR-043…FR-048）；它本要投递的 `rules` lane 本身，
  也在确认无人读它之后于 2026-09-11 删除。于是这个落差**重新敞开**：没有任何东西
  会把知识推进会话，agent 只能自己调 `coffer__search` 才能触达共享 store。本 ADR
  其余部分依然成立，唯独这一条不再成立。
- **只导入，不投影。** _2026-09-10 撤回。_ Coffer 曾能读取某个 agent 自己积累的
  原生记忆，让用户一次性把它接管进来。这一条同样 ship 了却从未被使用，已删除
  （spec agent-registry FR-040/FR-041）。它确立的那个**方向**仍然成立——没有任何东西回流到
  agent 的文件里——但如今两个方向都没有路径了。

**本 ADR 最初选定的机制并非如此，且已被移除。** 它把规范 store *向外*投影到每个
agent 的原生位置 —— 每个 agent 一个 `AgentMemoryAdapter`，`projection_mode` 取值
`SYMLINK | RENDER | NONE`，把规范目录 symlink 到 Claude Code 的 auto-memory 路径，
把一个 marker 围栏的托管块 render 进 Codex 配置文件，并**关闭每个 agent 自己的原生
记忆**，使规范 store 保持为唯一写入者。
[Memory via MCP](memory-via-mcp-not-native-projection.md) 于 2026-06-18 整体撤回
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

- **取回是有意的，不是自动的。** agent 只有在调用 `coffer__search` 时才看得见一条
  事实。自 2026-09-10 删除 session-start 注入后，**没有任何东西**是环境式的。这是
  「不写 agent 文件」的完整代价，我们明知而接受：那条环境式路径本来就从未真正
  跑起来过。
- **躺在 agent 自己 store 里的事实就留在那里。** 它们不会自行迁移；导入功能删除后，
  也不再有把它们搬过来的办法。
- **Coffer 的工具是唯一写入路径。** 不会讲 MCP 的 agent 无法向共享 store 贡献内容。
- **agent 写下的东西日后可能被重写。** 定期整理（2026-09-11）会无人值守地按定时
  合并重复的 note、把它们重写成主题文档。共享单一 store 让这件事值得做 —— 它要愈合
  的重复，正是同一条事实被好几个 agent 各写一遍 —— 但一条 note 因此不是一份固定的
  产物。`.history/` 保留旧版本，也是全部的安全网；落盘前没有复核环节。

## Alternatives Considered

**每个 agent 一个孤岛，即最初那版基于 mem0 的记忆设计的做法。** 被否：它正是本 ADR 要消除的分叉。

**逐 agent 的原生投影（本 ADR 最初的机制）。** 格式已匹配处用 symlink、不匹配处用
托管块，并关闭 agent 自己的原生记忆使副本无法分叉。被 Memory via MCP 取代：那样 Coffer
就在改动并关闭另一个工具的配置，且每个受支持的 agent 都欠一个手工维护、追着上游
格式跑的适配器。

**渲染进各 agent 自己的记忆格式，双向。** 把规范 store 投影*进*每个 agent 的私有
格式，并在编辑时*反向*解析回来，使每个 agent 都原生地编辑、变更双向流动。被否：
把一个私有、还在演进的 agent 记忆格式无损往返是业内未解难题，且天生有损。

**把知识折进 agent-workspace 配置（让它直接写 `CLAUDE.md`）。** 因分层理由被否：
它会塌掉 L1（配置）/ L2（知识）边界。知识保持与 agent 无关。

**两个 kind、一套基底 —— 一副 `memory` 面孔加一副 `knowledge_base` 面孔。** 这正是
该 store 实际被建成的样子，并已于 2026-09-10 合并掉（见
[Files as Truth](files-as-truth-sqlite-retrieval.md) 的修订历史）。基底从一开始
就是共享的，分成两份的只有门面，而它逼着调用方去猜一条事实属于哪副面孔。事后被否：
跨 agent 共享一个 store 才是要点，在同一个 store 上再糊一副面孔，只是多一样要保持
同步的东西，却没有收益。

## 修订历史

- **2026-06-09** —— 初版决定：一个规范的、逐条 markdown 的记忆 store，跨 agent
  共享方式为「MCP 读写 + 逐 agent 原生投影（`SYMLINK | RENDER | NONE`）」的混合
  机制，并关闭每个被投影 agent 自己的原生记忆。作用域为两层：global + per-project。
- **2026-06-18** —— [Memory via MCP](memory-via-mcp-not-native-projection.md)
  移除了投影那一半：Coffer 绝不写入或关闭 agent 的原生记忆文件。共享 store 那一半
  不受影响。
- **2026-09-10** —— 为知识层合并重新表述。本 ADR 跨 agent 共享的那个 store，现在
  就是单一的 `knowledge` kind（`memory` 与 `knowledge_base` 已合并）；store 名变成
  三种 scope；十二个 `coffer__*` 记忆/KB 工具变成八个。决策本身 —— 一个共享 store，
  而非每个 agent 一个 —— 未变；变的只是它被写下时所用的词汇。
- **2026-09-11** —— **两条 lane，六个工具。** 跨 agent 共享的这个 store 只保留
  两条 lane：`notes/`，即 agent 或用户写下的一切，`coffer__write` 直接落进去；
  以及 `docs/`，即上传后归一为 markdown 的文档 —— 外加隐藏的 `.history/`
  与 `.raw/`。`knowledge/inbox/` 那条梯度，以及 `rules/`、`handoff/`、
  `superseded/`，全部删除，破坏性且不设缓冲区。工具面从八个降到六个：
  `coffer__set_handoff` 与 `coffer__resume` 随交接 lane 一起退役，跨会话、跨 agent
  的接续从此由普通的 note 承载，而不再单占一条 lane。`rules` lane 直接删除 ——
  它的投递通道已在 2026-09-10 移除，且没有任何东西读它 —— 这也了结了上文那条已撤回
  的「环境式交付」bullet 留下的最后一根线头。取而代之，`notes/` 的可读性由定期整理
  维持：合并重复、把 note 重写成主题文档，并把旧版本留在 `.history/`
  （见 [Files as Truth](files-as-truth-sqlite-retrieval.md) 的修订历史）。重复
  per-project scope 的 AI 辅助合并一并删除：worktree 感知的 `git_root` 已消除成因，
  残留在每次 daemon 启动时被自动愈合，在同一个问题上再留一条手动路径不值那层抽象。
  决策本身 —— 一个共享 store，经 MCP 触达，绝不写进 agent 自己的记忆文件 —— 未变。
