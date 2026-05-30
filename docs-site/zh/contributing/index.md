# 为 Coffer 贡献代码

感谢你对 Coffer 感兴趣。本页是面向**人类贡献者**的入口。AI agents（Claude Code、Codex、Cursor）请改读仓库根目录中的 `AGENTS.md`。

## 快速开始

```bash
git clone https://github.com/wyx-sg/Coffer.git
cd Coffer
make install    # venv + backend deps
make hooks      # wire pre-commit + commit-msg hooks
make dev        # backend daemon (:8000)
```

## 项目基准

- **`.specify/memory/constitution.md`** —— Coffer 是什么、永远不该变成什么。
- **`AGENTS.md`** —— 运行手册；人类同样可以读，规则一视同仁。

## 工作流

每次贡献都遵循以下六个步骤：

1. 从 `main` 拉分支（命名规范见 [Conventional Commits 与 git 工作流](/zh/reference/conventions/workflow)）。
2. 如果改动是用户可见的，**先**写或更新 spec —— 见 [规范驱动开发（SDD）](/zh/reference/conventions/sdd)。每项特性都从 spec 开始，代码跟随 spec，而非反过来。
3. 按对应测试层级补测试，再写实现。
4. 本地跑 `make verify-all`。
5. 提 PR；title 必须符合 **Conventional Commits** 格式。
6. 等 review 与合并。分支以 squash-merge 合入 `main`。

### Conventional Commits

PR 标题和 commit subject 必须遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范：`type(scope): description`。pre-commit hook 会强制检查。完整规则、分支命名及合并策略见 [Conventional Commits 与 git 工作流](/zh/reference/conventions/workflow)。

### 规范驱动开发（SDD）

所有用户可见的改动都需要在实现开始**之前**编写或更新 spec —— 即 `specs/<NNN>-<short-name>/spec.md`。spec 是合约，实现必须满足它。完整 SDD 规范见 [规范驱动开发（SDD）](/zh/reference/conventions/sdd)。

## 测试

四个层级，提 PR 前请先跑完：

```bash
make verify-unit          # < 5s
make verify-integration   # < 30s
make verify-contract      # < 5s
make verify-e2e           # MCP shim + daemon round-trip

make verify               # unit + integration + contract (skip e2e)
make verify-all           # everything
```

## 安全

不要在公开 GitHub issue 里报告安全问题。见 [安全策略](/zh/contributing/security)。

## 许可证

提交贡献即表示你同意你的贡献以 [MIT License](https://github.com/wyx-sg/Coffer/blob/main/LICENSE) 授权。
