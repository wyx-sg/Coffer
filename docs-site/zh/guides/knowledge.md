---
title: 知识
description: 把你和智能体对工作环境的了解，存成一个由保留下来的来源编译而成的 Markdown 页面 wiki，每个智能体都用自己的文件工具读取，并请你的智能体来整理它。
---

# 知识 {#knowledge}

知识是一个存放工作环境相关 Markdown 的目录：服务、仓库、约定、决策、坑，这台机器上的每个智能体都会读。每个知识集都是一个小 wiki：你上传的素材作为**来源**保留下来，你的智能体再把它们编译成互相链接的**页面**。本页讲如何创建知识集、添加来源和页面、你和你的智能体如何修改它们、你的智能体如何在你按**整理**时整合来源、修好 Coffer 发现的问题并整理页面、一次整理如何记成一次可以撤销的改动、Coffer 如何检查知识集并让它保持最新、如何回看文件的历史并找回某个版本、如何在 Obsidian 中打开知识集，以及智能体如何找到这些内容。

## 知识用来做什么 {#what-knowledge-is-for}

知识存放的是你所处环境里的事实：哪个团队负责某个服务，某个内部 API 怎么鉴权，某个迁移为什么按这个顺序。它之所以在那里，是因为你或者和你一起工作的智能体把它放了进去。

- **所有智能体共用一份。** Claude Code 和 Codex 读的是同一批文件，一个智能体上午记下的东西，另一个下午就能读到。
- **普通文件。** 每个页面、每个来源都是一个 Markdown 文件，你可以打开、编辑、grep、备份。Coffer 不建索引、不做 embedding，也不在数据库里另存一份内容。
- **来源保留，页面编译。** 你上传的东西作为 Markdown 来源保留，页面会写明它依据哪些来源，所以任何一句话都能追溯到它出自的来源。知识在页面里生长：每个页面讲一个主题，写明它依据哪些来源，并链接到相关的页面。
- **共同编写。** 你在自己的编辑器里编辑页面，知识页面只以只读方式显示它们并把它们交给编辑器打开；智能体用自己的文件工具写页面，遵循 `coffer-guide` 技能里的规则：一条事实放进已经拥有这个主题的页面。你按**整理**时，你的智能体会先把仍在等待的来源并进页面，修好 Coffer 发现的问题，再合并、拆分、修正页面，整次整理记成一次你可以撤销的改动。Coffer 自己不在你的知识上运行任何模型。

知识不是[记忆](/zh/guides/memory)。记忆是智能体在工作中学到的东西，从它们各自的记忆库里读出来；知识是有人刻意写下来的东西。

## 知识集的结构 {#how-a-collection-is-laid-out}

**知识集**是知识根目录下的一个顶层文件夹：

```text
~/.coffer/vault/knowledge/
└── payments/                        ← one collection
    ├── README.md                    ← the schema: what belongs here, page types, rules
    ├── sources/
    │   ├── gateway-design.md        ← a source: the upload converted to Markdown
    │   └── oncall-notes.md          ← a source from a Markdown upload
    ├── assets/
    │   └── gateway-design-1a2b3c4d/ ← the pictures taken out of one upload
    │       └── image-1.png
    ├── pages/
    │   ├── session-ownership.md     ← a page
    │   └── gateway/
    │       └── rate-limits.md       ← nesting is allowed and means nothing
    └── .inbox/                      ← hidden: a drop zone, kept as sources at the next sweep
```

