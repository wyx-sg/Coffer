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
确认某个候选项即可注册它——Coffer 会为你填入该类型的默认 skill 目录与建议名称。
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

如果你的 agent 装在非标准位置，用显式 skill 目录把它添加进来：

```bash
coffer agent add codex --name codex-work --skill-dir /opt/codex-work/skills
```

Coffer 会校验该路径存在、是目录、当前用户可写，且不是特权系统位置。
任何失败都会给出具体原因。受支持的类型是 `claude_code` 与 `codex`。

名称是可选的——省略 `--name`，Coffer 会按类型派生一个稳定的默认名（下划线变
连字符，如 `claude_code` → `claude-code`）。在桌面应用中，add/edit 表单提供一个
**文件夹选择器**来选择自定义 skill 目录，而无需手动输入路径：打包应用用 OS 原生
目录对话框，Web 用 daemon 支撑的文件夹浏览器。

## 更新一个 agent

```bash
coffer agent edit codex-work --skill-dir /opt/codex-work/skills-v2
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

| Agent       | key                                              |
| ----------- | ------------------------------------------------ |
| Claude Code | `settings`、`settings_local`、`global`、`memory` |
| Codex       | `config`、`memory`                               |

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
不变），原子写入，并保留上一版本的 `.bak`，使错误的编辑可恢复。桌面端的配置文件
标签页提供同样的编辑 + 保存，外加一个编辑器内查找/替换便利功能。

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
- agent 的 `skill_dir` 会成为未来 skill 投递（spec 005）使用的目标目录。

## 故障排查

**「默认 skill_dir 不可写」** —— 你的安装位于当前用户无法写入的目录。
要么修复该路径的权限，要么在添加 agent 时传入 `--skill-dir <可写路径>`。

**「注册了我不想要的 agent」** —— `coffer agent rm <name>`。只要它仍处于安装
状态，它就仍会作为发现候选项出现，但在你再次确认之前不会进入你的 registry。

**「发现漏掉了一个已安装的 agent」** —— 你的安装位于非标准位置，因此其标记
不在 Coffer 查找的地方。用 `coffer agent add <type> --skill-dir <你的路径>`
显式添加。
