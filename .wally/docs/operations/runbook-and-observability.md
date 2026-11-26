---
kind: operations
scope: runbook-and-observability
status: draft
origin: generated
source_paths: [src/octop_browser/cdp/launcher.py, src/octop_browser/record/replay.py, src/octop_browser/record/store.py, src/octop_browser/idle.py, src/octop_browser/session.py, src/octop_browser/cli.py, src/octop_browser/record/daemon.py]
symbols: [get_page_ws_url, _get_ws_url, terminate_browser, ReplayRunner, _capture_failure_artifacts, _write_report, recording_summary, BrowserIdleController, metrics_summary, _format_result, send_request]
upstream: [contracts/error-codes.md, contracts/configuration.md]
downstream: [operations/boundary.md]
---

# 可观测性信号与故障定位决策树（Agent Runbook）

本仓无独立监控端点与集中日志服务，可观测信号全部来自：CLI `--json` 输出、回放报告与失败快照、录制 `manifest.json`/`events.jsonl`、守护 `status`/`ping` 应答、Chrome 启动 stderr 临时文件，以及 `BrowserSession.metrics_summary()` 的内存累计。本页把常见症状映射到确定性源码根因。

## 1. 诊断信号读取入口表

| 信号类别 | 接口 / 磁盘文件位置 | 核心诊断字段 | 源码锚点 |
|---|---|---|---|
| 单动作结果 | CLI `--json` / MCP `TextContent.text` | `success`、`content`、`error`、`metrics`、`metadata` | `src/octop_browser/cli.py:502`、`src/octop_browser/mcp_server.py:476` |
| 会话累计 | `BrowserSession.metrics_summary()` | `total_actions`、`total_duration_ms`、`total_estimated_tokens`、`errors` | `src/octop_browser/session.py:875` |
| 录制状态 | `record status` → `{"ok", "active"}`；`record show <id>` → `recording_summary()` | `recordingId`、`status`、`profile`、`startUrl`、`endUrl`、`events`、`steps`、`*Path`、`hasSteps`、`hasSkillDraft`、`latestReplayReport` | `src/octop_browser/record/daemon.py:82`、`src/octop_browser/record/store.py:135` |
| 录制原始事件 | `<id>/events.jsonl` | 逐行 `seq`、`kind`、`receivedAt`、`targetId`、`page.url`、`redacted` | `src/octop_browser/record/store.py:88`、`:82` |
| 回放报告 | `<id>/replay-reports/replay_<时间>.json` | `status`、`steps[].status/matchedBy/error`、`verification`、`failureArtifacts`、`reportPath` | `src/octop_browser/record/replay.py:35`、`:647` |
| 失败快照 | `<id>/replay-reports/failure_<时间>_<step>/` | `reason.txt`、`dom_snapshot.json`、`screenshot.png` 或 `screenshot_error.txt` | `:425`、`:441`、`:450`、`:454`、`:464` |
| Chrome 启动失败 | `launch_or_attach` 的临时 stderr 文件尾部 4096 字节 | `Chrome exited immediately (returncode=...)` 后附 stderr | `src/octop_browser/cdp/launcher.py:374`、`:401` |
| 守护可达性 | `send_request({"command":"ping"}, timeout=1.0)` | `{"ok": False, "error": "Record daemon is not running..."}` | `src/octop_browser/record/daemon.py:168`、`:152` |
| 空闲回收 | `BrowserIdleController._check_once` 的 INFO 日志 | `Browser profile {name!r} idle for {n}s; stopping Chrome` | `src/octop_browser/idle.py:104` |
| 安装进度 | MCP `install_browser` 聚合的 `InstallEvent.log` 行 | `OK` / `FAILED: {error}` 与逐行日志 | `src/octop_browser/mcp_server.py:386`、`src/octop_browser/install.py:411` |

## 2. 症状 → 根因定位与修复决策树

### 症状 A：动作返回 `Failed to create session` 或 `Chrome did not start`

1. 读 `Chrome exited immediately (returncode=...)` 的 stderr 尾部（`src/octop_browser/cdp/launcher.py:377`）：缺共享库则按 `manual_hint()` 补依赖（`src/octop_browser/linux_deps.py:209`）；沙箱问题检查 `BROWSER_USE_NO_SANDBOX`（`src/octop_browser/cdp/launcher.py:302`）。
2. 确认二进制存在：`chromium_executable()`（`src/octop_browser/install.py:94`）或 `find_chrome()`（`:150`）；缺失则跑 `octop-browser install-browser`（[安装引导](../business/wf-chromium-install.md)）。
3. 核对 `BROWSER_USE_CDP_HOST` 与 `BROWSER_USE_CDP_PORT_START`（`src/octop_browser/settings.py:139`、`:145`）：远程主机未监听会命中 `Cannot launch Chrome on remote host`（`:518`），应改设 `BROWSER_USE_CDP_WS_URL`。
4. 检查 `BROWSER_USE_LAUNCH_RETRIES`/`DELAY`（`:153`、`:156`）是否过小导致轮询耗尽（`:395`）。

