# AGENTS.zh.md

> English: [AGENTS.md](./AGENTS.md)

Coffer 项目的 AI 代理操作手册（Claude Code、Codex、Cursor 及未来的 agent）。会话开始时阅读。

## 1. 一览

| 属性         | 值                                                                |
| ------------ | ----------------------------------------------------------------- |
| **项目**     | Coffer —— 本地优先的 AI agent 保险箱。单用户。坚定开源。          |
| **方法论**   | 基于 Speckit 的规格驱动开发（SDD, Spec-Driven Development）。     |
| **语言栈**   | Python 3.12+（后端），TypeScript 5.x（前端）。                    |
| **真理来源** | `.specify/memory/constitution.md`（原则）；`specs/`（产品契约）。 |
| **默认分支** | `main`。                                                          |
| **许可证**   | MIT。                                                             |

## 2. 会话开始时阅读的文件

按顺序：

1. **`.specify/memory/constitution.md`** —— 长期适用的原则与不变量。
2. **`AGENTS.md`**（即本文件英文版）。
3. 与当天工作范围相关的 **`agents/<topic>.md`**：
   - [`agents/sdd.md`](./agents/sdd.md) —— spec 目录布局、验收场景、端到端可交付规则。
   - [`agents/workflow.md`](./agents/workflow.md) —— 分支、Conventional Commits、AI 署名、PR 流程、合并策略。
   - [`agents/stack.md`](./agents/stack.md) —— 后端（Python / FastAPI / SQLite）+ 前端（TS / React / Vite / Tailwind / shadcn）。包含文件大小限制、分层架构导入规则、wire-contract 规则。
   - [`agents/testing.md`](./agents/testing.md) —— 四层测试（unit / integration / contract / e2e）、验收标记、mocking 原则。
4. 涉及 spec 的工作时，阅读对应的 **`specs/<NNN>-<short-name>/spec.md`**。

资料冲突时：**constitution 优先**，并向用户指出不一致。

## 3. 会话协议

```
1. 把今天的范围回讲给用户确认
2. 切到正确的分支（见 agents/workflow.md）
3. 以小且可提交的颗粒度推进（每个逻辑变更一次提交）
4. 开 PR 前：make verify
5. 最终推送前 squash 成一个 commit
6. 开 PR —— 在 PR 已开的状态停下，等待用户明确的合并指令
```

**会话内的硬性停止条件：**

- 25 条实质性消息内仍无已提交的 checkpoint → 停下来与用户对齐。
- 同一工具失败重复 3 次 → 停下来找根因，不要无脑重试。
- 任何与 constitution 或本文件冲突的情况 → 停下来询问，不要绕开。

## 4. 自决 vs 询问

用户已经把架构层面的决定权下放给你。**默认自决并解释**，不要过度提问。

| 决策                                                | 行动                                                                                                                                 |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| 架构 / spec 内部范围 / 技术选型                     | **自决**。记录到 spec 的 `plan.md` 或 `docs/decisions/ADR-NNN.md`。                                                                  |
| 单个 spec 内的命名 / API 形态                       | **自决**。记录到 spec 的 `plan.md`。                                                                                                 |
| 增加 / 删除一个 feature spec                        | **暂停**。需要用户确认。                                                                                                             |
| 发布一个 tag                                        | **暂停**。需要用户确认。                                                                                                             |
| 强推 / rebase 已发布分支 / 删除带有未合并工作的分支 | **暂停**。始终确认。                                                                                                                 |
| `git push origin main`（直接推 main）               | **绝不**。一律走 PR。                                                                                                                |
| 合并一个已开的 PR                                   | **暂停**，除非用户明确授权（「merge it」或等价的直接指令）。见 [`agents/workflow.md`](./agents/workflow.md) 的「Merge Policy」一节。 |

## 5. 常用命令

