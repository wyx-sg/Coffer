# Quickstart —— Coffer Agent Registry

> English: [quickstart.md](./quickstart.md)

在 Coffer 完成首次启动设置之后，Agent Registry 让你把本机已安装的 AI agent
告诉 Coffer，从而让后续功能（skills、memory、knowledge base）知道把资产
往哪里投递。

## 首次启动时的自动检测

无需操作 —— daemon 第一次启动时会扫描已知的 agent 安装路径，并把找到的
任何一个注册进来：

| Agent 类型       | 检测标记                                                                                                 |
| ---------------- | -------------------------------------------------------------------------------------------------------- |
| Claude Code      | `~/.claude/`                                                                                             |
| Claude Desktop   | macOS: `~/Library/Application Support/Claude/`；Linux: `~/.config/Claude/`；Windows: `%APPDATA%/Claude/` |
| Cursor           | `~/.cursor/`                                                                                             |
| OpenAI Codex CLI | `~/.codex/`                                                                                              |

每一个被检测到的 agent 都以 `auto_detected=true` 注册，并使用其默认的
skill 目录。打开 Agents 页面（或运行 `coffer agent list`）即可看到。

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
coffer agent add cursor --name cursor-work --skill-dir /opt/cursor-work/skills
```

Coffer 会校验该路径存在、是目录、当前用户可写，且不是特权系统位置。
任何失败都会给出具体原因。

## 更新一个 agent

```bash
coffer agent edit cursor-work --skill-dir /opt/cursor-work/skills-v2
```

## 移除一个 agent

```bash
coffer agent rm cursor-work
```

移除一个自动检测出来的 agent 会写入一条「抑制」记录，使得 daemon 后续
重启不会再自动重新添加它。你随时可以手动重新添加（手动添加会解除抑制）。

## 重新跑自动检测

如果你在 Coffer 启动之后才装上新的 agent 类型，可以让 Coffer 再扫一次：

```bash
coffer agent detect
```

桌面应用的 Agents 页面也提供同样的入口。

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

**「自动检测出我不想要的 agent」** —— `coffer agent rm <name>`。Coffer 下次
启动不会再自动添加它。

**「自动检测漏掉了一个已安装的 agent」** —— 你的安装位于非标准位置。用
`coffer agent add <type> --skill-dir <你的路径>` 显式添加。
