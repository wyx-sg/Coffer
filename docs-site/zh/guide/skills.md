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

## 决定哪些 agent 收到某个技能

一个技能送达某个 agent,当且仅当该技能处于**启用**状态,且该 agent 在它的**启用范围(scope)**内。刚导入的技能是「已启用、未设置 scope」,因此对所有 agent 生效;要收窄就用所有支持 scope 的资源共用的那组命令:

```bash
coffer scope set skill:my-skill --agents claude-code   # 只给这个 agent
coffer scope clear skill:my-skill                      # 回到所有 agent
coffer resource disable skill:my-skill                 # 一次性从所有 agent 收回
coffer skill verify                                    # 报告漂移;有则非零退出
```

- 投递就是在该 agent 的 `skills/` 目录下创建一个指向主副本的符号链接;上面两个输入任一改变,链接都会被自动创建或回收。
- Coffer 从不自动修复漂移。`verify` 报告缺失、被篡改或孤立的链接;你显式修复(`coffer skill update`,或重新应用 scope)。
- `coffer skill rm <name>` 删除技能并拆除其所有链接。

## 在应用里

**Skills** 页列出你的主库;通过文件选择器或 Git URL 导入,打开一个技能可查看其元数据并浏览主文件夹,任何文本文件都可就地编辑。投递在技能自己这一侧设置 —— 列表页的启用开关,以及技能页面上的启用范围控件。每个 agent 的 **Skills** 标签页则只读地展示它当前收到了哪些技能。参见 [Agents](/zh/guide/agents)。

[知识 →](/zh/guide/knowledge)
