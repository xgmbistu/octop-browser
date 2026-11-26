---
kind: mapping
scope: inbound-to-outbound-mapping
status: draft
origin: generated
source_paths: [src/octop_browser/cli.py, src/octop_browser/mcp_server.py, src/octop_browser/tool_interface.py, src/octop_browser/record/daemon.py, src/octop_browser/session.py, src/octop_browser/actions/interact.py, src/octop_browser/actions/capture.py, src/octop_browser/cdp/client.py]
symbols: [_action_kwargs, call_tool, browser_tool, dispatch, _resolve_coords, screenshot, send, dom_tree]
upstream: [contracts/api-reference.md, integrations/index.md]
downstream: [integrations/downstream/chrome-cdp.md, integrations/downstream/record-daemon-ipc.md, integrations/downstream/mcp-transport.md]
---

# 上下游参数组装与字段映射矩阵

专为「上游加字段透传/转换给下游、或下游返回字段回填给上游」需求设计，精确追踪字段在 CLI/MCP 入参、`browser_tool` 关键字参数、CDP 请求 `params` 字典与 `ToolResult` 之间的变形规则。所有字典 Key 均可在标注行号回读，禁止臆造字段名。

## 1. 上游入口 → 下游扇出编排顺序表（Fan-Out Sequence）

| 上游入口（Action / 路由 / 命令） | 主编排函数（`路径:行号`） | 按序调用的下游封装方法链 | 短路 / 聚合规则 |
|---|---|---|---|
| 任意浏览器动作（CLI/MCP/Python/回放） | `browser_tool` (`src/octop_browser/tool_interface.py:91`) | `1. _get_or_create_session` (`:164`) → `2. getattr(sess, action)` (`:180`) → `3. CDPClient.send` (`src/octop_browser/cdp/client.py:75`) | 未知动作 / 参数错 / 断线重连失败即短路，返回 `_error_result` |
| `click --ref btn_2` | `BrowserSession.click` (`src/octop_browser/session.py:377`) | `1. RefCache.lookup` (`src/octop_browser/actions/interact.py:42`) → `2. DOM.getBoxModel` (`:23`) → `3. Input.dispatchMouseEvent` ×2 (`:74`) | ref 缺失立即抛 `CDPSessionError`，不派发输入 |
| `screenshot --full-page` | `actions.capture.screenshot` (`src/octop_browser/actions/capture.py:87`) | `1. Page.getLayoutMetrics` (`:154`) → `2. Page.captureScreenshot` (`:170`) → `3. base64 解码写盘` (`:185`) | `data` 为空直接返回失败 `ToolResult` |
| `record start`（守护模式） | `cli._run_record` (`src/octop_browser/cli.py:557`) | `1. ensure_daemon` (`:573`) → `2. send_request({"command":"start", ...})` (`:577`) → `3. RecordDaemon.dispatch` (`src/octop_browser/record/daemon.py:43`) → `4. RecordController.start_in_process` (`src/octop_browser/record/recorder.py:350`) | daemon 未就绪返回 `ok=False`，不进入采集 |
| `replay run <id>` | `ReplayRunner.run` (`src/octop_browser/record/replay.py:25`) | `1. read_steps` (`:31`) → `2. browser_tool("dom_tree", level="structured")` (`:112`) → `3. match_target` (`:117`) → `4. browser_tool("click"/"fill"/...)` (`:120`) | 任一步 `failed` 采快照并 break |
| `install_browser` | `_handle_install_browser` (`src/octop_browser/mcp_server.py:372`) | `1. install_chromium_stream()` (`:377`) → `2. 聚合 InstallEvent` (`:378`) → `3. 拼 OK/FAILED` (`:386`) | 终态 `done` 事件决定输出 |

## 2. 核心场景入向 → 出向字段级映射矩阵（Field-Level Mapping）

### 场景 A：浏览器动作入参 → CDP 请求字典键

#### A.1 上游入参字段 → 下游请求字典键

