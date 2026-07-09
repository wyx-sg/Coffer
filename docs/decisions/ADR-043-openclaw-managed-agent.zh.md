# ADR-043：OpenClaw 是第六个受管叶子 agent

> English: [ADR-043-openclaw-managed-agent.md](ADR-043-openclaw-managed-agent.md)

**状态**：已接受
**日期**：2026-07-10
**决策人**：Yuxing Wu
**相关**：推翻 [ADR-040](ADR-040-re-widen-agent-registry.zh.md) 关于 openclaw 的结论；完成 [ADR-042](ADR-042-context-injection-mechanisms.zh.md) 启动、记录于 [`docs/research/openclaw-gateway-integration.zh.md`](../research/openclaw-gateway-integration.zh.md) 的纠错；spec `004-agent-registry`（FR-003/FR-003a/FR-013/FR-046/FR-048）、spec `008-agent-chat`（agent providers）、spec `011-provider-switching`（投影）

## 背景

[ADR-040](ADR-040-re-widen-agent-registry.zh.md) 重新加回了 `opencode` /
`hermes` / `cursor`，却把 **openclaw** 留在外面：「对等网关、不是叶子」，并给出
一张五行能力表、其中四个 facet 判为 N/A。ADR-042 的第一性复查发现**五行错了三
行**（MCP 可注入、原生记忆可禁用、skills 可直接投放），research note 随之推翻结
论——*openclaw 就是可行的受管叶子 agent*——「待有真实安装可供验证」。

真实安装现已存在（openclaw **2026.6.11**，已 onboard、在 PATH 上），下表每一条
能力断言都对着它探针验证过——遵循 ADR-042 的纪律：每格能力都引用文档或探针，绝
不引用假设。

## 探针验证的能力矩阵

| Facet | 机制 | 证据 |
| --- | --- | --- |
| Chat 适配器（spec 008） | `openclaw agent --agent main --session-key <key> -m <text> --json --local` → stdout 是一个干净的 JSON blob（`payloads[].text`、`finalAssistantVisibleText`、`stopReason`、`completion.finishReason`、`executionTrace.winnerProvider/winnerModel`）；日志走 stderr。**非流式**——Coffer 第一个此类 provider。`--local` = 完全嵌入式，无需 gateway 守护进程，插件注册表每次运行预载。相同 `--session-key` → 相同会话。 | 实时回合，2026.6.11 |
| Coffer-MCP 注入（FR-019） | `~/.openclaw/openclaw.json`（纯 JSON）中的 `mcp.servers.<name>`，`{command, args?, env?, enabled?}` command-map。容器是**嵌套的**——manifest 的 `container_key` 是点分路径 `mcp.servers`，JSON 变换每个点下钻一层对象。注意：openclaw 在配置加载时拒绝 server `env` 里的解释器启动键（`NODE_OPTIONS`、`PYTHONPATH` 等）；Coffer 的条目不带 env。 | scratch 配置探针：`openclaw mcp status` 列出手写的 `coffer: stdio` 条目 |
| 会话上下文注入（FR-043/044/048） | `PLUGIN_DROP`，**openclaw 风味**：package 目录 `extensions/coffer-session-context/`（带 `openclaw.extensions` 的 `package.json`、`{id, configSchema}` 的 `openclaw.plugin.json`、导出 `definePluginEntry` 的 `index.js`）**加** `plugins.entries.<id>.enabled: true`——非内置插件 **fail-closed**。Hook：`api.on("before_prompt_build", h)`；handler 返回 `{appendSystemContext}`。插件在进程内全权限运行 → 能 spawn `coffer-hook`。 | `openclaw config validate` 接受 package + 开关组合；实时插件注入回合（见「影响」） |
| Provider 投影（spec 011） | `models.providers.coffer = {api, baseUrl, apiKey, models}`；`apiKey` 支持 `${UPPERCASE_VAR}`；模型引用 `provider/model`；活动模型经 `agents.defaults.model.primary`（保留用户 `fallbacks`）。自定义 provider 的 `models` **必填**、每项需同时有 `id` 与 `name`；`models: []` 合法（未绑定 agent 的投影）。openclaw 同时支持 `openai-completions` 与 `anthropic-messages` 两种 `api`。 | 各形状均经 `openclaw config validate` 探针，2026-07-10 |
| 缺 key 的降级 | `apiKey: "${COFFER_PROVIDER_KEY}"` 背后的 env var 缺失只是启动 **WARNING**（"Missing env var … feature using this value will be unavailable"）、exit 0、其他 provider 不受影响——**推翻文档「配置加载即抛错」的说法**，也正是 codex 式投影可行的原因：磁盘上持久化引用、每个 Coffer 驱动的回合注入 key，用户自己运行的 openclaw 没有该变量时优雅降级。 | 探针 2026-07-10 |
| 原生记忆禁用（FR-046） | `plugins.slots.memory: "none"` 清空 memory 插件槽；恢复 = 移除该键。 | `openclaw config validate` 接受 |
| Skills（spec 005） | `~/.openclaw/skills/<name>/SKILL.md`；**符号链接**的 skill 目录会被发现——Coffer 现有 `FOLDER` 投递不变即可用。 | 实时发现探针 |
| 检测 | 默认标记 `~/.openclaw`（存在 `OPENCLAW_STATE_DIR` 等 env 覆盖，与其他 agent 的非默认目录同样对待：不解析）。 | 安装布局 |

