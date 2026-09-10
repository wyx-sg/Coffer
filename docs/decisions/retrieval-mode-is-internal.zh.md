# 检索 mode 是引擎内部细节；外部界面只暴露「查询→答案」。

**Status**: Accepted
**Date**: 2026-06-21（2026-09-10 修订；见修订历史）
**Spec**: [specs/knowledge/spec.md](../../specs/knowledge/spec.md)

## 背景

检索基底（ADR：files-as-truth-sqlite-retrieval）支持四种模式 —— `grep`、`keyword`、`vector` 与
`hybrid`（keyword + vector 的 RRF 融合）。最初 KB 与记忆的界面把这套分类暴露到外部：REST
`search`/`recall` 接受 `mode` 参数，并回显解析出的 `mode` 和一个 `fallback`
字段，MCP 工具带 `mode?` 参数，人用 web 面板在搜索框旁还放了一个 grep
框。外部传入非法 mode 会得到 `400 SEARCH_MODE_INVALID`。

Coffer 是一个**极简的个人工具**，不是企业级搜索产品。让单个用户在每次查询时
在「keyword」「vector」「hybrid」之间选择是摩擦，不是功能：正确的策略是语料的属性
（是否配置了 embedding？），不是问题的属性。引擎已经能从每个 scope
的配置解析出合理默认 —— 启用 vector 时为 `hybrid`，否则为 `keyword`。把 mode
旋钮暴露到外部，会迫使每一个外部调用方（REST 客户端、CLI、经 MCP 的 agent、web
UI）去理解并重述一个引擎本可自行做出的决定，还把一个降级细节（`fallback`）泄漏进每一次查询响应
—— 而该状况指标界面已经报告了（`documents_degraded`）。grep 是另一种形态的能力
（精确/正则的文件匹配，而非排序 passage），属于 agent/脚本，而非点「搜索」的人。

## 决策

外部检索界面呈现**一次查询 → 一个答案**。具体而言：

- **从所有外部输入移除 `mode`**：REST 的 search 请求、CLI 的 search 命令，以及
  MCP 检索工具（`coffer__search(query, scope?, top_k?)`）。调用方永远不选模式。
- **从 search 响应移除 `mode` 和 `fallback`**：响应只携带排序后的结果。不再逐查询
  回显解析出的 mode，也没有 `fallback` 标志。
- **模式保持在引擎/服务内部**：引擎与检索服务仍解析并运行某个模式（启用 vector 时为
  `hybrid`，否则为 `keyword`）；每个 scope 的 `retrieval_modes` / `default_mode`
  仍是内部配置。`RetrievalMode` 枚举和内部 domain 的 `SearchResult` 类型不变。
- **grep 仍是独立的内部/agent 工具**：`coffer__grep` 与 `/grep`
  端点为 agent 和脚本保留，但 grep 入口**从人用 web 面板移除**。
- **每个 scope 唯一的检索旋钮是 vector 开/关**（由该 scope 是否列出 vector 模式决定）。
  启用 vector 会把解析出的默认翻为 `hybrid`；这就是面向用户的全部检索选择。

## 后果

- **更简单的外部契约。** 一个搜索输入（`query`、`top_k?`）和一个答案（排序
  passage / hits）。没有可逐查询配错的东西。
- **`SEARCH_MODE_INVALID` 移除。** 既无外部 mode，就不存在非法 mode 请求，因此
  search 操作去掉其 `400`，`SearchModeInvalid` domain 错误也不再适用。（即便代码无害地保留该符号，也不会被任何外部路径引用。）
- **降级通过指标体现，而非响应标志。** 当解析出的策略需要向量但无可用 embedding
  provider 时，引擎在内部回退到 keyword 并仍返回结果 —— 绝不报错。「vector 不可用」由
  `documents_degraded` 指标报告，不逐查询回显。
- **保留引擎灵活性。** 因为 mode 是内部的，解析策略（或未来更聪明的路由）可以改变而不触动任何外部契约、不破坏调用方。
- **grep 仍在它该在的地方可用。** agent 和脚本通过专用工具/端点保留精确文件/行匹配；只有人用面板少了那个框。

## 已考量的备选方案

- **保留 `mode` 但给默认值。** 拒绝：该参数仍需在每个界面被文档化、校验、推敲，且仍把
  `fallback` 泄漏进响应 —— 对一个语料已决定正确策略的单用户来说全是成本、毫无收益。
- **保留响应里的 `fallback`，只移除输入 `mode`。** 拒绝：降级是语料/配置状况，不是逐查询结果；用
  `documents_degraded` 报告一次足矣，逐查询标志会诱使调用方对瞬时状态分支。
- **在人用面板保留 grep。** 拒绝：grep 返回文件/行匹配而非排序 passage —— 一种不同的心智模型，会扰乱「问个问题、得到答案」的界面；agent 才是正确的消费者。

## 修订历史

- **2026-06-21** —— 初版决定：检索 mode 是引擎内部细节；外部界面接受一次查询、
  返回一个答案。
- **2026-09-10** —— 因知识层合并而重命名。`memory` 与 `knowledge_base` 合为一个
  `knowledge` kind，故本 ADR 点名的两个检索工具 —— `coffer__search_knowledge` 与
  `coffer__recall` —— 现在合为一个 `coffer__search`，`coffer__grep_knowledge` 则是
  `coffer__grep`；两套逐 store 的检索配置合为一份逐 scope 的 `KnowledgeConfig`，
  而它也不再带任何 embedding 字段（embedding 改由安装级配置解析，某个 scope 是否
  启用向量，纯粹由它是否列出该 mode 决定）。**决策本身未变** —— mode 仍在内部，
  外部界面仍是一次查询进、一个答案出。若说有什么变化，这次合并反而强化了它：
  一个工具横跨两条 lane，调用方要做的选择又少了一个。
