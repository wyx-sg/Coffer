# 数据模型 — 知识层

> English: [data-model.md](./data-model.md)

这一层的状态就是一个目录。本文描述磁盘上的东西——目录树、frontmatter 契约、
命名规则——外加一个 collection 仍然占用的那一行数据库记录，以及各 surface
用来作答的内存值对象。权威是 [`spec.md`](./spec.md) 与
[Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md)。

## 没有 schema

**知识层不拥有任何表**（FR-081、SC-004）。Markdown 文件是唯一真相，没有任何
东西从它们派生出来：没有 `documents` 行、没有 chunk、没有全文索引、没有
embedding——因此没有内容哈希要比对，没有重建索引，也没有任何形式的对账
（FR-001）。

一个 collection 在数据库里的唯一存在，和其它每个 Resource 一样：kind 无关的
`resources` 表里的一行。那一行承载 collection 的名字、它的 `enabled` 标志以及
它的 per-agent `scope`，不承载任何关于它内容的东西。

## 磁盘布局

```text
~/.coffer/knowledge/
├── shopee/                         # 一个 collection = 一个顶层文件夹 = 一个 Resource
│   ├── README.md                   # 首段 = 这个 collection 的描述
│   ├── account/                    # 人自己的归档方式；系统不赋予它任何含义
│   │   └── session-ownership.md
│   ├── gateway-routing.md
│   └── .history/                   # tidy 覆盖掉的旧版本（隐藏）
└── coffer/
    ├── README.md
    └── release-process.md
```

- `~/.coffer/knowledge/` 是根目录；测试里由 `$COFFER_KNOWLEDGE_ROOT` 覆盖。
  路径构造只存在于一个模块 `infrastructure/knowledge/paths.py`（FR-006）。
- 一个 **collection** 既是一个顶层子目录，*也是*一个 `knowledge` Resource。
  它由人有意创建；读取、写入或 agent 的工作目录都不会开通一个（FR-010）。
  没有 `global`、没有 `project-<ULID>`、没有 git 根解析、也没有 scope 到项目根
  的映射表（FR-011）。
- collection 内部怎么嵌套是人自己的事。子目录是可选的、可任意深，对系统毫无
  含义，系统既不要求也不创建（FR-004）。
- **点开头的条目对目录和 grep 都不可见**（FR-005）。`.history/` 是 Coffer 自己
  写的唯一一个（FR-052）。隐藏片段会被路径守卫**拒绝**而不只是跳过：把
  `.history/` 里的旧版本交回去，等于用活文件已经替换掉的内容作答。

### `README.md`

collection 在自己目录下的 `README.md` 里描述自己；目录对一个 collection 的
一句话描述就是该文件的首段，没有 README 时为空（FR-013）。它绝不存在数据库里，
因此不会和在文件夹里翻看的人读到的东西漂移。
`POST /api/v1/knowledge/collections` 在给了 `description` 时会写一份。

## 文件

每个文件都是带 `---` 围栏 YAML frontmatter 块的 Markdown，只由
`infrastructure/knowledge/frontmatter.py` 读写（PyYAML 唯一落脚处）。

```markdown
---
title: Session ownership
description: Which service owns a login session, and what reads it.
actor: agent
created_at: '2026-09-12T04:18:33Z'
updated_at: '2026-09-12T04:18:33Z'
---

Login state is owned by `account.session`.
```

| Key | 类型 | 说明 |
| --- | --- | --- |
| `title` | `str` | 人类可读。创建时也是文件名的来源。 |
| `description` | `str` | **必填**（FR-003）。没有带排序的索引之后，目录就是检索界面，一个不描述自己的文件等于找不到。 |
| `actor` | `agent` \| `user` | 谁最后写的。来自写入时的 `X-Coffer-Actor` 头，或工具自己的 actor。 |
| `created_at` | ISO-8601 `str` | 替换时保留，所以文件即使只靠自己也留得住自己的历史。 |
| `updated_at` | ISO-8601 `str` | 每次写入都更新。 |

**且仅此而已**（FR-003）。没有 `id`——路径就是身份（FR-002）——也没有 `lane`、
`source_path`、`source_sha256`、`source_format`、`source_mode`、`converter`、
`embed_status` 或 `content_sha256`：它们描述的机制都已不存在。

frontmatter 解析是退化而不是抛错：没有围栏、或围栏里 YAML 不合法的文件，得到
空 frontmatter 加正文，这样一个手改出多余冒号的文件不会弄崩整趟目录遍历。

### 命名

文件名是标题的可读 slug，而不是不透明的 id，因为没有「id → 标题」的索引之后，
文件名正是人在 Finder 里读到、agent 在 grep 结果里读到的东西（FR-002）。规则
归 `infrastructure/knowledge/naming.py`：

