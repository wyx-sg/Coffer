# 实施计划：知识层

> English: [plan.md](./plan.md)

**Spec**: [./spec.md](./spec.md)
**ADR**: [Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md)
**Status**: Accepted —— 2026-09-12 精简为纯文件

**目录名**: 本 spec 位于 `specs/knowledge/`，这个目录名就是所有入链和
`scripts/audit_acceptance.py` 所依据的 spec id。

## 概要

知识层是一个 **Markdown 文件目录**，而不是架在它们之上的索引。
`~/.coffer/knowledge/<collection>/…` 是唯一真相：不分块、不向量化、不分词、
不对账，所以用户在自己编辑器里改过的文件，在 agent 的下一次调用里就是活的。
一个 **collection** 既是一个顶层文件夹，也是一个由人有意创建的 `knowledge`
Resource，它存在就是为了让框架的 per-agent scope 能授权它。检索是在调用时
遍历目录树生成的目录，加上 ripgrep。五个 MCP 工具：`list`、`grep`、`read`、
`write`、`delete`。

这取代了横跨三层约 10,800 行后端代码、十一张数据库表、两条存储 lane、三种
scope、四种检索模式和一整条任意格式摄入流水线——2026-09-12 的审计发现这套
栈大部分从未执行过。证据与推理在 ADR 里；本文描述的是建成的东西。

## 技术上下文

| 维度 | 取值 |
| --- | --- |
| **语言 / 版本** | Python 3.12+、TypeScript 5.x |
| **本 spec 新增的主要依赖** | `PyYAML`（frontmatter），以及 `PATH` 上的 `ripgrep`。别无其它——没有索引、embedding 或转换类库（FR-080）。 |
| **存储** | `~/.coffer/knowledge/<collection>/` 下的 Markdown 文件。**没有数据库表**（FR-081）：一个 collection 就是 kind 无关的 `resources` 表里的一行，和其它 Resource 一样。 |
| **测试** | 四层模型配合验收标记。不需要假的 embedding provider，因为没有任何东西向量化。 |
| **约束** | 路径构造收拢在一个模块里；隐藏条目不可寻址；任何模块 MUST NOT 引入索引、embedding 或转换类库。 |
| **规模** | 单用户；语料规模保持在目录塞得进 agent 上下文的范围（本机语料 51 篇）。 |

## 章程检查

标准的分层规则。domain 里放的是描述磁盘内容的值对象，没有任何描述数据库行的
东西；application 里放一个服务、五个工具、tidy 流程与 skill 种子；
infrastructure 拥有路径、文件树、frontmatter 与 ripgrep 适配器。PyYAML 只活在
`infrastructure/knowledge/frontmatter.py`，路径构造只活在
`infrastructure/knowledge/paths.py`。

## 项目结构

```text
backend/coffer/
├── domain/knowledge/
│   ├── entry.py                    # CollectionEntry、DirectoryEntry、FileEntry、
│   │                               # CatalogueLevel、KnowledgeFile、GrepMatch/Outcome
│   ├── config.py                   # KnowledgeConfig —— 空的，拒绝未知键
│   └── errors.py                   # CollectionNotFound / Exists、FileNotFound、UnsafeKnowledgePath
├── application/knowledge/
│   ├── kind.py                     # make_knowledge_kind()；supports_scope=True
│   ├── service.py                  # 唯一的服务：collection、目录、读/写/删、grep
│   ├── builtin_tools.py            # 五个 coffer__* 工具
│   ├── tidy.py / tidy_tools.py     # 有界 agentic 流程及其工具面
│   ├── tidy_worker.py              # 间隔 worker，未开启时不跑
│   ├── skill_seed.py               # 把知识 skill 送进 Coffer 自己的 skill 库
│   └── skill_assets/coffer-knowledge/SKILL.md
├── infrastructure/knowledge/
│   ├── paths.py                    # 路径构造与穿越防护的唯一所有者
│   ├── fs.py                       # 文件树：目录遍历、原子读/写/删
│   ├── frontmatter.py              # 唯一 import PyYAML 的模块
│   ├── naming.py                   # slugify + unique_name —— 路径就是身份
│   └── legacy_migration.py         # migration 0066 先跑的那次单向磁盘重写
└── surfaces/
    ├── http/knowledge/             # routes.py、schemas.py、tidy_state.py
    ├── http/knowledge_wiring.py    # 组装：设置 app.state.kinds["knowledge"]
    ├── http/tidy_wiring.py         # 从 internal_engine_config 读 auto_tidy_enabled
    └── cli/knowledge_cmd.py        # `coffer knowledge …` —— 一个模块，已无可拆分的东西
```

```text
frontend/src/
├── pages/KnowledgePage.tsx         # collection 列表
└── kinds/knowledge/
    ├── KnowledgeDetailPage.tsx     # 一棵树，没有 lane tab
    ├── KnowledgeTreeLevel.tsx      # 一次一层，与目录一致
    ├── KnowledgePreviewBody.tsx    # 只读渲染；没有应用内编辑器
    └── useKnowledge.ts             # 全部 query + mutation，层级 key 挂在 ["knowledge"] 下
```

## 接口面

- **MCP —— 五个工具**：`list`、`grep`、`read`、`write`、`delete`。没有一个接受
  `scope`、`mode`、`top_k` 或 `cwd`；一次调用覆盖该会话 agent 身份被授权的每一个
  collection（FR-012、FR-024）。
