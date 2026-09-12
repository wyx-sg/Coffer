# 知识层是一个文件目录，不是一个索引

> English: [knowledge-is-plain-files.md](./knowledge-is-plain-files.md)

**Status**: Proposed
**Date**: 2026-09-12
**Deciders**: Yuxing Wu
**Supersedes**: [Retrieval Stack — Markdown Files as Truth, SQLite FTS5 + sqlite-vec](files-as-truth-sqlite-retrieval.md)、[Retrieval mode is an internal engine detail](retrieval-mode-is-internal.md)
**Related**: spec [knowledge](../../specs/knowledge/spec.md)；[Everything Is a Resource Kind](everything-is-a-resource-kind.md) 与 [Per-Agent Resource Scope](per-agent-resource-scope.md)（两者都保留）；[Memory via MCP](memory-via-mcp-not-native-projection.md)

## 背景

已建成的知识层是三层架构里约 10,800 行后端代码加上它的各个 surface，背后有 11 张
数据库表。它带着两条存储 lane、三种 scope、经 MarkItDown 的任意格式摄入、FTS5 与
sqlite-vec 之上以倒数排名融合的四种检索模式、一个周期性的 agentic 整理（tidy）过程，
以及六个 MCP 工具。

2026-09-12 对本机实际安装做的审计，查清了其中有多少真的在用。

**日常工作中没有任何东西去取它。** 在全部调用历史里（506 条，一个月），每一次知识
工具调用——13 次 `search`、8 次 `write`、8 次 `list`、4 次 `read`——都发生在
**2026-09-11**，也就是某个 agent 建这批语料的那一天。此前此后没有一次来自日常工作。
与此同时，同一台机器上 Claude Code 的原生记忆光 Coffer 一个项目就有 75 篇，因为那份
会被自动加载进上下文。

**大部分机制从未执行过：**

| 能力 | 本机实际状态 |
| --- | --- |
| 向量检索（sqlite-vec、embedding、hybrid RRF、`embed_pending` 重试） | `embedding_config` 是**空表**；没有任何 scope 启用过 `vector` |
| 周期性 tidy（FR-033–FR-035） | 知识相关 audit 事件为 **0**；`.history/` 在磁盘上**根本不存在** |
| 任意格式转换（MarkItDown、csv 转换器） | **50 篇里 50 篇**都是 `converter: passthrough` 且 `source_format: md` |
| `.raw/` 原件 lane | 50 个文件，与 `docs/` 下的对应文件**逐字节相同** |
| 外部源追踪（`check-sources`、`update-source`、`auto_update_sources`） | 零调用 |
| `source_mode: converted \| edited` 再转换锁 | **50 篇里 50 篇**是 `converted`；这把锁从未生效 |
| scope 显示标签 | `knowledge_scope_labels` 是**空表** |
| 具名 collection | 三个月来创建了 **0 个** |
| 按项目的 scope | 解析出 **14** 个项目根，**1** 个有内容；已创建的 4 个 scope 里有 2 个是只读搜索留下的空壳 |

两个结构性失误解释了其中大部分。

**把属性做成了目录。** `notes/` ÷ `docs/` 这条 lane 声称区分的是「谁写的」和
「谁传的」，但唯一带有行为后果的差别只有一个：这份内容的真相在 Coffer 里还是在
外面——而本机没有一篇在外面：50 篇全是 agent 写的 markdown，只不过走了文件那道门
进来。`global` ÷ `project-<ULID>` ÷ collection 这套 scope 想表达的是「这条知识关于
什么」，那是内容的属性。两者都付出了物理结构的全部代价——迁移、空壳、割裂的 UI、
查询时的跨边界融合——去表达一行 frontmatter 就能承载的东西。检索**必须**靠倒数排名
跨 scope 融合才可用，这件事本身就是破绽：隔离从来不是目的。

**没有 embedding，索引买到的就只剩排序。** 索引相对 ripgrep 唯一多出来的能力是概念
检索——用「鉴权」去匹配写着「认证」的文档。那需要 embedding，而 embedding 从未被
配置过。去掉它之后，FTS5 相对 ripgrep 多出来的只有 BM25 排序和分块粒度，而这两件事
agent 自己就会做：它读命中行、判断哪个文件相关，然后反正要读全文。在本机语料上实测
（51 篇，1.4 MB），一次 ripgrep 查询返回与 FTS5 相同的答案集，耗时 **27 毫秒**，而且
匹配中文根本不需要分词器。这中间没有好的折中：要么完整的语义栈，要么不要索引。在这个
区间里，只留 FTS5 是性价比最差的一档。

决定其余一切的是用户定下的目标：**知识由人和 agent 共同管理。** 任何只有其中一方能
看见的东西，都放错了地方。

