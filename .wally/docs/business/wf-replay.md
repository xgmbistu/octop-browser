---
kind: workflow
scope: WF-06
status: draft
origin: generated
source_paths: [src/octop_browser/record/replay.py, src/octop_browser/record/matcher.py, src/octop_browser/record/skill_generator.py, src/octop_browser/record/store.py]
symbols: [ReplayRunner, run, match_target, _run_verification, _capture_failure_artifacts, _fallback_dom_action, _resolve_url, _replace_known_search_query, _write_report, SkillGenerator, generate]
upstream: [business/index.md, business/wf-semantic-steps.md]
downstream: [business/wf-action-dispatch.md, operations/runbook-and-observability.md]
---

# WF-06 · 录制回放、目标匹配与验证报告闭环

`replay run <id>` 读取 `steps.json`，逐步用 `browser_tool` 重新执行意图（不是坐标或旧 ref），以 `structured` DOM 快照 + `match_target` 打分定位当前页面元素，全部成功后跑 `verification` 并写回 `replay_<时间>.json` 报告。异步执行，失败短路并落盘失败快照。

## 1. 符号级端到端执行调用树

```text
Trigger: replay run <id> -> cli._run_replay (src/octop_browser/cli.py:610)
  └─ ReplayRunner().run(recording_id, profile, inputs) (src/octop_browser/record/replay.py:25)
       ├─ steps_doc = store.read_steps(recording_id) (:31)
       ├─ 初始化 report = {recordingId, startedAt, status:"running", inputs, stepsLoaded, steps:[], verification:[]} (:35)
       ├─ [guard] not steps_doc.steps -> RuntimeError("Recording has no replayable steps") (:45)
       ├─ for step in steps_doc.steps:
       │    ├─ [open] _resolve_url -> browser_tool("navigate", url=...) (:53)
       │    ├─ [new_tab] browser_tool("new_tab", url=..., force_new=True)，记 target_map (:66)
       │    ├─ [click/fill/select/set_checked] (:84)
       │    │    ├─ _switch_for_step_target 按 target_map 切标签 (:88)
       │    │    ├─ dom = browser_tool("dom_tree", level="structured") (:112)
       │    │    ├─ ref, matched_by = match_target(step.target, dom.content) (src/octop_browser/record/matcher.py:19)
       │    │    ├─ [if ref] 按 kind 调 click/fill/select/eval_js(set_checked) (:118)
       │    │    ├─ [else] _fallback_dom_action：selector/xpath JS 或 bbox 坐标 (:155、:469)
       │    │    └─ [if step.expect.urlContains] browser_tool("wait", url_contains=..., timeout_ms=10000) (:189)
       │    ├─ [press] browser_tool("press", key=...) (:200)
       │    ├─ [navigate] is_transient_auth_or_risk_url 命中则 status="skipped" (:208、:210)
       │    ├─ [scroll_to] eval_js("window.scrollTo(x,y)") (:241)
       │    ├─ [else] status="skipped" (:269)
       │    └─ [if entry.status == "failed"] _capture_failure_artifacts + report.status="failed" + break (:272)
       ├─ [for-else 正常收尾] 无 executed 步骤则抛 RuntimeError("Recording has no executable steps") (:282)
       │    └─ _run_verification(steps_doc.verification) -> status="passed" 或 "failed" (:285、:290)
       ├─ [except] report.status="failed" + error + endedAt (:292)
       └─ [finally] _write_report(recording_id, report) -> replay-reports/replay_<时间>.json (:296、:647)
```

## 2. 分阶段业务规则与分支判定表

| 阶段 | 负责函数（`路径:行号`） | 精确布尔条件 / 阈值 | 命中分支行为 | 状态或数据副作用 |
|---|---|---|---|---|
| 目标打分 | `match_target` (`src/octop_browser/record/matcher.py:19`) | selector 交集 +80、id +70、nameAttr +60、role +25、name 全等 +50、部分匹配 +20、`best[0] >= 45` 才返回 | 低于 45 返回 `(None, "not-found")` | 无 |
| 结构化 DOM 前置 | `run` (`:112`) | `dom.success` 为真且 `content` 是 `str` | 否则 `RuntimeError("Could not get DOM snapshot")` | 无 |
| 输入解析 | `_run_replay` (`src/octop_browser/cli.py:610`) | `--input k=v` 仅当含 `=` 才并入 `inputs` | 无等号项被丢弃 | `inputs` 字典 |
| 变量替换 | `_resolve_value` (`:566`) | `value.startswith("{{") and value.endswith("}}")` | `inputs.get(key, "")`，缺失填空串 | 不报错 |
| URL 变量替换 | `_resolve_url` (`:606`) | `resolved.replace("{{"+key+"}}", value)` 逐键替换；`inputs["query"]` 存在时调 `_replace_known_search_query` | 百度用 `wd`、google/bing 用 `q`，`quote_plus` 编码 | 无 |
| 瞬态风控跳过 | `run` (`:210`) | `is_transient_auth_or_risk_url(url)` 为真 | `status="skipped"`，`reason="transient_auth_or_risk_redirect"`，`continue` | 该步不算失败 |
| 验证类型 | `_run_verification` (`:329`) | `url_contains`/`text_contains`/`selector_exists` 走 `wait(timeout_ms=10000)`；`title_contains`/`element_text_contains`/`input_value_equals` 走 `eval_js` 并 `_truthy_js_content` | 未知类型 `status="skipped"`，附 `Unsupported verification` | 任一失败即 `failed=True` 并 break |
| 真值判定 | `_truthy_js_content` (`:575`) | 字符串归一为 `true`/`"true"`/`1` 才算真 | 否则判失败 | 无 |
| 失败快照 | `_capture_failure_artifacts` (`:425`) | 任意 `failed` 步骤触发 | 写 `reason.txt`、可选 `dom_snapshot.json` 与 `screenshot.png`（`full_page=True`） | `failure_<时间>_<step>/` |
| 报告落盘 | `_write_report` (`:647`) | 无条件 | `replay_<Ymd_HM_S>.json`，`indent=2` | `report.reportPath` |

