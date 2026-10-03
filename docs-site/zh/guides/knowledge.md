---
title: 知识
description: 把你和智能体对工作环境的了解，存成一个个 Markdown 文件夹，每个智能体都用自己的文件工具读取。
---

# 知识 {#knowledge}

知识是一个存放工作环境相关 Markdown 文档的目录：服务、仓库、约定、决策、坑，这台机器上的每个智能体都会读。本页讲如何创建知识集、添加和编辑文档、Coffer 的整理如何把新条目并入文档、如何回看每一次改动并撤销，以及智能体如何找到这些内容。

## 知识用来做什么 {#what-knowledge-is-for}

知识存放的是你所处环境里的事实：哪个团队负责某个服务，某个内部 API 怎么鉴权，某个迁移为什么按这个顺序。它之所以在那里，是因为你或者和你一起工作的智能体把它放了进去。

- **所有智能体共用一份。** Claude Code 和 Codex 读的是同一批文件，一个智能体上午记下的东西，另一个下午就能读到。
- **普通文件。** 每篇文档都是一个 Markdown 文件，你可以打开、编辑、grep、备份。Coffer 不建索引、不做 embedding，也不在数据库里另存一份内容。
- **共同编写。** 你在知识页面或自己的编辑器里编辑文档，智能体提交新条目。Coffer 的整理会把每个条目并入已经覆盖该主题的文档，让一条事实只存在一个地方，而不是堆成一堆笔记。

知识不是[记忆](/zh/guides/memory)。记忆是智能体在工作中学到的东西，从它们各自的记忆库里读出来；知识是有人刻意写下来的东西。

## 知识集的结构 {#how-a-collection-is-laid-out}

**知识集**是知识根目录下的一个顶层文件夹：

```text
~/.coffer/vault/knowledge/
└── payments/                     ← one collection
    ├── README.md               ← what this collection is about
    ├── session-ownership.md    ← a document
    ├── gateway/
    │   └── rate-limits.md      ← nesting is allowed and means nothing
    └── .inbox/                 ← hidden: items waiting to be curated
```

- **文档**是知识集里的 Markdown 文件。文档的路径就是它的身份，没有单独的 id。文件名是标题的 slug，重名时加 `-2` 这样的后缀。
- 知识集里的**文件夹**是可选的，不代表任何含义。你或整理都可以创建、移动、删除它们。
- 知识集根目录的 **`README.md`** 描述这个知识集。它的第一段就是 Coffer 所有显示知识集描述的地方用的描述，也是 `coffer-guide` 技能告诉智能体这个知识集讲什么的依据。它从不作为文档列出、计数或整理。
- **隐藏条目**（以 `.` 开头的名字）不计入任何文档数，也不进目录。Coffer 在知识集里只写一个隐藏条目：`.inbox/` 文件夹，提交的条目在这里等待整理。知识页面把 `.inbox/` 显示为该知识集的**收件箱**，并显示有多少条目在等；其中的条目可以读，但不能编辑或删除；其他隐藏条目都不会列出。

知识根目录位于保险库仓库 `~/.coffer/vault` 里，`coffer path knowledge` 会打印出来。它不能挪到别处：保险库外的目录树，它的历史就看不到了。

### Frontmatter {#frontmatter}

每篇文档都带 YAML frontmatter：

```markdown
---
title: Session ownership
description: Which service owns user sessions, and where the TTL is configured.
actor: user
created_at: 2026-09-20T08:14:03.512840+00:00
updated_at: 2026-09-22T10:02:41.090311+00:00
---

The `account-session` service owns ...
```

| 键 | 含义 |
| --- | --- |
| `title` | 文档标题。 |
| `description` | 一句话说明文档讲什么。智能体在目录里看到的就是它。 |
| `actor` | `user` 或 `agent`，表示来源条目是谁写的。 |
| `created_at`、`updated_at` | 时间戳。 |

