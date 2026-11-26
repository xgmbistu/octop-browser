---
kind: panorama
scope: callchain-panorama
status: draft
origin: generated
source_paths: [src/octop_browser/tool_interface.py, src/octop_browser/session.py, src/octop_browser/cdp/client.py, src/octop_browser/cdp/launcher.py, src/octop_browser/record/recorder.py, src/octop_browser/record/replay.py]
symbols: [browser_tool, BrowserSession, CDPClient, launch_or_attach, RecordSession, ReplayRunner, _on_binding_called]
upstream: [INDEX.md]
downstream: [integrations/topology-and-mapping.md, contracts/error-codes.md]
---

# 主干调用链全景

提炼贯穿全仓的 4 条主干执行链路：同步动作链、录制采集链、语义回放链、会话启动与空闲回收链；以符号级条件调用树与跨进程桥接表连接静态搜索会断链的线程投递、`subprocess`、动态动作分发与注入式回调。

## 1. 主干链路索引

| 链路 ID | 链路名称 | 模式 | 起点符号（`路径:行号`） | 终点落点 | 对应业务页 |
|---|---|---|---|---|---|
| `CC-01` | 同步动作链 | 同步请求 | `browser_tool` (`src/octop_browser/tool_interface.py:91`) | Chrome 页面 CDP 命令 + `ToolResult` | [WF-02](../business/wf-action-dispatch.md) |
| `CC-02` | 录制采集链 | 异步事件 + 守护进程 | `RecordDaemon.dispatch` (`src/octop_browser/record/daemon.py:39`) | `events.jsonl` + `manifest.json` | [WF-04](../business/wf-record-capture.md) |
| `CC-03` | 语义回放链 | 异步编排 | `ReplayRunner.run` (`src/octop_browser/record/replay.py:25`) | `replay_<时间>.json` 报告 / 失败快照 | [WF-06](../business/wf-replay.md) |
| `CC-04` | 会话启动与空闲回收链 | 子进程 + 后台任务 | `BrowserSession.create` (`src/octop_browser/session.py:198`) | Chrome 进程 / `terminate_browser` | [WF-01](../business/wf-browser-session-lifecycle.md) |

## 2. 符号级条件调用树（Hop-by-Hop Symbolic Traces）

### `CC-01`：同步动作链

```text
CLI/MCP/Python -> browser_tool(action, profile, **kwargs) (src/octop_browser/tool_interface.py:91)
  ├─ [guard] action not in _KNOWN_ACTIONS -> _error_result("Unknown action ...") (:120)
  ├─ [branch] action == "close_session" -> sess.close(kill) 或 terminate_browser (:125)
  ├─ [session] _get_or_create_session(profile, headless, mode, urls) (:164)
  │    └─ 未命中 -> BrowserSession.create -> _InternalCDPSession.connect (src/octop_browser/session.py:49)
  ├─ [dispatch] method = getattr(sess, action) (src/octop_browser/tool_interface.py:180)
  │    ├─ TypeError -> _error_result("Invalid parameters ...") (:183)
  │    ├─ CDPSessionError 断线 -> _drop_session + 重建会话重试一次 (:186)
  │    └─ 其它异常 -> logger.exception + _error_result (:211)
  ├─ [outbound] CDPClient.send(method, params) (src/octop_browser/cdp/client.py:75)
  │    ├─ payload = {"id": msg_id, "method": method, "params": params or {}} (:91)
  │    ├─ ws.send + await asyncio.wait_for(future, timeout) (:98、:99)
  │    ├─ [if "error" in result] -> CDPSessionError (:113)
  │    └─ return result.get("result", {}) (:115)
  └─ [return] ToolResult -> _record (src/octop_browser/session.py:895)
       └─ 失败 -> _fire("action_error")；成功 -> _fire("after_action", metrics) (:901、:903)
```

### `CC-02`：录制采集链

```text
record start -> ensure_daemon() (src/octop_browser/record/daemon.py:190)
  └─ [bridge: Unix socket] send_request({"command":"start", ...}) (:160)
       └─ RecordDaemon.dispatch -> RecordController.start_in_process (src/octop_browser/record/recorder.py:350)
            ├─ _attach -> launch_or_attach + get_page_ws_url (:331)
            ├─ store.create(manifest) -> 目录树 (src/octop_browser/record/store.py:45)
            └─ RecordSession.start -> _install_on_client (:83、:165)
                 ├─ Runtime.addBinding + Page.addScriptToEvaluateOnNewDocument (:170、:172)
                 ├─ client.on("Runtime.bindingCalled", _on_binding_called) (:176)
                 └─ asyncio.create_task(_poll_targets()) (:99)

页面 DOM 事件 (recorder.js) -> emit(kind, data) (src/octop_browser/record/injected/recorder.js:55)
  └─ [bridge: CDP binding] globalThis[CONFIG.bindingName](payload) (:57)
       └─ Runtime.bindingCalled -> _on_binding_called (src/octop_browser/record/recorder.py:256)
            ├─ [guard] nonce / 字节上限 / 限流 (:264、:273)
            └─ _append -> redact_event -> store.append_event -> events.jsonl (:240、:248)
```

### `CC-03`：语义回放链

