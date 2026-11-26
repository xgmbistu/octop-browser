---
kind: workflow
scope: WF-03
status: draft
origin: generated
source_paths: [src/octop_browser/dom/builder.py, src/octop_browser/dom/refs.py, src/octop_browser/actions/interact.py, src/octop_browser/session.py]
symbols: [DOMBuilder, build, _walk, _make_ref, RefCache, store, lookup, invalidate, _resolve_coords, _get_center, click, fill_text, select_value]
upstream: [business/index.md, contracts/api-reference.md]
downstream: [integrations/downstream/chrome-cdp.md, business/wf-replay.md]
---

# WF-03 · DOM 快照、ref 签发与 ref 驱动交互闭环

`dom_tree(level)` 拉取 `DOM.getDocument` 与页面 url/title，经 `DOMBuilder` 编译为四档文本，同时把可交互节点登记为稳定 `ref → nodeId`；`click/type/fill/hover/select` 用 ref 反查坐标后派发 `Input.dispatch*`。核心业务不变量：任何跨文档导航必须清空 `RefCache`，否则 Agent 拿到过期节点号。同步执行，产物为 DOM 文本与 `RefCache` 内存状态。

## 1. 符号级端到端执行调用树

```text
Trigger: browser_tool("dom_tree", level="interactive") -> BrowserSession.dom_tree (src/octop_browser/session.py:300)
  ├─ [1] doc = client.send("DOM.getDocument", {"depth": -1}); root = doc["root"] (:306)
  ├─ [2] info = client.send("Runtime.evaluate", {"expression": "...location.href...", "returnByValue": True}) (:308)
  │    └─ page_info = json.loads(info["result"]["value"]) -> url, title (:317)
  ├─ [3] builder = DOMBuilder(dom=root, url, title, ref_cache) (:320)
  ├─ [4] content = builder.build(level=level) (src/octop_browser/dom/builder.py:160)
  │    ├─ _walk 递归：tag in _INTERACTIVE_TAGS 或 role in _INTERACTIVE_ROLES 判可交互 (src/octop_browser/dom/builder.py:223)
  │    ├─ [guard] tag == "a" and not attrs.get("href") -> is_interactive = False (:225)
  │    ├─ ref = _make_ref(tag, counter) -> 前缀 inp/btn/lnk/sel/txt 或 tag[:3] (src/octop_browser/dom/builder.py:124)
  │    ├─ ref_cache.store(ref, node["nodeId"]) (:230)
  │    ├─ 递归 contentDocument / shadowRoots / _CONTEXT_TAGS (iframe/frame) (:274)
  │    └─ [level 分支] minimal -> _build_minimal (:298)；interactive -> _build_interactive (:304)；full -> _build_full (:337)；structured -> _build_structured (:359)
  └─ [5] tokens = len(content) // 4 -> ToolResult(success=True, content, metrics) (src/octop_browser/session.py:327)

Trigger: browser_tool("click", ref="btn_2") -> interact.click (src/octop_browser/actions/interact.py:63)
  ├─ _resolve_coords(client, ref_cache, ref, selector, x, y) (:32)
  │    ├─ [if ref] node_id = ref_cache.lookup(ref)；None -> CDPSessionError("Ref not found. Call dom_tree() first.") (:44)
  │    │    └─ box = client.send("DOM.getBoxModel", {"nodeId": node_id})；中心 = (content[0]+content[4])/2, (content[1]+content[5])/2 (:21)
  │    ├─ [elif selector] DOM.getDocument {"depth":0} + DOM.querySelector {"nodeId","selector"} (:48)
  │    └─ [elif x,y] 直接用坐标；否则 ValueError("Must provide ref, selector, or (x, y)") (:60)
  └─ Input.dispatchMouseEvent 两次（mousePressed/mouseReleased）(:74)
```

## 2. 分阶段业务规则与分支判定表

