---
title: 编写技能库
description: 组织一个由 Coffer 投递的技能库，让同一份主体服务所有组织：环境差异放进 profile，平台细节留给载体技能。
---

# 编写技能库 {#writing-skill-libraries}

单个技能很好写。但一个要投递给多个智能体、跨多个组织或项目使用的技能库，就需要规则。没有规则的话，同一套方法会被复制进五个技能，某个平台的命令参考会被粘进工作流里，每个技能还会悄悄写死某一家公司的主机和命名约定。

本页讲如何组织这样一个库：技能分哪几类、环境差异如何表达、技能文件夹如何布局，以及如何通过 Coffer 编写和投递技能库。技能格式本身以及 Coffer 如何存储和投递技能，见[技能](/zh/guides/skills)。

## 两类技能 {#two-kinds-of-skill}

库中的每个技能都属于以下两类之一。

| | 产品领域 | 载体 |
| --- | --- | --- |
| 负责 | 一套**方法**：如何把一件事做好，与任何平台无关 | 一个**平台的细节**：主机、凭据、命令、API 结构 |
| 例子 | 从日志排查故障、提交改动供评审、提工单、验证已部署的改动 | 日志平台的 CLI、工单系统的 API、容器平台、数据库门户 |
| 随组织变化吗？ | 不变。差异放在它的 profile 里 | 变。它*就是*组织相关的那部分 |
| 有 `profiles/` 吗 | 有 | 没有；连接信息放在 `connection.md` 里 |

产品领域决定*该做什么*：某条线索指向哪个服务、搜索的时间窗口要多宽、评审请求的标题必须长什么样。*怎么做*则交给解析后的 profile 指定的载体。这样，只需改一个 profile 值，同一份产品主体就能对接另一个日志平台或工单系统。

载体对一个平台了如指掌，但对方法一无所知。它可以是你写的技能，也可以是其他团队发布的技能。

### 委托就是一次真正的技能调用 {#delegation-is-a-real-skill-call}

产品领域需要做平台操作时，就调用载体。它从不把载体的指令拷进自己的主体里。原因有两个：

- **归因。** 载体技能可能带有自己的 Hook、用量统计或权限检查。只有技能真正被调用时它们才会触发。把它的命令内联复制过来，就绕过了它们。
- **腐坏。** 载体随平台一起变化。你主体里的那份命令副本，会在载体下一次发布时过时，而且没有任何东西会提醒你。

参考资料也一样。产品领域从不携带平台的查询语言语法或参数参考。某一步需要确切语法时，就去问载体。profile 可以*写出*语言的名称（`query_language: <name>`），让方法能提到它，但语法本身留在载体那里。

### 载体取值 {#carrier-values}

profile 用以下几种形式之一指定载体：

| 值 | 含义 |
| --- | --- |
| `Skill(<name>)` | 以真正的技能调用方式调用该技能。绝不复制它的命令。 |
| `Skill(<plugin>:<name>)` | 随智能体插件发布的技能，智能体会以插件前缀列出它。规则相同：调用它，绝不复制它。 |
| `<domain-name>` | 本库中的另一个领域。加载它的 `SKILL.md` 并遵循其路由表。 |
| 一个裸命令，例如 `gh` | 直接调用这个 CLI。 |
| `local-file` | 没有平台；写到磁盘。 |
| `none` | 这个环境还没有已知的载体。如实说明并询问用户。 |

当两种能力不在同一个平台上时，一个领域可能需要不止一个载体类的键。搜索日志和把线索对应到负责它的服务是两件不同的事，所以日志排查领域第一件读 `carrier`，第二件读 `service_lookup_carrier`。部署领域读 `deploy_trigger` 来启动流水线，读 `carrier` 来查看实际运行的是什么。永远不要假设一个载体在某平台上能做一件事，就也能做相邻的另一件事。

在 profile 中指定某个载体之前，先读一读该载体自己的 `SKILL.md`，确认它记载了你的主体将向它请求的操作。当它做不了主体需要的某件事时，把这个缺口记录在 profile 里（例如列出工单载体无法设置的字段），并让主体告诉用户，而不是悄悄丢掉这个值或编造一次调用。

