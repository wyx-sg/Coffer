# 知识

**知识**(knowledge)是 Coffer 中唯一一处存放"agent 应该知道的一切"的地方:agent(或你)写下的笔记,以及你摄取进来的文档。两者都以 Markdown 文件形式保存在 `~/.coffer/knowledge/` 下,由同一个 SQLite 索引建索引,并从同一次检索中一并返回。文件是事实来源;索引随时可用 `coffer knowledge reindex` 重建。

Coffer 曾经把这件事拆成两种资源 kind —— 一个只可读的*知识库*,和一个只有 agent 写入的*记忆*。它们从来就不是两样东西。`documents`、`chunks`、FTS5 和 sqlite-vec 从一开始就是共用的;被复制的只是门面。实际使用中知识库几乎是个空壳,记忆本身早就有自己的 `knowledge/` 车道,而这种拆分还逼着每个调用方在挑工具之前先回答"这算记忆还是知识?"—— 一个在调用侧毫无意义的问题。现在只有一种 kind `knowledge`、一个存储根,以及一次覆盖全部内容的检索。

## 作用域

一个知识作用域就是一个名为 `knowledge:<scope>` 的资源。名字本身决定了它的行为:

- **`global`** —— 无论你在哪个仓库都成立的内容。首次写入时自动开通。
- **`project-<ULID>`** —— 限定一个项目,由 agent 工作目录的 git 根解析得到。同样在首次使用时自动开通,你从不手工创建。
- **其他任意名字** —— 你有意创建的集合,例如 `handbook`。它们**不会**自动开通:因为一个名字拼错就悄悄建出一个作用域,比直接报错更糟。

```bash
coffer knowledge create handbook --description "Company onboarding docs"
coffer knowledge list
coffer knowledge describe global
```

检索会横跨一个作用域的两条车道;未指定作用域的 agent 拿到的是当前项目的作用域,并回退到 `global`。

## 一个作用域里有什么

`~/.coffer/knowledge/<scope>/` 就是一棵普通目录树,你可以用日常工具读取、编辑、grep 和备份:

| 路径        | 存放什么                                             |
| ----------- | ---------------------------------------------------- |
| `notes/`    | agent 或你写下的内容。`coffer__write` 直接落在这里。   |
| `docs/`     | 摄取进来的文档,已规范化为 Markdown。                  |
| `.raw/`     | 摄取文件未经改动的原件。隐藏目录,ripgrep 会跳过。     |
| `.history/` | 整理流程替换掉的笔记旧版本。同样隐藏,同样的理由。      |

两条内容车道,外加它们背后的两个隐藏归档。再没有别的了:一条笔记就是一条笔记 —— 无论它是 agent 刚写下的,还是之后被整理流程折叠进了某个主题文档。

手工编辑这些文件是允许且预期之内的 —— Coffer 在检索前会重新扫描这棵树,带外编辑会被纳入。

## 写入笔记

一条笔记就是一个值得跨越本次会话保留下来的事实、决策或偏好。它落在 `notes/`,按原文存储:写入时没有 LLM。

```bash
coffer knowledge remember global "所有仓库优先用 pnpm 而非 npm" --title pkg-manager
coffer knowledge entries global                       # 列出笔记
coffer knowledge get global <entry-id>
coffer knowledge edit-entry global <entry-id> "…"     # 整理
coffer knowledge forget global <entry-id>
```

单条笔记的长度由作用域的 `max_entry_chars` 限制;用 `coffer knowledge configure <scope> --max-entry-chars N` 调整。

## 摄取文档

把任意格式的文件交给 Coffer,它会转换为 Markdown,把结果归入 `docs/`,把原件留在 `.raw/`,分块并建索引。

```bash
coffer knowledge ingest handbook ./onboarding.pdf     # 任意格式 → Markdown
coffer knowledge ingest handbook ./notes.docx
coffer knowledge documents handbook                   # 里面有什么
coffer knowledge read handbook <document-id>
```

- 转换覆盖 pdf、docx、pptx、xlsx、html 等(默认上限 25 MB,创建时可用 `--max-document-mb` 调整)。重新摄取同一来源需要 `--replace`。
- 你手工编辑过的文档归你所有:`coffer knowledge edit` 会写入它,并且它不会被悄悄地从原件重新转换。确实需要重转时用 `coffer knowledge reconvert`。
- Coffer 会记住摄取文件的来处。`coffer knowledge check-sources <scope>` 报告哪些原件在磁盘上变化了,`coffer knowledge update-source <scope> <document-id>` 把新版本拉进来。想让它在后台自动刷新,用 `coffer knowledge configure <scope> --auto-update-sources`。

## 检索

一次检索同时覆盖笔记和文档 —— 这种统一正是全部的意义所在。

```bash
coffer knowledge search handbook "如何重置密码"                # 排序段落
coffer knowledge recall global "用哪个包管理器?"               # 笔记 + 文档一起排序
coffer knowledge grep handbook "TODO"                          # 精确 / 正则,无索引
```

引擎内部有四种模式 —— `grep`(在 Markdown 上做字面/正则)、`keyword`(FTS5 + BM25)、`vector`(sqlite-vec 最近邻)和 `hybrid`(在 keyword + vector 之上做 RRF 融合)。**调用方从不挑选模式。** 由作用域的配置决定,引擎按每次查询自行选择;把模式参数暴露出去,只会让调用方去猜一个内部细节。

向量检索按作用域显式开启:

```bash
coffer knowledge create research --enable-vector
coffer knowledge configure handbook --enable-vector
```