你加的其他键，Coffer 每次重写文件时都会连同值一起保留。Coffer 不会往文档里写任何东西来记住整理看过什么：这些信息保存在本机的 `~/.coffer/local/curation.json` 里，记录的是整理上次确认每篇文档时它的内容。

::: tip 写主题，不写文件名
文档里不能用文件名或路径去引用另一个知识文件，因为整理重组知识集时路径会变。要写「见网关限流的说明」，不要写「见 `gateway/rate-limits.md`」。违反这条规则的文档，整理会拒绝写入。
:::

## 创建知识集 {#create-a-collection}

知识集只能有意创建。读、写或者智能体的工作目录都不会自动创建知识集。

::: code-group

```sh [CLI]
coffer knowledge add payments --description "Payments platform: ownership, APIs, data flows."
```

```text [Web UI]
Knowledge → New collection → Name, What belongs in here → Create collection
```

:::

这会创建 `~/.coffer/vault/knowledge/payments/`，如果你给了描述，还会创建一个装着这段描述的 `README.md`。在知识页面上，**新建知识集**会同时要求填写名称和「这里放什么」。知识集没有标题：所有页面和列表都按文件夹名显示它。它的描述就是 README 的开头一段：可以在知识集页面直接修改（点一下文字，离开输入框时保存），也可以用 `coffer knowledge edit payments --description "…"`，或者直接改文件。不管哪种方式，都只改这一段，下面写的内容保持不变。`coffer knowledge edit payments --name <new>` 会重命名知识集，并连同目录一起移动。

列出已有的知识集：

```sh
coffer knowledge list
```

**知识**页面的树里显示的是同一份列表，每个知识集带文档数，下面是它的**收件箱**以及待整理条目数。只有这里能看到等待中的条目数，侧边栏不会为它们显示角标。

## 添加知识 {#add-knowledge}

有六种方式。其中五种是往知识集隐藏的 `.inbox/` 里提交一个**条目**，再由整理把它并入文档；第六种是你自己编辑文件，直接修改文档。

### 由智能体提交：`coffer__write` {#from-an-agent-coffer-write}

连接到 Coffer MCP 网关的智能体（见[连接客户端](/zh/guides/connect-a-client)）只有一个知识工具：`coffer__write`。它接收 `collection`、`title`、`description` 和 `body`。智能体不选文件或文件夹，也不用检查这条事实是否已经写过；放在哪里由整理决定。

`coffer-guide` 技能会告诉智能体，学到持久有效的东西时就用 `coffer__write`。你也可以直接要求：「把我们刚发现的 session TTL 记到 payments 知识集里。」

如果写入指定的知识集不存在，会被拒绝，错误信息里会列出可用的知识集。

### 从 CLI 提交：`coffer knowledge write` {#from-the-cli-coffer-knowledge-write}

```sh
coffer knowledge write --collection payments \
  --title "Session TTL" \
  --description "Where the session TTL is set and its current value." \
  --body "The TTL is 30 days, set in account-session's config key session.ttl_days."
```

### 上传文档 {#upload-a-document}

上传会把文件转换成 Markdown，并把文本作为一个条目提交。原始文件和提取出的文本都不会单独保存成文件；其中的新内容会被并入知识集的文档。没有设置 Coffer 的引擎时无从整理，上传会直接作为一篇文档加入知识集，上传对话框里也会这样说明。

::: code-group

```sh [CLI]
coffer knowledge upload ./session-design.pdf --collection payments
```

```text [Web UI]
Knowledge → Upload → choose a file and the collection → Upload
```

:::

| 接受 | 格式 |
| --- | --- |
| 转换 | `pdf`、`docx`、`pptx`、`xlsx`、`xls`、`html`、`htm`、`epub` |
| 表格 | `csv`、`tsv` |
| 按文本读取 | `md`、`markdown`、`mdx`、`txt`、`text`、`rst`、`json`、`yaml`、`yml`、`toml`、`ini`、`cfg`、`log`、`sql`，以及常见源码文件（`py`、`js`、`ts`、`go`、`rs`、`java`、`sh` ……） |

