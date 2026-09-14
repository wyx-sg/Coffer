# 知识

**知识**(knowledge)是 Coffer 中唯一一处存放"agent 应该知道的一切"的地方 —— agent(或你)写下的内容,以及你上传进来的文档。它就是 `~/.coffer/knowledge/` 下的一棵 Markdown 文件目录,一个集合一个文件夹,而这些文件就是它的全部。这里没有索引:没有向量库,没有全文表,`coffer.db` 里也没有任何需要与磁盘保持同步的东西。你在自己编辑器里改过的文件、agent 刚写下的文件、`git` 拉下来的文件,在 Coffer 看来都是同一回事 —— 因为中间什么都没有。

Coffer 曾经会把这些文件做 embedding,并按语义对检索结果排序。这项能力是被**有意**移除的:现在的检索就是在文件本身上做字面文本匹配。没有任何东西需要构建、重建或保持新鲜,也没有任何东西会过期。

## 集合

一个集合就是一个名为 `knowledge:<name>` 的资源,外加 `~/.coffer/knowledge/<name>/` 这个目录。两者一起出现,而且只因为你明确要求 —— 读取或写入都不会顺带创建集合,所以一个拼错的名字换来的是报错,而不是一个悄悄建出来的空集合。

```bash
coffer knowledge create handbook --description "Company onboarding docs"
coffer knowledge collections
coffer resource delete knowledge:handbook     # 集合的生命周期是资源的事
```

因为集合是一种资源,由框架的 per-agent scope 决定谁能读它。一个 agent 的调用会覆盖所有对它启用的集合 —— 任何知识工具都没有 scope 参数,也不存在"某个集合这个 agent 有权限、却必须报出名字才能用"的情况。这层授权是一种约定,而非安全边界:手握 shell 工具的 agent 照样能直接读目录。它防的是误检索,不是蓄意访问。

## 一个集合里有什么

`~/.coffer/knowledge/<collection>/` 就是一棵普通目录树,你可以用日常工具读取、编辑、grep 和备份。集合之下你想怎么嵌套文件夹都行,Coffer 不会赋予这套结构任何自己的含义。

每个文件都是带 frontmatter 的 Markdown,其中有标题和一句话描述。描述不是装饰 —— 浏览目录的人正是靠它来挑文件,所以请把它写成"这里面是什么,我什么时候会想要它"。`README.md` 描述的是它所在的那个文件夹,而不计入该文件夹的文件。

Coffer 只为自己创建两个目录,都以点开头,因此 ripgrep 会跳过、目录遍历也会绕开:

| 路径        | 存放什么                                             |
| ----------- | ---------------------------------------------------- |
| `.raw/`     | 上传文档的原始字节,以便转换得不好时可以重来。          |
| `.history/` | 整理流程替换掉的旧版本。                              |

手工编辑这些内容是允许且预期之内的。这里没有需要挂钩的写入路径,也没有可能忘记执行的重建索引步骤:下一次检索读到的就是磁盘上此刻的文件。

## 写入文件

```bash
coffer knowledge write --in handbook \
  --title "Package manager" \
  --description "Which package manager every repo here uses, and why" \
  --body "Prefer pnpm over npm in all repos."

coffer knowledge ls handbook                       # 目录的一层
coffer knowledge read handbook/package-manager.md
coffer knowledge write --path handbook/package-manager.md --title … --description … --body …
coffer knowledge delete handbook/package-manager.md
```

写入按原文存储 —— 写入时没有 LLM,agent 也从不需要操心归档到哪。`--in` 在某个集合或文件夹下新建文件,`--path` 覆盖已有文件。用任意编辑器把一个 Markdown 文件丢进目录,同样是一种完整的写入方式。

## 上传文档

把任意格式的文件交给 Coffer,它会转换成 Markdown 并作为一个普通知识文件归档,同时把原件留在 `.raw/`。

```bash
coffer knowledge upload ./onboarding.pdf --collection handbook
coffer knowledge upload ./notes.docx --collection handbook --directory onboarding
```

- 转换覆盖 pdf、docx、pptx、xlsx、html 等。超过 20 MB 上限的上传会在任何转换和写入之前被拒绝,不支持的类型也会被指名拒绝。
- 转换出来的文档与你手打的文档没有区别:同样的 frontmatter,同样的审计事件,在树里同样的位置。
- 描述在输入侧可选,在输出侧从不可选。没有配置内部模型连接时,Coffer 会从文档开头的正文中提取一句描述,而不是留下一条空白的目录条目。

## 找东西

三种动作,按你已经知道什么来挑:

```bash
coffer knowledge ls handbook/onboarding      # 浏览:文件夹与文件,带描述
coffer knowledge grep "SO_REUSEADDR"         # 每一条匹配行,形如 path:line
coffer knowledge search "daemon port"        # 命中的文件,连同匹配到的那几行
```

`ls` 每次走目录的一层,让你从标题和描述里挑出**哪个文件**。`grep` 和 `search` 是同一个匹配器、跑在同一批文件上 —— 都是对调用方可见的每个集合执行 ripgrep —— 只是报告方式不同:`grep` 给你每一条匹配行,`search` 每个文件给一条结果,带上该文件的标题、描述以及匹配到的行。当你要的是文件而不是行时,用 `search`。

