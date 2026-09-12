# Quickstart —— Memory（跨 agent 共享记忆）

> English: [quickstart.md](./quickstart.md)

> **历史文档 —— 2026-09-10。** spec knowledge（Knowledge Base）与 spec knowledge（Memory）
> 于当日合并为统一的 **Knowledge Layer（知识层）**。合并后的模型以
> [`spec.md`](./spec.md) 为准 —— 一个 `knowledge` kind、三种 scope、单一存储根
> `~/.coffer/knowledge/<scope>/`、六个 `coffer__*` 工具。本文档记录的是合并之前
> 的设计；凡出现「memory 面」「`memory` kind」`~/.coffer/memory/` 或
> `/api/v1/memory_stores` 之处，请以 `spec.md` 中合并后的对应物为准。下文的命令与
> 工具名已更新到合并后的 surface，照抄即可运行。目录名 `specs/knowledge/` 同样是
> 历史遗留：它是所有入链与验收审计所依赖的 spec id。

memory 是 Coffer 统一知识底座的 **memory 面**。事实是 markdown 文件（真相源），跨所有 agent 共享 —— **只经 MCP 读写**（Coffer 保留自己的规范化格式，不触碰各 agent 的原生记忆文件）。写入时不调 LLM；agent 直接写一条干净的事实。

## 通过 MCP 客户端（主要 surface）

出现六个内置工具（无需 store 引用 —— 作用域由 agent 的工作目录解析）：

- `coffer__search(query, scope?, top_k?)` —— 一次检索同时覆盖某作用域的 notes 与上传的文档，返回排序结果。
- `coffer__grep(pattern, scope?, max_matches?)` —— 对作用域内每个 Markdown 文件做字面/正则匹配。
- `coffer__read(id, scope?)` —— 按 id 读取整条（note 或文档）全文。
- `coffer__list(scope?, all?, limit?)` —— 浏览单个作用域的内容，或 `all=true` 列出所有作用域的目录。
- `coffer__write(text, title?, description?, filename?, id?, scope?)` —— 写一条 note、存一个文档（`filename`）、或改写已有条目（`id`）。
- `coffer__delete(id, scope?)` —— 删除一条 note 或文档。

写入直接落进该作用域的 `notes/` lane —— 没有 inbox 要排空，也没有交接 lane，所以
任何内容都不必先被归档到某处才能被找到。

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

### 整理 notes lane

一个作用域的 notes 会被定期整理：后台 worker 在 daemon 启动时跑一趟补齐，之后按
间隔执行，合并重复的 note 并把它们重写成主题文档。任何覆盖或合并之前，先把旧版本
复制进隐藏的 `.history/`，因此无人值守的重写始终可以捞回来。未配置内部模型
（设置 → LLM 连接）时这趟整理空转。

手动跑一趟：

```bash
coffer knowledge organize project-01J…    # 对该作用域的 notes/ 跑一趟整理
```

Web UI 对应作用域 header 上的**「整理」**按钮。每趟整理在 Coffer 的审计日志里记一行
—— 不再有 per-scope 的变更记录文件。

## Web UI

1. 侧栏 → **Memory**。页面以表格列出所有作用域（global 加每项目一个 —— 自动置备 —— 以及任意具名集合）。「Notes」列统计各作用域写下了多少条。
2. 点一行进入该作用域的详情页。
3. 详情页是**两个 tab：文档与 Notes**，树上方一个过滤框，输入即按文件名匹配 —— 纯本地，无按钮，不发请求。服务端检索留在它该在的地方：agent 走 `coffer__search`，命令行走 `coffer knowledge recall`。
4. 点一条展开 **只读** 渲染（UI 不在应用内编辑 note 正文）。每个文件及其所在文件夹提供 **在外部编辑器中打开** 与 **在文件管理器中显示**（由本地 daemon 执行的真实 OS 动作）；打开哪个编辑器由全局首选编辑器偏好决定（见 spec ui-shell）。要纠正一条 note，就在自己的编辑器里打开它 —— 下一次检索经 lazy reindex-on-read 拾取改动。
5. header 保留标题、重命名铅笔和项目路径。**「上传」**与**「整理」**是仅有的两个按钮；设置 / 检查源文件 / 重建索引收进溢出菜单。只有真的出现降级文档时才显示警告。

