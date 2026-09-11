# Quickstart —— Coffer Skill Manager

> English: [quickstart.md](./quickstart.md)

在 Coffer 中集中管理符合 AgentSkills 标准的 skill 文件夹，然后投递到一个或多个已注册的 AI agent（spec agent-registry）。

## 前置条件

- Coffer 的 daemon 正在运行（运行 `coffer daemon`，或用 `coffer open` 启动它并打开 Web UI）。
- 至少有一个 agent 已注册（自动检测或 `coffer agent add` —— 参考 spec agent-registry 的 quickstart）。
## 导入已有的 skill 文件夹

如果你已经在 `~/.claude/skills/my-skill/` 里有一个 skill，把它纳入 Coffer 管理：

```bash
coffer skill import ~/.claude/skills/my-skill
```

Coffer 会：

1. 读取 `SKILL.md`，校验 frontmatter（`name`、`description` 必填）。
2. 把文件夹拷到 `~/.coffer/skills/my-skill/`（规范 master）。
3. 注册一个 kind 为 `skill` 的 Resource。
4. 以「已启用、未设置 scope」注册，因此对所有 agent 生效。
5. 在每个 agent 的 `config_dir/skills` 文件夹下创建一个指向 master 的目录 symlink（POSIX）或 junction（Windows）。

之后，**所有 agent** 都能在它们自己的 `config_dir/skills` 文件夹下看到这个 skill。

## 决定哪些 agent 收到某个 skill

一个 skill 送达某个 agent，当且仅当该 skill 处于**启用**状态，且该 agent 在这个
skill 的**启用范围（scope）**内。控制项只有这两个：既没有按 agent 的 follow 开关，
也没有 per-binding 的开关。

scope 是框架自己那条按 agent 的激活轴（[ADR per-agent-resource-scope](../../docs/decisions/per-agent-resource-scope.md)），
所以 skill 用的就是所有支持 scope 的 kind 共用的那组命令——未设置 scope 即对所有
agent 生效：

```bash
coffer scope show skill:my-skill
coffer scope set skill:my-skill --agents codex        # 只给 codex
coffer scope set skill:my-skill --no-agents           # 休眠：谁也不给
coffer scope clear skill:my-skill                     # 回到所有 agent
```

禁用 skill 本身则一次性把它从所有 agent 收回，重新启用后按 scope 授予的范围还回去：

```bash
coffer resource disable skill:my-skill
coffer resource enable skill:my-skill
coffer skill list --json | jq '.items[] | select(.name=="my-skill") | {enabled, scope, bindings}'
```

任一侧的改动都会立即调谐：已投递但掉出 scope 的副本、或属于刚被禁用的 skill 的副本，
都会被回收。Web UI 里对应的就是 Skill 列表页的启用开关与 skill 详情页的启用范围控件。

如果目标位置已经有别的东西（普通文件或非 Coffer 的 symlink），操作会被拒绝，除非加 `--force`。`--force` 会先把既有目标备份到 `<path>.coffer-backup-<timestamp>`，再创建 link。

## Adopt Coffer 尚未管理的 skill

如果 agent 的 skill 文件夹里有手工放置的 skill（手工复制或由其他工具安装），
Coffer 可以列出并 adopt 它们。扫描覆盖两个 agent 类型的
`<config_dir>/skills`，外加 Codex 的 `~/.agents/skills`：

```bash
coffer skill unmanaged claude-code
coffer skill unmanaged claude-code --json
```

Coffer 托管的链接与 Codex 的 `.system` 之类的内部条目绝不会出现。指向 Coffer
主库之外的 symlink 会作为 foreign link 列出——只呈现、永不可 adopt（来源
未知）。

把一个合法条目 adopt 进主库（它会被校验、移动到 `~/.coffer/skills/<name>/`、
注册，并作为托管链接重新投递给该 agent）：

```bash
coffer skill adopt claude-code my-skill --location skills
```

或者把不想要的条目从 agent workspace 中删除（仅磁盘——绝不动主库内容或
binding）：

```bash
coffer skill rm-unmanaged claude-code my-skill --location skills
```

## 校验 drift

