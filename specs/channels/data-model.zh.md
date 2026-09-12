# Data Model：Channels

> English: [data-model.md](./data-model.md)

## 资源：`channel:<name>`

channel 是既有 `resources` 表中的行（kind = `channel`）。`config_json` 由
一个以 `channel_type` 为判别字段 (discriminator) 的 Pydantic union 校验：

```
ChannelConfig (discriminator: channel_type)
├── common (两种类型共有, _CommonChannelFields)
│   ├── default_agent: str = "claude_code"  # chat provider key；必须是已注册的 agent
│   ├── default_agent_config: dict | None
│   ├── require_mention: bool = True        # 群聊准入（FR-035）
│   └── ignore_other_mentions: bool = False # 群聊准入（FR-035）
├── TelegramChannelConfig
│   ├── channel_type: "telegram"
│   └── bot_token_ref: str            # credential-store ref, probed at register
└── SeaTalkChannelConfig
    ├── channel_type: "seatalk"
    ├── delivery: "webhook" | "websocket" = "webhook"  # 入站传输（FR-071）
    ├── app_id: str                     # 两种投递都必需
    ├── app_secret_ref: str             # credential-store ref；两种投递都必需
    ├── signing_secret_ref: str | None  # webhook：必需 —— websocket：禁止
    ├── public_base_url: str | None     # 仅 webhook：隧道公网基址（https://host）
    └── tunnel_token_ref: str | None    # 仅 webhook：cloudflared token ref（托管隧道）
```

校验规则：

- `*_ref` 字段不得看起来像裸 secret（命中 Telegram token 模式或高熵长
  字符串会被拒绝，并提示用户去凭据存储）—— 与 `mcp_server` 拒绝静态值
  secret 的姿态一致。
- 该 kind 声明了 `credential_ref_extractor`，因此 `ResourceService` 会在
  写入行之前探测每一个 ref；悬空的 ref 会中止注册。
- `default_agent` 是 chat **provider key**（如 `claude_code`，下划线）——
  turn 编排器据以解析 agent 的键，而**不是** `claude-code` 资源名；连字符值能通过
  注册却会在 turn 时报 `UNKNOWN_AGENT`，让 bot 静默失活。它在**创建**
  （`validate_config`）和**编辑**（`on_update_config`）时都对照实时 agent registry
  校验（[Built-in Agent Is Internal](../../docs/decisions/builtin-agent-is-internal-capability.zh.md)
  退役了旧的 `builtin` 伪 agent）：未注册的 agent 会被当场拒绝，而
  不是在首个 turn 才静默失败。仅当 registry 为空时跳过校验，以免 registry 配错时
  阻断所有 channel 写入。`default_agent_config` 仍是透传。
- channel 不带任何模型策展。它曾短暂拥有自己的 `default_model` 与 `models` 允许范围，
  两者都已移除：channel 只绑定一个 agent、别无其他——新会话跑在所绑定 agent 自己的 CLI
  默认模型上，`/model` 卡片提供该 agent 的整份 catalogue，且不拒绝任何 id。迁移
  `20260912_0067_drop_channel_model_curation.py` 单向地把这两个键从每一条既有 channel
  config 里剥掉，不留 load-time 垫片（房规）——`_CommonChannelFields` 禁止多余键，
  仍带着它们的行在加载时会校验失败。
- `delivery` 决定 SeaTalk 那几个字段哪些合法，整条规则由一个
  `model_validator(mode="after")` 统一持有，使「允许的组合」与「禁止的组合」永远不会
  各自漂移（FR-071）：

  | 字段                 | `delivery: "webhook"`        | `delivery: "websocket"` |
  | -------------------- | ---------------------------- | ----------------------- |
  | `app_id`             | 必需                         | 必需                    |
  | `app_secret_ref`     | 必需                         | 必需                    |
  | `signing_secret_ref` | **必需**                     | **禁止**                |
  | `public_base_url`    | 可选                         | **禁止**                |
  | `tunnel_token_ref`   | 可选（设了即托管隧道）       | **禁止**                |

  「禁止」 这一半才是让配置可读的关键：websocket channel 没有请求体要签名、没有公网 URL
  要描述、也没有隧道要照看，所以这三者里任何一个存下了值，都是在宣称一套并不存在的运行
  时安排。每条错误消息点明字段名以及它与哪种投递方式冲突，风格与其余跨字段校验一致——
  因为用户走到这个错误上，正是在切换某个既有 channel 的传输方式：那是他们唯一一刻同时
  握着两套字段。