- NFKC 归一化、转小写、把空白 / `_` / `/` / `\` 折成 `-`、丢掉 `A-Za-z0-9-` 与
  CJK 之外的一切、把连续 `-` 折成一个、截到 80 字符。**保留 CJK，绝不转写**——
  罗马化出来的名字双方都认不出。结果为空时用 `untitled`。
- 只有在 `<slug>.md` 已被占用时，`unique_name` 才追加 `-2`、`-3`、…。

### 穿越防护

每个会成为路径片段的名字都过 `paths.check_segment`（FR-006）：非空、不是全点、
不以点开头、且匹配 `[A-Za-z0-9._\- ]` 或 CJK。违反即 `UnsafeKnowledgePath`
（`KNOWLEDGE_PATH_UNSAFE`，HTTP 400）。写入是原子的——同目录临时文件再 `replace`。

## 值对象（`backend/coffer/domain/knowledge/entry.py`）

它们是**一个答案的形状，绝不是一行记录的形状**：目录的某一层是在调用时遍历目录、
读取 frontmatter 生成的（FR-020），所以它们一个都不落盘，也一个都不会陈旧。

| 类型 | 字段 | 是什么 |
| --- | --- | --- |
| `CollectionEntry` | `name`、`description`、`file_count` | 目录顶层的一个 collection。`description` 取 README 首段；`file_count` 递归计数，排除隐藏条目。 |
| `DirectoryEntry` | `path`、`name`、`file_count` | 被列出那一层里的一个子目录。`path` 相对于根目录——把它传回去就能下钻。 |
| `FileEntry` | `path`、`title`、`description`、`actor`、`updated_at` | 目录里呈现的一个文件：足以在不读正文的情况下判断相关性。 |
| `CatalogueLevel` | `path`、`directories`、`files` | **一层**，绝不是整棵树（FR-021）。 |
| `KnowledgeFile` | 五个 frontmatter 字段 + `path`、`body`、`file_path`、`folder_path` | 一个完整文件。两个绝对路径正是 UI 提供「在外部编辑器打开」与「在文件管理器中显示」所需（FR-062）。 |
| `GrepMatch` | `path`、`line_number`、`line` | 一条 ripgrep 命中。 |
| `GrepOutcome` | `matches`、`truncated` | 一次有界运行；`truncated` 表示 `max_matches` 是否截断了它（FR-022）。 |

常量：`ACTOR_AGENT = "agent"`、`ACTOR_USER = "user"`。

`surfaces/http/knowledge/schemas.py` 里的 HTTP wire 模型与它们一一对应。这种
镜像是刻意的而非冗余：domain 类型描述磁盘上有什么，wire 模型描述客户端被承诺
什么，于是从 wire 上拿掉一个字段绝不等于对这一层本身隐藏它。

## `knowledge` Resource

`make_knowledge_kind()` 声明 `supports_scope=True`——per-agent 授权正是一个
collection 之所以是 Resource 的全部理由（FR-012）。agent 看见、grep、读、写的
恰好是为它激活的那些 collection，不存在把已授权 collection 排除在默认之外的规则。

`KnowledgeConfig`（`domain/knowledge/config.py`）是**空的，且拒绝未知键**。一个
collection 完全没有设置：没有检索模式、没有 chunk 大小、没有条目长度上限、没有
embedding 字段、没有自动更新开关、没有显示标签（FR-081）。过去逐 scope 配置的
每一样，配置的都是已不存在的机制。

执行点只在 MCP 工具面。同时握有 shell 或文件读取工具的 agent 可以直接读
`~/.coffer/knowledge/` 下的任何文件：scope 防的是误召回，不是有意访问，系统
如实这么讲，而不是暗示一种它并不提供的隔离（FR-014）。

## 错误（`domain/knowledge/errors.py`）

失败模式就是一个目录的失败模式。

| 类 | code | HTTP |
| --- | --- | --- |
| `CollectionNotFound` | `KNOWLEDGE_COLLECTION_NOT_FOUND` | 404 |
| `CollectionExists` | `KNOWLEDGE_COLLECTION_EXISTS` | 409 |
| `KnowledgeFileNotFound` | `KNOWLEDGE_FILE_NOT_FOUND` | 404 |
| `UnsafeKnowledgePath` | `KNOWLEDGE_PATH_UNSAFE` | 400 |
| `KnowledgeError`（基类） | `KNOWLEDGE_ERROR` | 400 |

## 审计与调用记录

不变，仍然落库，因为它们不是知识——它们是 Coffer 自己的簿记。一次内置工具调用
记一行 `mcp_invocations`（工具、谁、耗时、结果——绝不含参数、绝不含内容）；写入
或删除额外记一条以 agent 为 actor 的 `audit_log` 事件（FR-041）。

## 那一个安装级的 tidy 设置

这一层唯一的设置并不属于这一层：`auto_tidy_enabled` 是 `internal_engine_config`
上的一个布尔列，**默认 false**（FR-051）。它只管后台 worker 是否按间隔跑 tidy；
手动触发从不查它。

## migration 0066 做了什么

`20260912_0066_knowledge_is_plain_files.py`（FR-070、FR-071）。**顺序就是全部
要点**：文档的标题只活在 `documents.title` 里，所以磁盘重写**先**跑，读取它即将
销毁的那些行。

重写把 `<scope>/{notes,docs}/<ULID>.md` 变成 `<collection>/<标题的-slug>.md`，
恰好带上上面那五个 frontmatter 键；`global` 落进 `shopee`，每个 `project-<ULID>`
scope 落进 `coffer`；`.raw/`——它那 50 个文件与 lane 里的对应文件逐字节相同——
被删除；被清空的 scope 目录被移除；每个 collection 拿到一份 `README.md`；
`knowledge` 的 Resource 行从 scope 重新指向 collection。

然后删掉十一张表，每个 drop 都加了守卫，使缺少其中任何一张的数据库仍能升级：
`documents`、`chunks`、六张 `documents_fts*`（虚拟表的 drop 会带走它的影子表；
后面显式的影子 drop 是为影子已被孤立的那种情况准备的）、`embedding_config`、
`knowledge_scope_labels` 与 `knowledge_scope_project_roots`。

`downgrade` 直接抛错。这条 migration 按设计就是单向的——ULID 文件名与 `.raw/`
副本无法重建——而且**任何地方都不留兼容垫片**。重写是幂等的：再跑一次找不到
lane 目录，什么也不做。