如果你（或别的工具）在某个 agent 的 `config_dir/skills` 文件夹里动过文件，让 Coffer 报告它：

```bash
coffer skill verify
```

报告会按 drift 类别列出条目并附建议处置方式。Coffer **不**会自动修复 drift —— 由你决定是重新启用还是禁用。

## 浏览 skill 文件（只读）

Web UI 把 skill 的 master 文件夹以文件树展示，并在只读查看器中查看单个文件。要修改文件，经查看器的「在外部编辑器中打开」/「在文件管理器中显示」操作，在自己的外部编辑器或文件管理器中打开该文件（或其所在文件夹）。同样的读取数据也可通过 REST API 获取，且每个条目都带磁盘绝对路径。

以递归树列出 master 文件夹：

```bash
curl -s http://127.0.0.1:8000/api/v1/skills/my-skill/files \
  -H "X-Coffer-Token: $COFFER_TOKEN" | jq
```

```json
{
  "root": {
    "name": "my-skill",
    "path": "",
    "abs_path": "/Users/me/.coffer/skills/my-skill",
    "type": "dir",
    "size": null,
    "children": [
      {
        "name": "scripts",
        "path": "scripts",
        "abs_path": "/Users/me/.coffer/skills/my-skill/scripts",
        "type": "dir",
        "size": null,
        "children": [
          {
            "name": "run.py",
            "path": "scripts/run.py",
            "abs_path": "/Users/me/.coffer/skills/my-skill/scripts/run.py",
            "type": "file",
            "size": 42,
            "children": []
          }
        ]
      },
      {
        "name": "SKILL.md",
        "path": "SKILL.md",
        "abs_path": "/Users/me/.coffer/skills/my-skill/SKILL.md",
        "type": "file",
        "size": 87,
        "children": []
      }
    ]
  }
}
```

读取单个文件内容（`path` 查询参数相对 master 文件夹根）：

```bash
curl -s "http://127.0.0.1:8000/api/v1/skills/my-skill/files/content?path=SKILL.md" \
  -H "X-Coffer-Token: $COFFER_TOKEN" | jq
```

```json
{
  "path": "SKILL.md",
  "abs_path": "/Users/me/.coffer/skills/my-skill/SKILL.md",
  "folder_abs_path": "/Users/me/.coffer/skills/my-skill",
  "content": "---\nname: my-skill\n...",
  "truncated": false,
  "binary": false,
  "size": 87
}
```

读取被限制在 master 文件夹内：越界路径（`../...`、绝对路径或越界 symlink）以 `400` 拒绝。超过 256 KiB 的文件返回 `truncated: true`；非文本文件返回 `binary: true` 且 `content` 为空。

## 移除 skill

```bash
coffer skill rm my-skill
```

Coffer 先移除每个 agent 的 symlink，再删除 binding，最后删除 master 文件夹。审计日志中会记录这次移除及对应 config 快照。

## 磁盘布局长这样

```
~/.coffer/skills/
  my-skill/
    SKILL.md
    scripts/...
    references/...
    .coffer.meta.json     # 源 provenance（仅供取证）

~/.claude/skills/my-skill        → symlink 指向 ~/.coffer/skills/my-skill
~/.codex/skills/my-skill         → symlink 指向 ~/.coffer/skills/my-skill
```

对上述任一路径下的编辑都会落在 master 上（symlink 是透明的），不存在拷贝 drift。

## 排错

**"SKILL.md missing required frontmatter field"** —— 打开你要导入的文件夹，确认顶部 YAML 中 `name` 与 `description` 均非空。

**"Refusing to overwrite existing target"** —— 目标 link 位置存在非 Coffer 的文件或目录。要么自己清掉，要么加 `--force` 让 Coffer 先备份再替换。

**"Symlink creation failed; falling back to copy"** —— 你的文件系统不支持目录 junction（Windows + FAT32 或某些网络共享）。Coffer 已把 skill 内容拷到目标位置，并在审计中记录这次降级；UI 会在该 binding 上显示警告标记。

**在 `~/.coffer/skills/<name>/` 内手工编辑后看到 drift** —— 这是正常的：master 是可编辑的事实来源；其他 agent 通过自己的 symlink 在下一次读取时即可看到改动。
