# Quickstart —— Memory（跨 agent 共享记忆）

> English: [quickstart.md](./quickstart.md)

> **历史文档 —— 2026-09-10。** Knowledge Base 与 Memory 两份规范于当日合并为统一的
> **Knowledge Layer（知识层）**。合并后的模型以
> [`spec.md`](./spec.md) 为准 —— 一个 `knowledge` kind、三种 scope、单一存储根
> `~/.coffer/knowledge/<scope>/`、八个 `coffer__*` 工具。本文档记录的是合并之前
> 的设计；凡出现「memory 面」「`memory` kind」`~/.coffer/memory/` 或
> `/api/v1/memory_stores` 之处，请以 `spec.md` 中合并后的对应物为准。下文的命令与
> 工具名已更新到合并后的 surface，照抄即可运行。目录名 `specs/knowledge/` 同样是
> 历史遗留：它是所有入链与验收审计所依赖的 spec id。

memory 是 Coffer 统一知识底座的 **memory 面**。事实是 markdown 文件（真相源），跨所有 agent 共享 —— **只经 MCP 读写**（Coffer 保留自己的规范化格式，不触碰各 agent 的原生记忆文件）。写入时不调 LLM；agent 直接写一条干净的事实。

## 通过 MCP 客户端（主要 surface）

出现八个内置工具（无需 store 引用 —— 作用域由 agent 的工作目录解析）：

- `coffer__search(query, scope?, top_k?)` —— 一次检索同时覆盖某作用域里写下的条目与已 ingest 的文档，返回排序结果。
- `coffer__grep(pattern, scope?, max_matches?)` —— 对作用域内每个 Markdown 文件做字面/正则匹配。
- `coffer__read(id, scope?)` —— 按 id 读取整条（条目或文档）全文。
- `coffer__list(scope?, all?, limit?)` —— 浏览单个作用域的内容，或 `all=true` 列出所有作用域的目录。
- `coffer__write(text, title?, description?, filename?, id?, scope?)` —— 写一条条目、存一个文档（`filename`）、或改写已有条目（`id`）。
- `coffer__delete(id, scope?)` —— 删除一条条目或文档。
- `coffer__set_handoff(body)` —— 保存当前工作现场（按 project + 分支）。
- `coffer__resume()` —— 返回当前 project + 分支已保存的工作现场。

```text
# 在一个 git 项目内，agent 记下一条项目事实：
coffer__write(text="This repo deploys via `make release`, never git push --tags.",
              title="Release process")

# 一条到处可用的个人偏好：
coffer__write(text="Prefers tabs over spaces.", title="Indentation", scope="global")

# 之后 —— 也许是另一个 agent —— 来检索：
coffer__search(query="how do we deploy?")
```

`search` 在每次调用时惰性重建该作用域目录的索引，因此另一个 agent（经 MCP）、用户在 Coffer UI、或直接在磁盘上所做的编辑会即时可见。

## CLI

CLI 用**名字**以位置参数寻址作用域 —— `global`、`project-<ulid>` 或具名集合（`global` 与每项目作用域自动置备；`coffer knowledge list` 显示已有哪些）。没有 `--scope` 这类 flag。

```bash
# 看有哪些作用域（一个 global + 每项目一个 + 任意具名集合），再查看其中一个。
coffer knowledge list
coffer knowledge describe global

# 向某作用域写一条条目（actor=user）。
coffer knowledge remember project-01J… "API base path is /api/v2."
coffer knowledge remember global "Prefers tabs over spaces."

# 列出条目 / 取单条。
coffer knowledge entries project-01J…
coffer knowledge entries global --json
coffer knowledge get global <entry-id>

# 从某作用域检索。
coffer knowledge recall project-01J… "deployment"
coffer knowledge recall project-01J… "deployment" --top-k 3 --json
coffer knowledge search project-01J… "deployment"     # 段落检索，文档也覆盖
coffer knowledge grep global "部署流程"                 # 对 Markdown 文件做精确/regex 匹配 —— 对 CJK 极好用

# 编辑、删除、清空一个作用域（作用域保留）。
coffer knowledge edit-entry global <entry-id> "API base path is /api/v3."
coffer knowledge forget global <entry-id>
coffer knowledge clear project-01J… --yes
```

