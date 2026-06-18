# 实现计划：009 —— Channels

> English: [plan.md](./plan.md)

## Summary

新增一个 `channel` resource kind，把 IM 账号（Telegram、SeaTalk）接到
spec-008 的聊天平台上。channel 内核（配对、路由、命令、排队、渲染策略、
notify）建立在一个小巧的 adapter 协议之上、与具体类型无关；
Telegram 与 SeaTalk 是头两个 adapter。一个独立的回调监听器进程为 SeaTalk
提供 webhook ingress，遵循章程的公网 surface 规则。前端在 Agents 导航组
里新增一个 Channels 页面。

## Technical Context

- **进程内直接驱动平台** —— `ChatService.create_conversation`、
  `TurnOrchestrator.start_turn`（把返回的队列消费到 `None` 哨兵）、
  `interrupt_turn`。channel 内核与聊天平台之间不走
  HTTP。
- **不引入新 SDK。** Telegram 与 SeaTalk 都用 `httpx` 对固定 host
  （`api.telegram.org`、`openapi.seatalk.io`）通信。channel 配置中不存在
  用户可控的 URL，因此 skill-fetcher 的 SSRF 防护不在此路径上。
- **adapter 运行时** —— daemon 里的一个 reconciler 任务（RetentionWorker
  模式）：约每 2 s 把启用状态的 channel 资源与运行中的 adapter 任务做
  diff；在 enable、disable、配置变更、delete 时启动/停止/重启。资源框架
  不加任何新的生命周期 hook。
- **凭据物化** —— `CredentialResolver` 从 `application/mcp/` 移到共享的
  `application/credentials/resolver.py`（出现第二个使用方；章程的抽取
  规则）。MCP 侧更新 import；行为不变。

## Constitution Check

- **Local-first** —— 全部状态在 SQLite/凭据存储中；出站调用只指向用户
  显式注册的 IM 平台。✓
- **公网可达 surface 必须是独立进程、只服务带签名的路径** —— SeaTalk
  监听器是独立进程，只服务 `POST /seatalk/{channel}` + 签名校验，绑定
  127.0.0.1，公网 URL 由用户的隧道提供。daemon 本身保持仅 loopback。✓
- **凭据** —— bot token、app secret、signing secret 都活在凭据存储里；
  配置只携带 ref；ref 在注册时被探测；secret 经 env 传给监听器子进程
  （沿用既定的 MCP 子进程模式），从不持久化或写日志。✓
- **分层** —— domain 保持纯净（信封、配置 schema、签名函数都只依赖
  stdlib + pydantic）；application 定义 adapter 协议；infrastructure 实现
  传输；surfaces 负责装配。✓

## Module layout — backend

```
backend/coffer/
├── domain/channel/
│   ├── config.py        # ChannelConfig discriminated union + ref validation
│   ├── envelopes.py     # InboundMessage, ChannelCapabilities
│   └── signing.py       # seatalk_signature(body, secret) — pure hashlib
├── application/
│   ├── credentials/resolver.py   # CredentialResolver (hoisted from mcp)
│   └── channel/
│       ├── ports.py     # ChannelAdapter protocol + AdapterCallbacks
│       ├── kind.py      # make_channel_kind (redactor, ref extractor, on_delete)
│       ├── pairing.py   # PairingManager (codes, TTL, attempt bounds)
│       ├── service.py   # ChannelService: pairing API, notify, status, peers
│       ├── inbound.py   # InboundProcessor: owner gate, commands, queueing,
│       │                #   conversation mapping, turn driving
│       └── runtime.py   # ChannelRuntime: reconciler loop + listener lifecycle
├── infrastructure/channel/
│   ├── persistence.py   # ChannelPeerModel + repo
│   ├── render.py        # markdown → telegram HTML / plain; chunking
│   ├── telegram.py      # TelegramAdapter: long poll, send/edit, buttons
│   ├── seatalk.py       # SeaTalkAdapter: token cache, send, cards, typing
│   └── listener_spawn.py# spawn/stop/health of the callback listener child
└── surfaces/
    ├── callback/        # the listener process (separate uvicorn app)
    │   ├── app.py       # POST /seatalk/{channel}: challenge echo, verify,
    │   │                #   forward to daemon over loopback
    │   └── __main__.py  # python -m coffer.surfaces.callback
    ├── http/
    │   ├── channel_routes.py   # pairing-code, status, notify, events ingest
    │   └── channel_wiring.py   # wire_channel_kind(): kind, service, runtime
    └── cli/channel_cmd.py      # list/register/pair/status/notify
```

