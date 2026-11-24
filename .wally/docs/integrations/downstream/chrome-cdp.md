---
kind: downstream-contract
scope: chrome-devtools-protocol
status: draft
origin: generated
source_paths: [src/octop_browser/cdp/client.py, src/octop_browser/cdp/launcher.py, src/octop_browser/session.py, src/octop_browser/actions/navigate.py, src/octop_browser/actions/interact.py, src/octop_browser/actions/capture.py, src/octop_browser/actions/js_eval.py, src/octop_browser/dom/builder.py]
symbols: [CDPClient.send, CDPClient.connect, launch_or_attach, get_page_ws_url, _InternalCDPSession.connect, navigate, click, screenshot, eval_js, DOMBuilder.build]
upstream: [../index.md, ../topology-and-mapping.md]
downstream: []
---

# 下游出向接口契约：`chrome-cdp`

Chrome DevTools Protocol 是本仓唯一的运行时业务下游：通过 WebSocket 发送 JSON-RPC 帧并解包 `result` 内层。业务字典不在 `CDPClient` 一处，而分散在 `actions/*`、`session.py`、`dom/builder.py` 的业务封装中，本节逐层展开。

## 1. 封装定位与连接契约

| 契约项 | 精确值 / 规则 | 源码锚点 |
|---|---|---|
| 传输底座 | `CDPClient`，基于 `websockets.asyncio.client.ClientConnection` | `src/octop_browser/cdp/client.py:11-12,30-54` |
| 业务封装文件 | `actions/navigate.py`、`actions/interact.py`、`actions/capture.py`、`actions/js_eval.py`、`session.py`、`dom/builder.py` | `src/octop_browser/session.py:13-18` |
| 直连开关 | `cfg.cdp_ws_url` 非空时跳过 launcher 直接连该 WebSocket | `src/octop_browser/session.py:55-63` |
| 启动与页面发现 | `launch_or_attach()` → `get_page_ws_url()`；HTTP 探测 `{cdp_host}:{port}/json/version` 与 `/json` | `src/octop_browser/cdp/launcher.py:497-615,618-671` |
| 连接后 domain | 依次 `Page.enable`、`DOM.enable`、`Runtime.enable`；`Input` 无 enable 方法，直接 dispatch | `src/octop_browser/session.py:63-68` |
| 帧大小上限 | `max_size=cfg.cdp_max_message_size`，默认 33554432（32 MiB），0 表示禁用 | `src/octop_browser/cdp/client.py:67-70` |
| 公共成功判定 | 响应无 `error` 键，返回 `result["result"]` 内层字典 | `src/octop_browser/cdp/client.py:113-116` |

## 2. 本仓上游调用方反查表

| 本仓封装方法 | 上游调用模块与函数 | 所属业务流 / 接口 | 调用点锚点 |
|---|---|---|---|
| `_InternalCDPSession.connect` | `BrowserSession.create` | [`WF-01`](../../business/wf-browser-action.md) | `src/octop_browser/session.py:236-237` |
| `navigate` | `BrowserSession.navigate`、`new_tab`、`_navigate_existing_tab` | WF-01 / 回放 open | `src/octop_browser/session.py:266-268,651-656` |
| `click` / `type_text` / `fill_text` / `select_value` | `BrowserSession.click/type/fill/select` | WF-01 / 回放 click/fill | `src/octop_browser/session.py:385-460` |
| `screenshot` | `BrowserSession.screenshot`、`ReplayRunner._capture_failure_artifacts` | WF-01 / 回放失败留证 | `src/octop_browser/session.py:361-369`、`src/octop_browser/record/replay.py:454-460` |
| `eval_js` | `BrowserSession.eval_js`、`wait`、`list_tabs` 辅助 | WF-01 / 验证 | `src/octop_browser/session.py:487`、`src/octop_browser/record/replay.py:362-369` |
| `DOMBuilder.build` | `BrowserSession.dom_tree` | WF-01 / 目标重匹配 | `src/octop_browser/session.py:320-326` |

## 3. 封装方法总清单