每次上传一个文件，最大 20 MB。不支持的类型会被拒绝，并指出是哪种类型（`INGEST_REJECTED`）；转换后没有文本的（比如纯图片 PDF）也会被拒绝。被拒绝的上传不会留下任何东西。

条目的 `title` 取自文档本身（第一行的 `# ` 标题，没有就用文件名）。`description` 在配置了 Coffer 自用模型时由模型撰写，没配置时取文档开头的正文。

### 用手机：在消息渠道里发 `/kb` {#from-your-phone-kb-in-a-channel}

如果你配对了一个[消息渠道](/zh/guides/channels)，先把文档作为附件发过去，再发送：

```text
/kb payments
```

Coffer 会走同样的上传流程把附件存进该知识集，并回复一条确认，写明文件和知识集。不带名称，或者名称不是你的知识集时，它会给出一张列出所有知识集的卡片供你选择。只有消息渠道的所有者才能保存。

### 自己编辑文件 {#edit-a-file-yourself}

用任何编辑器在知识集文件夹里写、改、删 Markdown 文件，本身就是修改知识的完整方式，不需要导入步骤。改动在下一次读取时就生效，下一轮整理扫描会注意到这次编辑（内容和整理上次确认的不同，而且不是整理自己或其他机器做的改动），并把它贯彻到知识集的其余部分。

在知识页面上，选中一篇文档，用**编辑**原地修改，或者用 **⋯** 菜单里的**在编辑器中打开**或**在 Finder 中显示**跳到文件。编辑器里只有文档正文：frontmatter 以只读方式显示在上方，标着*由整理维护*。编辑器是唯一需要你主动保存的地方：**放弃**会丢掉改动，**保存**（**⌘S**）保留改动；带着未保存的改动离开时，页面会先问是否不保存就离开，期间树里会用一个点标出正在编辑的文档。如果保存时发现文件在页面加载后已经在磁盘上被改过（无论是你自己的编辑器还是一轮整理改的），保存会被当作冲突拒绝（`KNOWLEDGE_FILE_CONFLICT`），文件保持原样。页面会提示文档已在磁盘上改动、你的文字没有保存，并提供**比较**、**复制我的文字**和**重新加载**，但绝不会再覆盖保存一次。**比较**会并排显示两个版本和它们的差异：**保留我的编辑**或**采用磁盘上的版本**；没被选中的那个版本仍保留在文档的历史里。**重新加载**会采用磁盘上的版本，并且会先确认，因为它会丢掉你的文字。保存下来的文件算作你的编辑，和在你自己编辑器里改的完全一样。在 CLI 下，用你自己的编辑器修改 `coffer path knowledge <collection>` 下的文件。

智能体也可以用自己的文件工具做同样的事：`coffer-guide` 技能告诉它们，读过的文档可以直接编辑来修正或补充。

## 整理 {#curation}

整理是条目变成知识的过程。它是一轮简短、有边界的处理，由 Coffer 自用的模型驱动（在 **设置 › 通用 → Coffer 自用模型** 下配置，见[模型提供商](/zh/guides/providers)）。

### 一轮整理做什么 {#what-a-pass-does}

每轮只处理**一个条目**：某个知识集收件箱里最早的条目，或者一篇在整理上次看过之后被人编辑过的文档。模型会拿到：

- 完整的条目，
- 最多五篇完整的候选文档，按条目里有辨识度的字符串做字面匹配选出，以及
- 该知识集完整的标题和描述目录，这样在候选文档都不合适时，它可以新开一篇文档。

它能在这一个知识集里列出、读取、写入和废弃文档，别的都不能碰：不能碰收件箱，不能碰 `README.md`，也不能碰其他知识集。然后它把新内容并入合适的文档，或者新开一篇。

模型遵守两条规则：