```text
replay run <id> -> ReplayRunner.run (src/octop_browser/record/replay.py:25)
  ├─ steps_doc = store.read_steps(recording_id) (:31)
  ├─ [guard] not steps -> RuntimeError("Recording has no replayable steps") (:45)
  ├─ for step:
  │    ├─ [open/navigate/new_tab] _resolve_url -> browser_tool("navigate"/"new_tab") (:53、:66)
  │    ├─ [click/fill/select/set_checked] dom_tree(structured) (:112)
  │    │    └─ match_target(step.target, dom.content) -> ref 或 not-found (:117)
  │    ├─ [press/navigate/scroll_to] 对应 browser_tool 动作 (:200、:208、:241)
  │    └─ [if failed] _capture_failure_artifacts + break (:272)
  ├─ [for-else] _run_verification -> passed / failed (:285、:290)
  └─ [finally] _write_report -> replay-reports/replay_<时间>.json (:296、:647)
```

### `CC-04`：会话启动与空闲回收链

```text
BrowserSession.create (src/octop_browser/session.py:198)
  ├─ [bridge: subprocess] launch_or_attach -> subprocess.Popen(cmd, env, start_new_session=True) (src/octop_browser/cdp/launcher.py:578)
  ├─ _get_ws_url 轮询 /json/version (:350)
  ├─ get_page_ws_url 选 sticky target (:618)
  ├─ CDPClient.connect -> websockets.connect(ws_url, max_size) (src/octop_browser/cdp/client.py:67)
  │    └─ asyncio.create_task(_recv_loop()) (:72)
  └─ [bridge: 后台任务] idle_controller.start -> asyncio.create_task(_run()) (src/octop_browser/idle.py:43)
       └─ _check_once 超时 -> reap_now -> _drop_session + terminate_browser (:98、:70、:80)
```

## 3. 跨线程 / 队列 / 子进程 / 协议桥接表（Static-Jump Bridges）

| 投递方符号（`路径:行号`） | 桥接机制 | 实际接收执行入口（`路径:行号`） | 载荷结构 |
|---|---|---|---|
| `cli._run_record` (`src/octop_browser/cli.py:577`) | Unix socket + 独立子进程 | `RecordDaemon.handle` / `dispatch`（`src/octop_browser/record/daemon.py:25`、`:39`） | 单行 JSON 请求 `{"command": ...}` |
| `mcp_server.call_tool` (`src/octop_browser/mcp_server.py:405`) | Unix socket + 独立子进程 | `RecordDaemon.dispatch`（`:39`） | 单行 JSON 请求 |
| `recorder.js emit` (`src/octop_browser/record/injected/recorder.js:55`) | `Runtime.bindingCalled` CDP 事件 | `RecordSession._on_binding_called`（`src/octop_browser/record/recorder.py:256`） | `{nonce, schemaVersion, event:{...}}` |
| `browser_tool` (`src/octop_browser/tool_interface.py:180`) | `getattr` 动态动作分发 | `BrowserSession.<action>`（`src/octop_browser/session.py:262` 起） | `**kwargs` 字典 |
| `mcp_server.call_tool` (`src/octop_browser/mcp_server.py:349`) | `_ACTION_MAP` 字符串映射 | `browser_tool`（`src/octop_browser/tool_interface.py:91`） | `{"name", "arguments"}` |
| `launch_or_attach` (`src/octop_browser/cdp/launcher.py:578`) | `subprocess.Popen` | Chrome 进程 `Popen` | argv 列表 + env 字典 |
| `CDPClient.connect` (`src/octop_browser/cdp/client.py:72`) | `asyncio.create_task` | `_recv_loop`（`:152`） | WebSocket 帧 |
| `RecordSession.start` (`src/octop_browser/record/recorder.py:99`) | `asyncio.create_task` | `_poll_targets`（`:220`） | 0.5s 周期 |
| `BrowserIdleController.start` (`src/octop_browser/idle.py:43`) | `asyncio.create_task` | `_run` / `_check_once`（`:111`、`:98`） | 空闲截止期 |
| `install_chromium_stream` (`src/octop_browser/install.py:575`) | `asyncio.to_thread` + `ThreadPoolExecutor` | `race_download_sources`（`src/octop_browser/playwright_download.py:108`） | CDN 候选列表 |
| `verify_chromium` (`src/octop_browser/install.py:614`) | `asyncio.to_thread` | `chrome --version` 子进程 | 二进制路径 |
| `terminate_browser` (`src/octop_browser/cdp/launcher.py:490`) | `asyncio.to_thread` | `pkill_chrome_profile`（`src/octop_browser/cdp/launch_prep.py:189`） | profile data_dir |
| `Page.addScriptToEvaluateOnNewDocument` (`src/octop_browser/record/recorder.py:172`) | CDP 注入 | `recorder.js` IIFE（`src/octop_browser/record/injected/recorder.js:1`） | `source` 字符串 |

## 4. 共变耦合与修改清单（Agent Co-Change Playbook）

- **新增动态分发点**：在本页第 3 节登记投递方与消费入口，并在 [认知边界](../operations/boundary.md) 第 3 节同步；`getattr` 链变更必须核对 `_KNOWN_ACTIONS`（`src/octop_browser/tool_interface.py:20`）。
- **新增子进程 / 后台任务**：登记桥接机制，并核对 [部署与运行时](../operations/deployment-and-runtime.md) 的进程边界表与 [构建与单测映射](../operations/dev-and-test.md) 的隔离规范。
- **修改链路符号**：`CC-*` 对应的流程专页（[业务总表](../business/index.md)）与 [入向接口契约全集](../contracts/api-reference.md) 的 Handler 锚点同步。
- **回归**：`pytest tests/unit/test_tool_interface.py tests/unit/test_record_daemon_client.py tests/unit/test_record_replay_replay_runner.py tests/unit/test_idle.py`，命令见 [构建与单测映射](../operations/dev-and-test.md)。
