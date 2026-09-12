# SeaTalk 入站走 WebSocket，SDK 由 operator 提供

> English: [seatalk-websocket-inbound.md](./seatalk-websocket-inbound.md)

**状态**：已接受
**日期**：2026-09-12
**决策者**：Yuxing Wu
**相关**：spec [channels](../../specs/channels/spec.zh.md)（FR-071、FR-072）；
[Channel Adapter 框架](channel-adapter-framework.zh.md)；
[Daemon Detect-or-Spawn](daemon-detect-or-spawn.zh.md)

## 背景

SeaTalk 的入站一直是 webhook。平台把事件 POST 到一个公网 URL，因此 Coffer——一个绑在
loopback 上、自己没有任何公网地址的 local-first 金库——只能把这样一个地址「制造」出来。
为此而存在的那套装置，是 channel 层里最繁复的一块机械：

- 一个**独立的监听进程**，在 SeaTalk channel 启用时由 daemon 拉起，因为章程不允许把
  公网可达的 surface 放在 daemon 内部；
- 每个请求上的**签名校验**，它存在的唯一理由就是这个端点任何找到它的人都能访问；
- 一条从该端点通到 loopback 端口的**隧道**——最初由属主自己搭，自托管隧道那次工作之后，
  变成 daemon 依据 channel 上的 connector token 拉起并看住的一个 `cloudflared` 子进程；
- channel 上记着的一个**公网基址**，好让状态能报出当初交给平台的是什么，以及一个探测它
  的可达性测试。

这里每一样东西，都是为了抵消「bot 没有公网地址」这一个事实而存在的。没有一样是这个产品
真正要做的事。

SeaTalk 现在给出了第二种投递方式的文档：**WebSocket Event Callback**。bot 持有一条到
平台的出网连接，在这条连接上用 app 凭据注册，事件就从它自己打开的 socket 上来。没有公网
URL，没有监听器，没有隧道，没有签名。平台自己的约束是一个 bot **同一时刻只用一种投递
方式**——两者是互替，不是叠加。

这件事此前被记为「有意不做」，理由有两条，而现在两条都变了：

1. **协议没有文档。** 当时公开的材料只讲了怎么调用一个厂商 SDK。现在这项能力有了文档，
   所以 Coffer 实现的行为是一份契约，而不是一次猜测。
2. **那个 SDK 对一个 MIT 仓库不可用。** `seatalk-oapi-sdk-py` 从一个内部企业门户分发，
   在公共 PyPI 上不存在，也没有任何公开许可。这一点**并没有**变。变的是这个认识：Coffer
   根本不需要去解决它——见下面的决策。

## 决策

**采纳 WebSocket 作为 SeaTalk 的第二种入站传输，按 channel 选择；并把平台的 SDK 当作一个
由 operator 提供的可选依赖，而不是本仓库要携带的东西。**

1. **`delivery` 是 SeaTalk channel 配置上的一个字段**——`webhook`（默认，也正是这个字段
   出现之前存下的每一条 channel 的样子）或 `websocket`——而它决定了其余哪些字段才允许存在。
   websocket channel 禁止 `signing_secret_ref`、`public_base_url` 与 `tunnel_token_ref`：
   没有请求体要签名，没有 URL 要描述，没有隧道要照看，而一个什么都决定不了的配置字段只会
   歪曲正在运行的系统。`app_id` 与 `app_secret_ref` 两边都必需，因为注册握手就靠它们认证。

2. **这条传输终止在既有的摄入接缝上，比 adapter 再高一行。** SDK 的通用事件回调交出来的是
   原始事件 dict，形状与 webhook 的请求体本来就一样，所以 connector 调用的正是 HTTP 路由
   调用的那个 channel service 摄入入口。它下游的一切——去重、归一化、属主门禁、媒体下载、
   线程、turn——都是共用的、未被改动的，也不需要按传输分别测试，因为已经没有按传输不同的
   东西了。只有两样真正长成 webhook 形状的东西留在监听器里：签名校验与 `event_verification`
   握手。

3. **监督（supervision）归 Coffer，因为 SDK 自己没有。** 这个 SDK 是同步、基于线程的，
   并且不会重连。所以每个 websocket channel 配一个 connector，自带监督循环——连接、在工作
   线程上 listen、失败后退避重试——由一个按 channel 的 controller 持有，其形状对照既有的
   隧道 controller，并由 channel runtime 以和隧道完全相同的方式做收敛。runtime 统计监听器
   时现在只算 webhook channel，所以一套只有 websocket 的部署根本不跑监听器。

