# ADR-022 — 跨 Agent Transcript 历史：用于搜索与浏览的本地派生索引

> English: [ADR-022-cross-agent-transcript-history.md](./ADR-022-cross-agent-transcript-history.md)

- **状态：** 已接受
- **Spec:** [007-memory](../../specs/007-memory/spec.md)（扩展 —— 不分配新 spec 编号），经 [ADR-021](./ADR-021-chat-as-vault-console.md) 在 [008-agent-chat](../../specs/008-agent-chat/spec.md) 中呈现
- **关联：** [ADR-020](./ADR-020-transcript-distillation.md)（transcript 蒸馏 —— 部分推翻其 Alternative B）、[ADR-012](./ADR-012-files-as-truth-sqlite-retrieval.md)（files-as-truth + SQLite 检索）、[ADR-016](./ADR-016-multi-machine-sync.md)（多机同步）、Spec 004（只读工作区不变量）

## 背景

[ADR-020](./ADR-020-transcript-distillation.md) 把 agent transcript 蒸馏成
**memory 事实** —— 对耐久知识的有损提取（"我们学到了什么"）。它有意拒绝了：(A) 一
个被同步的 transcript _kind_、(B) 浏览/继续功能、(C) 写回 agent 的 session store。

用户仍然想在一个地方**找到并重看跨所有 agent 的真实对话** —— 像管理 memory 那样
管理聊天记录：从多个 agent 摄入 → 一个 hub → 搜索与召回。蒸馏回答不了"给我看那次
我们尝试方案 X 的会话"；只有对话本身能回答。

ADR-020 Alternative A 的反对意见，针对的明确是"把**原始 transcript 当成被同步的
真相**来持久化"：它们的体量、其中携带的密钥 / 工具 payload / 文件内容、git 同步
膨胀、以及 files-as-truth 模型。**这些反对意见并不适用于一个本地、可重建、指向
磁盘文件的派生索引。** ADR-020 Alternative B（浏览）当初被缓，是因为缺乏生态传播
力和落脚处，**而非因为它错了**；[ADR-021](./ADR-021-chat-as-vault-console.md) 的
Vault Console 现在给了它一个落脚处。

## 决策

新增一个**跨 agent transcript 历史索引**：在 Coffer 已经读取的、原地存放的
`.jsonl` transcript（`~/.claude/projects/`、`~/.codex/sessions/`）之上建一个
**本地、可重建**的索引，在 Vault Console 中呈现为跨所有 agent（以及本地
网页/IM 会话）的统一**搜索**和只读**浏览**。

- **复用 distill 切片的 reader 与 scrubber。** 索引复用 `transcript_reader.py`
  （`parse_claude_code` / `parse_codex`）和 `scrub.py`。只把**脱敏后的自然语言
  turn** 索引进现有的 SQLite `documents` / FTS 基底
  （[ADR-012](./ADR-012-files-as-truth-sqlite-retrieval.md)），用一个**仅索引用
  的判别值** —— **不是**被同步的 resource kind。原始 transcript 字节永不拷进
  files-as-truth，也永不进 git 同步。
- **浏览按需读取。** 一个会话通过只读读取其文件来渲染；显示脱敏后的 turn。未来
  若提供未脱敏回放，则直接读用户自己的文件，永不持久化。
- **搜索复用现有检索原语**（FTS5 BM25 默认；vector 可选），在脱敏文本上按
  agent / project / 时间过滤。
- **`continue`/`resume` 保持在范围外**（缓做，同 ADR-020 B）。会话上已存的
  resumable session id 让它将来若有需求可以接上。

### 两层：本地原始历史 vs 同步的蒸馏/交接

让"只在本地"在跨机时也不丢价值的分层：

- **第一层 —— 原始历史（本地，永不同步）。** 即本 ADR 的 transcript 索引。它回答
  "给我看/搜索**这台**机器上的真实对话"。它是可重建的本地派生物，永不经 Spec 010
  的 git 介质传播。原始对话本来就是你不希望撑大 git、不希望泄露密钥的东西。