## Profile {#profiles}

产品领域把**方法**放在主体里，把关于**环境**的一切都从 profile 中读取：调用哪个载体、哪些主机属于该组织、有哪些环境、分支和标题如何命名。主体读键，profile 提供值。切换环境从来不需要编辑主体。

### 扁平的 profile，一次覆盖 {#flat-profiles-one-override}

领域的 `profiles/` 文件夹包含 `default.md`，外加你实际工作的每个环境各一个文件：

```text
profiles/
  default.md        every key the body reads, with a generic value or none
  <org>.md          one environment: its hosts and every value that differs
  <org>-<other>.md  another environment, added only when one exists
```

环境文件之间没有继承。每个文件对它的环境都是完整的，所以一个值要么在那个文件里，要么在 `default.md` 里，别无他处。同一组织内出现第二个环境时，它得到一个自己的同级文件，而不是叠在第一个之上的一层；在两个文件之间复制几行，比一条没人能预测的合并链便宜得多。

解析就是一次覆盖：取 `default.md`，再用所选环境文件设置的每个键替换它。映射逐键合并；标量或列表直接替换默认值。

### 选择环境 {#selecting-the-environment}

每个领域的 `SKILL.md` 都带有同一段文字，一字不差（下面是它在 `SKILL.md` 中的英文原文，lint 按原文比对）：

> **Profile.** Read `profiles/default.md`. Then pick an environment: the one the user names for this request; otherwise the profile whose `remote_hosts` lists the host of the current repository's `origin` remote (`git remote get-url origin`); otherwise none. If an environment was picked, read its file and let every key it sets replace the default. Use the merged values for the rest of this skill; never mix values from two environment files.

在整个库中保持完全一致，意味着只需学一条规则、只有一处需要修改；可移植性 lint 会检查这段文字有没有偏移。

### Profile 文件是数据 {#profile-files-are-data}

frontmatter 存放设置。文件正文最多几行，说明这是什么环境。对不明显的值，在旁边用一行 YAML 注释解释：

```markdown
---
remote_hosts: [git.example.com]
carrier: Skill(example-log-search)
service_lookup_carrier: none   # no verified clue-to-service lookup exists yet
query_language: <name>
timezone: <area>/<city>
branch:
  format: "{author}/{type}/{ticket}/{slug}"
---

# <org>

The organisation's log platform, reached through its own skill.
```

更长的设计理由——某个键为什么存在、为什么要和另一个拆开——属于本指南或该领域的设计记录，而不是一个智能体每次运行都要读的文件。

### 键属于领域 {#keys-belong-to-a-domain}

每个领域定义自己的键，`default.md` 声明其中每一个，即使值是 `none`。键按主体需要什么来命名（`carrier`、`review.title_template`、`layers.api`），从不按某个特定平台命名。描述同一环境在不同系统中的多个值——工单项目 key、数据平台的项目代码——都是该环境文件中的普通键，而不是单独的层。

### 诚实的取值：`none` 和 `ask` {#honest-values-none-and-ask}

`none` 是一个陈述：还没有任何环境为此指定载体或来源。读到 `none` 的主体会说明哪个键没有设置，并询问用户。它绝不退而使用恰好在旁边的某个载体，也绝不猜测。

`ask` 对约定的作用相同：`local_path: ask` 或 `version_signal: ask` 表示约定未知，所以主体会询问，而且不会把得到的回答升级成一条固定约定。

当主体需要的某个键完全不存在时，主体会写出键名以及应该定义它的文件，然后停下。

## 文件夹布局 {#folder-layout}

```text
<domain>/
  SKILL.md                    routing only; under 500 lines
  sub-skills/<intent>/SKILL.md
  functions/NN-<step>.md      only for a domain with one ordered flow
  references/<topic>.md
  profiles/default.md
  profiles/<org>.md
  scripts/lint_portable.py
  scripts/test_*.py
  agents/openai.yaml          optional interface metadata for Codex
```

