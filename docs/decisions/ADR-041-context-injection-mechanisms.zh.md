# ADR-041：上下文注入是一个 facet、三种机制，而非一种

> English: [ADR-041-context-injection-mechanisms.md](ADR-041-context-injection-mechanisms.md)

**状态**：Accepted
**日期**：2026-07-09
**决策者**：Yuxing Wu
**相关**：取代 [ADR-040](ADR-040-re-widen-agent-registry.zh.md) 的能力矩阵；spec `004-agent-registry`（FR-003a、FR-043/044）；基于 [ADR-037](ADR-037-rules-runtime-injection.zh.md)（SessionStart 注入）

## 背景

[ADR-040](ADR-040-re-widen-agent-registry.zh.md) 把 `opencode`、`hermes`、`cursor`
重新加为受管 agent，并记录了一份能力矩阵（spec 004 的 FR-003a），声明每个 product
支持哪些 facet。**其中四格是错的。** 对着上游文档和源码重新做第一性核查后发现：

1. **Cursor 有一个文档明载的 `sessionStart` hook。** ADR-040 以"headless 触发
   SessionStart/End 在上游未文档化"为由把它推迟。事实上 `~/.cursor/hooks.json`
   明确文档化了 `sessionStart`，其输出 schema 带一个 `additional_context` 字段
   ——正是 Coffer 的注入点。（其兄弟 `beforeSubmitPrompt` **不能**注入，输出只有
   `{continue, user_message}`。）
2. **opencode 的插件能注入，不只是观察。** ADR-040 记的是"只有进程内 JS 插件回调"。
   `@opencode-ai/plugin` 的 `Hooks` 接口暴露了 `chat.message`（其 `output.parts`
   可变）和 `experimental.chat.system.transform`（可往 system prompt 里 push）。
