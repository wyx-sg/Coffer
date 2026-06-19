# ADR-030：逐项目知识库文档 scope 与可恢复软删除

> English: [ADR-030-per-project-kb-scope-and-soft-delete.md](ADR-030-per-project-kb-scope-and-soft-delete.md)

**状态**：已回退（2026-06-20）—— 见下方回退说明
**日期**：2026-06-19 · 2026-06-20 回退
**决策者**：Yuxing Wu
**关联**：spec `006-knowledge-base`、`007-memory`；完成 [ADR-028（文档共管）](ADR-028-knowledge-base-documents-co-managed.md)；构建于 [ADR-012（文件即真相）](ADR-012-files-as-truth-sqlite-retrieval.md) 之上；与 [ADR-026（memory 经 MCP）](ADR-026-memory-via-mcp-not-native-projection.md) 同源；属于完成统一知识重设计的切片（知识 = 记忆 + 文档 × 全局 / 项目）

> **⚠️ 2026-06-20 已回退。** 本 ADR 的决定在落地一天后被撤回。它当初要支撑的统一
> **知识**界面,被发现混淆了两种不同的工作流——用户上传的文档(知识库)与智能体写入的
> 记忆(记忆)——因此 UI 被拆回两个独立界面。统一视图一旦消失,逐项目**文档** scope
> 与文档软删除存在的唯一理由(两者都只是为了在那个合并视图里让文档对齐记忆的项目轴)便
> 不再成立,于是一并回退。系统回到
> [ADR-028](ADR-028-knowledge-base-documents-co-managed.md) 基线:知识库文档在**全局
> scope** 下共管、采用**硬删除**。**记忆自身的全局 / 逐项目 scope 不受影响**——它早于
> 本 ADR(见 [ADR-026](ADR-026-memory-via-mcp-not-native-projection.md))。原始决定原文
> 保留于下方备查。

## 背景

[ADR-028](ADR-028-knowledge-base-documents-co-managed.md) 交付了**全局 scope 下**的
共管核心，并明确把两块内容推迟"到后续在统一知识 UI 中呈现它们的切片，以保持本次改动
可评审、避免堆出没有 UI 的后端状态"：

- **逐项目文档 scope**——文档的 全局 / 项目 轴。
- **可恢复软删除（回收站 / 恢复）**——"需要自己的 UI 才有意义"。

本 ADR 在那个统一知识切片落地时做出这两项决策。

有两个事实构成它的前提：

1. **memory（007）本就有两层 scope**：一个全局 store（`WORKSPACE_GLOBAL` 哨兵
   `project_id`）和一个按**项目 ULID** 索引的逐项目 store，该 ULID 由 agent 的
   git-root 路径确定性派生（[ADR-026](ADR-026-memory-via-mcp-not-native-projection.md)
   时期）。KB 这一面则在**每一行**上都带哨兵。统一知识模型——知识 = 记忆（notes）+
   文档（documents）× 全局 / 项目——需要文档也能逐项目存在，使一个项目的 notes 与文档
   在同一 scope 下并存。
2. **删除曾是硬删除。** ADR-028 把它作为临时措施接受，由 F01 审计痕迹与逐文档锁保护。
   随着统一 UI 给了文档一个真正的管理界面，可恢复回收站现在既可行也是预期之内的。

## 决策

### 1. 逐项目文档 scope

- 一份 KB 文档带一个**真实的 `project_id`**：全局文档用 `WORKSPACE_GLOBAL` 哨兵，
  逐项目文档用一个**项目 ULID**（git-root 路径的确定性 Crockford-base32——与 memory
  所用的*同一个* `project_ulid`）。`project_id` 本就是 `documents` 上的一列；本次为
  KB 这一面真正填充它，而不再总是盖上哨兵。
- **磁盘布局以向后兼容的方式新增一个逐项目子树。** 全局文档仍在
  `knowledge/<kb>/docs/` + `raw/`（已有文档不被搬动）；逐项目文档位于
  `knowledge/<kb>/projects/<ulid>/docs/` + `raw/`。这种不对称是刻意的——它镜像
  memory 的 `global/` + `projects/<ulid>/` 切分，同时不搬动任何已存储的全局文档。
- **重新上传标识按 `(kb, project_id)` 划界。** 同一文件名在全局与某项目，或跨两个项目，
  都是独立文档。（`find_by_filename` 本就接受 `project_id`。）
- **list、read、grep 以及 keyword / vector 检索都按解析出的 `project_id` 划界。**
  grep 天然受限于 scope（它遍历该 scope 的 `docs/` 目录）；keyword / vector 在
  `documents.project_id` 上过滤。
- **scope 解析在边界完成，而非在 service 内。** REST ingest 端点接受一个显式的
  `project_id`（统一 UI 发送用户正在查看的 scope）；agent MCP 写入从 agent 上报的
  `cwd`（git-root → `project_ulid`）解析项目，在没有 git root 或没有 `cwd` 时回退到
  全局。git-root → ULID 的辅助函数（`scope_fs`）从 `infrastructure/memory/` 移入共享的
  `infrastructure/knowledge/` 底座，使两面共用一份实现，且不引入被禁止的跨 kind 导入。

### 2. 可恢复软删除（回收站 / 恢复）

