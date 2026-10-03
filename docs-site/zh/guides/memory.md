---
title: 记忆
description: 让 Coffer 读取每个智能体学到的东西，按仓库提炼成一套笔记，并在会话开始、每次提问、以及踩到已知陷阱之前，把合适的笔记交还给智能体。
---

# 记忆 {#memory}

Coffer 读取你的智能体本来就在维护的记忆（Claude Code 的按项目笔记，Codex 的任务组和档案），把它们提炼成每个仓库一套笔记，外加一套全局笔记，并让每个智能体都能用上这些笔记。它从不往智能体自己的记忆里写回任何东西。本页讲 Coffer 读什么、笔记放在哪里、智能体怎样收到笔记、怎样确认投递在起作用、怎样用触发器守住一个已知陷阱，以及怎样浏览、关闭和重建这些笔记。

## 记忆聚合用来做什么 {#what-memory-aggregation-is-for}

每个智能体都有自己的记忆，彼此却看不到对方的。Claude Code 上午在某个仓库学到的东西，Codex 下午还得重新学一遍。

Coffer 弥合这个缺口，但不接管任何一个智能体的记忆：

1. **读取。** Coffer 读取每个已注册且已启用的智能体的原生记忆文件。它从不在那里创建、修改、移动或删除任何东西，也从不改动智能体的记忆设置。
2. **提炼。** Coffer 自己的模型把读到的内容改写成 Coffer 自己措辞的笔记，一个主题一个文件；两个智能体分别学到的同一条经验会合并成一条笔记。
3. **投递。** 安装好的 Hook 在三个时机把笔记交还给智能体：会话开始时给出当前仓库和 `global` 的索引；你发送提问时给出该提问点到的几条笔记；在某条命令运行之前，给出你绑定到这条命令上的那条笔记。

记忆不是[知识](/zh/guides/knowledge)。知识是你或智能体刻意写下的关于外部世界的东西；记忆是智能体在工作中学到、被自动收集起来的东西。

| | 记忆 | 知识 |
| --- | --- | --- |
| 来源 | 智能体自己的记忆文件，只读 | 你，或者智能体把它写下来 |
| 组织方式 | 按仓库，外加 `global` | 按知识集 |
| 谁写存储的文本 | Coffer，通过提炼 | 你和智能体，直接写 |
| 怎样到达智能体 | 通过 Hook：会话开始时给索引，每次提问时给匹配的笔记，已知陷阱之前给触发器的笔记 | `coffer-guide` 技能指向那里时，智能体自己去读 |
| 存储丢了怎么办 | 从智能体自己的记忆重建 | 就没了 |

## Coffer 读什么 {#what-coffer-reads}

| 智能体 | 读取的文件 |
| --- | --- |
| Claude Code | `<config_dir>/projects/<project>/memory/*.md` 里的每个事实文件：frontmatter 里的 `name`、`description` 和 `type`，以及正文。Claude Code 自己的 `MEMORY.md` 索引会被跳过。 |
| Codex | `<config_dir>/memories/MEMORY.md`（每个任务组的偏好、可复用知识和失败记录），以及 `memory_summary.md`（档案、长期偏好，以及 Codex 为每个任务组列出的检索词）。 |

Coffer 不读会话记录，也不读 rollout 文件。两个智能体本来就会把自己的会话提炼进记忆，Coffer 从那里开始。

如果某个智能体的记忆格式变了，某个文件再也解析不了，那么这个智能体在这一轮里什么都不贡献，失败会连同文件路径和原因一起报告出来；另一个智能体的记忆照常读取，之前各轮留下的笔记也原样保留。

## 分区 {#partitions}

**分区**是 `~/.coffer/derived/memory/` 下的一个文件夹。每个仓库一个，另有一个名为 `global` 的分区：

- 一个条目归档到它被学到时所在的仓库。主检出、它的各个 worktree，以及同一个仓库的另一份克隆，都对应同一个分区，分区以仓库的目录名命名。
- 关于**你本人**而不是某个项目的条目（类型 `user`：你的偏好、Codex 的档案），无论来自哪个仓库，都归到 `global`。
- 关于怎样工作的指导（类型 `feedback`）归到给出它的那个仓库，因为它通常只约束那个仓库。只有在任何仓库之外给出的 feedback 才归到 `global`。
- 在一个不是仓库的目录里学到的条目不会产生分区。由提炼这一轮来决定它归到 `global` 还是哪里都不放。

分区只由聚合创建，你不需要自己建。

