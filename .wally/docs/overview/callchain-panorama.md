---
kind: panorama
scope: callchain-panorama
status: draft
origin: generated
source_paths: [src/octop_browser/tool_interface.py, src/octop_browser/session.py, src/octop_browser/actions/navigate.py, src/octop_browser/cdp/launcher.py, src/octop_browser/record/daemon.py, src/octop_browser/record/recorder.py, src/octop_browser/record/replay.py, src/octop_browser/install.py]
symbols: [browser_tool, BrowserSession.create, navigate, launch_or_attach, send_request, RecordSession.start, ReplayRunner.run, ensure_chromium]
upstream: [../INDEX.md]
downstream: [../integrations/topology-and-mapping.md, ../contracts/error-codes.md]
---

# 主干调用链全景

本仓有四条主干链：同步工具调用、浏览器启动、录制上行与回放、安装引导。静态搜索在反射分发、Unix socket、子进程与 CDP 事件回调处会断链，本页以符号级调用树与桥接表显式连接投递点和消费入口。

## 1. 主干链路索引

| 链路 ID | 链路名称 | 模式 | 起点符号（`路径:行号`） | 终点落点 | 对应业务页 |
|---|---|---|---|---|---|
| `CC-01` | 同步工具调用 | 同步请求 | `browser_tool` (`src/octop_browser/tool_interface.py:91`) | Chrome CDP → `ToolResult` | [`../business/wf-browser-action.md`](../business/wf-browser-action.md) |
| `CC-02` | 浏览器启动与页面发现 | 子进程 + HTTP 轮询 | `launch_or_attach` (`src/octop_browser/cdp/launcher.py:497`) | Chrome 进程 + 页面 WS URL | [`../architecture/cdp-layer.md`](../architecture/cdp-layer.md) |
| `CC-03` | 录制上行与语义回放 | 守护进程 + 事件上行 | `send_request` (`src/octop_browser/record/daemon.py:140`)、`ReplayRunner.run` (`src/octop_browser/record/replay.py:25`) | events.jsonl → steps.json → 回放报告 | [`../business/wf-record-replay.md`](../business/wf-record-replay.md) |
| `CC-04` | 安装引导 | 阻塞 / 流式子进程 | `ensure_chromium` (`src/octop_browser/install.py:280`)、`install_chromium_stream` (`:486`) | Playwright 缓存 + 系统库 | [`../business/wf-chromium-bootstrap.md`](../business/wf-chromium-bootstrap.md) |

## 2. 符号级条件调用树

### `CC-01`：同步工具调用

```text
CLI/MCP/Python -> src/octop_browser/tool_interface.py:91 browser_tool(action, profile, ...)
  ├─ [guard] action 不在 _KNOWN_ACTIONS -> _error_result -> return : :120-123
  ├─ [branch] close_session -> 弹注册表 + [if kill] terminate_browser -> return : :125-161
  ├─ [session] _get_or_create_session -> _registry 命中或 BrowserSession.create : :57-68
  │    └─ create -> pm.get_or_create(profile) -> internal.connect() : src/octop_browser/session.py:198-250
  ├─ [if urls 且会话已存在] urls[0] navigate，其余 new_tab(force_new) : :170-177
  ├─ [dispatch] getattr(sess, action)(**kwargs) : :179-182
  │    └─ navigate -> ref_cache.invalidate() -> CDP Page.navigate -> wait load 5s -> ToolResult
  │         src/octop_browser/session.py:262-270、src/octop_browser/actions/navigate.py:25-57
  └─ [error-map] TypeError -> 参数错误；断链 -> 重建重试一次；其他 -> 错误结果 : :183-212
```

### `CC-02`：浏览器启动与页面发现

```text
_InternalCDPSession.connect() -> src/octop_browser/session.py:49-72
  ├─ [if cfg.cdp_ws_url] 直连 -> CDPClient.connect(ws_url) -> 跳过下面全部步骤 : :55-57
  └─ [else] launch_or_attach(profile, headless) -> src/octop_browser/cdp/launcher.py:497-615
       ├─ [if port in use] attach -> _get_ws_url(/json/version) : :508-514
       ├─ [guard remote host] 非 loopback -> RuntimeError : :516-523
       ├─ find_chrome() 四级查找 -> :150-187
       ├─ prepare_chrome_launch() 环境自愈 -> src/octop_browser/cdp/launch_prep.py:207-228
       ├─ Popen(chrome, flags..., about:blank, start_new_session=True) : :566-578
       │    └─ [if exit 21/ProcessSingleton/SingletonLock] recover_profile + 重试一次 : :583-613
       └─ _get_ws_url 轮询 -> _tail_stderr 快失败 : :350-398
  └─ get_page_ws_url(port, profile) -> 黏性 target > 非 about:blank > 任意 page > 造页 : :618-671
  └─ enable Page/DOM/Runtime -> Emulation.setDeviceMetricsOverride -> idle.start : session.py:63-72
```

### `CC-03`：录制上行与语义回放

