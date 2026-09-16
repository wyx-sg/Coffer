# 功能规格：知识层

> English: [spec.md](./spec.md)

**Created**: 2026-05-22（当时叫 *Memory*）· **与知识库合并**: 2026-09-10 · **精简为纯文件**: 2026-09-12 · **恢复摄入**: 2026-09-12 · **移除带排序的检索**: 2026-09-14
**Status**: Accepted
**目录名**: 本 spec 位于 `specs/knowledge/`，这个目录名就是所有入链和 `scripts/audit_acceptance.py` 所依据的 spec id。

**Input**: Coffer 存放**关于用户工作环境的知识**：他的代码仓库、服务、项目、对接的人，以及值得跨会话留存的决策和陷阱。它既是人上传进来的东西，也是人和 agent 一起写下的东西，归档进一个个 **collection**。它是一个 **Markdown 文件目录**——文件就是唯一真相，人靠打开文件夹找到需要的东西；agent 靠读目录、grep 某一行，或者问某个词句出现在哪些文件里找到它。见 [Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md)。

**知识不是记忆。** 知识讲的是世界——某个平台的 API 契约、某个服务归谁所有、某人发布的一篇文档——它在这里，是因为有人把它放了进来。记忆讲的是用户和他的项目，它随着 agent 干活自行累积。两者在所有要紧的维度上都不同——谁写的、怎么划分、怎么投递，以及一条条目能不能被*取代*——所以它们是两层：本层按 collection 归档、需要时**拉取**；spec [memory](../memory/spec.md) 按项目划分、在会话开始时**推送**。

## 这一层服从的原则

**知识由人和 agent 共同管理。** 下面每一条决定都由它推出：元数据放在文件里而不是数据库行里，因为只有文件是双方都能看见的；目录是生成的而不是存下来的，因为存下来的那份会和人在文件管理器里看到的漂移；人的编辑器和 agent 的 `write` 触及的是同一批字节，中间没有任何东西。

## 2026-09-12 移除了什么，为什么

对本机实际安装的审计发现这一层大部分从未执行过：`embedding_config` 是空表，`.history/` 在磁盘上不存在，50 篇文档里 50 篇都是 `converter: passthrough`，而一个月调用历史里每一次知识工具调用都发生在某个 agent 建语料的那一天。两个结构性失误解释了这一切——属性被做成了目录（`notes/` ÷ `docs/`、`global` ÷ `project-<ULID>` ÷ collection），而一旦 embedding 从未被配置，索引买到的就只剩 agent 自己会做的排序。

移除：任意格式转换与转换器注册表；`.raw/` lane；外部源追踪；`source_mode` 与再转换锁；lane 划分；由 cwd 推导的 scope、自动创建与 `project-<ULID>` 命名；FTS5、sqlite-vec、混合融合、分块、读时惰性重建索引与显式重建；per-scope 检索配置；scope 显示标签。随之移除 11 张表。

## 2026-09-12 又恢复了什么，为什么

上面那些移除里有一项在同一天被撤回，理由是移除时没有权衡到的。这不是对那次精简的翻案——**路径仍然是身份，frontmatter 仍然是元数据，文件仍然是唯一真相**。回来的是一个入口。

**摄入回来，是因为从用户真正所在的地方够不到文件系统。**「把一篇 Markdown 放进目录」这个入口，只在用户坐在这台机器前时才存在。他随身的入口是手机：渠道已经能收附件，也已经会为一轮对话抽取其中的文本（spec [channels](../channels/spec.md) FR-030）。把一篇文档从那个聊天发给 Coffer、让它落进某个 collection，就是本层缺的那条摄入路径——而这也让 Web 上传重新值得存在，作为同一条路径的另一端。

## 2026-09-14 移除了什么，为什么

带排序的检索在 2026-09-12 被恢复，现在又被**有意拿掉**。它是能跑的：查询经内部连接做 embedding，段落向量放在一个可丢弃的 sidecar 里，用余弦排序，而没有配置连接时由一次字面搜索兜底。这次拿掉的是 embedding 那一半，以及一切为它而存在的东西——sidecar 索引、新鲜度记账、向量运算，还有「一个答案有两条路径」这件事本身。

