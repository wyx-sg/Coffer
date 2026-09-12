# 快速上手 — 知识层

> English: [quickstart.md](./quickstart.md)

知识就是 `~/.coffer/knowledge/<collection>/` 下的一个 Markdown 文件目录。agent
靠读一份即时生成的目录再 grep 找到需要的东西，就像它导航一个代码库；你靠打开
文件夹找到。没有索引，所以你们中一方写下的东西，另一方立刻就能看到。见
[`spec.md`](./spec.md) 与
[Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md)。

## 先建一个 collection

没有任何东西会自动开通。一个 **collection** 既是一个顶层文件夹，*也是*一个
`knowledge` Resource——你有意创建它，而这正是它能被逐 agent 授权的前提。

```bash
coffer knowledge create shopee -d "Internal systems — services, data plane, the chains between them."
coffer knowledge collections
```

`create` 会建目录、注册 Resource，并把 `--description` 写进这个 collection 的
`README.md`。目录对一个 collection 的一句话描述永远取自该 README 的首段，所以
以后改描述就是改那个文件。

只有被授权的 agent 才看得见一个 collection：

```bash
coffer scope set knowledge:shopee --agents claude_code
coffer scope show knowledge:shopee
coffer scope clear knowledge:shopee          # 恢复为所有 agent
```

删除 collection 走 Resource 框架，而不是某条知识路由——生命周期、审计与级联
都与其它资源完全一致：

```bash
coffer resource delete knowledge:shopee
```

## 经 MCP 客户端（主要界面）

五个内置工具。没有 scope 参数、没有模式、没有 `top_k`：一次调用覆盖该 agent
被授权的每一个 collection。

- `coffer__list(path?)` —— 目录，**一次一层**。不带参数时列出你可读的每个
  collection，各带描述与文件数。带路径时返回该目录的直接子目录与文件，每个
  文件带 `title` 和 `description`。
- `coffer__grep(pattern, collection?, max_matches?)` —— 对文件跑 ripgrep，
  字面或正则，返回文件、行号与命中行。不分词，所以中文和别的文本一样能命中。
- `coffer__read(path)` —— 完整读一个文件，外加它的绝对路径。
- `coffer__write(title, description, body, directory | path)` —— 在
  `directory` 下创建文件（文件名由 `title` slug 化而来），或替换 `path` 处的
  文件。二者恰选其一。
- `coffer__delete(path)` —— 从磁盘删除一个文件。

**没有 `coffer__search`**：背后没有带排序的索引，它只会是 `grep` 的第二个名字。

动作是「先看目录再 grep」——下钻决定*读哪个文件*，grep 定位*哪一行*：

```text
coffer__list()                              # → shopee（48 篇）、coffer（4 篇）
coffer__list(path="shopee")                 # → account/、gateway-routing.md、…
coffer__list(path="shopee/account")         # → 标题 + 描述
coffer__read(path="shopee/account/session-ownership.md")

coffer__grep(pattern="account.session")     # 已经知道字面串的时候
coffer__grep(pattern="部署流程", collection="shopee")

coffer__write(title="Release process",
              description="How this repo cuts a release, and what not to do.",
              body="Deploys via `make release`, never `git push --tags`.",
              directory="coffer")
```

agent 之所以知道这一层存在，是因为 Coffer 通过它常规的 skill 通道投递了
`coffer-knowledge` skill——没有 hook、没有会话注入，也不往 agent 自己的记忆
文件里写任何东西。

## CLI

八条命令，全都是 daemon 之上的薄 HTTP 外壳。路径相对于知识根目录。

```bash
# 浏览。
coffer knowledge collections                       # 每个 collection
coffer knowledge ls shopee                         # 一层：文件夹 + 文件
coffer knowledge ls shopee/account --json
coffer knowledge read shopee/account/session-ownership.md

# 直接搜文件本身。没有索引；这就是搜索。
coffer knowledge grep "account.session"
coffer knowledge grep "部署流程" --in shopee        # 中文很好用——不需要分词器
coffer knowledge grep "make release" --json

# 写入。--in（在这里新建）与 --path（替换这个）恰选其一。
coffer knowledge write -t "Release process" \
  -d "How this repo cuts a release, and what not to do." \
  -b "Deploys via \`make release\`, never \`git push --tags\`." \
  --in coffer
coffer knowledge write -t "Release process" -d "…" -b "…" --path coffer/release-process.md

# 删一个文件。
coffer knowledge delete coffer/release-process.md
```

`--json` 在 `collections`、`ls`、`read`、`grep` 上都可用。

## 用你自己的工具整理

文件系统就是摄入界面。从 Finder 把一篇 Markdown 丢进某个 collection、在编辑器里
改掉一行错的、删掉一篇过时的——每一次改动对下一次调用都是即时生效的，不需要
导入、不需要重建索引、也没有任何东西要对账，因为文件**就是**知识。

你手工添加的文件应当带上 Coffer 写的那套 frontmatter，否则它在目录里的标题与
描述会是空的：

```markdown
---
title: Session ownership
description: Which service owns a login session, and what reads it.
actor: user
created_at: '2026-09-12T04:18:33Z'
updated_at: '2026-09-12T04:18:33Z'
---

Login state is owned by `account.session`.
```

没有上传端点，也没有格式转换。一份 PDF 在有人把它变成 Markdown 之前，不是知识。

## 整理（tidy）

针对单个 collection 的一趟有界 agentic 流程：它合并重复内容、把它们重写成连贯
的文档，动手之前先把每个旧版本复制进隐藏的 `.history/`。没有配置内部模型
（设置 → LLM 连接）时，它是干净的 no-op。

```bash
coffer knowledge organize shopee
```

Web UI 里对应的是 **Tidy** 按钮。后台 worker 也可以按间隔跑这趟流程，但它
**默认关闭**且是安装级的——请到设置 → 引擎里有意打开，因为它会在没有 diff
可审的情况下改写你和你的 agent 共同管理的文件。每一趟都记进 Coffer 的审计日志。

## Web UI

1. 侧边栏 → **知识**。一棵树，没有 tab：先是各个 collection，再是你在里面
   嵌套的任何东西。
2. 点一个文件看到**只读**渲染。UI 没有编辑器；文件及其所在文件夹各自提供
   **在外部编辑器打开**与**在文件管理器中显示**（由本机 daemon 执行的真实
   系统操作；打开哪个编辑器取决于全局首选编辑器设置，见 spec ui-shell）。
   你的修改立刻生效——没有任何东西需要对账。

## 文件在哪

```text
~/.coffer/
├── coffer.db                       # 完全没有知识相关的表——每个 collection 只有 resources 里的一行
└── knowledge/
    ├── shopee/
    │   ├── README.md               # 首段 = 这个 collection 的描述
    │   ├── account/
    │   │   └── session-ownership.md
    │   ├── gateway-routing.md
    │   └── .history/               # tidy 替换掉的旧版本（隐藏）
    └── coffer/
        ├── README.md
        └── release-process.md
```

`.history/` 以点开头是刻意的：ripgrep 跳过隐藏条目，所以归档的旧版本绝不会跟
活文件一起返回。

## 上限

- `grep` 命中数：1–500，默认 200。响应会标记 `truncated`。
- 文件名：标题的 slug，最长 80 字符，CJK 原样保留；重名时追加 `-2`、`-3`、…。
- 目录规模：没有硬上限，但设计假设目录塞得进 agent 的上下文——到几百篇文件
  都很从容。
