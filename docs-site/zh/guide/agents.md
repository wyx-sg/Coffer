# Agent

**Agent** 是一个已注册的本地 AI 编码助手，Coffer 可以管理它的配置文件以及它与 Coffer 自身 MCP 服务器的连接。目前已发布两种 agent 类型：`claude_code` 和 `codex`。

Coffer 绝不会自动注册 agent。它可以**检测**你机器上已安装的 agent，但每一个都需要你确认后才会被注册。

## 检测与注册

运行检测以发现已安装的 agent，然后注册你想要的那些：

```bash
coffer agent detect            # → claude_code（已检测）、codex（已检测）
coffer agent add claude_code   # 注册；--name 默认为 claude-code
coffer agent add codex --name my-codex --config-dir ~/.codex --description "工作笔记本"

coffer agent list              # → claude-code | claude_code | registered
```

- `coffer agent detect` 扫描已安装的 agent 并报告检测结果。此步骤不会注册任何东西 —— 仅做发现。
- `coffer agent add <type>` 注册一个 agent。`<type>` 为 `claude_code` 或 `codex`。`--name` 可选，默认为按类型生成的名称（例如 `claude_code` → `claude-code`）。可选标志：`--config-dir PATH`（agent 的配置目录 —— 默认为该类型的标准位置，例如 `~/.claude`；Coffer 会把技能交付到该目录的 `skills/` 子文件夹中）和 `--description TEXT`。
- `coffer agent list` 显示所有已注册的 agent，及其类型和状态。
- `coffer agent show <name>` 打印某个已注册 agent 的详情；`coffer agent rm <name>` 移除它。

## 编辑配置文件

每个 agent 暴露一组经过策展的配置文件，用一个简短的**键 (key)** 寻址：

| 类型          | 键               | 文件                                          |
| ------------- | ---------------- | --------------------------------------------- |
| `claude_code` | `settings`       | `~/.claude/settings.json`                     |
| `claude_code` | `settings_local` | `~/.claude/settings.local.json`               |
| `claude_code` | `global`         | `~/.claude.json`（同时存放用户级 MCP 服务器） |
| `claude_code` | `memory`         | `~/.claude/CLAUDE.md`                         |
| `codex`       | `config`         | `~/.codex/config.toml`                        |
| `codex`       | `memory`         | `~/.codex/AGENTS.md`                          |

列出某个 agent 的键、打印某个文件，或编辑某个文件：

```bash
coffer agent config ls claude-code              # 列出策展的文件 + 哪些已存在
coffer agent config cat claude-code settings    # 打印 ~/.claude/settings.json
coffer agent config edit claude-code settings   # 在你的编辑器中打开
coffer agent config edit claude-code settings --from-file ./settings.json
```

在每个接口面上，写入都经过同样的安全保障：

- **格式校验** —— JSON 和 TOML 文件在写入前先被解析。格式错误的内容会被拒绝，磁盘上的文件保持不变。
- **原子写入**并保留 `.bak` 备份 —— 旧内容会被保存在文件旁边。
- **允许列表中尚未创建的文件**也会被列出。打开一个尚不存在的文件会显示为空；读取它**不会**创建该文件。

## 安装 Coffer 的 MCP 服务器

一条命令即可将 Coffer 自身的 MCP 服务器条目 —— 一个指向 `coffer-mcp-shim` 二进制的 `coffer` stdio 条目 —— 写入（或从中移除）某个 agent 的配置：

```bash
coffer agent mcp status claude-code      # → 未安装 / 已安装
coffer agent mcp install claude-code     # 写入 coffer 条目
coffer agent mcp uninstall claude-code   # 移除它
```

安装是幂等的：再次运行只会就地更新已有条目，而不会重复添加。安装完成后，该 agent 通过 shim 即可访问你在 Coffer 中注册的每一台服务器 —— 参见[接入客户端](/zh/guide/connect-client)。

## Web UI 操作演示

[Web UI](/zh/guide/web-ui) 中的 **Agents** 页面无需终端即可完成同样的流程：

1. 打开 **Agents** 并点击 **Detect** 扫描已安装的 agent。检测对话框列出找到的结果；确认某个 agent 即可注册它。
2. agent 详情页有四个标签 —— **Overview**、**Skills**、**MCP servers** 和 **Config files**。
3. 在 **Config files** 标签中，在编辑器中打开任意策展的配置文件。编辑器在保存时校验格式、以原子方式写入并保留 `.bak` 备份，还内置一个**查找/替换**框，可滚动到匹配项。
4. 使用头部的 **Install Coffer MCP** 开关添加或移除 `coffer` 条目，并配有实时状态指示。
5. 在 **Skills** 标签中，为此 agent 逐个启用或禁用技能，或用 **Install skills** 绑定更多技能。**MCP servers** 标签显示 Coffer 向该 agent 暴露的服务器（目前为只读）。

[接入客户端 →](/zh/guide/connect-client)