- 知识集根目录的 **`README.md`** 是这个知识集的**纲要**。它在第一个 `##` 小节之前的第一段，就是 Coffer 所有显示知识集描述的地方用的描述，也是 `coffer-guide` 技能告诉智能体这个知识集讲什么的依据。它的**页面类型**和**规则**两节，以及它关于本知识集约定的其他内容，优先于指南的默认规则。frontmatter 里的 `verify_after_days` 决定一次核对管多久（见[需要重新核对的页面](#pages-due-a-recheck)）。它从不作为页面或来源列出，也不计数。
<<<<<<< HEAD
- **`sources/`** 保留到达的素材：每次上传和每个放进收件箱的文件，转换成 Markdown。你上传的文件本身不放进知识集：Coffer 把它留在你上传它的那台 Mac 上（见[图片和原文件](#pictures-and-the-original-file)）。智能体读来源，从不编辑来源。
- **`assets/`** 放 Coffer 从上传的文档里取出的图片，每次上传一个文件夹。来源会链接它自己的图片，所以你读来源时能看到它们，智能体也能打开它们。它们和 Markdown 一样随知识集同步，也有历史。
=======
- **`sources/`** 保留到达的素材：每次上传和每个放进收件箱的文件，转换成 Markdown。只保留 Markdown，不保留你上传的文件，所以知识集始终是一棵每个智能体都能读的 Markdown 树。智能体读来源，从不编辑来源。
>>>>>>> origin/claude/project-thread-6qp5yc
- **`pages/`** 放 wiki 本身：你和你的智能体编写并保持更新的页面。智能体首先读的就是这里。
- `pages/` 和 `sources/` 里的**文件夹**是可选的，不代表任何含义。你或你的智能体都可以创建、移动、删除它们。只有 `pages/`、`sources/` 和 `assets/` 这几个文件夹本身有含义。
- 知识集里的**其他文件**会在树里列出，但既不进目录，也不参与检查。留在 `pages/`、`sources/` 和 `assets/` 之外的 Markdown 文件会被扫描移进 `pages/`（见[自己在运行的是什么](#what-runs-on-its-own)）。
- **隐藏条目**（以 `.` 开头的名字）不计入任何计数，也不进目录和检查，知识页面不会列出其中任何一个。Coffer 会读的是 `.inbox/`：留在那里的 Markdown 文件会在下一次扫描时作为来源保留下来（见[放进收件箱的文件](#a-file-in-the-inbox)）。

文件的路径就是它所在的位置；它的 **slug**（去掉 `.md` 的文件名）是链接用的名字。文件名是标题的 slug，重名时加 `-2` 这样的后缀。

知识根目录位于保险库仓库里，即 `~/.coffer/vault/knowledge`，`coffer-guide` 技能会把它告诉每个智能体。它不能挪到别处：保险库外的目录树，它的历史就看不到了。

### Frontmatter {#frontmatter}

每个页面都带 YAML frontmatter：

```markdown
---
title: Session ownership
type: concept
description: Which service owns a login session, and how long it lives.
sources: [gateway-design, oncall-notes]
aliases: [sessions]
verified: 2026-10-12
actor: agent
created_at: 2026-09-20T08:14:03.512840+00:00
updated_at: 2026-09-22T10:02:41.090311+00:00
---

The `account-session` service owns ... see [[rate-limits|the gateway's limits]].
```

| 键 | 含义 |
| --- | --- |
| `title` | 页面标题。 |
| `type` | 页面的种类：`concept`、`entity`、`how-to`、`decision` 或 `overview`，除非知识集的 README 定义了自己的类型。智能体看到的目录按它分组。 |
| `description` | 一句话说明页面回答什么问题。智能体在目录里看到的就是它。 |
| `sources` | 页面依据的来源的 slug。没有任何页面在这里列出的来源仍在[等待](#sources-wait-until-a-page-cites-them)。 |
| `aliases` | 链接可以用来指向这个页面的其他名字，比如改名后的旧 slug。 |
| `verified` | 最近一次对照来源或代码核对这个页面的日期（`YYYY-MM-DD`），阅读窗格里页面的说明行会显示它。没有这个日期，或者日期早于知识集的 `verify_after_days`，页面就[需要重新核对](#pages-due-a-recheck)。页面的事实从哪里来，写在这里和 `sources` 里，不要在正文里写一段列出读过什么。 |
| `actor` | `user` 或 `agent`，表示这个页面是谁写的。 |
| `created_at`、`updated_at` | 时间戳。 |

Coffer 自己不写页面：谁写页面，谁就给它这些键，`coffer-guide` 技能就是这样教智能体的。缺少 `title`、`type` 或 `description`、没有列出任何 `sources` 或者没有 `verified` 的页面照样能用；[检查](#check-a-collection)知识集时它会作为一条发现出现。

<<<<<<< HEAD
来源带着 Coffer 保留它时写入的键：`title`、`description`、`actor`、`created_at`、`updated_at`；从上传的文件转换来的来源还带有 `original`（文件名）和 `original_sha256`（它的指纹）。这两个键请保持原样。智能体或你还可以再加三个键，它们只描述这个来源，不改动它的内容：
=======
来源带着 Coffer 保留它时写入的键：`title`、`description`、`actor`、`created_at`、`updated_at`。智能体或你还可以再加三个键，它们只描述这个来源，不改动它的内容：
>>>>>>> origin/claude/project-thread-6qp5yc

| 键 | 含义 |
| --- | --- |
| `summary` | 用一两句话说明这个来源讲了什么，由智能体在整合或整理时写上。目录和知识集的**内容**都会显示它。 |
| `superseded_by` | 替换这个来源的新来源的 slug，比如一份设计文档的下一版（见[来源被替换时](#when-a-source-is-replaced)）。 |
| `ingest: skipped` | 用于没有任何值得写成页面的内容的来源，让它不再等待。 |

你给文件加的其他键，Coffer 每次重写文件时都会连同值一起保留。

### 用 slug 链接页面 {#link-pages-by-slug}

页面用 slug 链接另一个页面，从不用路径：`[[session-ownership]]`，或者用 `[[session-ownership|the session service]]` 来指定显示的文字。链接也可以写某个页面的 `aliases` 之一，或者某个来源的 slug。整理知识集时路径会变；slug 只在页面改名时才变，而 `coffer-guide` 技能会告诉智能体：给页面改名时，要更新指向它的链接，或者把旧 slug 留在 `aliases` 里。

每次读取页面时，Coffer 都会解析其中的每个链接，不区分大小写。什么都指不到的链接是**失效**的，指到不止一个文件的链接是**有歧义**的；两者都会由[检查](#check-a-collection)报告，知识页面也会在页面里标出失效链接。

### 来源在被页面引用之前一直等待 {#sources-wait-until-a-page-cites-them}

只要没有页面在 `sources` 里列出某个来源，而它既没有标记 `ingest: skipped`，也没有 `superseded_by`，这个来源就处于**等待**状态。除此之外，没有任何东西记录哪些来源已经整合：一旦有页面引用了某个来源，它就不再等待。知识页面会给等待中的来源标上**待整理**，知识集页面会统计它们的数量，`coffer-guide` 的目录会列出它们，**整理**会请你的智能体先整合它们。

## 创建知识集 {#create-a-collection}

知识集只能有意创建，而且只能由人创建。读、写、智能体的工作目录，或者智能体放进其他文件夹的 Markdown 文件，都不会创建知识集。

<Shot name="knowledge-page" alt="“知识库”页面，含一个集合及其文档。" />

```text
知识 → 添加 → 新建知识集… → 名称、这里放什么 → 创建知识集
```

树顶部也有**新建知识集**按钮。**添加**菜单会说明每一项保存什么：新建的知识集存在 Coffer 里，同步到你的其他 Mac，保留历史，由你的智能体整理。这会创建 `~/.coffer/vault/knowledge/payments/` 和它的 `README.md`；`pages/` 和 `sources/` 在第一次往里写东西时出现。README 一开始就把默认规则写了出来，你能看到智能体遵循的是什么，也可以修改：

```markdown
---
verify_after_days: 90
---

# payments

How payments are taken, settled and refunded.

## Page types

- `overview`: where to start. What this collection covers and which pages to read first.
- `concept`: what something is and why it works the way it does.
- `entity`: one service, system or team. What it owns and how to reach it.
- `how-to`: the steps for one task.
- `decision`: a choice that was made, the options and the reason.

## Rules

- One subject per page. Link related pages with `[[slug]]`.
- Every page lists the sources it draws on in `sources`, and the day it was last
  checked against them or the code in `verified`.
- `verify_after_days` at the top of this file is how many days a check holds
  before Coffer asks for another. `0` turns it off.
```

可以在这里改页面类型，或者加上你自己的规则；智能体会优先遵循这个文件，而不是它们的默认规则。知识集没有标题：所有页面和列表都按文件夹名显示它。它的描述就是 README 在第一个 `##` 小节之前的开头一段：可以在知识集页面直接修改（点一下文字，离开输入框时保存），也可以直接改文件。不管哪种方式，都只改这一段，下面的内容（包括页面类型和规则）保持不变。

要重命名知识集，在它的页面上选 **⋯ → 重命名…**，输入新名字。它的文件夹会随之改名（`~/.coffer/vault/knowledge/<新名字>/`），页面仍停在这个知识集上，智能体从下一次目录更新起按新名字找到它。如果新名字已被别的知识集占用，或不是合法的文件夹名，会在输入框下方提示，什么都不会改。

**知识**页面的树里列出所有知识集。

## 添加知识 {#add-knowledge}

素材以来源的形式进来，知识以页面的形式生长。有五种方式。

### 由智能体提交：写进页面 {#from-an-agent-write-into-the-pages}

智能体用自己的文件工具归档知识。连接了 Coffer 的智能体会读到 `coffer-guide` 技能（见[连接客户端](/zh/guides/connect-a-client)），里面写明了知识根目录和各个知识集，并教了写页面的七条规则：

1. 找到这条事实的归属：把它并入 `pages/` 下已经拥有这个主题的页面，只有没有页面拥有它时才新建页面。
2. 一个字都不丢：页面里原有的每条事实都要在这次编辑后保留。
3. 按主题组织，不按谁写的、什么时候写的。
4. 两种说法不一致时，较新的胜出，除非较旧的被来源、日期、命令输出或代码证明是对的。被取代的说法仍然看得到。
5. 用 `[[slug]]` 链接其他页面，从不用路径；给页面改名时，更新指向它的链接，或把旧 slug 留在 `aliases` 里。
6. 从不编辑来源，只能给它加上 `ingest: skipped`、`superseded_by` 或 `summary`。
7. 给每个页面写 `title`、`type`、一行说明它回答什么问题的 `description`、它依据的 `sources`、可能有的 `aliases`、最近一次对照来源或代码核实页面的日期 `verified`，以及 `actor: agent`。页面的事实从哪里来写在 `sources` 和 `verified` 里，不要在正文里写一段列出读过什么。

指南还会让智能体**把查出来的答案写回去**。它为了回答你的问题去读了来源、代码或某个系统，而页面里还没有这个答案时，它会在结束前把答案写进拥有这个主题的页面：读的如果是来源，就把它加进 `sources`，把 `verified` 设为今天，并用一句话告诉你它加了什么。猜测、观点，或者只在这次对话里成立的东西，它不会写回去。每一次这样的写入都在知识集的历史里，你可以撤销。

你也可以直接要求：「把我们刚发现的 session TTL 记到 payments 知识集里。」知识集必须已经存在；只有你才创建知识集。智能体写下的东西马上就能读到，下一次扫描会把它提交进[历史](#history-and-restore)。智能体写错了位置的页面（比如写在知识集根目录），一分钟内会被移进 `pages/`。

### 上传来源 {#upload-a-source}

上传会把文件转换成 Markdown，连同其中的图片立刻作为来源保留在知识集里。你上传的文件本身只留在这台 Mac 上（见[图片和原文件](#pictures-and-the-original-file)）。

```text
知识 → 添加 → 上传文档… → 选择或拖入文件，选知识集 → 上传
```

**添加**菜单会说明上传保存什么：每个文件转换成 Markdown，作为来源保存在你选的知识集里，并随它同步。上传对话框还会说明图片会一起保留，文件本身留在这台 Mac 上。

| 接受 | 格式 |
| --- | --- |
| 转换 | `pdf`、`docx`、`pptx`、`xlsx`、`xls`、`html`、`htm`、`epub` |
| 表格 | `csv`、`tsv` |
| 按文本读取 | `md`、`markdown`、`mdx`、`txt`、`text`、`rst`、`json`、`yaml`、`yml`、`toml`、`ini`、`cfg`、`log`、`sql`，以及常见源码文件（`py`、`js`、`ts`、`go`、`rs`、`java`、`sh` ……） |

比如上传一个 PDF，会得到 `sources/gateway-design.md`（提取出的 Markdown 加上 frontmatter），以及 `assets/gateway-design-<编码>/` 下它的图片。按文本读取的文件（Markdown、纯文本、源码）也以同样的方式成为来源。名字和已有来源重复时，会加上后缀（`-2`）。

可以一次选择或拖入多个文件。每个文件单独列出它的状态（等待、正在转换、完成，或失败及原因），文件一个接一个地发送，一个失败不会挡住其余的。ZIP 压缩包和超过 20 MB 的文件在发送前就会标为拒绝并写明原因。失败的文件留在对话框里，可以重试；最后会有一条提示说明保存了几个、失败了几个。上传只选知识集，不选文件夹。不支持的类型会被拒绝，并指出是哪种类型；转换后没有文本的（比如纯图片 PDF）也会被拒绝。被拒绝的文件不会留下任何东西。

来源的 `title` 取自文件（第一行的 `# ` 标题，没有就用文件名）。它的 `description` 取开头的正文，没有时用标题。之后这个来源就开始[等待](#sources-wait-until-a-page-cites-them)：把它的内容并进页面，是你按**整理**时（见[整理一个知识集](#tidy-a-collection)）或你随时请求时你的智能体的事。

### 图片和原文件 {#pictures-and-the-original-file}

**图片。** PDF、幻灯片、Word 文档或网页里的示意图、图表和截图会和来源一起保留。它们放在知识集的 `assets/` 文件夹里，在以这次上传命名的文件夹中，来源在它们原来出现的位置链接每一张；PDF 的图片列在正文之后的 **Images** 下，按它们所在的页分组。在知识页面上读来源时它们直接显示在正文里，从树里打开一张图片会显示这张图片。智能体像打开其他文件一样打开它们。并不是每张图片都会保留：

- 小装饰（项目符号、分隔线、图标，任何一边不到 48 像素的图）会被丢掉；
- 在文档里反复出现的图片，比如每张幻灯片上的标志，只保留一份；
- 超过 5 MB 的图片会被丢掉，一次上传最多保留 40 张；
- 浏览器不能显示的格式会存成 PNG。

图片随知识集同步到你的其他 Mac，和知识集里的任何文件一样有历史。只有图片、没有文字的扫描 PDF 仍然会被拒绝。

**原文件。** 你上传的文件保存在你上传它的那台 Mac 上，在保险库之外，从不同步：幻灯片、PDF 这样的原文件很大，而智能体读的是 Markdown 和图片。来源会记下它，所以在那台 Mac 上打开来源时，标题下面一行会显示**原文件**和文件名；点文件名就会用默认应用打开它，看到原来的版式。在你的其他 Mac 上，这一行写着**原文件 `<name>` 在上传的那台 Mac 上**。Markdown 或文本上传本身就是来源，所以没有要保留的原文件。

### 放进收件箱的文件 {#a-file-in-the-inbox}

Markdown 文件也可能出现在知识集隐藏的 `.inbox/` 文件夹里：来自 Coffer 之外的智能体、另一台机器，或旧版指南。

```text
~/.coffer/vault/knowledge/payments/.inbox/session-ttl.md
```

文件名无所谓，frontmatter 可有可无。下一次扫描会把这个文件作为来源保留在 `sources/` 下，并补全它缺的部分：

| Frontmatter | 补全来源 |
| --- | --- |
| `title` | 第一个 `# ` 标题，没有就用文件名。 |
| `description` | 第一段正文，没有就用标题。 |
| `actor` | `agent`，除非文件里另有写明。 |
| `created_at`、`updated_at` | 扫描发现该文件的时间。 |

写入者自己设置的内容都会保留，包括其他键，每个文件都会记入审计日志。和上传一样，新来源会一直等待，直到有页面引用它。只有知识集自己的 `.inbox/` 才算数。写在不是知识集的顶层文件夹里的 Markdown 文件不会被处理，也不会进目录：只有人才能创建知识集。收件箱里不是 Markdown 的文件原样留着。

### 在聊天里：让智能体来存 {#from-a-chat-ask-your-agent}

如果你配对了一个[消息渠道](/zh/guides/channels)，并没有专门的知识命令。把文档或这段对话发给聊天里的智能体（私聊或群组都行），让它存进知识，比如「把这个存进 payments」。智能体用自己的文件工具把它写进知识集的页面，规则和写其他页面一样。

### 自己编辑文件 {#edit-a-file-yourself}

用任何编辑器在知识集的 `pages/` 文件夹里写、改、删页面，本身就是修改知识的完整方式，不需要导入步骤。改动在下一次读取时就生效，下一次扫描会把它作为在磁盘上编辑提交进历史。给你写的页面加上和智能体一样的 frontmatter（见 [Frontmatter](#frontmatter)）；[检查](#check-a-collection)会告诉你缺了什么。

在知识页面上，选中一个页面或来源，用**在编辑器中打开**，或 **⋯** 菜单里的**在访达中显示**跳到文件。知识页面本身从不编辑文件：它只读地显示文件，下一次读取就会显示你的编辑器或智能体保存的内容。没有未保存状态，没有保存过期的拒绝，也没有离开前不保存的询问，因为页面上没有任何东西持有你的文字。在编辑器中打开用的是**设置 › 通用**里选择的编辑器。

要添加页面，把 Markdown 文件存到知识集的 `pages/` 文件夹下（知识集上的**在访达中显示**）。要添加素材，用**添加 → 上传文档…**，或把 Markdown 文件放进知识集的 `.inbox/`。来源保持原样：来源记录的是到达的东西。

智能体用自己的文件工具做同样的事，遵循 `coffer-guide` 技能给它们的写作规则（见[由智能体提交](#from-an-agent-write-into-the-pages)）。

## 整理一个知识集 {#tidy-a-collection}

时间一长，知识集会攒下要做的事：还没有任何页面用过的来源，两个回答同一个问题的页面，一个回答好几个问题的页面，一条被较新页面推翻的说法，一个已经指不到任何页面的链接。Coffer 自己不去修。它把这件事交给你的智能体，由它用自己的文件工具读文件并编辑页面。

### 按下整理 {#press-tidy}

```text
知识 → 选择知识集 → 整理
知识 → 整理全部   （每个知识集，一个接一个）
```

**整理**会在你的首选终端里启动默认的交接智能体，把一份提示词作为它的第一条消息：写明知识集、它的文件夹、页面数和待整理来源数，以及 Coffer 在知识集**待办**里列出的每条发现（见 [Coffer 自己能发现的问题](#what-coffer-finds-on-its-own)）。你可以在终端里看着智能体工作。知识页面页头的**整理全部**会以同样的方式发送一份提示词，写明每个知识集及其数量（包括发现了几条问题），请智能体一个一个地处理，并用 `coffer knowledge check <collection>` 读出每个知识集的发现。没有可用的托管智能体时，按钮改为提供**复制提示词**：把它粘贴到你用的任何智能体里。

提示词会让智能体去看 `coffer-guide` 技能的**整合来源**和**整理一个知识集**两节。照着做，智能体一次处理一个知识集：

1. 在改动任何东西之前，用 `coffer knowledge tidy-start <collection>` **开始整理**（见[一次整理就是一次改动](#a-tidy-is-one-change)）。
2. **整合等待中的来源**，从最早的开始：完整读每个来源，把它的内容并进拥有相应主题的页面，为没有页面拥有的主题新建页面，把来源的 slug 加进它改过的每个页面的 `sources`，并给来源写上 `summary`。如果这个来源替换了一个旧来源，它会给旧来源标上 `superseded_by`，并重新核对引用旧来源的页面。没有任何值得保留内容的来源（重复的、空的导出）则标记为 `ingest: skipped`。
3. **修好 Coffer 发现的问题**：失效和有歧义的链接、没有被链接的页面和不完整的页面、没有来源的页面、缺失的来源、引用了过期来源的页面。它会**重新核对每个需要重新核对的页面**，对照来源或代码修正变了的地方，并把 `verified` 设为今天；核对不了的页面保留原来的日期，写进汇报。没有 `summary` 的来源，它都会补上。
4. 读知识集的 `README.md` 和每个页面的标题与描述，再完整读页面。
5. 把回答同一个问题的页面**合并**成一个，保留每条事实和每个来源，把被合并掉的 slug 留在保留下来的页面的 `aliases` 里，并删掉被合并掉的页面。
6. 把回答好几个不相关问题的页面**拆分**，一个主题一个页面，并互相链接。
7. 按「新的说法胜出，除非旧的被证明是对的」这条规则**修正**错误、过时或矛盾之处，重写没有说明页面回答什么问题的描述，并给在多个页面里提到、却没有页面的主题建一个页面。
8. **拿不准的不动手**：两个页面说法冲突却看不出哪个对、要删掉大段内容、要改 README 里的页面类型，这些写进汇报，留给你决定。
9. 用 `coffer knowledge tidy-finish <collection> --set summary="<汇报>"` **结束整理**。汇报写明它整合或跳过了哪些来源，合并、拆分、修正、重新核对和删除了什么，以及留给你决定的事。最后一部分是**缺口**：页面回答不了的问题、多个页面都提到却没有页面负责的主题，以及值得去找的来源（一份规格、一份运行手册、一个可以问的人）。

不需要改的地方，它一概不动。你也可以用自己的话请任何装有 `coffer-guide` 技能的智能体去做这件事：「把 payments 的知识整理一下。」

### 一次整理就是一次改动 {#a-tidy-is-one-change}

从 `tidy-start` 到 `tidy-finish`，Coffer 把智能体在这个知识集里的编辑放在一起，而不是一个文件一个文件地记录：

- 知识集页面会提示有智能体正在整理它，整理结束后它的编辑会作为一次改动出现。磁盘上的文件随着智能体的工作而变化，每次读取都能看到。
- 这期间没有任何东西提交这些编辑：扫描不会，保险库自己的扫描器也不会。如果一轮[保险库同步](/zh/guides/vault-sync)要改动其中某个文件，它会等待，就像对待任何还没进历史的编辑一样。
- 智能体结束时，所有编辑记成**一次改动**，写入者是智能体，带着它的汇报。知识集的**改动记录**把它显示为一条：智能体、时间、汇报，以及按标题列出的文件。
- 什么都没改的整理不记录任何东西。
- 智能体一直不结束，也不会永远占着这个知识集：知识集 30 分钟没有变化后，Coffer 会结束这次整理，把它改过的东西记成一次改动，显示为*未汇报即结束*。
- `tidy-start` 之前知识集里已有的改动，会先作为在磁盘上编辑记录下来，所以这次整理只包含智能体做的事。

Coffer 只在整理进行时记着它：整理期间 Coffer 重启的话，已做的编辑会记成普通的在磁盘上编辑，丢掉的只是分组。智能体没有运行 `tidy-start` 时也是这样。

### 撤销一次整理 {#undo-a-tidy}

```text
知识 → 选择知识集 → 改动记录 → 这次整理 → 撤销这次整理…
```

**撤销这次整理…** 会把这次整理动过的每个文件放回整理之前的样子：改过的页面回到原来的文字，删掉的页面回来，新建的页面被移除。Coffer 会先询问，写明是哪次整理、会放回多少个文件。撤销是一次由你写入的新改动，所以那次整理仍留在历史里，排在撤销之前；撤销也会记入[活动](/zh/guides/activity)。

如果其中某个文件在整理之后又被改过（被你、别的智能体或同步），对话框会列出它，在你选择**仍然撤销**之前什么都不撤销；选择后，那些之后的修改也会丢掉。它们仍在历史里，所以文件的**历史**还能把它们找回来。

在命令行上，`coffer knowledge undo <version>` 做同样的事；有文件在之后被改过时，会以 `KNOWLEDGE_UNDO_CONFLICT` 拒绝并写明这些文件；加上 `--set force=true` 仍然撤销。version 是这次改动的版本，从 `coffer knowledge changes` 里找。

只想放回某一个页面，就打开它，按**历史**，选中整理之前的版本，按**恢复此版本…**（见[历史与恢复](#history-and-restore)）。

### 只想先听听意见 {#ask-for-a-review-only}

想在智能体动手之前先听它打算改什么，就在整理打开的会话里直接说：「先别改，说说你打算怎么做。」`coffer-guide` 技能会告诉只被要求检查或审阅的智能体：只报告，什么都不改。然后你再告诉它哪些可以动手。

### 没有什么会自己整理 {#nothing-tidies-on-its-own}

整理只在你按下它或请你的智能体去做时才运行。Coffer 不会自己启动智能体运行，所以不会有消耗你额度的动作，也不会开出你没发起的对话。

::: info 什么会离开你的机器
Coffer 不会把任何关于你知识的东西发给任何模型。你按下整理时，智能体读到的文件会发给该智能体自己的提供商，和与它的任何对话一样。
:::

## 检查一个知识集 {#check-a-collection}

能机械地发现的问题，Coffer 在每次读取知识集时自己找出来，一个都不修。修它们是[整理](#tidy-a-collection)的一部分，整理的提示词带着同一份清单。

### Coffer 自己能发现的问题 {#what-coffer-finds-on-its-own}

知识集页面的**待办**一节列出这些发现，按种类分组，最严重的在前。每条按标题写明页面（悬停可看到路径），点一下就打开它。次要的种类（没有来源的页面、没有被链接的页面）折叠成一行，可以展开。没有可报告的内容时，这一节只显示一行说明。

| 发现 | 含义 |
| --- | --- |
| **失效链接** | 一个指不到任何页面、别名或来源的 `[[链接]]`。 |
| **有歧义的链接** | 一个指到不止一个文件的 `[[链接]]`。 |
| **重复的名称** | 两个页面的 slug 相同，或者一个别名指到两个页面。 |
| **缺失的来源** | 页面的 `sources` 里写了一个不存在的来源，或者来源的 `superseded_by` 指向一个不存在的来源。 |
| **引用了过期来源的页面** | 页面引用了一个已被替换的来源，却没有引用任何替换它的来源（见[来源被替换时](#when-a-source-is-replaced)）。这一行写明它引用的来源和最新的替换者。 |
| **待整理的来源** | 没有任何页面引用、也没有标记 `ingest: skipped` 或 `superseded_by` 的来源。 |
| **不完整的页面** | 缺少 `title`、`type` 或 `description` 的页面。 |
| **需要重新核对的页面** | `verified` 日期缺失或早于知识集期限的页面（见[需要重新核对的页面](#pages-due-a-recheck)）。这一行写明上次核对的日期，或者*从未核对*。 |
| **没有来源的页面** | `sources` 为空的页面。 |
| **没有被链接的页面** | 知识集里有两个或更多页面时，没有任何其他页面链接到的页面。`overview` 类型的页面除外：它们是入口。 |

这些发现在每次读取时从文件算出来，不存在任何地方，所以文件一变它们就是最新的。它们是提示，不是错误：你写的没有来源的页面照样能用。在命令行上，`coffer knowledge check <collection>` 会打印同样的列表（见 [`coffer knowledge`](/zh/reference/cli/knowledge#knowledge-check)）。

### 来源被替换时 {#when-a-source-is-replaced}

来源会过期：新的设计文档或运行手册替换了你的页面当初依据的那一份。给旧来源标上新来源的 slug：

```markdown
---
title: Gateway design (2025)
superseded_by: gateway-design-2026
---
```

智能体在整合一个替换了旧来源的新来源时，会自己加上这一行。从那以后，每个引用了旧来源、却没有引用任何新来源的页面，都会列在**引用了过期来源的页面**下，下一次整理会对照新来源重新核对它。替换可以连成一串：`v1` 被 `v2` 替换、`v2` 又被 `v3` 替换时，同时引用 `v1` 和 `v3` 的页面就是最新的。旧来源留在原处，不再等待，因为页面仍然可以引用它来说明过去的情况；打开它会看到**已被替换为**和指向替换者的链接，目录也会标出它，让智能体知道它已经不能作为依据。指向不存在来源的 `superseded_by` 会列在**缺失的来源**下。

### 需要重新核对的页面 {#pages-due-a-recheck}

来源没变，页面也可能和现实脱节：它描述的代码或系统变了。每个页面都带着 `verified`，即最近一次对照来源或代码核对它的日期；`verified` 缺失或早于知识集期限的页面，会列在**需要重新核对的页面**下。打开它会看到**需要重新核对**，没有日期时还会显示*从未核对*。它只是被标出来：仍然留在目录里，智能体照样会读。

期限是 90 天。可以在 README 的 frontmatter 里设成别的值，比如运行手册的知识集设 `verify_after_days: 30`；设为 `0` 就关闭这个知识集的检查。负数，或者不是整数天数的值，都按 90 天算。整理会重新核对列出的每个页面，并把 `verified` 设为今天。

更新之后第一次打开知识集时，所有没有 `verified` 的页面都会被列出来。按**整理**，智能体会逐个重新核对。

## 自己在运行的是什么 {#what-runs-on-its-own}

后台的**扫描**让知识集保持最新。它大约每分钟运行一次，不调用任何模型。每一轮它会：

- 把放进知识集 `.inbox/` 的文件作为来源保留下来（见[放进收件箱的文件](#a-file-in-the-inbox)），
- 把留在知识集里 `pages/`、`sources/` 和 `assets/` 之外的 Markdown 文件（README 除外，并且要等它一分钟没人动过）移到 `pages/` 下相同的相对路径，名字被占用时加后缀，不改动它的文字，
- 把自上次提交以来树里变过的东西（你编辑器里的保存和你的智能体对文件的编辑）作为在磁盘上编辑提交进历史，以及
- 重新渲染 `coffer-guide` 技能的目录，这样你或智能体手工添加的页面会被列出来。

它在每台机器上都运行，不参与[保险库同步](/zh/guides/vault-sync)的各轮，也从不等待其中任何一轮，并且不改写任何文件的文字。知识功能关闭期间它会被跳过（见[实验功能](/zh/guides/experimental-features)）。

### 页面和来源出现之前的知识集 {#collections-from-before-pages-and-sources}

在页面和来源出现之前建的知识集，文档放在它的根目录和它自己的文件夹里。更新之后的第一次扫描会把它们全部移进 `pages/`，保留原来的文件夹结构，作为一次由 **Coffer** 写入的改动，你可以在知识集的**改动记录**里看到，也可以从历史里撤回。它们的文字不变；它们缺的东西（`type`、`sources`）会出现在[检查](#check-a-collection)里，一次**整理**会把它们补上。

## 智能体如何找到知识 {#how-agents-find-knowledge}

Coffer **没有读取、列出或搜索知识的工具**。智能体用它已有的工具按路径读文件：`Read`、`Grep`、它的 shell。

告诉它去哪里找的是 Coffer 内置的 [`coffer-guide` 技能](/zh/guides/skills#the-built-in-coffer-guide-skill)，Coffer 会把它链接进每个智能体的技能文件夹：

- 它的**描述**出现在每个会话里，列出你各个知识集的主题，取自每个 `README.md`，并说明这个技能教如何写下、整理和检查知识。
- 它的**正文**在智能体打开技能时加载，给出知识根目录的路径和每个知识集的目录：它的 README、按 `type` 分组的页面（每个页面的路径、标题和描述），以及它的来源，每个来源标着 *(waiting)* 或 *(superseded by …)*，后面跟着它的 `summary`。它还带有上面讲的结构、写页面的规则，以及整合来源和整理的步骤。

页面里没有智能体要找的东西时，指南会让它在知识集的 `sources/` 里 grep 确切的字符串。目录太大时会被缩短：先去掉描述和摘要，只列出等待中的来源，还是太长就只列出每个知识集的数量和要搜索的文件夹，技能里会说明这一点。

目录一变，Coffer 就重写这个技能，所以新页面会在一次扫描内出现在里面。

::: details 为什么没有搜索工具
智能体会稳定地使用它已有的文件工具，却很少记得去调一个专用的检索工具。给它们一份目录和一个路径，就把检索变成了它们本来就擅长的事；而且对几百个文件做一次字面 `grep`，能准确匹配标识符和名字，模糊搜索反而会把它们弄混。完整理由见[知识架构](/zh/architecture/knowledge)。
:::

给每个知识集写一个好的 `README.md`：模型判断你的知识是否相关时，匹配的就是它的第一段；它关于页面类型和规则的内容，就是智能体要遵循的。

## 浏览和阅读 {#browse-and-read}

在知识页面里，先在树中选知识集，再选页面或来源。它们同时也是普通文件：知识根目录是 `~/.coffer/vault/knowledge/`，每个知识集是其中的一个文件夹，所以你可以用自己的工具读和 grep。知识集的 **⋯** 菜单里有**复制路径**。

知识页面是一棵树加一个阅读窗格，两者都撑满页头下方的窗口。标题带着**实验性**标签；页头的操作是**整理全部**和**添加**，后者是页面唯一的主按钮。**添加**会打开一个菜单，每一项都带一行说明它在 Coffer 里保存什么：**上传文档…**（见[上传来源](#upload-a-source)）、**新建知识集…**（见[创建知识集](#create-a-collection)）和**接入外部文件夹…**（见[接入外部文件夹](#link-an-external-folder)）。树的顶部，**知识集**有一个**新建知识集**按钮；下面是按文件夹名显示的每个知识集。展开一个知识集，先显示**页面**和**来源**，然后是其中的其他内容；每个文件都按文件名显示，每个页面带着它的类型图标，每个来源带着来源图标，仍在等待整合的来源带着**待整理**标记。树会记住你展开和收起了什么：离开页面或刷新之后回来，还是同样的知识集和文件夹开着。

**知识集。** 选中一个知识集，它的窗格栏里有**整理**和 **⋯** 菜单。下面是它的文件夹名、这里放什么（点一下可编辑；离开输入框或按 **⌘Enter** 保存，**Esc** 取消，并有提示给出**撤销**），以及一行概要：多少个页面、多少个来源及其中几个待整理、文件夹路径和复制按钮、最后更新时间。概要下面一行浅色文字说明这个知识集由 Coffer 管理：同步到你的其他 Mac，保留历史，由你的智能体整理。有智能体正在整理它时，会有一条提示（见[一次整理就是一次改动](#a-tidy-is-one-change)）。然后是三节：

- **待办**列出 Coffer 在知识集文件里发现的问题，最严重的在前，每条按标题写明页面，点一下就打开，其中包括**引用了过期来源的页面**和**需要重新核对的页面**（见 [Coffer 自己能发现的问题](#what-coffer-finds-on-its-own)）。
- **内容**按类型显示知识集的页面：概览、概念、实体、操作指南、决策，然后是 README 定义的类型，最后是没有类型的页面；每种一张卡片，带着类型图标、页面数和前几个标题，再写明还有多少个；**来源**卡片列出来源：等待中的在前，然后是其余的，已被替换的排在最后并划掉；每个都写明状态（*待整理*、*被 N 页引用*、*已跳过*或*已被替换*），下面是它的摘要。点开每个标题就打开对应文件。
- **改动记录**列出这个知识集的每次改动，最新的在前：它做了什么、谁写的、什么时候，以及按标题列出它涉及的文件，点开每个文件都会打开它的历史。一次整理是一条，带着智能体的汇报和**撤销这次整理…**（见[撤销一次整理](#undo-a-tidy)）；彼此相隔不到 10 分钟的磁盘编辑合成一条，列出它们的文件。**显示更多**会加载更早的改动。

知识集的 **⋯** 菜单里有**在访达中显示**、这台 Mac 装了 Obsidian 时的**在 Obsidian 中打开**（见[在 Obsidian 中打开知识集](#open-a-collection-in-obsidian)）、**复制路径**、**重命名…**和**删除知识集…**；里面还什么都没有的知识集会这样说明，并提醒你可以上传一个来源，或把 Markdown 文件放进它的文件夹。

**页面或来源。** 选中一个文件会只读地显示它。它的窗格栏先写明文件在哪里，然后是**历史**（见[历史与恢复](#history-and-restore)）、Markdown 的**预览 / 源码**切换、作为按钮的**在编辑器中打开**（见[自己编辑文件](#edit-a-file-yourself)），以及 **⋯** 菜单（**在访达中显示**、装了 Obsidian 时的**在 Obsidian 中打开**，以及**删除**）。标题下面一行描述这个文件，读自它的 frontmatter：

- **页面**：它的类型、谁写的、什么时候创建的、页面带有 `verified` 时的**核对过**及日期，[需要重新核对](#pages-due-a-recheck)时的**需要重新核对**（没有日期时还会显示*从未核对*），以及它的来源，点开每个都会打开对应来源；页面写了但并不存在的来源会被划掉。正文里，每个 `[[链接]]` 都是指向它所指页面或来源的链接；失效的链接标成红色，悬停提示说没有叫这个名字的东西。行内代码比代码块更淡，长路径在 `/` 处换行。
<<<<<<< HEAD
- **来源**：有来源替换它时，显示**已被替换为**和指向替换者的链接；**被 N 个页面引用**，点开每个都会打开对应页面；还没有页面引用时显示**待整理**；上传来的来源还会显示**原文件**和文件名，在上传它的那台 Mac 上点它会打开这个文件（见[图片和原文件](#pictures-and-the-original-file)）。

页面或来源用相对路径链接的图片会在预览里直接显示。在树里选中一个图片文件（比如 `assets/` 下的），会显示这张图片。
=======
- **来源**：有来源替换它时，显示**已被替换为**和指向替换者的链接；**被 N 个页面引用**，点开每个都会打开对应页面；还没有页面引用时显示**待整理**。
>>>>>>> origin/claude/project-thread-6qp5yc

页面没有搜索框，也没有按知识集的开关：⌘K 按名字跳到知识集，每个知识集都到达每个智能体。知识页面上没有手工输入页面的表单：你在自己的编辑器里写，智能体则通过写文件来写。

## 在 Obsidian 中打开知识集 {#open-a-collection-in-obsidian}

知识集就是 [Obsidian](https://obsidian.md) 能直接读的普通 Markdown：把它的文件夹（或整个知识根目录）作为 Obsidian 库打开，就可以在 Obsidian 里浏览、搜索和编辑页面。`[[slug]]` 链接按文件名解析，和 Obsidian 的解析方式一样；frontmatter 里的 `aliases` 正是 Obsidian 本来就读的键。Coffer 会忽略 `.obsidian/` 这类隐藏文件夹（Obsidian 在里面存它的设置）：不提交、不进目录、不同步。

这台 Mac 装了 Obsidian 时，知识集的 **⋯** 菜单和文件的 **⋯** 菜单里会有**在 Obsidian 中打开**。第一次使用时：

1. 在 Obsidian 里选**打开文件夹作为仓库**（Open folder as vault），选中知识集的文件夹 `~/.coffer/vault/knowledge/<collection>/`。`~/.coffer` 是隐藏的：在对话框里按 **⌘⇧.** 显示它，或者在知识集上用**复制路径**，再按 **⌘⇧G** 粘贴。
2. 在 Obsidian 的**设置 › 文件与链接**里，把**新建笔记的存放位置**设成知识集的 `pages/` 文件夹。留在 `pages/` 和 `sources/` 之外的 Markdown 文件会在一分钟内被扫描移进 `pages/`，所以建在库根目录的笔记会被移走。

在 Obsidian 里保存的编辑和在任何编辑器里一样：马上生效，由下一次扫描记成在磁盘上编辑。`sources/` 下的文件请保持原样。

## 接入外部文件夹 {#link-an-external-folder}

如果你已经在用自己的工具记笔记，比如一个 Obsidian 库、一个 Logseq 图谱，或者仓库里的一个 Markdown 文件夹，可以把这个文件夹共享给你的智能体，而不用挪动它。Coffer 把它叫作接入的外部文件夹。

```text
知识 → 添加 → 接入外部文件夹… → 文件夹、名称 → 接入文件夹
```

**文件夹**是它的绝对路径，比如 `/Users/you/Obsidian/Work`。**名称**是 Coffer 和智能体称呼它的名字：在你自己输入之前，它跟着文件夹本身的名字走；不管怎样，磁盘上的文件夹都不会改名。在命令行里，同样的操作是 `coffer knowledge link --set folder=/Users/you/Obsidian/Work`（见 [`coffer knowledge link`](/zh/reference/cli/knowledge#knowledge-link)）。

### Coffer 会做什么 {#what-coffer-does-with-a-linked-folder}

- **把它共享给每个智能体。** 这个文件夹在每个智能体都会读的 `coffer-guide` 技能里有单独的一节：它的路径、它的规则文件，以及按标题列出的每篇 Markdown 笔记。智能体用自己的文件工具在原处读这些笔记。
- **在知识页面上显示它。** 树里用外部文件夹图标列出它，你可以打开、阅读其中任何一篇笔记。它的页面在名字旁标着**外部**，并列出四项信息：**位置**（它的路径，附**在访达中显示**）、**笔记**（它有多少篇 Markdown 笔记）、**规则文件**，以及**管理方式**：由它自己的工具维护，Coffer 只把它共享给智能体。
- **每次都重新读取。** 不做任何缓存，所以你在 Obsidian 里保存的笔记，就是页面和智能体下一次看到的内容。

### Coffer 不会做什么 {#what-coffer-does-not-do-with-a-linked-folder}

- **不复制任何东西。** 没有文件会进入 `~/.coffer`。这个文件夹始终是唯一的一份。
- **不往文件夹里写任何东西。** 不能往里上传，它的笔记没有**删除**，它的描述（它自己 `README.md` 的第一段）不在这里编辑，它也没有**整理**、**待办**、收件箱，不会把笔记移进 `pages/`。Coffer 的 `pages/` 和 `sources/` 结构对它不适用。
- **不记录历史。** 它的笔记没有**历史**，它的页面没有**改动记录**，也不能通过 Coffer 撤销任何东西。需要时请用这个文件夹自己的工具：Obsidian 的文件恢复，或者文件夹本身是仓库时用 git。
- **不同步它。** 文件夹里的文件和这个接入关系都不会经由[保险库同步](/zh/guides/vault-sync)到达你的其他 Mac。接入关系只记录在这台 Mac 上的 `~/.coffer/local/resources/knowledge/` 里，因为文件夹的路径只在这台 Mac 上成立。想在另一台 Mac 上用同样的笔记，就用文件夹自己的工具（Obsidian Sync、iCloud 云盘、git）让它保持一致，再在那台 Mac 上也接入一次。

### 智能体怎样往里写 {#how-agents-write-in-a-linked-folder}

文件夹的**规则文件**是它根目录下 `AGENTS.md`、`CLAUDE.md` 和 `README.md` 中第一个存在的那个。指南会告诉智能体，在往文件夹里写任何东西之前先遵守这个文件；没有规则文件时，只按现有笔记的写法来写。Coffer 给知识集定的规则（页面放在 `pages/`、来源分开保存、frontmatter 里的页面类型、收件箱、整理）在这里都不适用。所以，如果你希望智能体往你的库里添加笔记，就把你的约定写进库根目录的 `AGENTS.md`；如果只希望它们读，也在那里写明。

### 大文件夹 {#large-linked-folders}

Coffer 会跳过 `.obsidian/`、`.git/` 这类隐藏文件夹和 `node_modules`。一个文件夹最多读取 5000 篇 Markdown 笔记，超过 2 MB 的文件会列出，但不在页面上显示。只想共享大库的一部分时，接入其中的子文件夹，而不是整个库。

### 不能接入的文件夹 {#folders-that-cannot-be-linked}

文件夹必须存在，并且要用绝对路径给出。Coffer 自己的文件夹 `~/.coffer` 不能接入，包含它的文件夹也不行，比如你的主目录或磁盘根目录。这些会被拒绝并返回 [`KNOWLEDGE_FOLDER_REFUSED`](/zh/reference/error-codes)。已经接入过的文件夹，或者别的知识集已经在用的名字，会被拒绝并返回 `KNOWLEDGE_COLLECTION_EXISTS`。

### 重命名或断开接入 {#rename-or-disconnect-a-linked-folder}

接入文件夹的 **⋯** 菜单里有**在访达中显示**、装了 Obsidian 时的**在 Obsidian 中打开**、**复制路径**、**重命名…**和**断开接入…**。**重命名…**只改 Coffer 和智能体使用的名字。**断开接入…**会先询问；之后智能体不再看到这个文件夹，里面的每个文件都留在原处。

## 每个知识集都对所有智能体生效 {#every-collection-reaches-every-agent}

知识集没有开关，也没有按智能体设置的生效范围：每个知识集（包括接入的外部文件夹）对所有智能体都可用，只有删除才能让它从智能体的 `coffer-guide` 技能里消失（接入的文件夹用**断开接入…**，文件保持不动）。

::: warning 这不是访问控制
技能会把知识根目录交给智能体，智能体可以用自己的工具读取其下的任何东西。不要把这台机器上的智能体不该读的内容放进知识集。
:::

## 历史与恢复 {#history-and-restore}

知识集的每一次改动都会作为一个版本保留：你的上传和删除、放进收件箱并作为来源保留下来的文件、扫描把零散文档移进 `pages/`、保险库同步带进来的内容，一次整理（记成一次由智能体写入、带着汇报的改动），以及在 Coffer 之外用你自己的编辑器或智能体文件工具做的编辑。每次改动都注明**写入者**：`user`、`agent`、`daemon`（Coffer 把零散文档移进 `pages/`）、`sync` 或 `disk`（早期版本的 Coffer 写的版本是 `curation`），所以你总能知道谁改了什么。知识集页面在它的**改动记录**里列出这些改动。

历史就是保险库仓库自己的历史：知识集位于 `~/.coffer/vault` 的 `knowledge/` 下，所以 `git -C ~/.coffer/vault log -- knowledge/<collection>/<path>` 读到的是同样的版本，[保险库同步](/zh/guides/vault-sync)会把它们带到你的其他机器上。Coffer 的保险库需要 `git`；没有 git 时，应用会一直显示 [Coffer 需要 git](/zh/guides/troubleshooting#coffer-needs-git)，直到装好为止。如果守护进程运行期间 git 没了，所有写入照常工作，知识集的改动记录和删除的**撤销**所读的改动流会被拒绝。这个拒绝附带一段提示词，让你的智能体按适合你机器的方式安装 git，并用 `git --version` 确认。

### 找回较早的版本 {#bring-back-an-earlier-version}

在页面或来源的窗格栏里按**历史**。历史会占满整个知识区域，树和文件都让开，给版本列表和 diff 留出空间；页面地址会加上 `?history=1`，所以指向它的链接也会打开历史。里面是一张卡片，中间有一条可以拖动的分隔线；按它的 ✕ 或按 **Esc** 回到文件。

- **左边：版本列表，最新的在最上面，** 标题是**版本**并带着数量。每一行说明这个版本做了什么（*创建*、*编辑*或*删除*，或*恢复了 &lt;日期&gt; 的版本*）、谁写的、什么时候，以及它改动的行数（+N −M）。写入者显示为**你**（你通过 Coffer）、**在磁盘上编辑**（你自己的编辑器、shell，或智能体自己的文件工具）、按产品名显示的智能体（通过 Coffer 工具写入时）、**Coffer** 或**同步**。最新的一个标着**当前**，打开历史时默认选中它。
- **右边：选中的版本，** 显示它的短 id、写入者和时间，以及它改动的每个文件的差异。对于不是当前的版本，一个开关决定差异显示什么：**本版本的改动**（与它之前的版本比）或**与当前版本对比**（从该版本到文件现在的样子）。

要回到某个版本，选中它，按**恢复此版本…**。Coffer 会先询问：文件会恢复成那个版本，**作为一个新版本**保存，所以历史里的内容都不会丢。恢复由你写入，在历史里显示为*恢复了 &lt;日期&gt; 的版本*，并记入[活动](/zh/guides/activity)。如果文件在你打开历史之后又变了（有了更新的版本，或你在编辑器里保存过），恢复会被拒绝并返回 `VAULT_FILE_STALE`，对话框会这样告诉你；重新打开历史再试即可。打开历史时，你在磁盘上做的编辑也会先记成它自己的一个版本，所以最新的版本总是文件现在的样子。

你也可以用 git 读同样的版本：`git -C ~/.coffer/vault log -p -- knowledge/<collection>/<path>`。

提示消失之后，已删除的文件就没有窗格可以打开它的历史了，但它的版本仍在保险库的 git 历史里，所以可以用 git 找回（见[删除文件和知识集](#delete-files-and-collections)）。

## 删除文件和知识集 {#delete-files-and-collections}

通过 Coffer 删除只能由人来做。Coffer 不给智能体任何能删除知识的工具，而你可以删除任何页面或来源，不管是谁写的。这也只是一次普通的文件删除，所以在你自己的编辑器里删文件同样可以，历史里会把它记为一次磁盘上的编辑。

- **删除一个页面或来源：** 知识 → 选中文件 → **⋯** → **删除**。立刻执行。删除仍被页面引用的来源，会让这些页面在[检查](#check-a-collection)里出现缺失的来源。它的图片仍留在 `assets/` 下，它的原文件仍留在上传它的那台 Mac 上；不再需要的话请自己删掉。
- **删除整个知识集及其中所有文件：** 知识 → 选中知识集 → **⋯** → **删除知识集…**。Coffer 会先询问，写明知识集的名字和会一并删除多少个文件。

::: tip 删除可以撤销
删除会弹出一条提示 *已删除 `<name>`*，带**撤销**，它会完整放回被删掉的东西：文件回到它的知识集，知识集连同它的页面、来源和 README 一起回来，作为一次由你写入的新改动。如果同一路径上已经又有了文件，或者同名知识集已经重新存在，撤销会被拒绝，不写入任何东西。提示消失之后，被删的文件就没有窗格可以打开它的历史了，但它的版本仍在保险库的历史里，可以用 git 找回（`git -C ~/.coffer/vault log -- knowledge/<path>`）；被删知识集的文件也可以，但它的注册信息不行，所以**删除知识集…**会先询问。
:::

## 不要放进知识的东西 {#what-not-to-put-in-knowledge}

- **密钥。** 不放 key、令牌或密码。请用[密钥存储](/zh/guides/secret-store)。
- **代码里已经写明的东西。** 智能体能在仓库里读到的，就不该放这里。
- **草稿笔记。** 放进来的东西，一个月后应该依然成立。

## 故障排查 {#troubleshooting}

**一次整理把页面改坏了。** 在知识集**改动记录**里这次整理的那一条上，用**撤销这次整理…**撤销整次整理（见[撤销一次整理](#undo-a-tidy)）；或者只放回一个页面：打开它，按**历史**，选一个整理之前的版本，按**恢复此版本…**。

**一次整理显示成了好几次磁盘编辑。** 智能体没有先运行 `coffer knowledge tidy-start`，或者它工作时 Coffer 重启了。它的编辑都在历史里，一次编辑一条；从页面的**历史**里恢复。

**知识集页面说有智能体在整理，但什么都没发生。** 智能体没有运行 `tidy-finish` 就停了。请它结束，或者等着：知识集 30 分钟没有变化后，Coffer 会结束这次整理，记为*未汇报即结束*。

**更新之后，所有页面都列在需要重新核对的页面下。** 这些页面还没有 `verified` 日期。按**整理**：智能体会逐个重新核对并写上日期。想关闭某个知识集的这项检查，就在它的 README 里设 `verify_after_days: 0`。

**整理之后来源仍然是待整理。** 没有页面在 `sources` 里列出它的 slug。请你的智能体整合它；如果其中没有值得写成页面的内容，就请它标记 `ingest: skipped`。

**某个链接显示为红色。** 它指不到任何页面、别名或来源，通常是页面被改了名或被合并掉了。修好这个链接，或者把旧 slug 加进保留下来的页面的 `aliases`；**整理**会修好它发现的失效链接。

**我的文档被移进了 `pages/`。** 这是扫描在把零散的 Markdown 归入知识集的结构（见[页面和来源出现之前的知识集](#collections-from-before-pages-and-sources)）。新页面请写在 `pages/` 下；这次移动在**改动记录**里，可以从历史里恢复。

**整理只提供复制提示词。** 没有可用的托管智能体。到**智能体**里添加一个，或者把复制的提示词粘贴到你用的智能体里；它必须装有 `coffer-guide` 技能。

**在 Obsidian 里新建的笔记被移进了 `pages/`。** Obsidian 把它建在了库根目录，扫描把它归了档。把 Obsidian 新建笔记的存放位置设成知识集的 `pages/` 文件夹（见[在 Obsidian 中打开知识集](#open-a-collection-in-obsidian)）。

**菜单里没有在 Obsidian 中打开。** 只有这台 Mac 装了 Obsidian（在 `/Applications` 或你自己的“应用程序”文件夹里）时，Coffer 才会提供它。

**来源说它的原文件在另一台 Mac 上。** 上传的文件只保存在上传它的那台 Mac 上。到那台 Mac 上打开这个来源，或者在这台 Mac 上重新上传这个文件。

**上传的文档里少了一张图。** 一边不到 48 像素、超过 5 MB，或一次上传里排在第 40 张之后的图片不会保留；画在图片里的文字会作为图片保留，而不是文字。可以在上传它的那台 Mac 上查看原文件。

**智能体没有用到知识。** 检查 `coffer-guide` 技能已启用并且到达那个智能体（技能页面上它的**生效范围**按钮），以及知识集的 `README.md` 开头是否有一句写明主题的话。

**智能体写的文件没有出现。** 写进知识集的页面在下一次读取时就会出现。留在 `.inbox/` 里的文件必须是 Markdown，直接放在已有知识集的 `.inbox/` 文件夹里，并在下一次扫描（约一分钟内）成为来源；放在别处的文件不会被处理，不是 Markdown 的文件也不会作为来源保留。

## 相关 {#related}

- [技能](/zh/guides/skills)：携带目录以及写下、整合和整理规则的 `coffer-guide` 技能
- [记忆](/zh/guides/memory)
- [保险库同步](/zh/guides/vault-sync)：哪些内容会同步，以及接入的文件夹为什么不同步
- [知识架构](/zh/architecture/knowledge)
- [`coffer knowledge` 命令参考](/zh/reference/cli/knowledge)
- [MCP 工具参考](/zh/reference/mcp-tools)
- [知识规格](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/knowledge/spec.md)
<<<<<<< HEAD
- [Knowledge Is a Wiki of Pages Compiled From Kept Sources](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/knowledge-is-a-wiki-of-pages-compiled-from-kept-sources.md)、[Knowledge Is Plain Files](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/knowledge-is-plain-files.md) 、[Tidying Knowledge Is the Agent's Job, One Hand-Off Recorded as One Change](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/tidying-knowledge-is-the-agents-job.md)、[Knowledge Stays Current Through Flags Coffer Computes and an Agent Clears](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/knowledge-stays-current-through-flags-coffer-computes.md)、[A Linked Knowledge Folder Is Shared in Place, Read-Only to Coffer, and Recorded Machine-Local](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/linked-knowledge-folders-are-read-only-and-machine-local.md) 和 [Knowledge Sources Keep Their Images; Originals Stay on This Mac](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/knowledge-sources-keep-their-images-and-originals-stay-on-this-mac.md)
=======
- [Knowledge Is a Wiki of Pages Compiled From Kept Sources](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/knowledge-is-a-wiki-of-pages-compiled-from-kept-sources.md)、[Knowledge Is Plain Files](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/knowledge-is-plain-files.md) 、[Tidying Knowledge Is the Agent's Job, One Hand-Off Recorded as One Change](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/tidying-knowledge-is-the-agents-job.md)、[Knowledge Stays Current Through Flags Coffer Computes and an Agent Clears](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/knowledge-stays-current-through-flags-coffer-computes.md) 和 [A Linked Knowledge Folder Is Shared in Place, Read-Only to Coffer, and Recorded Machine-Local](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/linked-knowledge-folders-are-read-only-and-machine-local.md)
>>>>>>> origin/claude/project-thread-6qp5yc