理由是：原本作为*回退*的那一层，恰恰就是这个语料真正需要的全部。在几百篇文件的规模上，一个会读目录、会 grep 词句的 agent 已经能找到它要的东西，而那层排序为它买到的很少，代价却是多一份要和磁盘保持同步的东西、多一项有些安装根本没有的连接依赖，以及「读一次就把文件正文发出这台机器」。所以 `search` 现在就是那次字面搜索本身，从回退升格为答案：对调用方可见的文件跑 ripgrep，按文件返回。哪天语料规模真的需要，embedding 可以重新挣回它的位置；那是之后的一个决定，而不是这次留下的半截工程。

这次移除换来的是：**查询和文件之间不再隔着任何派生物。** 没有索引，也就没有什么要重建、没有什么会过期、没有什么要对账，更没有什么要排除在备份之外。

同一条理由也延伸到 Web 页面，于是**页内搜索框也随之移除**。collection 的详情页上原本有一个框，向 `/knowledge/search` 发请求，然后在本该是树的位置回一串命中列表——这是通往同一个文件的第二条路，有它自己的规则，还叠在它正在查询的那个文件夹之上。collection *就是*一个文件夹，所以这个页面现在只做浏览这一件事：左边一棵树，右边一个只读预览，和 skill 详情页的 Files tab 是同一副两栏（FR-061）。`search` 路由本身不动，它为之而建的调用方也都还在——agent 用 `coffer__search`，CLI 用 `coffer knowledge search`。被拿掉的只是那个在树上面重复了树的调用方。

## 用户场景与测试

### 用户故事 1 — 一个知识库，所有 agent（优先级 P1）

开发者上午用 Claude Code，下午用 Codex。上午某个 agent 记下某服务的登录态归 `account.session` 所有；下午另一个 agent 找到了它，因为两者读的是同一个目录。没有副本会漂移，因为只有一份。

**独立测试**：从一个 MCP 客户端写入一条事实；从另一个身份不同的客户端列目录并把文件读回来。

### 用户故事 2 — collection 是人的归档方式，也是授权单位（优先级 P1）

有些知识是公司内部细节，不能让他运行的每个 agent 都拿到；有些是业余项目的，给谁都无所谓。开发者有意创建一个 collection，把敏感材料放进去，只授权给可以看的 agent。collection 内部他爱怎么嵌套怎么嵌套，Coffer 既不知道也不关心。

**独立测试**：创建两个 collection，其中一个只授权给单个 agent，确认另一个 agent 的目录和读取都不包含它。手工建一个嵌套文件夹，确认目录能走进去。

### 用户故事 3 — 没有索引也能找到对的文件（优先级 P1）

agent 需要一条自己说不出确切措辞的事实。它先列出 collection、读每个的一句话描述，下钻到最可能的那个，读那里的标题和描述，然后要么直接读某个文件，要么用刚学到的字面串去 grep。

**独立测试**：对一个有内容的 collection，逐层调用目录并确认返回了标题和描述；grep 一个中文串并确认命中的文件与行。

### 用户故事 4 — 人用自己的工具做整理（优先级 P2）

开发者从 Finder 把一篇 Markdown 丢进某个 collection，在自己的编辑器里改掉一行错的，删掉一篇过时的。每一次改动对下一次 agent 调用都是即时生效的，不需要任何导入步骤，因为文件**就是**知识。

**独立测试**：在 Coffer 之外添加一个文件，确认它出现在目录和 grep 里；改一个文件，确认 `read` 返回的是新字节。

### 用户故事 5 — agent 知道这一层存在（优先级 P1）

Coffer 投递的一个 skill 告诉 agent 这一层在这里、怎么用。它走的是已经在投递 Coffer 其它 skill 的同一条通道，所以每个被管理的 agent 都能拿到，不需要 hook，也不往 agent 自己的记忆里写任何东西。

**独立测试**：在绑定了某个受管 agent 的情况下，确认知识 skill 出现在它的 skill 目录里，并且写明了「先看目录再 grep」这套动作。

### 用户故事 6 — 人要求的时候才整理（优先级 P3）

笔记会堆积、会重复。开发者触发一次 tidy，它先归档每个旧版本，再合并改写。他也可以让它定时跑，但必须先自己打开——而且在 vault 同步之后，只会在被指名为 tidy owner 的那一台机器上跑。

