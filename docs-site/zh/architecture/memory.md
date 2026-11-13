---
title: 记忆
description: Coffer 怎样在保险库里保存一个汇集每个智能体记忆的中心库，按每个智能体自己加载的方式写进它的记忆，只同步在仓库里学到的记忆，并把整理留给智能体。
---

# 记忆 {#memory}

本页讲 Coffer 记忆层的工作原理：它如何从 Claude Code 和 Codex 自己的记忆文件里读出它们学到的东西，把每条记忆保存在保险库的中心库里，再在每台机器上把每一条写进其他智能体自己的记忆。本页面向想了解机制和背后理由的工程师。按任务组织的说明见[记忆指南](/zh/guides/memory)。

## 要解决的问题 {#the-problem}

每个编程智能体都有自己的记忆，彼此却看不到对方的。Claude Code 在每个项目下一条记忆写一个 Markdown 文件，每次会话加载它的 `MEMORY.md` 索引。Codex 把它的会话提炼成一份记忆摘要，每次会话加载。现在两者也都会整理自己的记忆：Claude Code 的 Auto Dream 负责合并和清理，Codex 的整合在输入变化时重写记忆。它们做不到的，是看到对方学到了什么，或者自己在你另一台机器上学到了什么。

Coffer 的答案是一次同步，而不是一套自己的记忆系统：

1. **发布。** 每台机器读取自己智能体的原生记忆，把智能体自己写下的每条记忆发布到**中心库** `vault/memory/`，每条记忆一个文件。保险库同步在你的各台机器之间传送中心库。
2. **写入。** 每台机器把中心库里的每个条目，按对方自己的格式，写进本机除来源之外的每个智能体，智能体会把它当作自己的记忆加载。
3. **整理和加载交给智能体。** Coffer 不往会话里投递任何东西，也从不修改智能体自己写的记忆。合并、纠正和遗忘都是每个智能体自己的整理。