| 部分 | 内容 |
| --- | --- |
| `SKILL.md` | frontmatter、标准的 Profile 段落、一张从用户意图到子技能或函数的路由表，以及一个 Boundaries 部分。不含工作流步骤。 |
| `sub-skills/` | 用户会单独请求的事情。每个都有自己的 `SKILL.md`，带 `name` 和 `description`。 |
| `functions/` | 同一个流程中不会被单独调用的有序步骤。按位置编号。 |
| `references/` | 本领域中多个子技能或函数共享的方法和策略：一份手册、一个 schema、安全规则。 |
| `profiles/` | `default.md` 和每个环境各一个文件（见 [Profile](#profiles)）。这是唯一可以出现组织相关字符串的地方。 |
| `scripts/` | 确定性的检查，每个都带测试。 |
| `connection.md` | 仅限载体：主机、密钥位置、后端。 |

区分 `sub-skills/` 和 `functions/` 的检验标准：会有人单独请求这件事吗？“开一个评审请求”和“这个路径归哪个服务”是子技能。“运行预检”或“执行用例 3”只有在手头已有一份计划时才有意义，所以它们是函数。一个领域可以两者都有；一个测试编排领域有八个编号函数，外加一个用于校验计划文件而不执行它的子技能。

### Frontmatter {#frontmatter}

```yaml
---
name: <domain>
description: "Use when … NOT … — that is <other-domain>."
metadata:
  profiles: [default, <org>]
  requires: [<base-skill>]
---
```

`metadata.profiles` 是该领域附带的 profile 文件的索引。`metadata.requires` 在[声明的依赖](#declared-dependencies)中介绍。顶层的 `requires:` 是另一回事：技能驱动的命令行工具（`gh`、`jq`），可带最低版本和登录检查，Coffer 会检查它们，缺失时交给你的智能体去安装——见[命令行工具](/zh/guides/clis)。封装某个 CLI 的载体技能应该在那里声明它。同一个键的映射形式还可以写出技能的命令需要的 Coffer 密钥，如 `requires: {commands: [psql], secrets: [orders-db]}`，这样技能的 **依赖** 标签页和总览会在某个密钥未设置时告诉使用者——见[技能需要的密钥](/zh/guides/skills#secrets-a-skill-needs)。同一个映射还可以在 `tools:` 下按名字（即它们在 Coffer 里的名字）写出技能调用的 MCP 服务器和自定义工具分组，如 `requires: {commands: [psql], secrets: [orders-db], tools: [orders-api]}`：**依赖** 标签页会在**工具**下列出它们，工具关闭的技能会进入**需要处理**。Coffer 不认识的名字会被跳过，警告显示在[命令行工具](/zh/guides/clis)页面上——见[技能需要的工具](/zh/guides/skills#tools-a-skill-needs)。映射下的其他键会被拒绝并给出警告。包含 `: `（冒号加空格）的描述要加引号；不加的话它是无效的 YAML，技能会解析失败。描述最多 1024 个字符；更长的 Coffer 会拒绝导入。

### 文件夹卫生 {#folder-hygiene}

- **技能内不放虚拟环境。** venv 里有解析到文件夹之外的符号链接，而 Coffer 会拒绝导入含有任何此类链接的文件夹。把它放在外面，比如 `~/.cache/coffer-skill-venv`，并在 `SKILL.md` 中写明重建它的那一行命令。
- **不放测试缓存。** 把 pytest 的 `cache_dir` 指到文件夹之外，并用 `PYTHONDONTWRITEBYTECODE=1` 运行。
- **不放密钥。** 技能文件夹会通过保险库同步进入 git，所以绝不存放任何值。把密钥作为独立密钥存进 Coffer（`coffer secret set secret/<name>`），并以 `coffer://secret/<name>` 引用它——写在 `connection.md` 里，或作为技能附带的 env 文件中的值。需要它的命令在 `coffer run` 下运行，它只在该命令的环境中设置这个值：

  ```sh
  coffer run --secret PGPASSWORD=orders-db -- psql -h db.internal orders
  coffer run --env-file connection.env -- ./query.sh
  ```

  不要保留 `~/.coffer/secrets/<name>.env` 这样的明文文件；密钥页面上的**查找明文密钥**会找出它们并把它们移入存储。见[密钥](/zh/guides/secrets)。在 `requires: {secrets: [...]}` 下写出技能用到的每个密钥的名称，这样 Coffer 能在它未设置时告诉你。

## 描述 {#descriptions}

智能体只凭描述来挑选技能，所以描述承担了路由的职责。每条描述都要说清三件事：

1. **何时使用**，用用户真正会说的话。
2. **差异从哪里来**：“come from a profile, so one body serves every log platform”（来自 profile，所以一份主体服务所有日志平台）。
3. **它不是什么，以及该去哪里。**

第三点就是同能力歧义规则。凡是两个技能都可能回答同一个请求的地方，两条描述都要划清界线并互相点名：

> NOT for entering a single already-known container to read its logs — that is the container domain. NOT a syntax reference for the platform's query language — ask the carrier for that.
>
> （不用于进入某个已知容器读取日志——那是容器领域的事。不是平台查询语言的语法参考——去问载体。）

子技能的描述在其领域内做同样的事。在 `SKILL.md` 的 Boundaries 部分重复这条边界，并在那里解释理由。

## 可移植性 {#portability}

产品主体在 `profiles/` 之外不包含任何组织相关的字符串：没有内部主机名、没有服务名、没有工单前缀、没有用户路径、没有平台品牌名。某一步需要这类值时，就读一个 profile 键。

`scripts/lint_portable.py` 负责强制执行这一点。它不区分大小写地扫描 `profiles/` 之外的每个 `.md` 和 `.txt` 文件，比对一份禁用词列表，外加一些匹配无法逐个列举的名称族的模式；每处命中都会给出文件、行号和匹配内容，并以 1 退出。frontmatter 的 `metadata:` 块不参与检查，因为一份 profile 名称列表是索引，不是指令。`name` 和 `description` 仍会被扫描。

每次编辑后都运行它。它标出一个正当的词时，要有意识地调整模式；看得见的误报，好过悄无声息的泄漏。

同一个脚本还会检查 `SKILL.md` 是否原样带有标准的 Profile 段落。因为每个技能是单独投递的（见下文），每个领域都带着自己的一份 `lint_portable.py` 及其测试；让这些副本在整个库中保持一致。

## 共享基础技能，而不是共享文件路径 {#shared-base-skills-never-shared-file-paths}

当多个领域用到同一套方法（如何收集证据、如何写一份发现报告）时，把这套方法放进一个独立的小**基础技能**，让每个领域通过智能体的技能机制按名称加载它，比如 Claude Code 的 Skill 工具。

永远不要用相对路径引用另一个技能的文件，比如 `../other-skill/references/report.md`。Coffer 按每个技能自己的生效范围，把它独立地投递给每个智能体。对正在读你技能的智能体来说，那个文件夹可能根本不存在，而路径会失败，还没有清楚的报错。

基础技能的描述要说明它由其他领域加载，而不是由用户直接调用：

```yaml
description: "Evidence and report rules shared by investigation domains. Loaded by those domains when they write findings; not something a user asks for directly."
```

一个库通常需要两个：一个管**证据和报告**（原样引用证据、遮蔽密钥、只报告你实际触及的证据层、简要和详细两种报告模板、在宣称载体不可达之前先试一试），一个管**写操作把关**（预览、确认“现在做这个改动”、确认不能延伸、绝不重试结果不确定的写操作、回读校验、走工具的正门）。每个需要报告或写操作的领域都加载它们，而不是把规则重述一遍。

在同一个技能内部，相对路径没问题：`references/`、`profiles/` 和 `scripts/` 是一起走的。

## 声明的依赖 {#declared-dependencies}

加载另一个技能的技能要声明它：

```yaml
metadata:
  requires: [<base-skill>]
```

这项声明是给人看的：修改某个基础技能时，在整个库上运行 `grep -l "requires:.*<base-skill>"` 就能列出所有需要复查的领域；设置某个技能的生效范围时，把基础技能的生效范围也扩展到同样的智能体。Coffer 不强制执行它。

运行时，如果加载某个必需的技能失败，主体会如实说明并写出该技能的名称。它绝不临时拼凑一个替代品来顶替缺失的方法。

由 profile 值指定的载体不列在 `requires` 中；它们随环境变化，由 `none` 规则来覆盖。

## 运行时纪律 {#runtime-discipline}

这些规则要写进每个产品主体，通常放在 Boundaries 或 Notes 部分。

### 先尝试，再宣称能力缺失 {#try-before-claiming-a-capability-is-missing}

在告诉用户某样东西无法访问或未授权之前，先调用解析后的 profile 指定的载体，并引用它实际返回的错误。智能体已连接工具的列表不能作为证据：列表里可能有一个同类文档的、不相干且未授权的连接器，而真正能干活的技能已经装好却从未被尝试过。这种失败在用户看来像权限问题，其实并不是。

### 只走正门 {#front-doors-only}

载体的安全检查就在它的命令里。调用这些命令；绝不为了绕过检查而导入脚本的内部实现或直接调用它的 API。给载体写 CLI 时，不要导出一个能不经命令层就发出写操作的客户端，并用测试确认它做不到。

### 证据经得起精简 {#evidence-survives-brevity}

发现要原样引用关键证据：日志行、错误正文、数据行。只裁剪到相关部分，遮蔽密钥，保留时间戳和 ID。即使回复必须很短，比如在手机聊天里，也是如此。精简证据周围的文字，绝不精简证据本身。一个没有附上所依据那一行的总结，是无法核查的。

### 说出你没能解析的东西 {#say-what-you-could-not-resolve}

当某个模板占位符、profile 键或必需的输入无法解析时，写出它的名字，然后停下。绝不编造一个团队会当作承诺来读的值，比如评审人、日期或工单 key。

## 编排型领域 {#orchestrator-domains}

有些产品领域驱动的是其他领域，而不是单个载体。一个端到端验证已部署改动的领域会触及 API、数据库、容器平台和日志平台，而每一层都已经有自己的领域在服务。它负责流程和安全策略，把每一层委托出去。

### 层通过 profile 映射到领域 {#layers-map-to-domains-through-the-profile}

```yaml
layers:
  api: <api-domain>
  db: <database-domain>
  container: <container-domain>
  logs: <log-investigation-domain>
deploy_confirm: <deploy-domain>
environments:
  candidates: [test, staging, live]
  default: test
  per_call_confirm: [live]
```

在 `default` 中每一层都是 `none`：不存在通用的 API 测试工具。一个函数触及某个键未设置的层时，会写出这个键，并询问由哪个工具来执行这一层。相关但不同的判断要放在不同的键上：`deploy_confirm`（“这是不是正确的代码”）与 `layers.container`（“这个容器在干什么”）是分开的，即使同一个平台两个问题都能回答。

编排型领域绝不重新实现某一层。如果一个请求只需要一层，就把用户引到那一层的领域，而不是跑完整个流程。

### 关卡 {#gates}

把流程写成编号的函数，函数之间有明确的关卡：

| 关卡 | 规则 |
| --- | --- |
| 计划评审 | 计划写好并展示出来；在用户批准或修改之前，什么都不运行。只有只读检查可以在这道关卡之前运行。 |
| 变更确认 | 每一次会产生变更的调用都要确认。在 `per_call_confirm` 中的环境里，每次调用、每一次都要确认。其他环境中，用户可以一次性预先授权一份已评审计划中的所有变更。批准计划永远不等于确认变更。 |
| 恢复 | 每一次已执行的变更都要撤销，校验基线，报告残留。永不跳过，即使运行中途被终止。 |

### 只读与变更纪律 {#read-only-and-mutation-discipline}

- 预先把每一步归类为只读或会产生变更。计划中每个会产生变更的用例都自带撤销步骤。
- 编排者是纯粹的测试者：发现环境缺陷时，它停下来，报告缺陷并建议修复方法。它不会为了让自己继续下去而执行 DDL、修改配置或重启服务。
- 前提条件是被确认的，而不是被制造的。验证领域通过部署领域确认改动已部署；它从不触发部署。
- 把计划的 schema 放在 `references/` 中，并用脚本校验它，这样格式错误的计划会在任何东西运行之前就失败。

## 编写流程 {#authoring-workflow}

在 `~/.coffer` 之外、你自己的文件夹里编写（示例用的是 `~/src/skills/<domain>`）。添加技能会把文件夹拷进 `~/.coffer/vault/skills/`；在存储内部编写，就等于把一个文件夹导入到它自己身上。

```sh
# 1. Author and test in the authoring root
cd ~/src/skills/<domain>
~/.cache/coffer-skill-venv/bin/pytest -q scripts
~/.cache/coffer-skill-venv/bin/python scripts/lint_portable.py .
```

然后从 **Skills → Add skill → From a folder**（选编写目录）添加这个文件夹。Coffer 会校验并投递它，技能页面上的**检查副本**确认投递情况。

第一次导入之后，以编写目录作为唯一的事实来源：

- 做正式改动时，编辑编写目录，重新运行测试和 lint，然后再从 **Skills → Add skill → From a folder** 添加一次，并在冲突那一行选择**替换**。
- 做快速修复时，编辑主文件夹（`~/.coffer/vault/skills/<domain>/`，或技能的**文件**标签页）中的文件；智能体下次读取时就会看到改动。把同样的改动也应用到编写目录，否则下一次**替换**会把它覆盖掉。
- **检查副本**报告主副本与每个智能体已投递链接之间的偏移，**修复**把缺失或被改指向的链接放回去。

当一个新领域取代了几个旧的单一用途技能时，要等新领域端到端跑通之后，再删除旧的（技能的 **⋯ › 删除…**），然后确认智能体的技能文件夹里没有残留的过期链接。

## 设计一个新领域 {#designing-a-new-domain}

1. **说出方法。** 用一句话写出这个领域负责、而任何平台都不负责的东西。写不出来的话，它就是一个载体。
2. **找出邻居。** 列出所有可能回答同一请求的技能，并双向写好 NOT 子句。
3. **拆分意图。** 决定哪些步骤用户会单独请求（`sub-skills/`），哪些只存在于某一个流程中（`functions/`）。
4. **列出 profile 键。** 主体需要的每个主机、名称、约定和载体都成为一个键。如实设置 `default.md`，没有通用答案的地方写 `none` 或 `ask`。
5. **核实每个载体。** 读载体自己的 `SKILL.md`，确认它记载了主体将向它请求的内容。把缺口记录在 profile 中。
6. **你用到的每个环境写一个文件。** 每个文件自身都是完整的；只有真的出现第二个环境时，才添加同级文件。
7. **把共享的方法提取成基础技能。** 如果另一个领域已经有同样的规则，就把它们提取出来，按名称加载，并声明 `metadata.requires`。
8. **复制 lint。** 从现有领域原样拿来 `lint_portable.py` 及其测试，再加上领域专用的校验器和它们自己的测试。
9. **写主体。** `SKILL.md` 只放 Profile 段落、路由和边界。加上运行时规则：先尝试载体再宣称它缺失、引用证据、写出没能解析的东西。
10. **检查。** 测试通过，lint 干净，每个环境文件合并到 `default.md` 之上后得到你期望的值，文件夹里没有 venv、缓存或密钥，必需的基础技能的生效范围覆盖同样的智能体。然后导入并校验。

## 相关 {#related}

- [技能](/zh/guides/skills)——技能格式、导入、生效范围、编辑与偏移
- [保险库同步](/zh/guides/vault-sync)——技能文件夹如何到达你的其他机器
- [密钥存储](/zh/guides/secret-store)
