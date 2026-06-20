# Quickstart —— Coffer Agent Registry

> English: [quickstart.md](./quickstart.md)

在 Coffer 完成首次启动设置之后，Agent Registry 让你把本机已安装的 AI agent
告诉 Coffer，从而让后续功能（skills、memory、knowledge base）知道把资产
往哪里投递。

## 发现已安装的 agent

Coffer 绝不静默注册任何 agent。它提供一次只读扫描，把找到的「已安装但尚未
注册」的 agent 报告为**候选项（candidate）**；你审阅后确认要添加哪些：

| Agent 类型   | 检测标记     |
| ------------ | ------------ |
| Claude Code  | `~/.claude/` |
| OpenAI Codex | `~/.codex/`  |

每个类型都同时涵盖该产品的 CLI 与 app/IDE 形态，因为它们共享一个配置目录
（Claude Code 用 `~/.claude/`，Codex 用 `~/.codex/`）。

打开 Agents 页面并运行发现（或运行 `coffer agent detect`）即可看到这些候选项。
确认某个候选项即可注册它——Coffer 会为你填入该类型的默认配置目录与建议名称。
在你确认之前，不注册任何内容，磁盘上也不做任何改动。

## 列出你的 agent

```bash
coffer agent list
```

脚本用 JSON：

```bash
coffer agent list --json
```

## 手工添加一个 agent（自定义路径）

如果你的 agent 装在非标准位置，用显式配置目录把它添加进来：

```bash
coffer agent add codex --name codex-work --config-dir /opt/codex-work
```

Coffer 会自动创建 `<config-dir>/skills` 子目录（skill 投递到这里），随后校验解析
后的路径存在、是目录、当前用户可写，且不是特权系统位置。任何失败都会给出具体
原因。受支持的类型是 `claude_code` 与 `codex`。

名称是可选的——省略 `--name`，Coffer 会按类型派生一个稳定的默认名（下划线变
连字符，如 `claude_code` → `claude-code`）。`--config-dir` 同样可选——省略它，
Coffer 会使用该类型的标准位置（Claude Code 用 `~/.claude`，Codex 用 `~/.codex`）。
在桌面应用中，add/edit 表单提供一个**文件夹选择器**来选择自定义配置目录，而无需
手动输入路径：打包应用用 OS 原生目录对话框，Web 用 daemon 支撑的文件夹浏览器。

## 更新一个 agent

```bash
coffer agent edit codex-work --config-dir /opt/codex-work-v2
```

## 移除一个 agent

```bash
coffer agent rm codex-work
```

移除并非永久——Coffer 不保留任何「抑制」列表。只要该 agent 仍处于安装状态，
它就会在下次扫描时重新作为发现候选项出现，因此误删一个 agent 只需再确认一次
即可轻松撤销。

## 再次发现 agent

要扫描「已安装但未注册」的 agent（例如安装了新 agent 之后），再运行一次发现：

```bash
coffer agent detect
```

它只读地列出候选项，不注册任何内容。用 `coffer agent add <type> ...` 添加某个
候选项（或在桌面 Agents 页面确认它）。

## 查看一个 agent 的配置文件

每个 agent 类型都暴露一组精选的自有配置文件。列出它们：

```bash
coffer agent config ls claude-code
coffer agent config ls claude-code --json
```

| Agent       | key                                                                 |
| ----------- | ------------------------------------------------------------------- |
| Claude Code | `settings`、`settings_local`、`global`、`instructions`、`subagents` |
| Codex       | `config`、`instructions`、`hooks`                                   |

（`instructions` 是人工撰写的指令文件——`CLAUDE.md` / `AGENTS.md`。
`subagents` 是一个**目录**条目；见下文「编辑目录型配置条目」。）

打印某个文件的内容：

```bash
coffer agent config cat claude-code settings
```

编辑某个文件。不带 `--from-file` 时，会在你的 `$EDITOR` 中打开该文件的当前内容；
保存后 Coffer 会把编辑后的内容写回：

```bash
coffer agent config edit claude-code settings
```

或者非交互式地从某个文件保存内容：

```bash
coffer agent config edit claude-code settings --from-file ./new-settings.json
```

保存时，Coffer 会按文件格式校验内容（畸形的 `json`/`toml` 会被拒绝、磁盘文件保持
不变），原子写入，并保留上一版本的 `.bak`，使错误的编辑可恢复。如果文件在你读取
之后已在磁盘上被改动，保存会被拒绝，编辑器会提供重新加载，而不是悄悄覆盖。桌面端
的配置文件标签页以**只读**方式显示每个文件，并为文件及其所在文件夹提供
「在外部编辑器中打开 / 在文件管理器中显示 / 复制路径」，让你在自己的编辑器里编辑
（Coffer 使用你在 Settings 中的「首选外部编辑器」偏好）；上面的 `coffer agent
config edit` CLI 是程序化的编辑路径。

## 编辑目录型配置条目