## 3. 回放报告与技能草稿字段字典

| 报告 / 产物键 | 类型 | 含义 | 产出位置 |
|---|---|---|---|
| `status` | `str` | `running` → `passed` 或 `failed` | `:38`、`:290`、`:293` |
| `steps[].status` | `str` | `passed` / `failed` / `skipped` | `:51`、`:59`、`:270` |
| `steps[].matchedBy` | `str` | `selector`/`id`/`nameAttr`/`role`/`name`/`partial-name` 的组合、`selector/xpath`、`bbox` 或 `not-found` | `src/octop_browser/record/matcher.py:59`、`:489` |
| `failureArtifacts` | `dict[str,str]` | `reasonPath`、`domSnapshotPath`、`screenshotPath` 或 `screenshotErrorPath` | `:440`、`:443`、`:451`、`:462`、`:465` |
| `verification[]` | `list[dict]` | `type`、`value`、`status`、可选 `error`/`selector` | `:340`、`:416` |
| `reportPath` | `str` | 报告文件绝对路径 | `:297` |

`SkillGenerator.generate`（`src/octop_browser/record/skill_generator.py:32`）把同一份 `StepsDocument` 编译为 `draft.skill.md`：YAML 头 `name/description/allowed-tools`（`:47`），正文含「Required inputs」「Workflow」「Target matching guidance」「Verification」「Privacy notes」等章节；`_workflow_md` 按 8 种 `kind` 逐行渲染（`:113`），`_inputs_md` 展开 `inputs` 的 `name/kind/example`（`:101`）。

## 4. 幂等、并发互斥与异常补偿回滚表

| 边界 / 故障场景 | 源码检测条件 | 保护 / 回滚 / 降级动作 |
|---|---|---|
| 无可回放步骤 | `not steps_doc.steps`（`:45`） | 抛 `RuntimeError`，报告仍由 `finally` 写出 |
| 全部步骤被跳过 | `executed` 为空（`:282`） | 抛 `RuntimeError("Recording has no executable steps")` |
| 目标匹配失败 | `ref is None`（`:154`） | 先试 `_fallback_dom_action`，仍失败才标 `failed` 并采快照 |
| `switch_tab` 失败 | `not switched.success`（`:96`） | 立即 `failed` + `failureArtifacts` + `break` |
| 切标签焦点漂移 | `_switch_for_step_target` 注释（`:321`） | 即使记录目标看似当前也强制重新激活，保证多标签确定性 |
| 新标签导航失败 | `navigation_result.success` 为假（`src/octop_browser/session.py:614`） | `_close_failed_new_target` 切回原标签并 `Target.closeTarget` |
| 全部为 skipped | — | 不计入 `passed`，`Skipped is not passed` 由 SOP 侧把关 |

## 5. 共变耦合与修改清单（Agent Co-Change Playbook）

- **新增步骤 `kind`**：`SemanticProcessor._build_steps`（`src/octop_browser/record/semantic.py:396`）、`ReplayRunner.run` 分发链（`:47`）、`SkillGenerator._workflow_md`（`src/octop_browser/record/skill_generator.py:113`）与 [语义折叠](wf-semantic-steps.md) 联动。
- **修改匹配权重**：`match_target` 的加分表与阈值 45（`src/octop_browser/record/matcher.py:29`、`:60`）必须与 [DOM ref 流程](wf-dom-ref-targeting.md) 的 `structured` 字段字典一致。
- **修改报告字段**：`_write_report`（`:647`）、`RecordingStore.recording_summary` 的 `latestReplayReport`（`src/octop_browser/record/store.py:141`）与 [可观测性 Runbook](../operations/runbook-and-observability.md) 同步。
- **修改搜索词替换**：`_replace_known_search_query` 的 `wd`/`q` 映射（`:619`）与 `_resolve_url`（`:606`）成对核查。
- **必跑流程闭环回归**：`pytest tests/unit/test_record_replay_replay_runner.py tests/integration/test_record_replay_e2e.py`，端到端 `scripts/record_replay_smoke.py:57`，命令见 [构建与单测映射](../operations/dev-and-test.md)。
