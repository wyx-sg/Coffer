# 记忆

**记忆**(memory)是跨你所有 agent 的一份共享事实集。任何 agent(或你)写下的一条事实,会作为一个 Markdown 文件保存在 `~/.coffer/memory/` 下,被其他每个 agent 通过 Coffer 网关召回,并被**原生投影**进每个 agent 各自的记忆位置,使得没有任何按 agent 的副本发生漂移。

记忆与知识共用同一底座:文件是事实来源,SQLite 索引可重建,三种检索模式同样适用。

## 两个作用域

- **global** —— 处处生效(`~/.coffer/memory/global/`)。
- **per-project** —— 限定一个项目,由 agent 工作目录的 git 根解析得到。

存储按作用域自动开通;你从不“创建”它。`recall` 默认同时返回两个作用域。

## 添加与召回

```bash
coffer memory add global "所有仓库优先用 pnpm 而非 npm" --name pkg-manager
coffer memory recall global "用哪个包管理器?"             # 跨 project + global
coffer memory facts global                               # 列出事实
coffer memory edit global <fact-id> "…"                  # 整理
coffer memory delete global <fact-id>
```

- 事实按原文存储 —— 写入时没有 LLM。
- `recall` 在检索前会重新扫描事实目录以纳入带外编辑,并使用与知识库相同的 grep / keyword / vector 模式。

## 原生投影

把一个存储绑定到某个 agent,会把其事实投影进该 agent 自己的记忆:

```bash
coffer memory bind <store> claude-code --project-root /path/to/repo
coffer memory unbind <store> claude-code
```

- **Claude Code** —— 项目记忆目录被符号链接进 `~/.claude/projects/<slug>/memory/`,自动生成的 `MEMORY.md` 索引遵循 Claude Code 自身的记忆格式。
- **Codex** —— 事实渲染进 `AGENTS.md` 中一个受管区块;Codex 的原生记忆被禁用,因此绝不会出现第二份副本。

agent 同样获得 MCP 工具:`coffer__remember`、`coffer__recall`、`coffer__update_memory`、`coffer__forget` 和 `coffer__list_memory`。一个桌面 UI 让你按作用域浏览与整理事实。

[渠道 →](/zh/guide/channels)
