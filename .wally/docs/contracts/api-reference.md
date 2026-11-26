---
kind: api-contract
scope: inbound-api
status: draft
origin: generated
source_paths: [src/octop_browser/cli.py, src/octop_browser/mcp_server.py, src/octop_browser/tool_interface.py, src/octop_browser/__init__.py, src/octop_browser/record/daemon.py]
symbols: [_build_parser, main, _ACTION_ALIAS, _TOOLS, _ACTION_MAP, list_tools, call_tool, _KNOWN_ACTIONS, browser_tool, __all__, dispatch]
upstream: [INDEX.md, overview/business-architecture.md]
downstream: [integrations/topology-and-mapping.md, contracts/error-codes.md]
---

# 入向接口契约全集（Inbound API / RPC / MCP / CLI Reference）

本仓是 Python 库 + CLI + MCP stdio/SSE 服务，无 HTTP REST 业务路由。入向面共 6 类：`browser_tool` 20 个动作、CLI 35 条命令、MCP 25 个工具、Python API 12 个导出、录制守护 5 个 JSON 命令、SSE 2 条路由，合计 99 项。全局无鉴权与租户层，身份隔离完全靠 `profile` 名映射到独立 Chrome `--user-data-dir`；运行参数由外部环境注入（见 [配置手册](configuration.md)）。

## 1. 公共协议、鉴权与响应包络规范

| 维度 | 精确实现规则 | 源码锚点 |
|---|---|---|
| 认证凭据提取 | 无登录态校验；MCP 的 `mcpServers.<name>.env` 注入 `BROWSER_USE_*`，不进 `inputSchema` | `src/octop_browser/mcp_server.py:28` |
| 资源归属隔离 | `profile` 名 → `ProfileManager.get_or_create` → 独立 `data_dir` 与 `cdp_port` | `src/octop_browser/profile.py:165` |
| 标准成功包络 | `ToolResult(success=True, content, metrics, metadata)`；CLI `--json` 输出 `model_dump(mode="json")` | `src/octop_browser/cli.py:502` |
| 标准失败包络 | `ToolResult(success=False, content="", error, metrics全零)`；CLI 打印 `ERROR: ...`、MCP 返回 `ERROR: ...` 文本 | `src/octop_browser/tool_interface.py:46`、`src/octop_browser/mcp_server.py:477` |
| MCP 工具声明 | `Tool(name, description, inputSchema)`，`type="object"` + `properties` + `required` | `src/octop_browser/mcp_server.py:24` |
| MCP 结果包络 | `list[TextContent]`，`TextContent(type="text", text=...)` | `src/octop_browser/mcp_server.py:479` |
| CLI 退出码 | 成功 `0`、失败 `1`；失败写 `sys.stderr` | `src/octop_browser/cli.py:532`、`:534` |
| daemon 协议 | 单行 JSON + `\n`，应答 `{"ok": bool, ...}` | `src/octop_browser/record/daemon.py:160`、`:165` |

## 2. 全量入向接口路由总表（Master Inbound Inventory）

### 2.1 `browser_tool` 动作白名单（20 项，`src/octop_browser/tool_interface.py:20`）

| 分组 | 动作 | 执行模式 | Handler 符号与锚点 | 参数组 |
|---|---|---|---|---|
| 导航 | `navigate` | 同步 | `BrowserSession.navigate` (`src/octop_browser/session.py:262`) | `url` |
| 导航 | `go_back` / `go_forward` / `reload` | 同步 | `src/octop_browser/session.py:272`、`:280`、`:288` | 无 |
| 页面状态 | `dom_tree` | 同步 | `src/octop_browser/session.py:300` | `level` |
| 页面状态 | `screenshot` | 同步 | `src/octop_browser/session.py:348` | `crop/element_ref/full_page/path` |
| 交互 | `click` | 同步 | `src/octop_browser/session.py:377` | `ref/selector/x/y` |
| 交互 | `type` / `fill` | 同步 | `src/octop_browser/session.py:396`、`:416` | `text/ref/selector` |
| 交互 | `press` / `select` / `scroll` / `hover` | 同步 | `src/octop_browser/session.py:436`、`:442`、`:462`、`:473` | `key/value/direction/amount/ref` |
| JS 与等待 | `eval_js` / `wait` | 同步 | `src/octop_browser/session.py:485`、`:491` | `expression` / `url_contains/text/selector/timeout_ms` |
| 标签 | `new_tab` / `switch_tab` / `close_tab` / `list_tabs` | 同步 | `src/octop_browser/session.py:563`、`:735`、`:766`、`:799` | `url/force_new/tab_id` |
| 生命周期 | `close_session` | 同步 | 特例分支 `src/octop_browser/tool_interface.py:125` | `kill` |