**独立测试**：对一个有重复内容的 collection 跑一次 tidy；确认 `.history/` 里有旧版本，且归档副本永远不出现在 grep 结果里。

### 用户故事 7 — 文档能从用户所在的任何地方进 vault（优先级 P1）

开发者在聊天里收到一份 PDF。他把它转发到自己的 Coffer 渠道，说清它该进哪个 collection，它就以 Markdown 的形式落在那里，标题和描述都已填好，原件另存一边。回到桌前，他把文件拖到「知识」页面上，做的是同一件事。两种方式过后它都只是某个 collection 里的一个文件，和他手写的那些毫无区别。

**独立测试**：通过 REST 面上传一篇非 Markdown 文档，确认 collection 里出现了带 frontmatter 的 Markdown 文件、原件在 `.raw/` 下，且转换出的文本可以被 `read` 读到。

### 用户故事 8 — 要的是文件，不是行（优先级 P1）

agent 手里有一个有辨识度的词或短语，它要的是这个词句出现在哪些*文件*里——而且它也负担不起先把目录翻一遍。它拿这个词句去搜，拿回包含它的那几个文件，每个都带着 `title`、`description` 和命中的行，于是它在真正读之前就能判断自己找到了什么。匹配是字面的，所以一个用 agent 自己的话措辞的问题什么也找不到；工具自己的描述和投递出去的 skill 都会这么说。

**独立测试**：写一个含有某个有辨识度短语的文件，搜它，确认该文件带着 `title`、`description` 和命中行返回；再搜一个语料里完全不出现的措辞，确认返回的是空结果而不是报错。

## 验收场景

### Scenario: a written note lands as a markdown file with a readable name

### Scenario: frontmatter carries title, description and actor

### Scenario: a file added out-of-band is visible to the next call

### Scenario: the catalogue lists collections with their README description

### Scenario: the catalogue lists one level of a collection

### Scenario: the catalogue walks into a nested directory

### Scenario: grep matches a literal string across a collection

### Scenario: grep matches CJK content

### Scenario: grep skips hidden directories

### Scenario: read returns a file by path

### Scenario: creating a collection registers a knowledge resource

### Scenario: an unknown collection is an error, never auto-created

### Scenario: a collection outside an agent's scope is absent from its catalogue

### Scenario: a collection outside an agent's scope cannot be read

### Scenario: write creates a file and replaces an existing one

### Scenario: delete removes the file from disk

### Scenario: a path escaping the knowledge root is rejected

### Scenario: the six built-in knowledge tools appear in the client tool list

### Scenario: search returns the files a phrase appears in, with the lines that matched

### Scenario: search spans only the collections the caller may see

### Scenario: an uploaded document lands as markdown with frontmatter

### Scenario: an uploaded original is kept under .raw/ and stays out of retrieval

### Scenario: an upload of an unsupported type is refused with its reason

### Scenario: a document forwarded to a channel lands in a collection

### Scenario: tidy archives the prior revision before rewriting

### Scenario: tidy is a no-op when no internal model is configured

### Scenario: the tidy worker stays off unless enabled

### Scenario: a second tidy pass over the same collection is refused while the first is running

### Scenario: the knowledge skill is delivered to a managed agent

### Scenario: the viewer renders content read-only and offers open and reveal

### Scenario: migration rewrites ULID documents into named files in collections

## 需求

### 存储

- **FR-001**: 知识 MUST 以 Markdown 文件形式存放在 `~/.coffer/knowledge/<collection>/` 下。文件是**唯一真相**，查询和它们之间 MUST NOT 隔着任何派生物：系统 MUST NOT 保留任何形式的检索索引——没有向量、没有 sidecar、没有缓存——每一个答案都在调用时直接读盘得出。
- **FR-002**: 文件的**路径就是它的身份**。frontmatter 里 MUST NOT 有独立的 id 字段，任何地方 MUST NOT 有 id 到路径的映射。文件名 MUST 是由标题推出的人类可读 slug；重名时追加短后缀。
- **FR-003**: 每个文件 MUST 带 YAML frontmatter，包含 `title`、`description`、`actor`（`agent` | `user`）、`created_at`、`updated_at`，且仅此而已。`description` 是**必填**而非可选：search 是字面匹配，所以对任何调用方引不出原话的东西，目录就是检索界面，一个不描述自己的文件等于找不到。
- **FR-004**: 一个 collection MAY 含有任意深度的子目录。系统 MUST NOT 赋予它们含义、MUST NOT 要求它们存在、MUST NOT 创建它们。
- **FR-005**: 隐藏条目（点开头）MUST 被排除在目录和 grep 之外。`.history/` 是系统自己写的唯一一个。
- **FR-006**: 每个会成为路径片段的名字 MUST 通过穿越防护，且路径构造 MUST 只存在于一个模块中。