| 序号 | CDP 命令字 | 发起封装 | CDP 域 | 读写类型 | 幂等/重试 | 定义锚点 |
|---|---|---|---|---|---|---|
| 1 | `Page.navigate` | `navigate` | Page | 写 | 等待 load 事件最多 5 秒 | `src/octop_browser/actions/navigate.py:25-57` |
| 2 | `Page.reload` / `Runtime.evaluate(history.back/forward)` | `reload`, `go_back`, `go_forward` | Page/Runtime | 写 | 先清 ref | `src/octop_browser/actions/navigate.py:60-87` |
| 3 | `DOM.getDocument` | `dom_tree`, `interact._resolve_coords` | DOM | 读 | 每次重建 | `src/octop_browser/session.py:306`、`src/octop_browser/actions/interact.py:48-52` |
| 4 | `DOM.getBoxModel` | `interact._get_center`, `capture.screenshot` | DOM | 读 | — | `src/octop_browser/actions/interact.py:21-29`、`src/octop_browser/actions/capture.py:136-149` |
| 5 | `DOM.querySelector` / `DOM.resolveNode` | `interact` 的 selector / select 分支 | DOM | 读 | — | `src/octop_browser/actions/interact.py:47-57,239-242` |
| 6 | `Input.dispatchMouseEvent` | `click`, `scroll`, `hover` | Input | 写 | click 连发 pressed/released | `src/octop_browser/actions/interact.py:63-89,112-164` |
| 7 | `Input.dispatchKeyEvent` | `type_text`, `fill_text`, `press_key` | Input | 写 | 逐字符发送 | `src/octop_browser/actions/interact.py:92-109,167-223` |
| 8 | `Runtime.callFunctionOn` | `select_value` | Runtime | 写 | 派发 input/change | `src/octop_browser/actions/interact.py:249-257` |
| 9 | `Runtime.evaluate` | `eval_js`, DOM 元信息, wait | Runtime | 读/写 | `awaitPromise=true` | `src/octop_browser/actions/js_eval.py:19-26` |
| 10 | `Page.getLayoutMetrics` | `screenshot` full_page / 尺寸回填 | Page | 读 | 新旧字段名双兜底 | `src/octop_browser/actions/capture.py:154-159,192-203` |
| 11 | `Page.captureScreenshot` | `screenshot` | Page | 读 | base64 → 写盘 | `src/octop_browser/actions/capture.py:170-187` |
| 12 | `Emulation.setDeviceMetricsOverride` | `_InternalCDPSession._apply_viewport` | Emulation | 写 | 失败只记 debug 日志 | `src/octop_browser/session.py:74-96` |
| 13 | `Target.createTarget` / `Target.closeTarget` / `Target.activateTarget` | `new_tab`, `close_tab`, `switch_to_target` | Target | 写 | 切换后重建客户端 | `src/octop_browser/session.py:113-147,594-604,773-775` |

## 4. 逐方法请求字典与响应解包契约

### 4.1 `Page.navigate` → `navigate`（`src/octop_browser/actions/navigate.py:25-57`）

**A. 发往下游的组装字典**

```json
{"id": 1, "method": "Page.navigate", "params": {"url": "https://example.com"}}
```

| 字典键路径 | 类型 | 必填条件 | 默认值 | 值来源与转换 | 组装行号 |
|---|---|---|---|---|---|
| `id` | `int` | 必填 | 自增序号 | `self._id += 1` | `src/octop_browser/cdp/client.py:89-90` |
| `method` | `str` | 必填 | `"Page.navigate"` | 常量字面量 | `src/octop_browser/actions/navigate.py:37` |
| `params.url` | `str` | 必填 | — | 上游 `url` 原样透传 | `src/octop_browser/actions/navigate.py:37` |

**B. 返回字典与解包规则**

