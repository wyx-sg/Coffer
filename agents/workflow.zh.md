# Workflow — 分支、提交、PR、合并策略

> English: [workflow.md](./workflow.md)

涵盖：分支命名、Conventional Commits、AI 联合作者署名、PR 流程、合并策略。

## 分支

### 允许的前缀

| Prefix                  | Purpose                                    | Example                            |
| ----------------------- | ------------------------------------------ | ---------------------------------- |
| `feature/<short-name>`  | New functionality scoped to a spec         | `feature/mcp-servers-crud`         |
| `fix/<short-name>`      | Bug fix scoped to a spec                   | `fix/mcp-servers-list-cursor`      |
| `docs/<short-name>`     | Documentation only                         | `docs/contributing-rewrite`        |
| `refactor/<short-name>` | Internal restructuring, no behavior change | `refactor/extract-credential-port` |
| `chore/<short-name>`    | Deps, tooling, CI, project meta            | `chore/upgrade-fastapi-to-0.115`   |

规则：

- 全程 kebab-case。
- short name 一般映射（或描述）受影响的 spec 文件夹（`specs/001-mcp-servers/` → `feature/mcp-servers-...`）。分支名不必带数字前缀。
- 从最新 `main` 拉分支：`git checkout main && git pull --ff-only && git checkout -b <prefix>/<name>`。
- 合并后分支自动删除（squash merge 策略）。

## 提交

### Conventional Commits 1.0

```
<type>(<scope>): <subject>

<body>

<footer>
```

- **Type**：`feat | fix | docs | refactor | perf | test | build | ci | chore | revert`。
- **Scope**：受影响 spec 或区域的描述性名称（`mcp-servers`、`clis`、`ui`、`build`、`ci`）。不用数字 `NNN` 前缀——保持可读。
- **Subject**：祈使现在时，小写，无句号，≤ 72 字符。

### Footer

```
Fixes #123
Refs 001-mcp-servers, 003-skills
BREAKING CHANGE: <description>
Co-authored-by: Claude <noreply@anthropic.com>
```

### 示例

```
feat(mcp-servers): aggregate upstream MCP tools through one stdio endpoint

Implements the coffer-as-MCP-aggregator behavior: registered upstream
MCP servers' tools are merged and re-exposed on the daemon's MCP HTTP
endpoint. Satisfies 001-mcp-servers acceptance scenarios 3–5.

Refs 001-mcp-servers
Co-authored-by: Claude <noreply@anthropic.com>
```

```
fix(mcp-servers): missing pagination cursor in list endpoint

Added regression test in 001-mcp-servers spec.md acceptance scenario
"list servers with cursor".

Fixes #42
Co-authored-by: Claude <noreply@anthropic.com>
```

### AI 联合作者署名

当 AI agent 实质参与某次提交时，加 `Co-authored-by` 署名。邮箱是一种非官方约定（GitHub 把这一行渲染为多作者署名；邮箱不一定真实存在）：

| Agent              | Co-author email                                                     |
| ------------------ | ------------------------------------------------------------------- |
| Claude (Anthropic) | `noreply@anthropic.com`                                             |
| Codex (OpenAI)     | `noreply@openai.com`                                                |
| Cursor             | `noreply@cursor.sh`                                                 |
| Other              | use the agent's documented address; otherwise the platform vendor's |

若多个 AI 合作完成同一次提交，逐行列出每个 `Co-authored-by:`。

不该加的场景：

- 纯工具产出（`pip install --upgrade`）—— 是人的提交。
- 机器人机械性提交（dependabot 等）—— 它们自带 bot 身份。

## Pull Request

### 标准流程

1. 从 feature 分支向 `main` 开 PR。
2. PR 标题遵守 Conventional Commits（同样 72 字符上限）。
3. PR 描述：
   - **What** 改了什么。
   - **Why** 为什么。
   - **How to test**（或：「由 `spec.md` 验收场景 X、Y 覆盖」）。
   - **Spec references**。
   - **Screenshots** 涉及 UI 改动时附截图。
   - **Breaking changes** 显式声明。
4. CI 全绿（评审前每个并行 job 必须通过）。
5. **Squash merge** —— 保持 `main` 线性。
6. 分支自动删除。

### 卫生规则

- **一个 PR 一个提交** —— 最终推送前 squash（`git reset --soft main && git commit -m "<final-subject>"`）。
- **Subject + PR title 72 字符上限** —— PR 标题与 squash 后的提交保持一致。
- **先 `gh pr edit --title` 再 `git push --force-with-lease`** —— 每次快照都让标题与 squash 提交同步。
- **PR 标题和正文与 squash 后的提交保持同步** —— 每次 force push 前再核对一遍。

### 每次 force-push 前的自查清单

1. PR 标题还和 squash 后的 subject 一致吗？
2. PR 正文还能描述当前 diff 真正包含的内容吗？
3. 测试方案准确吗？

任一答案为「否」，先修再 force-push。标题 + 正文一起改，一批搞定。

### 作者工作流速查

```bash
git checkout main && git pull --ff-only
git checkout -b feature/<short-name>
git add <files> && git commit -m "feat(<scope>): <subject>"
make verify
git reset --soft main && git commit -m "<final-subject>"   # squash
git push -u origin feature/<short-name>
gh pr create --fill --base main
```

## 合并策略

### 默认：停在 PR 已开

PR 开好后，agent 停下并汇报。agent **不**自主合并——等待人类授权。

### 例外：用户显式授权

只有当下面**全部**满足时，agent 才**可以**执行 `gh pr merge --squash`：

1. 用户在对话中给出**明确、直接的授权**（如「merge it」、「merge PR #N」、「ship it AND merge」）。「looks good」「this is ready」这类隐性信号本身**不**构成授权。
2. CI 全绿（所有并行 job）。
3. 自评走过一遍，零未决问题。「批准但还有一处小修」**不**算零问题。
4. PR 标题 + 正文仍与 squash 后的提交 subject + diff 匹配。

任一条件含糊 → 合并前先问。默认停下来。

### 自评收敛

PR 自评在 ≤ 4 轮内收敛，回报递减：

- **第 1 轮**：真 bug、死代码、spec 漂移、测试缺口、安全项。
- **第 2 轮**：第 1 轮修改引入的文档漂移、边界脆弱点。
- **第 3 轮**：第 2 轮修改引入的细枝末节（类型、位置、命名）。
- **第 4 轮**：风格细节（内联 import、措辞前置）。

如果剩下的都只是观感问题、CI 全绿、用户也表达了合并意向，第 3 轮即可停。别为了理论上的完美继续推（第 5 轮往后基本捞不出东西）。

### 禁止 force-merge / 直推

即便有用户授权，**永远不要**：

- force-push 到 `main`。
- 直推 `main`（一切变更走 PR）。
- 合并 CI 红的 PR。
- 合并 subject 违反 commitlint 的 PR。

### 恢复

如果 `main` 上的某个合并提交有缺陷：

1. 新开一个 PR（用 `git revert -m 1 <merge-sha>` 回滚）。
2. 在描述中附上原 PR # 作为上下文。
3. 走正常评审。

**永远不要** force-push 到 `main` 来「撤销」合并。
