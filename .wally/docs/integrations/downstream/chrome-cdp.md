---
kind: downstream-contract
scope: chrome-cdp
status: draft
origin: generated
source_paths: [src/octop_browser/cdp/client.py, src/octop_browser/actions/navigate.py, src/octop_browser/actions/js_eval.py, src/octop_browser/actions/capture.py, src/octop_browser/session.py]
symbols: [CDPClient, send, enable_domain, navigate, go_back, go_forward, reload, eval_js, screenshot, dom_tree, new_tab, list_tabs, switch_to_target]
upstream: [integrations/index.md, integrations/topology-and-mapping.md]
downstream: []
---

# 下游出向接口契约：Chrome DevTools Protocol（CDP）

Chrome/Chromium 是本仓**唯一**的浏览器执行下游：进程由 `subprocess` 拉起后，既通过 `aiohttp` 访问其 HTTP 发现端点，也通过 `websockets` 建立页面级 WebSocket 收发 CDP 帧。所有业务动作最终都编译为 `CDPClient.send(method, params)` 出向字典，返回统一包在 `{"id", "result"}` 或 `{"id", "error"}` 中。Chrome 服务端实现不在本仓，属外部黑盒（见 [认知边界](../../operations/boundary.md)）。

## 1. 封装定位与连接契约

| 契约项 | 精确值 / 规则 | 源码锚点 |
|---|---|---|
| 本仓传输底座 | `CDPClient`，出向帧 `{"id": msg_id, "method": method, "params": params or {}}` | `src/octop_browser/cdp/client.py:91` |
| 连接参数 | `websockets.connect(ws_url, max_size=_settings.cdp_max_message_size)`，默认上限 `33554432` | `src/octop_browser/cdp/client.py:67` |
| 页面 WS URL 来源 | `get_page_ws_url` 从 `/json` 的 `type=="page"` 目标中挑 `webSocketDebuggerUrl` | `src/octop_browser/cdp/launcher.py:618` |
| 直连旁路 | `cfg.cdp_ws_url` 非空时跳过 launcher，直接连给定 WebSocket | `src/octop_browser/session.py:55` |
| 域使能 | 连接后依次 `Page.enable`、`DOM.enable`、`Runtime.enable`；`Input` 域不使能 | `src/octop_browser/session.py:64` |
| 公共成功判定 | 响应无 `error` 键即成功；`result.get("result", {})` 为内层返回字典 | `src/octop_browser/cdp/client.py:113` |
| 命令超时 | `asyncio.wait_for(future, timeout=cfg.cdp_timeout)`，默认 `30.0s` | `src/octop_browser/cdp/client.py:99` |
| HTTP 探测主机 | 一律取 `cfg.cdp_host`，禁止硬编码 `localhost` | `src/octop_browser/cdp/launcher.py:369` |

## 2. 本仓上游调用方反查表

| 本仓封装入口 | 上游调用模块与函数 | 所属流程 | 调用点锚点 |
|---|---|---|---|
| `CDPClient.send` | `BrowserSession.dom_tree` / `wait` / `new_tab` / `list_tabs` | [动作分发](../../business/wf-action-dispatch.md) | `src/octop_browser/session.py:306`、`src/octop_browser/session.py:516` |
| `CDPClient.send` | `actions.navigate.navigate` / `go_back` / `go_forward` / `reload` | [会话生命周期](../../business/wf-browser-session-lifecycle.md) | `src/octop_browser/actions/navigate.py:37` |
| `CDPClient.send` | `actions.interact.click` / `type_text` / `fill_text` / `scroll` / `hover` / `select_value` | [ref 定位](../../business/wf-dom-ref-targeting.md) | `src/octop_browser/actions/interact.py:75` |
| `CDPClient.send` | `actions.capture.screenshot` | [动作分发](../../business/wf-action-dispatch.md) | `src/octop_browser/actions/capture.py:170` |
| `CDPClient.send` | `RecordSession._install_on_client` / `RecordController.start_in_process` | [录制采集](../../business/wf-record-capture.md) | `src/octop_browser/record/recorder.py:170` |
| `CDPClient.send` | `_InternalCDPSession.switch_to_target` / `_apply_viewport` | [标签管理](../../business/wf-tab-management.md) | `src/octop_browser/session.py:113` |

## 3. 封装方法总清单（全量 CDP 命令字）

