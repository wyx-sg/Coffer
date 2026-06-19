# 竞品调研 —— AI Agent 评估与 Eval 飞轮

> 中文版：本文件 · English: [agent-evaluation.md](./agent-evaluation.md)
>
> 面向 Coffer 评估方向（ADR-019"闭合 eval 飞轮"、ADR-017 AI-eval 层）的内部竞品调研报告。
> **日期：** 2026-06-16。**方法：** deep-research harness（本轮读了 Coffer 仓库核对现状；
> 多条结论 3-0 确认）。
>
> **对设定的更正。** "Coffer 评估基本是蓝图、尚未落地"这一前提**部分已过时。** ADR-019 已
> **Accepted（2026-06-14）**，且本地优先的 `evals/` harness 已**落地**——确定性检索 + 工具检索
> 套件、可插拔模型工具路由套件、带相对回归门的提交基线、`evals.yml` CI 工作流、可选 gitignore 的
> 捕获 sink（`COFFER_EVAL_CAPTURE`）、以及把捕获的工具检索迹提升为金样的交互式 `curate.py`。

## 1. 全景速览

2026 年的评估市场**收敛到一种架构**，受访八个工具都不同程度地实现它：

> **捕获**生产迹 → **打分**（确定性代码检查 + LLM-as-judge、RAG 忠实度/可溯源性、工具使用正确性）
> → 把有趣/低分/负反馈的迹**精选**进**金样数据集** → 在 CI 中对这些数据集**做门禁**离线评估 →
> 重新部署 → 在线**复测**。

| 层                | 工具                                                                                        | 注                                     |
| ----------------- | ------------------------------------------------------------------------------------------- | -------------------------------------- |
| **完整商业飞轮**  | Braintrust、LangSmith                                                                       | 一键 迹→数据集、在线 LLM 评判、CI 门禁 |
| **开源支柱**      | DeepEval（Apache-2.0）、Promptfoo（MIT —— **2026-03 被 OpenAI 收购**）、Ragas（Apache-2.0） | 本地优先、CI 友好                      |
| **可观测 + 评估** | Galileo、Arize Phoenix                                                                      | 本轮取证较少                           |

### 各玩家

- **Braintrust** —— 最完整的商业飞轮。捕获每条生产迹；**LLM-as-judge 在线打分**自动/异步、对应用
  无延迟影响、无需 ground truth；**一键把任意迹加进数据集**；端到端*且逐步*评估 agent，含**工具使用
  正确性**（选对工具、计划连贯、参数正确）；并通过已发布的 GitHub Action（`braintrustdata/eval-action`，
  低于阈值阻止合并）**在每个 PR 上做离线评估门禁**。_细节：_ 迹→数据集的提升是人工精选；在线打分在配置
  打分规则 + 采样率后才开启，非默认。[3-0 确认]
- **LangSmith** —— 显式*闭合*飞轮："在线评估暴露问题 → 成为离线测试用例 → 离线评估验证修复 → 在线
  评估确认生产改进"。把生产迹（含**负反馈运行**）转为数据集样本（一键"Add to Dataset" + 自动 run-rules）。
  四种评判器——**人工**（带评分量表的标注队列）、**代码**、**LLM-as-judge**（无参考或带参考）、**成对比较**
  ——并**独特地把 LLM 评判器对齐到人工标注（"Align Evals"，**对齐分 = 与人类专家匹配的百分比）。[3-0 确认]
- **DeepEval**（`confident-ai`，Apache-2.0）—— 本地优先、**pytest 风格**评估，配商业 Confident AI
  云。CI 评估的开源默认选择。
- **Promptfoo**（MIT 开放内核，**2026-03 被 OpenAI 收购**）—— 声明式 prompt/agent 测试矩阵；CI 集成强。
- **Ragas**（Apache-2.0）—— **无参考 RAG 指标**（忠实度、答案相关性、上下文精度/召回）。
- **Galileo / Arize Phoenix** —— 补全商业 / 开源可观测一侧。

## 2. 能力对比