### collection

- **FR-010**: 一个 **collection** 是知识根目录下的一个顶层子目录，同时是一个 `knowledge` Resource。它 MUST 由人通过 REST/CLI/UI 有意创建，MUST NOT 由读取、写入或 agent 的工作目录自动创建。
- **FR-011**: 系统 MUST NOT 从 agent 的 cwd 推导任何边界。MUST NOT 存在 `global` scope、`project-<ULID>` 命名、git 根解析，以及 scope 到项目根的映射表。
- **FR-012**: collection MUST 支持 Resource 框架的 **per-agent scope**：一个 agent 只能看见、grep、读取和写入为它激活的 collection。agent 的调用 MUST 覆盖它被授权的**每一个** collection——MUST NOT 存在把已授权 collection 排除在默认之外的规则。一次调用据以授权的身份 MUST 是会话握手上报的身份（spec [mcp-gateway](../mcp-gateway/spec.md) FR-021），由网关以 `agent` 参数写进调用，任何工具的 input schema 都不公开这个参数；客户端在这个名字下自行传入的值 MUST 被丢弃，绝不采信。
- **FR-013**: collection 的一句话描述 MUST 取自其目录下 `README.md` 的首段，没有该文件时为空。它 MUST NOT 存在数据库里。
- **FR-014**: per-agent 授权仅在 MCP 工具面执行，系统 MUST 如实描述这一点：它防的是误召回，不是有意的文件系统访问。

### 检索

- **FR-020**: 目录 MUST 在调用时通过遍历目录、读取 frontmatter **即时生成**。系统 MUST NOT 把它物化成文件或表。
- **FR-021**: `list` MUST **一次走一层**：不带路径时返回调用方可见的每个 collection，各带 README 描述与文件数；带路径时返回该目录的直接子目录和文件，每个文件带 `title` 和 `description`。
- **FR-022**: `grep` MUST 对调用方可见的 collection 的文件运行 ripgrep，支持字面或正则、递归匹配，返回文件、行号与命中行。命中数 MUST 有上限，响应 MUST 标记是否被截断。ripgrep 是优先项而不是硬性要求：`PATH` 上没有 `rg` 的机器上，同一次搜索 MUST 改由内置的 Python 遍历完成，走同样的文件、同样的语义——跳过隐藏项、逐行正则、同样的上限与同样的截断标记——调用方除了速度看不出任何差别，守护进程 MUST 把这次回退记一次日志。
- **FR-023**: `read` MUST 按路径返回文件全文。MUST NOT 有分块、段落粒度或 `top_k`。
- **FR-024**: `search` MUST 以一次文本查询**出现在哪些文件里**作答，每个文件附上它的路径、`title`、`description` 和命中的行，文件数与每个文件的命中行数都 MUST 有上限。它 MUST 使用 `grep` 所用的同一个匹配器——正则、大小写敏感——作用于同一批文件；两个工具只在「报什么」上不同，`grep` 按行报，`search` 按文件报。MUST NOT 有分数、MUST NOT 有排序、MUST NOT 有标题段落，任何 surface 上 MUST NOT 存在检索*模式*，也 MUST NOT 存在第二条得出答案的路径。既然匹配是字面的，`search` MUST 在调用方读得到的地方把这一点说清楚：工具自己的描述 MUST 告诉 agent 给它一个有辨识度的词或确切短语，而不是一句用自己的话措辞的问题。
- **FR-028**: 一个文件 MUST 在落地的那一刻就可搜，没有任何重建索引步骤——不是因为有一条新鲜度规则让索引跟得上磁盘，而是因为根本没有索引需要跟。`search` 在调用时直接读文件，所以编辑器、渠道、`write` 或 `git` 写下的文件，下一次调用就能找到。
- **FR-029**: `search` MUST 只覆盖调用方可见的 collection 之下的文件，MUST 跳过隐藏目录（`.history/`、`.raw/`）。它 MUST NOT 把文件内容发往任何地方：search 完全在本机运行，不需要任何形式的连接。

