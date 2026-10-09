---
title: coffer uninstall
description: "Remove Coffer from this Mac: disconnect the agents, remove the skill links, start at login, the binaries and the installer's PATH lines, then stop the daemon."
pageClass: cli-ref
---

# coffer uninstall

Remove Coffer from this Mac: disconnect the agents, remove the skill links, start at login, the binaries and the installer's PATH lines, then stop the daemon. ~/.coffer stays unless --delete-data.

```sh
coffer uninstall [OPTIONS]
```

本页与 `coffer uninstall --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

With the desktop app, this opens its uninstall dialog, where you confirm.

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--yes, -y` <span class="cli-chip">选项</span> | 开关 |  | Do not ask before uninstalling |
| `--delete-data` <span class="cli-chip">选项</span> | 开关 |  | Also delete ~/.coffer (not the Keychain); asks for 'delete my data' at a terminal, whatever else is given |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
