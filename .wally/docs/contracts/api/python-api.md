---
kind: api-contract
scope: python-api
status: draft
origin: generated
source_paths: [src/octop_browser/__init__.py, src/octop_browser/tool_interface.py, src/octop_browser/session.py, src/octop_browser/models.py, src/octop_browser/hooks.py, src/octop_browser/install.py, src/octop_browser/record/recorder.py, src/octop_browser/record/replay.py]
symbols: [browser_tool, BrowserSession, ToolResult, ActionMetrics, HooksMixin, ensure_chromium, install_chromium_stream, RecordController, ReplayRunner]
upstream: [../api-reference.md]
downstream: [../error-codes.md, ../../integrations/topology-and-mapping.md]
---

# Python API 逐接口契约

包根导出 13 个符号（`src/octop_browser/__init__.py:15-28`）。核心入口是异步的 `browser_tool()` 与 `BrowserSession`；录制/回放类不在包根导出，需从 `octop_browser.record` 导入（`src/octop_browser/record/__init__.py:14-23`）。

## 1. 包根导出与类型契约

| 符号 | 类型 | 用途与锚点 |
|---|---|---|
| `BrowserSession` | class | 持久会话，`await BrowserSession.create(profile="work")` (`src/octop_browser/session.py:174-196`) |
| `browser_tool` | async fn | 无状态动作分发 (`src/octop_browser/tool_interface.py:91-212`) |
| `ToolResult` / `ActionMetrics` / `TabInfo` | Pydantic model | 统一返回包络 (`src/octop_browser/models.py:10-42`) |
| `OctopSettings` / `settings` | dataclass / 单例 | 配置对象与进程默认 (`src/octop_browser/settings.py:109-185`) |
| `BrowserMode` | type alias | `auto\|headed\|headless` (`src/octop_browser/mode.py:21`) |
| `InstallEvent` / `chromium_executable` / `ensure_chromium` / `install_chromium_stream` | TypedDict / fn / async gen | 安装引导 (`src/octop_browser/install.py:81-100,280-369,486-620`) |

## 2. `browser_tool()` 精确签名与行为

```python
await browser_tool(action: str, profile: str = "default",
                   headless: bool | None = None, mode: BrowserMode | None = None,
                   urls: list[str] | None = None, **kwargs) -> ToolResult
```

| 参数 | 位置 | 类型 | 必填 | 默认值 / 校验 | 含义与透传去向 |
|---|---|---|---|---|---|
| `action` | 调用 | `str` | 是 | 必须属于 `_KNOWN_ACTIONS` 19 项 | 反射到 `BrowserSession` 同名方法 (`src/octop_browser/tool_interface.py:20-43,179-182`) |
| `profile` | 调用 | `str` | 否 | `"default"` | `_registry` 键 + Chrome user-data-dir 名 (`:63-68`) |
| `headless` | 调用 | `bool \| None` | 否 | `None` | 仅首次创建会话生效，优先级高于 mode (`src/octop_browser/session.py:231-235`) |
| `mode` | 调用 | `BrowserMode \| None` | 否 | `None` | 缺省读 `cfg.browser_mode` |
| `urls` | 调用 | `list[str] \| None` | 否 | `None` | 首个 URL 导航当前页，其余 `new_tab(force_new=True)` (`:170-177`) |
| `**kwargs` | 调用 | `Any` | 视动作而定 | — | 原样传给会话方法；`TypeError` 被翻译为参数错误 (`:183-184`) |

**错误分支**：非法 action → `_error_result(action, "Unknown action ...")`；`close_session` 残留 kwargs → 参数错误；会话创建异常 → `"Failed to create session: ..."`；断链 → 重建后重试一次；非断链异常 → 错误字符串回传而不抛出（`src/octop_browser/tool_interface.py:120-212`）。

## 3. `BrowserSession` 生命周期与方法契约

### 3.1 创建与关闭

| 方法 | 签名 | 契约要点 |
|---|---|---|
| `create` | `async classmethod (profile="default", headless=None, mode=None, urls=None, profile_manager=None, settings=None) -> BrowserSession` | 模式优先级 `headless > mode > cfg.browser_mode`；`urls` 逐项开标签 (`src/octop_browser/session.py:198-250`) |
| `__aenter__` / `__aexit__` | async | 上下文管理器；退出时调用 `close()` (`:252-256`) |
| `close` | `async (kill: bool = False) -> None` | `kill=True` 触发空闲控制器或 `terminate_browser()`；profile 数据与登录态保留 (`:887-889`、`src/octop_browser/session.py:149-163`) |
| `metrics_summary` | `() -> dict[str, Any]` | 返回 `total_actions`、`total_duration_ms`、`total_estimated_tokens`、`errors` (`:875-881`) |

### 3.2 动作方法与参数字典

