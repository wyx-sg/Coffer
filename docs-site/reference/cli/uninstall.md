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

This page matches what `coffer uninstall --help` prints. Add `--help` to any command below to see its options in the terminal.

With the desktop app, this opens its uninstall dialog, where you confirm.

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--yes, -y` <span class="cli-chip">option</span> | flag |  | Do not ask before uninstalling |
| `--delete-data` <span class="cli-chip">option</span> | flag |  | Also delete ~/.coffer (not the Keychain); asks for 'delete my data' at a terminal, whatever else is given |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