| 上游入参字段路径（类型） | 转换 / 校验 / 默认值注入逻辑 | 目标下游与封装方法 | 下游请求字典精确 Key 路径（类型） | 组装源码锚点 |
|---|---|---|---|---|
| `action` (`str`) | 命中 `_KNOWN_ACTIONS` 后 `getattr(sess, action)` | `BrowserSession.<action>` | 决定 `method` 命令字 | `src/octop_browser/tool_interface.py:180` |
| `url` (`str`) | 直接透传，无校验 | `Page.navigate` | `params["url"]` (`str`) | `src/octop_browser/actions/navigate.py:37` |
| `ref` (`str`) | `RefCache.lookup` → `nodeId` → `DOM.getBoxModel` → 中心坐标 | `Input.dispatchMouseEvent` | `params["x"]`、`params["y"]` (`float`)、`params["type"]`、`params["button"]="left"`、`params["clickCount"]=1` | `src/octop_browser/actions/interact.py:41`、`:75` |
| `selector` (`str`) | `DOM.getDocument {"depth":0}` + `DOM.querySelector` | `Input.dispatchMouseEvent` | `params["selector"]`（中间命令）、`params["x"]`/`params["y"]` | `:48`、`:50` |
| `x` / `y` (`int`) | `float(x)`、`float(y)` | `Input.dispatchMouseEvent` | `params["x"]`、`params["y"]` | `:58` |
| `text` (`str`) | 逐字符 `for char in text` | `Input.dispatchKeyEvent` | `params["type"]="char"`、`params["text"]=char` | `:104` |
| `key` (`str`) | `code` 映射表（`Enter/Tab/Escape/Backspace`，`:209`） | `Input.dispatchKeyEvent` | `params["type"]="keyDown"/"keyUp"`、`params["key"]`、`params["code"]` | `:215` |
| `level` (`str`) | 四档枚举，默认 `interactive` | `DOM.getDocument` + `Runtime.evaluate` | `params["depth"]=-1`、`params["expression"]`、`params["returnByValue"]=True` | `src/octop_browser/session.py:306`、`:308` |
| `full_page=True` | `Page.getLayoutMetrics` 取 `cssContentSize` | `Page.captureScreenshot` | `params["format"]="png"`、`params["clip"]={x,y,width,height,scale}`、`params["captureBeyondViewport"]=True` | `src/octop_browser/actions/capture.py:125`、`:143`、`:168` |
| `element_ref` (`str`) | `DOM.getBoxModel` 取 content 四边形 | `Page.captureScreenshot` | `params["clip"]`（由 bbox 计算） | `:130`、`:143` |
| `profile` (`str`) | 只作 `_registry` 键，**不进 CDP 字典** | `_get_or_create_session` | 无（隐式上下文） | `src/octop_browser/tool_interface.py:57` |
| `mode` (`BrowserMode`) | 仅首次建会话生效，解析为 headless | `_build_flags` | `--headless=new` argv 项（非 CDP 字典） | `src/octop_browser/cdp/launcher.py:221` |
| `viewport_width/height` (`int`) | `max(int(...), 1)` | `Emulation.setDeviceMetricsOverride` | `params["width"]`、`params["height"]`、`params["deviceScaleFactor"]=1`、`params["mobile"]=False` | `src/octop_browser/session.py:86` |

#### A.2 下游返回字典 → 本仓对象 / 上游出参回填

| 下游返回键路径（类型） | 判空 / 兜底 / 格式转换逻辑 | 回填目标字段路径（类型） | 解包源码锚点 |
|---|---|---|---|
| `result["root"]` (`dict`) | `doc["root"]` 直接取 | `DOMBuilder(dom=root, ...)` | `src/octop_browser/session.py:307` |
| `result["result"]["value"]` (`str`) | `json.loads(info.get("result", {}).get("value", "{}"))` | `ToolResult.content` 的 url/title | `:317` |
| `result["model"]["content"]` (`list[float]`) | `(content[0]+content[4])/2`、`(content[1]+content[5])/2`，缺省 `[0]*8` | 点击坐标 `cx/cy` | `src/octop_browser/actions/interact.py:25`、`:27` |
| `result["data"]` (`str` base64) | 空串判失败；否则 `base64.b64decode` 写盘 | `ToolResult.content` = PNG 路径；`metadata.path/size_kb/url/title/width/height/full_page/element_ref` | `src/octop_browser/actions/capture.py:171`、`:185`、`:206` |
| `result["targetId"]` (`str`) | `cdp_result.get("targetId", "")` | `ToolResult.content` 与 `metadata.target_id` | `src/octop_browser/session.py:597`、`:611` |
| `result["errorText"]` (`str`) | 非空即转失败 `ToolResult` | `ToolResult.error` | `src/octop_browser/actions/navigate.py:38`、`:43` |
| `result["result"]["value"]`（`eval_js`） | `subtype=="error"` 取 `description`；否则 dict 原样 / list 与标量 `json.dumps` | `ToolResult.content` | `src/octop_browser/actions/js_eval.py:27`、`:41` |
| `GET /json` 元素的 `id/url/title/webSocketDebuggerUrl` | 过滤 `type=="page"`，取 `t.get(key, "")` | `TabInfo.tab_id/url/title/active` 与 `metadata.tabs` | `src/octop_browser/session.py:820`、`:846` |

### 场景 B：录制与回放请求字典映射

