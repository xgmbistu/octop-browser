---
kind: api-contract
scope: mcp-tools
status: draft
origin: generated
source_paths: [src/octop_browser/mcp_server.py, src/octop_browser/tool_interface.py, src/octop_browser/record/daemon.py, src/octop_browser/install.py]
symbols: [_TOOLS, _ACTION_MAP, list_tools, call_tool, send_request, install_chromium_stream]
upstream: [../api-reference.md]
downstream: [../../integrations/topology-and-mapping.md, ../../contracts/error-codes.md]
---

# MCP Tools 逐接口 Schema

MCP 服务端名为 `octop-browser`（`src/octop_browser/mcp_server.py:22`），共注册 25 个 Tool。全部 Tool 经 `call_tool()` 分发，浏览器动作最终走 `_ACTION_MAP` → `browser_tool()`；录制/回放/安装按名称显式分支。

## 1. 传输与调用约定

| 维度 | 规则 | 锚点 |
|---|---|---|
| 默认传输 | stdio：`stdio_server()` → `app.run(read_stream, write_stream, ...)` | `src/octop_browser/mcp_server.py:526-530` |
| 可选 SSE | `MCP_PORT` 设置后启用，`MCP_HOST` 默认 `0.0.0.0`；路由 `/sse`、`/messages/` | `src/octop_browser/mcp_server.py:491-525` |
| 工具列表 | `@app.list_tools()` 返回 `_TOOLS` 常量列表 | `src/octop_browser/mcp_server.py:367-369` |
| 调用入口 | `@app.call_tool()` 签名 `(name, arguments)`，返回 `list[TextContent]` | `src/octop_browser/mcp_server.py:391-479` |
| 动作映射 | `_ACTION_MAP` 含 14 项，未命中且非特殊工具返回 `Unknown tool: <name>` | `src/octop_browser/mcp_server.py:349-364,459-461` |
| 失败回显 | `ToolResult.success=False` → `ERROR: <error>` | `src/octop_browser/mcp_server.py:476-479` |

## 2. 浏览器动作 Tool 全量 Schema（14 项）

| Tool 名 | `inputSchema.properties` 键 | 必填（`required`） | 默认值 | 分发 action | 定义锚点 |
|---|---|---|---|---|---|
| `browser_navigate` | `url: string`, `profile: string` | `url` | profile=`default` | `navigate` | `src/octop_browser/mcp_server.py:25-36` |
| `browser_dom_tree` | `level: string`（四档枚举）, `profile: string` | 无 | level=`interactive` | `dom_tree` | `src/octop_browser/mcp_server.py:37-51` |
| `browser_screenshot` | `profile`, `element_ref: string`, `full_page: boolean`, `path: string` | 无 | full_page=`false` | `screenshot` | `src/octop_browser/mcp_server.py:52-75` |
| `browser_click` | `ref`, `selector: string`, `x`, `y: integer`, `profile` | 无（运行时三选一校验） | profile=`default` | `click` | `src/octop_browser/mcp_server.py:76-89` |
| `browser_type` | `text`, `ref`, `selector`, `profile`（均 string） | `text` | profile=`default` | `type` | `src/octop_browser/mcp_server.py:90-103` |
| `browser_eval_js` | `expression: string`, `profile: string` | `expression` | profile=`default` | `eval_js` | `src/octop_browser/mcp_server.py:104-115` |
| `browser_fill` | `text`, `ref`, `selector`, `profile`（均 string） | `text` | profile=`default` | `fill` | `src/octop_browser/mcp_server.py:116-129` |
| `browser_press` | `key: string`, `profile: string` | `key` | profile=`default` | `press` | `src/octop_browser/mcp_server.py:130-141` |
| `browser_wait` | `url_contains`, `text`, `selector`（string）, `timeout_ms: integer`, `profile` | 无（至少一条件才生效） | timeout_ms=`10000` | `wait` | `src/octop_browser/mcp_server.py:142-155` |
| `browser_new_tab` | `url: string`, `profile: string` | 无 | profile=`default` | `new_tab` | `src/octop_browser/mcp_server.py:241-251` |
| `browser_switch_tab` | `tab_id: string`, `profile: string` | `tab_id` | profile=`default` | `switch_tab` | `src/octop_browser/mcp_server.py:252-263` |
| `browser_close_tab` | `tab_id: string`, `profile: string` | 无 | profile=`default` | `close_tab` | `src/octop_browser/mcp_server.py:264-274` |
| `browser_list_tabs` | `profile: string` | 无 | profile=`default` | `list_tabs` | `src/octop_browser/mcp_server.py:275-284` |
| `browser_close_session` | `profile: string`, `kill: boolean` | 无 | kill=`false` | `close_session` | `src/octop_browser/mcp_server.py:285-303` |