有些配置条目是文件目录而非单个文件——Claude Code 的 `subagents` 条目
（`~/.claude/agents/`，每个个人 subagent 一个 Markdown 文件）。列出、写入与
删除单个子文件：

```bash
coffer agent config files claude-code subagents          # 列出子文件
coffer agent config write claude-code subagents reviewer.md --from-file ./reviewer.md
echo "..." | coffer agent config write claude-code subagents reviewer.md
coffer agent config rm claude-code subagents reviewer.md
```

子路径在任何磁盘访问之前都会被校验（不允许 `..`、绝对路径，仅限 `.md`）；
写入会按需创建文件，并享有同一套原子写入 + `.bak` 安全网；删除会把先前内容
保留为 `.bak`。

## 查看并 adopt agent 自己的 MCP 条目

除了 Coffer 的一键条目之外，MCP 标签页（与 CLI）还会显示 agent 自身文件中
配置的每一个 MCP server——从文件实时派生，绝不复制：

```bash
coffer agent mcp entries claude-code
coffer agent mcp entries claude-code --json
```

每个条目显示其名称、来源文件、传输方式、格式定义了开关时的 `enabled` 标志
（Codex），以及 Coffer 中是否已注册了等价的 `mcp_server` 资源。env/header 的
值绝不离开 daemon——只列出键名。

就地移除或开关一个条目（文件会保留 `.bak`）：

```bash
coffer agent mcp remove-entry claude-code my-server
coffer agent mcp toggle-entry codex my-server --disabled   # 仅 Codex
```

把一个直连条目 **adopt** 进 Coffer，改为通过 gateway 服务所有 agent。疑似密钥
的 env/header 键必须映射到凭据 (credential) 引用——Coffer 把值作为 Fernet 密文
存入其加密凭据存储 ([ADR-015](../../docs/decisions/ADR-015-envelope-encrypted-credential-store.md))；
明文绝不进入数据库、日志或审计：

```bash
coffer agent mcp adopt claude-code my-server --secret API_KEY=coffer/mcp/my-server/api_key
```

Coffer 先注册 `mcp_server` 资源、验证它可以回读，然后才从 agent 的文件中移除
该条目；任何失败都会回滚，你绝不会丢失一个可用的条目。名称冲突时错误会给出
建议名——用 `--name <suggested>` 重试。

## 开关或卸载 plugin

Plugins 标签页（与 CLI）列出 agent 已安装的 plugin，按 marketplace 分组：

```bash
coffer agent plugin list codex
coffer agent plugin disable codex my-plugin@my-marketplace
coffer agent plugin enable codex my-plugin@my-marketplace
coffer agent plugin uninstall codex my-plugin@my-marketplace   # 仅 Codex
```

开关只写文档化的配置面（Codex 条目的 `enabled` 字段；Claude Code
`settings.json` 中的 `enabledPlugins` 映射）——绝不写 agent 的内部状态文件。
`uninstall` 会移除 Codex 的配置条目及其缓存目录；Claude Code 的卸载需要
agent 自己的工具（`claude plugin`），因此 Coffer 提供禁用外加一条提示。

## 把 Coffer 的 MCP 安装到某个 agent

一条命令把 Coffer 聚合后的 MCP server 接进某个 agent：

```bash
coffer agent mcp status claude-code      # 已安装? false
coffer agent mcp install claude-code     # 写入 `coffer` stdio 条目
coffer agent mcp status claude-code      # 已安装? true
coffer agent mcp uninstall claude-code   # 移除它
```

`install` 把一个 `coffer` 条目写进 agent 的 MCP 配置（Claude Code 写
`~/.claude.json`，Codex 写 `~/.codex/config.toml`），指向 `coffer-mcp-shim`
的绝对路径。它是幂等的、会把先前配置备份到 `.bak`，并且在桌面 Agents 页面
上也以一键按钮形式提供。安装后请重启你的 agent 以加载 Coffer 的工具。

## 背后发生了什么

- 每个 agent 都作为 kind 为 `agent` 的 Resource 存进 Coffer 的 SQLite
  数据库，标识为 `agent:<name>`。kind-agnostic Resource 框架（在 spec 001
  中引入）提供 CRUD、校验与 audit。
- 每一次 add / edit / remove 都会写入 audit 事件，可通过 `coffer audit list`
  查询。
- agent 的 `<config_dir>/skills` 会成为未来 skill 投递（the 005-skill-manager spec）使用的目标目录。

## 故障排查

**「默认 config_dir 不可写」** —— 你的安装位于当前用户无法写入的目录。
要么修复该路径的权限，要么在添加 agent 时传入 `--config-dir <可写路径>`。

**「注册了我不想要的 agent」** —— `coffer agent rm <name>`。只要它仍处于安装
状态，它就仍会作为发现候选项出现，但在你再次确认之前不会进入你的 registry。

**「发现漏掉了一个已安装的 agent」** —— 你的安装位于非标准位置，因此其标记
不在 Coffer 查找的地方。用 `coffer agent add <type> --config-dir <你的路径>`
显式添加。
