# 为 Coffer 贡献代码

> English: [CONTRIBUTING.md](./CONTRIBUTING.md)

感谢你对 Coffer 感兴趣。本文是面向**人类贡献者**的入口。AI agents（Claude Code、Codex、Cursor）请改读 [`AGENTS.md`](./AGENTS.md)。

## 快速开始

```bash
git clone https://github.com/wyx-sg/Coffer.git
cd Coffer
make install                       # venv + backend deps
make hooks                         # wire pre-commit + commit-msg hooks
make dev                           # backend daemon (:8000)
```

## 项目基准

- **[`.specify/memory/constitution.md`](./.specify/memory/constitution.md)** —— Coffer 是什么、永远不该变成什么。
- **[`AGENTS.md`](./AGENTS.md)** —— 运行手册；人类同样可以读，规则一视同仁。

## 工作流

1. 从 `main` 拉分支（命名规范见 [`agents/workflow.md`](./agents/workflow.md)）。
2. 如果改动是用户可见的，**先**写或更新 `specs/<NNN>-<short-name>/spec.md`（见 [`agents/sdd.md`](./agents/sdd.md)）。
3. 按对应测试层级补测试，再写实现（见 [`agents/testing.md`](./agents/testing.md)）。
4. 本地跑 `make verify-all`。
5. 提 PR；title 必须符合 Conventional Commits。
6. 等 review 与合并。分支以 squash-merge 合入。

## 测试

四个层级，详见 [`agents/testing.md`](./agents/testing.md)：

```bash
make verify-unit          # < 5s
make verify-integration   # < 30s
make verify-contract      # < 5s
make verify-e2e           # MCP shim + daemon round-trip

make verify               # unit + integration + contract (skip e2e)
make verify-all           # everything
```

## 锁文件

`backend/uv.lock` 是后端依赖版本的唯一事实来源。它由 [uv](https://docs.astral.sh/uv/) 从 `backend/pyproject.toml` 生成，把每个传递依赖都钉到确切的版本 + 哈希。

- **CI 与发布以 frozen 方式安装。** `.github/workflows/ci.yml` 与 `release.yml` 跑 `uv sync --frozen`，它只安装 `uv.lock` 里的确切版本，并在锁文件与 `pyproject.toml` 不同步时失败。正是这一点让打 tag 的发布产物可复现 —— 它们永远不会按 `pyproject.toml` 里的 `>=` 下界来构建。
- **`pyproject.toml` 声明下界；`uv.lock` 钉版本。** 在 `pyproject.toml`（人类可读的约束）里改依赖；绝不手改 `uv.lock`。
- **改依赖后刷新锁文件。** 在 `pyproject.toml` 里新增、升级或移除依赖后，运行：

  ```bash
  make lock        # = uv lock --project backend
  ```

  把更新后的 `uv.lock` 与 `pyproject.toml` 的改动放在同一次提交里。如果某个 PR 的锁文件与 `pyproject.toml` 漂移，CI 的 frozen 安装会拒绝它。

- **本地安装**（`make install`）走的是 editable 的 `pip install`，所以日常开发不需要 uv。只有刷新锁文件这一步以及 CI/发布安装才走 uv。

## 安全

不要在公开 issue 里报告安全问题。见 [`SECURITY.md`](./SECURITY.md)。

## 许可证

提交贡献即表示你同意你的贡献以 [MIT License](./LICENSE) 授权。
