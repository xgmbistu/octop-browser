---
kind: api-contract
scope: inbound-api
status: draft
origin: generated
source_paths: [src/octop_browser/tool_interface.py, src/octop_browser/cli.py, src/octop_browser/mcp_server.py, src/octop_browser/session.py]
symbols: [browser_tool, _build_parser, main, call_tool, _TOOLS, BrowserSession]
upstream: [../INDEX.md]
downstream: [api/mcp-tools.md, api/cli-commands.md, api/python-api.md, ../integrations/topology-and-mapping.md, error-codes.md]
---

# 入向接口契约全集（Python / MCP / CLI Reference）

本仓对外不监听 HTTP 业务端口，入口共三类：Python `browser_tool()`、MCP 的 25 个 Tool、CLI 的 24 个顶层命令（含 10 个 `record` 子命令与 1 个 `replay run`）。总数超过 20，故本页保留公共协议与全量路由总表，逐接口 Schema 拆到 `api/` 子页。

## 1. 公共协议、隔离与响应包络规范

| 维度 | 精确实现规则 | 源码锚点 |
|---|---|---|
| 会话身份 | 所有入口用 `profile` 字符串隔离；默认 `"default"` | `src/octop_browser/tool_interface.py:63-68`、`src/octop_browser/cli.py:57-61` |
| 动作白名单 | 19 个合法 action，非法时返回合法集合排序后的错误 | `src/octop_browser/tool_interface.py:20-43,120-123` |
| 统一返回包络 | `ToolResult(success, content, error, metrics, metadata)`；CLI `--json` 输出 `model_dump(mode="json")` | `src/octop_browser/models.py:20-33`、`src/octop_browser/cli.py:502-511` |
| MCP 返回包络 | 每个 Tool 返回 `list[TextContent]`；浏览器动作失败文本前缀 `ERROR: ` | `src/octop_browser/mcp_server.py:476-479` |
| 录制命令包络 | CLI/MCP 录制类命令输出 `{"ok": bool, ...}`；daemon 不可达时给可操作错误 | `src/octop_browser/record/daemon.py:148-159`、`src/octop_browser/cli.py:604-607` |
| 回放包络 | `ReplayRunner.run()` 返回 `status=running\|passed\|failed` 及 `steps[]`、`verification[]`、`reportPath` | `src/octop_browser/record/replay.py:35-43,291-298` |
| 传输 | MCP 默认 stdio；`MCP_PORT` 设置后启用 SSE + `/sse`、`/messages/` | `src/octop_browser/mcp_server.py:482-530` |
| 错误退出码 | CLI 动作失败退出 1，录制 `ok=False` 退出 1，回放非 `passed` 退出 1 | `src/octop_browser/cli.py:531-534,604-607,620-623` |

## 2. 全量入向接口路由总表

### 2.1 Python 公共 API（`from octop_browser import ...`）

| 分组 | 接口 | 类型 | 执行模式 | Handler 符号与锚点 | 下游落点 |
|---|---|---|---|---|---|
| 核心 | `BrowserSession` | class | 异步上下文管理器 | `src/octop_browser/session.py:174-196` | CDP |
| 核心 | `browser_tool` | async fn | 协程直出 | `src/octop_browser/tool_interface.py:91-212` | `BrowserSession` |
| 核心 | `ToolResult` / `ActionMetrics` / `TabInfo` | model | 数据 | `src/octop_browser/models.py:10-42` | — |
| 配置 | `OctopSettings` / `settings` | dataclass / 单例 | 数据 | `src/octop_browser/settings.py:109-185` | — |
| 类型 | `BrowserMode` | type alias | 数据 | `src/octop_browser/mode.py:21` | — |
| 安装 | `chromium_executable` / `ensure_chromium` / `install_chromium_stream` / `InstallEvent` | fn / async gen / TypedDict | 同步 / 流式 | `src/octop_browser/install.py:68-74,94-100,280-369,486-620` | Playwright CDN |
| 会话动作 | `navigate` / `go_back` / `go_forward` / `reload` | async method | 协程 | `src/octop_browser/session.py:262-294` | `actions/navigate.py` |
| 会话动作 | `dom_tree` / `screenshot` | async method | 协程 | `src/octop_browser/session.py:300-371` | `dom/builder.py`、`actions/capture.py` |
| 会话动作 | `click` / `type` / `fill` / `press` / `select` / `scroll` / `hover` | async method | 协程 | `src/octop_browser/session.py:377-479` | `actions/interact.py` |
| 会话动作 | `eval_js` / `wait` | async method | 协程（wait 轮询 0.25s） | `src/octop_browser/session.py:485-557` | `actions/js_eval.py`、`Runtime.evaluate` |
| 会话动作 | `new_tab` / `switch_tab` / `close_tab` / `list_tabs` | async method | 协程 | `src/octop_browser/session.py:563-869` | `Target.*` + HTTP `/json` |
| 会话生命周期 | `close(kill=False)` / `metrics_summary()` | async / sync method | 协程 / 直出 | `src/octop_browser/session.py:875-889` | 本地状态 |

