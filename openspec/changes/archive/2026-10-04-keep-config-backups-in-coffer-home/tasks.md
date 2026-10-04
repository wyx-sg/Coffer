## 1. Backups in Coffer's home
- [x] 1.1 `config_backups_dir()` in `infrastructure/vault/home.py`
- [x] 1.2 `ConfigFileStore` copies prior content to a timestamped file there; `latest_backup`
- [x] 1.3 Docstrings and ports stop describing `.bak`

## 2. Retention
- [x] 2.1 `config_backups` policy (domain default, tree sweep keeping each file's newest, wiring)
- [x] 2.2 Storage usage counts it under History
- [x] 2.3 Settings > Data > History row, en and zh copy

## 3. Copy and docs
- [x] 3.1 Dialog and confirmation copy says a backup is kept in Coffer's folder
- [x] 3.2 Docs site (en, zh), ADR, specs and data models

## 4. Tests
- [x] 4.1 Store unit tests, retention test, updated `.bak` assertions, frontend test