| 序号 | `method` | 读写 | 组装位置 | 说明 |
|---|---|---|---|---|
| 1 | `Page.enable` / `DOM.enable` / `Runtime.enable` | 使能 | `src/octop_browser/cdp/client.py:124` | `enable_domain` 拼接 `"{domain}.enable"` |
| 2 | `Page.navigate` | 写 | `src/octop_browser/actions/navigate.py:37` | 导航并等 `Page.loadEventFired` |
| 3 | `Page.reload` | 写 | `src/octop_browser/actions/navigate.py:84` | 重载 |
| 4 | `Runtime.evaluate` | 读/写 | `src/octop_browser/actions/navigate.py:64`、`src/octop_browser/actions/js_eval.py:19` | 执行 JS，含 `history.back/forward` |
| 5 | `DOM.getDocument` | 读 | `src/octop_browser/session.py:306`、`src/octop_browser/actions/interact.py:48` | DOM 快照根节点 |
| 6 | `DOM.getBoxModel` | 读 | `src/octop_browser/actions/interact.py:23` | 元素中心坐标 |
| 7 | `DOM.querySelector` | 读 | `src/octop_browser/actions/interact.py:50` | CSS 选择器定位 |
| 8 | `DOM.resolveNode` | 读 | `src/octop_browser/actions/interact.py:239` | 取 `objectId` 供 `callFunctionOn` |
| 9 | `Input.dispatchMouseEvent` | 写 | `src/octop_browser/actions/interact.py:75` | 点击、悬停、滚轮 |
| 10 | `Input.dispatchKeyEvent` | 写 | `src/octop_browser/actions/interact.py:104` | 逐字符输入、按键、全选 |
| 11 | `Runtime.callFunctionOn` | 写 | `src/octop_browser/actions/interact.py:249` | `<select>` 赋值并派发事件 |
| 12 | `Page.getLayoutMetrics` | 读 | `src/octop_browser/actions/capture.py:154` | 整页 / 视口尺寸 |
| 13 | `Page.captureScreenshot` | 读 | `src/octop_browser/actions/capture.py:170` | 返回 base64 PNG |
| 14 | `Emulation.setDeviceMetricsOverride` | 写 | `src/octop_browser/session.py:86` | 固定视口 |
| 15 | `Target.createTarget` / `Target.activateTarget` / `Target.closeTarget` | 写 | `src/octop_browser/session.py:595`、`:114`、`:666` | 标签生命周期 |
| 16 | `Runtime.addBinding` / `Page.addScriptToEvaluateOnNewDocument` | 写 | `src/octop_browser/record/recorder.py:170`、`:172` | 录制脚本注入 |
| 17 | `Browser.close` | 写 | `src/octop_browser/cdp/launcher.py:471` | 优雅关闭（经 browser 级 WS） |

## 4. 逐方法请求字典与响应解包契约（Full Dict Schemas）

### 4.1 公共帧 `CDPClient.send(method, params)`（`src/octop_browser/cdp/client.py:75-116`）

#### A. 发往下游的组装字典表

```json
{"id": 7, "method": "Page.navigate", "params": {"url": "https://example.com"}}
```

| 字典键路径 | 类型 | 必填条件 | 默认值 / 固定值 | 值来源与转换逻辑 | 组装行号 |
|---|---|---|---|---|---|
| `id` | `int` | 必填 | 自增 `self._id` | 每条命令 `+= 1`，用作 Future 匹配键 | `:89` |
| `method` | `str` | 必填 | — | 调用方传入的 CDP 命令字，如 `"DOM.getDocument"` | `:91` |
| `params` | `dict` | 必填 | `{}` | `params or {}`，空参数一律序列化为空对象 | `:92` |

#### B. 返回字典与解包规则表

| 返回键路径 | 类型 | 提取、判空兜底与转换规则 | 解包行号 |
|---|---|---|---|
| `id` | `int` | `_recv_loop` 用 `msg["id"]` 弹 `_pending` 并 `set_result(msg)` | `:159` |
| `result` | `dict` | `inner = result.get("result", {})` 返回给调用方 | `:115` |
| `error` | `any` | 存在即抛 `CDPSessionError(f"CDP error for {method}: {result['error']}")` | `:113` |
| `method`（事件帧） | `str` | 无 `id` 时按 `_listeners[method]` 分发，注入 `__client` 键 | `:163` |

### 4.2 导航与页面控制

