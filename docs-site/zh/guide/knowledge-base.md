# 知识库

**知识库**(KB)是一个你的 agent 可检索但不可写入的文档存储。你以任意格式添加文件;Coffer 把每个文件在磁盘上规范化为 Markdown —— 这是事实来源 —— 并通过三种检索模式服务回去。Markdown 文件是权威的;SQLite 索引可用 `coffer kb reindex` 重建。

## 创建并填充 KB

```bash
coffer kb create handbook                            # 默认模式:keyword + grep
coffer kb ingest handbook ./onboarding.pdf           # 任意格式 → Markdown
coffer kb ingest handbook ./notes.docx
coffer kb list-docs handbook                         # 里面有什么
```

- 摄取会把 pdf、docx、pptx、xlsx、html 等转换为 Markdown(默认上限 25 MB)。重新摄取同一来源需要 `--replace`。
- 原件保存在 KB 的 `raw/` 文件夹下;你手动编辑过的文档不会再从其原件重新转换。

## 检索

```bash
coffer kb search handbook "如何重置密码"                   # 排序段落(keyword)
coffer kb grep handbook "TODO"                            # 在 Markdown 上做精确 / 正则
coffer kb search handbook "休假政策" --mode vector        # 语义(需要 embedding)
```

- **grep** 是无索引的精确/正则;**keyword**(默认)是 FTS5 BM25 排序;**vector** 是语义最近邻,需显式开启。
- 用 `coffer kb set-embedding handbook --provider … --model …` 启用 vector。未配置 embedding 的 vector 检索会回退到 keyword 而非报错。

## 给你的 agent

每个接入的 MCP 客户端会自动获得只读工具 —— `coffer__list_knowledge_bases`、`coffer__search_knowledge`、`coffer__grep_knowledge` 和 `coffer__read_document`。没有写入工具:agent 读取你的知识,不会改动它。

在应用里,知识库位于 **Resources** 之下 —— 创建一个 KB、把文件拖进去、检索;详情视图展示文档数、chunk 数、磁盘占用,以及已建索引的检索模式。

[记忆 →](/zh/guide/memory)