```text
~/.coffer/derived/memory/
├── global/
└── payments-api/
    ├── MEMORY.md      ← the index: one line per note
    ├── notes/         ← Coffer's notes, one topic per file
    │   └── retry-budget-for-ledger-writes.md
    ├── RETIRED.md     ← notes that were retired, and why
    └── .raw/          ← what was read from the agents, verbatim (hidden)
```

| 文件 | 内容 |
| --- | --- |
| `MEMORY.md` | 索引。每行给出一条笔记的标题、它的文件、一句能独立成立的描述，以及来源提供的检索词，最新的在前。会话收到的就是它。 |
| `notes/<slug>.md` | 一条笔记。frontmatter 里有 `title`、`description`、`type`（`user`、`feedback` 或 `project`）、`origins`（构成这条笔记的每个智能体文件）、`created_at` 和 `updated_at`，有时还有 `search_terms`。正文是 Coffer 自己的措辞。 |
| `RETIRED.md` | 每条已退役笔记的标题、原因，以及取代它的笔记。下一轮会读这个文件，这样同一个没变过的来源不会把已退役的主题又带回来。当构成一条笔记的所有原始条目都已离开 `.raw/`（智能体删掉了那条事实，或者它现在归到了另一个分区）时，这条笔记也会在这里退役，原因写作「its sources are gone」；这类记录不会阻止该主题以后回来。 |
| `.raw/` | 每个条目读到时的原样内容，附带智能体、来源路径和读取时间。它是提炼这一轮的输入，也让你能拿一条笔记去对照它原来的文字。它不在 Web 界面里显示，也不能通过分区的文件路由读取；要看就到磁盘上 `coffer path memory <partition>` 下面打开。 |

`~/.coffer/derived/memory/` 下的一切都是派生的，随时可以删掉再重建，而且[保险库同步](/zh/guides/vault-sync)不会带上它：每台机器都根据自己装的智能体各自构建。

## 各轮如何运行 {#how-the-passes-run}

有两个后台轮次让分区保持最新，默认都开启。

| 轮次 | 做什么 | 默认计划 | 是否用模型 |
| --- | --- | --- | --- |
| **从智能体读取**（聚合） | 读取每个已启用智能体的记忆文件，把新条目写进 `.raw/`。自上一轮以来内容没变的来源文件会被跳过。 | 守护进程启动时一次，之后每小时一次 | 否 |
| **提炼记忆** | 对每个分区，把新条目对照索引分派：并入某条笔记、新开一条笔记、让某条笔记退役，或者什么都不留；然后只重写有变化的笔记，并重写 `MEMORY.md`。 | 启动后约一分钟一次，之后每 6 小时一次 | 配置了模型时用 |