`--json` 在上面每个读命令上都可用。没有 `--mode` flag：检索模式是引擎内部细节（[Retrieval Mode Is Internal](../../docs/decisions/retrieval-mode-is-internal.zh.md)）—— 引擎自行解析该作用域的策略（作用域列了 vector 就是 `hybrid`，否则 `keyword`），未配置 embedding provider 时内部静默回退到 `keyword`，不带逐查询标注。`coffer knowledge grep` 是真实服务的 —— ripgrep 扫 Markdown 文件，无索引、无分词器，所以在 FTS5 失效的地方（如 CJK）也能用。

### 合并重复的项目作用域（AI 辅助）

多机同步可能给**同一个**项目留下两个 `project-<ulid>` 作用域（没有 origin remote、可携带身份之前铸的作用域、remote 改名）。先扫描，再合并确认的一对——增量式、任何内容都不会丢，被合并掉的身份此后仍会解析到幸存者（FR-056–059）：

```bash
coffer knowledge merge-scan               # 确定性 + 内部引擎两层提议
coffer knowledge merge project-01H… project-01J…          # source → target
coffer knowledge merge project-01H… project-01J… --no-organize   # 跳过合并后的 reorg
```

Web UI 对应 **记忆 → 查找重复库（AI）**。未配置内部引擎（设置 → LLM 连接）时，扫描仍会报告能靠 git remote 一致证明的库对。

## Web UI

1. 侧栏 → **Memory**。页面以表格列出所有记忆 store（global store 加每项目一个 —— 自动置备，所以没有「New store」操作）。
2. 点一行 store 进入它的逐 store 详情页。
3. 条目列表是主视图，顶部有 recall 框。没有模式选择器——检索 mode 是引擎内部细节（ADR: retrieval-mode-is-internal）。
4. 点一条事实展开 **只读** 渲染（UI 不在应用内编辑事实内容）。每条事实及其所在文件夹提供 **在外部编辑器中打开** 与 **在文件管理器中显示**（由本地 daemon 执行的真实 OS 动作）；打开哪个编辑器由全局首选编辑器偏好决定（见 spec ui-shell）。要纠正一条事实，就在自己的编辑器里打开它 —— 下一次 recall 经 lazy reindex-on-read 拾取改动。
5. 头部显示事实条数与落盘大小；kebab 菜单提供「Clear scope」。要添加或删除事实，用 `coffer knowledge remember` / `coffer knowledge forget`（或 REST API）。

每次写入 —— agent（MCP）、CLI 或 REST —— 都会重建索引并审计；Web UI 本身是只读视图。不存在派生的 `MEMORY.md`：`knowledge/` 下的 markdown 文件就是事实源（ADR: files-as-truth-sqlite-retrieval）。

## 可选：vector recall

默认检索是 keyword + grep —— 零配置、离线、语言无关。embedding provider 是**全安装级**的，不挂在单个作用域上：在 Web UI 里配一次（**模型 provider → Embedding**，即 `PUT /api/v1/embedding/config`），CLI 没有对应命令。作用域只需在自己的 retrieval modes 里列上 `vector` 来选择加入：

```bash
coffer credentials set embed-key      # embedding 配置引用的那把 key
coffer knowledge configure project-01J… --enable-vector
```

`coffer knowledge configure <name>` 对作用域配置做 PATCH；其余旋钮有 `--max-entry-chars`、`--chunk-size`、`--chunk-overlap`、`--auto-update-sources/--no-auto-update-sources`。启用 vector 会对作用域里已有的内容重建索引。新建具名集合时也可以直接带上：`coffer knowledge create <name> --enable-vector`。

双语内容推荐本地 provider（`fastembed` 配 `bge-m3`）或对中文嵌入好的云端模型。embedding 模型可变 —— 改它会重嵌每一个列了 vector 模式的作用域。未配置 embedding 时，启用了 vector 的作用域会在内部回退到 keyword，不带逐查询标注。

## 文件在哪

```
~/.coffer/
├── coffer.db                              # SQLite —— 可重建索引（documents、chunks、FTS5、vec、audit）
└── memory/
    ├── global/
    │   └── prefers-tabs.md                # 每条事实文件 = 真相
    └── projects/<project-ulid>/
        └── deploy-via-make-release.md
```

markdown 文件是真相源；`coffer.db` 随时可从它们重建。

## Limits

- 条目文本：1–8192 字符（每个作用域可经 `--max-entry-chars` 配置到 32 768）。
- search `top_k`：1–20（默认 5）。
- 作用域：`global`、某个 `project-<ulid>` 作用域，或具名集合 —— 工具调用时省略则按 agent 的 cwd 解析（不在项目内则回落到 `global`）。