4. **SDK 是由 operator 提供的可选依赖。** Coffer 不 vendor 它，不声明它，也不在 daemon
   导入时 import 它。Coffer 到一个 vendor 目录里找它——设了 `$COFFER_SEATALK_SDK_DIR`
   就用它，否则用 `~/.coffer/vendor`——只在该目录存在时才把它前置到 import 路径上，并在一个
   websocket channel 启动时才惰性 import。SDK 缺失是一个按 channel 的状况，给出点明「搜过
   哪个目录」与平台文档的可操作消息，而不是一次崩溃，也不是整个 daemon 的失败。

## 考虑过的替代方案

- **把 SDK vendor 进本仓库。** 直接否决。Coffer 是 MIT、受 OSS 约束；该 SDK 从内部企业门户
  分发，没有任何公开许可。把它拷进来，等于在一个公开仓库里放进无人授权我们再分发的代码。
  任何便利都抵不过这一条。

- **把它声明为依赖。** 否决：它不在公共 PyPI 上，所以每一个外部用户的安装都会坏，CI 也解析
  不出来。一个取不到的依赖不是依赖，而是一次构建失败。

- **重新实现它的线路协议。** 很有诱惑力，因为这个 SDK 是裸 socket 之上一层很薄的客户端，
  自带帧格式和一个 ping 线程——几百行的量。否决，因为协议没有公开：注册握手、envelope 与
  ack 的形状、被踢的语义，全都得从一个无人为其写文档的二进制里逆出来，而平台随时可以改动
  其中任何一处且无需通知。我们会拥有一个猜测，并把它叫做传输层。读有文档的 SDK 接口、并向
  operator 要这个 SDK，才是对「我们知道什么」诚实。

- **只保留 webhook 这一种传输。** 否决：那等于为了补偿一个金库故意不要的地址，持续养着一个
  监听进程、一套签名方案、一个隧道子进程和一个公网主机名——而且是在 Coffer 本身是唯一可能
  桥梁的那个平台上。只要属主能提供 SDK，那个形状更对的传输就应该对他可用。

- **一个 bot 同时跑两种方式，socket 掉线时用 webhook 兜底。** 否决，因为平台禁止：一个 bot
  同一时刻只用一种投递方式。做这种兜底意味着要在故障期间用代码去翻该 app 自己后台里的设置，
  这既没有接口可用，又恰恰是那种会让故障更糟的隐藏状态。

## 后果

- **一个 SeaTalk app 只许一条连接，且最新的注册者胜出。** 如果同一个 app 在第二台机器上被
  注册——另一套安装、同事在试——那次注册会把这一条踢掉，事件也跟着过去。connector 会报出
  kicked 状态，并按一段较长的固定延迟退避，而不是去抢这个 socket，因为两个进程抢着注册会让
  两边都饿死。在两台机器上跑 Coffer 的属主必须只在其中一台启用该 channel；这就是规范里对
  channel 平台身份早已写明的「单一消费者」规则，只是现在多了一个看得见的失败形态。

- **连接断开期间事件投递是暂停的。** 重启、网络抖动或退避窗口期间，没有任何公网端点帮着接住
  事件；平台如何处置投递不成的事件是平台的行为，不是 Coffer 能排队绕开的事。webhook 投递在
  隧道挂掉时有同样的暴露，但隧道的存活与否属主看得见，而这一条在 daemon 内部——所以连接状态
  要成为状态面一等公民报出来的东西，而不是一行日志。

- **投递方式是一个两边都要改的设置。** 它活在这里的 channel 上，也活在 SeaTalk 开发者后台的
  app 上，两者必须同步移动。在 Coffer 里切换会清掉另一种方式所拥有的字段，这是诚实而非有损：
  这次切换本来就不免费，因为后台必须同步改。在 websocket 一侧，后台的 Re-verify 只有在连接
  真的活着时才会通过，所以顺序是*先在 Coffer 里启用，再去那边验证*——这个顺序陷阱值得写下来，
  因为做反了看上去就像产品坏了。

- **没有 SDK 的安装是一等配置。** 这正是本项目外部用户手里的那套，也正因如此 webhook 投递
  仍然被完整支持。WebSocket 是 operator 可以加上的一项能力，绝不是产品赖以站住的地基；任何
  测试都不得因为真 SDK 不在而跳过，所以测试套件针对一个「就是契约」的替身来写。

- **webhook 那套装置留着。** 什么都没删：监听器、签名校验、托管隧道、公网基址与可达性测试，
  仍然是 webhook 投递的正确实现，也仍然是拿不到 SDK 的属主唯一的选择。于是第二条传输的代价
  就是多一条路要维护——这个代价值得付，因为新的那条把公网 surface 整个去掉了，而这是把旧的
  那条打磨到多好都做不到的事。
