# ADR-023：Channel 入口差异化层

> English: [ADR-023-channel-entrypoint-differentiation.md](./ADR-023-channel-entrypoint-differentiation.md)

**状态**：已接受
**Spec**：[009-channels](../../specs/009-channels/spec.zh.md)

> **修订（2026-06-20，简化 8.4）。** per-binding workspace allowlist、`/cwd`
> 切换命令，以及 peer 的 `preferred_workspace` 均已撤销：channel 统一运行在
> Coffer 托管的默认工作目录（`~/.coffer/workspace`）。`/agent` + `/model`
> 切换命令及入口差异化核心保持不变。

## 背景

Spec 009 让 Coffer 成为 channel 入口管理者：owner 把一个 IM 账号配对到
`channel:<name>` 资源,通过 chat 平台的接缝驱动任一已注册 agent（`builtin`、
`claude_code`、`codex`）。

入口管理者仍缺的是把它从「一根固定线」变成「交换机」的那一层：owner 只能跟
channel 配置里写死的那一个 agent、在（operator 写死的）那一个工作目录里对话,
没有谁驱动了什么的记录,而在不能编辑消息的平台（SeaTalk）上,长桥接 turn 运行
期间**毫无信号**。这些正是入口管理者该拥有、而现成 IM bot 都跳过的差异化点。

代码里两个事实塑造了设计：

- 一个 conversation **终身 pin 它的 `agent_key`**,桥接 provider 在
  `init_conversation` **固化 `cwd`**,没有 re-key 路径。但桥接 turn 的
  **`model`** 在每次重建 adapter（每 turn 一次）时从 `agent_config` 重新读取。
- 桥接 agent **必须有 `cwd`**（无默认,缺了即拒绝）,而该 `cwd` **没有任何
  allowlist**——任意主机目录都收。channel 也从没给 owner 选它的途径。

## 决策

1. **结构维 vs 参数维——所有切换统一一个心智模型。**
   - _结构维_（`agent_key`、`cwd`）在建会话时 pin,中途不可改。切换其一会
     **开一个新会话**,带上另一维的粘性值;旧会话留在历史里。`/agent` 属结构维。
   - _参数维_（`model`）每 turn 重读。切换其一**在同会话下条 turn 生效**。
     `/model` 属参数维。

   这对应 provider 的真实契约（cwd/agent 固定于 `init_conversation`;model 读于
   `build_adapter`）,因此命令语义是诚实的,而非用合成的 re-key 糊弄。

2. **per-channel agent 路由是粘性的,存在 peer 上。** `/agent <key>` 对 agent
   注册表校验,把选择记为 peer 的粘性首选;`/new` 与懒创建用粘性 agent,无则
   回落 channel 配置的 `default_agent`。辅助（面向 vault）agent 不是路由对象——
   路由发生在注册表暴露的 chat 路径 agent 之间（`builtin`、`claude_code`、
   `codex` 及未来注册的 agent）,且不为任何 agent 写 channel 侧代码（spec 009
   SC-004 保持）。

3. ~~**workspaces 是 channel 级 allowlist,也是 cwd 安全边界。** 一个 channel
   声明一组**命名 workspace**（`{name, path}`）,注册时校验存在;可选
   `default_workspace` 指定未选时使用的那个。`/cwd <name>` 在其中选择（结构维
   →开新会话）。**channel 永不接受来自 IM 消息的裸文件路径**——owner 只能挑
   operator 预授权的名字。~~ —— **已撤销（2026-06-20，简化 8.4）。** channel
   现在统一运行在 Coffer 托管的默认工作目录（`~/.coffer/workspace`）；不存在
   per-channel allowlist，也没有 `/cwd` 命令。

4. **model 选择是参数维透传,仅在有 registry 处走 registry。** 对 `builtin`,
   `/model <name>` 对 Coffer model registry 解析,设 conversation 的 `model_id`
   覆盖。对桥接 agent,`/model <name>` 写 `agent_config["model"]`——上游 CLI 认识
   的原始 model 串,不校验透传,因为 Coffer 不拥有那个命名空间;typo 会以 CLI
   错误回传到 chat。（这同时修了 Claude Code provider 此前接受 `model` 选项却
   从不持久化、导致永远由 CLI 自选的问题。）

5. ~~**channel 驱动的工作在审计日志里是一等的。**~~ _2026-09-10 撤回。_
   `CHANNEL_TURN_STARTED` 曾记录谁在哪个 channel、经哪个 agent 驱动了哪个 turn。
   它与另外 26 个事件类型一起被退役,依据是这一条本身通不过的规则:一个事件要值得
   一行审计,必须落在 Coffer 之外、不可逆或安全敏感、或是当前状态看不出来的低频
   配置变更。一个 turn 跑过了三条都不占——会话与其消息本身就是那份记录,而且量很大。
   channel 层仍然审计的是**配对**(`channel_pairing_issued` / `channel_paired`),
   因为那才是把「可以驱动 turn」这项权限授予某个发送者的动作。

6. **owner gate 校验发送者身份,而非只看会话身份。** inbound 信封携带
   `sender_id`（Telegram `from.id`、SeaTalk `employee_code`）;pairing 把它记到
   peer,owner gate 校验 `chat_id` **且**（当 peer 有已存 `sender_id` 时）发送者。
   这堵住群聊洞（此前已配对群聊里任意成员都能过 chat-id-only 闸）,同时向后
   兼容：本改动前配对的 peer `sender_id` 为 null,退化为 chat-id-only 闸。

7. **turn 完成被显式信号化,capability-agnostic。** 每个 turn 后,channel 发一条
   紧凑事实摘要作为新消息——成功（`done`、工具数、耗时、token）、错误或中断。
   它是一次新的 `send_text` 而非编辑,因此在每个平台行为一致;在 SeaTalk（不能
   编辑、长桥接 turn 期间什么都不显示）上,这是 owner 得到的唯一 turn 结束信号。

## 备选方案

- **就地 re-key 会话的 agent/cwd** 而非开新会话——否决;provider 在
  `init_conversation` 固化二者,桥接 CLI session 又绑定其 cwd,就地 re-key 是会
  破坏 resume 连续性的假象。
- **接受来自 IM 消息的裸 cwd 路径**（`/cwd /some/path`）——否决;可远程触达的
  入口把 agent 指向任意主机目录,正是 allowlist 要守的边界。
- **对桥接 model 串按精选列表校验**——作为 cargo-cult 否决;Coffer 不拥有上游
  CLI 的 model 命名空间,还得追着它跑。透传 + 回传 CLI 错误更诚实更便宜。
- **turn 期间 token 级流式 + 刷心跳**——暂否决;单条完成摘要才是高价值低噪声的
  信号,且块级工具进度在平台可编辑处已存在。

## 结果

- peer 增列：已配对发送者身份（`sender_id`）及粘性 agent 首选
  （`preferred_agent`）；一个 migration 覆盖。无新表。（`preferred_workspace`
  以及 config 上的 `workspaces`/`default_workspace` 已撤销，见上方修订。）
- 命令集增 `/agent` 与 `/model`；二者都骑现有 slash 命令接缝、在 channel core
  里按能力选行为,因此没有 adapter 学到它们——差异化层是 channel-agnostic 的,
  任何未来 channel 都继承它（spec 009 SC-003 保持）。（`/cwd` 已撤销，见上方
  修订。）
- 审计日志能回答「谁经哪个 channel 驱动了哪个 agent」,无需改 schema。
