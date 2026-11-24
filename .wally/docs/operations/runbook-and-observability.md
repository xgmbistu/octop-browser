---
kind: operations
scope: runbook-and-observability
status: draft
origin: generated
source_paths: [src/octop_browser/session.py, src/octop_browser/cdp/launcher.py, src/octop_browser/record/daemon.py, src/octop_browser/record/replay.py, src/octop_browser/record/store.py, src/octop_browser/cli.py, src/octop_browser/install.py]
symbols: [metrics_summary, _tail_stderr, send_request, ReplayRunner.run, recording_summary, _format_result, verify_chromium]
upstream: [../contracts/error-codes.md]
downstream: []
---

# 可观测性信号与故障定位决策树

本仓没有服务端日志采集或指标上报：可观测性由 CLI 退出码、`ToolResult.metrics`、hook 事件、落盘报告与启动期 stderr tail 五类信号组成。下列决策树均已锚定源码条件。

## 1. 诊断信号读取入口表

| 信号类别 | 接口 / 磁盘位置 | 核心诊断字段 | 源码锚点 |
|---|---|---|---|
| 会话累计指标 | `session.metrics_summary()` | `total_actions`、`total_duration_ms`、`total_estimated_tokens`、`errors` | `src/octop_browser/session.py:875-881` |
| 单次动作指标 | `ToolResult.metrics`（CLI `--json` 输出） | `action`、`duration_ms`、`dom_nodes_scanned`、`estimated_tokens`、`screenshot_size_kb` | `src/octop_browser/models.py:10-17`、`src/octop_browser/cli.py:502-511` |
| 动作事件钩子 | `before_action` / `after_action` / `action_error` | 动作名与参数、ActionMetrics、失败 ToolResult | `src/octop_browser/hooks.py:14-16`、`src/octop_browser/session.py:895-903` |
| 录制 daemon 状态 | `record status` / MCP `browser_record_status` | `active.recordingId`、`active.events` | `src/octop_browser/record/daemon.py:82-101` |
| 录制摘要 | `record show <id>` / MCP `browser_record_show` | `events`、`steps`、`hasSteps`、`skillDraft`、`latestReplayReport` | `src/octop_browser/record/store.py:135-162` |
| 回放报告 | `recordings/<id>/replay-reports/replay_<ts>.json` | `status`、`steps[].status`、`matchedBy`、`verification`、`error`、`reportPath` | `src/octop_browser/record/replay.py:35-43,291-298,647-657` |
| 失败现场 | `replay-reports/failure_<ts>_<step>/` | `reason.txt`、`dom_snapshot.json`、`screenshot.png` 或 `screenshot_error.txt` | `src/octop_browser/record/replay.py:425-467` |
| Chrome 启动 stderr | 未链接临时文件 tail（最多 4096 字节，附在 RuntimeError 文案里） | `.so` 缺失、`Failed to move to new namespace`、`--database is required` | `src/octop_browser/cdp/launcher.py:401-417,374-398` |
| CLI 退出码 | 进程返回值 | 0 成功；1 动作/录制/回放失败 | `src/octop_browser/cli.py:531-534,604-607,620-623` |
| 空闲回收日志 | `logger.info("Browser profile %r idle for ...")`，logger 名按 profile | 空闲秒数、profile 名 | `src/octop_browser/idle.py:104-108` |

## 2. 症状 → 根因定位与修复决策树

### 症状 A：`click/type` 报 `Ref '...' not found`

1. 查上次是否发生导航：`navigate/go_back/go_forward/reload` 都会 `ref_cache.invalidate()`（`src/octop_browser/actions/navigate.py:28,63,73,83`）。导航后必须重新 `dom-tree`。
2. 查是否切了标签：`_InternalCDPSession.switch_to_target()` 会重建 `CDPClient` 并清空 ref（`src/octop_browser/session.py:136-142`）。
3. 查目标元素是否仍在 `interactive` 档：`a` 标签无 `href` 不计为交互，`script/style/svg` 被跳过（`src/octop_browser/dom/builder.py:224-226,48-61`）；必要时改用 `--level full` 或 `structured`。
4. 若以 `selector` 调用，确认 `DOM.querySelector` 未返回 0（`src/octop_browser/actions/interact.py:53-55`）。

### 症状 B：Chrome 启动失败或超时

1. 读错误文案里的 `Chrome stderr (tail)`：缺 `.so` → 按 `manual_hint()` 装库（`src/octop_browser/install.py:256-267`）。
2. `Failed to move to new namespace` → 容器缺 `CLONE_NEWUSER`，设 `BROWSER_USE_NO_SANDBOX=1`（`src/octop_browser/cdp/launcher.py:283-347`）。
3. `chrome_crashpad_handler: --database is required` → 确认 `_build_flags()` 已带 `--disable-crash-reporter`（`src/octop_browser/cdp/launcher.py:206-215`）。
4. `returncode=21` / `ProcessSingleton` / `SingletonLock` → launcher 自动清锁并重试一次；仍失败则手工删除 `profiles/<name>/*.stale-*` 外的旧锁（`src/octop_browser/cdp/launcher.py:583-613`）。
5. 轮询 20×0.25s 耗尽 → 调大 `BROWSER_USE_LAUNCH_RETRIES` / `BROWSER_USE_LAUNCH_DELAY`（`src/octop_browser/cdp/launcher.py:367-368`）。

