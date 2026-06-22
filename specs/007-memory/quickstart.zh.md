# Quickstart —— Memory（跨 agent 共享记忆）

> English: [quickstart.md](./quickstart.md)

memory 是 Coffer 统一知识底座的 **memory 面**。事实是 markdown 文件（真相源），跨所有 agent 共享 —— **只经 MCP 读写**（Coffer 保留自己的规范化格式，不触碰各 agent 的原生记忆文件）。写入时不调 LLM；agent 直接写一条干净的事实。

## 通过 MCP 客户端（主要 surface）

出现五个内置工具（无需 store 引用 —— 作用域由 agent 的工作目录解析）：

- `coffer__recall(query, scope?, mode?, top_k?)` —— 搜索 project + global 记忆（默认两者；`mode` 为 `grep` | `keyword` | `vector`）。
- `coffer__remember(text, scope?)` —— 保存一条事实（默认 `scope=project`）。
- `coffer__set_handoff(body)` —— 保存当前工作现场（按 project + 分支）。
- `coffer__resume()` —— 返回当前 project + 分支已保存的工作现场。
- `coffer__list_memory(scope?)` —— 浏览。

```text
# 在一个 git 项目内，agent 保存一条项目事实：
coffer__remember("This repo deploys via `make release`, never git push --tags.",
                 scope="project", type="project")

# 一条到处可用的个人偏好：
coffer__remember("Prefers tabs over spaces.", scope="global", type="user")

# 之后 —— 也许是另一个 agent —— 跨两个作用域召回：
coffer__recall("how do we deploy?")
```

`recall` 在每次调用时惰性重建事实目录索引，因此另一个 agent（经 MCP）、用户在 Coffer UI、或直接在磁盘上所做的编辑会即时可见。

## CLI

CLI 用**名字**以位置参数寻址 store —— `global` 或 `project-<ulid>`（store 自动置备；`coffer memory list` 显示已有哪些）。没有 `--scope` 这类 flag。

```bash
# 看有哪些 store（一个 global + 每项目一个），再查看其中一个。
coffer memory list
coffer memory describe global

# 向某 store 加一条事实（actor=user）。
coffer memory add project-01J… "API base path is /api/v2."
coffer memory add global "Prefers tabs over spaces."

# 列出事实 / 取单条。
coffer memory facts project-01J…
coffer memory facts global --json
coffer memory get global <fact-id>

# 从某 store 召回。
coffer memory recall project-01J… "deployment"
coffer memory recall project-01J… "deployment" --mode keyword --top-k 3 --json
coffer memory recall global "部署流程" --mode grep        # 对事实文件做精确/regex 匹配 —— 对 CJK 极好用

# 编辑、删除、清空一个 store（store 保留）。
coffer memory edit global <fact-id> "API base path is /api/v3."
coffer memory delete global <fact-id>
coffer memory clear project-01J… --yes
```

`--json` 在每个读命令上都可用。`--mode` 是 `grep` | `keyword` | `vector`（默认 `keyword`）。`grep` recall 是真实服务的 —— ripgrep 扫事实文件，无索引、无分词器，所以在 FTS5 失效的地方（如 CJK）也能用。未配置 embedding provider 时 `vector` 回退到 `keyword`（带标注）。

## Desktop

1. 侧栏 → **Memory**。页面以表格列出所有记忆 store（global store 加每项目一个 —— 自动置备，所以没有「New store」操作）。
2. 点一行 store 进入它的逐 store 详情页。
3. 事实列表是主视图，顶部有 recall 框（模式选择器默认 keyword）。
4. 点一条事实展开 **只读** 渲染（UI 不在应用内编辑事实内容）。每条事实及其所在文件夹提供 **在外部编辑器中打开** 与 **在文件管理器中显示**（桌面与 web 上都是真实 OS 动作——web 上经 daemon）；打开哪个编辑器由全局首选编辑器偏好决定（见 spec 002-ui-shell）。要纠正一条事实，就在自己的编辑器里打开它 —— 下一次 recall 经 lazy reindex-on-read 拾取改动。
5. 头部显示事实条数与落盘大小；kebab 菜单提供「Clear scope」。要添加或删除事实，用 `coffer memory add` / `coffer memory delete`（或 REST API）。

每次写入 —— agent（MCP）、CLI 或 REST —— 都会重新生成 `MEMORY.md`、重建索引并审计；桌面 UI 本身是只读视图。

