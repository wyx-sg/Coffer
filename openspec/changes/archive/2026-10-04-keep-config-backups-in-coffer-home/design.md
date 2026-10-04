## Where backups go

`~/.coffer/config-backups/`, resolved by `infrastructure/vault/home.config_backups_dir()`
next to `skill_data_dir()`; it is a runs-class directory (records of what happened:
never synced, pruned by retention), not part of the vault. The store reads `HOME`
at the moment of each write, like every other path, so tests that repoint `HOME`
move it too.

## Layout

`config-backups/<basename>-<12 hex of sha256(absolute path)>/<UTC timestamp>.<ext>`

- The folder key is the file's name plus a hash of its absolute path: readable
  when browsing (`settings.json-3fa91c0d2b7e`), unambiguous when two agents (or
  two config directories) have a file of the same name. An agent-type level was
  considered and dropped: the store is given paths, not agents, and a custom
  `CLAUDE_CONFIG_DIR` has no reliable type from its path.
- File name: `%Y%m%dT%H%M%S%fZ` plus the original suffix, so names sort in time
  order and keep a type that editors recognise. A name collision (two writes in the
  same microsecond) appends `-1`, `-2`.
- The directory and its files are mode 0700 / 0600: config files hold tokens.
- The backup is a copy made BEFORE the atomic replace, exactly the old safety
  property; the copy's mtime is the time it was taken (not the original's), which
  is what retention measures.

## Generations

The three-generation rotation (`BACKUP_COPIES`) goes. Every write keeps its own
copy; retention, not a count, bounds the folder. The newest backup of each file
is the one an undo wants, found with `latest_backup(path)` (newest name).

## Retention

`config_backups` is a file policy registered beside `skill_data`. The sweep is a
recursive pass over `config-backups/` that treats each folder as one file's history:
the newest backup in a folder is never a candidate, however old; every other file
older than the window is deleted; empty folders are removed (never the root);
symlinks are neither followed nor deleted. The preview counts with the same rule.
Default 30 days, `forever` allowed. `skill_data`'s sweep is untouched (the
"keep newest per folder" rule is an option of the shared tree sweep).

## Not done

No migration: `.bak`, `.bak.1`, `.bak.2` already beside agent configs stay, and
nothing reads them. No `coffer path config-backups`: backups are for the user to
find from Settings and the docs, not for scripts.