| 阶段 | 负责函数（`路径:行号`） | 精确布尔条件 / 阈值 | 命中分支行为 | 状态或数据副作用 |
|---|---|---|---|---|
| 可交互标签集 | `_walk` (`src/octop_browser/dom/builder.py:223`) | `tag in _INTERACTIVE_TAGS`（`button,input,select,textarea,a,label,form`，`:12`）或 `role in _INTERACTIVE_ROLES`（11 个角色，`:33`） | 满足才签发 ref | `ref_cache.store` |
| 锚点例外 | `_walk` (`:225`) | `tag == "a" and not attrs.get("href")` | 强制 `is_interactive=False`，不发 ref | 无 |
| 结构标签集 | `_walk` (`:259`) | `tag in _STRUCTURAL_TAGS`（`header/nav/main/footer/section/article/h1..h6/p/table`，`:15`） | 仅 `full` 层输出缩进文本 | `structural` 列表 |
| 跳过标签集 | `_walk` (`:203`) | `tag in _SKIP_TAGS`（`script/style/meta/link/noscript/svg/path/head/html/#document`，`:48`） | 不输出但继续递归子节点 | 无 |
| ref 命名 | `_make_ref` (`:124`) | 前缀映射 `input→inp`、`button→btn`、`a→lnk`、`select→sel`、`textarea→txt`，其余 `tag[:3]` | `f"{prefix}_{idx}"`，同类自增 | `counter[prefix]` |
| 文本截断 | `_subtree_text` (`:80`) | `len(" ".join(parts)) > 300` | 停止收集并 `[:300]` | 控制 token |
| 选择器候选 | `_selector_candidates` (`:97`) | 依次取 `data-testid/data-test/data-cy`、`id`、`name`、`aria-label`、`type` | 去重后输出最多 5 个（语义折叠阶段 `[:5]`） | 供回放匹配 |
| 导航失效 | `navigate` (`src/octop_browser/actions/navigate.py:28`) | 进入函数即 `ref_cache.invalidate()` | `go_back/go_forward/reload/switch_to_target` 同样调用 | 清空 `_refs` |
| token 估算 | `dom_tree` (`src/octop_browser/session.py:327`) | `len(content) // 4` | 写入 `ActionMetrics.estimated_tokens` | 会话累计 |

## 3. 四档 DOM 输出与字段字典

| `level` | 输出形态 | 关键字段 / 格式 | 构造位置 |
|---|---|---|---|
| `minimal` | 两行文本 | `Page: {url} \| "{title}"`、`Interactive elements: {n} \| Scroll: yes` | `src/octop_browser/dom/builder.py:298` |
| `interactive`（默认） | 逐行 `[ref=x] tag ...` | input 带 `[type]` 与 `placeholder`/`label`；button/a/select/textarea 各自格式 | `:304` |
| `full` | 结构标签 + 可交互清单 | `<tag ref=x type=... placeholder=...>` | `:337` |
| `structured` | JSON | `{"url", "title", "elements": [{"ref","tag","role","node_id", 可选 type/label/accessibleName/name/placeholder/text/id/nameAttr/testId/selectorCandidates/framePath/shadowPath/href}]}` | `:359` |

`structured` 的 `elements` 数组是 [回放流程](wf-replay.md) 中 `match_target` 的唯一输入（`src/octop_browser/record/matcher.py:13`），字段名变更会直接破坏目标匹配。`_build_structured` 里 `accessibleName` 同时写入 `name` 别名（`:374`）。

## 4. 幂等、并发互斥与异常补偿回滚表

| 边界 / 故障场景 | 源码检测条件 | 保护 / 回滚 / 降级动作 |
|---|---|---|
| ref 未命中 | `ref_cache.lookup(ref) is None`（`src/octop_browser/actions/interact.py:42`） | 抛 `CDPSessionError("Ref '...' not found. Call dom_tree() first.")`，提示重新取 DOM |
| 选择器无匹配 | `result.get("nodeId", 0)` 为 0（`:53`） | `CDPSessionError("Selector '...' matched no elements.")` |
| 无目标参数 | 三者皆空（`:60`） | `ValueError("Must provide ref, selector, or (x, y)")` |
| `<select>` 无法解析 | `objectId` 缺失（`src/octop_browser/actions/interact.py:240`） | `CDPSessionError("Could not resolve ref '...'.")` |
| 导航后旧 ref | `RefCache.invalidate()`（`src/octop_browser/dom/refs.py:23`） | 清空全部映射，迫使 Agent 重新 `dom_tree` |
| `DOMBuilder.build` 未知层级 | `level` 不在四档（`:184`） | `ValueError(f"Unknown DOM level: {level!r}")` |

## 5. 共变耦合与修改清单（Agent Co-Change Playbook）

- **新增可交互标签或角色**：`_INTERACTIVE_TAGS` / `_INTERACTIVE_ROLES`（`src/octop_browser/dom/builder.py:12`、`:33`）、`_make_ref` 前缀表（`:124`）与 `recorder.js` 的 `roleOf`（`src/octop_browser/record/injected/recorder.js:75`）联动。
- **修改 `structured` 字段**：`_build_structured`（`:359`）、`matcher.match_target` 的打分键（`src/octop_browser/record/matcher.py:19`）与 [语义折叠](wf-semantic-steps.md) 的 `_compact_target`（`src/octop_browser/record/semantic.py:44`）三处同步。
- **新增导航类动作**：必须调用 `ref_cache.invalidate()`（对照 `src/octop_browser/actions/navigate.py:28`），并在 [会话引擎](../architecture/browser-session-engine.md) 的不变量表登记。
- **必跑流程闭环回归**：`pytest tests/unit/test_dom_builder.py tests/unit/test_refs.py tests/unit/test_navigate_actions.py tests/unit/test_record_replay_replay_runner.py`，命令见 [构建与单测映射](../operations/dev-and-test.md)。