每次写入 —— agent（MCP）、CLI 或 REST —— 都会重建索引并审计；Web UI 只在上传文档或跑一趟整理时写入。不存在派生的 `MEMORY.md`，也没有 `INDEX.md`：`notes/` 与 `docs/` 下的 markdown 文件就是真相源（Files as Truth）。

## 可选：vector recall

默认检索是 keyword + grep —— 零配置、离线、语言无关。embedding 是**全安装级**配置的，不挂在单个作用域上：在 Web UI 里配一次（**设置 → 引擎 → Embedding**，即 `PUT /api/v1/embedding/config`），CLI 没有对应命令。那张卡片就是两个选择器——先选模型提供商，再选它的一个 `embedding` 类型的模型——与它上方的内部引擎卡片同一形状；没有「添加模型」表单，也没有 key 字段。该配置**命名一条连接**——你已经配好的某条 LLM 连接——外加它上面的一个模型；协议、base URL 与 API key 都从那条连接解析，所以 embedding 设置里既没有 `base_url`、也没有 `credential_ref`，更不持有自己的 key。作用域只需在自己的 retrieval modes 里列上 `vector` 来选择加入：

```bash
# key 已经在连接上；先去「模型 provider」加一条连接
coffer knowledge configure project-01J… --enable-vector
```

命名一条不存在的连接、一条 `anthropic` 连接（没有 embedding API）、一条做了策展但其中没有 modality 为 `embedding` 的条目的连接，或该连接并未策展的某个模型，都会以 422 被拒绝并说明是哪一种。完全不做策展的连接表示不限制，你填的模型 id 会被直接采信。`POST /api/v1/embedding/test` 接收 `{connection, model}`，报告向量维度且不持久化任何东西。未命名连接时该配置不生效，检索退化为 keyword/grep。

`coffer knowledge configure <name>` 对作用域配置做 PATCH；其余旋钮有 `--max-entry-chars`、`--chunk-size`、`--chunk-overlap`、`--auto-update-sources/--no-auto-update-sources`。启用 vector 会对作用域里已有的内容重建索引。新建的具名集合天生就带 vector，创建对话框不再询问：一个作用域带哪种索引是实现细节，不该在创建时拿去问用户。

双语内容推荐本地连接（Ollama 配 `bge-m3`）或对中文嵌入好的云端模型。embedding 模型可变 —— 改它会重嵌每一个列了 vector 模式的作用域。未配置 embedding 时，启用了 vector 的作用域会在内部回退到 keyword，不带逐查询标注。

## 文件在哪

```
~/.coffer/
├── coffer.db                                  # SQLite —— 可重建索引（documents、chunks、FTS5、vec、audit）
└── memory/
    ├── global/
    │   ├── notes/                             # 谁写下的内容（coffer__write 落这里）
    │   │   ├── prefers-tabs.md                # 每条 note 一个文件 = 真相
    │   │   └── .history/                      # 整理覆盖前的旧版本（隐藏）
    │   ├── docs/                              # 上传的文档，统一转成 markdown
    │   └── .raw/                              # 上传的原件（隐藏）
    └── projects/<project-ulid>/
        ├── notes/deploy-via-make-release.md
        ├── docs/
        └── .raw/
```

两条 lane：`notes/` 放人或 agent 写下的一切，`docs/` 放上传进来的一切。`.history/`
与 `.raw/` 刻意隐藏 —— ripgrep 会跳过它们，所以 `coffer__grep` 永远不会在正文旁边
又返回一个归档旧版或一份原件。markdown 文件是真相源；`coffer.db` 随时可从它们重建。

## Limits

- 条目文本：1–8192 字符（每个作用域可经 `--max-entry-chars` 配置到 32 768）。
- search `top_k`：1–20（默认 5）。
- 作用域：`global`、某个 `project-<ulid>` 作用域，或具名集合 —— 工具调用时省略则按 agent 的 cwd 解析（不在项目内则回落到 `global`）。
