---
kind: api-contract
scope: api-mcp-tools
status: draft
origin: generated
source_paths: [src/octop_browser/mcp_server.py, src/octop_browser/tool_interface.py]
symbols: [_TOOLS, _ACTION_MAP, list_tools, call_tool, _handle_install_browser, Tool, TextContent]
upstream: [contracts/api-reference.md, architecture/mcp-server.md]
downstream: [contracts/api/record-replay.md, contracts/error-codes.md]
---

# MCP 工具逐接口契约（25 项 inputSchema）

`mcp_server._TOOLS`（`src/octop_browser/mcp_server.py:24`）是 25 个 `mcp.types.Tool` 的静态列表，`list_tools()` 原样返回（`:367`）；`call_tool(name, arguments)` 按名称分发（`:391`）。每个工具的 `inputSchema` 均为 `{"type": "object", "properties": {...}, "required": [...]}`；运行参数 `BROWSER_USE_*` 不进 schema，由客户端 `mcpServers.<name>.env` 注入（`src/octop_browser/mcp_server.py:28`）。

## 1. 公共协议与响应包络

| 维度 | 精确规则 | 源码锚点 |
|---|---|---|
| 工具声明 | `Tool(name, description, inputSchema)`，注册于 import 时 | `src/octop_browser/mcp_server.py:24` |
| 请求 | `{"name": str, "arguments": dict}` | `:391` |
| 成功响应 | `[TextContent(type="text", text=str(result.content))]` | `:476`、`:479` |
| 失败响应 | `[TextContent(type="text", text="ERROR: " + result.error)]` | `:477` |
| 未知工具 | `[TextContent(type="text", text=f"Unknown tool: {name}")]` | `:461` |
| 浏览器动作映射 | `_ACTION_MAP` 把 `browser_*` 名映射到 `_KNOWN_ACTIONS` 动作 | `:349` |
| 录制工具 | 直接调 `RecordController` / `RecordingStore` / `send_request`，不进 `_ACTION_MAP` | `:395` |

## 2. 浏览器动作工具（14 项）

| 工具名（`锚点`） | `properties` 精确键（类型 / 默认） | `required` | 映射动作 |
|---|---|---|---|
| `browser_navigate` (`:25`) | `url: string`、`profile: string="default"` | `["url"]` | `navigate` |
| `browser_dom_tree` (`:37`) | `level: string` 枚举 `minimal/interactive/full/structured`，默认 `interactive`；`profile` | 无 | `dom_tree` |
| `browser_screenshot` (`:52`) | `profile`、`element_ref: string`、`full_page: boolean=false`、`path: string` | 无 | `screenshot` |
| `browser_click` (`:76`) | `ref: string`、`selector: string`、`x: integer`、`y: integer`、`profile` | 无 | `click` |
| `browser_type` (`:90`) | `text: string`、`ref`、`selector`、`profile` | `["text"]` | `type` |
| `browser_eval_js` (`:104`) | `expression: string`、`profile` | `["expression"]` | `eval_js` |
| `browser_fill` (`:116`) | `text: string`、`ref`、`selector`、`profile` | `["text"]` | `fill` |
| `browser_press` (`:130`) | `key: string`、`profile` | `["key"]` | `press` |
| `browser_wait` (`:142`) | `url_contains`、`text`、`selector`、`timeout_ms: integer=10000`、`profile` | 无 | `wait` |
| `browser_new_tab` (`:241`) | `url: string`、`profile` | 无 | `new_tab` |
| `browser_switch_tab` (`:252`) | `tab_id: string`、`profile` | `["tab_id"]` | `switch_tab` |
| `browser_close_tab` (`:264`) | `tab_id: string`、`profile` | 无 | `close_tab` |
| `browser_list_tabs` (`:275`) | `profile` | 无 | `list_tabs` |
| `browser_close_session` (`:285`) | `profile`、`kill: boolean=false` | 无 | `close_session` |

`browser_screenshot` 的 `path` 描述明确「绝对路径原样使用，相对路径解析到 `BROWSER_USE_SCREENSHOTS_DIR`」（`:65`）；`browser_close_session` 的 `kill` 描述为「Also terminate the Chrome process.」（`:296`）。这 14 项经 `_ACTION_MAP.get(name)` 后走 `browser_tool(action=..., **arguments)`（`:475`），因此 `arguments` 中的未知键会直接触发 `TypeError` 并转成 `ERROR: Invalid parameters ...`。