## 决策

**知识就是一个 Markdown 文件目录，agent 用 grep 和 read 去取。没有派生索引，也就
没有任何东西需要对账。**

- **存储。** `~/.coffer/knowledge/<collection>/…` 下是文件名人类可读的 Markdown
  文件。文件的 YAML frontmatter 带 `title`、`description`、`actor`
  （`agent` | `user`）和时间戳——元数据跟着文件走，所以人打开文件就看得见，agent
  grep 就找得到。没有 `id` 字段：路径就是身份。
- **检索 = 目录 + ripgrep。** `list` 一次走一层——不带参数时列出调用方有权看到的
  所有 collection，带路径时列出该层的子目录和文件，每一项都带 frontmatter 里的
  `title` 和 `description`。`grep` 做字面或正则匹配，递归；`read` 返回一个文件。
  agent 沿目录下钻选出**哪一篇**，再用 grep 找到**哪一行**。没有模式、没有排序、
  没有分块、没有 `top_k`。
- **目录是生成的，绝不物化。** 它在调用时遍历目录、读取 frontmatter 产生，所以不可能
  和磁盘漂移——根本没有第二份副本需要同步。一个物化的索引文件会把这次决策要消除的
  「派生物」问题原样带回来；旧设计里的 `knowledge/INDEX.md` 已在 2026-09-11 因为
  「是副产品而不是内容」被删除，这里不需要它回来。
- **collection 用自己的 `README.md` 描述自己。** 目录里对一个 collection 的一句话
  描述，取自该目录下 `README.md` 的首段。这是每个人和每个 agent 都已经会读的约定，
  它让描述对在 Finder 里浏览的人可见，而不是埋在数据库的一行里；而且它不会漂移：
  README 说的是这个 collection 是干什么的，从不复述里面有哪些文件。
- **collection 是唯一的边界，它存在是为了被授权。** 一个顶层子目录就是一个
  `knowledge` Resource：由人有意创建，Resource 框架的 per-agent scope 决定哪些
  agent 能看见它。collection 内部的嵌套是人自己的归档方式，对系统没有意义——
  ripgrep 本来就递归。
- **没有任何边界是推导出来的。** Coffer 不再从 agent 的 cwd 解析 scope，不在读取时
  自动创建任何东西，也不再生成 `project-<ULID>` 这样的名字。agent 的读取覆盖所有
  授权给它的 collection；不存在「默认看不见某个 collection」的规则。
- **五个工具，从六个减下来。** `list`、`grep`、`read`、`write`、`delete`。`search`
  没有了：背后没有带排序的索引之后，它只会是 `grep` 的第二个名字，而「这该用 search
  还是 grep？」正是 2026-09-10 那次合并在上一层消掉的同一种猜测。`write` 创建或替换
  一个文件；`delete` 删掉一个。
- **人加知识就是往目录里放文件。** 人把一篇 Markdown 丢进目录即可——文件系统就是
  上传界面，下一次 grep 就能看到它。
- **靠一个投递的 skill 让 agent 知道这一层存在。** Coffer 渲染一个描述知识层的
  skill，通过它本来就在运行的 skill 投递通道送出去（spec
  [skill-manager](../../specs/skill-manager/spec.md)、
  [Cross-Platform Skill Delivery](cross-platform-skill-delivery.md)）。agent 原生
  发现它——name 和 description 常驻上下文，body 教它「先看目录再 grep」这套动作——
  不需要 hook、不需要会话注入、不写任何 agent 的记忆文件。这条通道在本机已被证明有效：
  今天有 15 个 `coffer-*` skill 被投递并原生发现，而工具自己的描述一个月里一次检索
  都没触发。这是一个有证据支撑的假设，不是已验证的修复；而验证很便宜：调用日志本来就
  记录每一次知识调用，一周的日常工作就能给出答案。
- **tidy 保留，但自动执行默认关闭。** 一个有界的 agentic 过程——由 Coffer 的内部模型
  连接驱动——合并重复笔记、把它们改写成连贯的文档，并在动手前先把每个旧版本复制进
  `.history/`。它的工具面就是上面那五个，而且没有索引之后，跑完不需要对账。它始终可以
  手动触发（一个按钮，以及 `coffer knowledge organize`）；按间隔运行它的后台 worker
  由一个安装级设置控制，**默认关闭**——一个会无人值守改写共管语料的东西，应该是人主动
  打开的，而不是人某天发现它在跑。`.history/` 以点开头，所以 ripgrep 会跳过它，归档的
  旧版本永远不会作为第二条命中返回。
- **UI 保持只读。** 它渲染内容，并在人自己的编辑器里打开文件
  （[Daemon Proxies File Actions](daemon-proxies-os-file-actions.md)）。没有索引之后，
  在外部做的编辑立刻生效，不需要任何对账。

