---
kind: workflow
scope: WF-02
status: draft
origin: generated
source_paths: [src/octop_browser/tool_interface.py, src/octop_browser/session.py, src/octop_browser/models.py, src/octop_browser/hooks.py]
symbols: [browser_tool, _KNOWN_ACTIONS, _error_result, _is_disconnected_error, _get_or_create_session, _drop_session, BrowserSession._record, HooksMixin._fire, ToolResult, ActionMetrics]
upstream: [business/index.md, contracts/api-reference.md]
downstream: [integrations/downstream/chrome-cdp.md, business/wf-dom-ref-targeting.md]
---

# WF-02 · 单动作分发、执行与结果归一化闭环

`browser_tool(action, profile, **kwargs)` 是全仓统一执行入口：CLI、MCP、Python API 与 [回放流程](wf-replay.md) 都收敛到这里。流程把动作字符串映射为 `BrowserSession` 方法，统一包成 `ToolResult`，并在成功/失败后触发 hooks 与指标累计。同步执行，产物仅为一个 `ToolResult`（`success/content/error/metrics/metadata`）。

## 1. 符号级端到端执行调用树

```text
Trigger: browser_tool(action, profile="default", mode=None, urls=None, **kwargs) (src/octop_browser/tool_interface.py:91)
  ├─ [guard] action not in _KNOWN_ACTIONS -> _error_result("Unknown action '...'. Valid: [...]") (:120)
  ├─ [branch action == "close_session"] (:125)
  │    ├─ kill = bool(kwargs.pop("kill", False))；残留 kwargs -> _error_result (:126)
  │    ├─ [if sess in _registry] await sess.close(kill=kill) (:135)
  │    ├─ [elif kill and not settings.cdp_ws_url] terminate_browser(managed_profile, cdp_host) (:140)
  │    └─ return ToolResult(success=True, content="Session '<profile>' closed.", metrics=...) (:152)
  ├─ [session] sess = _get_or_create_session(profile, headless, mode, urls) (:164)
  │    └─ 失败 -> _error_result("Failed to create session: {exc}") (:168)
  ├─ [urls 补开标签] if urls and profile in _registry -> navigate/new_tab(force_new=True) (:172)
  ├─ [dispatch] method = getattr(sess, action); result = await method(**kwargs) (:180)
  │    ├─ TypeError -> _error_result("Invalid parameters for '<action>': {exc}") (:183)
  │    ├─ _is_disconnected_error(exc) 为真 -> _drop_session + 重建会话重试一次 (:186)
  │    └─ 其他异常 -> logger.exception + _error_result(action, str(exc)) (:211)
  └─ [return] ToolResult -> BrowserSession._record(result) (src/octop_browser/session.py:895)
       ├─ _action_count += 1；累计 duration_ms 与 estimated_tokens (:896)
       └─ [if not success] _errors += 1 且 _fire("action_error", result)；else _fire("after_action", metrics) (:899)
```

## 2. 分阶段业务规则与分支判定表

| 阶段 | 负责函数（`路径:行号`） | 精确布尔条件 / 规则 | 命中分支行为 | 副作用 |
|---|---|---|---|---|
| 动作白名单 | `browser_tool` (`src/octop_browser/tool_interface.py:120`) | `action` 不在冻结集合 `_KNOWN_ACTIONS`（20 项，`:20`） | 返回 `success=False`，不建会话 | 空 `ActionMetrics`（`duration_ms=0`） |
| `close_session` 参数 | `browser_tool` (`:125`) | `kill = bool(kwargs.pop("kill", False))`，之后 `kwargs` 必须为空 | 残留键返回 `Invalid parameters for 'close_session'` | 从 `_registry` 弹出会话 |
| 会话复用 | `_get_or_create_session` (`:57`) | `profile not in _registry` 才 `BrowserSession.create` | 命中即复用，忽略后续 `mode`/`headless`/`urls` 的建会话语义 | `_registry[profile] = sess` |
| 动态分发 | `getattr(sess, action)` (`:180`) | 方法名与动作字符串同名 | `TypeError` 判为参数错误而非会话故障 | 调用 `BrowserSession` 方法 |
| 断线重连 | `_is_disconnected_error` (`:83`) | `CDPSessionError` 且文本含 `not connected` 或 `connection lost` | `_drop_session` 后重建会话并重试一次 | 重试仍失败则 `_error_result` |
| 错误结果构造 | `_error_result` (`:46`) | 任意失败分支 | 固定 `content=""`、`error=message`、全零 `ActionMetrics` | 不触发 `after_action` |
| hooks 顺序 | `HooksMixin._fire` (`src/octop_browser/hooks.py:45`) | 回调抛异常被 `except Exception` 吞掉并 `logger.exception` | 单个坏 hook 不影响动作返回 | 逐回调 `await`（协程才等待） |
| 指标口径 | `_record` (`src/octop_browser/session.py:895`) | `result.metrics.estimated_tokens` 累加 | `metrics_summary()` 返回 4 键汇总（`:875`） | 失败才计入 `_errors` |