而 embedding 本身是**整个安装配置一次**的,位于 Web UI 的 **Settings → Embedding**。作用域自身不带任何 embedding 字段;它只通过在检索模式里列出 `vector` 来选择加入。未配置 embedding 却要求 vector 的作用域会回退到 keyword,而非报错。

索引只是一份投影,从来不是真相。`coffer knowledge reindex <scope>` 会从磁盘上的 Markdown 重建它。

## 整理流程

笔记会不断累积,同一件事也会被写下两遍。一个周期性的**整理流程**(tidy pass)会合并重复的笔记,并把它们改写成连贯的主题文档 —— 就地进行,仍在 `notes/` 之内。

它有两条触发路径,因为二者覆盖的缺口不同。**空闲触发**:每次写入都会重置同一个合并计时器,静默一段时间之后,发生过变化的作用域被整理 —— 这正是"会话结束后 Coffer 顺手收拾了一下"的那种感觉。**定时触发**:对每个作用域做周期性巡检,守护进程启动时补一趟,之后每隔几小时一趟。巡检能覆盖空闲计时器结构上覆盖不了的情况 —— 你在自己编辑器里改过的文件、计时器还没触发就重启了的守护进程,以及最近没人写过的作用域。

两条路径都会取走作用域的写锁,因此巡检和刚触发的计时器是串行而非竞争的;而在没有配置内部模型时,这个流程什么也不做。真正改动了东西的那一趟会以 `knowledge_tidied` 记入 Coffer 的审计日志;什么也没改动的那一趟不会留下记录。不再有按作用域存放的变更日志文件。

这个流程会在无人值守的情况下改写你和你的 agent 写下的文字。在任何覆盖或合并之前,它会先把上一个版本移入 `.history/`,因此改写始终可恢复 —— 这份归档就是全部的安全网,落地之前没有 diff 需要你批准。

想随时手工跑一趟:

```bash
coffer knowledge organize <scope>            # 立刻跑一次整理流程
coffer knowledge clear <scope>               # 清空一个作用域的全部笔记
```

详情页上的 **Tidy** 按钮做的是同一件事。

## CLI

以上全部都在一个分组 `coffer knowledge` 之下:

| 领域   | 命令                                                                                   |
| ------ | -------------------------------------------------------------------------------------- |
| 作用域 | `list` · `describe` · `create` · `configure` · `label` · `delete`                       |
| 笔记   | `remember` · `entries` · `get` · `edit-entry` · `forget` · `clear` · `recall`           |
| 文档   | `ingest` · `documents` · `read` · `edit` · `reconvert` · `delete-doc` · `reindex`       |
| 检索   | `search` · `grep`                                                                       |
| 整理   | `organize`                                                                              |
| 来源   | `check-sources` · `update-source`                                                       |

## REST 接口

守护进程在 `/api/v1/knowledge` 下提供知识接口,作用域作为路径段,`entries` / `documents` 作为子资源:

| 路由                                             | 用途                          |
| ------------------------------------------------ | ----------------------------- |
| `GET`/`POST` `/api/v1/knowledge`                 | 列出作用域;创建一个集合。     |
| `GET`/`PATCH` `/api/v1/knowledge/{scope}`        | 读取或重新配置一个作用域。     |
| `/api/v1/knowledge/{scope}/entries`              | 笔记 CRUD。                   |
| `/api/v1/knowledge/{scope}/documents`            | 摄取、列出、读取、编辑、删除。 |
| `/api/v1/knowledge/{scope}/search` · `/recall` · `/grep` | 检索。                |
| `/api/v1/knowledge/{scope}/organize`             | 立刻跑一次整理流程。           |
| `/api/v1/knowledge/{scope}/reindex` · `/check-sources` | 维护。                   |

删除整个作用域走与 kind 无关的资源路由 `DELETE /api/v1/resources/knowledge/{name}` —— 并不存在 `DELETE /api/v1/knowledge/{scope}`。

## MCP 工具

每个接入的 MCP 客户端会获得六个内置知识工具。每个都接受可选的 `scope`,默认取当前项目的作用域,并回退到 `global`:

| 工具                 | 作用                                                                   |
| -------------------- | ---------------------------------------------------------------------- |
| `coffer__search`     | 横跨笔记**与**文档返回排序片段。模式由引擎决定。                        |
| `coffer__grep`       | 在作用域的每个 Markdown 文件上做字面或正则匹配,返回文件与行号。         |
| `coffer__read`       | 按 id 读取一项的完整内容 —— 笔记或文档,自动判别。                       |
| `coffer__list`       | 一个作用域里有什么,或 `all=true` 列出每个作用域及其计数。                |
| `coffer__write`      | 归档一条笔记、存一份 Markdown 文档(`filename`),或整体重写某项(`id`)。 |
| `coffer__delete`     | 按 id 删除一条笔记或一个文档,连同文件。                                 |

agent 在这里既读也写 —— 一个 agent 记下的笔记,正是下一个 agent 召回的内容,这也正是把它放进 Coffer、而非某个 agent 自己存储里的意义。

## 在 Web UI 中

知识在 **Resources** 之下是一个页面。`/knowledge` 列出你的作用域,含笔记数、文档数和磁盘占用;`/knowledge/:scope` 打开单个作用域,包含两个标签页 —— **Documents** 和 **Notes** —— 以及树上方一个随输入即时匹配文件名的过滤框。创建集合、把文件拖进去、浏览与整理笔记、跑一次整理流程,都在这里完成。服务端检索留在它该在的地方:agent 用 `coffer__search`,CLI 用 `coffer knowledge recall`。

[渠道 →](/zh/guide/channels)
