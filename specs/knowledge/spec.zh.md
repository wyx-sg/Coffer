# 功能规格：知识层

> English: [spec.md](./spec.md)

**Created**: 2026-05-22（当时叫 *Memory*）· **与知识库合并**: 2026-09-10 · **精简为纯文件**: 2026-09-12
**Status**: Accepted
**目录名**: 本 spec 位于 `specs/knowledge/`，这个目录名就是所有入链和 `scripts/audit_acceptance.py` 所依据的 spec id。

**Input**: Coffer 只存一样东西——**关于用户工作环境的知识**：他的代码仓库、服务、项目、对接的人，以及值得跨会话留存的决策和陷阱。它就是一个 **Markdown 文件目录**。agent 靠读目录和 grep 找到需要的东西，就像它导航一个代码库；人靠打开文件夹找到。**没有任何派生索引**：不分块、不向量化、不需要对账，所以一方写下的东西另一方立刻就能看到。见 [Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md)。

## 这一层服从的原则

**知识由人和 agent 共同管理。** 下面每一条决定都由它推出：元数据放在文件里而不是数据库行里，因为只有文件是双方都能看见的；目录是生成的而不是存下来的，因为存下来的那份会和人在文件管理器里看到的漂移；人的编辑器和 agent 的 `write` 触及的是同一批字节，中间没有任何东西。

## 2026-09-12 移除了什么，为什么

对本机实际安装的审计发现这一层大部分从未执行过：`embedding_config` 是空表，`.history/` 在磁盘上不存在，50 篇文档里 50 篇都是 `converter: passthrough`，而一个月调用历史里每一次知识工具调用都发生在某个 agent 建语料的那一天。两个结构性失误解释了这一切——属性被做成了目录（`notes/` ÷ `docs/`、`global` ÷ `project-<ULID>` ÷ collection），而一旦 embedding 从未被配置，索引买到的就只剩 agent 自己会做的排序。

移除：任意格式转换与转换器注册表；`.raw/` lane；外部源追踪；`source_mode` 与再转换锁；lane 划分；由 cwd 推导的 scope、自动创建与 `project-<ULID>` 命名；FTS5、sqlite-vec、混合融合、分块、读时惰性重建索引与显式重建；per-scope 检索配置；scope 显示标签。随之移除 11 张表。

## 用户场景与测试

### 用户故事 1 — 一个知识库，所有 agent（优先级 P1）

开发者上午用 Claude Code，下午用 Codex。上午某个 agent 记下某服务的登录态归 `account.session` 所有；下午另一个 agent 找到了它，因为两者读的是同一个目录。没有副本会漂移，因为只有一份。

**独立测试**：从一个 MCP 客户端写入一条事实；从另一个身份不同的客户端列目录并把文件读回来。

### 用户故事 2 — collection 是人的归档方式，也是授权单位（优先级 P1）

有些知识是公司内部细节，不能让他运行的每个 agent 都拿到；有些是业余项目的，给谁都无所谓。开发者有意创建一个 collection，把敏感材料放进去，只授权给可以看的 agent。collection 内部他爱怎么嵌套怎么嵌套，Coffer 既不知道也不关心。

**独立测试**：创建两个 collection，其中一个只授权给单个 agent，确认另一个 agent 的目录和读取都不包含它。手工建一个嵌套文件夹，确认目录能走进去。

### 用户故事 3 — 没有索引也能找到对的文件（优先级 P1）

agent 需要一条自己说不出确切措辞的事实。它先列出 collection、读每个的一句话描述，下钻到最可能的那个，读那里的标题和描述，然后要么直接读某个文件，要么用刚学到的字面串去 grep。

**独立测试**：对一个有内容的 collection，逐层调用目录并确认返回了标题和描述；grep 一个中文串并确认命中的文件与行。

### 用户故事 4 — 人用自己的工具做整理（优先级 P2）

开发者从 Finder 把一篇 Markdown 丢进某个 collection，在自己的编辑器里改掉一行错的，删掉一篇过时的。每一次改动对下一次 agent 调用都是即时生效的，不需要任何导入步骤，因为文件**就是**知识。

**独立测试**：在 Coffer 之外添加一个文件，确认它出现在目录和 grep 里；改一个文件，确认 `read` 返回的是新字节。

### 用户故事 5 — agent 知道这一层存在（优先级 P1）

Coffer 投递的一个 skill 告诉 agent 这一层在这里、怎么用。它走的是已经在投递 Coffer 其它 skill 的同一条通道，所以每个被管理的 agent 都能拿到，不需要 hook，也不往 agent 自己的记忆里写任何东西。

**独立测试**：在绑定了某个受管 agent 的情况下，确认知识 skill 出现在它的 skill 目录里，并且写明了「先看目录再 grep」这套动作。

### 用户故事 6 — 人要求的时候才整理（优先级 P3）

笔记会堆积、会重复。开发者触发一次 tidy，它先归档每个旧版本，再合并改写。他也可以让它定时跑，但必须先自己打开。