- `documents` 新增一个**可空的 `deleted_at`**。删除一份*活动*文档是一次**软删除**：
  它移除 `docs/<id>.md` 与索引行（chunks / FTS5 / vec），但**保留** `raw/<id>.<ext>`
  与置了 `deleted_at` 的 `documents` 行。该文档从一切活动读取中消失——list、get、
  search、grep、metrics 以及重新上传匹配——它们都过滤 `deleted_at IS NULL`。
- **恢复**从保留的 `raw/` 原件重新转换文档，重新生成 `docs/<id>.md`，重新索引，并清空
  `deleted_at`。`source_mode` 重置为 `converted`：被恢复的文档是从原件新鲜转换的。删除前
  对正文的任何**编辑都不会被找回**——软删除移除了编辑过的 markdown，只保留原始 `raw/`
  （与 ADR-028 的"只保留最新一份原件——无版本历史"一致）。
- **删除一份已在回收站的文档会将其永久清除**（移除 `raw/` + 该行）。因此对活动文档
  "delete"是把它丢进回收站；对回收站中文档"delete"则是显式的永久清除。**KB 级**删除
  仍然硬移除一切，包括回收站。
- **锁（FR-021）仍然护卫**：被锁文档不能被软删除、清除，也不能被恢复覆盖。
- **reindex-on-read 不得复活墓碑**，且该护卫是双向的：因为软删除移除了 `docs/<id>.md`，
  扫描的*重建*分支（文件在、无行 → 重构）永远看不到该文件；又因为*剪枝*分支（行在、文件
  没了 → 硬删除）**只在活动行上**操作（`list_documents` 过滤 `deleted_at IS NULL`），它
  永远不会硬删除墓碑。保留的 `raw/` 刻意不被扫描——只有 `docs/` 是 markdown 真相——所以
  它无法触发重建。
- **审计**：软删除记录 `KB_DOCUMENT_DELETED`（沿用既有事件，现在含义为"移入回收站"）；
  恢复记录 `KB_DOCUMENT_RESTORED`；永久清除记录 `KB_DOCUMENT_PURGED`。

### 为什么共享 repo 的过滤对 memory 是安全的

`documents` 表及其 repo 与 memory 这一面共享。给 repo 读取加上 `deleted_at IS NULL`
对 memory 行是一个**no-op**：memory 从不设置 `deleted_at`（memory 的 `forget` 是对
fact 文件 + 其行的硬删除），所以它的行始终满足该谓词，行为不变。

## 后果

**正面**

- 完成统一知识模型：一个项目的 notes（memory）与文档（KB）现在同处一条 全局 / 项目 轴
  之下，被一起呈现。
- agent 的删除变得**可恢复**（软删除）——对共管文档而言，这是比 ADR-028 硬删除严格更安全
  的默认行为，而清除仍保持显式。
- 既有的全局语料库在磁盘上原封不动；逐项目文档是增量的。

**负面 / 取舍**

- **恢复会丢失正文编辑**（它从 `raw/` 重新转换）。接受：无版本历史（ADR-028），而一份
  策展/编辑过的文档应当被**锁定**，锁会完全阻止其删除。
- **回收站在清除或删除 KB 之前是无界的**（无自动过期）。对单用户本地工具而言接受；清除是
  显式的，删除 KB 会清空它。
- `search` / `grep` 新增了 `project_id` 作用域，而 FTS / vec 索引仍按
  `(kind, resource_name)` 索引。**grep** 按各作用域的 `docs/` 目录定界；**keyword**
  搜索在既有的 FTS↔`documents` JOIN 上过滤（`AND d.project_id = :pid`），因此 `LIMIT k`
  直接返回作用域内真正的前 k 条——无需多取。**vector** 搜索是例外：sqlite-vec 的 KNN
  没有 `project_id`，所以先多取 KNN、在 JOIN 处过滤、再截断到 `top_k`——其召回受多取上限
  约束；可接受，因为向量是可选项且语料库很小（SC-002 ≤ 50 份文档）。
- 文档的 scope 在 **ingest 时固定**；在全局与某项目之间"移动"一份文档是一次重新 ingest，
  而非翻转一个 metadata。为保持磁盘真相与稳定 id 完整而接受。

## 备选方案

**逐项目 = 每个项目一个独立的 KB 资源**（镜像 memory 为每个项目造一个
`project-<ulid>` Resource 的做法）。否决：它把一个语料库碎裂成 N 个资源，破坏"一个 KB、
多个 scope 视图"。在一个 KB 资源内按 `project_id` 列划界，可保持单一语料库带一条 scope 轴。

**软删除保留 `docs/<id>.md`**（把它移入一个 `trash/` 子树）以保住编辑。本切片否决：它令
reindex-on-read 复杂化（扫描得学会跳过一个 trash 子树）并重新引入类似版本历史的状态；从
保留的 `raw/` 重新转换更简单，也让"`docs/` 中的文件是活动真相"保持诚实。

**用 `status` / 布尔列做墓碑**而非 `deleted_at` 时间戳。否决：`deleted_at` 同时充当回收站
排序键以及恢复 / 审计 UX 的"何时"；布尔承载更少却无任何节省。

**不做清除——删除 KB 是唯一的清理途径。** 否决：一个没有逐文档清除的无界回收站是个隐患。
让"删除一份回收站中的文档 = 清除"是最不意外的入口，且无需新增动词。