| 能力              | Braintrust | LangSmith          | DeepEval  | Promptfoo | Ragas     | **Coffer evals/**                          |
| ----------------- | ---------- | ------------------ | --------- | --------- | --------- | ------------------------------------------ |
| 确定性检查        | ✅         | ✅                 | ✅        | ✅        | —         | **✅ 检索 + 工具检索套件**                 |
| LLM-as-judge      | ✅ 在线    | ✅ 4 型            | ✅        | ✅        | ✅（RAG） | **❌ 尚无**                                |
| RAG 忠实度指标    | ✅         | ✅                 | ✅        | 部分      | **✅**    | **❌**                                     |
| 工具使用正确性    | ✅ 逐步    | ✅                 | ✅        | ✅        | —         | **✅ 工具路由套件**                        |
| 金样数据集        | ✅         | ✅                 | ✅        | ✅        | ✅        | **✅ 提交基线**                            |
| CI 回归门禁       | ✅ Action  | ✅                 | ✅ pytest | ✅        | ✅        | **✅ `evals.yml` + 相对门**                |
| 在线 → 数据集捕获 | ✅ 一键    | ✅ 一键 + 规则     | 经云      | —         | —         | **✅ `COFFER_EVAL_CAPTURE` + `curate.py`** |
| 人工标注队列      | 部分       | ✅                 | 经云      | —         | —         | **❌**                                     |
| 评判器↔人工校准  | —          | **✅ Align Evals** | —         | —         | —         | **❌**                                     |
| 本地优先 / 无载荷 | 云         | 云                 | **✅**    | **✅**    | **✅**    | **✅ 本地优先、无载荷**                    |
| 开源              | 仅 Action  | ❌                 | ✅        | ✅        | ✅        | ✅                                         |

## 3. Coffer 对比

**Coffer 已独立建出这些工具所售卖的那个循环的最小版本。** 已落地的 `evals/` harness 已经做到
捕获（`COFFER_EVAL_CAPTURE`）→ 精选（`curate.py` 把迹提升为金样）→ 数据集（提交基线）→ 门禁
（`evals.yml` + 相对回归），且范围限定为**本地优先、无载荷**（与调用日志的 谁/何时/时长/结果、
无参数/结果一致）。这就是 Braintrust/LangSmith 的飞轮，有意做了隐私限定。

**Coffer 已对齐之处。**

1. **飞轮形状匹配。** 捕获 → 精选 → 金样 → CI 门禁正是收敛架构；Coffer 在无云的情况下建出了它。
2. **确定性 + 工具使用套件**（检索、工具检索、工具路由）镜像了领头者跑的确定性与工具使用正确性检查。
3. **无载荷是有原则的差异化** —— 商业工具把完整迹（prompt/输出）捕获到云；Coffer 的仅元数据捕获
   对本地优先金库是本职。

**Coffer 落后 —— 具体借鉴。**

1. **无 LLM-as-judge。** 每个领头者都用 LLM-as-judge 评开放式质量（聊天答案、RAG 忠实度），确定性
   检查够不到。Coffer 的内部模型（ADR-024）可在聊天 / `ask` 输出上跑**本地 LLM 评判**——无需云。
2. **无 RAG 忠实度指标。** Ragas 式无参考指标（忠实度、上下文精度）直接契合 Coffer 的 KB，且无需金样答案。
3. **无人工反馈环 / 评判器校准。** LangSmith 的 Align Evals（把评判器对齐到人工标注）和负反馈驱动捕获
   是最值得借鉴的强模式——聊天里的"踩"可自动把迹捕获进评估 sink。
4. **调用日志 + 迹蒸馏是未被利用的捕获源。** ADR-020 迹蒸馏已读取本地迹；把调用日志 + 蒸馏后的迹喂进
   同一个 `COFFER_EVAL_CAPTURE` sink，能把飞轮拓宽到工具检索之外。

## 4. 给 Coffer 的关键结论

1. **更新表述：飞轮已落地，不是蓝图。** ADR-019 已 Accepted，`evals/` 在本地实现 捕获→精选→金样→门禁
   ——以"我们建出了 Braintrust/LangSmith 那个循环的隐私限定版"作为头条。
2. **加入本地 LLM-as-judge**（经 ADR-024 内部模型）评确定性检查够不到的开放式质量——最大的单一缺口。
3. **加入 Ragas 式无参考 RAG 指标**给 KB / `ask`——无需金样答案，可直接套用。
4. **借鉴负反馈捕获 + 评判器校准**（LangSmith）：聊天"踩"自动捕获进评估 sink；用用户自己的标注校准本地评判器。
5. **把调用日志 + ADR-020 迹接入捕获 sink**，把飞轮拓宽到工具检索之外。

## 5. 来源

一手：

- braintrust.dev —— articles/how-to-eval、docs/evaluate、docs/evaluate/score-online、docs/best-practices/agents · github.com/braintrustdata/eval-action
- docs.langchain.com/langsmith —— evaluation-concepts、manage-datasets-in-application · langchain.com/langsmith/evaluation · langchain.com/resources/llm-evals
- github.com/confident-ai/deepeval · promptfoo.dev（OpenAI 收购，2026-03）· github.com/explodinggradients/ragas
- Galileo（galileo.ai）· Arize Phoenix（docs.arize.com/phoenix）

已核对 Coffer 仓库：`evals/`（套件、基线、`curate.py`）、`.github/workflows/evals.yml`、ADR-019、ADR-017。

## 核查更新（2026-06-19）

> 复核一轮：Coffer 本地 eval 飞轮的各项主张对仓库逐条成立；网络主张大体确认，仅一处修正
> （Braintrust 的 `eval-action` 是报告而非门禁）和两处新增覆盖（Galileo、Arize Phoenix）。

### ✅ 已确认

- **已落地的 eval 飞轮。** `evals/` 含确定性套件（`retrieval_eval.py`、
  `tool_search_eval.py`）及一个带模型的路由套件（`routing_eval.py`，不进 CI）；
  `COFFER_EVAL_CAPTURE` 的 JSONL 捕获 sink 默认关闭——发射端
  `record_tool_search` 在 `repo:backend/coffer/application/eval_capture.py`、
  handler 在 `repo:backend/coffer/infrastructure/logging/eval_capture.py`、经
  `repo:backend/coffer/application/mcp/gateway_builtin.py` 接入
  `coffer__search_tools`；交互式 `repo:evals/curate.py` 把捕获的迹提升进
  `datasets/tool_search.jsonl`。
- **提交基线 + 相对回归 CI 门禁。** `evals/baselines/{retrieval,tool_search,routing}.json`
  均存在；`repo:evals/run.py` 以 `floor = baseline - tolerance` 做门禁（检索 0.01 /
  工具检索 0.05 / 路由 0.10），回归时非零退出；`repo:.github/workflows/evals.yml` 在 PR
  上跑确定性、无模型的检索 + 工具检索门禁，按路径过滤（路由套件仅按需触发）。
- **支撑各项借鉴的 ADR 状态。** ADR-019（闭合 eval 飞轮）已 Accepted，2026-06-14；
  ADR-020（迹蒸馏）已 Accepted——对应借鉴 #4 / 结论 #5；ADR-024（内置 agent 是内部能力）
  已 Accepted，2026-06-14——对应本地 LLM 评判借鉴 #1。
  `repo:docs/decisions/ADR-019-close-the-eval-flywheel.md`、
  `repo:docs/decisions/ADR-020-transcript-distillation.md`、
  `repo:docs/decisions/ADR-024-builtin-agent-is-internal-capability.md`
- **Promptfoo —— MIT、2026-03 被 OpenAI 收购。** 收购于 2026-03-09 宣布；Promptfoo
  "将保持开源……在当前许可证下"。MIT 由仓库许可证本身确认（公告只确认开源延续、未点名许可证）。
  https://www.promptfoo.dev/blog/promptfoo-joining-openai/ ;
  https://github.com/promptfoo/promptfoo
- **LangSmith Align Evals。** 把 LLM 评判器对齐到人工标注；对齐分 = 评判器与人类专家匹配的样本
  百分比；UI 中的更正会作为 few-shot 样本喂入后续 prompt——逐字确认。
  https://blog.langchain.com/introducing-align-evals/ ;
  https://docs.langchain.com/langsmith/improve-judge-evaluator-feedback
- **Braintrust 在线打分是显式开启。** 在线打分规则在项目级创建（打分器、span/trace 范围、采样率），
  异步跑在生产迹上、对应用无延迟影响——确认"配置打分规则 + 采样率后才开启，非默认"。
  https://www.braintrust.dev/docs/evaluate/score-online ;
  https://www.braintrust.dev/foundations/online-scoring

### ✏️ 已修正

- **Braintrust `eval-action` 是报告，不是门禁。** 旧："在每个 PR 上做离线评估门禁……低于阈值
  阻止合并。" → 修正：`braintrustdata/eval-action` 在 CI 中跑评估，并在 PR 上贴一条实验对比
  **评论**（分数差、回归指示），它本身**不**按阈值阻止合并——合并门禁需要单独的工作流/分支保护
  设置。每个 PR 的离线评估运行属实；自动按阈值阻止合并的说法被夸大。
  https://github.com/braintrustdata/eval-action

### ❓ 仍待核查

- **ADR-017 状态细节。** ADR-017（分层工业级 harness）状态为 **Proposed**（日期 2026-06-13），
  **并非** Accepted。报告只把它当作"AI-eval 层"的相关背景引用，从未声称其已 Accepted，故无需正文
  改动——此处按核查要求标注。
  `repo:docs/decisions/ADR-017-industrial-grade-harness-in-layers.md`
- **Promptfoo 许可证命名。** MIT 仅由仓库许可证本身确认；OpenAI/Promptfoo 的声明只说"在当前许可证
  下保持开源"，未点名 MIT。

### ➕ 新增覆盖

- **Galileo**（商业）—— Agent Reliability 平台：观测 / 评估 / 护栏 / 改进 agent，含专为 agent 设计
  的指标（工具选择质量、工具错误率、动作推进/完成、流程遵循）以及 **Luna-2** 小模型评判器（亚 200ms、
  约 0.95 准确率），使 100% 流量在线打分在经济上可行。**报告里光秃秃的"Galileo（galileo.ai）"一行
  漏掉的重大更新：Cisco 于 2026-05-22 完成对 Galileo 的收购。** https://galileo.ai/ ;
  https://blogs.cisco.com/news/cisco-announces-the-intent-to-acquire-galileo
- **Arize Phoenix**（开源）—— 来自 Arize AI、基于 OpenTelemetry 的 Apache-2.0 LLM 可观测 + 评估
  平台；可本地 / 自托管 / 在 notebook 中运行（或 Arize 云），带 LLM-as-judge 评估（相关性、毒性、
  幻觉、RAG、工具调用）。常被描述为"拥有 LangSmith 级能力却不把数据发给第三方"——是最贴近 Coffer
  本地优先、无载荷立场的外部类比，只是 Phoenix 捕获完整迹，而 Coffer 仅保留元数据。
  https://github.com/Arize-ai/phoenix ; https://arize.com/phoenix/