| 下游返回键 | 类型 | 提取/判空/兜底规则 | 解包行号 |
|---|---|---|---|
| `result.errorText` | `str \| None` | 非空即 `success=False`，`error="Navigation failed for <url>: <errorText>"` | `src/octop_browser/actions/navigate.py:38-45` |
| `result.frameId` | `str` | 读取后丢弃，内容固定 `"Navigated to <url>"` | `src/octop_browser/actions/navigate.py:53-54` |
| `Page.loadEventFired` | 事件 | `asyncio.wait_for(..., 5.0)`，超时被吞掉仍返回成功 | `src/octop_browser/actions/navigate.py:29-49` |

### 4.2 `Page.captureScreenshot` → `screenshot`（`src/octop_browser/actions/capture.py:87-228`）

**A. 发往下游的组装字典**

```json
{"id": 1, "method": "Page.captureScreenshot", "params": {"format": "png", "clip": {"x": 0, "y": 0, "width": 800, "height": 600, "scale": 1}, "captureBeyondViewport": true}}
```

| 字典键路径 | 类型 | 必填条件 | 默认值 | 值来源与转换 | 组装行号 |
|---|---|---|---|---|---|
| `params.format` | `str` | 必填 | `"png"` | 常量 | `src/octop_browser/actions/capture.py:125` |
| `params.clip` | `dict` | `element_ref` 命中或 `full_page=True` 才写入 | 不传（视口截图） | element_ref 走 `DOM.getBoxModel.model.content` 8 点取 min/max；full_page 走 `cssContentSize`/`contentSize` → `width/height` | `src/octop_browser/actions/capture.py:130-168` |
| `params.clip.x/y/width/height/scale` | `int` | 有 `clip` 时必填 | `scale=1` | 坐标计算见上 | `src/octop_browser/actions/capture.py:143-149,161-167` |
| `params.captureBeyondViewport` | `bool` | 仅 `full_page` 分支 | — | 常量 `True` | `src/octop_browser/actions/capture.py:168` |
| 输出路径 | `Path` | 非 CDP，本地落盘 | `screenshots_dir/octop-<ms>.png` | 绝对路径原样用；相对路径拼在 base 下 | `src/octop_browser/actions/capture.py:46-59` |

`element_ref` 与 `full_page` 互斥且前者优先（`src/octop_browser/actions/capture.py:130-150`）；`crop` 参数是保留位，当前无独立效果（`src/octop_browser/actions/capture.py:101`）。

**B. 返回字典与解包规则**

| 下游返回键 | 类型 | 提取/兜底/转换 | 解包行号 |
|---|---|---|---|
| `result.data` | `str` | base64 解码后 `write_bytes()`；空串返回 `success=False` | `src/octop_browser/actions/capture.py:170-187` |
| `Page.getLayoutMetrics.cssVisualViewport` / `visualViewport` | `dict` | 视口截图时补 width/height，取 `clientWidth`/`width` 与 `clientHeight`/`height` | `src/octop_browser/actions/capture.py:192-203` |
| `Runtime.evaluate` 的 `{url,title}` | `str` | 失败降级为空串，写入 `metadata` | `src/octop_browser/actions/capture.py:62-84,205-215` |
| `metadata` | `dict` | 含 `path/url/title/full_page/element_ref/width/height/size_kb` | `src/octop_browser/actions/capture.py:206-215` |

### 4.3 `Input.dispatchMouseEvent` → `click`（`src/octop_browser/actions/interact.py:63-89`）

| 字典键路径 | 类型 | 必填 | 值来源 |
|---|---|---|---|
| `params.type` | `str` | 是 | 循环取 `mousePressed`、`mouseReleased` 两次 |
| `params.x` / `params.y` | `float` | 是 | `_resolve_coords()` 返回的中心点或显式坐标 |
| `params.button` | `str` | 是 | 固定 `"left"` |
| `params.clickCount` | `int` | 是 | 固定 `1` |

返回解包：`content = "Clicked <desc> at (<cx>, <cy>)"`，`metrics.dom_nodes_scanned=1`、`estimated_tokens=10`（`src/octop_browser/actions/interact.py:85-89,12-18`）。`scroll` 复用同一命令但键为 `{"type":"mouseWheel","x":400,"y":300,"deltaX","deltaY"}`（`src/octop_browser/actions/interact.py:124-133`）；`hover` 只发 `mouseMoved`（`src/octop_browser/actions/interact.py:152-159`）。