**独立测试**：对一个有重复内容的 collection 跑一次 tidy；确认 `.history/` 里有旧版本，且归档副本永远不出现在 grep 结果里。

## 验收场景

### Scenario: a written note lands as a markdown file with a readable name

### Scenario: frontmatter carries title, description and actor

### Scenario: a file added out-of-band is visible to the next call

### Scenario: the catalogue lists collections with their README description

### Scenario: the catalogue lists one level of a collection

### Scenario: the catalogue walks into a nested directory

### Scenario: grep matches a literal string across a collection

### Scenario: grep matches CJK content

### Scenario: grep skips hidden directories

### Scenario: read returns a file by path

### Scenario: creating a collection registers a knowledge resource

### Scenario: an unknown collection is an error, never auto-created

### Scenario: a collection outside an agent's scope is absent from its catalogue

### Scenario: a collection outside an agent's scope cannot be read

### Scenario: write creates a file and replaces an existing one

### Scenario: delete removes the file from disk

### Scenario: a path escaping the knowledge root is rejected

### Scenario: the five built-in knowledge tools appear in the client tool list

### Scenario: tidy archives the prior revision before rewriting

### Scenario: tidy is a no-op when no internal model is configured

### Scenario: the tidy worker stays off unless enabled

### Scenario: the knowledge skill is delivered to a managed agent

### Scenario: the viewer renders content read-only and offers open and reveal

### Scenario: migration rewrites ULID documents into named files in collections

## 需求

### 存储

- **FR-001**: 知识 MUST 以 Markdown 文件形式存放在 `~/.coffer/knowledge/<collection>/` 下。文件是**唯一真相**；系统 MUST NOT 维护任何对其内容的派生索引——没有 chunk 表、没有全文索引、没有 embedding，因此也没有任何形式的对账。
- **FR-002**: 文件的**路径就是它的身份**。frontmatter 里 MUST NOT 有独立的 id 字段，任何地方 MUST NOT 有 id 到路径的映射。文件名 MUST 是由标题推出的人类可读 slug；重名时追加短后缀。
- **FR-003**: 每个文件 MUST 带 YAML frontmatter，包含 `title`、`description`、`actor`（`agent` | `user`）、`created_at`、`updated_at`，且仅此而已。`description` 是**必填**而非可选：没有带排序的索引之后，目录就是检索界面，一个不描述自己的文件等于找不到。
- **FR-004**: 一个 collection MAY 含有任意深度的子目录。系统 MUST NOT 赋予它们含义、MUST NOT 要求它们存在、MUST NOT 创建它们。
- **FR-005**: 隐藏条目（点开头）MUST 被排除在目录和 grep 之外。`.history/` 是系统自己写的唯一一个。
- **FR-006**: 每个会成为路径片段的名字 MUST 通过穿越防护，且路径构造 MUST 只存在于一个模块中。

### collection

- **FR-010**: 一个 **collection** 是知识根目录下的一个顶层子目录，同时是一个 `knowledge` Resource。它 MUST 由人通过 REST/CLI/UI 有意创建，MUST NOT 由读取、写入或 agent 的工作目录自动创建。
- **FR-011**: 系统 MUST NOT 从 agent 的 cwd 推导任何边界。MUST NOT 存在 `global` scope、`project-<ULID>` 命名、git 根解析，以及 scope 到项目根的映射表。
- **FR-012**: collection MUST 支持 Resource 框架的 **per-agent scope**：一个 agent 只能看见、grep、读取和写入为它激活的 collection。agent 的调用 MUST 覆盖它被授权的**每一个** collection——MUST NOT 存在把已授权 collection 排除在默认之外的规则。
- **FR-013**: collection 的一句话描述 MUST 取自其目录下 `README.md` 的首段，没有该文件时为空。它 MUST NOT 存在数据库里。
- **FR-014**: per-agent 授权仅在 MCP 工具面执行，系统 MUST 如实描述这一点：它防的是误召回，不是有意的文件系统访问。

### 检索

- **FR-020**: 目录 MUST 在调用时通过遍历目录、读取 frontmatter **即时生成**。系统 MUST NOT 把它物化成文件或表。
- **FR-021**: `list` MUST **一次走一层**：不带路径时返回调用方可见的每个 collection，各带 README 描述与文件数；带路径时返回该目录的直接子目录和文件，每个文件带 `title` 和 `description`。
- **FR-022**: `grep` MUST 对调用方可见的 collection 的文件运行 ripgrep，支持字面或正则、递归匹配，返回文件、行号与命中行。命中数 MUST 有上限，响应 MUST 标记是否被截断。
- **FR-023**: `read` MUST 按路径返回文件全文。MUST NOT 有分块、段落粒度或 `top_k`。
- **FR-024**: 任何 surface 上 MUST NOT 存在 `search` 工具，也 MUST NOT 存在任何检索模式。

### 写入

