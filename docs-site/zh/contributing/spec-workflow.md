---
title: 规格驱动的工作流
description: Coffer 如何使用 OpenSpec：能力的组织方式、需求与场景怎么写、propose-apply-archive 的 change 工作流、验收标记，以及什么时候该写决策记录（ADR）。
---

# 规格驱动的工作流 {#spec-driven-workflow}

Coffer 的产品契约用 [OpenSpec](https://github.com/Fission-AI/OpenSpec) 编写。本页解释规格如何组织、如何编写一条需求、一个行为变更如何走完 propose、apply 和 archive 的流程，以及场景如何与测试关联。在修改任何用户能观察到的东西之前，先读这一页。完整的约定见 [`.agents/openspec.md`](https://github.com/wyx-sg/Coffer/blob/main/.agents/openspec.md)。

## `openspec/` 的两半 {#the-two-halves-of-openspec}

- `openspec/specs/` 描述系统**现在**做什么。
- `openspec/changes/` 存放将要改变它的工作。每个已交付的 change 都保存在 `changes/archive/` 下。

每个改变外部可见行为的 pull request 都带一个 change 文件夹，并在合并前把它归档。因此 `main` 上的规格总是描述 `main` 上的代码。如果代码和规格不一致，错的是代码。

```text
openspec/
  config.yaml                        project context + writing rules the CLI injects
  specs/<capability>/
    spec.md                          purpose, requirements, scenarios (required)
    data-model.md                    entities and fields, when the capability has state
    contracts/api.openapi.yaml       the wire contract, generated from the models, when it has endpoints
    <child>/spec.md                  a child capability, id <capability>/<child>
  changes/<change-id>/
    .openspec.yaml                   schema and creation date (+ skip_specs for no-delta work)
    proposal.md                      why, and what changes
    design.md                        how, when the change is not obvious
    tasks.md                         the checklist /opsx:apply works through
    specs/<capability>/spec.md       deltas: ADDED / MODIFIED / REMOVED / RENAMED
  changes/archive/YYYY-MM-DD-<change-id>/
```

## 各项能力 {#the-capabilities}

能力只有名字，从不编号。它的 id 就是它在 `openspec/specs/` 下的路径，所以子能力的 id 是 `<parent>/<child>`。验收标记按这个 id 指明能力。

| 能力 | 负责什么 |
| --- | --- |
| [`agent-registry`](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/agent-registry/spec.md) | 已注册的智能体、它们的配置文件、MCP 安装、插件、模型目录、原生记忆和对话记录 |
| `agent-registry/claude-code`、`agent-registry/codex` | 每种智能体类型如何实现这些切面 |
| [`channels`](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/channels/spec.md) | 通往智能体的消息渠道，与具体平台无关 |
| `channels/telegram`、`channels/seatalk` | 各平台的具体机制 |
| [`chat`](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/chat/spec.md) | 轮次平台（智能体适配器、对话、事件流）和在终端里打开会话的对话列表 |
| [`secret`](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/secret/spec.md) | 加密的密钥存储，以及「其他一切只持有引用」这条规则 |
| [`daemon`](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/daemon/spec.md) | Coffer 进程：每个保险库一个、发现机制、回环 HTTP 防护、提供界面、日志、终端安装 |
| [`desktop-app`](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/desktop-app/spec.md) | macOS 桌面壳：窗口、托盘、握手、检测或启动守护进程、`.dmg` |
| [`experimental-features`](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/experimental-features/spec.md) | 功能注册表、按机器的开关、关闭对应入口 |
| [`internal-engine`](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/internal-engine/spec.md) | 语音转文字模型，以及 Coffer 的机械维护任务 |
| [`knowledge`](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/knowledge/spec.md) | 纯文件的知识集及其整理 |
| [`mcp-gateway`](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/mcp-gateway/spec.md) | 聚合在一个端点之后的上游 MCP 服务器 |
| [`memory`](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/memory/spec.md) | 通过保险库里的中心库，把每个智能体的原生记忆同步进其他智能体自己的记忆 |
| [`provider-switching`](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/provider-switching/spec.md) | 投射到每个智能体配置中的模型提供商连接 |
| [`resource-framework`](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/resource-framework/spec.md) | 与类型无关的资源模型、scope、审计日志、保留策略、最小 CLI 规则 |
| [`skill-manager`](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/skill-manager/spec.md) | 技能主存储以及向智能体的投递 |
| [`vault-storage`](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/vault-storage/spec.md) | `~/.coffer/` 下的五类存储、作为 git 仓库并通过一次经过校验的提交写入的保险库，以及一次性升级 |
| [`vault-sync`](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/vault-sync/spec.md) | 让保险库与用户自己的 git 远端收敛 |
| [`web-ui`](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/web-ui/spec.md) | 应用外壳、信息架构、共享的列表与详情约定、i18n |

一项能力覆盖一种行为在交付它的每一层、每个入口上的表现：后端、CLI、MCP、REST 和 Web。Coffer 从不把一种行为按入口拆成多份规格。当一项能力随类型而变时，父能力放所有类型共有的部分，每个子能力只放不同的部分。[`.agents/openspec.md`](https://github.com/wyx-sg/Coffer/blob/main/.agents/openspec.md#deciding-what-is-a-capability) 给出了判断新东西是否值得单独成为一项能力的五条检验。通常的答案是去更新一项已有的能力。

## 编写需求与场景 {#writing-requirements-and-scenarios}

每条需求都用 **SHALL** 或 **MUST** 陈述规则，并至少拥有一个场景，场景按 GIVEN、WHEN、THEN 和 AND 步骤书写。下面这段节选自 [`experimental-features`](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/experimental-features/spec.md)：

```markdown
### Requirement: Declare the experimental features in one registry
Coffer MUST declare its experimental features in one registry, and every
surface MUST take the list from it. The registry names exactly two features,
in this order: `knowledge` and `memory`.

A stored setting for a key the registry does not name MUST be ignored by every
read — logged, never listed — and MUST NOT fail anything.

#### Scenario: a stored setting for a feature the registry does not name is ignored
- **GIVEN** a daemon config whose `features` object holds a key the registry does not name
- **WHEN** the daemon starts and the features and the daemon status are read
- **THEN** the daemon starts, neither the features listing nor the status `features` map names the key, and no request fails because of it
```

这些规则（`openspec/config.yaml` 也会在 CLI 规划 change 时把它们喂给 CLI）：

- 需求标题是一个简短的祈使短语，在所属规格内唯一。需求没有编号，靠标题识别。
- 场景名在所属规格内唯一，因为验收标记会引用它。
- 陈述用户可观察到的行为。内部机制应写在 change 的 `design.md`、[架构页面](/zh/architecture/)或决策记录里，而不是 `spec.md`。
- 用平实的英文书写，不要带 "Day 3" 或 "last updated" 这类时间标注。

`openspec validate --all --strict` 会让任何没有场景的需求失败。`make verify-acceptance` 会运行它。

## 引用一条需求 {#citing-a-requirement}

因为需求没有编号，引用时要写明它的能力和确切标题。在 Markdown 里，链接到该规格并引用标题。在代码注释里，这样写：

```python
# spec experimental-features "Declare the experimental features in one registry"
```

`scripts/check_spec_citations.py` 在 `make lint` 中运行，扫描每一个被跟踪的文件，包括本站。它把每处引用和 `openspec/specs/` 下的 `### Requirement:` 标题逐一对照。能力或标题不存在的引用会让门禁失败。所以给一条需求改名后，必须等到所有引用旧标题的地方都跟着改掉，门禁才会通过。进行中的 change 新增或改名的标题，在该 change 归档前都视为有效。能力和决策记录都只有名字，从不编号。

## change 工作流 {#the-change-workflow}

```mermaid
flowchart LR
    P["提出（Propose）"] --> A["实施（Apply）"]
    A --> V["make verify"]
    V --> R["归档（Archive）"]
    R --> M["合并（Merge）"]
```

OpenSpec CLI 的版本锁定在根目录的 `package.json` 里，`make install` 会下载它。以 `npx openspec …` 的方式运行。它的 Claude Code 命令签入在 `.claude/commands/opsx/` 下，对应的技能在 `.claude/skills/openspec-*` 下：

| 命令 | 作用 |
| --- | --- |
| `/opsx:explore` | 在确定要做一个 change 之前，先把问题或需求想清楚 |
| `/opsx:propose` | 创建一个 change 文件夹，生成它的提案、增量、设计和任务。只做规划，不写代码 |
| `/opsx:apply` | 逐个任务实现一个 change，每完成一项就在 `tasks.md` 里勾掉 |
| `/opsx:update` | 修订进行中的 change 的产物 |
| `/opsx:sync` | 把一个 change 的增量合并进主规格，但不归档 |
| `/opsx:archive` | 把增量合并进 `openspec/specs/`，并把文件夹移到 `changes/archive/` |

这些技能调用的是裸的 `openspec`，所以要么把 `node_modules/.bin` 加到你的 `PATH`，要么全局安装锁定的那个版本。不用 Claude Code 时，同样的步骤就是普通文件加 CLI 调用。

### 1. 提出 {#_1-propose}

```sh
npx openspec list                 # changes in flight; "No active changes found." when none
```

创建 `openspec/changes/<change-id>/`。id 使用 kebab-case，以动词开头，比如 `add-telegram-topics` 或 `tighten-skill-import`。

- **`proposal.md`** 有两节：*Why* 和 *What Changes*。写出需求有变化的每一项能力。描述这个 change 做了什么，而不是它没做什么。
- **`specs/<capability>/spec.md`** 在 `## ADDED Requirements`、`## MODIFIED Requirements`、`## REMOVED Requirements` 或 `## RENAMED Requirements` 下存放增量。修改过的需求要完整重述，包括场景。
- **`design.md`**：只要评审者会希望某个选择得到解释，就需要它，包括你否决掉的备选方案。
- **`tasks.md`** 是实现清单。

不改变任何需求的 change（比如重构、工具链改动或文档改动），只有在有值得评审的计划时才建文件夹，并在 `.openspec.yaml` 中设置 `skip_specs: true`。一行修复不需要文件夹。

### 2. 实施 {#_2-apply}

逐个任务实现，每完成一项就在 `tasks.md` 里勾掉。放弃的任务用删除线划掉并写明原因，不要删掉它。边做边为每个新增或修改的场景写测试（见[验收标记](#acceptance-scenarios-and-markers)）。

### 3. 在同一个 pull request 里归档 {#_3-archive-in-the-same-pull-request}

代码完成并且 `make verify` 通过后：

```sh
npx openspec archive <change-id> --yes
```

增量会合并进 `openspec/specs/`，文件夹移到 `changes/archive/YYYY-MM-DD-<change-id>/`。什么都不会被删除：归档记录了每种行为为什么是现在这样。要在 pull request 合并**之前**、在同一个 pull request 里归档，这样 `main` 上永远不会出现领先或落后于代码的规格。

## 验收场景与标记 {#acceptance-scenarios-and-markers}

每个场景都必须至少被一个测试覆盖，哪个层级都行。测试用一个标记写明它覆盖的场景：

::: code-group

```python [pytest]
@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="a stored setting for a feature the registry does not name is ignored",
)
def test_a_stored_setting_for_a_retired_feature_is_ignored(home):
    daemon_config.write_feature_setting("retired_feature", False)
    with _client() as c:
        status = c.get("/api/v1/daemon/status").json()
    assert "retired_feature" not in status["features"]
```

```ts [Vitest / Playwright]
import { acceptance } from "@/test/acceptance"; // e2e specs import ./_acceptance

acceptance("web-ui", "activity gives each record its own tab", async ({ page }) => {
  // ...
});
```

```rust [Rust]
// acceptance(spec = "desktop-app", scenario = "a spawned daemon outlives the app")
#[test]
fn a_spawned_daemon_leaves_the_apps_process_group() { /* ... */ }
```

:::

`scripts/audit_acceptance.py` 在 `make verify-acceptance` 和 CI 中运行。它扫描每个 `spec.md` 和每个测试文件，遇到以下任何一种情况就失败：

- 某个场景没有任何标记覆盖
- 某个标记指向不存在的能力或场景，通常发生在改名之后（进行中的 change 新增的场景在该 change 归档前视为存在，并会被列出）
- 标记打在一个永远不会运行的测试上（`@pytest.mark.skip`、Rust 的 `#[ignore]`）
- 同一份规格里一个场景名用了两次

通过时会打印一行摘要：

```text
audit_acceptance: OK — 854 scenario(s) across 20 spec(s) all covered.
```

pytest 标记以 `--strict-markers` 注册，所以标记名拼错会导致收集失败。TypeScript 审计在匹配前会去掉注释，所以被注释掉的 `acceptance(...)` 调用不算覆盖。Rust 标记只有在下一个 `fn` 之前紧跟着 `#[test]` 或 `#[tokio::test]` 时才算数。各测试层级如何使用这些标记，见[测试](/zh/contributing/testing#acceptance-markers)。

## 端到端可交付规则 {#the-end-to-end-deliverable-rule}

一项能力只有在用户真正能操作它时才算交付。这意味着后端持久化，加上暴露它的每一个入口（REST、Web 界面、智能体调用它时经由 `coffer-mcp-shim` 的 MCP，以及 Web 界面或桌面应用提供的每个管理操作对应的 `coffer` 命令），全部连通，并且每个场景都有通过的测试覆盖。只有后端没有入口，或者只有页面没有后端，都不算完成。

有一条规则适用于所有规格：**每个管理操作都有一条命令。** 人在 Web 界面页面或桌面应用里能做的事，智能体都能用一条调用同一 REST 路由的 `coffer` 命令来做，所以无论谁来操作，校验、审计和生命周期都一样。豁免的只有两类：归属规格声明为可直接读取或编辑的普通文件（知识文档、技能的文件、智能体自己的配置和原生记忆文件），用普通工具读写；以及意义完全在于窗口的操作（原生文件夹选择器、在编辑器、终端或访达中打开文件、界面的语言和主题）。需要本人在场的步骤交给桌面应用自己的在场验证。所有命令共享一份约定：`--json`、`--data '<json>' | @file | -` 加可重复的 `--set key=value`、守护进程错误码原样透传，以及稳定的[退出码](/zh/reference/error-codes#cli-exit-codes)。每条命令都在 CLI 的注册表里登记它代表的界面操作和路由；Web 界面调用的某个路由或桌面外壳的某个命令既没有命令也没有记录豁免时，[`resource-framework`](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/resource-framework/spec.md) 规格的测试就会失败；注册表同时生成 [CLI 覆盖表](/zh/reference/cli-coverage)。因此，新增页面操作的改动要在同一个拉取请求里加上它的命令。这项决策见 [`command-line-parity-with-the-web-ui`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/command-line-parity-with-the-web-ui.md)。

## 文档随代码一起改 {#docs-change-with-the-code}

当一个改动改变了行为，同一个 pull request 要更新：

- 规格增量，并归档进 `openspec/specs/`
- `contracts/api.openapi.yaml`（当端点或 schema 变化时）。它从不手动编辑：修改后端模型并运行 `make contracts`，它会重新生成契约，再生成前端类型；然后像评审其他改动一样评审契约的 diff
- `data-model.md`（当实体变化时）
- [`docs-site/architecture/`](/zh/architecture/) 下的架构页面。如果其中的代码布局树或内置工具清单与代码出现偏移，`scripts/check_architecture_doc.py` 会失败
- 受影响的决策记录、本站的页面，以及任何 `.agents/` 约定

纯重构，或者对契约没有影响的纯前端改动，不需要改规格。

## 架构决策记录 {#architecture-decision-records}

规格说的是 Coffer 做*什么*。[`docs/decisions/`](https://github.com/wyx-sg/Coffer/tree/main/docs/decisions) 里的决策记录（ADR）说的是*为什么*这样构建。满足以下条件的决策要写一篇决策记录：

- 以后很难更改，否则会破坏兼容性或需要大面积重写；
- 是结构性的，即影响不止一个模块，或约束未来的工作；
- 是一个未来读者会质疑的取舍；或者
- 偏离了某个默认做法、流行惯例、原则或更早的决策记录。

版本升级、常规 bug 修复、命名或格式、以及属于规格 `## Purpose` 的范围决策，都不要写决策记录。

一篇决策记录只陈述**一个**决策，并论证每一个认真考虑过的方案，包括被选中的那个。文件名就是标题的 kebab case 形式，不带编号，比如 `experimental-features-instead-of-a-release-branch.md`：

```markdown
# Experimental Features Instead of a Release Branch

**Status**: Accepted
**Date**: YYYY-MM-DD
**Deciders**: <who decided>
**Related**: spec [experimental-features](../../openspec/specs/experimental-features/spec.md)

## Context
## Options Considered
### Option A — <name> (chosen)
### Option B — <name>
## Decision
## Consequences
```

这个目录记录的是**现行**设计，而不是按时间排列的日志。当某个决策改变时，重写负责它的那篇决策记录，让它读起来像是今天写的，被替换的设计作为其中一个方案来论证。当它所决定的东西被移除时，删掉这篇决策记录，其余的交给 git 历史。每篇新决策记录都要加到 [`docs/decisions/README.md`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/README.md) 的索引里，`scripts/check_adr_index.py` 会让索引和文件保持一致。对[原则](/zh/architecture/principles)本身的修改属于修正案，需要单独提一个提案 pull request，说明动机、影响和备选方案。

本站的[决策记录](/zh/architecture/decisions)页面概括了当前的各篇决策记录。

## 相关 {#related}

- [测试](/zh/contributing/testing)
- [参与贡献概览](/zh/contributing/)
- [资源框架](/zh/architecture/resource-framework)
- [`.agents/openspec.md`](https://github.com/wyx-sg/Coffer/blob/main/.agents/openspec.md)