| 方法 | 关键参数（默认值） | 返回内容 | 锚点 |
|---|---|---|---|
| `navigate` | `url: str` | `"Navigated to <url>"` | `src/octop_browser/session.py:262-270` |
| `go_back` / `go_forward` / `reload` | 无 | 固定文本 | `:272-294` |
| `dom_tree` | `level: DOMLevel = "interactive"` | DOM 文本或 JSON；异常兜底空串 | `:300-346` |
| `screenshot` | `crop=False`, `element_ref=None`, `full_page=False`, `path=None` | PNG 路径；`metadata` 含 8 键 | `:348-371` |
| `click` | `ref=None`, `selector=None`, `x=None`, `y=None` | `"Clicked <desc> at (x, y)"` | `:377-394` |
| `type` | `text: str`, `ref=None`, `selector=None` | `"Typed N character(s)"` | `:396-414` |
| `fill` | `text: str`, `ref=None`, `selector=None` | `"Filled N character(s)"` | `:416-434` |
| `press` | `key: str` | `"Pressed <key>"` | `:436-440` |
| `select` | `value: str`, `ref=None`, `selector=None` | `"Selected <value>"` | `:442-460` |
| `scroll` | `direction="down"`, `amount=300` | `"Scrolled <direction> by <amount>px"` | `:462-471` |
| `hover` | `ref: str` | `"Hovered over ref=... at (x, y)"` | `:473-479` |
| `eval_js` | `expression: str` | JSON 字符串或字典；JS error 为失败 | `:485-489` |
| `wait` | `url_contains=None`, `text=None`, `selector=None`, `timeout_ms=10000` | `"Wait condition satisfied"` 或超时失败 | `:491-557` |
| `new_tab` | `url=None`, `force_new=False` | `content=target_id`，`metadata.target_id` | `:563-649` |
| `switch_tab` | `tab_id: str` | `"Activated tab <id>"` | `:735-764` |
| `close_tab` | `tab_id: str \| None` | `"Closed tab <id>"` 或无操作提示 | `:766-797` |
| `list_tabs` | 无 | 每行 `[id] title — url`；`metadata.tabs` 为 `TabInfo` 列表 | `:799-869` |

所有方法统一返回 `ToolResult`（`src/octop_browser/models.py:20-33`），并经过 `_fire(before_action)` 与 `_record()` 的指标累计（`src/octop_browser/session.py:895-903`）。

## 4. Hook 事件契约

`BrowserSession` 混入 `HooksMixin`（`src/octop_browser/hooks.py:19-25`），`@session.on(event)` 注册回调，回调可同步或异步；异常只记日志不中断动作（`src/octop_browser/hooks.py:45-53`）。

| 事件 | 载荷 | 触发时机 | 锚点 |
|---|---|---|---|
| `before_action` | `{"action": str, "params": dict}` | 每个动作体执行前 | `src/octop_browser/session.py:263-265` |
| `after_action` | `ActionMetrics` | 动作成功并记录后 | `src/octop_browser/session.py:903` |
| `action_error` | `ToolResult` | 动作失败并记录后 | `src/octop_browser/session.py:899-901` |
| `page_navigated` | 无 | 保留事件，`on()` 接受但当前无代码路径发出 | `src/octop_browser/hooks.py:14-16,27-43` |

## 5. 录制与回放子包 API（非包根导出）

| 类/函数 | 签名 | 返回值 | 锚点 |
|---|---|---|---|
| `RecordController.doctor` | `async (profile="default") -> dict` | `ok/profile/cdpPort/pageWsUrl` | `src/octop_browser/record/recorder.py:341-348` |
| `RecordController.start_in_process` | `async (profile, privacy=None, name=None) -> tuple[RecordSession, dict]` | 会话与启动信息 | `:350-395` |
| `RecordController.generate_steps` / `generate_skill` | `(recording_id, ...)` | `ok/stepsPath` 或 `ok/skillDraft` | `:397-417` |
| `ReplayRunner.run` | `async (recording_id, profile="default", inputs=None) -> dict` | 回放报告 + `reportPath` | `src/octop_browser/record/replay.py:25-298` |
| `RecordingStore` | `(cfg=None)` | 录制目录与文件读写 | `src/octop_browser/record/store.py:14-162` |

## 6. 共变耦合与修改清单

1. 改包根导出：同步 `src/octop_browser/__init__.py:15-28` 与 `../api-reference.md` 导出表。
2. 改任意动作签名：同步 `[_KNOWN_ACTIONS](src/octop_browser/tool_interface.py:20-43)`、CLI/MCP Schema 与 `tests/unit/test_tool_interface.py`。
3. 改 `ToolResult` 字段：影响 `HooksMixin` 的 `action_error` 载荷、CLI JSON 输出与所有断言，跑 `tests/unit/test_models.py`、`tests/unit/test_hooks.py`。
4. 改安装导出：保持 `ensure_chromium() -> bool` 与 `install_chromium_stream() -> AsyncGenerator[InstallEvent]` 形态，跑 `tests/unit/test_install.py`。

## 7. 关联文档

- [入向接口全集](../api-reference.md) · [浏览器引擎组件](../../architecture/browser-engine.md) · [数据模型](../../business/domain-models/index.md)