### 写入与摄入

- **FR-030**: `write` MUST 依据 `title`、`description` 和正文创建文件，或在给定已存在路径时替换它。写入 MUST 是一次普通的文件写——没有 LLM、没有转换、没有索引步骤。
- **FR-031**: `delete` MUST 从磁盘上删除文件。
- **FR-032**: 把一篇 Markdown 放进目录 MUST 始终是一种完整的添加知识的方式——不需要导入、不需要注册、不需要转换。下面的摄入只是为文件系统够不到的场景多开的一个入口，绝不是必经之路。
- **FR-033**: 系统 MUST 接受把一篇文档上传进指定的 collection 并把它转成 Markdown。支持的输入 MUST 恰好是 `markitdown` 能处理的那些，加上纯文本和 CSV；不支持的类型 MUST 被拒绝并指明类型，MUST NOT 半转换地存下来。
- **FR-034**: 转换后的文档 MUST 落成一个普通的 Markdown 文件，此后与手写的毫无区别：一个可读的 slug 作文件名，加上 FR-003 的 frontmatter——`title` 取自文档本身（取不到时退回它的文件名），`description` 也要填好：配了内部连接时由它生成，没配时取文档开头的正文。
- **FR-035**: 上传的原件 MUST 存放在 **collection 根目录**下唯一一个隐藏的 `.raw/` 目录里，路径就是转换后的文件相对该根目录的路径，使一次糟糕的转换可以从用户发来的字节重做。`.raw/` MUST 被排除在目录、grep 和 search 之外，并 MUST 在其转换后的文件被删除时一并删除。Coffer MUST NOT 定时重新转换它，也 MUST NOT 把它当外部源追踪——这正是 2026-09-12 精简因从未被用到而移除的那两套机制。
- **FR-036**: 发到 Coffer 渠道的文档 MUST 能经同一条转换路径摄入某个 collection，使手机和「知识」页面成为同一个入口的两端（spec [channels](../channels/spec.md)）。渠道 MUST 在存下之前向主人确认 collection，且 MUST NOT 存下任何来自非主人的东西。
- **FR-037**: 上传 MUST 有界：一次调用一个文件、一个大小上限，以及一条指明该上限的拒绝。转换失败 MUST NOT 留下 Markdown 文件，也 MUST NOT 留下 `.raw/` 原件。

### 工具与投递

- **FR-040**: Coffer 的 MCP 网关 MUST 在 `coffer__` 前缀下暴露恰好**六个**内置知识工具：`list`、`grep`、`read`、`search`、`write`、`delete`。上传不在其中——文档从人的界面进来（「知识」页面或某个渠道），而不是从 agent 的工具调用进来。
- **FR-041**: 内置调用 MUST 继续记录一行 `mcp_invocations`（工具、谁、耗时、结果——不含参数与内容）。写入或删除 MUST 额外记录一条以 agent 为 actor 的审计事件。
- **FR-042**: Coffer MUST 通过既有的 skill 投递通道（spec [skill-manager](../skill-manager/spec.md)）投递一个**知识 skill**，教会「先看目录再 grep」这套动作，以及什么时候该改用 `search`。本层 MUST NOT 自作主张往任何会话里推送任何东西，也 MUST NOT 写入任何 agent 自己的记忆文件：知识是被拉取的。会话开始时的投递属于 spec [memory](../memory/spec.md)，那一层自带预算和自己的同意机制。

### 整理

