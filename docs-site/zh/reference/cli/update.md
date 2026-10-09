---
title: coffer update
description: "Upgrade Coffer to the newest release and restart the daemon on it."
pageClass: cli-ref
---

# coffer update

Upgrade Coffer to the newest release and restart the daemon on it.

```sh
coffer update [OPTIONS]
```

本页与 `coffer update --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

The installer's binaries are downloaded, checked against the release's SHA256SUMS and swapped in place; the desktop app installs its own signed update; a source checkout is upgraded with git.

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--check` <span class="cli-chip">选项</span> | 开关 |  | Only say whether a newer release exists |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
