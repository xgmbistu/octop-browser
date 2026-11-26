---
kind: api-contract
scope: api-browser-actions
status: draft
origin: generated
source_paths: [src/octop_browser/tool_interface.py, src/octop_browser/session.py, src/octop_browser/cli.py, src/octop_browser/actions/interact.py, src/octop_browser/actions/capture.py]
symbols: [_KNOWN_ACTIONS, browser_tool, _action_kwargs, _ACTION_ALIAS, BrowserSession, click, screenshot, wait, _resolve_coords]
upstream: [contracts/api-reference.md]
downstream: [business/wf-action-dispatch.md, contracts/error-codes.md]
---

# 浏览器动作与 CLI 命令逐接口契约

本页展开 [入向接口契约全集](../api-reference.md) 中 20 个 `browser_tool` 动作与 21 个 CLI 动作命令的逐项入参、出参与错误分支。全部动作统一返回 `ToolResult`；公共字段 `profile`（默认 `"default"`）与 `mode`/`headless` 仅在首次建会话生效（`src/octop_browser/tool_interface.py:108`）。

## 1. 公共入参与全局约定

| 位置 | 字段名 | 类型 | 必填 | 默认值 / 约束 | 含义与透传去向 |
|---|---|---|---|---|---|
| kwarg | `profile` | `str` | 否 | `"default"` | 会话注册表键，`_get_or_create_session`（`:57`） |
| kwarg | `mode` | `BrowserMode` | 否 | `None`（回落 `BROWSER_USE_MODE`） | 仅首次建会话生效（`:110`） |
| kwarg | `headless` | `bool \| None` | 否 | `None` | legacy 覆盖，优先级最高（`src/octop_browser/session.py:231`） |
| kwarg | `urls` | `list[str]` | 否 | `None` | 首次建会话时开多标签（`:113`） |
| CLI | `--profile` | `str` | 否 | `"default"` | `_add_common_args`（`src/octop_browser/cli.py:55`） |
| CLI | `--json` | `flag` | 否 | 关 | `result.model_dump(mode="json")`（`:505`） |
| CLI | `--headed/--headless/--auto` | 互斥 flag | 否 | `auto` | `_add_mode_args`（`:70`） |

`browser_tool` 未识别的动作返回 `Unknown action '<name>'. Valid: [...]`（`:120`），多余参数由 `getattr(sess, action)(**kwargs)` 触发 `TypeError` 并转成 `Invalid parameters for '<action>': ...`（`:183`）。

## 2. 20 个动作逐项入参 / 出参契约

| 动作 | 入参键（类型 / 默认） | `ToolResult.content` 成功形态 | `metadata` | Handler 锚点 |
|---|---|---|---|---|
| `navigate` | `url: str`（必填） | `Navigated to {url}` | `None` | `src/octop_browser/session.py:262` |
| `dom_tree` | `level: str = "interactive"`（四档枚举） | 四档 DOM 文本 / JSON | `None` | `:300` |
| `screenshot` | `crop=False`（保留）、`element_ref=None`、`full_page=False`、`path=None` | PNG 绝对路径字符串 | `path/url/title/full_page/element_ref/width/height/size_kb`（`src/octop_browser/actions/capture.py:206`） | `:348` |
| `click` | `ref/selector/x/y`（四选一，`src/octop_browser/actions/interact.py:32`） | `Clicked {desc} at (x, y)` | `None` | `:377` |
| `type` | `text: str`（必填）、`ref=None`、`selector=None` | `Typed {n} character(s)` | `None` | `:396` |
| `fill` | `text: str`、`ref=None`、`selector=None` | `Filled {n} character(s)` | `None` | `:416` |
| `press` | `key: str`（必填） | `Pressed {key}` | `None` | `:436` |
| `select` | `value: str`、`ref=None`、`selector=None` | `Selected {value}` | `None` | `:442` |
| `scroll` | `direction="down"`（4 向）、`amount=300` | `Scrolled {direction} by {amount}px` | `None` | `:462` |
| `hover` | `ref: str`（必填） | `Hovered over ref=... at (x, y)` | `None` | `:473` |
| `eval_js` | `expression: str`（必填） | JSON 字符串或 `dict`（`src/octop_browser/actions/js_eval.py:41`） | `None` | `:485` |
| `wait` | `url_contains/text/selector=None`、`timeout_ms=10000` | `Wait condition satisfied` | `None` | `:491` |
| `go_back` / `go_forward` | 无 | `Navigated back` / `Navigated forward` | `None` | `:272`、`:280` |
| `reload` | 无 | `Page reloaded` | `None` | `:288` |
| `new_tab` | `url=None`、`force_new=False` | `targetId` 字符串或复用说明 | `{"target_id": ...}`（`:611`） | `:563` |
| `switch_tab` | `tab_id: str`（必填） | `Activated tab {tab_id}` | `None` | `:735` |
| `close_tab` | `tab_id=None` | `Closed tab {tab_id}` 或 `No tab_id supplied` | `None` | `:766` |
| `list_tabs` | 无 | `[{id}] {title} — {url}` 多行或 `(no open tabs)` | `{"tabs": [...]}`（`:846`） | `:799` |
| `close_session` | `kill=False` | `Session '<profile>' closed.` | `None` | `src/octop_browser/tool_interface.py:125` |