- **FR-050**: 系统 MUST 提供针对某个 collection 的有界 agentic **tidy** 过程，由内部模型连接驱动，其工具面是四个文件操作——`list`、`read`、`write`、`delete`。它 MUST 在任何覆盖或合并之前把文件旧版本复制进 `.history/`。没有配置内部连接时 MUST 是干净的 no-op。
- **FR-051**: tidy MUST 可从 UI 和 `coffer knowledge organize` 手动触发。后台 worker MAY 按间隔运行它，由一个**默认关闭的安装级设置**控制。该设置 MUST 同时**指名一台机器**。它今天是 singleton `internal_engine_config` 行上那一个 `auto_tidy_enabled` 布尔值，worker 的 enabled-check 每一跳都读它；它 MUST 再带上一个 owner 机器 id——取自同步机器注册表的 `machine_id`（spec [vault-sync](../vault-sync/spec.md)），在没有选定 owner 之前为 null——这样这个开关读起来是*在这里开着*，而不只是*开着*。
- **FR-052**: `.history/` MUST 以点开头，因此被排除在目录和 grep 之外。
- **FR-053**: tidy 设置 MUST 是**同步状态**，随 vault 走在已经承载它的 `internal-engine` 文档里，让每台机器对 owner 是谁达成一致。一次 tidy MUST 只在设置指名的那台机器上运行，在其它每一台上 MUST 是干净的 no-op。没有这条规则，两台机器会各自改写同一份语料：它们把同一对笔记合并进一篇主题文档，却是*不同*的两篇，而 git 干净地合并了结果——两边都同意原始文件已删除，两篇主题文档又是不同路径上的新增——于是 vault 里同一份知识存了两遍，且没有任何冲突被报出来。如果 owner 机器是关着的，那就根本不会有 tidy 发生；对一个后台的锦上添花功能来说，这是可以接受的取舍。
- **FR-054**: 一次 tidy 与一轮 converge MUST NOT 重叠。两者都在写 vault，改写进行到一半时取的导出是一份被撕开的快照，所以它们 MUST 取同一把锁。此外，只要还有未解决的冲突或待确认事项，这次 tidy MUST 被跳过，绝不把改写叠在一次没解决的分歧之上。
- **FR-055**: 当 owner 的 tidy 删掉了一个文件，而另一台机器编辑过它时，**编辑 MUST 胜出**：文件带着它的编辑保留下来，删除被丢弃，且这一轮 MUST NOT 报冲突。一次新鲜的编辑是人或 agent 刚刚做出的决定；而删除只是一个整理上的判断，下一次 tidy 自然会再做一遍。
- **FR-056**: 同一个集合上同一时刻 MUST 只有**一次 tidy** 在跑，不论是谁发起的。一次 tidy 要跑上几分钟并改写该集合的文件，所以对同一集合的第二次 tidy 不是更快的整理，而是两个写者在同一个目录上打架。一次手动触发若在已有 tidy 进行中时到达，MUST 被**拒绝**而不是排队（`UPKEEP_ALREADY_RUNNING`，409）——调用方要的是「开始一次 tidy」，而这次并不会开始——定时 worker 则 MUST **跳过**那个已在整理中的集合，而不是等在它后面，反正下一轮扫描还会再来。此刻正在被改写的是哪些集合 MUST 可读，这样一个在 tidy 进行中才打开的界面看到的是这次 tidy，而不是一个空闲的按钮在邀请第二次点击。这份记录属于单个 daemon 且不比它活得更久：一次 tidy 活在被请求的那个进程里，所以重启即终结，读回来就是空的——这是事实，不是丢失的记录。

### Surface

- **FR-060**: `/api/v1/knowledge` 下的 REST API 与 `coffer knowledge` CLI 组 MUST 覆盖：创建 collection、按路径列目录、读文件、search、上传文档、写文件、删文件、触发 tidy。删除 collection 走 Resource 框架（`DELETE /api/v1/resources/knowledge/{name}`）。MUST NOT 存在索引、重建索引、check-sources、update-source、embedding 配置或 per-scope 设置端点。
- **FR-061**: Web UI MUST 把一个 collection 呈现为**两栏文件浏览器**，和 skill 的文件夹用的是同一副（spec [skill-manager](../skill-manager/spec.md)）：左边一棵**单一树**——没有 lane tab，按 FR-021 列目录的方式一级一级展开——右边是从树上选中的那个文件，通过统一文件预览以**只读**方式渲染，并对它及其所在文件夹提供「在外部编辑器打开」和「在文件管理器中显示」。MUST NOT 有应用内编辑器。它 MUST 提供把文档上传进当前所看 collection 的入口。这个页面 MUST NOT 自带检索框：树旁边那唯一一个输入框只在客户端筛选已经显示出来的名字，而真正去读文件内容的是 `search` 和 `grep`，它们的调用方是 agent 的工具和 CLI。没有索引新鲜度可报，也没有重建可给。
- **FR-062**: 读取响应 MUST 带上文件的绝对路径及其所在文件夹的绝对路径。

