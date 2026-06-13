# 对话

Coffer 的**对话**是与一个运行在你保险库之上的 AI agent 的流式对话。这里有两类 agent 应答:

- **内置 agent**(“Coffer Assistant”)—— 一个进程内 agent,运行在你配置的 LLM 上,通过 Coffer 自己的网关访问你的 MCP 工具、知识库、记忆与技能;
- **CLI agent** —— 你已安装的 **Claude Code** 或 **Codex** 二进制,在你为每个对话挑选的工作目录里被驱动。

::: tip 先配置一个模型
内置 agent 没有自己的模型。对话前先在 **Settings → Models**(或 `coffer model add`)添加一个;你注册的第一个模型成为默认。CLI agent 使用它们各自配置的模型,而非 Coffer 的。
:::

## 从命令行对话

`coffer chat` 与**内置 agent**对话:

```bash
coffer chat -m "我有哪些 MCP 服务器和知识库?"           # 单轮,打印回复
coffer chat                                           # 交互式多轮会话
coffer chat --model <model-id>                        # 为新对话选择模型
coffer chat -c <conversation-id>                      # 恢复一个对话
```

- `coffer model add --name … --provider <anthropic|openai|ollama> --model … [--default]` 注册一个模型;`coffer model list` / `edit` / `rm` 管理它们。
- CLI 对话与桌面、Web 应用展示的是同一批对话 —— 它们保存在 SQLite 中,重启后依然存在。

::: tip 与 Claude Code / Codex 对话
选择 CLI agent 及其工作目录是在应用的**新建对话**对话框里完成的,而非命令行 —— `coffer chat` 始终使用内置 agent。
:::

## 在应用里对话

**Chat** 页是侧边栏的第一个入口:

1. 点击**新建对话**并选择一个 agent。内置 agent 选一个模型;Claude Code / Codex 则选一个**工作目录**。
2. 发送消息,看着回复流式输出。工具调用以可展开的内联卡片形式出现。
3. 需要工具授权的 agent 会显示 **Allow / Deny** 卡片,该轮会暂停直到你决定。(内置 agent 不会暂停。)
4. **Stop** 结束一轮并保留已生成的部分输出。流式进行时输入框被锁定。

## 保留策略

对话遵循一个两阶段生命周期,两个窗口都可在 **Settings → Data** 中配置:闲置对话被自动归档(默认 7 天),随后已归档的对话(及其消息)在归档之后一段时间被删除(默认 30 天)。活跃对话永远不会被删除阶段删除;任一阶段都可关闭。

[技能 →](/zh/guide/skills)