### 2.2 CLI 顶层命令（24 项，`src/octop_browser/cli.py:96`）

| 命令 | `argparse` 注册锚点 | 分发函数 | 对应动作 / 控制器 |
|---|---|---|---|
| `install-browser` | `:125` | `main` 直分支 (`:637`) | `ensure_chromium` |
| `navigate` | `:141` | `_run_action` (`:514`) | `navigate` |
| `open` | `:147` | `_run_action` | 强制 `list_tabs` + `urls`（`:520`） |
| `dom-tree` | `:167` | `_run_action` | `dom_tree` |
| `screenshot` | `:188` | `_run_action` | `screenshot` |
| `click` | `:201` | `_run_action` | `click` |
| `type` / `fill` | `:212` / `:220` | `_run_action` | `type` / `fill` |
| `press` / `wait` | `:230` / `:236` | `_run_action` | `press` / `wait` |
| `select` / `scroll` / `hover` | `:245` / `:254` / `:262` | `_run_action` | `select` / `scroll` / `hover` |
| `eval-js` | `:268` | `_run_action` | `eval_js` |
| `go-back` / `go-forward` / `reload` | `:275` | `_run_action` | 同名动作 |
| `new-tab` / `switch-tab` / `close-tab` / `list-tabs` | `:285` / `:290` / `:295` / `:300` | `_run_action` | 同名动作 |
| `close-session` | `:305` | `_run_action` | `close_session` |
| `record` | `:320` | `_run_record` (`:537`) | 10 个子命令，见 2.3 |
| `replay` | `:391` | `_run_replay` (`:610`) | 1 个子命令，见 2.3 |
| `--version` | `:111` | `_package_version` (`:47`) | 只读 |

### 2.3 CLI 二级子命令（11 项）

| 命令 | 注册锚点 | 分发分支 |
|---|---|---|
| `record doctor` | `:323` | `RecordController.doctor` (`src/octop_browser/cli.py:540`) |
| `record daemon-start` | `:327` | `ensure_daemon` (`:543`) |
| `record daemon-stop` | `:332` | `send_request({"command":"shutdown"})` (`:545`) |
| `record status` | `:337` | `send_request({"command":"status"})` (`:547`) |
| `record stop` | `:340` | `send_request({"command":"stop", ...})` (`:549`) |
| `record start` | `:346` | 进程内会话（`--duration>0`，`:557`）或 daemon (`:573`) |
| `record list` | `:368` | `RecordingStore().list_recordings()` (`:586`) |
| `record show` | `:371` | `RecordingStore().recording_summary()` (`:593`) |
| `record generate-steps` | `:377` | `RecordController().generate_steps()` (`:595`) |
| `record generate-skill` | `:383` | `RecordController().generate_skill()` (`:597`) |
| `replay run` | `:393` | `ReplayRunner().run()` (`:617`) |

### 2.4 MCP 工具（25 项，`src/octop_browser/mcp_server.py:24`）

| 工具组 | 工具名（`注册锚点`） | 分发目标 |
|---|---|---|
| 浏览器动作 | `browser_navigate` (`:25`)、`browser_dom_tree` (`:37`)、`browser_screenshot` (`:52`)、`browser_click` (`:76`)、`browser_type` (`:90`)、`browser_eval_js` (`:104`)、`browser_fill` (`:116`)、`browser_press` (`:130`)、`browser_wait` (`:142`) | `_ACTION_MAP` → `browser_tool` |
| 浏览器动作 | `browser_new_tab` (`:241`)、`browser_switch_tab` (`:252`)、`browser_close_tab` (`:264`)、`browser_list_tabs` (`:275`)、`browser_close_session` (`:285`) | `_ACTION_MAP` → `browser_tool` |
| 多标签 | `browser_open` (`:304`) | 特例 `browser_tool(list_tabs, urls=..., mode=...)` (`:464`) |
| 录制 | `browser_record_doctor` (`:156`)、`browser_record_start` (`:164`)、`browser_record_stop` (`:176`)、`browser_record_status` (`:188`)、`browser_record_list` (`:193`)、`browser_record_show` (`:198`) | `RecordController` / `RecordingStore` / `send_request` |
| 录制 | `browser_record_generate_steps` (`:207`)、`browser_record_generate_skill` (`:216`) | `RecordController` |
| 回放与安装 | `browser_replay_run` (`:228`)、`install_browser` (`:332`) | `ReplayRunner` / `install_chromium_stream` |

