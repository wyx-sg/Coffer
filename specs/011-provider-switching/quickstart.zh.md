# 快速上手——Coffer Provider Switching

> English: [quickstart.md](./quickstart.md)

在 Coffer 中集中管理 LLM provider profile，然后原子地将匹配 agent 的原生配置切换到该 provider。

## 前提条件

- Coffer daemon 正在运行（启动桌面应用或执行 `coffer daemon`）。
- 至少已注册一个 agent（自动检测或通过 `coffer agent add`——参见 spec 004 快速上手）。

## 添加 provider profile

通过 `--secret` 提供原始 API key（或省略以触发提示）：

```bash
# Anthropic provider（投影到 Claude Code）
coffer provider add my-anthropic \
  --wire anthropic \
  --base-url https://api.anthropic.com \
  --model claude-opus-4-5 \
  --fast-model claude-haiku-4-5 \
  --secret sk-ant-...

# OpenAI 兼容 provider（投影到 Codex）
coffer provider add my-openai \
  --wire openai \
  --base-url https://api.openai.com \
  --model gpt-4o \
  --wire-api chat \
  --secret sk-...
```

Coffer：
1. 校验 profile 字段。
2. 将原始 key 存入 Fernet vault，路径为 `provider/<name>/key`。
3. 持久化 kind 为 `provider` 的 Resource（config 只持有 `credential_ref`，绝不含原始 key）。
4. 审计 `RESOURCE_CREATED`。

## 复用现有 credential ref

若已有凭证存储（例如两条 profile 共用同一 key）：

```bash
coffer provider add my-alternate \
  --wire anthropic \
  --base-url https://api.anthropic.com \
  --model claude-sonnet-4-6 \
  --credential-ref provider/my-anthropic/key
```

## 激活（切换）provider

```bash
coffer provider switch my-anthropic
```

Coffer：
1. 将 `my-anthropic` 设为活跃的 anthropic profile（先清除之前的活跃记录，再设置目标——由单进程 daemon 串行执行）。
2. 投影到 `~/.claude/settings.json`——合并以下托管键：
   - `apiKeyHelper = "coffer provider key --wire anthropic"`
   - `env.ANTHROPIC_BASE_URL = <base_url>`
   - `env.ANTHROPIC_MODEL = <model>`
   - `env.ANTHROPIC_SMALL_FAST_MODEL = <fast_model>`（若未设置则省略）
3. 写入前创建 `~/.claude/settings.json.bak` 备份。
4. `settings.json` 中所有其他键（theme、mcpServers 等）保持不变。
5. 报告哪些 agent 已更新，哪些被跳过。
6. 审计 `PROVIDER_SWITCHED`。

## Claude Code——无需额外步骤

由于 `settings.json` 中写入了 `apiKeyHelper = "coffer provider key --wire anthropic"`，Claude Code 会在需要时调用该命令获取 key。**Claude Code 无需环境变量。** 原始 key 永远不写入磁盘。

## Codex——在 shell 中设置环境变量

由于 Codex 从 `COFFER_PROVIDER_KEY` 读取 key，启动 Codex 前需在 shell 中 export：

```bash
export COFFER_PROVIDER_KEY="$(coffer provider key --wire openai)"
codex  # 或您的 Codex 启动方式
```

或加入 shell 初始化文件（`~/.zshrc`、`~/.bashrc`）：

```bash
# shell 启动时动态解析活跃 openai provider 的 key
export COFFER_PROVIDER_KEY="$(coffer provider key --wire openai 2>/dev/null || true)"
```

> **为什么 Codex 需要额外步骤？**
> 这是选择决策 B（凭证隔离）的可接受代价：原始 key 永远不写入 `config.toml`。Codex 通过环境变量读取（`~/.codex/config.toml` 中的 `env_key = "COFFER_PROVIDER_KEY"`）。将此环境变量自动注入 Coffer 启动的 Codex 进程与 hot-switch 一同延期。

## 列出和查看 profile

```bash
coffer provider list
coffer provider list --json | jq '.providers[].name'
coffer provider show my-anthropic
```

## 解析活跃 key（apiKeyHelper）

Claude Code 会自动调用，您也可以直接执行：

```bash
coffer provider key --wire anthropic   # 活跃 anthropic profile
coffer provider key --wire openai      # 活跃 openai profile
```

解析方式为给定 wire format 的活跃 profile。此子命令不支持位置参数 `<name>` 形式。

原始 key 只打印到 stdout，不记录到日志。

## 更新 profile

```bash
# 修改模型或 base URL
coffer provider edit my-anthropic --model claude-opus-4-5-20251101

# 轮换存储的 key
coffer provider edit my-anthropic --secret sk-ant-newkey...
```

更新 key 会轮换 Fernet vault 条目；`credential_ref` 保持不变。

## 删除 profile

```bash
coffer provider remove my-anthropic
```

若无其他 profile 共用该 credential ref，vault 条目也会被删除。

## 桌面应用

打开 Coffer → 侧边栏 **Providers**。Providers 页显示所有 profile 的表格，列：name、wire format、base URL、model、active。

行操作：
- **Switch**——激活该 profile（等同于 `coffer provider switch`）
- **Delete**——删除 profile（带确认）

**Add** 按钮打开新建 profile 表单。原始 key 只在该表单对话框中接受，并立即存入 vault。

如需编辑 profile（修改模型、base URL 或轮换 key），请使用 CLI（`coffer provider edit`）或 PATCH API。桌面页不提供内联编辑功能。

## 磁盘布局一览

```
~/.coffer/sync/
  resources/
    provider/
      my-anthropic.yaml    # 同步的 profile config（不含 secret）
  credentials/
    provider/
      my-anthropic/
        key.enc            # 原始 API key 的 Fernet 密文

~/.claude/settings.json    # 已合并托管键（apiKeyHelper, env.*）
~/.claude/settings.json.bak   # 每次投影前的备份

~/.codex/config.toml       # 已合并托管键（model, model_providers.coffer.*）
~/.codex/config.toml.bak      # 每次投影前的备份
```

## 故障排查

**"Neither secret_value nor credential_ref provided"**——传入 `--secret`（或等待提示），或传入 `--credential-ref` 复用现有 vault 条目。

**"Both secret_value and credential_ref provided"**——只能提供其中一个。若要复用已有 key，请使用 `--credential-ref`。

**"No active anthropic profile found"**——先执行 `coffer provider switch <name>` 激活一条 profile，再使用 `coffer provider key`。

**Codex 未使用新 provider**——确认在当前 shell 会话中切换后已 export `COFFER_PROVIDER_KEY`（`export COFFER_PROVIDER_KEY="$(coffer provider key --wire openai)"`）。正在运行的 Codex 进程需重启后才能使用更新后的环境变量。

**"切换后 settings.json 中出现意外键"**——Coffer 只合并定义的托管键，从不删除其他键。如发现意外变更，请对比 `~/.claude/settings.json.bak`（最后一次切换前的备份）。

**激活 profile 报告 `skipped: ["codex"]`**——Coffer 中尚未注册 Codex agent。通过 `coffer agent add`（参见 spec 004）或桌面 Agents 页注册，profile 仍会标记为活跃。