- **`delivery` 不配任何迁移。** 在这个字段存在之前存下的每一条 channel 都是 webhook
  channel——当时只有这一种传输——而字段默认值就是 `webhook`，所以「值不存在」本来就恰好
  等于那些行实际的样子。没有任何东西被重新解释，没有任何值改变含义，也没有哪一行的行为
  取决于被改写一次；在这里做迁移，等于把 `webhook` 写到本来就按 `webhook` 行事的行上。
  （对比上面的迁移 `0067`：它必须**去掉**模型已不再接受的键——一个带着「与存量现状一致」
  默认值的新字段，正好是相反的情形。）这也是为什么任何地方都没有 load-time 垫片——没有
  旧形状需要翻译。
- channel 的 turn 运行在 Coffer 托管的默认工作目录 `~/.coffer/workspace`
  （首次使用时创建）。

## 表：`channel_peers`

已配对的 owner 与对话指针。目前每个 channel 一行；以 chat id 为键，使
未来支持群聊时只需新增一行，而不是做迁移。

| column                   | type                                         | notes                                                                                                                            |
| ------------------------ | -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `id`                     | INTEGER PK                                   |                                                                                                                                  |
| `resource_id`            | INTEGER, FK `resources.id` ON DELETE CASCADE | 所属 channel                                                                                                                     |
| `chat_id`                | TEXT                                         | Telegram chat id / SeaTalk employee_code                                                                                         |
| `display_name`           | TEXT                                         | 配对时发送者的名字，用于 UI/status                                                                                               |
| `paired_at`              | DATETIME (UTC)                               |                                                                                                                                  |
| `active_conversation_id` | TEXT NULL                                    | 当前对话；对话消失时清空                                                                                                         |
| `sender_id`              | TEXT NULL                                    | 已配对发送者的稳定 id（Telegram from.id、SeaTalk employee_code）；owner gate 在其存在时校验它。NULL → chat-id-only 闸（旧 peer） |
| `preferred_agent`        | TEXT NULL                                    | 粘性 agent 选择（`/agent`）；NULL → channel `default_agent`                                                                      |

约束：`UNIQUE (resource_id, chat_id)`；对 `resource_id` 建索引。

`active_conversation_id` 是指向聊天平台 `conversations` 表的软引用（跨
接缝不建 FK）：如果对话已被删除，下一条入站消息会检测到悬空
的 id 并创建一段新对话。

`sender_id` / `preferred_agent` 都可空，使本修订前配对的 peer 优雅退化：
null sender id 表示 chat-id-only 闸，null agent 首选表示用 channel 默认值。

迁移：`20260612_0015_channel_tables.py`（创建 + 对称的 downgrade）；
`20260614_0022_channel_peer_differentiation.py` 增加上述两个可空列。模型
模块由 `migrations/env.py` import，因此 Alembic 能看到其 metadata。

## 内存态（从不持久化）

| object              | scope           | content                                                          |
| ------------------- | --------------- | ---------------------------------------------------------------- |
| `PairingCode`       | 按 channel      | 码、过期时间、剩余尝试次数；重新签发即替换，成功/过期/耗尽即丢弃 |
| message queue       | 按 peer         | 有界 FIFO（10），存放等待轮到自己的入站文本                      |
| progress state      | 按运行中的 turn | 可编辑状态消息的 IM message id、上次编辑时间戳                   |
| seatalk token cache | 按 channel      | app access token + 过期时间                                      |

崩溃行为：这一切都随 daemon 一起蒸发；turn 由聊天平台的启动清扫标记为
failed，配对码重新签发，队列归零。用户依赖的任何东西都不会只活在内存
里。

## 规范化信封（domain 值对象）

```
InboundMessage:  channel name, chat_id, sender display name, text,
                 platform message id, timestamp
InboundCallback: channel name, chat_id, sender_id, data（点选的 ChoiceButton
                 value）, callback_id, platform message id (FR-018)
OutboundText:    markdown text (rendered per adapter capability), 可选
                 ChoiceButtons（label + 不透明 value）→ 选择卡片
ChannelCapabilities: supports_live_text, supports_edit, supports_buttons,
                 supports_typing, max_message_chars
```

adapter 负责在平台载荷与这些信封之间互译；application 内核永远看不到
Telegram update 或 SeaTalk event 的形状。

## 审计事件（spec channels）

| event                    | when                             |
| ------------------------ | -------------------------------- |
| `channel_pairing_issued` | 生成一个配对码时                 |
| `channel_paired`         | 某个发送者认领该码并成为 peer 时 |

资源生命周期事件（`resource_created` … `resource_deleted`）由框架自动
产生。turn 活动**不**审计：一个 turn 发生过既不是不可逆的、也不是安全敏感的，
事后更不是看不见的——会话与其消息本身就是记录。配对之所以审计，是因为它把
「可以驱动 turn」这项权限授予了某个发送者，而这正是审计日志存在的理由。
