# ADR-014：Channel Adapter 框架

> English: [ADR-014-channel-adapter-framework.md](./ADR-014-channel-adapter-framework.md)

**Status**: Accepted
**Spec**: [009-channels](../../specs/009-channels/spec.md)

## Context

Coffer 需要消息 channel（Telegram、SeaTalk，以后更多），让唯一的 owner
通过它们与聊天平台（spec 008）上的任何 agent 对话、接收
通知。channel 和 agent 都还会继续增加，因此集成成本必须保持 N + M：新增
一个 channel 不得触碰 agent 代码，新增一个 agent 也不得触碰 channel
代码。

有两条平台约束塑造了这个设计：

- 章程要求公网可达的 surface 必须作为独立进程运行，且只服务带签名的回调
  路径；而 SeaTalk 只通过公网 webhook 投递事件。
- daemon 是全部状态的唯一所有者，并且已经在运行受监管的后台 worker
  （retention worker）和子进程（MCP 上游）。

## Decision

1. **channel 是一种 resource kind**（`channel:<name>`，ADR-007），完整
   搭乘通用的生命周期、审计与凭据 ref 机制。secret 活在凭据存储里；配置
   只携带 ref，并在注册时被探测。
2. **薄 adapter，共享内核。** adapter 只实现传输：生命周期、出站发送/
   编辑、把入站消息规范化成公共信封，以及一份 `ChannelCapabilities` 声明
   （能否编辑消息？能否显示按钮？能否显示输入中？）。配对、owner 门、
   命令、排队、对话映射与渲染策略都放在与 kind 无关的 channel
   内核里。内核根据能力选择行为，从不根据 adapter 类型 —— Telegram 靠
   编辑一条消息来流式展示进度，SeaTalk 降级为「先确认、后给最终回复」，
   内核里零平台条件分支。
3. **只通过聊天平台既有的接缝触达它** ——
   `ChatService.create_conversation`、`TurnOrchestrator.start_turn` /
   `interrupt_turn` —— 进程内调用，与 web UI 经 HTTP
   做的事完全一致。channel 对 agent 一无所知；agent 也分不清一个 turn 来
   自 channel 还是 UI。任何已注册的 agent 都能从任何 channel 触达，双方
   都无需改代码。
4. **adapter 在 daemon 内以受监管的 asyncio 任务运行**，由一个
   reconciler 循环管理（RetentionWorker 模式）：每个 tick 把启用状态的
   channel 资源与运行中的 adapter 做 diff，并启动/停止/重启以对齐。资源
   框架不加任何新的生命周期 hook；disable、配置修改与 delete 都会在一个
   tick 内收敛。
5. **SeaTalk 的 ingress 是一个独立的回调监听器进程**，在任何 SeaTalk
   channel 处于启用状态时由 daemon 拉起。它只在一个 loopback 端口上服务
   `POST /seatalk/{channel}`：应答平台的验证 challenge、校验
   `sha256(body + signing_secret)`，并把合法事件携带 daemon token 经
   loopback 转发给 daemon。用户把一条隧道（cloudflared/ngrok）指向该
   端口；Coffer 永不把 daemon 本身暴露出去。
6. **owner 绑定只走配对码**：一个 8 字符的一次性码（无歧义字母表、1 小时
   TTL、有界猜测次数、仅存内存），从 UI/CLI 签发，再由 owner 用自己的
   账号发给 bot。其他所有人都被静默忽略。重新配对会替换绑定。不存在直接
   输入用户 id 的路径 —— 配对同时验证了传输的往返，而一个打错的 id 会
   静默绑到错误的账号上。
7. **不用平台 SDK。** 两个传输都用裸 httpx 对固定 host 通信；用到的 API
   面很小，引入 SDK 只会多一个依赖外加一条 import 限界契约，毫无杠杆。

## Alternatives considered

- **独立的 channel-gateway 进程（OpenClaw 形态）** —— 隔离更好，但对一个
  单用户本地 daemon 来说，进程管理面（detect-or-spawn、PID、日志）翻倍；
  否决。
- **把 channel 做成 MCP server** —— 数据流向颠倒了（MCP 是 agent→tool 的
  出站；channel 是 user→agent 的入站）；否决。
- **为 SeaTalk 提供 webhook 中继服务** —— 一个托管中继能让用户免去隧道，
  但引入了需要运营的基础设施和一个第三方信任根；隧道让一切都归用户所
  有。等真实使用提出需求再重新考虑。
- **以直接录入用户 id 的 allowlist 作为配对的替代方案** —— 否决；见决策
  6。

## Consequences

- 第三种 channel = 一个 adapter + 一份配置 schema + 对称的 importlinter
  条目；测试套件的假 adapter 演示了这套配方。
- 平台上的第二个 agent 立即可从 Telegram 与 SeaTalk 触达；测试套件用一个
  脚本化 provider 驱动 channel 来钉死这一点。
- reconciler 拥有全部运行时状态变迁；REST/CLI/UI 永不直接启停 adapter，
  这让 status 始终诚实。
- 监听器的拉起模式（env 注入 secret、pidfile、孤儿清扫）复用 MCP 子进程
  的约定，包括冻结构建下同目录二进制的解析。