3. **Hermes 的 session hook 不是"待做"，是死的。** ADR-040 把它推迟为"一种新机制"。
   上游 issue [NousResearch/hermes-agent#2817](https://github.com/NousResearch/hermes-agent/issues/2817)
   确认 `on_session_start`、`on_session_end`、`pre_llm_call`、`post_llm_call`
   "文档里有，但运行时从不调用"——它们只存在于 `VALID_HOOKS` 里。**closed as not
   planned。** 只有 tool hook 真的触发。
4. **Cursor 的 provider 投影确实做不到**——四格里唯一站得住的一格。
   `cursor-agent --help`（v2026.02.27）没有任何 base-URL 参数；`cli-config.json`
   没有 endpoint 键；自定义 base URL 是 IDE-only。

误判的根因是结构性的，不是笔误。`HookInjectionSpec` 恰好只建模了一种投递机制
——*往一个 JSON 配置文件里写一条 shell 命令*——于是任何以别的方式注入上下文的
product 都掉进了"缺席 facet"。这个抽象是按它的**实现**（hook）命名的，而不是按
它的**目的**（把 Coffer 的规则与记忆送到模型面前）命名的。

## 决策

**用 `ContextInjectionSpec` 取代 `HookInjectionSpec`，以 `InjectionMode` 三值
判别**，一值对应一种上游真实存在的机制：

- `SHELL_COMMAND` —— agent 执行 `coffer-hook` 并读取其 stdout。
  Claude Code、Codex、**以及 Cursor**。
- `PLUGIN_DROP` —— agent 只提供进程内 JS/TS 回调。Coffer 落一个薄壳插件文件，
  壳里 spawn 同一个 `coffer-hook` 二进制。opencode、openclaw。
- `INSTRUCTIONS_BLOCK` —— agent 根本没有可用的 hook。Coffer 把载荷渲染进 agent
  instructions 文件里的 marker 块。Hermes。

**三者共享同一个载荷来源**：daemon 的
`GET /api/v1/agents/{agent}/session-context` 端点。只有最后一公里——谁去取、以
什么信封交给模型——不同。这正是三种机制不会退化成三份平行实现的原因。

**本 slice 只实现 `SHELL_COMMAND`。** `PLUGIN_DROP` 与 `INSTRUCTIONS_BLOCK` 是
已识别的扩展点，暂无 descriptor 使用——与 `SkillDeliveryMode` 早已预留
`RULES_MDC` / `EXTERNAL_DIR` 完全同构。服务遇到未实现的 mode 时按缺席 facet 处理
（`HookInstallUnsupported` → 422；`status` 报 `installed=False`）。

**第二个判别字段 `HookFlavor` 承载磁盘形状。** shell-command hook 并非同一种形状。
Claude Code 和 Codex 用 PascalCase 事件名做键、值是 matcher 组；Cursor 用 camelCase
事件名做键、值是扁平命令条目，且文档顶层带一个 `version`。`HookFlavor` 同时决定
`coffer-hook` 打印的 stdout 信封——Claude 是 `hookSpecificOutput.additionalContext`，
Cursor 是顶层 `additional_context`。

**Cursor 安装的命令带 `--dialect` 和 `--event`。** Cursor 的 `hooks.json` 按事件
分键，但它并不契约性地在 hook 的 stdin 里给出事件名。与其依赖一个未经证实的
payload 字段，不如在安装时把事件烘进命令的参数里。由此得出两条：

- **当 `--event` 已给出 SessionStart 时，`coffer-hook` 根本不读 stdin。**
  `sys.stdin.read()` 会阻塞到 EOF，且没有任何东西约束它（5s 超时只管 HTTP）。
  一个把 stdin 留着不关的 agent 会因此卡在自己的启动路径上——而这正是
  failure-is-silent 契约要防的事。只有真的需要 payload 时才去读。
- **cwd 未知时是「省略」，绝不发空串。** daemon 按 `cwd` 最近的 git root 来划定
  记忆与规则的 scope；空串会解析到 **daemon 自己**的工作目录——那是个长驻进程，
  可能正待在一个毫不相干的仓库里。只有「不带 cwd 参数」才真正意味着全局 scope。
  hook 进程继承 agent 的工作目录，所以 payload 缺省时它就是正确来源；若它读不到
  （目录已被删除），则丢掉该参数，bundle 仍会送达、按全局 scope。

**Cursor 的 provider 投影仍是缺席 facet，但要显式说明、而非静默隐藏。** 界面上写明
原因（cursor-agent 锁死 Cursor 后端），而不是把控件悄悄拿掉。

## 影响

- Cursor 获得会话上下文注入——规则与记忆抵达 `cursor-agent` 的方式，和抵达
  Claude Code 完全一样。它从来就不是一个上游缺口。
- facet 现在按目的命名，于是剩下两个 agent 可以靠**新增一种 mode 的实现**来收口，
  而不是去拓宽一个 hook 模型：opencode 与 openclaw 走 `PLUGIN_DROP`，hermes 走
  `INSTRUCTIONS_BLOCK`。
- `hook_install` 的变换接受 `commands: Mapping[HookEvent, str]` 而非单条命令，
  因为 Cursor 需要每个事件一条不同的命令。
- Coffer 识别自有条目时会用 `shlex.split` 解析用户自建的命令，而引号不配对会抛异常。
  一条 Coffer 解析不了的命令按定义就不是 Coffer 的（它写入的每一段都做了引号转义），
  所以解析失败读作「不是我们的」，而不是让 daemon 500。
- 卸载是安装的真逆运算：Coffer 写进一个原本没有 `version` 的 Cursor `hooks.json`
  的顶层 `version`，在文档中再无其他内容时会被一并移除；与其他内容并存的 `version`
  属于该文件，予以保留。
- Cursor 的 config 文件白名单新增 `hooks` 键（`~/.cursor/hooks.json`）。
- **每一处能力缺口从此必须带证据。** 一格写 "N/A"，就得引用使其成立的上游文档、
  参数或 issue；ADR-040 的四格里有三格没有，而这三格全错了。
- **Cursor 的 `sessionStart` 在 headless 下是否触发，尚未实证。** 机制有文档，
  而 marker 探针测试被 `cursor-agent` 要求登录挡住了。间接证据很强（Cursor 文档称
  云端 agent "只运行基于命令的 hook"；Skynet 正是往同一个文件里装了 CLI 专用
  hook）。这是本 ADR 中唯一一条依据文档而非真机探针的论断。

## 备选方案

- **保留 `HookInjectionSpec`，另加一个平行的 `PluginDropSpec`。** 否决：两个 facet
  回答同一个问题（"上下文如何抵达模型？"）意味着每个消费者都要检查两处，而 hermes
  ——两者都不需要——会被永久留在缺口里。
- **彻底放弃 hook，所有 agent 统一用 instructions 文件注入。** 简单且均质，但它
  换掉了动态路径：静态块无法逐轮取最新记忆，SessionEnd 蒸馏也随之消失。否决。
- **在 headless 触发被实证之前，继续推迟 Cursor。** 否决：机制有文档，且安装是可逆的
  （`.bak` + uninstall）。带着一条记录在案的不确定性交付，胜过扣住一个 product
  自己宣传的能力。