`browser_close_session` 的 `kill=true` 会终止 Chrome 并释放端口，默认只断开 CDP（`src/octop_browser/tool_interface.py:125-161`）。

## 3. 多标签与录制 Tool 全量 Schema（8 项）

| Tool 名 | `inputSchema.properties` 键 | 必填 | 默认值 | 服务端处理 | 定义锚点 |
|---|---|---|---|---|---|
| `browser_open` | `urls: array[string]`, `profile`, `mode`（auto/headed/headless） | `urls` | profile=`default`, mode=`auto` | 特例：以 `list_tabs` + `urls` 调 `browser_tool` | `src/octop_browser/mcp_server.py:304-331,462-473` |
| `browser_record_doctor` | `profile: string` | 无 | profile=`default` | `RecordController.doctor()` | `src/octop_browser/mcp_server.py:156-163,395-399` |
| `browser_record_start` | `profile`, `name: string`, `privacy: string` | 无 | profile=`default`, privacy=`mask-sensitive` | `ensure_daemon()` → `send_request({"command":"start",...})` | `src/octop_browser/mcp_server.py:164-175,400-414` |
| `browser_record_stop` | `recording_id`, `name: string`, `generate_steps: boolean` | 无 | generate_steps=`true` | `send_request({"command":"stop",...})` | `src/octop_browser/mcp_server.py:176-187,415-424` |
| `browser_record_status` | 空对象 | 无 | — | `send_request({"command":"status"})` | `src/octop_browser/mcp_server.py:188-192,425-427` |
| `browser_record_list` | 空对象 | 无 | — | `RecordingStore().list_recordings()` | `src/octop_browser/mcp_server.py:193-197,428-436` |
| `browser_record_show` | `recording_id: string` | `recording_id` | — | `RecordingStore().recording_summary()` | `src/octop_browser/mcp_server.py:198-206,437-442` |
| `browser_record_generate_steps` | `recording_id: string` | `recording_id` | — | `RecordController.generate_steps()` | `src/octop_browser/mcp_server.py:207-215,443-445` |
| `browser_record_generate_skill` | `recording_id`, `name: string` | `recording_id` | — | `RecordController.generate_skill()` | `src/octop_browser/mcp_server.py:216-227,446-450` |

daemon 不可达时 `send_request()` 返回 `{"ok": false, "error": "Record daemon is not running. ..."}`（`src/octop_browser/record/daemon.py:148-159`），MCP 侧把整个字典 `str()` 后作为文本返回。

## 4. 回放与安装 Tool Schema（2 项）

| Tool 名 | `inputSchema.properties` 键 | 必填 | 默认值 | 服务端处理 | 定义锚点 |
|---|---|---|---|---|---|
| `browser_replay_run` | `recording_id: string`, `profile: string`, `inputs: object` | `recording_id` | profile=`default`, inputs=`{}` | `ReplayRunner().run()` | `src/octop_browser/mcp_server.py:228-240,451-457` |
| `install_browser` | 空对象 | 无 | — | `install_chromium_stream()` 聚合日志，终态 `OK` / `FAILED: <error>` | `src/octop_browser/mcp_server.py:332-346,372-388`、`src/octop_browser/install.py:486-620` |

## 5. 参数映射与共变清单

- **MCP 参数 → action kwargs**：`call_tool()` 直接把 `arguments` 传给 `browser_tool(action, **arguments)`（`src/octop_browser/mcp_server.py:475`）；`profile` 混入 kwargs 后由 `browser_tool` 显式读取。
- **无 per-tool 环境变量字段**：`BROWSER_USE_*` 通过客户端配置的 `mcpServers.<name>.env` 注入，不写进 `inputSchema`。
- **新增 Tool 改动链**：`_TOOLS` 追加 `Tool(...)` → 若是浏览器动作则加 `_ACTION_MAP` 条目，否则在 `call_tool()` 加分支 → 同步 [`../../contracts/api-reference.md`](../api-reference.md) → 跑 `tests/unit/test_mcp_server.py`。
- **修改 Schema 默认值**：CLI 侧默认值在 `src/octop_browser/cli.py:96-404`，两侧必须保持一致，否则同一动作经不同入口行为不同。

## 6. 关联文档

- [入向接口全集](../api-reference.md) · [CLI 命令 Schema](cli-commands.md) · [API 与 MCP 分发组件](../../architecture/api-and-mcp.md)
