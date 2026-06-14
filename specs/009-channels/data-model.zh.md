# Data Model：009 —— Channels

> English: [data-model.md](./data-model.md)

## 资源：`channel:<name>`

channel 是既有 `resources` 表中的行（kind = `channel`）。`config_json` 由
一个以 `channel_type` 为判别字段 (discriminator) 的 Pydantic union 校验：

```
ChannelConfig (discriminator: channel_type)
├── common (两种类型共有, _CommonChannelFields)
│   ├── default_agent: str = "builtin"
│   ├── default_agent_config: dict | None
│   ├── workspaces: list[Workspace] = []   # 命名 cwd allowlist
│   └── default_workspace: str | None      # workspaces[].name 之一
├── TelegramChannelConfig
│   ├── channel_type: "telegram"
│   └── bot_token_ref: str            # credential-store ref, probed at register
└── SeaTalkChannelConfig
    ├── channel_type: "seatalk"
    ├── app_id: str
    ├── app_secret_ref: str            # credential-store ref
    └── signing_secret_ref: str        # credential-store ref

Workspace: { name: str, path: str (绝对路径) }
```

校验规则：

- `*_ref` 字段不得看起来像裸 secret（命中 Telegram token 模式或高熵长
  字符串会被拒绝，并提示用户去凭据存储）—— 与 `mcp_server` 拒绝静态值
  secret 的姿态一致。
- 该 kind 声明了 `credential_ref_extractor`，因此 `ResourceService` 会在
  写入行之前探测每一个 ref；悬空的 ref 会中止注册。
- `default_agent` / `default_agent_config` 不在注册时校验（agent registry
  在创建对话时校验，那是平台的权威关口）；无效的 agent 会在首次接触时以
  turn 错误的形式暴露。
- `workspaces` 是从该 channel 选取 agent 时的 cwd allowlist。形状（名字唯一、
  绝对路径、`default_workspace ∈ names`）由 Pydantic 模型校验；kind 的
  `validate_config` 钩子另外要求注册时每个 `path` 是已存在目录，因此坏的
  workspace 会中止注册、不写入任何行。chat 消息永不提供裸路径——只给名字。

## 表：`channel_peers`

已配对的 owner 与对话指针。目前每个 channel 一行；以 chat id 为键，使
未来支持群聊时只需新增一行，而不是做迁移。

| column | type | notes |
| --- | --- | --- |
| `id` | INTEGER PK | |
| `resource_id` | INTEGER, FK `resources.id` ON DELETE CASCADE | 所属 channel |
| `chat_id` | TEXT | Telegram chat id / SeaTalk employee_code |
| `display_name` | TEXT | 配对时发送者的名字，用于 UI/status |
| `paired_at` | DATETIME (UTC) | |
| `active_conversation_id` | TEXT NULL | 当前对话；对话消失时清空 |
| `sender_id` | TEXT NULL | 已配对发送者的稳定 id（Telegram from.id、SeaTalk employee_code）；owner gate 在其存在时校验它。NULL → chat-id-only 闸（旧 peer） |
| `preferred_agent` | TEXT NULL | 粘性 agent 选择（`/agent`）；NULL → channel `default_agent` |
| `preferred_workspace` | TEXT NULL | 粘性 workspace 选择（`/cwd`）；NULL → channel `default_workspace` |

约束：`UNIQUE (resource_id, chat_id)`；对 `resource_id` 建索引。

`active_conversation_id` 是指向聊天平台 `conversations` 表的软引用（跨
接缝不建 FK）：如果对话已在 Chat 页面被删除，下一条入站消息会检测到悬空
的 id 并创建一段新对话。

`sender_id` / `preferred_agent` / `preferred_workspace` 都可空，使本修订前
配对的 peer 优雅退化：null sender id 表示 chat-id-only 闸，null 首选表示用
channel 默认值。

迁移：`20260612_0015_channel_tables.py`（创建 + 对称的 downgrade）；
`20260614_0022_channel_peer_differentiation.py` 增加上述三个可空列。模型
模块由 `migrations/env.py` import，因此 Alembic 能看到其 metadata。

## 内存态（从不持久化）

| object | scope | content |
| --- | --- | --- |
| `PairingCode` | 按 channel | 码、过期时间、剩余尝试次数；重新签发即替换，成功/过期/耗尽即丢弃 |
| message queue | 按 peer | 有界 FIFO（10），存放等待轮到自己的入站文本 |
| progress state | 按运行中的 turn | 可编辑状态消息的 IM message id、上次编辑时间戳 |
| approval routing | 按待处理审批 | `request_id ↔ (chat, prompt message id)`，让一次按钮点按能解决正确的审批门并更新正确的消息 |
| seatalk token cache | 按 channel | app access token + 过期时间 |

崩溃行为：这一切都随 daemon 一起蒸发；turn 由聊天平台的启动清扫标记为
failed，配对码重新签发，队列归零。用户依赖的任何东西都不会只活在内存
里。

## 规范化信封（domain 值对象）

```
InboundMessage:  channel name, chat_id, sender display name, text,
                 platform message id, timestamp
ApprovalClick:   channel name, chat_id, value (request id + decision),
                 prompt message id
OutboundText:    markdown text (rendered per adapter capability)
ChannelCapabilities: supports_edit, supports_buttons, supports_typing,
                 max_message_chars
```

adapter 负责在平台载荷与这些信封之间互译；application 内核永远看不到
Telegram update 或 SeaTalk event 的形状。

## 审计事件（spec 009）

| event | when |
| --- | --- |
| `channel_pairing_issued` | 生成一个配对码时 |
| `channel_paired` | 某个发送者认领该码并成为 peer 时 |
| `channel_notify_sent` | notify 把文本投递给 peer 时 |

资源生命周期事件（`resource_created` … `resource_deleted`）由框架自动
产生。对话/turn 活动由聊天平台审计；channel 层不在那里添加任何东西。