| 命令 | 出向 `params` 精确键 | 返回解包键 | 组装 / 解包行号 |
|---|---|---|---|
| `Page.navigate` | `{"url": str}` | `result["errorText"]`（非空即失败）、`result["frameId"]` | `src/octop_browser/actions/navigate.py:37`、`:38` |
| `Page.reload` | `{"ignoreCache": False}` | 无（仅判成功） | `src/octop_browser/actions/navigate.py:84` |
| `Runtime.evaluate`（历史） | `{"expression": "history.back()"}` / `"history.forward()"` | 无 | `src/octop_browser/actions/navigate.py:64`、`:74` |
| `Runtime.evaluate`（页面信息） | `{"expression": "JSON.stringify({url: location.href, title: document.title})", "returnByValue": True}` | `result["result"]["value"]` → `json.loads` → `url` / `title` | `src/octop_browser/session.py:308`、`:317` |
| `Runtime.evaluate`（`wait`） | `{"expression": expr, "returnByValue": True}`，`expr` 产出 `{url, text, selector}` | `result["result"]["value"]` → `data["url"]`、`data["text"]`、`data["selector"]` | `src/octop_browser/session.py:516`、`:519` |
| `Runtime.evaluate`（`eval_js`） | `{"expression": str, "returnByValue": True, "awaitPromise": True}` | `result["result"]["subtype"]` 为 `error` 时取 `description`；否则取 `value` | `src/octop_browser/actions/js_eval.py:19`、`:27` |

### 4.3 DOM 与 ref 定位

| 命令 | 出向 `params` 精确键 | 返回解包键 | 组装 / 解包行号 |
|---|---|---|---|
| `DOM.getDocument`（快照） | `{"depth": -1}` | `result["root"]` 整棵节点树 | `src/octop_browser/session.py:306`、`:307` |
| `DOM.getDocument`（选择器根） | `{"depth": 0}` | `result["root"]["nodeId"]` | `src/octop_browser/actions/interact.py:48`、`:49` |
| `DOM.getBoxModel` | `{"nodeId": int}` | `result["model"]["content"]`（8 个浮点，取 `[0]+[4]` 与 `[1]+[5]` 求中心） | `src/octop_browser/actions/interact.py:23`、`:25` |
| `DOM.querySelector` | `{"nodeId": root_id, "selector": str}` | `result.get("nodeId", 0)`，为 0 判未命中 | `src/octop_browser/actions/interact.py:50`、`:53` |
| `DOM.resolveNode` | `{"nodeId": node_id}` | `result["object"]["objectId"]` | `src/octop_browser/actions/interact.py:239`、`:240` |
| `Runtime.callFunctionOn` | `{"objectId": str, "functionDeclaration": str, "arguments": [{"value": value}], "returnByValue": True}` | `result["result"]["value"]` | `src/octop_browser/actions/interact.py:249`、`:255` |

### 4.4 输入事件

| 命令 | 出向 `params` 精确键 | 组装行号 |
|---|---|---|
| `Input.dispatchMouseEvent`（点击） | `{"type": "mousePressed"\|"mouseReleased", "x": cx, "y": cy, "button": "left", "clickCount": 1}`，循环两次 | `src/octop_browser/actions/interact.py:74`、`:75` |
| `Input.dispatchMouseEvent`（悬停） | `{"type": "mouseMoved", "x": cx, "y": cy}` | `src/octop_browser/actions/interact.py:152` |
| `Input.dispatchMouseEvent`（滚轮） | `{"type": "mouseWheel", "x": 400, "y": 300, "deltaX": int, "deltaY": int}` | `src/octop_browser/actions/interact.py:124` |
| `Input.dispatchKeyEvent`（字符） | `{"type": "char", "text": char}`，逐字符发送 | `src/octop_browser/actions/interact.py:104` |
| `Input.dispatchKeyEvent`（全选） | `{"type": "keyDown"\|"keyUp", "key": "a", "code": "KeyA", "modifiers": 2\|4}`，Ctrl 与 Meta 各一轮 | `src/octop_browser/actions/interact.py:180`、`:181` |
| `Input.dispatchKeyEvent`（按键） | `{"type": "keyDown"\|"keyUp", "key": key, "code": code}` | `src/octop_browser/actions/interact.py:215`、`:218` |

### 4.5 截图、视口与标签