关键接缝：

- `ChannelAdapter` 协议：`capabilities`、`start(callbacks)`、`stop()`、
  `send_text`、`edit_text`、`delete_message`、
  `send_typing`。可选的 surface 由
  `ChannelCapabilities` 声明；内核只查询能力，永不查询 adapter 类型。
- `AdapterCallbacks`（交给 adapter）：`on_message(InboundMessage)`。
  adapter 永不 import chat 模块。
- SeaTalk adapter 没有轮询循环；daemon 的事件接收路由经 runtime 的注册表
  调用 adapter 上的 `handle_event`。
- 监听器子进程在拉起时经 env 拿到逐 channel 的 signing secret、daemon
  URL 和 daemon token；除此之外不保有任何状态。源码安装以
  `[sys.executable, -m, coffer.surfaces.callback]` 拉起；冻结构建
  (frozen build) 则定位同目录的 `coffer-callback` 二进制（与
  `daemon_spawn_command` 相同的探测模式）。

## Module layout — frontend

```
frontend/src/
├── pages/ChannelsPage.tsx            # list + add entry point
├── pages/ChannelDetailPage.tsx       # status, pairing, enable/disable, delete
├── kinds/channel/                    # AddChannelDialog, schema, cards
├── lib/api/channels.ts               # hand-written wire types (chat.ts pattern)
└── lib/hooks/useChannels.ts          # queries + mutations
```

导航：`Channels` 加入 `nav.group.agents` 组（ADR-007 预留的位置）。
secret 先经既有的 keychain 路由保存、再创建资源，部分失败时回滚
（AddMcpServerDialog 模式）。i18n：`en.json`/`zh.json` 中新增 `channels`
namespace（由 parity 测试强制对齐）。

## Tests

- **Unit**：配置校验（ref、拒绝形似 secret 的值）、pairing manager
  （TTL、尝试次数、替换）、markdown 渲染 + 分块、签名函数、命令解析、
  能力驱动的策略选择。
- **Integration**（真实 SQLite、假传输）：一个 `FakeChannelAdapter` 对着
  一个脚本化 `AgentProvider` 驱动完整入站管线（register → pair →
  message → reply → /new → /stop → queue →
  notify）；Telegram adapter 对着本地假 Bot API（ASGI httpx
  transport）：轮询、offset 提交、HTML 回退、按钮；SeaTalk adapter 对着
  假 openapi host：token 刷新、发送、卡片、429 退避；回调监听器 app：
  challenge 回显、好/坏签名、转发；channel 路由 + CLI 命令；runtime
  reconciler（enable/disable/delete/配置变更）。
- **Contract**：新路由的 `/openapi.json` 与 `contracts/api.openapi.yaml`
  做一致性校验。
- **Acceptance**：spec.md 的每个 scenario 都带一个
  `@pytest.mark.acceptance(spec="009-channels", scenario=...)`（或前端
  `acceptance(...)`）标记；由 `make verify-acceptance` 审计。

测试套件使用的假 channel adapter 同时充当 SC-003 的证明（新 channel =
adapter + schema 而已）；脚本化的第二个 provider 证明 SC-004（任何
agent 皆可触达）。

## Importlinter & enforcement

- 新模块对称地加入每个跨 kind 的 `forbidden_modules` 列表；新增一条
  "Cross-kind imports forbidden (channel)" 契约，镜像既有的五条；与 kind
  无关的内核契约（C6）补上 channel 模块。
- `application/credentials/` 是与 kind 无关的共享代码（如同
  `application/audit_service.py`）；mcp 与 channel 都可以 import 它。
- `surfaces/callback` 只 import domain/channel 的签名函数 + httpx +
  fastapi；它永不 import daemon 内部模块。
- 所有文件 ≤ 400 行；每个路由声明 `response_model`；mypy strict。

## Risks & mitigations

- **Telegram/SeaTalk API 漂移** —— 传输被钉在 adapter 背后，配有假服务器
  集成测试；平台的变更只会弄坏一个文件。
- **进度消息的编辑限速** —— 编辑节流到间隔 ≥ 1.5 s，且进度消息是
  best-effort：失败时降级为「先确认、后给最终回复」。
- **监听器端口冲突** —— 端口可经 env 配置（`COFFER_CALLBACK_PORT`，默认
  8787），并在 channel status 中展示，因此隧道目标始终可发现。
- **配对途中 daemon 重启** —— 配对码按设计只存内存；status 界面会显示
  「无待用码」，重新签发只需一次点击。
