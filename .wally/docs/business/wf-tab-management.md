---
kind: workflow
scope: WF-08
status: draft
origin: generated
source_paths: [src/octop_browser/session.py, src/octop_browser/profile.py, src/octop_browser/cdp/launcher.py]
symbols: [BrowserSession.new_tab, switch_tab, close_tab, list_tabs, _find_blank_target_id, _switch_to_target_with_retry, _close_failed_new_target, _InternalCDPSession.switch_to_target, Profile.save_target, get_page_ws_url]
upstream: [business/index.md, business/wf-browser-session-lifecycle.md]
downstream: [business/wf-record-capture.md, integrations/downstream/chrome-cdp.md]
---

# WF-08 · 标签页管理与跨进程目标粘性闭环

`new_tab/switch_tab/close_tab/list_tabs` 管理 Chrome 页目标，`switch_to_target` 在切换后重建页面级 CDP WebSocket 并把 `targetId` 持久化到 `.octop-browser-target.json`，使短命 CLI 进程下次仍附着同一标签。核心难点是 `Target.activateTarget` 只聚焦 Chrome 标签、不迁移 WebSocket 绑定，因此必须显式重连（源码注释 `src/octop_browser/session.py:101`）。

## 1. 符号级端到端执行调用树

```text
Trigger: browser_tool("new_tab", url=..., force_new=False) -> BrowserSession.new_tab (src/octop_browser/session.py:563)
  ├─ current_url = _current_page_url() if url and not force_new (:574)
  ├─ [分支 A] url 且 current_url in _REUSABLE_BLANK_URLS -> 复用当前标签 _navigate_existing_tab (:578)
  ├─ [分支 B] url 且 _find_blank_target_id() 命中空白页 -> switch_to_target(blank) 后导航 (:582、:587)
  ├─ [分支 C] 否则 -> client.send("Target.createTarget", {"url": create_url}) (:594)
  │    ├─ target_id = cdp_result.get("targetId", "") (:597)
  │    ├─ _switch_to_target_with_retry(target_id, attempts=3, delay=0.1) (:599、:693)
  │    └─ [if create_url != url] _navigate_existing_tab(url) (:602)
  ├─ [失败补偿] navigation_result 失败且切过标签 -> _close_failed_new_target (:614、:658)
  └─ _record(result) -> ToolResult(content=target_id, metadata={"target_id": ...}) (:648)

switch_to_target(target_id, activate=True) (src/octop_browser/session.py:98)
  ├─ [guard] cfg.cdp_ws_url 非空 -> RuntimeError("Cannot switch tabs when connected via BROWSER_USE_CDP_WS_URL") (:107)
  ├─ [if activate] client.send("Target.activateTarget", {"targetId": target_id}) (:113)
  ├─ aiohttp GET http://{cdp_host}:{port}/json -> 找 type=="page" 且 id==target_id (:121、:125)
  ├─ [guard] 无 match 或 无 webSocketDebuggerUrl -> RuntimeError("No page target found for tab ...") (:133)
  ├─ 关闭旧 client、新建 CDPClient、ref_cache.invalidate() (:136、:141)
  ├─ 连接新 WS、重新 enable Page/DOM/Runtime、_apply_viewport (:142、:146)
  └─ profile.save_target(target_id) -> 写 .octop-browser-target.json (:147、src/octop_browser/profile.py:69)

list_tabs() (:799) -> GET /json -> 过滤 type=="page" -> TabInfo(tab_id,url,title,active) (:820)
  └─ active_id 优先取 load_target()，失效则退化为首个 page target (:810、:817)
```

## 2. 分阶段业务规则与分支判定表