`screenshot` 的 `element_ref` 优先于 `full_page`（`src/octop_browser/actions/capture.py:130`）；`full_page` 用 `Page.getLayoutMetrics().cssContentSize` 构造 `clip` 并置 `captureBeyondViewport=True`（`:150`、`:168`）。`wait` 每 `0.25s` 轮询 `Runtime.evaluate`，超时返回 `Timeout waiting for condition`（`src/octop_browser/session.py:501`、`:544`）。

## 3. CLI 动作命令参数字典（21 条）

| CLI 命令 | 位置参数 | 专属选项 | `_action_kwargs` 分支 |
|---|---|---|---|
| `navigate` | `url` | — | `src/octop_browser/cli.py:433` |
| `open` | `urls+`（1 个以上） | — | `:431`（改走 `list_tabs`） |
| `dom-tree` | — | `--level`（4 档枚举，默认 `interactive`） | `:435` |
| `screenshot` | — | `--full-page`、`--element-ref`、`--path` | `:437` |
| `click` | — | 互斥必填 `--ref` / `--selector` / `--xy X Y` | `:444` |
| `type` / `fill` | `text` | 可选 `--ref` / `--selector` | `:451`、`:457` |
| `press` | `key` | — | `:463` |
| `wait` | — | `--url-contains`、`--text`、`--selector`、`--timeout-ms`（默认 10000） | `:465` |
| `select` | `value` | 互斥必填 `--ref` / `--selector` | `:473` |
| `scroll` | — | `--direction`（`up/down/left/right`）、`--amount`（默认 300） | `:479` |
| `hover` | `ref` | — | `:482` |
| `eval-js` | `expression` | — | `:484` |
| `new-tab` | — | `--url` | `:486` |
| `switch-tab` | `tab_id` | — | `:489` |
| `close-tab` | — | `--tab-id` | `:491` |
| `close-session` | — | `--kill` | `:494` |
| `go-back` / `go-forward` / `reload` / `list-tabs` | — | 仅公共参数，无 kwargs | `:497` |

CLI 通过 `_ACTION_ALIAS` 把 `dom-tree→dom_tree`、`eval-js→eval_js`、`go-back→go_back`、`go-forward→go_forward`、`new-tab→new_tab`、`switch-tab→switch_tab`、`close-tab→close_tab`、`list-tabs→list_tabs`、`close-session→close_session` 共 9 项映射为下划线动作（`src/octop_browser/cli.py:413`）；`open` 在 `_run_action` 里强制改为 `list_tabs`（`:520`）。

## 4. 错误分支速查

| 条件 | 对外错误 | 锚点 |
|---|---|---|
| 未知动作 | `Unknown action '<name>'. Valid: [...]` | `src/octop_browser/tool_interface.py:120` |
| 参数多余 / 类型错 | `Invalid parameters for '<action>': ...` | `:183` |
| 会话创建失败 | `Failed to create session: {exc}` | `:168` |
| ref / 选择器未命中 | `Ref '...' not found. Call dom_tree() first.` / `Selector '...' matched no elements.` | `src/octop_browser/actions/interact.py:44`、`:55` |
| 截图空数据 | `Page.captureScreenshot returned empty data` | `src/octop_browser/actions/capture.py:176` |
| 非法 DOM 层级 | `Unknown DOM level: '<level>'` | `src/octop_browser/dom/builder.py:184` |

完整异常传播链见 [错误码字典](../error-codes.md)，逐动作调用链见 [动作分发流程](../../business/wf-action-dispatch.md)。

## 5. 共变耦合与修改清单（Agent Co-Change Playbook）

- **新增动作**：`_KNOWN_ACTIONS`（`src/octop_browser/tool_interface.py:20`）→ `BrowserSession` 方法 → `_ACTION_ALIAS` 与 `_action_kwargs`（`src/octop_browser/cli.py:413`、`:426`）→ MCP `_TOOLS`/`_ACTION_MAP`（`src/octop_browser/mcp_server.py:24`、`:349`）→ 本页第 2、3 节与 [入向接口契约全集](../api-reference.md) 总表。
- **修改入参键**：`_action_kwargs` 的分支、MCP `inputSchema` 的 `properties`（`src/octop_browser/mcp_server.py:28`）与 [参数组装映射](../../integrations/topology-and-mapping.md) 三处联动；`getattr` 动态分发要求参数名与 `BrowserSession` 方法签名逐字一致。
- **修改出参**：`ToolResult` 字段（`src/octop_browser/models.py:20`）、`_format_result`（`src/octop_browser/cli.py:502`）与 [领域模型](../../business/domain-models/tool-result-and-metrics.md) 同步。
- **回归**：`pytest tests/unit/test_tool_interface.py tests/unit/test_cli.py tests/unit/test_capture.py tests/unit/test_navigate_actions.py`，命令见 [构建与单测映射](../../operations/dev-and-test.md)。