- **HTTP —— `/api/v1/knowledge` 下八条路由**：列出与创建 collection、
  `GET /tree`、`GET`/`PUT`/`DELETE /file`、`GET /grep`，以及
  `POST /collections/{name}/tidy`。删除 collection 走
  `DELETE /api/v1/resources/knowledge/{name}`——collection 的生命周期就是
  Resource 的生命周期。见 [`contracts/api.openapi.yaml`](./contracts/api.openapi.yaml)。
- **CLI —— 八条命令**：`collections`、`create`、`ls`、`read`、`write`、
  `delete`、`grep`、`organize`。
- **UI**：一棵树、只读预览、对文件及其所在文件夹提供「在外部编辑器打开」与
  「在文件管理器中显示」（[Daemon Proxies File Actions](../../docs/decisions/daemon-proxies-os-file-actions.md)）。
- **投递**：`coffer-knowledge` skill，开机时种进 Coffer 自己的 skill 库，再经
  既有的 skill 通道投递（spec [skill-manager](../skill-manager/spec.md)）。
  幂等——每次开机重新导入打包的那个文件夹，所以对素材的修改会随下一次 daemon
  启动送达，删掉了 skill 的用户也会拿回来。没有 hook、没有会话注入，也不写入
  任何 agent 自己的记忆文件（FR-042）。

## 整理（tidy）

针对单个 collection 的一趟有界 agentic 流程，由 internal-engine 连接驱动，其
工具面就是同样那五个操作。它在任何覆盖之前把文件旧版本复制进 `.history/`，
而背后没有索引，所以事后没有任何东西要对账。没有配置内部连接时，它是干净的
no-op（`status: no_model`）。

`TidyWorker` 的形状照抄 `RetentionWorker`——开机稍后跑一趟补齐，之后按间隔执行，
失败的一趟只记日志不杀死循环——但它会查一个安装级开关：`internal_engine_config`
上的 `auto_tidy_enabled`，**默认 false**。这个默认值本身就是要点，而不是出于
谨慎：这趟流程会在没有 diff 可审的情况下改写人与 agent 共同管理的文件，所以一个
无人值守的改写器应该是操作者主动打开的，而绝不该是他某天发现它在跑（FR-051）。

## 迁移

一条 revision，`0066_knowledge_is_plain_files`，而**顺序就是全部要点**。文档的
标题只活在 `documents.title` 里，所以 `upgrade` 先跑磁盘重写——读取它即将销毁的
那些行——然后才删掉十一张表，每个 drop 都加了守卫，使缺少其中任何一张的数据库
仍能升级（FR-070、FR-071）。`downgrade` 直接抛错：ULID 文件名与 `.raw/` 副本无法
重建，且任何地方都不留兼容垫片。细节见 [`data-model.md`](./data-model.md)。

## 风险与已接受的取舍

| 风险 | 立场 |
| --- | --- |
| **没有语义匹配。** `grep` 只匹配字面文本；概念性召回现在依赖 agent 读目录并自行判断相关性。 | 接受，但有天花板：只要目录塞得进上下文它就成立——每条约 40 tokens，所以几百篇很从容，几千篇不行。越过之后的答案是一个为那个需求而建的真正语义栈，而不是这里移除的那一套，那一套从未被配置过。 |
| **tidy 会在没有审阅环节的情况下改写共同管理的产物。** 落盘前没有任何东西做 diff。 | `.history/` 就是全部安全网，而且 worker 默认关闭，让人在自己决定之前一直留在环内。 |
| **排序成了 agent 的问题。** 在大语料上做宽泛 grep 会返回很多命中。 | 目录是让这件事仍然可处理的原因，这给文件名和 `description` 压上了真实的分量——`description` 之所以必填正是为此。 |
| **迁移是破坏性且单向的。** | 刻意如此。标题在删表**之前**被写进文件名与 frontmatter；没有第二次机会，也没有垫片。 |
| **per-agent 授权是约定，不是安全边界。** 握有 shell 工具的 agent 能读根目录下任何文件。 | 每个 surface 都如实这么说（FR-014）。真正的隔离需要独立仓库或文件系统权限，不在范围内。 |
| **投递一个 skill 是否真能让 agent 伸手够这一层，尚未被证明。** 工具描述已被证明做不到。 | 这是一个有证据支撑的假设——今天有十五个 `coffer-*` skill 被原生发现——而且验证成本很低：调用日志本来就记录每一次知识调用，一周的日常工作就能回答它，不需要任何新埋点。 |

## 范围之外

- 任何派生索引：分块、FTS5、向量、embedding、混合融合、重建索引、读时惰性重建。
- 任何摄入界面：上传、格式转换、转换器注册表、`.raw/` 出处、外部源追踪、
  再转换锁。
- 任何派生边界：由 cwd 解析的 scope、自动开通、`project-<ULID>` 命名、git 根解析。
- 应用内编辑器。UI 负责渲染；编辑交给用户自己的编辑器。
- 读取时的 rerank、HyDE、multi-query 或 LLM 综述——综述由 agent 做。
- 文件系统监听器。没有任何东西是派生的，也就没有任何东西需要失效。
- 多机收敛（章程约束；导出、导入与单向备份由 vault-export-import spec 覆盖）。
