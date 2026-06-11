# Quickstart —— Memory（跨 agent 共享记忆）

> English: [quickstart.md](./quickstart.md)

memory 是 Coffer 统一知识底座的 **memory 面**。事实是 markdown 文件（真相源），跨所有 agent 共享 —— 经 MCP 读写、并投影进各 agent 的原生位置。写入时不调 LLM；agent 直接写一条干净的事实。

## 通过 MCP 客户端（主要 surface）

出现五个内置工具（无需 store 引用 —— 作用域由 agent 的工作目录解析）：

- `coffer__recall(query, scope?, top_k?)` —— 搜索 project + global 记忆（默认两者）。
- `coffer__remember(text, scope?, type?)` —— 保存一条事实（默认 `scope=project`）。
- `coffer__update_memory(id, text)` —— 编辑一条事实。
- `coffer__forget(id)` —— 删除一条事实。
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

`recall` 在每次调用时惰性重建事实目录索引，因此另一个 agent（或 Claude 经其 symlink）所做的编辑会即时可见。

## 原生投影（一份记忆，所有 agent）

规范化文件被投影进各 agent 的原生位置，于是你继续用各 agent 自己的记忆 UX：

| Agent       | Project 层                                                | Global 层                           |
| ----------- | --------------------------------------------------------- | ----------------------------------- |
| Claude Code | 目录 **symlink** → `~/.claude/projects/<slug>/memory/`    | 渲染 block 进 `~/.claude/CLAUDE.md` |
| Codex       | 渲染 block 进 `<project>/AGENTS.md`（原生 `memories` 关） | 渲染 block 进 `~/.codex/AGENTS.md`  |

对 Claude，保持 auto-memory **开启** —— 被 symlink 的目录 _就是_ 规范化 store，于是 Claude 自己的编辑成为规范化内容。对 Codex，Coffer 渲染一个 managed block：

```
<!-- coffer:memory:start (managed, do not edit) -->
- [deploy-via-make-release](deploy-via-make-release.md) — This repo deploys via make release.
<!-- coffer:memory:end -->
```

标记之外的内容绝不被触碰；重渲染是幂等的。若你绑定项目时 Claude 的记忆目录已有真实文件，Coffer 先把它们 **合并** 进规范化 store，再把该目录替换为 symlink —— 不覆盖任何内容。

新增一个 agent 就是一个 `AgentMemoryAdapter`；memory 底座不动。

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

# 投影（建立 / 列出 / 移除一个原生绑定）。
coffer memory bind project-01J… my-claude --project-root /abs/path/to/repo
coffer memory projections project-01J…
coffer memory unbind project-01J… my-claude
```

`--json` 在每个读命令上都可用。`--mode` 是 `grep` | `keyword` | `vector`（默认 `keyword`）。`grep` recall 是真实服务的 —— ripgrep 扫事实文件，无索引、无分词器，所以在 FTS5 失效的地方（如 CJK）也能用。未配置 embedding provider 时 `vector` 回退到 `keyword`（带标注）。

## Desktop

1. 侧栏 → **Memory**。页面以表格列出所有记忆 store（global store 加每项目一个 —— 自动置备，所以没有「New store」操作）。
2. 点一行 store 进入它的逐 store 详情页。
3. 事实列表是主视图，顶部有 recall 框（模式选择器默认 keyword）。
4. 点一条事实展开 / 就地编辑 / 删除；**Add fact** 写一个新 markdown 文件（actor=user）。
5. 头部显示事实条数与落盘大小；kebab 菜单提供「Clear scope」。

每次用户写入都会重新生成 `MEMORY.md`、重建索引、对已绑定 agent 重新投影并审计。

## 可选：vector recall

默认检索是 keyword + grep —— 零配置、离线、语言无关。要启用 vector recall，在 store 上配置 embedding provider：

```bash
coffer keychain set embed-key
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

## Limits

- 事实文本：1–8192 字符（每 store 可配置到 32 768）。
- recall `top_k`：1–20（默认 5）。
- 作用域：`global`、`project` 或 `both`（recall 默认）。