### 症状 B：`Ref 'X' not found. Call dom_tree() first.`

1. 确认刚发生过导航类动作：`navigate/go_back/go_forward/reload/switch_to_target` 均清空 `RefCache`（`src/octop_browser/actions/navigate.py:28`、`src/octop_browser/session.py:141`）；每次导航后必须重跑 `dom-tree`。
2. 若 ref 来自上一次 CLI 进程：跨进程靠 `.octop-browser-target.json` 保持标签粘性（`src/octop_browser/profile.py:49`），但 ref 缓存只在内存，进程重启必然失效。
3. 核对 `structured` 输出的 `elements` 是否含目标（`src/octop_browser/dom/builder.py:359`），tag 未进 `_INTERACTIVE_TAGS` 则不会签发 ref（`:12`）。

### 症状 C：录制守护报 `Record daemon is not running` 或 `Daemon did not start`

1. `ensure_daemon` 先 `is_running()` 探活（`src/octop_browser/record/daemon.py:191`），未就绪才 `start_daemon_process`（`:176`）。
2. 检查 `BROWSER_RECORD_REPLAY_DIR`（`src/octop_browser/record/settings.py:26`）下 `daemon.sock` 是否残留；`run()` 启动前会 `unlink`（`:108`），陈旧 socket 或 pid 文件会导致 30 次探活失败（`:194`）。
3. 用 `record daemon-start --json` 观察 `pid`/`socket`；`record status` 看 `active` 摘要（`:93`）。

### 症状 D：回放 `status="failed"` 且 `matchedBy="not-found"`

1. 读 `failureArtifacts.reasonPath` 与 `domSnapshotPath`（`src/octop_browser/record/replay.py:441`、`:450`），对照 `match_target` 打分阈值 45（`src/octop_browser/record/matcher.py:60`）。
2. 检查页面是否改版导致 `selectorCandidates`/`id`/`nameAttr` 全不匹配；`_fallback_dom_action` 会试 selector/xpath JS 与 bbox 坐标（`:469`、`:491`），仍失败才短路。
3. 若为瞬态风控 URL，报告会标 `status="skipped"` 且 `reason="transient_auth_or_risk_redirect"`（`:210`），不计入失败。
4. 变量未注入会让 `fill` 的值变空串（`_resolve_value` 返回 `inputs.get(key, "")`，`:566`），确认 `--input key=value` 拼写。

### 症状 E：截图报 `message too big` 或空 `data`

1. `CDPClient.connect` 的 `max_size` 取 `cdp_max_message_size`（默认 32 MiB，`src/octop_browser/cdp/client.py:69`）；大页面需调大 `BROWSER_USE_CDP_MAX_MESSAGE_SIZE`（`src/octop_browser/settings.py:171`）。
2. 空 `data` 分支返回 `Page.captureScreenshot returned empty data`（`src/octop_browser/actions/capture.py:176`），检查 `full_page` 是否触发超大 `clip`（`:150`）。

## 3. 可观测信号与审计落点

| 信号 | 落点 | 保留策略 |
|---|---|---|
| Chrome 启动 stderr | `tempfile.TemporaryFile(prefix="octop-browser-chrome-", suffix=".log")`（`src/octop_browser/cdp/launcher.py:554`） | 父进程关闭句柄但 Chrome 保留 dup fd，inode 在 Chrome 退出后回收（`:548` 注释） |
| 录制事件 | `events.jsonl` 追加（`:82`） | 长期保留，`chmod 0o600` |
| 回放报告 | `replay_<时间>.json`（`:651`） | 按时间戳新建，不覆盖旧报告 |
| 失败快照 | `failure_<时间>_<step>/`（`:437`） | 每次失败新建目录 |
| 日志级别 | `logging.basicConfig(level=logging.INFO)`（`src/octop_browser/cli.py:633`）、MCP `logging.INFO`（`src/octop_browser/mcp_server.py:534`） | 无结构化日志 / 无审计端点 |

## 4. 共变耦合与修改清单（Agent Co-Change Playbook）

- **新增诊断信号**：`recording_summary`（`src/octop_browser/record/store.py:135`）、回放 `report` 初始化（`:35`）、`_capture_failure_artifacts`（`:425`）与本页第 1、3 节联动。
- **修改错误文案**：`_is_disconnected_error`（`src/octop_browser/tool_interface.py:83`）依赖字面文本，改 `CDPSessionError` 消息会让自动重连失效，须同步 [错误码字典](../contracts/error-codes.md)。
- **修改回放报告结构**：`_write_report`（`:647`）、`recording_summary.latestReplayReport`（`src/octop_browser/record/store.py:141`）与 CLI `status == "passed"` 判定（`src/octop_browser/cli.py:623`）一起核查。
- **回归**：`pytest tests/unit/test_record_replay_replay_runner.py tests/unit/test_record_replay_store_skill.py tests/unit/test_launcher.py tests/unit/test_idle.py`，命令见 [构建与单测映射](dev-and-test.md)。