### 迁移

- **FR-070**: 一条 migration MUST 删除所有知识专属的表——`documents`、`chunks`、六张 `documents_fts*`、`embedding_config`、`knowledge_scope_labels`、`knowledge_scope_project_roots`——并加守卫，使缺少其中任何一张的数据库仍能升级。
- **FR-071**: 在删表**之前**，一次数据迁移 MUST 重写磁盘语料：每篇文档的 `title`（今天只存在数据库里）成为它的文件名和 frontmatter，文件从 `notes/` 和 `docs/` 移入 collection，`.raw/` 被删除。现有 scope 落成两个 collection：关于内部系统的文档进 `shopee`，项目自己的进 `coffer`。迁移 MUST 是单向的，**不留任何兼容垫片**。

### 约束

- **FR-080**: 本层 MUST NOT 带**任何向量库或 embedding 模型依赖**：`sqlite-vec`、`fastembed`、mem0、chroma、LlamaIndex MUST NOT 出现在依赖集中，任何地方也 MUST NOT 计算、获取或存放向量。search 就是 ripgrep——机器上有它就用它，没有就走 FR-022 的内置字面遍历——两者都不是索引。`markitdown` 在渠道的转换器之外，同时成为本层的转换器；importlinter 契约 MUST 恰好只允许这两个消费者，不再有别的。
- **FR-081**: 知识层 MUST NOT 向 `coffer.db` 新增任何表，也 MUST NOT 在知识根目录之外建自己的目录。一个 collection 就是 kind 无关的 `resources` 表里的一行，和其它 Resource 一样；本层持有的其余一切都是人打得开的文件。

## 成功标准

- **SC-001**: 一个 agent 写下的事实，另一个 agent 能通过目录读到，中间没有任何索引步骤。
- **SC-002**: 人在 Coffer 之外添加或编辑的文件，下一次调用就能返回，不需要导入、重建索引或对账。
- **SC-003**: 只被授权某个 collection 的 agent，无法通过任何内置工具看到另一个。
- **SC-004**: 这一层在 `coffer.db` 里不持有任何知识专属的表，也不在任何地方留下文件内容的派生副本。
- **SC-005**: 对语料的一次 grep 能返回命中的文件与行，中文内容同样如此，且不需要分词器。
- **SC-006**: 在 Coffer 之外添加的文件，下一次 `search` 就能返回，中间不需要重建任何东西：整台安装里找不到索引目录、找不到 sidecar，也找不到一条重建索引的命令。
- **SC-007**: 从渠道发来的一篇文档，事后就是目标 collection 里的一个 Markdown 文件，原件可以找回，而 agent 读它的方式和读其它文件一样。
- **SC-008**: `search` 在一台全新安装上就能工作，什么都不用配——不需要连接、不需要索引、不需要任何设置。

## 假设

- 语料规模保持在几百篇文件。在这个规模下目录仍然塞得进 agent 的上下文，对这么多文件跑 ripgrep 也是瞬时的，所以 `search` 是对「先看目录再 grep」的补充而不是替代。几万篇文件，或者一个 agent 确实没法靠名字导航的语料，会是另一套设计、另一个决定——也正是 embedding 会被重新考虑的地方。
- tidy 会在没有审阅环节的情况下改写文件，所以 `.history/` 就是全部的安全网。它默认关闭正是因为这个。
- 内部连接是用户内容唯一可以离开这台机器的地方，这一点 spec [channels](../channels/spec.md) FR-022 已经为语音确立过。search 从不使用它——它读不出磁盘之外——所以会发到那里去的知识文本，只有 tidy（FR-050）和摄入文档时生成 `description`（FR-034）发出的那些。
