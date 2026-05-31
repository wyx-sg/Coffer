# Quickstart —— Knowledge Base Manager

> English: [quickstart.md](./quickstart.md)

006-knowledge-base 落地之后，开发者会怎么端到端地用它。三条路径：CLI、桌面端、通过 MCP 客户端。

## CLI

```bash
# 用默认 embedding 模型创建一个 KB。
coffer kb create design-notes --description "Internal design docs and ADRs"

# 摄入几份文件。
coffer kb ingest design-notes ~/work/notes/architecture.md
coffer kb ingest design-notes ~/work/notes/adr-005.md
coffer kb ingest design-notes ~/papers/raft.pdf

# 摄入一整个目录（逐个文件）。
for f in ~/work/notes/*.md; do
  coffer kb ingest design-notes "$f"
done

# 看一眼。
coffer kb list                              # 列所有 KB
coffer kb describe design-notes             # 文档数 + 磁盘占用 + 配置
coffer kb list-docs design-notes            # 文档行
coffer kb list-docs design-notes --json     # 用于管道

# 检索。
coffer kb search design-notes "how does our retry policy work?"
coffer kb search design-notes "raft leader election" --top-k 3 --json

# 删除单个文档。
coffer kb delete-doc design-notes 8a3f1c2b...     # id 来自 list-docs
# 或按文件名（唯一解出则删，否则失败）。
coffer kb delete-doc design-notes --filename architecture.md

# 删除整个 KB。
coffer kb delete-kb design-notes              # 先确认
coffer kb delete-kb design-notes --yes        # 不交互
```

每个读类命令都支持 `--json`，输出一份完整 JSON 文档，适合 `| jq` / 脚本化。stderr 走人类可读的进度信息。

## 桌面端

1. 启动 Coffer。
2. 侧栏 → **Resources** → **Add** → 选 **Knowledge Base**。
3. 填表单（名称、描述、embedding 模型 —— 默认值已预填）。提交。
4. 新 KB 出现在列表里。点进去。
5. 把文件拖进上传区，或点 **Upload** 选文件。
6. 进度条跑完，文档出现在列表中。
7. 用 KB 详情页顶部的 **Search** 框试搜。
8. 每行右侧有文档操作（删除、复制 id、查看抽取出来的文本）。
9. 通过详情页头部的 kebab 菜单删除整个 KB。

## 通过 MCP 客户端（Claude Code / Cursor / ...）

把 Coffer 配成你的客户端的 MCP server 后，三个新工具会出现：

- `coffer__list_knowledge_bases` —— 列出可用 KB，附 description 与文档数。
- `coffer__search_knowledge_base(kb, query, top_k=5)` —— 排名片段，含 `text`、`document_id`、`filename`、`score`、`position`。
- `coffer__get_document(kb, document_id)` —— 文档的抽取全文 + metadata。

一个示例对话流：

> **User**: "How does our service handle backoff?"
>
> **Agent**（工具调用）：`coffer__search_knowledge_base("design-notes", "service backoff strategy")`
>
> **Agent**（看到片段后）："Per `design-notes/architecture.md`, services use exponential backoff with full jitter, capped at 30 s. See passages 1 & 3 below."

不需要额外装 MCP server —— 这些是 Coffer 自家 MCP 网关端点的内置工具。

## 首次下载模型

默认 embedding 模型 `BAAI/bge-small-en-v1.5` 在首次使用时从 HuggingFace Hub 下载（约 130 MB），缓存到标准位置 `~/.cache/huggingface/`。同一模型的后续 KB 都复用此缓存。

若想预热模型（例如装机阶段触发），跑：

```bash
coffer kb warmup
```

它只下载默认模型，不摄入任何东西。

## 文件落在哪里

```
~/.coffer/
├── coffer.db                  # SQLite —— 控制面（resources、kb_documents、audit、...）
└── kb/
    └── design-notes/
        ├── raw/
        │   ├── 8a3f1c2b....md
        │   ├── 4e7d2901....md
        │   └── a91bcd2e....pdf
        └── index/
            └── ...             # LlamaIndex 持久化索引
```

备份一个 KB = 拷贝它的目录 + 备份 SQLite 行。`coffer daemon backup`（已发布）做 SQLite 快照；`kb/` 目录请纳入文件系统级别的备份策略。

## 默认上限

- 每文档：25 MB。
- 每 KB 约 500 篇文档（软限制；并无硬性 cap，但超过这个量级后检索延迟会涨）。
- 默认开箱支持的格式：`.md`、`.markdown`、`.txt`、`.rst`、`.pdf`，以及常见源码扩展（`.py`、`.js`、`.ts`、`.go`、`.java`、`.rs`、`.c`、`.h`、`.cpp`、`.hpp`、`.sh`、`.yaml`、`.yml`、`.json`）。
- 其他类文本文件：自行转成文本再摄入。
