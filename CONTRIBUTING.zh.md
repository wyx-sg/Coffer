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

## 安全

不要在公开 issue 里报告安全问题。见 [`SECURITY.md`](./SECURITY.md)。

## 许可证

提交贡献即表示你同意你的贡献以 [MIT License](./LICENSE) 授权。