### 4.4 `Runtime.evaluate` → `eval_js`（`src/octop_browser/actions/js_eval.py:12-59`）

| 字典键路径 | 值来源与转换 |
|---|---|
| `params.expression` | 上游 JS 表达式原样透传 |
| `params.returnByValue` | 固定 `True` |
| `params.awaitPromise` | 固定 `True` |
| 返回 `result.subtype == "error"` | 取 `description` 作为 `error`，`success=False` |
| 返回 `result.value` | `dict` 原样返回；`list`/标量走 `json.dumps(ensure_ascii=False)`；`None` → `"null"` |

### 4.5 `DOM.getDocument` → DOM 快照（会话 + builder）

| 字典键路径 | 值来源 | 锚点 |
|---|---|---|
| `params.depth` | 固定 `-1`（全树） | `src/octop_browser/session.py:306` |
| 返回 `root` | 传给 `DOMBuilder` 作为 `_dom` | `src/octop_browser/session.py:307,320-325` |
| 节点 `attributes` 扁平数组 | `zip` 转字典后提取 `role/aria-label/placeholder/type/id/name/data-testid` 等 | `src/octop_browser/dom/builder.py:217-258` |
| 节点 `nodeId` | 写入 `RefCache.store(ref, nodeId)` 并出现在 structured 输出 | `src/octop_browser/dom/builder.py:229-230,359-393` |

## 5. 下游错误拦截与翻译

| 条件 / 错误字面量 | 来源 | 本仓转换结果 | 代码行号 |
|---|---|---|---|
| WebSocket 帧 `error` 键 | CDP 返回 | `CDPSessionError("CDP error for <method>: <error>")` | `src/octop_browser/cdp/client.py:113-114` |
| `Timeout waiting for response to <method>` | `asyncio.TimeoutError` | `CDPSessionError`，超时值来自 `cfg.cdp_timeout` | `src/octop_browser/cdp/client.py:100-104` |
| `Not connected` | `_ws is None` | `CDPSessionError`，被 `_is_disconnected_error()` 识别并触发一次会话重建 | `src/octop_browser/cdp/client.py:83-84`、`src/octop_browser/tool_interface.py:83-88` |
| `Connection lost: <exc>` | 接收循环异常 | 写入所有 pending future，上报为失败 | `src/octop_browser/cdp/client.py:172-177` |
| `Ref '<ref>' not found. Call dom_tree() first.` | 本地前置校验 | 不向 CDP 发命令，直接抛错 | `src/octop_browser/actions/interact.py:43-44`、`src/octop_browser/actions/capture.py:132-135` |
| `Chrome did not start on <host>:<port> after N attempts` | launcher 轮询耗尽 | `RuntimeError`，附带 stderr tail | `src/octop_browser/cdp/launcher.py:393-398` |
| `No page target found for tab <target_id>` | 切标签匹配失败 | `RuntimeError`，ref 缓存同步失效 | `src/octop_browser/session.py:133-142` |

完整错误字典见 [`../../contracts/error-codes.md`](../../contracts/error-codes.md)。

## 6. 共变耦合与修改清单

- **新增 CDP 命令**：在对应 `actions/*` 写封装 → 补本页第 3、4 节字典表 → 更新 `../../integrations/topology-and-mapping.md` → 跑 `tests/unit/test_capture.py` 或 `test_navigate_actions.py`。
- **改 `CDPClient.send()` 的信封**：会影响全部 13 个命令，必须全仓搜索 `client.send(` 并跑 `tests/integration/test_session.py`。
- **改 `DOMBuilder` 输出字段**：直接破坏录制目标匹配（`match_target()` 读 `elements[].selectorCandidates`），同步改 `record/matcher.py` 与 `tests/unit/test_dom_builder.py`。
- **改截图路径解析**：`BROWSER_USE_SCREENSHOTS_DIR` 与 `path` 的相对/绝对规则需同步 `contracts/configuration.md`；禁止把 base64 塞回 `content`。