```bash
make install                # 一次性：venv + 后端 + 前端依赖
make verify                 # 快速路径（lint + unit + integration + contract）
make verify-all             # 加 e2e
make dev                    # 并行起 backend (:8000) + frontend (:5173)

git checkout -b feature/<short-name>
git add <files> && git commit -m "feat(<scope>): <subject>"
git push -u origin feature/<short-name>
gh pr create --fill --base main
```

详见 [`agents/workflow.md`](./agents/workflow.md) 与 [`agents/testing.md`](./agents/testing.md)。

## 6. 维护 `agents/`

只有同时满足以下**两个**条件时，才把一个 topic 文件拆成子目录：

1. 文件超过 **~300 行**。
2. 它包含**互相独立的子主题**，读者会单独 bookmark。

否则保持扁平。举例：只有当 `stack.md` 同时变得超过 ~300 行**且**后端 / 前端两块都各自写成长文时，才拆成 `agents/stack/{backend,frontend}.md`；同时更新 §2 的链接。

## 7. 双语文档规则

本仓库里的每一份散文式文档，都是「英文真理源 + 中文翻译伴随版」成对出现。所有现有英文文档都已经有对应的 `.zh.md` 伴随版；新文档必须成对创建。

**路径约定。** 去掉 `.md` 后缀，加上 `.zh.md`，文件放在同一目录。**绝不能**在 `.md` 后面叠 `.zh.md`（没有 `CLAUDE.md.zh.md`，只有 `CLAUDE.zh.md`）。

```
AGENTS.md            ↔  AGENTS.zh.md
CLAUDE.md            ↔  CLAUDE.zh.md        （不是 CLAUDE.md.zh.md）
agents/sdd.md        ↔  agents/sdd.zh.md
docs/quickstart.md   ↔  docs/quickstart.zh.md
specs/001-…/spec.md  ↔  specs/001-…/spec.zh.md
```

**适用范围。**

- `AGENTS.md`、`README.md`、`CONTRIBUTING.md`、`SECURITY.md`。
- `agents/` 下的全部文档。
- `docs/**/*.md`（quickstart、decisions/ADR 等等）。
- `specs/**/*.md` 中除 `tasks.md` 之外的全部文件（spec.md、plan.md、research.md、data-model.md、quickstart.md）。
- `.specify/memory/*.md`（constitution、architecture、roadmap）。

**不适用的范围。**

- 代码、代码注释、标识符、JSON/YAML 配置。
- Conventional Commit 提交信息、分支名、PR 标题与描述 —— 保持英文（见 [`agents/workflow.md`](./agents/workflow.md)）。
- 自动生成的产物（OpenAPI yaml、lockfile、构建输出）。
- 给工具填空用、不会从头读到尾的脚手架模板 —— 例如 `.specify/templates/*.md`（Speckit 脚手架模板）、`specs/*/tasks.md`（AI/coder 的任务清单）、`.github/PULL_REQUEST_TEMPLATE.md`（GitHub 自动预填）。
- 内容微薄的指针 / marker 文件 —— 例如 `CLAUDE.md`（只有一行指向 `AGENTS.md`）。
- 仓库以外的任何东西（Claude Code skill、harness 配置等）。

**写作规则。**

1. 英文版是真理源。先改英文，再翻译。
2. 任何新增或修改英文文档的 commit，**必须**在同一个 commit 里同步更新它的 `.zh.md` 伴随版。审阅者**必须**拒收两边不同步的 commit。
3. 任何新增英文文档的 commit，**必须**同时新增 `.zh.md` 伴随版；不允许「之后再翻译」这种 stub。
4. 标题、锚点、链接目标在两个版本之间保持一致 —— 行文里只链接英文文件，读者通过伴随版切换语言，不通过深链。
5. 代码块、文件路径、命令片段、标识符在中文版里**原样保留**，只翻译散文部分。

**可发现性。** 在每份文件顶部交叉链接：英文版写 `中文版: [<name>.zh.md](./<name>.zh.md)`；中文版写 `English: [<name>.md](./<name>.md)`。
