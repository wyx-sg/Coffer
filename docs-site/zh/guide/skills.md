# 技能

**技能**(skill)是一个符合 [AgentSkills](https://agentskills.io) 标准的包 —— 一个含 `SKILL.md`(带 `name` 与 `description` frontmatter)的文件夹 —— 用来教会 agent 一项可复用的任务。Coffer 为每个技能保留一份规范副本,并把它**投递**给你选定的 agent,这样你只需管理一次技能,而不必在 `~/.claude`、`~/.codex` 等之间来回拷贝文件夹。

## 导入技能

从本地文件夹或公开的 Git URL 把技能加入主库:

```bash
coffer skill import ./my-skill                                      # 拷入一个本地文件夹
coffer skill fetch https://github.com/acme/skills --ref main --subpath foo
coffer skill list                                                  # → my-skill | local_import
coffer skill show my-skill                                          # 元数据 + 文件
```

- `import` 取一份时间点快照;`fetch` 记录 Git 来源,之后可用 `coffer skill update <name>` 刷新。
- 主副本位于 `~/.coffer/skills/<name>/`。

## 把技能投递给 agent

为某个 agent 启用技能,会在该 agent 的 `skills/` 目录创建一个指向主副本的符号链接:

```bash
coffer skill enable my-skill --agent claude-code     # 投递(符号链接)
coffer skill disable my-skill --agent claude-code    # 移除链接
coffer skill verify                                  # 报告漂移;有则非零退出
```

- Coffer 从不自动修复。`verify` 报告缺失、被篡改或孤立的链接;你显式修复(重新 enable,或 `coffer skill update`)。
- `coffer skill rm <name>` 删除技能并拆除其所有绑定。

## 在应用里

**Skills** 页列出你的主库;通过文件选择器或 Git URL 导入,打开一个技能可查看其元数据与只读文件树。按 agent 的投递在每个 agent 的 **Skills** 标签页 —— 为该 agent 开关某个技能。参见 [Agents](/zh/guide/agents)。

[知识库 →](/zh/guide/knowledge-base)