导出的 13 个符号清单位于 `src/octop_browser/__init__.py:15-28`。逐参数字典见 [`api/python-api.md`](api/python-api.md)。

### 2.2 MCP Tools（25 个）

| 分组 | Tool 名称 | 方法 | 分发路径 | 定义锚点 |
|---|---|---|---|---|
| 浏览器动作（14） | `browser_navigate`, `browser_dom_tree`, `browser_screenshot`, `browser_click`, `browser_type`, `browser_eval_js`, `browser_fill`, `browser_press`, `browser_wait`, `browser_new_tab`, `browser_switch_tab`, `browser_close_tab`, `browser_list_tabs`, `browser_close_session` | call_tool → `_ACTION_MAP` → `browser_tool` | 反射到 `BrowserSession` | `src/octop_browser/mcp_server.py:24-331,349-364,459-479` |
| 多标签（1） | `browser_open` | call_tool 特例：`list_tabs` + `urls` | `browser_tool` | `src/octop_browser/mcp_server.py:304-331,462-473` |
| 录制（8） | `browser_record_doctor`, `browser_record_start`, `browser_record_stop`, `browser_record_status`, `browser_record_list`, `browser_record_show`, `browser_record_generate_steps`, `browser_record_generate_skill` | daemon / 本地 Store | `RecordController` / `send_request` | `src/octop_browser/mcp_server.py:156-227,395-450` |
| 回放（1） | `browser_replay_run` | `ReplayRunner.run` | 本地 Store + `browser_tool` | `src/octop_browser/mcp_server.py:228-240,451-457` |
| 安装（1） | `install_browser` | `install_chromium_stream` | 子进程流 | `src/octop_browser/mcp_server.py:332-346,372-388` |

逐 Tool `inputSchema` 见 [`api/mcp-tools.md`](api/mcp-tools.md)。

### 2.3 CLI 命令（24 顶层 + 11 子命令）

| 分组 | 命令 | 入口 | 定义锚点 |
|---|---|---|---|
| 安装 | `install-browser` | `main()` 分支 | `src/octop_browser/cli.py:124-138,637-643` |
| 单步动作 | `navigate` / `open` / `dom-tree` / `screenshot` / `click` / `type` / `fill` / `press` / `wait` / `select` / `scroll` / `hover` / `eval-js` | `_run_action()` | `src/octop_browser/cli.py:140-272,514-534` |
| 历史与标签 | `go-back` / `go-forward` / `reload` / `new-tab` / `switch-tab` / `close-tab` / `list-tabs` / `close-session` | `_run_action()` | `src/octop_browser/cli.py:274-317,514-534` |
| 录制 | `record doctor` / `daemon-start` / `daemon-stop` / `status` / `stop` / `start` / `list` / `show` / `generate-steps` / `generate-skill` | `_run_record()` | `src/octop_browser/cli.py:319-388,537-607` |
| 回放 | `replay run` | `_run_replay()` | `src/octop_browser/cli.py:390-402,610-623` |
| 元信息 | `--version` / `--help` | `argparse` | `src/octop_browser/cli.py:111-122` |

逐命令参数见 [`api/cli-commands.md`](api/cli-commands.md)。

## 3. 接口分组交叉速查

| 能力 | Python | MCP | CLI | 共变锚点 |
|---|---|---|---|---|
| 点击元素 | `session.click(ref=...)` | `browser_click` | `click --ref` | `src/octop_browser/tool_interface.py:20-43` |
| 结构化 DOM | `session.dom_tree(level="structured")` | `browser_dom_tree` | `dom-tree --level structured` | `src/octop_browser/dom/builder.py:10` |
| 录制 | 无包级导出，走 `RecordController` | `browser_record_start` | `record start` | `src/octop_browser/record/recorder.py:304-417` |
| 安装 | `ensure_chromium` / `install_chromium_stream` | `install_browser` | `install-browser` | `src/octop_browser/install.py:280-369` |

## 4. 逐接口精确契约入口

三条能力线的完整 Schema 与错误分支分别收录于：
- [`api/python-api.md`](api/python-api.md)：`browser_tool` 与 `BrowserSession` 全部方法的参数表、返回与错误分支。
- [`api/mcp-tools.md`](api/mcp-tools.md)：25 个 Tool 的 `inputSchema` 属性、必填项与默认值。
- [`api/cli-commands.md`](api/cli-commands.md)：每个子命令的位置参数、选项、退出码与 `--json` 行为。

错误分支统一汇总在 [`error-codes.md`](error-codes.md)，字段流转向见 [`../integrations/topology-and-mapping.md`](../integrations/topology-and-mapping.md)。
