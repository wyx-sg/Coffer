# ADR-038：Channel 媒体——DB 只存引用，发送时按 agent 物化

> English: [ADR-038-channel-media.md](ADR-038-channel-media.md)

**状态**：Accepted
**日期**：2026-07-04
**决策者**：Yuxing Wu
**相关**：spec `009-channels`（FR-020）；构建于 [ADR-014](ADR-014-channel-adapter-framework.zh.md)（channel adapter 框架）

## 背景

channel 驱动的 agent 必须能收到 owner 从手机发来的图片和文件（起因场景：「这是新时间的截图，把请帖改一下」）。此前 `TelegramAdapter._dispatch` 只读 `message.text`，任何非文本消息以空信封到达内核后被拒——agent 从未看到图片。

两个受支持的 agent 消费图片的方式不同：

- **Claude Code**（经 Claude Agent SDK 的 stream-json 输入驱动）接受用户回合里内联的 `image`/`document` **内容块**（base64）——这是程序化驱动的官方原生机制，模型直接「看到」图，无需工具调用。
- **Codex**（经其 app-server RPC 驱动）**没有**内联图路径；它是路径原生（`-i <path>` + `view_image` 工具）。Anthropic 的 image block 对它无意义。

对主流 agent 喂图方式的调研（aider、Cline、OpenHands、Continue、Open Interpreter、Goose 都内联 base64；Codex 与 CLI 进程型桥接给路径）确认：**没有单一机制**同时适配两者——稳健设计必须按 agent 分流。

矛盾点：内联 base64 是原生机制，但一张 3–5 MB 的照片会变成约 4–7 MB 的 base64——若持久化进消息内容，会撑大 chat DB 且每回合重发。

## 决策

**bytes 存到带外；chat DB 只存引用；发送时按 agent 物化。**

1. 传输层把每个附件（`getFile` → 下载）存到 Coffer 管理的媒体目录（`~/.coffer/channel-media`）。入站信封携带 `InboundAttachment(path, mime, filename)`。
2. bytes **绝不**进 chat DB。持久化的用户消息保留 caption（没有则一条简短的「(sent an image: …)」注记）。附件引用**带外、仅本回合**经 `start_turn → run_turn` 传递——不作为消息内容——因此冻结的消息模型、持久化、以及 web/OpenAPI 契约都不动。
3. 每个 agent adapter 按自己的原生形态物化引用：
   - **Claude Code** 在发送时读文件、**内存中** base64 编码、内联 `image` 块（PDF 用 `document`）；非视觉文件变成指向其路径的文本指针。base64 只存在于出站请求里。
   - **Codex** 收到附加在 prompt 后的磁盘路径（其原生模型）。

## 考虑过的替代方案

- **内联 base64 作为一种持久化进消息的新 `ContentBlock`**——最「原生」（附件在历史里、网页 UI 显示），但会波及消息模型、持久化、前端块渲染、OpenAPI 契约，且要么撑大 DB（base64）、要么仍需一个路径引用块。v1 否决：波及面与 DB 成本超过历史重放的收益，而后者在会话内已被 Claude Code 的 session resume 覆盖。
- **Anthropic Files API（`file_id`）**——针对跨多回合复用的大资产的规模优化，但有状态、锁供应商、Bedrock/Vertex 不可用、且未在 SDK stream-json 路径上有文档（Claude Code 订阅鉴权使 `file_id` scoping 不可靠）。对一次性 channel 发送是杀鸡用牛刀。留待真实需求出现。
- **对所有 agent 都只存盘 + 路径注记**——最简单，但把视觉 agent 打发去调一次 `Read`，而它本可原生看图。否决：不稳健，且调研显示内联是视觉 agent 的标准做法。

## 影响

- 历史保持精简；DB 无 base64；冻结的消息/持久化/web 接缝不动。
- 设计与模态无关：音频、zip 等都是同一种引用；新类型是新 `mime`，不是新 schema。未来的**音频原生** agent 只需 `run_turn` 多一个分支（内联音频块 vs 先转写成文字 vs 给路径），按 agent 能力分流——这正是 spec `009` FR-021（语音）所构建的接缝。
- 附件按回合物化，不作为消息内容持久化；因此重读完整历史（无 session resume）的后续回合看到的是注记而非图片。v1 可接受——Claude Code 的 resume 会在会话内保留它。
- bytes 会在 `~/.coffer/channel-media` 下累积；保留/清理是后续工作（本处不做门槛）。