匹配是字面的:一个正则表达式,区分大小写。请给它一个有辨识度的词或确切短语,而不是一句用你自己的话写成的问题 —— 这里没有排序、没有打分,也没有模式可挑。返回的就是包含你所输入内容的那些文件。

## 整理流程

一个集合会像笔记一样堆积起来:同一件事在两次会话里被写了两遍,某个文件一路长到覆盖了四个主题。这在写入时没有任何不对 —— 正因如此写入才保持"笨"。整理被推迟到**整理流程**(tidy pass)里完成:一次有边界的 agentic 改写,读一个集合里的文件,合并重复、拆开过于庞杂的文件,并给每个文件配上名副其实的标题与描述。

这个流程需要一个内部模型连接;没有配置时它干干净净地什么都不做。一个后台巡检会按周期跑它,并且在运维人员主动打开之前一直是关闭的 —— 无人值守的改写者应该是你打开的东西,而不是你某天发现它在跑。在跨机器的 vault 中,巡检只在其中一台上运行:两台机器合并同一批文件会产出两份不同的文档,而 git 会把它们当作两处新增干净地合并进来。

`.history/` 就是全部的安全网。这个流程用到的每个工具都会在覆盖或撤下一个文件之前先归档它的上一版,因此改写始终可恢复 —— 落地之前没有 diff 需要你批准。

想随时手工跑一趟:

```bash
coffer knowledge organize handbook
```

Web UI 里集合的页面上有一个 **Tidy** 按钮,做的是同一件事。

## CLI

以上全部都在一个分组 `coffer knowledge` 之下:

| 领域 | 命令                                          |
| ---- | --------------------------------------------- |
| 集合 | `collections` · `create`                      |
| 文件 | `ls` · `read` · `write` · `delete` · `upload` |
| 检索 | `grep` · `search`                             |
| 整理 | `organize`                                    |

删除一个集合是资源操作:`coffer resource delete knowledge:<name>`。

## REST 接口

守护进程在 `/api/v1/knowledge` 下提供知识接口。这些路由是*用户*的界面,因此不带 scope —— per-agent 授权管的是 agent 通过 MCP 工具看到什么,而不是 vault 的主人在自己的 UI 里看到什么。

| 路由                                               | 用途                          |
| -------------------------------------------------- | ----------------------------- |
| `GET`/`POST` `/api/v1/knowledge/collections`       | 列出集合;创建一个集合。       |
| `GET` `/api/v1/knowledge/tree?path=…`              | 目录的一层。                   |
| `GET`/`PUT`/`DELETE` `/api/v1/knowledge/file`      | 读取、写入或删除一个文件。     |
| `GET` `/api/v1/knowledge/grep`                     | 匹配到的行。                   |
| `POST` `/api/v1/knowledge/search`                  | 命中的文件,连同匹配到的行。   |
| `POST` `/api/v1/knowledge/upload`                  | 转换一份文档并归档。           |
| `POST` `/api/v1/knowledge/collections/{name}/tidy` | 立刻跑一次整理流程。           |

一次 search 的响应是 `{"results": [{path, title, description, lines: [{line_number, line}]}]}` —— 哪些文件,以及每个文件里匹配到了什么。

删除整个集合走与 kind 无关的资源路由 `DELETE /api/v1/resources/knowledge/{name}` —— 并不存在 `DELETE /api/v1/knowledge/collections/{name}`。

## MCP 工具

每个接入的 MCP 客户端会获得六个内置知识工具。它们都不接受 scope:一次调用覆盖调用方 agent 被授权的每个集合,而这个身份由网关在会话握手时给出。

| 工具             | 作用                                                        |
| ---------------- | ----------------------------------------------------------- |
| `coffer__list`   | 你可读的集合,或某个路径下目录的一层。                        |
| `coffer__grep`   | 匹配某个模式的每一行,带文件与行号。                          |
| `coffer__search` | 命中某个词或短语的文件,每个都带标题、描述和匹配到的行。       |
| `coffer__read`   | 按路径读取一个文件的完整内容。                                |
| `coffer__write`  | 在某个集合或文件夹下新建文件,或覆盖某个路径上的文件。         |
| `coffer__delete` | 删除一个文件,连同它在 `.raw/` 里的原件(如果有)。            |

它们围绕的动作是**先看目录,再 grep**:用 `list` 挑出哪个文件,用 `grep` 找到哪一行,而 `search` 用于你来不及先浏览的时候。它们刻意不是同一个工具的三种模式 —— agent 按自己已知的东西来挑,而不是按一个开关。

agent 在这里既读也写 —— 一个 agent 记下的文件,正是下一个 agent 找到的内容,这也正是把它放进 Coffer、而非某个 agent 自己存储里的意义。

## 在 Web UI 中

知识在 **Resources** 之下是一个页面。`/knowledge` 列出你的集合,含描述与文件数,**New collection** 用于创建;`/knowledge/:collection` 打开单个集合:一棵按层浏览的文件夹树,树上方有一个随输入即时匹配名称的过滤框,旁边渲染选中的文件,还有一个针对该集合的检索框,以及两个按钮 —— **Upload** 把一份文档转换后放进树里,**Tidy** 按需跑一趟整理流程。

[渠道 →](/zh/guide/channels)
