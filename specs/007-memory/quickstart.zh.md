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

```bash
# 在某作用域加一条事实（actor=user）。project = 当前 git 项目。
coffer memory add --scope project "API base path is /api/v2."
coffer memory add --scope global "Prefers tabs over spaces."

# 列出、召回。
coffer memory list --scope project
coffer memory list --scope global --json
coffer memory recall "deployment" --scope both
coffer memory recall "deployment" --mode keyword --top-k 3 --json

# 编辑、遗忘、清空一个作用域（store 保留）。
coffer memory edit <id> "API base path is /api/v3."
coffer memory forget <id>
coffer memory clear --scope project --yes

# Per-store 度量。
coffer memory describe --scope project
```

`--json` 在每个读命令上都可用。`--mode` 是 `grep` | `keyword` | `vector`（默认 `keyword`）；未配置 embedding provider 时 `vector` 回退到 `keyword`。

## Desktop

1. 侧栏 → **Resources** → 打开项目（或 **Global**）记忆 store。
2. 标签页在 **Global** 与 **Project** 作用域间切换。
3. 事实列表是主视图，顶部有 recall 框（模式选择器默认 keyword）。
4. 点一条事实展开 / 就地编辑 / 删除；**Add fact** 写一个新 markdown 文件（actor=user）。
5. 头部显示事实条数与落盘大小；kebab 菜单提供「Clear scope」。

每次用户写入都会重新生成 `MEMORY.md`、重建索引、对已绑定 agent 重新投影并审计。

## 可选：vector recall

默认检索是 keyword + grep —— 零配置、离线、语言无关。要启用 vector recall，在 store 上配置 embedding provider：

```bash
coffer keychain set embed-key sk-...
coffer memory configure --scope project \
    --enable-vector \
    --embedding-provider openai \
    --embedding-model text-embedding-3-small \
    --embedding-credential-ref embed-key
```

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
