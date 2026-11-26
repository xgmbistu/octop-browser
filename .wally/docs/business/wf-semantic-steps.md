---
kind: workflow
scope: WF-05
status: draft
origin: generated
source_paths: [src/octop_browser/record/semantic.py, src/octop_browser/record/models.py, src/octop_browser/record/url_filter.py]
symbols: [SemanticProcessor, process, _filter_events, _start_url, _build_steps, _infer_variables, _attach_navigation_expectations, _coalesce_scrolls, _verification, is_replayable_page_url]
upstream: [business/index.md, business/wf-record-capture.md]
downstream: [business/wf-replay.md, business/domain-models/recording-artifacts.md]
---

# WF-05 · 原始事件折叠为语义步骤与变量推断

`SemanticProcessor.process()` 把 `events.jsonl` 的原始事件按 `seq` 排序、白名单过滤、折叠成可回放的 `SemanticStep` 序列，推断输入变量并生成验证条件，最终产出 `StepsDocument`（`steps.json`）。这是「录制 → 可复用意图」的编译阶段，不含浏览器交互；同步纯函数式执行。

## 1. 符号级端到端执行调用树

```text
Trigger: RecordController.generate_steps / RecordSession.stop(generate_steps=True) (src/octop_browser/record/recorder.py:397)
  └─ events = store.read_events(recording_id) (src/octop_browser/record/store.py:88)
       └─ SemanticProcessor(recording_id, events).process() (src/octop_browser/record/semantic.py:338)
            ├─ [Stage 1] self.events = sorted(events, key=lambda e: int(e.get("seq", 0))) (:336)
            ├─ [Stage 2] useful = _filter_events -> 仅保留 14 种 allowed kind (:353、:354)
            ├─ [Stage 3] start_url = _start_url(useful) -> 首个 seq<=1 的 recorder_installed 页 URL (:372)
            ├─ [Stage 4] steps = _build_steps(useful, start_url) (:396)
            │    ├─ 若 start_url 非空先追加 kind="open" 的 step_001 (:402)
            │    ├─ click + 紧邻 input/change 且 _same_target -> 合并为一个值步骤 (:444)
            │    ├─ input/change -> _value_step：checkable→set_checked、select→select、其余→fill (:211)
            │    ├─ keydown 且 key 存在 -> kind="press" (:492)
            │    ├─ scroll -> scroll_to，pos 非零才保留 (:502)
            │    ├─ page_opened 且 is_replayable_page_url -> new_tab (:520、:523)
            │    └─ navigation/pushState/replaceState/popstate/hashchange -> navigate 或 new_tab (:545)
            ├─ [Stage 5] steps, inputs = _infer_variables(steps) -> fill/select 值替换为 {{var}} (:614)
            ├─ [Stage 6] steps = _attach_navigation_expectations(steps) -> 给前一 click/press 挂 urlContains (:626)
            │    └─ _coalesce_scrolls 把连续滚动合并到末尾 (:650)
            ├─ [Stage 7] verification = _verification(steps) -> 取最后一个 urlContains 生成 url_contains (:665)
            └─ [return] StepsDocument(recordingId, startUrl, inputs, steps, verification) (:345)
```

## 2. 分阶段业务规则与分支判定表

| 阶段 | 负责函数（`路径:行号`） | 精确布尔条件 / 阈值 | 命中分支行为 | 状态或数据副作用 |
|---|---|---|---|---|
| 事件白名单 | `_filter_events` (`src/octop_browser/record/semantic.py:353`) | `kind in allowed`（14 项：`recorder_installed/page_opened/click/dblclick/input/change/keydown/submit/scroll/navigation/history.pushState/history.replaceState/popstate/hashchange`） | 其它 kind 直接丢弃 | 无 |
| 起始 URL | `_start_url` (`:372`) | `recorder_installed` 且 `seq > 1` 跳过（说明是导航后重装） | 取首个合规页 URL，否则回退任意事件 URL | `StepsDocument.startUrl` |
| 低信号点击 | `_is_low_signal_result_click` (`:277`) | 非交互角色且文本 `>= 160` 字符，或选择器全含 `nth-of-type` | 跳过该 click | 无 |
| 空白页点击 | `_is_blank_page_click` (`:263`) | `url == "about:blank"` 且 target 为 `body/html` 或 xpath 为 `/html...` | 若下一事件是导航类，改产出 `navigate` 步骤 | `i += 2` |
| 点击+输入折叠 | `_build_steps` (`:444`) | `nxt.kind in {"input","change"}` 且 `_same_target` | 用 nxt 产出值步骤，`i += 2` | 少一个 click 步骤 |
| 重复 fill 去重 | `_build_steps` (`:482`) | `_same_fill_step(prev, target, value)` 命中任意既有步骤 | `i += 1` 跳过 | 无 |
| 可回放 URL | `is_replayable_page_url` (`src/octop_browser/record/url_filter.py:44`) | 排除 `about:blank`/`chrome://newtab/`、`chrome://`/`devtools://` 前缀与瞬态风控 URL | 为假不产 `navigate`/`new_tab` | 无 |
| 导航去重 | `_build_steps` (`:554`) | `url != start_url` 且非「上一 open/navigate/new_tab 同 URL」 | 否则跳过 | 无 |
| 变量推断 | `_infer_variables` (`:614`) | 仅 `kind in {"fill","select"}` 且 `value` 非空 | 调 `_var_for` 生成 `{{name}}` 并追加 `inputs` 描述 | `step.value` 被替换 |
| 变量命名 | `_var_for` (`:122`) | 值以 `{{...}}` 包裹 → `sensitive_value/secret`；含 email → `email`；含 search/query/百度/搜或 `q/wd/word/query/...` → `query`；含 date → `date`；否则 `_stable_input_name` | 重名加 `_2` 后缀 | `inputs` 列表 |
| 期望挂载 | `_attach_navigation_expectations` (`:626`) | `step.kind == "navigate"` 且前一个结果是 `click/press/submit` | 给前一步写 `expect.urlAfter` 与 `urlContains`（`_path_hint` 取末段路径） | 该 navigate 步骤被移除 |
| 验证生成 | `_verification` (`:665`) | 逆序找首个 `expect.urlContains` | 返回 `[{"type":"url_contains","value":...}]`，否则空列表 | `StepsDocument.verification` |