## 可选：vector recall

默认检索是 keyword + grep —— 零配置、离线、语言无关。要启用 vector recall，在 store 上配置 embedding provider：

```bash
coffer credentials set embed-key
coffer memory configure project-01J… \
    --enable-vector \
    --provider openai \
    --model text-embedding-3-small \
    --dimensions 1536 \
    --credential-ref embed-key
```

`coffer memory configure <name>` 对 store 配置做 PATCH；其余旋钮有 `--base-url`、`--default-mode`、`--max-fact-chars`。启用 vector 会对 store 里已有的事实重新 embedding。

双语内容推荐本地 provider（`fastembed` 配 `bge-m3`）或对中文嵌入好的云端模型。embedding 模型可变 —— 改它会重嵌整个 store。若请求 vector 但未配置，recall 返回 keyword 结果并标注此次回退。

## 文件在哪

```
~/.coffer/
├── coffer.db                              # SQLite —— 可重建索引（documents、chunks、FTS5、vec、audit）
└── memory/
    ├── global/
    │   ├── MEMORY.md                      # 重新生成的索引
    │   └── prefers-tabs.md                # 每条事实文件 = 真相
    └── projects/<project-ulid>/
        ├── MEMORY.md
        └── deploy-via-make-release.md
```

markdown 文件是真相源；`coffer.db` 随时可从它们重建。

## 对话记录提炼（Spec 007 扩展）

agent 的本地聊天记录包含了工程决策、项目约定、踩过的坑以及未了结的待办事项，但这些内容从未被显式记录为事实条目。对话记录提炼 (transcript distillation) 会读取这些会话内容，抹除其中的 secret 与工具调用负载，然后通过一次 LLM 调用提炼出持久化洞察，并将它们写入项目作用域的 memory store —— 从而立即可通过 `recall` 访问，并随 Spec 010 跨机同步。

原始记录**绝不落盘**。只有提炼后的事实文本才会进入 store。

### 第一步 —— 用 `--dry-run` 预览

```bash
# 列出某个已注册 agent 的可用会话。
coffer transcript list my-claude

# 预览将会写入的内容，但不实际提交。
coffer transcript distill my-claude \
    --session 01JXYZ… \
    --project /path/to/my-project \
    --dry-run
```

示例输出：

```
Insights (3):
  [decision]    Use make release for tagging
    Always tag and push via `make release`; never `git push --tags` directly — the Makefile target is atomic.
  [gotcha]      DB migration divergence between branches
    Switching branches with divergent Alembic lineages breaks the shared coffer.db; delete the DB and let the daemon recreate it.
  [convention]  Bilingual docs rule applies only to human-readable prose
    Tool-scaffolding templates (.speckit etc.) are exempt from the bilingual .zh.md requirement.
(dry-run: nothing was written to memory)
```

### 第二步 —— 正式运行

```bash
coffer transcript distill my-claude \
    --session 01JXYZ… \
    --project /path/to/my-project
```

示例输出：

```
Insights (3):
  [decision]   Use make release for tagging
    …
  [gotcha]     DB migration divergence between branches
    …
  [convention] Bilingual docs rule applies only to human-readable prose
    …
Created 3 fact(s):
  01JABC…
  01JDEF…
  01JGHI…
```

每条事实写入项目 store 时携带 `actor="agent"` 以及设置为对话记录 session id 的 `origin_session_id`。

### 第三步 —— 用 `recall` 查看提炼出的事实

```bash
# 从项目 store 召回（用 `coffer memory list` 查看真实的 store 名）。
coffer memory recall project-01J… "deployment tagging"
```

同样的事实也可以通过 MCP 从任何已注册的 agent 访问：

```text
coffer__recall("deployment tagging", scope="project")
```

### 选项

| Flag             | 说明                                               |
| ---------------- | -------------------------------------------------- |
| `--session ID`   | 提炼指定 session；省略则提炼该项目的所有 session。 |
| `--project PATH` | 只处理 project path 匹配 PATH 的 session。         |
| `--model ID`     | 覆盖用于提炼的 LLM 模型。                          |
| `--dry-run`      | 预览洞察，不写入任何事实。                         |

## Limits

- 事实文本：1–8192 字符（每 store 可配置到 32 768）。
- recall `top_k`：1–20（默认 5）。
- 作用域：`global`、`project` 或 `both`（recall 默认）。