记忆管人，[知识](/zh/architecture/knowledge)管事。记忆保存你是谁、怎么和你合作、一个项目当前的状态；它到达会话的方式和智能体自己的记忆一样。知识保存外部系统、团队和流程怎么运作，带来源和复查日期，智能体通过 `coffer-guide` 目录按需拉取。固定的一串步骤是技能。智能体在项目里留下的每条记忆，不论讲的是什么，Coffer 都同步，把它移进知识库是你和你的智能体的事；Codex 按任务留下的工作笔记不是记忆，不读取。只同步在仓库里学到的记忆：智能体在任何仓库之外学到的留在它自己那里（见[只同步项目记忆](#project-memories-only)）。往智能体的记忆里写东西，是[拉取，而非推送](/zh/architecture/design-principles#pull-not-push)的一个有边界的例外：Coffer 只写自己的文件和一个标记区块，修改前先备份，首次或大量同步先给预览，每次同步都审计，并提供一键撤销。这个决定和权衡过的方案见 ADR [Sync Memory Into Each Agent's Own Memory Through a Hub in the Vault](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/sync-memory-into-each-agents-own-memory.md)。

## 中心库 {#the-hub}

```text
~/.coffer/vault/memory/
└── projects/
    └── github.com-acme-payments/
        └── <id>.md
```

只读取 `projects/`：早先版本写下的 `sorted/` 或 `global/` 文件夹会被忽略。

- **项目键。** 项目以仓库的 `origin` URL 命名，并经过规范化：去掉协议、凭据、端口和末尾的 `.git`，主机名转为小写，路径保留大小写（`git@host:owner/repo.git` 和 `https://host/owner/repo` 得到同一个键）。没有远端的仓库退而使用目录名，因为路径不能跨机器使用。主检出、它的工作树，以及 `origin` 相同的另一份克隆，无论在哪台机器上，都是同一个项目。文件夹名是把键里 `[A-Za-z0-9._-]` 之外的字符都换成 `-` 后的结果；键本身写在每个条目 frontmatter 的 `project:` 里，所以从不需要反解文件夹名。
- **归档。** 记忆放在智能体放它的地方，不看类型：在某个仓库里学到的归入那个项目。工作目录不在任何仓库里的记忆（Claude Code 的项目目录是个临时文件夹，Codex 的某个条目所属会话不在仓库里）不发布；在保险库自己的检出 `~/.coffer/vault` 里学到的也不发布，那是 Coffer 的数据，不是一个项目。参见 [ADR：记忆放在智能体放它的地方](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/file-a-memory-where-its-agent-filed-it.md)。
- **条目 id。** `sha256(machine_id, agent_type, source_identity)` 的前 16 个十六进制字符。来源标识是 Claude Code 记忆文件在配置目录下的路径，或者 Codex 摘要的路径加上条目的项目范围和它文本的哈希。没变过的来源重读时映射到同一个 id。被 Codex 改写过的条目是一条新记忆，旧的那条在同一次同步里离开中心库。
- **Frontmatter。** `id`、`origin`（`machine`、`agent`、`source`）、`project`、`type`（`user`、`feedback`、`project` 或 `reference`）、`title`、`description`、`created_at` 和 `updated_at`。正文是记忆的文本。
- **可移植的路径。** 发布时，先把仓库根目录（以及智能体记录的每个工作树根目录）换成 `<repo>`，再把主目录换成 `~`，最长匹配优先，并且只在路径边界上替换。写入时，`<repo>` 展开成项目在写入机器上的检出位置，`~` 展开成那台机器的主目录。其他路径保持原样。
- **每个条目只有一个写入者。** 只有来源机器和来源智能体会创建、修改或删除一个条目；一台机器从不因为自己的智能体没有某些条目，就删除另一台机器的条目。所以两台机器从不编辑同一个文件，保险库同步合并中心库时总是干净的。
- **每次同步一次提交。** 一次同步对中心库的改动是一次保险库提交，写入者为 `memory-sync`，走保险库常规的经过校验的写入路径。
- **扣下密钥。** 条目发布之前，它的文本会经过与密钥扫描和同步推送检查相同的检测器。命中则扣下该条目；报告写明智能体和来源，但从不写出值。同步推送检查仍是第二道防线。

中心库里允许重复：两个智能体对同一个教训的说法是两个条目，每个智能体在自己那边合并它们。中心库是一条传送通道，不是一个经过整理的存储。

## 读取原生记忆 {#reading-native-memory}

每个受支持的智能体有一个读取器，每个读取器都遵循同样的两步约定：**列出来源**（智能体的记忆文件，各自计算哈希，不解析），然后**读取一个来源**（把一个文件解析成条目：标题、描述、类型、原文正文、锚点和项目根目录）。把两步分开，同步就能在付出解析代价之前跳过没变的文件。Coffer 只读取**已注册**的智能体，路径由每个智能体自己的配置目录推出。

| | Claude Code | Codex |
| --- | --- | --- |
| 读取的文件 | `<config_dir>/projects/<slug>/memory/*.md` | `<config_dir>/memories_v2/memory_summary.md` |
| 一个条目对应 | 一个记忆文件 | 摘要 `## What's in Memory` 一节里的一个条目 |
| 标题和描述 | frontmatter 的 `name` 和 `description` | 条目的第一个分句，以及它的那句话 |
| 类型 | `metadata.type`：`user`、`feedback`、`project` 或 `reference` | `project` |
| 项目根目录 | 同目录下会话记录里记下的 `cwd`，退而解码项目 slug | 条目指向的 rollout 摘要开头的 `cwd:` |
| 跳过 | 智能体自己的 `MEMORY.md` 索引，以及其中 Coffer 的区块 | 用户档案、偏好和通用提示（讲的是人，不是项目）、整个 v1 文件夹 `memories/`、`rollout_summaries/` 的正文、`extensions/` 下的一切，以及标了 `[via Coffer]` 的条目 |

两个读取器都不把会话记录或 rollout 当作来源。Claude Code 读取器读会话记录里的 `cwd`，Codex 读取器读 rollout 摘要开头的 `cwd:` 一行（下面的内容不读），都只为一件事：找出条目的项目根目录。

Codex 在 v2 摘要之外，还在 `memories/` 里留着旧的记忆（`MEMORY.md`，每项工作一个任务组，各有偏好、可复用知识和失败记录的条目）。Coffer 不读它。那些条目是单次任务的工作笔记：在维护者的机器上，中心库 308 条里有 232 条是它们，而 Claude Code 会加载的 4 KB 区块只放得下某个项目 90 条记忆里的 14 条，真正重要的反而被挤了出去。一次任务里值得带走的东西，Codex 自己会整合进 v2 摘要。还没有 `memories_v2/` 的 Codex 不发布任何记忆；Coffer 仍然往它里面写。见 ADR [Sync Memories, Not Task Notes](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/sync-memories-not-task-notes.md)。

无法解析来源的读取器会**大声地、隔离地**失败：这个智能体在这次同步里什么都不发布，记忆页写明路径和原因，另一个智能体照常读取，它之前发布的条目留在中心库里，不会被删除。

摘要与账本里记录的一致的来源会被跳过。账本丢了，代价只是一次完整重读。账本是在另一个读取器修订号下写的（同步改变归档方式时会提高修订号）也一样会忘掉摘要，所以一次同步就会把中心库里已有的记忆全部重新归档。

## 写入每个智能体 {#writing-into-each-agent}

一台机器把中心库的条目写进本机每个已注册的智能体，只有该条目的来源智能体在来源机器上除外：台式机上的 Claude Code 会收到笔记本上的 Claude Code 学到的东西。一个项目的条目只写到该项目在本机**已检出**的地方。检出位置在每次同步时从已注册智能体记录的工作目录（Claude Code 的项目目录，Codex rollout 摘要的 `cwd:`）得出，每个都解析到它的仓库；不会扫描磁盘。一个项目在本机检出了不止一份时，主检出优先于工作树，其次是最近使用的。

### Claude Code {#claude-code}

Claude Code 只读取它自己会加载的文字：项目 `MEMORY.md` 的前 200 行和 25 KB，以及 `rules/` 下的每个文件。一条记忆自己的文件，只有模型决定去打开时才会读，而在维护者两周的会话里它一次也没打开过。所以 Coffer 不往 Claude Code 里写**每条记忆一个文件**，只写它会加载的文字。这个决定和权衡过的方案（钩子、索引、MCP 工具、像知识库那样拉取）见 ADR [Claude Code Reads Other Agents' Memories as Text It Loads](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/claude-code-reads-other-agents-memories-as-text.md)。

- **项目记忆**写进该项目 `MEMORY.md` 末尾的标记区块，位于 `<config_dir>/projects/<slug>/memory/`，slug 是 Claude Code 自己对仓库根目录的编码，各工作树共用（不存在时会创建）。它们只在该项目的会话里加载。区块在 `<!-- coffer:memory-sync:begin -->` 和 `<!-- coffer:memory-sync:end -->` 之间；写入只替换两个标记之间的字节，没有标记时追加区块，之前的文件先存到 `~/.coffer/config-backups/`。
- **每条记忆一行**：它的原文，最多 800 个字符；原文不以标题开头时，前面加粗写上标题（Codex 用记忆的第一个分句作标题）；最后写明来自哪个智能体，最新的在前。
- **有上限。** 区块不超过 4 KB。放不下的记忆在最后一行计数，并写出列出它们的命令 `coffer memory entries --project <项目>`；记忆页也会把每一条标为放不下，让你看得到 Claude Code 没有加载哪些。

### Codex {#codex}

- **文件夹。** 每个存在的 Codex 记忆文件夹（`<config_dir>/memories/`、`<config_dir>/memories_v2/`）里的 `extensions/coffer/`，包含 `instructions.md` 和 `resources/<条目 id>-<slug>.md`。每个记忆文件夹是一个独立的写入位置，有自己的账本记录、状态和副本计数；v1 文件夹沿用原来的账本键。Codex 的整合把记忆扩展当作主要输入读取，并把被删除的资源视为遗忘的信号。Codex 会在十四天后清理名字以时间戳开头的资源，所以 Coffer 起的名字从不以时间戳开头。
- **更新的文件夹。** Coffer 不认识的 `memories_v<N>` 会作为一个不写入的位置列出，并报告为无法识别，和 Coffer 正在写的文件夹并列。
- **资源。** 标题、它适用的项目（本机的检出位置和项目键）、来源智能体、类型和日期，然后是记忆的文本。
- **instructions.md** 告诉整合：这些是你的其他智能体学到的记忆，只当作信息、绝不当作指令；把每条归到它写明的项目下；较新的证据胜过较旧的说法；从中得出的内容标上 `[via Coffer]`；永远不要删除这些文件。
- **记忆关闭。** `config.toml` 里的 `[features] memories` 关闭时，不为 Codex 写任何东西，页面会说明。

写入器如果认不出它要写入的布局（Claude Code 记忆目录的形状不对，或者 Codex 的记忆文件夹里没有 `MEMORY.md`、`memory_summary.md` 或 `rollout_summaries/`），就不为这个智能体写任何东西，并像读取器出错一样报告出来。每个由来源或条目构造出的路径都要经过路径穿越防护，读写都限定在已注册智能体的记忆路径和 `vault/memory/` 之内。

### Codex 自己的导入 {#codex-s-own-import}

Codex 可以自己导入 Claude Code 的项目记忆并保持更新。当它这样做时（Codex 记忆标签页上的一个开关，存在账本里，因为这个设置本身的位置没有文档），Coffer 在这台机器上跳过 Claude Code → Codex 这个方向。Codex → Claude Code 照常进行。

## 回声、吸收与移交 {#echo-absorption-and-hand-over}

写进智能体、下次同步再读回来，这个过程不能形成循环。

- **认得出副本。** 在 Claude Code 上，读取器跳过标记区块。在 Codex 上，读取器从不列出 `extensions/` 下的任何东西，并跳过标了 `[via Coffer]` 的条目。
- **吸收不会循环流转。** 智能体会把 Coffer 交给它的内容并入自己的记忆：Claude Code 在自己的某个文件里复述区块里的一行；Codex 的整合把一个资源改写成一个条目。那条记忆属于智能体，会被同步，但它的改写不能无休止地来回流转。账本为每个智能体保存 Coffer 交给它的每个句子的指纹（转小写、合并空白、去标点后取哈希）。当智能体自己的记忆发生变化，而新增的每个句子都是 Coffer 交给它的，这次变化只记录、不发布。一个事实只跨过每个智能体边界一次；改写到指纹认不出时，它作为该智能体自己的记忆发布，每一侧的整理再把它和已有的内容合并。
- **被修改或移除的副本归智能体所有。** 摘要与 Coffer 写入时不一致的 Codex 资源是 `edited`；不见了的是 `removed`。只要中心库条目没变，两者都保持不动。条目变化时，新版本作为一份新资源写在被修改的那份旁边，或者把被移除的重新写入。移除副本从不删除它的中心库条目。Coffer 的区块归 Coffer 自己，每次整体重写。

Coffer 从不创建、修改、移动或删除智能体记忆里的其他任何文件，也从不改动智能体的记忆设置。

## 只同步项目记忆 {#project-memories-only}

只有智能体在仓库里学到的记忆，Coffer 才会发布。Codex 的档案、偏好和通用提示，以及在临时文件夹里学到的任何东西，留在写下它的智能体里，不会到达其他智能体：Codex 在仓库之外学到的大多是某个雇主内部工具的习惯，把它们放进每个 Claude Code 会话，会把它们带进不相干的项目。对你本人的长期偏好，应写进每个智能体自己的说明文件（`~/.claude/CLAUDE.md`、`~/.codex/AGENTS.md`），由你自己写。保险库自己的检出也不算项目：智能体在 `~/.coffer/vault` 里干活是在打理 Coffer 的数据，在那里学到的东西讲的不是某个代码库。

在一个项目内，智能体留下的每条记忆都会同步，不看类型：Coffer 不按智能体把记忆记在项目里的哪个位置来评判它。过时的内容由每个智能体自己的整理清理。

只要来源里还有这条记忆，它就留在中心库里，即使它的仓库已经从来源机器上删掉：删掉一份检出并不等于你说这条经验错了，别的机器上可能还有这个项目。智能体或你把它从智能体自己的记忆里删掉时，它才离开中心库。见 ADR [Sync Only Project Memories](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/sync-only-project-memories.md) 和 [Sync Memories, Not Task Notes](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/sync-memories-not-task-notes.md)。

## 账本与预览 {#the-ledger-and-the-preview}

`~/.coffer/local/memory-sync.json` 只属于本机，从不同步。它记录每个来源的摘要及其产生的条目，按智能体和配置目录记录写入的每份副本及其目标路径、条目、条目版本、摘要和状态（`written`、`edited`、`removed`），交付句子的指纹、Codex 导入开关、这台机器是否确认过预览、上次同步时间及其报告。账本丢了只多一次预览：区块整体重写，每个 Codex 资源以条目 id 命名，预览会在重写发生之前把它们展示出来。

一次同步先算出完整的计划（中心库改动和副本改动），再动手写。中心库改动立即生效。副本改动只有在这台机器确认过预览、并且计划要新写或重写的副本不超过 50 份时才生效；否则计划会作为待处理预览保存到 `~/.coffer/local/memory-sync-preview.json`。**写入**严格执行这份计划，逐个重新检查目标的摘要，跳过此后变动过的；**取消**丢弃它。更新的同步会替换待处理的预览。

## 同步环节 {#the-sync-pass}

```mermaid
flowchart TD
  A["按已注册智能体列出来源"] --> B{"摘要没变？"}
  B -- 是 --> S["跳过"]
  B -- 否 --> R["读取来源"]
  R -- 失败 --> F["报告；保留它的中心库条目"]
  R -- 条目 --> E{"是副本，或只是吸收的文本？"}
  E -- 是 --> K["记录；不发布"]
  E -- 否 --> W{"看起来像密钥？"}
  W -- 是 --> H["扣下；报告"]
  W -- 否 --> P["发布到 vault/memory/（一次提交）"]
  S --> C
  K --> C
  P --> C["为已检出的项目按智能体规划副本"]
  C --> Q{"首次同步或超过 50 份副本？"}
  Q -- 是 --> V["保存为预览；等待写入"]
  Q -- 否 --> X["写入副本；更新账本"]
  X --> Y["有改动时审计 memory_synced"]
```

一个工作器在守护进程启动时运行一次同步，之后按间隔运行（默认一小时），执行者为 `system:memory-sync-worker`。它的开关和间隔是内部引擎的 `memory_sync` 环节，**每一轮**读取一次，所以在设置里改了无需重启即可生效；开关默认开启，一台机器上的第一次同步仍会先作为预览等待。**立即同步**手动运行同一个同步；同一时间只运行一次同步，运行期间的请求会得到"已在运行"的答复。失败的同步会写进日志，从不终止循环。

整个记忆层位于 `memory` 实验功能之后：关闭时，工作器跳过每一轮，`/api/v1/memory` 关闭。已写入的副本留在智能体里。

## 整理留给智能体 {#curation-stays-with-the-agents}

合并重复、纠正错误、遗忘过时内容，是每个智能体自己的事，按它自己的节奏进行：Claude Code 的 Auto Dream，Codex 的整合。Coffer 不展示、不开启也不启动它们，不为此读取智能体的任何设置或缓存，也不写任何设置。早先的版本展示过 Auto Dream 的状态，提供过**开启**和**立即整理**的移交；它们被移除了，因为那个状态来自一个没有文档的设置和一份缓存的账号默认值，Claude Code 的副本改成一个区块之后移交提示里已经列不出任何文件夹，而且智能体自己的功能应该由智能体自己来解释（[ADR](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/leave-agent-memory-curation-to-the-agent.md)）。

因此整理按智能体自己的节奏进行：一个很少使用的项目，在智能体下次整理之前，可能同时放着一份副本和智能体自己对同一教训的版本。Coffer 的正确性不依赖整理，因为它写的内容本身就是有效的。每个智能体的记忆标签页只显示 Coffer 这一侧：它在那里写了哪些副本，或者为什么写不进去。

## 撤销 {#undo}

**撤销同步**删除 Coffer 在这台机器上写入、且智能体没有修改过的每份副本，每个 `MEMORY.md` 里的标记区块和每个 Codex 记忆文件夹里的扩展文件夹，关闭自动同步，并记录 `memory_sync_undone`。它从不删除中心库条目，也不删除智能体自己写下的任何东西。让撤销精确无误的是账本：Coffer 知道它写下的每份副本及其来源。

## 审计 {#audit}

| 事件 | 何时 |
| --- | --- |
| `memory_synced` | 一次同步（或预览的**写入**）有了改动；列出发布、更新和删除的中心库条目，按智能体和路径列出写入、更新和移除的副本，扣下的记忆和失败的来源 |
| `memory_sync_undone` | 运行了**撤销同步** |

智能体自己对记忆的修改不是 Coffer 的行为，不审计。

## 没有表，也没有资源类型 {#no-table-no-resource-kind}

中心库是保险库里的文件，一台机器往智能体里写了什么记录在一个本机文件里。这一层不新增任何表，也不新增资源类型。

## 权衡与备选方案 {#trade-offs-and-alternatives}

- **不要中心库，直接同步进原生记忆。** 投递和整理都会是智能体自己的，但原生记忆只在本机，所以记忆不会跟着人去另一台机器。中心库补上了这一点，也让撤销变得精确。
- **由 Coffer 持有存储，智能体通过 MCP 工具读写。** 与智能体无关，也不碰任何智能体文件，但取决于智能体是否选择调用工具。Coffer 早先的回忆工具一生只被调用过五次。没人调用的检索不是检索。
- **只读聚合加 Hook 投递。** Coffer 保存自己的笔记，等人来整理重复项，并在会话开始和每次提问时通过 Hook 把笔记交给会话。机制最多、效果最少，而且附加在每条消息上的记忆并不受欢迎。
- **把 Coffer 的存储投射到原生位置。** 接管智能体的记忆目录并关掉它自己的记忆太过侵入，而且两种不断变化的私有格式之间不存在无损的双向映射。
- **由 Coffer 运行模型来合并记忆。** 两个智能体已经在用你使用的模型整理记忆；第二个整理者需要自己的模型连接，并在无人值守的情况下处理同样的文件。
- **第三个写入器抽象。** 两个读取器和两个写入器就各写两个。有了第三个智能体才值得抽象，不早于此。

写入器绑定了两种私有格式，其中之一（Codex 扩展）没有文档。写入器会检查它预期的布局，不符合就拒绝写入；它遵循的上游源码路径记录在模块里，并有验收测试固定文件名。

## 代码位置 {#where-it-lives-in-the-code}

| 关注点 | 位置 |
| --- | --- |
| 仓库标识、中心库条目、可移植路径、同步计划、吸收指纹和原生写入器的渲染 | 领域层的 `memory` 包 |
| 同步服务和工作器、发布、写入、报告和页面视图 | 应用层的 `memory` 包 |
| 原生记忆读取器和写入器、中心库存储、检出位置和账本 | 基础设施层的 `memory` 包 |
| `/api/v1/memory/sync/*` 路由和工作器的装配 | HTTP 表面 |
| `coffer memory` | CLI 表面 |

## 相关内容 {#related}

- 规格：[memory](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/memory/spec.md)
- 决策记录：[Sync Memory Into Each Agent's Own Memory Through a Hub in the Vault](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/sync-memory-into-each-agents-own-memory.md)、[Memory Is About the Person, Knowledge Is About the World](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/memory-is-about-the-person-knowledge-is-about-the-world.md)、[Claude Code Reads Other Agents' Memories as Text It Loads](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/claude-code-reads-other-agents-memories-as-text.md)、[Sync Memories, Not Task Notes](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/sync-memories-not-task-notes.md)、[Leave an Agent's Memory Curation to the Agent](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/leave-agent-memory-curation-to-the-agent.md)
- [记忆指南](/zh/guides/memory) · [知识架构](/zh/architecture/knowledge) · [保险库同步](/zh/architecture/vault-sync) · [持久化](/zh/architecture/persistence)