### 症状 C：`browser_tool()` 报断链或动作执行一半失败

1. 看错误是否含 `not connected` / `connection lost`：只有这两类会触发一次重建重试（`src/octop_browser/tool_interface.py:83-88,185-210`）。
2. 重试仍失败 → 用 `close_session(kill=True)` 释放端口后重来（`src/octop_browser/tool_interface.py:125-161`）。
3. 若设了 `BROWSER_USE_CDP_WS_URL` 直连远端，切标签会直接报不可切换（`src/octop_browser/session.py:107-110`），需改用本地受控 Chrome。
4. 空闲回收误杀：`BROWSER_USE_IDLE_TIMEOUT_MINUTES` 默认 0（关闭）；若开启，确认在途命令 `_active_commands>0` 时回收被跳过（`src/octop_browser/idle.py:98-109`）。

### 症状 D：录制没事件 / daemon 连不上

1. `record status` 看 `active` 是否为 null；`send_request()` 捕获连接失败会提示先跑 `record daemon-start`（`src/octop_browser/record/daemon.py:148-159`）。
2. 查 `daemon.pid` 与 `daemon.sock` 是否存在且属于当前 `BROWSER_RECORD_REPLAY_DIR`（`src/octop_browser/record/daemon.py:132-137`）。
3. 事件被丢弃有两种：payload 超过 `BROWSER_RECORD_MAX_EVENT_BYTES`（默认 65536）或每秒超过 `BROWSER_RECORD_MAX_EVENTS_PER_SECOND`（默认 100）（`src/octop_browser/record/recorder.py:232-238,263-268`）。
4. nonce 不符的事件会被丢弃，确认页面已执行 `Page.addScriptToEvaluateOnNewDocument` 注入（`src/octop_browser/record/recorder.py:165-180,273-274`）。
5. 敏感值显示为 `{{sensitive_value}}` 是预期脱敏，不是丢失（`src/octop_browser/record/privacy.py:74-81`）。

### 症状 E：回放报 `Could not match target` 或验证失败

1. 读失败报告 `failureArtifacts` 中的 `reason.txt` 与 `dom_snapshot.json`，确认目标是否还存在（`src/octop_browser/record/replay.py:425-467`）。
2. 看 `steps[].matchedBy`：`selector`/`id`/`nameAttr`/`role`/`name` 为实时匹配成功；`selector/xpath`、`bbox` 为回退；`not-found` 为彻底失败（`src/octop_browser/record/matcher.py:30-62`、`src/octop_browser/record/replay.py:469-497`）。
3. 回放只在 `structured` DOM 上匹配，确认该档输出包含 `selectorCandidates`（`src/octop_browser/dom/builder.py:359-393`）。
4. 若步骤被标 `skipped` 且 reason 为 `transient_auth_or_risk_redirect`，说明命中风控跳转白名单，属预期跳过（`src/octop_browser/record/url_filter.py:11-41`）。
5. 验证失败看 `verification[].type`：`url_contains`/`text_contains`/`selector_exists` 走 `wait` 10s 超时；`title_contains` 等走 `eval_js`（`src/octop_browser/record/replay.py:329-423`）。

### 症状 F：`install-browser` 报验证失败

1. 返回码 127 / stderr 含 `shared libraries` → 缺系统库，按输出中的 `.so` 名字与 `manual_hint()` 安装（`src/octop_browser/install.py:256-267`）。
2. `Chromium verification timed out` → `--version` 超过 10s（`src/octop_browser/install.py:247-248`）。
3. 下载阶段全部 CDN 失败 → 检查 `PLAYWRIGHT_DOWNLOAD_HOST` 是否被设为不可达镜像（`src/octop_browser/playwright_download.py:51-59`）。
4. `OCTOP_SKIP_PLAYWRIGHT_PIP=1` 且 Playwright 缺失 → 手工安装包后重试（`src/octop_browser/install.py:317-325`）。

## 3. 共变耦合与修改清单

- 新增诊断字段：同步 `ToolResult.metadata` 或回放报告结构，并更新本页信号表与 `../contracts/api-reference.md`。
- 改错误文案：必须同步 `../contracts/error-codes.md` 与本页决策树，否则 Agent 按旧关键词检索会失效。
- 改失败工件目录：同步 `../business/domain-models/index.md` 与 `deployment-and-runtime.md` 的目录树。
- 记录新日志：保持不输出敏感值；日志中不写 `BROWSER_USE_*` 的实际密钥类值。

## 4. 关联文档与信号入口索引

- [错误码字典](../contracts/error-codes.md) · [部署与运行时](deployment-and-runtime.md) · [认知边界](boundary.md)
- 临时排查时优先用 `octop-browser <command> --json` 取完整 `ToolResult`，再按本页决策树定位。
