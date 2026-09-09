# ADR-041：把 channel 附件持久化为引用块，从历史重新物化

> English: [ADR-041-persisted-attachment-reference.md](ADR-041-persisted-attachment-reference.md)

**状态**：已接受
**日期**：2026-07-09
**决策者**：Yuxing Wu
**相关**：spec `009-channels`（FR-033）；取代 [ADR-038](ADR-038-channel-media.zh.md)
中 v1「推迟持久化附件块」的决定

## 背景

[ADR-038](ADR-038-channel-media.zh.md) 把 channel 媒体的字节存在带外的
`~/.coffer/channel-media`，并把一个**仅本 turn**的附件引用带外传递——经由
`start_turn → run_turn`——**而非**作为消息内容。它明确地为 v1 **推迟**了一个持久化
的附件 `ContentBlock`，理由是波及面（消息模型、持久化、前端块渲染、OpenAPI 契约）以及内联
base64 带来的 DB 膨胀风险。

ADR-038 接受的后果：附件按 turn 物化但从不持久化，因此任何重读全历史（无 session
resume）的场景看到的是一条备注而非图片，且附件在网页 Chat 页里不可见。FR-033 重新审视这个
决定——关键认识是：一个**引用**块（path/mime/filename，**不含 bytes**）彻底消除了 DB 膨胀
这一反对理由。

## 决定

**把附件作为引用 `AttachmentBlock` 持久化进用户消息，并让这个持久化引用成为物化本 turn 的
单一事实来源。**

1. `AttachmentBlock(path, mime, filename, type="attachment")` 加入 `ContentBlock`
   联合类型（domain、JSON 序列化/反序列化、OpenAPI 契约）。它只携带引用，**绝不含 bytes**。
2. 编排器把本 turn 的附件持久化进用户消息内容（在 `TextBlock` 之后），即便是只有附件的
   turn 也如此。
3. turn 任务通过从**历史里最后一条用户消息**读回附件来**推导**交给 `adapter.run_turn`
   的附件——而非来自编排器向下线程传递的参数。由于历史是在用户消息持久化之后拉取的，
   `history[-1]` *就是*当前 turn 的用户消息。这让「从历史重新物化」名副其实，让每个 adapter
   **保持不变**（它们仍收到 `attachments: Sequence[Attachment]`，并像 ADR-038 那样按模型
   物化），并在守护进程重启后依然工作（历史是持久的）。
4. **网页**把引用渲染为用户气泡上一个紧凑的 `📎 filename · mime` 芯片。本地 **path 绝不发到
   线上**（线上 `ContentBlock` 暴露 `filename`/`mime`，而非 `path`）——一条泄露/安全红线。
5. **重放作用域仅限当前会话**——持久化引用物化的是*本*会话的 turn。无跨会话／切换 agent 的
   全历史重放。
6. **保留**：`~/.coffer/channel-media` 的 30 天 mtime 清扫跑在既有的保留节奏上（无大小上限）。
   决定（哪些文件足够旧）是一个纯 domain 助手；stat/unlink 清扫属于 infrastructure，在组合根
   注入进 `RetentionService`。

## 考虑过的替代方案

- **保持 ADR-038 原样（仅本 turn、带外参数）**——最简单，但附件在网页 UI 里不可见，且在
  turn 中途守护进程重启后丢失。否决：FR-033 存在的意义正是让附件持久且可见。
- **在持久化块里内联 base64**——ADR-038 否决的 DB 膨胀情形；仍然否决。引用块在不含 bytes
  的前提下拿到历史/可见性的好处。
- **把本地 path 发到线上**——能让网页 fetch/预览，但把绝对主机路径泄露给任何 API 客户端。
  出于安全否决；一个 filename/mime 芯片足够满足网页需求。
- **一个媒体服务端点 + 缩略图**——更丰富的网页预览，但面大得多（鉴权、range 服务、缓存）。
  推迟；芯片已足够。
- **引用计数式媒体保留（只删无引用文件）**——避免删掉某个存活会话仍指向的文件，但每次清扫都
  要扫描每个会话的块。不值得：bytes 可重新下载，死引用可优雅退化，因此纯 mtime 年龄清扫足够。

## 后果

- 附件留存在历史里、在网页 Chat 页里显示、并在守护进程重启后存活；持久化引用是物化的单一
  事实来源。
- adapter 保持不变——移动的是接缝（历史读回而非参数），而非 adapter 契约。ADR-038 的模态无关
  性质仍成立。
- 旧的纯文本消息行反序列化不变（无 schema 的 JSON 内容，无迁移）；`block_from_dict` 多了一个
  `attachment` 分支。
- 媒体字节由 30 天清扫界定，而非永久累积（补上了 ADR-038 留下的保留缺口）。
- 被取代的 ADR-038 条目：其「推迟持久化附件块」的替代方案与「不作为消息内容持久化」的后果被
  本 ADR 取代。
