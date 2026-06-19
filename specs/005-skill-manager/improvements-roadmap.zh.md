# Skill Manager —— 改进 Roadmap

状态：**已交付**——四项全部落地（#4 → #3 → #2 → #1）。FR 与验收场景见
`spec.md`；信任层决策见 ADR-027。源自
[`docs/research/agent-skills.md`](../../docs/research/agent-skills.md) 的竞品调研
（[`docs/research/README.md`](../../docs/research/README.md) 中的报告 #3）。调研判定
Coffer 在跨 agent 交付与 SSRF 加固摄取上领先，在四个点上落后。本 roadmap 把这四点
拆成排好序、按 PR 体量的工作，叠加在已发布的 005 skill manager 之上。

英文镜像见 [`improvements-roadmap.md`](./improvements-roadmap.md)。

## 落地顺序

```
#4 frontmatter 对齐   →  #3 信任层（L2）    →  #2 更新检测/钉选   →  #1 发现机制
   (小·前置)              (大·最高杠杆)         (中·独立)            (大·复用 #3/#4)
```

依赖理由：

- **#4 最先**——识别 `allowed-tools` frontmatter 字段，正是信任层（#3）要消费的数据。
- **#1 最后**——浏览即装复用现有的 git-fetch 入库路径，而该路径必须先带上 #3 的内容
  扫描与 #4 的校验，发现机制才骑在其上。
- **#2 与 #3** 互不依赖，可互换；若想更快出可发布成果，可走 4 → 2 → 3 → 1。

每项一个分支/一个 PR，spec 先行：先改 `spec.md`/`spec.zh.md`、`data-model.md`、
`contracts/api.openapi.yaml`，再带测试实现，最后 `make verify`。

## #4 —— agentskills.io frontmatter 对齐（本 PR）

**缺口。** `SkillFrontmatter` 原先只校验 `name` + `description` 是否存在；
`description` 没有长度上限（标准为 ≤1024），可选标准字段（`license`、实验性
`allowed-tools`）被 `extra="allow"` 默默丢弃。

**改动。** `description` 上限 1024 字符（硬 422，与既有 `name` 过长同一路径）；识别并
保留 `license` 与 `allowed-tools`（宽松归一化：列表或分隔字符串 → 归一化列表；格式
异常 → 视作缺省而容忍）。Spec：FR-004 修订、新增 FR-027、两条验收场景。`name` 保留
其字符集的有据超集（容忍下划线）以向后兼容。

**不在范围（推迟到 #2/verify）。** 强制标准的"name == 父目录名"规则——Coffer 写入时
把主库文件夹归一化为 `<name>`，所以它只影响 verify 期的一致性检查，归入 #2。

## #3 —— 信任层 L2（启发式扫描 + 警告）

调研的 #1 最高杠杆缺口，且对 vault 天经地义。**边界：** Coffer 只交付不运行，无法在
运行时强制 `allowed-tools`（那是宿主 agent 的事）。所以 Coffer 的"信任"是入库/启用前
把关，再把风险摆上台面。记录一份新 ADR。

- **L1 清单 + 溯源。** 枚举脚本/可执行文件（扩展名 + shebang + exec 位），记录
  path/size/sha256；读出声明的 `allowed-tools`；呈现 source URL、`git_ref`、入库
  时间、`version_hash`（均已存储）。
- **L2 启发式扫描。** 纯函数 `scan_skill_folder(folder) -> list[Finding]`
  （`severity`、`rule_id`、`file`、`line?`、`message`）。规则：危险 shell
  （`curl … | sh`、`eval`、base64→exec、`rm -rf`、sudo、写出目录外）、网络出口、疑似
  外泄（`~/.ssh`、`~/.aws`、env dump 外送）、`allowed-tools` 与实际行为不符
  （best-effort）、混淆（长 base64/hex blob）。
- **非硬拦。** 入库/启用照常；verdict ≥ high 标记 skill"需确认"，绑定/启用需显式 ack
  （`POST /skills/{name}/acknowledge-risk`，写审计）。扫描在 import、git-fetch、
  update-apply 时执行；结果持久化到 `SkillConfig`（`scan_verdict`、`findings_count`、
  `last_scanned_at`、`ruleset_version`）。
- **Surfaces。** detail 页 findings、list 徽章、`SKILL_SCANNED` /
  `SKILL_RISK_ACKNOWLEDGED` 审计事件、CLI `coffer skill scan <name>`。

## #2 —— 更新检测 + 钉选

`update_ops.apply_update` 已经对比 SKILL.md 哈希，但只是"拉了就改"。新增：

- `check_for_updates(ref)`——复用 `source_fetcher` 浅拉源、校验、算候选哈希、对比但
  不应用；返回 `UpdateStatus {available, current_hash, available_hash, rename_detected}`。
- `SkillConfig` 缓存字段（`update_available`、`last_update_check_at`、
  `available_version_hash`）供 list 徽章。
- 钉选：分支 `source.ref` 为跟随，tag/sha 为钉死；`pin_to_resolved` 把 `source.ref`
  写回当前 commit sha；钉死的 skill 不再 nag。
- 仅按需（按钮 / `coffer skill check-updates`）；v1 不做定时轮询（local-first）。并入
  #4 推迟的 verify 期 name==dir 检查。
- Surfaces：`POST /skills/{name}/check-update`、list 字段、CLI、UI 徽章。

## #1 —— 发现机制（浏览即装）

当前必须知道 git URL；竞品提供浏览即装的目录。

- `CatalogSource` 端口。v1：curated 静态目录（内置 JSON 或 pinned 索引 URL），列
  `{name, description, git URL, ref, publisher}`；可选接已知 registry
  （anthropics/skills、vercel-labs/skills、稳定的话接 agentskills.io API）。拉远程
  索引是允许的（local-first ≠ 无远程调用），做成 opt-in / 可刷新。
- install 复用 git-fetch 入库路径（SSRF guard + 校验 + #3 扫描），所以发现骑在 #3/#4
  之上。与 #2 交叉显示"有新版本"。
- Surfaces：`GET /catalog/skills`、`POST /catalog/refresh`、UI 目录页、CLI
  `coffer skill search`。

## 定位（非代码，随 #3 一起出）

主打调研强调的差异化："一个库，所有 agent，无需逐平台重传，自动跟随 + 例外——且每个
skill 入库即扫描。"等信任层让这句话成真后，更新 `docs-site/guide/skills.md` 与 README。