| 命令 | 出向 `params` 精确键 | 返回解包键 | 组装 / 解包行号 |
|---|---|---|---|
| `Emulation.setDeviceMetricsOverride` | `{"width": int, "height": int, "deviceScaleFactor": 1, "mobile": False}`，宽高经 `max(int(...), 1)` | 无（失败仅 debug 日志） | `src/octop_browser/session.py:86` |
| `Page.captureScreenshot` | `{"format": "png"}`；可选 `{"clip": {"x","y","width","height","scale":1}}` 与 `{"captureBeyondViewport": True}` | `result["data"]` base64 字符串，空即失败 | `src/octop_browser/actions/capture.py:125`、`:143`、`:161`、`:170` |
| `Page.getLayoutMetrics` | `{}` | `result["cssContentSize"]` 或 `contentSize` 的 `width`/`height`；视口取 `cssVisualViewport` 或 `visualViewport` 的 `clientWidth`/`width` | `src/octop_browser/actions/capture.py:154`、`:194`、`:200` |
| `Target.createTarget` | `{"url": create_url}` | `result.get("targetId", "")` | `src/octop_browser/session.py:594`、`:597` |
| `Target.activateTarget` | `{"targetId": target_id}` | 无 | `src/octop_browser/session.py:113` |
| `Target.closeTarget` | `{"targetId": tab_id}` | 无 | `src/octop_browser/session.py:666`、`:774` |

### 4.6 录制注入与 HTTP 发现端点

`Runtime.addBinding` 出向 `{"name": binding_name}`（`src/octop_browser/record/recorder.py:170`）；`Page.addScriptToEvaluateOnNewDocument` 出向 `{"source": config + recorder.js}`（`:172`）；`Runtime.bindingCalled` 事件回传 `{"name", "payload", "__client"}`（`:256`）。HTTP 端点字典如下：

| 端点 | 方法与 URL | 返回解包键 | 源码锚点 |
|---|---|---|---|
| 版本探测 | `GET http://{cdp_host}:{port}/json/version` | `data["webSocketDebuggerUrl"]` | `src/octop_browser/cdp/launcher.py:369`、`:387` |
| 目标列表 | `GET http://{cdp_host}:{port}/json` | 数组元素 `id`、`type`、`url`、`title`、`webSocketDebuggerUrl` | `src/octop_browser/cdp/launcher.py:677`、`:682`；`src/octop_browser/session.py:808` |
| 新建空白页 | `PUT` 优先、`GET` 回退 `http://{cdp_host}:{port}/json/new?about:blank` | `payload["type"] == "page"` 才采纳 | `src/octop_browser/cdp/launcher.py:695`、`:710` |
| 优雅关闭 | browser 级 WS `ws.send_json({"id": 1, "method": "Browser.close"})` | 无（靠端口探测确认退出） | `src/octop_browser/cdp/launcher.py:471` |

### 4.7 下游错误拦截与翻译

| 下游错误条件 | 本仓转换后的异常 / 兜底 | 代码行号 |
|---|---|---|
| 响应含 `error` 键 | `CDPSessionError(f"CDP error for {method}: ...")` | `src/octop_browser/cdp/client.py:113` |
| `wait_for` 超时 | `CDPSessionError(f"Timeout waiting for response to {method}")` | `src/octop_browser/cdp/client.py:100` |
| WebSocket 接收循环异常 | 全部 pending Future 置 `CDPSessionError("Connection lost: ...")`，`browser_tool` 据此重连一次 | `src/octop_browser/cdp/client.py:172`、`src/octop_browser/tool_interface.py:186` |
| `Page.navigate` 返回 `errorText` | `ToolResult(success=False, error="Navigation failed for {url}: {errorText}")` | `src/octop_browser/actions/navigate.py:39` |
| ref 未命中 `nodeId` | `CDPSessionError("Ref '...' not found. Call dom_tree() first.")` | `src/octop_browser/actions/interact.py:44` |
| `Page.captureScreenshot` 空 `data` | `ToolResult(success=False, error="Page.captureScreenshot returned empty data")` | `src/octop_browser/actions/capture.py:171` |

## 5. 共变耦合与修改清单（Agent Co-Change Playbook）

- **新增 CDP 命令**：先在本页第 3 节登记命令字，再按 4.x 模板补全 `params` 每个键与返回解包键，禁止只写「类似 `Runtime.evaluate`」；组装点集中在 `client.send`（`src/octop_browser/cdp/client.py:75`）。
- **修改返回解包**：任何 `result["..."]` 改动都需核对 `CDPClient.send` 的 `inner = result.get("result", {})`（`src/octop_browser/cdp/client.py:115`）是否仍能取到内层字典，并同步 [参数组装映射](../topology-and-mapping.md)。
- **特殊协议陷阱**：CDP 的 `params` 键为驼峰（`returnByValue`、`deviceScaleFactor`、`captureBeyondViewport`、`nodeId`、`targetId`）；`Input` 域无 `enable`；`Browser.close` 只能发到 browser 级 WS，页面级 WS 不认。
- **回归**：`pytest tests/unit/test_navigate_actions.py tests/unit/test_capture.py tests/unit/test_launcher.py`，命令见 [构建与单测映射](../../operations/dev-and-test.md)。