- **第二层 —— 蒸馏产物（同步）。** 跨 agent、跨机带走的是历史的**凝练**，而非历史
  本身：今天是 ADR-020 的 **memory 事实**，下一步自然是一个会话级的**摘要 /
  交接**产物 —— 一份紧凑、脱敏的"我们做到哪了 / 下一步是什么"，让另一个 agent 或
  另一台机器能接上这条线。它们小、可评审，且已经被 Spec 007 + Spec 010 治理，所以
  同步它们满足 ADR-020 Alternative A 的每一条反对意见。

所以跨机价值（一份能在别处接上的交接）搭在同步的蒸馏层上；体量大、含密钥的原始层
留在本地、可重建。交接/摘要产物自身的设计另起一份笔记（它建在 ADR-020 的蒸馏管线
之上）；本 ADR 只钉死**分层边界**：原始历史永不同步，蒸馏摘要才同步。

### 架构

- 扩展 `distill` 切片（或新增一个兄弟 `history` 切片），通过现有 reader/scrubber
  **port** 复用；新增的 indexer 只写 SQLite 索引。跨 kind 的 wiring 留在组合根
  （import-linter Contract 5）；`application/*` 不 import `infrastructure.*`。
- 索引是**派生产物**：`coffer history reindex`（CLI）和/或后台 watcher 从磁盘文件
  重建它。删掉索引不丢任何耐久数据。

### 不变量

- **本地、永不同步。** 原始历史索引（第一层）是机器本地的，永不经 Spec 010 的
  git 介质传播 —— 只有蒸馏的第二层（ADR-020 memory 事实，以及将来的摘要/交接
  产物）才同步。（宪法 I：不引入新的被同步真相；该索引是可重建的本地派生物，与
  FTS 索引本身同性质。）
- **不引入新 resource kind。** 该索引是 `documents` 表内部的一个判别值，而非带有
  UI/API/同步/契约面的 hub 资源 —— 这正是 ADR-020 Alternative A 所依赖的区分点。
- **保持 files-as-truth。** agent 自己的 `.jsonl` 是真相；Coffer 只读、绝不写
  （Spec 004）。浏览是只读。
- **入索引前脱敏。** ADR-020 的 scrubber 在任何文本进入索引前运行；
  `tool_use`/`tool_result` 块、文件内容、命令输出在解析时丢弃，与蒸馏一致。
- **不持久化工具调用内容。** roadmap 的 non-goal（"工具调用参数或结果持久化"）
  成立：只索引脱敏后的自然语言 turn。

## 被考虑的替代方案

### A —— 把 transcript 持久化为被同步的 `conversation` kind

（= ADR-020 Alternative A。）**仍然拒绝**，理由相同：体量、密钥、git 同步膨胀、
files-as-truth。

### B —— 只保留蒸馏，不做浏览/搜索（ADR-020 现状）

**现在拒绝。** 蒸馏是有损的，回答"我们学到了什么"，而非"给我看那次对话"。一个可
搜索的历史回答的是另一个、真实的问题，而 Vault Console
（[ADR-021](./ADR-021-chat-as-vault-console.md)）给了它一个 ADR-020 缓做浏览时
还不存在的落脚处。

### C —— 把脱敏后的 transcript 拷进 Coffer 自有文件再索引

**拒绝。** 重复内容、有与 agent 真实历史漂移的风险、并重新引入存储/密钥顾虑。
**原地**索引避免了这一切；agent 的文件仍是唯一真相源。

### D —— 现在就做 `continue`/`resume`

**缓做。** 这是一个附加的会话恢复问题，生态传播力仍低；将来可经会话上已存的
resumable session id 接上。

## 后果

- 在 agent transcript 之上建一个本地索引并保持新鲜（CLI 重建 + 可选 watcher）；
  它可重建、永不同步。
- Vault Console 获得**跨 agent 的历史搜索 + 只读浏览**界面 —— 这是把 Coffer 的
  chat 界面与任何原生客户端区分开的能力，也是
  [ADR-021](./ADR-021-chat-as-vault-console.md) 的具体回报。
- ADR-020 Alternative B 被**部分推翻**：搜索/浏览现在纳入；`continue`/`resume`
  保持缓做。
- 解析脆弱性沿袭自 ADR-020（`.jsonl` 格式无文档；防御式适配器跳过坏记录、绝不
  抛错）。
- 重建成本与索引体量随 transcript 体量增长；索引可裁剪、可重建，因此成本有界且
  保持本地。