### 2.5 Python API 导出（12 项，`src/octop_browser/__init__.py:15`）

| 符号 | 类别 | 来源模块 |
|---|---|---|
| `BrowserSession`、`browser_tool` | class / async fn | `session.py` / `tool_interface.py` |
| `ToolResult`、`ActionMetrics`、`TabInfo` | Pydantic model | `models.py` |
| `OctopSettings`、`settings` | dataclass / 单例 | `settings.py` |
| `BrowserMode` | `Literal` 类型 | `mode.py` |
| `chromium_executable`、`ensure_chromium`、`install_chromium_stream`、`InstallEvent` | fn / async gen / TypedDict | `install.py` |

### 2.6 录制守护 JSON 命令（5 项）与 SSE 路由（2 项）

| 协议 | 精确路径 / `command` | 分发分支 | 锚点 |
|---|---|---|---|
| Unix socket | `ping` | `{"ok": True, "active": ...}` | `src/octop_browser/record/daemon.py:41` |
| Unix socket | `start` / `stop` / `status` / `shutdown` | `RecordDaemon.dispatch` | `:43`、`:64`、`:82`、`:84` |
| SSE HTTP | `GET /sse` | `handle_sse` | `src/octop_browser/mcp_server.py:515` |
| SSE HTTP | `POST /messages/` | `sse.handle_post_message` | `:516` |

## 3. 接口分组与逐项契约索引

接口总数超过 20，`api-reference.md` 仅保留公共协议与全量路由总表，逐接口入参 / 出参字典按业务分组下沉子页：[浏览器动作与 CLI 命令](api/browser-actions.md)、[MCP 工具](api/mcp-tools.md)、[录制回放与守护命令](api/record-replay.md)。错误分支全表见 [错误码字典](error-codes.md)，字段映射见 [参数组装映射](../integrations/topology-and-mapping.md)。

## 4. 逐接口入参 / 出参精确契约（示例锚点）

### `[action] dom_tree` — 导出分级 DOM

- **入口与编排链**：`browser_tool("dom_tree", level=...)` → `BrowserSession.dom_tree` (`src/octop_browser/session.py:300`) → `DOMBuilder.build` (`src/octop_browser/dom/builder.py:160`)，关联 [WF-03](../business/wf-dom-ref-targeting.md)。
- **入参字典**：`level`（`minimal|interactive|full|structured`，默认 `interactive`，`src/octop_browser/cli.py:179`）；`profile`（默认 `"default"`）。
- **出参结构**：`ToolResult.content` 为 DOM 文本或 JSON 字符串，`metadata` 为 `None`，`metrics.estimated_tokens = len(content)//4`（`src/octop_browser/session.py:327`）。
- **错误分支**：`level` 非法 → `ValueError("Unknown DOM level")` (`src/octop_browser/dom/builder.py:184`)；CDP 异常 → `success=False` (`:335`)。

另外 98 项的逐项 Schema 全部分布在三个子页，不存在任何按分组折叠的条目。

## 5. 共变耦合与新增接口清单（Agent Co-Change Playbook）

1. 白名单 / 注册表：`_KNOWN_ACTIONS`（`src/octop_browser/tool_interface.py:20`）、`BrowserSession` 同名方法、`_ACTION_ALIAS`（`src/octop_browser/cli.py:413`）、`_TOOLS` 与 `_ACTION_MAP`（`src/octop_browser/mcp_server.py:24`、`:349`）。
2. 参数翻译：`_action_kwargs`（`src/octop_browser/cli.py:426`）与 `call_tool`（`src/octop_browser/mcp_server.py:391`）。
3. 文档：本页总表 + 三个子页 + [业务能力总表](../business/index.md) + [术语表](../overview/glossary.md) + `.wiki-meta.json` 的 `pageOrder`。
4. 回归：`pytest tests/unit/test_cli.py tests/unit/test_mcp_server.py tests/unit/test_tool_interface.py`，命令见 [构建与单测映射](../operations/dev-and-test.md)。