## 决定

1. **重新加回 `AgentType.OPENCLAW = "openclaw"`**，一条 `AgentDescriptor` 记录
   ——无需 DB 迁移（重新加回 `0031` 迁移删掉的枚举值；旧行当时已清除）。
2. **chat 适配器是非流式的**：每回合 spawn 一次，读 stdout 到 EOF，解析唯一的
   blob，发出 `TurnStarted` → 一个 `TextDelta` → `TurnDone`（`executionTrace`
   的 winner 盖在 assistant 消息上）。上游会话由 Coffer 派生的
   `--session-key coffer-<conversation_id>` 固定——不从流里发现、不逐回合持久化。
3. **没有 cwd 语义。** openclaw 是个人助理网关、不是 repo 作用域的 coding CLI：
   `openclaw agent` 没有 cwd 参数，回合在 agent 自己的 workspace
   （`agents.defaults.workspace`）里运行。provider 因此**忽略**会话的 cwd（如实
   记录、不做校验），而不是假装回合有项目作用域。
4. **MCP 注入以点分容器路径扩展 JSON 变换**（`mcp.servers`），不新增 entry
   style——条目本身就是 Claude Code 用的普通 command-map。
5. **会话上下文作为既有 `PLUGIN_DROP` mode 的第二个 `PluginFlavor`
   （`OPENCLAW`）交付**：三个渲染的 package 文件加 fail-closed 的
   `plugins.entries` 启用开关（spec 上的 `plugin_enable_config_key` 保持 hook
   service 的通用性）。卸载移除整个 package 且**不留 `.bak`**——内容为 Coffer
   渲染、可逐字节重建，且残留的备份 package 仍会被 openclaw 的扩展扫描器发现
   ——并移除启用开关（配置文件写入照常保留 `.bak`）。
6. **Provider 投影是 codex 式的**（磁盘上 `${COFFER_PROVIDER_KEY}` 引用，每个
   Coffer 驱动的回合把 key 注入子进程 env），按连接的 wire 选 `api`：`openai` →
   `"openai-completions"`，`anthropic` → `"anthropic-messages"`。openclaw 同时
   加入两个 wire 的默认 compatible-agents 集合。
7. **原生记忆禁用**把 `plugins.slots.memory: "none"` 接进既有 FR-046 开关。
8. **配置文件 allowlist**：`openclaw.json`（key `config`）+ 六个 workspace 指令
   文件（`instructions`/`soul`/`identity`/`user`/`tools`/`memory`，路径假定默认
   `~/.openclaw/workspace`）+ `extensions/` 目录条目。

## 影响

- Coffer 获得第一个**非流式** chat provider；chat 界面一次性显示完整回复。
  Coffer 侧不加超时（回合由 openclaw 自己的 `--timeout` 默认值治理）。
- **gateway 重启注意事项**：`--local` 嵌入式运行（所有 Coffer 驱动的回合）每次
  预载插件注册表、立即可见投放的扩展；长驻 `openclaw gateway`（channel 驱动的用
  法）要重启后才认。已记入 spec FR-048。
- openclaw *同时也*是对等网关（编排 coding CLI、承载 channels）。Coffer 只管理
  它作为叶子 agent 的那一面；research note 里勾画的「gateway 作为 LLM 端点」集
  成依然可用、不受影响。ADR-040 指出的继承效应如今是特性：Coffer 写入
  `~/.claude/` 等的内容会被 openclaw 派生的子 worker 继承。
- 本切片的 e2e 验证：带投放扩展 + stub `coffer-hook` 的一次实时 `--local` 回合
  确认注入的 marker 抵达模型（模型将其复述回来），且适配器端到端解析了真实的
  `--json` blob。

## 曾考虑的替代方案

- **继续排除 openclaw；只作为 OpenAI 兼容 LLM 连接集成**（ADR-040 的结论）。
  否决：支撑它的五条能力断言错了三条，纠正后的矩阵显示叶子 facet 完全对齐。连
  接式集成*另行*保留——两者并不竞争。
- **为嵌套容器新增一个 `McpEntryStyle`。** 否决：条目形状就是现有的
  command-map；只有容器位置不同，点分 `container_key` 是数据、不是机制。
- **卸载时保留扩展 package 的 `.bak`。** 否决：openclaw 会扫描 `extensions/`
  下的 package 目录，`.bak` package 仍会被发现（成为禁用的、id 过期的扩展）；
  package 完全由 Coffer 渲染，重装即逐字节重建。