两个轮次各有各的定时器：提炼不会等聚合（要两个一起跑，用[更新记忆](#run-a-pass-now)）；一个分区自上次提炼以来没有新条目，就不花一次模型调用。提炼是增量的：分派请求只带新条目和索引行，从不带笔记正文；每条被改到的笔记各用一个小请求重写。两个智能体关于同一条经验的条目，不管措辞差多远，最后都会落到同一条笔记里，它的 `origins` 会同时列出两者。

**没有内部模型时。** 如果没有配置 Coffer 的模型（见[模型提供商](/zh/guides/providers)），提炼照样运行，只是机械地运行：每个条目各自成为一条笔记，`MEMORY.md` 根据它们的 frontmatter 写出。你得到的是一份更单薄的索引，而不是一份空索引，而且不会调用任何模型。

::: info 什么会离开你的机器
只有提炼这一轮会把记忆内容发出去，而且只发给你配置的模型接入地址。聚合和投递什么都不发；提问时的排序在守护进程内部完成。
:::

### 修改计划 {#change-the-schedule}

在「记忆」页头里，**自动 · 每小时**会打开一个弹出框，里面有一个开关**自动读取记忆**和一个间隔。这个开关同时打开或关闭聚合和提炼；间隔是读取智能体记忆的频率，提炼保留它自己更慢的间隔。弹出框还会显示上次读取记忆的时间和下次读取的时间。页头会显示上次读取智能体记忆的时间（*14 分钟前读取*），如果某个智能体的记忆读不出来，也会在这里说明：页面上会出现一条警告横幅，写明智能体和路径，带**重试**和**交给智能体 ▾**，它的提示词请智能体修好读取权限；**更新记忆**运行期间，它显示*正在提炼第 2 / 5 个分区*。在命令行上，每个轮次都有各自的开关和间隔：

```sh
coffer config list engine.upkeep.
coffer config set engine.upkeep.aggregate.interval 1800
coffer config set engine.upkeep.distil.enabled off
coffer config unset engine.upkeep.distil.interval     # back to the default interval
```

修改无需重启即可生效。最短间隔是 60 秒。

### 立即运行一轮 {#run-a-pass-now}

::: code-group

```sh [CLI]
coffer memory sync                    # update memory: read every agent, then distil
```

```text [Web UI]
Memory → Update memory
Memory → choose the partition → Update memory
```

:::

**更新记忆**（`coffer memory sync`、`POST /api/v1/memory/sync`）一个动作跑完两个轮次：先读取每个已注册智能体的最新记忆，再提炼每个有了新条目的分区。它会报告在多少个分区里读到了多少条目、哪些来源解析失败，以及提炼了哪些分区。某个分区的提炼已经在运行时，会报告为已跳过，而不会让整个更新失败。分区列表页和单个分区页上的这个按钮是同一个。每个分区同一时间只跑一个提炼轮次。`coffer daemon status` 会显示当前正在运行什么。

## 智能体如何收到记忆 {#how-agents-receive-memory}

记忆在三个时机到达会话：

| 时机 | 智能体得到什么 | Hook 事件 |
| --- | --- | --- |
| **会话开始** | `global` 和会话所在仓库的索引，以及笔记在哪里 | `SessionStart` |
| **你发送的每次提问** | 你的提问点到的至多三条笔记（如果有匹配得足够好的） | `UserPromptSubmit` |
| **已知陷阱之前** | 你标记为陷阱的命令会被拦下一次，并以那条笔记作为原因；命令输出里出现已知错误时，会带出对应的笔记 | shell 上的 `PreToolUse` / `PostToolUse` |

三者都经过同一个 Hook，在你把智能体接入 Coffer 时安装进智能体自己的设置。这个设计背后的决策和依据见决策记录（ADR）[记忆在三个时机到达会话](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/memory-reaches-a-session-at-prompt-time-and-before-a-known-trap.md)。

### 安装 Hook {#install-the-hook}

投递借助每个智能体自己的 Hook 机制。这个 Hook 是智能体[接入 Coffer](/zh/guides/agents#connect-an-agent-to-coffer) 的其中一部分：接入智能体时安装它，断开时移除它。Coffer 从不把它装进你没有接入的智能体。

::: code-group

```sh [CLI]
coffer agent connect claude-code
coffer agent show claude-code               # lists the hook with the other parts
coffer agent hooks claude-code              # the hook's four entries, and whether it is current
coffer agent disconnect codex
```

```text [Web UI]
Agents → choose the agent → Connect to Coffer
```

:::

安装的是四个条目，每个事件一个，写在智能体的设置文件里：Claude Code 是 `~/.claude/settings.json`，Codex 是 `~/.codex/hooks.json`。

| 事件 | 何时触发 | 超时 |
| --- | --- | --- |
| `SessionStart` | 启动、恢复、清空和压缩时 | 10 秒 |
| `UserPromptSubmit` | 你发送的每次提问 | 5 秒 |
| `Bash` 上的 `PreToolUse` | 每条 shell 命令之前 | 5 秒 |
| `Bash` 上的 `PostToolUse` | 每条 shell 命令之后 | 5 秒 |

每个条目都运行同一条命令 `coffer memory hook --agent-uid <uid> --cwd "$PWD"`，并用完整路径调用 `coffer`（通常是 `~/.coffer/bin/coffer`），因为智能体运行 Hook 的 shell 的 `PATH` 里可能没有 `~/.coffer/bin`。这条命令读取智能体交给它的事件，用两个智能体都能读的 JSON 作答。每个条目都带有 `coffer-memory` 标记，这样 Coffer 能准确找到并移除它自己的条目。安装两次也只会每个事件留一个条目；移除只拿掉 Coffer 的条目，其他 Hook 和设置一概不动。Hook 在智能体的设置里，不在它的记忆文件里。

::: warning Codex 需要你批准全部四个条目
Codex 只运行你批准过的 Hook，没批准的会被悄无声息地跳过。接入一个 Codex 智能体之后，以及每次 Coffer 更新改变了 Hook 的命令之后，打开 Codex，运行 `/hooks`，信任 Coffer 的四个条目：`SessionStart`、`UserPromptSubmit`、`PreToolUse` 和 `PostToolUse`。没批准的条目只会被跳过，所以如果只信任 `SessionStart`，你只会得到索引，别的都没有。Coffer 不会自己批准自己的 Hook，只会报告它未被信任。智能体的**钩子**标签页、`coffer agent hooks <name>` 和待处理列表都会在缺少批准时显示出来。
:::

守护进程会让已安装的 Hook 保持最新。每一轮调和时，它都会把命令或事件集合与当前运行版本不一致的 Hook 重写回当前的四个条目。它从不给没有 Hook 的智能体添加 Hook。

Hook 是否已安装、是否最新、是否被信任，显示在**智能体**的页面上（它的连接状态和**钩子**标签页），而不在记忆页面上。[确认它在起作用](#see-it-working)里的投递视图只报告投递了什么，从不报告 Hook 的状态。

### 会话开始时：索引 {#at-session-start-the-index}

会话开始时的上下文依次包含：

1. `global` 分区的索引：关于你已知的东西；
2. 会话所在仓库对应分区的索引；
3. 该分区 `notes/` 文件夹的绝对路径，并说明笔记正文要当作文件读取；
4. 记忆根目录（`~/.coffer/derived/memory/`），它涵盖所有分区，所以另一个仓库的笔记，智能体用自己的工具搜一下就能找到。

Hook 输出的内容上限是 9,500 字节，低于两个智能体对 Hook 输出的限制：Claude Code 对超过约 10,000 个字符的内容只给模型看一小段预览，Codex 会把超过约 2,500 个 token 的内容从中间截掉。大型保险库的索引会超过这个大小。索引放不下时，最旧的行先被丢弃，当前仓库的行优先于 `global` 的行保留，并且文本会说明丢了多少行、哪个文件夹里还留着它们，每条笔记仍然都能当作文件读取。

### 每次提问时：你的提问点到的笔记 {#at-each-prompt-the-notes-your-prompt-names}

你发送提问时，Coffer 会拿当前仓库分区和 `global` 的笔记对它做排序，匹配每条笔记的标题、描述、检索词和正文中的词语，中文文本也能匹配。越过相关度门槛的最好的**三条**笔记会被加入会话，每条给出文件路径和一行说明：

```text
Coffer memory: notes recorded for this user that may apply to this request. …
- (/Users/you/.coffer/derived/memory/payments-api/notes/retry-budget-for-ledger-writes.md) a fact they recorded: Retry budget for ledger writes — ledger writes retry three times, then park in the dead-letter table.
```

- 一条笔记**每个会话只给一次**。之后的提问再点到同一条笔记，也不会再带进来，即使守护进程重启过。
- 很短的提问（少于三个词），以及 `continue`、`ok` 或 `继续` 这样的催促，不会带进任何东西，所以只是顺着往下聊的对话不花任何代价。
- 整个追加内容保持在 1.5 KB 以下。
- 排序只是对笔记文件做普通的词语匹配。不做 embedding，也没有任何东西离开你的机器。

### 已知陷阱之前：触发器 {#before-a-known-trap-triggers}

有些错误出在某条命令上：在错误的 Node 版本下运行 `make verify`，合并 PR 后忘了清理 worktree，用 BSD 的 `sed` 配 `\b`。关于它的笔记就放在索引里，二十个轮次之后照样出错。**触发器**把这样一条笔记绑到那条命令上，让智能体在关键时刻看到这条笔记。

- **`block`** 触发器会在一个会话中把第一条匹配的 shell 命令拦下**一次**，并把笔记作为原因告诉智能体。智能体的下一次尝试会被放行，所以如果那条命令本来就没问题，它再运行一次就行。
- **`context`** 触发器从不拦截。当一条命令的输出里出现已知错误时，它会在命令之后加上那条笔记，让智能体按已知的方式恢复。

笔记的措辞是你的长期规则或你记录下的事实，从不写成对智能体的命令，这样智能体会把它读成关于你的信息，而不是来自未知来源的指令。

触发器归你所有：由你来写，或者由你接受 Coffer 的提议。不会替你预先设置任何东西。见[用触发器守住已知陷阱](#guard-a-known-trap-with-a-trigger)。

### 在消息渠道的轮次中 {#in-channel-turns}

来自[消息渠道](/zh/guides/channels)的轮次由 Coffer 自己驱动，所以这个轮次的索引和笔记也由它自己投递。对已接入 Coffer 的智能体，它在这个轮次里仍会运行 Coffer 的 Hook，而 Hook 在会话开始和每次提问时会让开，所以不会重复到达：

- **索引。** 会话开始时的内容（`global` 索引、对话工作目录对应分区的索引，以及笔记在哪里）会进入这个轮次的系统提示词。索引为空时，这个轮次完全没有记忆开头。
- **你的消息点到的笔记。** Coffer 会像[每次提问时](#at-each-prompt-the-notes-your-prompt-names)一样，拿你发的每条消息对笔记排序（同样的三条上限、相关度门槛和大小上限），并把找到的内容加在智能体收到的你的消息之后。一条笔记每个对话只给一次，每次投递都会作为该智能体的一次 `prompt` 触发记录到审计日志。你的消息在对话里按你写的原样保存。

这些都不需要安装任何东西。在已接入的智能体上，触发器照样生效：在消息渠道的轮次里，Hook 仍会在每条命令前后作答，所以一个已启用的 `block` 触发器会在那里拦下命令，`context` 触发器会加上它的笔记，和在终端会话里一样。

从[对话](/zh/guides/chat)页面发出的轮次不会有这个追加：它得到记忆的方式和终端会话一样，在智能体已接入 Coffer 时通过智能体自己的 Hook 获得。没有哪个轮次会同时通过两种方式得到记忆。

### 按需：搜索记忆根目录 {#on-demand-search-the-memory-root}

需要另一个仓库（不是会话所在的那个）的笔记时，智能体用自己的文件工具搜索记忆根目录：对 `~/.coffer/derived/memory/` 执行 `grep` 一次覆盖所有分区，而会话开始时的内容会告诉它这个根目录。每条笔记都是一个 Markdown 文件，frontmatter 里有它的标题和一行描述。`coffer path memory` 打印根目录，`coffer path memory <partition>` 打印某个分区的文件夹。没有记忆工具：Coffer 不暴露任何让智能体调用的东西。

也没有让智能体通过 Coffer 写记忆的工具。智能体照常把东西记进它自己的记忆，Coffer 在下一轮读取。`coffer-guide` 技能会把这一点告诉智能体。

## 确认它在起作用 {#see-it-working}

**本周记忆投递了什么。** 对每个装有 Hook 的智能体，统计最近七天里：记忆到达它多少次，最后一次是什么时候，以及它的会话实际打开过多少条不同的笔记。

::: code-group

```sh [CLI]
coffer memory delivered
# claude-code: 142 deliveries in 7 days, notes read: 9, last: 2026-09-30T08:12:03Z
# codex: 37 deliveries in 7 days, notes read: unavailable, last: 2026-09-29T17:40:11Z

coffer memory delivered --json      # the same, with the count split by moment
```

```text [Web UI]
Memory → Delivered at session start
```

:::

在**记忆**页面上，**会话开始时投递 · 最近 7 天**区块每个智能体一行：*最近 7 天投递 42 次 · 读了 17 条记忆条目 · 最后一次 12 分钟前*。这段时间内什么都没收到的智能体显示**最近 7 天没有投递**。这个区块从不显示 Hook 本身；Hook 的状态和**修复**在智能体的页面上。

按时机（`session_start`、`prompt`、`guard`、`error`）拆分的计数在 `--json` 的结果里。「读取的笔记」是根据智能体的工具调用在记忆根目录下打开过的文件路径统计的；Coffer 从不读取消息或工具结果的内容。当 Coffer 读不到该智能体的会话记录时，它显示 **unavailable**（界面上是「读取条数不可用」），这和零不是一回事。

**某个分区所在仓库里，智能体在会话开始时到底拿到了什么**：和 Hook 会输出的文本相同，组合方式也相同：

::: code-group

```sh [CLI]
coffer memory delivered payments-api
coffer memory delivered payments-api --agent codex
```

```text [Web UI]
Memory → choose the partition → Delivered
```

:::

在 Web 界面里，分区的**投递内容**标签页（`/memory/<uid>/delivered`）以只读方式显示这段文本，可以在已接入的智能体之间切换（Claude Code 在前），并显示字符长度和一个**复制**按钮。

**每一次投递，逐条查看。** 每次投递都是一条审计事件，写明时机、会话以及它带的笔记（从不带笔记的内容）；触发器的触发还会写明是哪个触发器：

```sh
coffer log audit --event-type memory_delivery_fired --limit 20
```

同样的事件也可以在[活动](/zh/guides/activity)页面上查看。

## 用触发器守住已知陷阱 {#guard-a-known-trap-with-a-trigger}

触发器用 `<partition>/<slug>` 指定一条笔记（分区名，加上不带 `.md` 的笔记文件名），再加一个正则表达式。当你有一条关于某个命令、而智能体老是弄错的笔记时，就写一个：

```sh
# Hold `make verify` once per session, unless the command already puts Node 20 first.
coffer memory trigger add \
  --note coffer/frontend-vitest-needs-node-20 \
  --command '^make verify' \
  --unless 'v20'

# After any command whose output says GNU timeout is missing, add the note.
coffer memory trigger add \
  --note global/macos-has-no-gnu-timeout \
  --kind context \
  --error 'timeout: command not found'
```

你写的触发器写好就已启用，从下一条匹配的命令开始生效。它只在能访问到它那条笔记的会话里生效：`global` 笔记的触发器处处生效，某个仓库笔记的触发器只在那个仓库的会话里生效。无法编译的模式会以 `MEMORY_TRIGGER_INVALID` 被拒绝，并且什么都不会写入。

每个触发器是 `~/.coffer/vault/memory-triggers/` 下的一个 Markdown 文件，设置写在 frontmatter 里。你可以在编辑器里读或改它。它和记忆树分开存放，所以重建分区永远不会丢掉触发器。它是保险库内容，所以设置了[保险库同步](/zh/guides/vault-sync)时，它会和你的知识、技能一起传到你的其他机器上。给智能体看的原因是笔记当前的文本，所以提炼这一轮重写笔记时，触发器的消息也会跟着变。

### 审阅并启用提议 {#review-and-arm-proposals}

当提炼这一轮重写一条描述了与某个具体命令相关的陷阱的笔记时，它可能会为它**提议**一个触发器。提议在你启用它之前不会做任何事。

```sh
coffer memory trigger list
# frontend-vitest-needs-node-20-3fa1c2  armed  block  coffer/frontend-vitest-needs-node-20  ^make verify
# worktree-cleanup-after-merge-9b04e1  proposed  block  coffer/worktree-cleanup-after-merge  ^gh pr merge

coffer memory trigger arm worktree-cleanup-after-merge-9b04e1      # accept a proposal
coffer memory trigger disarm frontend-vitest-needs-node-20-3fa1c2  # stop it; it stays, as a proposal
coffer memory trigger delete worktree-cleanup-after-merge-9b04e1   # remove its file
```

只有人能启用触发器。每一次添加、提议、启用、停用和删除都会连同触发器及其笔记记录到审计日志。

### 写出精确模式的技巧 {#tips-for-tight-patterns}

- **写出真正运行的命令。** `--command` 模式从命令行执行的每个程序（`&&`、`||`、`;` 和 `|` 之间的每一段）的开头开始匹配，连同它的参数；匹配前会去掉 `VAR=value` 前缀，并去掉程序所在的目录。当程序是运行脚本的 shell 或解释器（`bash`、`sh`、`zsh`、`python3`、`node` 等）时，这一段改为从脚本名开始。所以 `make\s+verify` 能匹配 `make verify` 和 `cd web && make verify`，但不匹配 `grep "make verify" Makefile`；`e2e` 能匹配 `bash scripts/e2e.sh`，但不匹配 `cat scripts/e2e.sh`。只出现在后面某个参数里的词永远不会匹配。
- **用 `--unless` 放过正确的写法。** `--unless` 模式针对整条命令测试，包括前缀。如果命令已经做到了笔记要求的事，比如 `PATH=$HOME/.nvm/versions/node/v20.20.2/bin:$PATH make verify`，触发器就保持安静。
- **宽松的模式代价很小，并不危险。** 匹配过多的模式，代价是每个会话多拦下一条无害的命令：智能体读完笔记再运行一次就行。不过，看到它在不该触发的地方触发时，还是把它收紧；`coffer log audit --event-type memory_delivery_fired` 每次都会写明是哪个触发器。
- **用单引号括住模式**，让你的 shell 不去动它。

## 浏览记忆 {#browse-memory}

### Coffer 的分区 {#coffer-s-partitions}

::: code-group

```sh [CLI]
coffer memory list                             # partitions, note counts, repositories
coffer memory show payments-api
coffer path memory payments-api                 # MEMORY.md, notes/, RETIRED.md
cat "$(coffer path memory payments-api)"/MEMORY.md
cat "$(coffer path memory payments-api)"/notes/retry-budget-for-ledger-writes.md
```

```text [Web UI]
Memory → choose the partition
```

:::

在 Web 界面里，一条笔记叫作**记忆条目**（英文界面里是 memory）：每个主题一条。**记忆**页面的标题旁带**实验性**标签；它的主操作是**更新记忆**，旁边是**自动 · 每小时**。它在**会话开始时投递**区块下方用表格列出分区：分区、它的路径（`global` 显示为**所有项目**）、**示例记忆**（最近更新的那一条，或者有多少条目在等待提炼）、它的记忆条目数、**来源**（它学自哪些智能体）以及说明上次提炼时间的**已提炼**列。健康的行是灰色的，只有**仓库已不在**会着色。还没有任何分区时，它显示首次使用的欢迎面板**还没有提炼出任何东西**：带有**更新记忆**，并列出 Coffer 在这台 Mac 上找到记忆的已连接智能体；没有连接任何智能体时，则显示**打开智能体**来连接一个。仓库在磁盘上已经不存在的分区会标记为**仓库已不在**；它不再投递任何东西，并一直留在列表里，直到你删除它（见[重建分区](#rebuild-a-partition)）。

分区页面没有返回链接，也没有实验性标签：标题就是分区名，下面一行写着路径、记忆条目数和上次提炼的时间。它有两个标签页：

- **记忆条目**（默认）列出分区的记忆条目（每条显示标题和一行描述），旁边是选中的那一条。选中的记忆条目显示标题、一行写明它学自哪些智能体和最近更新时间的说明（*学自 Claude Code, Codex · 更新于 …*），以及正文，并为它自己的文件提供**在编辑器中打开**和**在 Finder 中显示**；列表和记忆条目撑满窗口，在内部滚动。列表下方，折叠起来的**已退役**组以只读方式列出已退役的记忆条目以及每条的原因。在没有设置 Coffer 的引擎时，页面上有一条横幅，说明在**设置 › 通用**里设置它之前，每个智能体的条目仍是它自己的记忆，并带有**打开设置**。还没提炼的分区不显示列表，只显示一个空状态。
- **投递内容**显示在这个分区的项目里，每个智能体会收到的会话开始文本（见[确认它在起作用](#see-it-working)）。

这个页面只显示 Coffer 的记忆条目。它不显示文件树，不显示 `MEMORY.md` 或 `RETIRED.md`，不显示 `.raw/`，不显示原生路径，也不显示任何智能体的原文；这些都留在磁盘上、REST 路由里和命令行中。没有针对单条记忆条目的操作：记忆条目是派生的，你的编辑会被下一轮提炼重写。页头的 **⋯** 菜单提供**在文件管理器中显示分区文件夹**、**复制路径**，**在活动中查看提炼记录**（“变更”标签页，每一轮提炼都记录在那里），以及只在仓库不在时才出现的**删除分区…**。

一条笔记的 `origins` frontmatter 写明了构成它的每个智能体文件，`.raw/` 保存了每个条目读到时的原样，所以一条读起来不对的笔记，你可以一路追溯到智能体实际记录的内容。

### 智能体自己的记忆 {#an-agent-s-own-memory}

要查看智能体为自己保存的记忆，打开**智能体 → 选择智能体 → 更多 → 记忆**。tab 以该智能体的 **Coffer 的记忆**开头——它的记忆 Hook、最近触发的时间和投递的内容——下面按项目、路径和条目数列出该智能体自己的每个原生记忆库。选中一个即可以只读方式浏览其中的文件。这些文件归智能体所有、由智能体重写；想改的话，在你的编辑器里打开。你在那里做的修改，会在下一轮聚合和提炼时进入 Coffer 的笔记。

## 每个分区都到达每个智能体 {#every-partition-reaches-every-agent}

分区没有开关，也没有按智能体划分的生效范围。每个分区都通过记忆 Hook 提供给每个智能体，包括对它毫无贡献的智能体，这正是聚合的意义所在。`coffer memory` 没有 `enable` 或 `disable`，通用的启用和禁用路由会以 `RESOURCE_NOT_TOGGLEABLE` 拒绝分区。

这控制的是 Coffer 交给智能体什么，而不是智能体能打开什么：笔记就是 `~/.coffer/derived/memory/` 下的普通文件。

要让 Coffer 完全不读某个智能体的记忆，禁用那个智能体（见[智能体](/zh/guides/agents)）。

## 重建分区 {#rebuild-a-partition}

因为 `~/.coffer/derived/memory/` 下的一切都是派生的，你可以扔掉一个分区，再从智能体自己的记忆重新构建它。触发器存放在保险库里，不在分区里，所以重建不会影响它们：

```sh
rm -rf ~/.coffer/derived/memory/payments-api
coffer memory sync
```

重建后的分区从同样的来源覆盖同样的主题。它的措辞会不同，因为笔记是提炼，而不是复制。记录在被删除的 `RETIRED.md` 里的退役信息会随之丢失，所以已退役的主题可能会回来。

要把一个分区从 Coffer 里彻底移除（比如一个标记为**仓库已不在**的分区），就删除它：

::: code-group

```sh [CLI]
coffer memory rm payments-api
```

```text [Web UI]
Memory → Delete on the partition's row
Memory → choose the partition → ⋯ → Delete partition…
```

:::

Web 界面只在标记为**仓库已不在**的分区上提供**删除**：其他分区会在下一次更新时被重新创建。确认对话框会说明会有多少条已提炼的记忆条目一起删除；该文件夹对应的智能体自己的记忆不会被动到。

## 局限 {#limits}

- **适用于每次回复的规则不归记忆管。** 像「总是用中文回复」或偏好的语气这样的规则适用于每个轮次。没有哪次提问会点到它，也没有哪条命令会触发它，所以检索和触发器都不能在合适的时机把它送到。把这类规则放进智能体每个轮次都会加载的指令里：Claude Code 是 `CLAUDE.md`，Codex 是 `AGENTS.md`。这些文件归你所有，Coffer 从不写它们。
- **很小的存储很少越过门槛。** 相关度门槛是在一个真实规模的存储上调出来的。排序按每个词在整个存储里有多罕见来加权，所以只有少数几条笔记时，即使是匹配的笔记得分也很低，一次提问通常什么都带不进来。这是有意为之：它避免一个只和笔记共享常见词的提问带进噪音。随着智能体学到的东西越来越多，检索会开始起作用。
- **闲置超过一周的会话会被当作新会话。** Coffer 根据审计日志里的投递记录重建每个会话已经拿到过什么，所以守护进程重启不会让某条笔记重复出现，也不会让触发器再多拦一条命令。超过七天的记录不会读回，所以闲置那么久的会话可能会再次拿到某条笔记。
- **检索只读当前仓库的分区和 `global`。** 归档在另一个仓库下的笔记，永远不会在提问时被带进来。智能体仍然可以通过搜索记忆根目录找到它。
- **Coffer 停了，记忆也绝不会碍事。** 如果守护进程没在运行、响应慢或返回错误，Hook 什么都不输出，直接放行提问或命令。你只是丢了这一次触发的投递，仅此而已。短提问和没有触发器匹配的命令根本不会联系守护进程。

## 故障排查 {#troubleshooting}

**分区是空的或者不见了。** 检查智能体是否已注册并启用，然后运行 `coffer memory sync` 并阅读它的报告。在 git 仓库之外学到的条目不会有自己的分区。

**智能体没收到它的记忆。** 运行 `coffer agent hooks <agent>`，确认 Coffer 的 Hook 在全部四个事件上都是最新的（如果显示 **needs repair** 或过期，重新接入这个智能体）。对 Codex，检查四个条目在 `/hooks` 里是否都已信任。然后运行 `coffer memory delivered` 看本周记忆是否到达了这个智能体，再运行 `coffer memory delivered <partition>` 看它在会话开始时到底拿到了什么。

**提问没带进任何笔记。** 短提问和催促从来不会。除此之外，就是提问里的词和这个仓库或 `global` 的任何笔记都匹配得不够好；存储里只有几条笔记时这很正常（见[局限](#limits)）。会话已经拿到过的笔记不会再给一次。

**触发器从来不触发。** 查看 `coffer memory trigger list`：提议在你启用之前一直显示 `proposed`。仓库笔记的触发器只在那个仓库的会话里生效，而且一个触发器每个会话只拦一次命令。拿实际执行的命令去测试模式，而不是整行（见[写出精确模式的技巧](#tips-for-tight-patterns)）。

**触发器拦下了不该拦的命令。** 收紧它的 `--command` 模式或加一个 `--unless`：删掉触发器再重新添加，或者编辑 `~/.coffer/vault/memory-triggers/` 下它的文件。在那之前，它每个会话的代价是拦下一条命令。

**笔记读起来像来源的副本，一个条目一条。** 没有配置 Coffer 的模型，所以提炼在机械地运行。到**设置 › 通用 → Coffer 自用模型**配置它；之后通过 `coffer memory sync` 或下一轮定时运行提炼的条目会经过模型。

## 相关内容 {#related}

- [知识](/zh/guides/knowledge)
- [技能](/zh/guides/skills)：`coffer-guide` 技能告诉智能体记忆如何工作
- [智能体](/zh/guides/agents)
- [记忆架构](/zh/architecture/memory)
- [MCP 工具参考](/zh/reference/mcp-tools)
- [记忆规格](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/memory/spec.md)
- [聚合智能体的记忆，从不写入](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/aggregate-agent-memory-never-write-it.md)
- [记忆在三个时机到达会话](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/memory-reaches-a-session-at-prompt-time-and-before-a-known-trap.md)