## 3. 结果实体与事件包络

| `ToolResult` 字段 | 类型 | 必填 / 默认 | 构造位置 |
|---|---|---|---|
| `success` | `bool` | 必填 | `src/octop_browser/models.py:29`；`_error_result` 置 `False`（`src/octop_browser/tool_interface.py:48`） |
| `content` | `str \| dict` | 必填 | 失败恒为 `""`；成功由各动作填充，如 `dom_tree` 文本（`src/octop_browser/session.py:334`） |
| `error` | `str \| None` | 默认 `None` | `src/octop_browser/models.py:31` |
| `metrics` | `ActionMetrics` | 必填 | `action/duration_ms/dom_nodes_scanned/estimated_tokens/screenshot_size_kb`（`src/octop_browser/models.py:10`） |
| `metadata` | `dict \| None` | 默认 `None` | `screenshot` 填 `path/url/title/full_page/element_ref/width/height/size_kb`（`src/octop_browser/actions/capture.py:206`） |

`_VALID_EVENTS` 为 `before_action/after_action/action_error/page_navigated` 四项（`src/octop_browser/hooks.py:14`），其中 `page_navigated` 仅注册、当前无代码路径触发（`:33`）。`before_action` 由各 `BrowserSession` 方法在动作体前显式 `_fire`（如 `src/octop_browser/session.py:263`）。

## 4. 幂等、并发互斥与异常补偿回滚表

| 边界 / 故障场景 | 源码检测条件 | 保护 / 回滚 / 降级动作 |
|---|---|---|
| 会话创建抛异常 | `except Exception` (`src/octop_browser/tool_interface.py:167`) | 返回 `_error_result`，不把半建会话写入 `_registry` |
| 参数类型不匹配 | `except TypeError` (`:183`) | 判定为调用方参数错误，不触发重连 |
| 陈旧会话断连 | `_is_disconnected_error` (`:83`) | `_drop_session` 关闭并从注册表移除，重建后重试一次（`:192`） |
| 重试再次失败 | `except Exception as retry_exc` (`:204`) | 记录 `logger.exception` 并返回错误，不无限重试 |
| `close_session` 关闭异常 | `except Exception` (`:136`) | 仅 debug 日志，仍返回 `success=True` |
| 动作内部异常 | `BrowserSession.dom_tree` 的 `except Exception` (`src/octop_browser/session.py:335`) | 动作自身包成失败 `ToolResult`，再经 `_record` 触发 `action_error` |

## 5. 共变耦合与修改清单（Agent Co-Change Playbook）

- **新增动作**：`_KNOWN_ACTIONS`（`src/octop_browser/tool_interface.py:20`）→ `BrowserSession` 同名方法（`src/octop_browser/session.py:262`）→ CLI `_ACTION_ALIAS`（`src/octop_browser/cli.py:413`）→ MCP `_ACTION_MAP`（`src/octop_browser/mcp_server.py:349`）→ [术语表](../overview/glossary.md)。
- **修改 `ToolResult` 字段**：`models.py`（`src/octop_browser/models.py:20`）、`_error_result`（`src/octop_browser/tool_interface.py:46`）、`_format_result` 的 `model_dump` 序列化（`src/octop_browser/cli.py:505`）与 [领域模型](../business/domain-models/tool-result-and-metrics.md) 一起改。
- **修改 hooks 事件集**：`_VALID_EVENTS`（`src/octop_browser/hooks.py:14`）、`_record` 的两处 `_fire`（`src/octop_browser/session.py:901`）与 README 事件表同步；新增事件若无人触发属死路径，须在 [高危雷区](../operations/pitfalls-and-adr.md) 登记。
- **必跑流程闭环回归**：`pytest tests/unit/test_tool_interface.py tests/unit/test_hooks.py tests/unit/test_models.py`，命令见 [构建与单测映射](../operations/dev-and-test.md)。