- **FR-030**: `write` MUST 依据 `title`、`description` 和正文创建文件，或在给定已存在路径时替换它。写入 MUST 是一次普通的文件写——没有 LLM、没有转换、没有索引步骤。
- **FR-031**: `delete` MUST 从磁盘上删除文件。
- **FR-032**: 系统 MUST NOT 接受上传或转换任何格式。人添加文档的方式是把 Markdown 放进目录；文件系统就是摄入界面。

### 工具与投递

- **FR-040**: Coffer 的 MCP 网关 MUST 在 `coffer__` 前缀下暴露恰好**五个**内置知识工具：`list`、`grep`、`read`、`write`、`delete`。
- **FR-041**: 内置调用 MUST 继续记录一行 `mcp_invocations`（工具、谁、耗时、结果——不含参数与内容）。写入或删除 MUST 额外记录一条以 agent 为 actor 的审计事件。
- **FR-042**: Coffer MUST 通过既有的 skill 投递通道（spec [skill-manager](../skill-manager/spec.md)）投递一个**知识 skill**，教会「先看目录再 grep」这套动作。它 MUST NOT 安装 hook、注入会话上下文，或写入任何 agent 自己的记忆文件。

### 整理

- **FR-050**: 系统 MUST 提供针对某个 collection 的有界 agentic **tidy** 过程，由内部模型连接驱动，其工具面就是上述五个操作。它 MUST 在任何覆盖或合并之前把文件旧版本复制进 `.history/`。没有配置内部连接时 MUST 是干净的 no-op。
- **FR-051**: tidy MUST 可从 UI 和 `coffer knowledge organize` 手动触发。后台 worker MAY 按间隔运行它，由一个**默认关闭的安装级设置**控制。
- **FR-052**: `.history/` MUST 以点开头，因此被排除在目录和 grep 之外。

### Surface

- **FR-060**: `/api/v1/knowledge` 下的 REST API 与 `coffer knowledge` CLI 组 MUST 覆盖：创建 collection、按路径列目录、读文件、写文件、删文件、触发 tidy。删除 collection 走 Resource 框架（`DELETE /api/v1/resources/knowledge/{name}`）。MUST NOT 存在上传、重建索引、check-sources、update-source、embedding 或 per-scope 设置端点。
- **FR-061**: Web UI MUST 把知识根呈现为**单一树**——没有 lane tab——通过统一文件预览以**只读**方式渲染内容，并对文件及其所在文件夹提供「在外部编辑器打开」和「在文件管理器中显示」。MUST NOT 有应用内编辑器。
- **FR-062**: 读取响应 MUST 带上文件的绝对路径及其所在文件夹的绝对路径。

### 迁移

- **FR-070**: 一条 migration MUST 删除所有知识专属的表——`documents`、`chunks`、六张 `documents_fts*`、`embedding_config`、`knowledge_scope_labels`、`knowledge_scope_project_roots`——并加守卫，使缺少其中任何一张的数据库仍能升级。
- **FR-071**: 在删表**之前**，一次数据迁移 MUST 重写磁盘语料：每篇文档的 `title`（今天只存在数据库里）成为它的文件名和 frontmatter，文件从 `notes/` 和 `docs/` 移入 collection，`.raw/` 被删除。现有 scope 落成两个 collection：关于内部系统的文档进 `shopee`，项目自己的进 `coffer`。迁移 MUST 是单向的，**不留任何兼容垫片**。

### 约束

- **FR-080**: 任何知识层模块 MUST NOT 引入索引、embedding 或转换类库，且 `sqlite-vec`、`fastembed`、mem0、chroma、LlamaIndex MUST NOT 出现在依赖集中。`markitdown` 保留，因为入站渠道附件仍需抽取文本（spec [channels](../channels/spec.md) FR-030）——importlinter 把它限制在唯一的消费者 `infrastructure.chat` 内，使它无法漂回本层。
- **FR-081**: 知识层 MUST NOT 向数据库新增任何表。一个 collection 就是 kind 无关的 `resources` 表里的一行，和其它 Resource 一样。

## 成功标准

- **SC-001**: 一个 agent 写下的事实，另一个 agent 能通过目录读到，中间没有任何索引步骤。
- **SC-002**: 人在 Coffer 之外添加或编辑的文件，下一次调用就能返回，不需要导入、重建索引或对账。
- **SC-003**: 只被授权某个 collection 的 agent，无法通过任何内置工具看到另一个。
- **SC-004**: 这一层不持有任何知识专属的数据库表，也不持有任何文件内容的派生副本。
- **SC-005**: 对语料的一次 grep 能返回命中的文件与行，中文内容同样如此，且不需要分词器。

## 假设

- 语料规模保持在目录塞得进 agent 上下文的范围内。按每条约 40 tokens 算，到几百篇都很从容；本机语料是 51 篇。越过之后的答案是一个真正的语义检索栈，为那个需求而建——不是这里移除的那一套，那一套从未被配置过。
- tidy 会在没有审阅环节的情况下改写文件，所以 `.history/` 就是全部的安全网。它默认关闭正是因为这个。