```text
CLI record start / MCP browser_record_start -> send_request({"command":"start"...})
  src/octop_browser/record/daemon.py:140-165
  └─ Unix socket -> RecordDaemon.handle -> dispatch -> start_in_process
       src/octop_browser/record/daemon.py:25-63、src/octop_browser/record/recorder.py:350-395
       ├─ RecordingStore.create() -> 目录 + events.jsonl : :378
       └─ RecordSession.start() -> addBinding + addScriptToEvaluateOnNewDocument + evaluate : :83-99,165-180
            └─ [event] Page JS emit -> Runtime.bindingCalled -> _on_binding_called -> _append
                 src/octop_browser/record/recorder.py:256-286,240-254
                 └─ redact_event -> append_event -> write_manifest
  RecordSession.stop() -> SemanticProcessor.process() -> steps.json -> SkillGenerator -> draft.skill.md
       src/octop_browser/record/recorder.py:101-134、src/octop_browser/record/semantic.py:338-351
  ReplayRunner.run() -> 逐步 browser_tool -> match_target(structured DOM) -> 回退 -> verification
       src/octop_browser/record/replay.py:25-298
       └─ [失败] _capture_failure_artifacts -> reason.txt + dom_snapshot.json + screenshot.png : :425-467
```

### `CC-04`：安装引导

```text
CLI install-browser / MCP install_browser -> ensure_chromium / install_chromium_stream
  src/octop_browser/cli.py:637-643、src/octop_browser/mcp_server.py:372-388
  ├─ [快路径] chromium_executable + verify_chromium OK -> return : src/octop_browser/install.py:293-300
  ├─ [pip] _playwright_available 为假 -> _run_pip_install（uv 优先）: :316-330,128-175
  ├─ [CDN] race_download_sources(custom/npmmirror/official) -> 逐候选 playwright install : :332-356
  │    └─ subprocess.run / create_subprocess_exec -> env 注入 PLAYWRIGHT_DOWNLOAD_HOST : playwright_download.py:165-172
  ├─ [系统库] build_install_steps -> sudo -n <pkgmgr> install -> 字体 optional : linux_deps.py:220-285
  └─ [门禁] verify_chromium -> [exe, "--version"] timeout=10 -> 唯一成败判据 : install.py:230-272
```

## 3. 跨线程 / 队列 / 子进程 / 协议桥接表

| 投递方符号（`路径:行号`） | 桥接机制 | 实际接收执行入口（`路径:行号`） | 载荷结构 |
|---|---|---|---|
| `browser_tool` (`src/octop_browser/tool_interface.py:179-182`) | `getattr(sess, action)` 动态反射 | `BrowserSession` 同名方法 (`src/octop_browser/session.py:262-869`) | `**kwargs` |
| `launch_or_attach` (`src/octop_browser/cdp/launcher.py:578`) | `subprocess.Popen` | Chrome 进程 + `_get_ws_url` 轮询 (`:350-398`) | argv 列表 + stderr 临时文件 |
| `terminate_browser` (`src/octop_browser/cdp/launcher.py:490,493`) | `asyncio.to_thread` | `pkill_chrome_profile` / `clear_profile_locks` (`src/octop_browser/cdp/launch_prep.py:189-228`) | `Path` (user-data-dir) |
| `CDPClient._recv_loop` (`src/octop_browser/cdp/client.py:152-177`) | WebSocket 事件 → 监听器回调 | `navigate` 的 `on_load` (`src/octop_browser/actions/navigate.py:31-35`)、`RecordSession._on_binding_called` (`src/octop_browser/record/recorder.py:256`) | CDP params + `__client` |
| `send_request` (`src/octop_browser/record/daemon.py:140-165`) | Unix socket 单行 JSON | `RecordDaemon.handle` → `dispatch` (`:25-91`) | `{"command": str, ...}` |
| `start_daemon_process` (`src/octop_browser/record/daemon.py:176-187`) | `subprocess.Popen` + `start_new_session` | `python -m octop_browser.record.daemon` → `main` (`:201-206`) | 无参数，socket 路径由配置决定 |
| `RecordSession.start` (`src/octop_browser/record/recorder.py:99`) | `asyncio.create_task` | `_poll_targets` 每 0.5s (`:220-230`) | 无载荷，内部轮询 `/json` |
| `BrowserIdleController.start` (`src/octop_browser/idle.py:43-48`) | `asyncio.create_task` | `_run` 周期检查 (`:111-129`) | 无载荷，读 `_last_activity` |
| `install_chromium_stream` (`src/octop_browser/install.py:377-390`) | `asyncio.create_subprocess_exec` + yield | MCP `_handle_install_browser` 聚合日志 (`src/octop_browser/mcp_server.py:377-388`) | `InstallEvent` 字典流 |
| `is_disconnected` 回调 (`src/octop_browser/install.py:400-407`) | 消费者断连信号 | `proc.kill()` | bool / coroutine |

## 4. 共变耦合与修改清单

- 改反射动作名：同步 `_KNOWN_ACTIONS`、`_ACTION_MAP`、`_ACTION_ALIAS` 三张表与 `contracts/api-reference.md`。
- 改进程启动/终止：同步 `../operations/deployment-and-runtime.md` 的进程拓扑，跑 `tests/unit/test_launcher.py`。
- 改 daemon 消息字典：CLI（`src/octop_browser/cli.py:537-607`）与 MCP（`src/octop_browser/mcp_server.py:395-457`）两侧都要改，跑 `tests/unit/test_record_daemon_client.py`。
- 改 CDP 事件监听：确认 `client.off()` 在退出时注销（`src/octop_browser/actions/navigate.py:50-51`），避免监听器泄漏。