## 3. 步骤 `kind` 与字段字典

| `SemanticStep.kind` | 关键字段 | 产出位置 |
|---|---|---|
| `open` | `url`、description | `:402` |
| `navigate` | `url`、`target`（可含 `targetId`）、`expect` | `:583` |
| `new_tab` | `url`、`target` | `:534` |
| `click` | `target`（`_compact_target` 输出） | `:470` |
| `fill` | `target`、`value`（变量化后） | `:233` |
| `select` | `target`、`value` | `:226` |
| `set_checked` | `target`、`value`（`true`/`false`） | `:218` |
| `press` | `key`、`target` | `:492` |
| `scroll_to` | `value`（`"{x:.3f},{y:.3f}"`）、`target` | `:509` |

`_compact_target` 只保留 11 个描述键、`selectorCandidates[:5]`、`xpath`、`bbox`、`framePath`/`shadowPath`（`src/octop_browser/record/semantic.py:44`）；`SemanticStep` 与 `StepsDocument` 的字段与别名（如 `schemaVersion`/`startUrl`）定义在 `src/octop_browser/record/models.py:69`、`:80`。`_step_id` 统一格式 `step_{n:03d}`（`:104`），重排后由 `:646` 重新编号。

## 4. 幂等、并发互斥与异常补偿回滚表

| 边界 / 故障场景 | 源码检测条件 | 保护 / 回滚 / 降级动作 |
|---|---|---|
| 事件乱序 | `sorted(..., key=int(seq))`（`:336`） | 按 `seq` 重排，缺失 `seq` 视为 0 |
| 事件为空 | `_build_steps` 仅 `start_url` 可能产一步 | `verify_chromium` 无关；回放侧会抛 `Recording has no replayable steps`（`src/octop_browser/record/replay.py:46`） |
| 起始 URL 缺失 | `_start_url` 返回 `""`（`:394`） | 不追加 `open` 步骤 |
| 目标完全相同误合并 | `_same_target` 用 `_target_key` 或 `selectorCandidates` 交集（`:94`） | 仅同目标才折叠，避免误并不同控件 |
| 变量名冲突 | `_var_for` 的 `while name in used`（`:162`） | 追加 `_2`、`_3` 后缀 |
| 无可靠验证条件 | `_verification` 返回空（`:669`） | Skill 草稿提示「需向用户确认成功状态」（`src/octop_browser/record/skill_generator.py:177`） |

## 5. 共变耦合与修改清单（Agent Co-Change Playbook）

- **新增 `kind`**：`_filter_events` 白名单（`:353`）、`_build_steps` 分支（`:396`）、`ReplayRunner.run` 的分发链（`src/octop_browser/record/replay.py:47`）、`SkillGenerator._workflow_md`（`src/octop_browser/record/skill_generator.py:113`）四处同步。
- **修改 `_compact_target` 键集**：`matcher.match_target` 的打分字段（`src/octop_browser/record/matcher.py:19`）与 [DOM ref 流程](wf-dom-ref-targeting.md) 的 `structured` 输出（`src/octop_browser/dom/builder.py:359`）联动，字段名不一致会让所有目标匹配失败。
- **修改 URL 过滤**：`is_replayable_page_url` / `is_transient_auth_or_risk_url`（`src/octop_browser/record/url_filter.py:11`、`:44`）与 `ReplayRunner` 的跳过分支（`src/octop_browser/record/replay.py:210`）成对核查。
- **必跑流程闭环回归**：`pytest tests/unit/test_record_replay_semantic.py tests/unit/test_record_replay_store_skill.py`，命令见 [构建与单测映射](../operations/dev-and-test.md)。