- **新的说法优先。** 条目和文档矛盾时，保留较新的说法，被取代的说法作为带日期的更正保留下来，依然可读。
- **你的编辑不动。** 如果条目是一篇你编辑过的文档，这轮整理绝不回退或改写你的文字。它会把你的改动向外贯彻：修正与之不一致的其他文档，把属于别处的段落挪过去。

一轮整理完成后，被整理的条目会从收件箱删除，被编辑的文档会以新内容记为已确认。没完成的一轮会把条目留在原处，之后再试。每轮整理是[历史](#history-and-undo)里的一次改动，所以你能看到它做了什么，也能撤销。

### 上限 {#limits}

| 上限 | 值 |
| --- | --- |
| 每轮写入次数（废弃一篇算一次） | 8 |
| 完整展示的候选文档 | 5 |
| 一轮能处理的最大条目 | 120,000 个字符 |
| 每次扫描每个知识集的轮数 | 5 |
| 每个知识集同时运行的轮数 | 1 |

一轮整理只能废弃那些内容已经在同一轮里写到别处的文档。超过大小上限的条目永远不会交给模型：收件箱条目会原样保留为一篇文档，被编辑的文档则直接记为已确认。连续三次撞到步数上限的条目也会原样保留，不再重试。

### 整理何时运行 {#when-curation-runs}

整理在后台扫描里运行，默认每小时一次，守护进程启动约一分钟后开始。所以新条目会在一小时内被整理；想马上整理，就手动整理（见下文）。每次扫描先处理收件箱条目（从最早的开始），再处理被编辑过的文档，每个知识集跑几轮。

开关和间隔在知识页面的页头修改：标题旁的 **自动 · 每小时** 会打开一个浮层，里面有开关、间隔、上次整理和下次整理的时间，以及**立即整理**。在 CLI 下：

```sh
coffer config list engine.upkeep.
coffer config set engine.upkeep.curate.interval 300
coffer config set engine.upkeep.curate.enabled off
```

最短间隔是 60 秒。改了间隔不用重启就生效。关掉扫描后，新条目会一直留在收件箱里，直到你手动整理，编辑也只在那时才被贯彻。

### 手动整理 {#curate-by-hand}

手动整理会清空一个知识集的待处理项：它拿走开始时所有待处理的东西（先是收件箱条目，从最早的开始，然后是整理上次看过之后被编辑的文档），每项跑一轮，一个接一个，直到全部处理完。它不受所有者机器限制（点按钮就是选择在这台机器上整理），但和扫描一样，当同步冲突或确认在等你处理时，会以 `KNOWLEDGE_CURATION_HELD`（409）被拒绝。收件箱条目按提交时间排序（条目自身的 `created_at`），从不按文件时间。

::: code-group

```sh [CLI]
# everything pending in the collection
coffer knowledge curate payments

# carry one edited document through, and nothing else
coffer knowledge curate payments --document gateway/rate-limits.md
```

```text [Web UI]
Knowledge → the collection's Inbox → Curate now
Knowledge → Recent changes → Curate now   (every collection with items waiting)
```

:::

在终端里等待时，CLI 会显示进度（`curating… 2 of 5 done`），然后每轮打印一行，最后给出汇总：

```text
1 of 3: ok payments/.inbox/session-ttl.md (2 written, 0 retired)
2 of 3: ok payments/.inbox/rate-limit-change.md (1 written, 1 retired)
3 of 3: ok payments/gateway/rate-limits.md (1 written, 0 retired)
payments: curated 3 of 3
```

`--json` 会为脚本打印完整结果，`coffer daemon status` 会列出正在进行的运行。

- 运行会**在第一轮失败时停止**。后面的条目保持待处理，等下一次运行或扫描。
- `truncated` 或 `too_large` 的一轮不会让它停下。
- 没有配置模型时，第一轮就把整个收件箱转成文档，运行以 `no_model` 结束。
- 运行期间新到的条目，等下一次运行或扫描。

每轮都会报告一个状态：

| 状态 | 含义 |
| --- | --- |
| `ok` | 这轮跑完，条目已确认。 |
| `up_to_date` | 没有待处理的东西。 |
| `no_model` | 没有配置内部模型；待处理的条目原样成为文档。 |
| `too_large` | 条目超过大小上限，原样保留。 |
| `truncated` | 这轮撞到步数上限。已写入的内容保留，条目之后再试。 |
| `failed` | 这轮没跑完。没有丢失任何东西，条目之后再试。 |

同一个知识集上已经有运行在进行时，新的请求会被拒绝，返回 `UPKEEP_ALREADY_RUNNING`，而不是排队。

### 没有内部模型时 {#without-an-internal-model}

如果没有配置 Coffer 自用模型，就没有任何东西需要等待：每次提交都会立刻原样成为知识集根目录下的一篇文档；手动整理会把收件箱里已有的东西都转成文档，并报告 `no_model`。不会有任何整理，但所有内容都能读。被编辑的文档不需要任何处理。

### 多台机器时 {#on-more-than-one-machine}

一轮整理会重写由[保险库同步](/zh/guides/vault-sync)在机器之间传递的文档。如果两台机器都整理，同一个条目会被并入两篇不同的文档。所以整理只在一台**所有者机器**上运行。

- 没有指定所有者时，保险库在哪里打开，整理就在哪里运行，单机时这是对的。
- 指定所有者：当保险库跨越多台 Mac 后，知识页头的**自动**浮层会显示**整理运行在**，带一个 Mac 选择器；或者在负责整理的那台 Mac 上运行 `coffer config set engine.curate_owner this`。
- `coffer config get engine.curate_owner` 会报告当前所有者，并标出没有任何已知机器认领的所有者（这种状态下整理不会在任何地方运行）；`coffer config unset engine.curate_owner` 会移除它。

整理和一轮同步永远不会同时进行；有同步冲突或待确认事项时，整理会跳过。

::: info 哪些内容会离开你的机器
整理会把条目、候选文档和目录发送给你配置的模型接入地址。上传还会把文档开头发给这个接入地址来撰写描述。知识层的其他部分不会把内容发往任何地方。
:::

## 智能体如何找到知识 {#how-agents-find-knowledge}

Coffer **没有读取、列出或搜索知识的工具**。智能体用它已有的工具按路径读文件：`Read`、`Grep`、它的 shell。

告诉它去哪里找的是 Coffer 内置的 [`coffer-guide` 技能](/zh/guides/skills#the-built-in-coffer-guide-skill)，Coffer 会把它链接进每个智能体的技能文件夹：

- 它的**描述**出现在每个会话里，列出你各个知识集的主题，取自每个 `README.md`。
- 它的**正文**在智能体打开技能时加载，给出知识根目录的路径和每个知识集里每篇文档的目录：路径、标题和描述。

目录一变，Coffer 就重写这个技能，所以新文档会在一次扫描内出现在里面。

::: details 为什么没有搜索工具
智能体会稳定地使用它已有的文件工具，却很少记得去调一个专用的检索工具。给它们一份目录和一个路径，就把检索变成了它们本来就擅长的事；而且对几百个文件做一次字面 `grep`，能准确匹配标识符和名字，模糊搜索反而会把它们弄混。完整理由见[知识架构](/zh/architecture/knowledge)。
:::

给每个知识集写一个好的 `README.md`：模型判断你的知识是否相关时，匹配的就是它的第一段。

## 浏览和阅读 {#browse-and-read}

::: code-group

```sh [CLI]
coffer path knowledge payments          # the collection's directory
ls "$(coffer path knowledge payments)"/gateway
cat "$(coffer path knowledge payments)"/session-ownership.md
```

```text [Web UI]
Knowledge → choose the collection in the tree → choose a document
```

:::

知识页面是一棵树加一个阅读窗格，两者都填满页头下方的窗口。标题带有**实验性**标签；页头上的操作是 **自动 · 每小时**（整理的开关、间隔和**立即整理**）和**上传**——这是页面唯一的主按钮，编辑文档时降为次要按钮。树的顶部，**知识集**标题栏带有**新建知识集**按钮；下面按文件夹名列出每个知识集，展开后是它的**收件箱**和各篇文档，文档按文件名显示。只有收件箱节点带数字：等待整理的条目数。**最近改动**位于知识集上方。选中一个知识集，会显示它的文件夹名、「这里放什么」（点一下即可编辑；离开输入框或按 **⌘Enter** 保存，**Esc** 取消，提示条带有**撤销**）以及它的属性：**文档**、**收件箱**（*N 个待整理*并带**打开收件箱**，或*无*）、**上次整理**（时间，或*从未*）和**文件夹**。「立即整理」正在清空收件箱时，页面显示 **整理中 · 第 n 个，共 m 个**。知识集的 **⋯** 菜单里有**在访达中显示**、**复制路径**和**删除知识集**；还没有任何内容的知识集会说明这一点，并提示你可以上传文档，或把 Markdown 文件拖进它的文件夹。选中一篇文档会渲染它，带**编辑**（见[自己编辑文件](#edit-a-file-yourself)）、Markdown 的**预览 / 源码**切换和 **⋯** 菜单（**在编辑器中打开**、**在 Finder 中显示**、**删除文档**），分两个标签页：**文档**和**历史**（见[历史与撤销](#history-and-undo)）。标题下面一行写着谁写的（如果是整理写的，带**查看这轮整理**链接）和创建时间。收件箱列出等待整理的条目（*一小时内自动整理*），带一个不显眼的**立即整理**；条目以只读方式打开，显示是谁、什么时候写的，整理归档后它就离开收件箱。手动**立即整理**结束时只弹出一条汇总提示；整理不了的条目（太大、被截断、超过步数上限）的结果写在最近改动里对应那一行上。

页面没有搜索框，也没有按知识集的开关：⌘K 可以按名称跳到某个知识集，而每个知识集都对所有智能体生效。页面上没有手敲一篇文档的表单：你通过**编辑**写，智能体通过 `coffer__write` 写。没设置 Coffer 的引擎时，没有收件箱、没有自动控件、也没有立即整理；在这个控件的位置，**整理需要 Coffer 的引擎**会带你去**设置 › 通用**，在此之前条目一到就成为文档。

这些文档就是普通文件：`coffer path knowledge` 打印知识根目录，`coffer path knowledge <collection>` 打印某个知识集的目录，你可以用自己的工具读取和 grep。

## 每个知识集都对所有智能体生效 {#every-collection-reaches-every-agent}

知识集没有开关，也没有按智能体设置的生效范围：每个知识集对所有智能体都可用，只有删除才能让它从智能体的 `coffer-guide` 技能里消失。`coffer knowledge` 没有 `enable` 或 `disable`，通用的启用和禁用路由会以 `RESOURCE_NOT_TOGGLEABLE` 拒绝知识集。

::: warning 这不是访问控制
技能会把知识根目录交给智能体，智能体可以用自己的工具读取其下的任何东西。不要把这台机器上的智能体不该读的内容放进知识集。
:::

## 历史与撤销 {#history-and-undo}

知识集的每一次改动都会作为一个版本保留：你的保存和删除、每轮整理、立刻成为文档的提交、保险库同步带进来的内容，以及在 Coffer 之外用你自己的编辑器或智能体文件工具做的编辑。每次改动都注明**写入者**：`user`、`agent`、`curation`（附带它整理的条目及提交者）、`sync` 或 `disk`，所以你总能知道谁改了什么。

历史就是保险库仓库自己的历史：知识集位于 `~/.coffer/vault` 的 `knowledge/` 下，所以 `coffer vault history knowledge/<collection>/<path>` 读到的是同样的版本，[保险库同步](/zh/guides/vault-sync)会把它们带到你的其他机器上。Coffer 的保险库需要 `git`；没有 git，守护进程不会启动，并会说明安装步骤。如果守护进程运行期间 git 没了，所有写入照常工作，历史命令会返回 `KNOWLEDGE_HISTORY_UNAVAILABLE`。这个拒绝附带一段提示词，让你的智能体按适合你机器的方式安装 git，并用 `git --version` 确认：历史标签页（*历史需要 git*）和**最近改动**（*最近改动需要 git*）会显示一行，带**重新检查**和**交给智能体 ▾**（菜单里可复制提示词），历史命令也会打印它。

### 查看文档的历史 {#look-at-a-document-s-history}

```sh
coffer knowledge history payments/session-ownership.md               # its versions, newest first
coffer knowledge history payments/session-ownership.md --version 3f2a9c1   # one version's diff
```

把任意版本恢复回来：

```sh
coffer knowledge restore payments/session-ownership.md 3f2a9c1
```

恢复本身是一个新版本，写入者是你；之前的历史保持不变。整理会把它当作你的普通编辑，贯彻到知识集的其余部分。已删除的文档也用同样的方式，从删除前的那个版本恢复。

### 查看最近改动 {#see-recent-changes}

```sh
coffer knowledge changes                 # every collection, newest first
coffer knowledge changes --collection payments   # one collection
coffer knowledge changes 8d41e07         # one change in full, with each document's diff
```

每次改动会列出写入者、时间、知识集，以及它新增、修改或删除的每篇文档和行数。各收件箱里还在等待的条目单独列出，附带提交者和时间。

在知识页面上，文档的**历史**标签页是一张按从新到旧排列的版本列表，显示写入者和行数变化。点一行，它会在原位展开成差异：**这个版本的改动**（相对上一个版本）或**与当前版本比较**，除当前版本外每个版本都有**恢复这个版本**。整理的那一行带有**查看这轮整理**链接。如果读不出历史，标签页里会显示一行**加载错误**，带**重试**和**打开活动**，文档标签页照常可用。树顶部的**最近改动**是所有知识集最近七天的时间线，按天分组，带**知识集**和**作者**筛选以及**清除筛选**（你的选择保存在页面地址里），上方显示待整理条目和**立即整理**；运行进行中时显示 **整理中 · 第 n 个，共 m 个**。一轮整理会链接到**查看这轮整理**，里面列出它改过的每篇文档，各带差异和指向其历史的链接；删除操作带有**恢复**（见[删除文档和知识集](#delete-documents-and-collections)）。

### 撤销一轮整理 {#undo-a-curation-pass}

如果你不认同某轮整理的做法，可以整体撤销：

```sh
coffer knowledge undo 8d41e07
```

这轮写入或废弃的每篇文档都会完全回到这轮之前的样子，它新建的文档会被移除，这些都作为一次由你写入的新改动完成。之后整理不会重做这一轮。这轮整理过的条目不会回到收件箱；它的文字仍在历史里。

在知识页面上，从**最近改动**打开这轮整理（或者在它写过的文档下方点**查看这轮整理**），然后选择**撤销这轮整理**；页面会先确认，列出每篇文档以及撤销会对它做什么。被拒绝的撤销会关闭确认，并用一句话指出之后被改动的文档，附带**打开它的历史**，你可以在那里恢复单个版本；撤销成功的一轮显示**已撤销**，附带撤销者和时间。

- 如果之后有改动碰过这轮的某篇文档，撤销会以 `KNOWLEDGE_UNDO_CONFLICT` 拒绝并指出那篇文档，不写入任何东西。可以改为编辑或恢复那篇文档，或者在保留后续编辑的前提下手动撤销这轮：拒绝信息附带一段给智能体的提示词（在这轮整理的页面上提供，`coffer knowledge undo` 也会打印），写明这轮整理、它碰过的每篇文档、之后被编辑的文档，以及用来查看这轮做了什么的 `git -C ~/.coffer/vault show <version> -- knowledge`。智能体只编辑文件，Coffer 把它写的内容记为一次磁盘上的编辑。
- 如果这一轮没有真正合并任何东西（没有模型、条目太大，或整理放弃了它），它创建的文档就是原样的条目，所以撤销也会把条目放回收件箱，你提交的内容不会丢。
- 只有整理轮次能这样撤销（否则返回 `KNOWLEDGE_NOT_A_PASS`）。其他改动请恢复文档的早期版本。

## 删除文档和知识集 {#delete-documents-and-collections}

只有人能删除。面向智能体的工具都不能删除知识，而你可以删除任何文档，不管是谁写的。

::: code-group

```sh [CLI]
rm "$(coffer path knowledge payments)"/gateway/rate-limits.md
```

```text [Web UI]
Knowledge → choose the document → ⋯ → Delete document
```

:::

删除整个知识集及其中所有文件：

::: code-group

```sh [CLI]
coffer knowledge rm payments
```

```text [Web UI]
Knowledge → choose the collection → ⋯ → Delete collection
```

:::

::: tip 删除可以恢复
在 Web 界面里，删除会立刻执行：没有确认框，也不用输入名称，只弹出一条提示 *已删除 `<name>`*，带**撤销**。被删除的文档或知识集仍在[历史](#history-and-undo)里，所以即使提示消失了，**撤销**也能把它放回来。**最近改动**会列出这次删除并带有**恢复**，它会完整放回被删掉的东西：文档回到它的知识集，知识集连同它的文档、README 和收件箱里等待的条目一起回来，作为一次由你写入的新改动。在 CLI 下，用 `coffer knowledge changes` 找到这次删除，再运行 `coffer knowledge restore --deleted <version>`。如果同一路径上已经又有了文档，或者同名知识集已经重新存在，恢复会被拒绝，不写入任何东西。
:::

## 不要放进知识的东西 {#what-not-to-put-in-knowledge}

- **密钥。** 不放 key、令牌或密码。请用[密钥存储](/zh/guides/secret-store)。
- **代码里已经写明的东西。** 智能体能在仓库里读到的，就不该放这里。
- **草稿笔记。** 放进来的东西，一个月后应该依然成立。

## 故障排查 {#troubleshooting}

**待处理的条目一直没被整理。** 检查整理是否打开（`coffer config get engine.upkeep.curate.enabled`），这台机器是否是所有者或者没有设置所有者（`coffer config get engine.curate_owner`），以及 Coffer 自用模型是否已配置。运行 `coffer knowledge curate <collection>` 查看每轮的状态。

**整理把一篇文档改坏了。** 用 `coffer knowledge changes --collection <collection>` 找到那轮整理，用 `coffer knowledge changes <version>` 查看，再用 `coffer knowledge undo <version>` 撤销；或者用 `coffer knowledge restore` 只恢复那一篇文档。

**智能体不用这些知识。** 检查 `coffer-guide` 技能是否已启用并对该智能体生效（`coffer skill scope coffer-guide`），以及知识集的 `README.md` 开头是否有一句话写明它的主题。

**智能体的工具里没有 `coffer__write`。** 这个智能体没有连接到 Coffer（`coffer agent connect <agent>`）。

## 相关 {#related}

- [技能](/zh/guides/skills)：承载目录的 `coffer-guide` 技能
- [记忆](/zh/guides/memory)
- [知识架构](/zh/architecture/knowledge)
- [MCP 工具参考](/zh/reference/mcp-tools)
- [知识规格](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/knowledge/spec.md)
- [Knowledge Is Plain Files](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/knowledge-is-plain-files.md) 和 [Aggregate the Agents' Memory; Never Write It](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/aggregate-agent-memory-never-write-it.md)