**移除：** 任意格式转换与转换器注册表；`.raw/` lane；外部源追踪（`check-sources`、
`update-source`、`auto_update_sources`、`source_path`、`source_sha256`）；
`source_mode` 与再转换锁；`notes/` ÷ `docs/` 的 lane 划分与 `documents.lane`；
由 cwd 推导的 scope、自动创建以及 `project-<ULID>` 命名；FTS5、sqlite-vec、
hybrid RRF、`embed_pending` 降级重试、分块、分块参数、读时惰性重建索引与显式重建；
per-scope 的检索/分块/上限配置；scope 显示标签。随之消失的还有 11 张表：`documents`、
`chunks`、六张 `documents_fts*` 表、`embedding_config`、`knowledge_scope_labels`、
`knowledge_scope_project_roots`。

**保留：** Markdown 文件作为唯一真相；`knowledge` 这个 Resource kind——现在是一个
collection 一个 Resource，为的是 per-agent 授权；tidy 过程及其 `.history/` 安全网；
只读查看器及其「在编辑器中打开」的能力。

## 后果

### 正面

- 一整类缺陷消失了。索引与磁盘漂移、content hash 对账，以及 `search`、`read`、`grep`
  三者对「自己覆盖哪个 scope」的三方分歧（PR #358 的成因），在没有索引时不可能发生。
- 人和 agent 真正共享同一份东西。人在自己编辑器里的修改，agent 下一次 grep 就能看到，
  中间没有任何环节；而 agent 写的每一项元数据，人打开文件就能读到。
- 这一层从约 10,800 行降到估计 1,500–2,500 行，知识专属的表从 11 张降到 0 张：
  一个 collection 就是 kind 无关的 `resources` 表里的一行，和其它 Resource 一样，
  知识层在数据库里再无其它东西。
- 人工添加知识的成本是复制一个文件，比任何上传界面都便宜。
- 授权变得有意义而不是顺带的：一个 collection 存在，是因为有人划了那条边界，而不是
  因为某个 agent 恰好在一个 git 仓库里启动过。

### 负面

- **语义匹配从 embedding 移到了模型身上，也就继承了模型的限制——以及一个天花板。**
  没有任何东西被向量化，所以 `grep` 只匹配字面文本；取代概念检索的是 agent 读目录、
  判断哪一篇相关——这件事它做得比向量距离更好，因为它理解问题背后的意图。这套成立的
  前提是目录塞得进上下文：按每条约 40 tokens 算，50 篇不算什么，500 篇仍然从容，
  5000 篇就不行了。分层目录让 agent 一次只读一层，把天花板往后推；越过之后，答案是
  一个真正的语义栈，为那个真实需求而建，而不是重新打开一个从未通电的组件。本机语料
  现在是 51 篇。
- **tidy 会在没有审阅环节的情况下改写共管语料。** 没有任何东西在它落盘前给出 diff，
  所以 `.history/` 就是全部的安全网。默认关闭让人保持在环内直到他自己决定打开，但
  worker 一旦开着，就是 agent 在无人值守地编辑人的文件。这是共同管理唯一不对称的
  地方，是为了一份否则会漂移的语料而做的有意交换。
- **排序成了 agent 的问题。** 在大语料上一次宽泛的 grep 会返回很多命中，agent 得自己
  收窄。让这件事保持可控的正是目录，而这对文件名和 `description` 提出了实打实的要求。
- **迁移是破坏性的、单向的。** 今天 title 只活在数据库里，所以每一个都必须在删表
  **之前**写进文件名和 frontmatter；没有第二次机会，也不留兼容垫片。现有语料落成两个
  collection——48 篇关于 Shopee 内部系统的文档进 `shopee`（这也正是授权真正有意义的
  那一批），Coffer 项目自己的 4 篇进 `coffer`——之后由人自己再归档。

### 中性

- **per-agent 授权是一种约定，不是安全边界。** 手里有 shell 或文件读取工具的 agent
  可以直接读 `~/.coffer/knowledge/` 下的任何文件。这个 scope 防的是误召回，不是有意
  访问。它取代的那套 scope 同样如此；真正的隔离需要独立的 vault 或文件系统权限，不在
  本次范围内。
- **投递依然由 agent 发起。** 知识只有在 agent 主动去取时才会进入会话
  （[Memory via MCP](memory-via-mcp-not-native-projection.md)）；投递的 skill 改变的是
  什么促使它去取，而不是由谁发起。没有任何东西被推进会话，也不会停用或写入任何 agent
  自己的记忆。这个 skill 够不够——上面的审计显示工具描述不够——是这次决策留下的唯一
  开放问题，而调用日志不需要任何新埋点就能回答它。