| 上游入参 | 转换逻辑 | 目标下游请求字典键 | 组装锚点 |
|---|---|---|---|
| CLI `record start --privacy mask-sensitive` | `args.privacy` 原样透传 | `{"command":"start","profile":...,"name":...,"privacy":...,"screenshots":"off"}` | `src/octop_browser/cli.py:577` |
| MCP `browser_record_start` 的 `arguments` | `.get("profile","default")`/`.get("name")`/`.get("privacy","mask-sensitive")` | 同上（无 `screenshots` 键，服务端补默认） | `src/octop_browser/mcp_server.py:406` |
| CLI `record stop --recording-id <id>` | `generate_steps = not args.no_generate_steps` | `{"command":"stop","recording_id":...,"generate_steps":bool,"name":...}` | `src/octop_browser/cli.py:549` |
| CLI `replay run --input k=v` | 仅含 `=` 的项 `split("=", 1)` 并入 `inputs` | `ReplayRunner.run(..., inputs=inputs)` → `_resolve_value` 的 `{{k}}` 替换 | `src/octop_browser/cli.py:612`、`src/octop_browser/record/replay.py:566` |
| 回放 `SemanticStep.value` | `{{...}}` 包裹时查 `inputs`，缺失填空串 | `browser_tool("fill", text=...)` / `("select", value=...)` | `:566`、`:122` |
| 录制事件 `event` | 包 `{seq, recordingId, receivedAt, ...event}` 后 `redact_event` | `events.jsonl` 单行字典 | `src/octop_browser/record/recorder.py:242`、`:248` |

### 场景 C：CDP 公共帧与结果包络

`CDPClient.send` 固定把 `(method, params)` 编译为 `{"id": msg_id, "method": method, "params": params or {}}`（`src/octop_browser/cdp/client.py:91`），`_recv_loop` 按 `msg["id"]` 匹配 Future（`:159`），任何含 `error` 的响应转 `CDPSessionError`（`:113`），成功返回 `result.get("result", {})`（`:115`）。上层 `browser_tool` 再统一包成 `ToolResult`（`:152`、`:181`）。

## 3. 通用字典拼装模式与共变修改清单（Co-Change Checklist）

- **公共信封构造器**：`CDPClient.send`（`src/octop_browser/cdp/client.py:75`）—— 固定骨架 `{"id": int, "method": str, "params": dict}`。
- **公共返回构造器**：`ToolResult`（`src/octop_browser/models.py:20`）—— `success/content/error/metrics/metadata` 五键。
- **守护请求构造器**：`send_request`（`src/octop_browser/record/daemon.py:140`）—— `{"command": str, ...}` 单行 JSON。
- **新增透传字段标准改动链**：
  1. 入向 Schema 新增字段与校验：CLI `sub.add_parser` (`src/octop_browser/cli.py:96`) 与 MCP `inputSchema` (`src/octop_browser/mcp_server.py:28`)。
  2. 中间转换函数提取并映射键名：`_action_kwargs` (`src/octop_browser/cli.py:426`) 与 `call_tool` (`src/octop_browser/mcp_server.py:391`)。
  3. 下游封装方法写入请求 `dict`：`browser_tool` (`src/octop_browser/tool_interface.py:91`) → `BrowserSession` 方法 → `client.send` 的 `params`。
  4. 如需回显，更新 `ToolResult` / `metadata` 序列化（`src/octop_browser/session.py:846`）。
  5. 更新下游 Mock 夹具并跑 `pytest tests/unit/test_cli.py tests/unit/test_mcp_server.py tests/unit/test_tool_interface.py`。

## 4. 共变耦合与修改清单（Agent Co-Change Playbook）

- **改 CLI/MCP 入参键**：`_action_kwargs`（`src/octop_browser/cli.py:426`）、MCP `inputSchema.properties`（`src/octop_browser/mcp_server.py:28`）与 `getattr(sess, action)(**kwargs)` 的方法签名（`src/octop_browser/tool_interface.py:180`）三处必须逐字一致。
- **改 CDP `params` 键**：各 `actions/` 组装点、`CDPClient.send` 的 `params or {}`（`:92`）与 [Chrome CDP 契约](downstream/chrome-cdp.md) 第 4 节字典表同步；键名大小写为驼峰，禁止臆造 snake_case。
- **改返回解包键**：`ToolResult` 字段、`_format_result` 的 `model_dump`（`src/octop_browser/cli.py:505`）、MCP `call_tool` 的 `str(result.content)`（`src/octop_browser/mcp_server.py:476`）与 [领域模型](../business/domain-models/tool-result-and-metrics.md) 联动。
- **改守护请求键**：CLI 组装（`src/octop_browser/cli.py:549`、`:577`）、MCP 组装（`src/octop_browser/mcp_server.py:406`、`:416`）与 `dispatch` 的 `request.get`（`src/octop_browser/record/daemon.py:50`）联动，见 [录制守护 IPC](downstream/record-daemon-ipc.md)。