## 3. 多标签工具（1 项）

| 工具名（`锚点`） | `properties` 精确键 | `required` | 分发特例 |
|---|---|---|---|
| `browser_open` (`:304`) | `urls: array<string>`、`profile`、`mode: string` 枚举 `auto/headed/headless`，默认 `auto` | `["urls"]` | `browser_tool(action="list_tabs", profile=..., urls=..., mode=...)`（`:464`） |

`call_tool` 对 `browser_open` 走独立分支：用 `urls` 首次建会话开多标签，再返回 `list_tabs` 摘要（`:462`），与 CLI `open` 的 `list_tabs` 改写（`src/octop_browser/cli.py:520`）语义一致。

## 4. 录制、回放与安装工具（10 项）

| 工具名（`锚点`） | `properties` 精确键 | `required` | 分发目标（`call_tool` 行号） |
|---|---|---|---|
| `browser_record_doctor` (`:156`) | `profile` | 无 | `RecordController().doctor(profile=...)` (`:395`) |
| `browser_record_start` (`:164`) | `profile`、`name`、`privacy: string="mask-sensitive"` | 无 | `ensure_daemon()` + `send_request({"command":"start", ...})` (`:400`) |
| `browser_record_stop` (`:176`) | `recording_id`、`name`、`generate_steps: boolean=true` | 无 | `send_request({"command":"stop", ...})` (`:415`) |
| `browser_record_status` (`:188`) | 空 `properties` | 无 | `send_request({"command":"status"})` (`:425`) |
| `browser_record_list` (`:193`) | 空 `properties` | 无 | `RecordingStore().list_recordings()` (`:428`) |
| `browser_record_show` (`:198`) | `recording_id: string` | `["recording_id"]` | `RecordingStore().recording_summary()` (`:437`) |
| `browser_record_generate_steps` (`:207`) | `recording_id: string` | `["recording_id"]` | `RecordController().generate_steps()` (`:443`) |
| `browser_record_generate_skill` (`:216`) | `recording_id: string`、`name` | `["recording_id"]` | `RecordController().generate_skill()` (`:446`) |
| `browser_replay_run` (`:228`) | `recording_id: string`、`profile`、`inputs: object` | `["recording_id"]` | `ReplayRunner().run(..., inputs=arguments.get("inputs") or {})` (`:451`) |
| `install_browser` (`:332`) | 空 `properties` | 无 | `_handle_install_browser()` → `install_chromium_stream()` (`:393`) |

`browser_record_start` 的请求字典只透传 `profile`/`name`/`privacy`（`:406`），守护进程侧再补 `screenshots` 默认值；`browser_record_stop` 传 `recording_id`/`name`/`generate_steps`（`:416`）。完整 daemon 请求字典见 [录制回放与守护命令](record-replay.md) 与 [录制守护 IPC](../../integrations/downstream/record-daemon-ipc.md)。

## 5. 共变耦合与修改清单（Agent Co-Change Playbook）

- **新增工具**：`_TOOLS`（`:24`）追加 `Tool(...)` → 浏览器动作还需 `_ACTION_MAP`（`:349`）与 `_KNOWN_ACTIONS`（`src/octop_browser/tool_interface.py:20`）→ `call_tool` 分支（`:391`）→ 本页对应分组表与 [入向接口契约全集](../api-reference.md) 总表。
- **修改 `inputSchema`**：`properties`/`required` 与 `call_tool` 里 `arguments.get(key, default)` 的取值键逐字一致；`browser_open` 的 `mode` 是唯一显式出现在工具 schema 里的运行模式参数（`:322`）。
- **修改响应包络**：`TextContent` 构造（`:479`）、`_handle_install_browser` 的 `OK/FAILED` 汇总（`:386`）与 [MCP 传输契约](../../integrations/downstream/mcp-transport.md) 联动。
- **回归**：`pytest tests/unit/test_mcp_server.py tests/unit/test_tool_interface.py`，命令见 [构建与单测映射](../../operations/dev-and-test.md)。