| 阶段 | 负责函数（`路径:行号`） | 精确布尔条件 / 阈值 | 命中分支行为 | 状态或数据副作用 |
|---|---|---|---|---|
| 空白页判定 | `new_tab` (`:578`) | `current_url in _REUSABLE_BLANK_URLS`（`about:blank`、`chrome://newtab/`、`chrome://newtab`，`:30`） | 复用当前标签，不新建 target | 无新 target |
| 空白页搜索 | `_find_blank_target_id` (`:713`) | `cfg.cdp_ws_url` 非空直接返回 `None`；遍历 `/json` 排除当前 target | 命中即返回可复用 id | 无 |
| 强制新标签 | `new_tab` (`:591`) | `force_new=True` 或前两分支未命中 | `Target.createTarget {"url": url or "about:blank"}` | 产生新 `targetId` |
| 切换重试 | `_switch_to_target_with_retry` (`:693`) | `attempts=3`、`delay=0.1`，三次全失败抛最后异常 | 逐次 `switch_to_target` | 无 |
| 直连禁用切换 | `switch_to_target` (`:107`) | `cfg.cdp_ws_url` 非空 | 抛 `RuntimeError`，禁止 `switch_tab` | 无 |
| 目标丢失 | `switch_to_target` (`:133`) | `not match` 或缺 `webSocketDebuggerUrl` | `RuntimeError("No page target found for tab ...")` | 无 |
| ref 失效 | `switch_to_target` (`:141`) | 无条件 | `ref_cache.invalidate()`，切页后旧 ref 全部作废 | 清空 `_refs` |
| 粘性目标选择 | `get_page_ws_url` (`src/octop_browser/cdp/launcher.py:651`) | `profile.load_target()` 命中存活 page | 选该目标；否则 `clear_target()` 后取首个非 `about:blank` 页（`:663`） | `save_target(target_id)`（`:669`） |
| `close_tab` 空参 | `close_tab` (`:772`) | `tab_id` 为 `None` | 返回成功但内容 `No tab_id supplied; nothing to close.` | 不发送 CDP |
| `list_tabs` 空结果 | `list_tabs` (`:830`) | 无 page target | `content = "(no open tabs)"` | `metadata.tabs = []` |

## 3. 目标状态文件与 `TabInfo` 字段字典

| 载体 | 键 / 字段 | 类型 | 读写位置 |
|---|---|---|---|
| `.octop-browser-target.json` | `target_id` | `str` | `Profile.save_target` / `load_target`（`src/octop_browser/profile.py:69`、`:49`） |
| `.octop-browser-profiles.json` | `{profile_name: cdp_port}` | `dict[str,int]` | `ProfileManager._save_ports`（`:143`） |
| `/json` 目标元素 | `id`、`type`、`url`、`title`、`webSocketDebuggerUrl` | `str` | `src/octop_browser/cdp/launcher.py:677`、`:682` |
| `TabInfo` | `tab_id`、`url`、`title`、`active` | `str/str/str/bool` | `src/octop_browser/models.py:36`；构造于 `src/octop_browser/session.py:821` |
| `ToolResult.metadata`（`list_tabs`） | `tabs` 数组，元素含 `tab_id/url/title/active` | `list[dict]` | `src/octop_browser/session.py:846` |

## 4. 幂等、并发互斥与异常补偿回滚表

| 边界 / 故障场景 | 源码检测条件 | 保护 / 回滚 / 降级动作 |
|---|---|---|
| 新标签导航失败 | `navigation_result.success` 为假（`:614`） | `_close_failed_new_target` 切回 `previous_target_id` 并 `Target.closeTarget`（`:658`） |
| 目标切换暂时失败 | `_switch_to_target_with_retry` 三次重试（`:693`） | 0.1s 间隔重试，仍失败抛最后异常 |
| 缓存目标已死 | `chosen is None` 且 `sticky_id` 非空（`src/octop_browser/cdp/launcher.py:655`） | `profile.clear_target()` 后走启发式选页，避免持续付查找成本 |
| Chrome 无 page 目标 | `pages` 为空（`:641`） | `_create_blank_page_target` 用 PUT（回退 GET）`/json/new?about:blank` 补建（`:642`、`:685`） |
| 直连远端 WS | `cfg.cdp_ws_url` 非空（`:107`） | 明确拒绝 `switch_tab`，不静默降级 |
| 关闭异常 | `close_tab` 的 `except Exception`（`:786`） | 返回失败 `ToolResult`，不抛出 |

## 5. 共变耦合与修改清单（Agent Co-Change Playbook）

- **修改目标粘性**：`Profile.save_target/load_target`（`src/octop_browser/profile.py:69`、`:49`）、`switch_to_target`（`src/octop_browser/session.py:147`）与 `get_page_ws_url` 的 sticky 分支（`src/octop_browser/cdp/launcher.py:653`）三处联动；legacy 文件名常量在 `:29`。
- **新增导航类动作**：必须 `ref_cache.invalidate()`（对照 `src/octop_browser/session.py:141`），并核对 [DOM ref 流程](wf-dom-ref-targeting.md)。
- **修改 `TabInfo`**：`models.py`（`src/octop_browser/models.py:36`）、`list_tabs` 构造（`:821`）、`metadata.tabs` 序列化（`:846`）与 [领域模型](../business/domain-models/tool-result-and-metrics.md) 同步。
- **修改 `/json` 解包键**：`_find_blank_target_id`（`:713`）、`list_tabs`（`:799`）、`_list_page_targets`（`src/octop_browser/cdp/launcher.py:674`）共用同一目标字典结构，键名必须一致。
- **必跑流程闭环回归**：`pytest tests/unit/test_tool_interface.py tests/integration/test_session.py tests/unit/test_profile.py`，命令见 [构建与单测映射](../operations/dev-and-test.md)。
