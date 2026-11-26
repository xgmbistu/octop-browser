---
kind: error-dict
scope: error-codes
status: draft
origin: generated
source_paths: [src/octop_browser/cdp/client.py, src/octop_browser/tool_interface.py, src/octop_browser/actions/interact.py, src/octop_browser/record/daemon.py, src/octop_browser/record/replay.py, src/octop_browser/session.py, src/octop_browser/mcp_server.py]
symbols: [CDPSessionError, _error_result, _is_disconnected_error, dispatch, send_request, ReplayRunner, run, _capture_failure_artifacts, call_tool, _format_result]
upstream: [contracts/api-reference.md, integrations/index.md]
downstream: [operations/runbook-and-observability.md, operations/pitfalls-and-adr.md]
---

# 错误码、异常传播与状态标识字典

本仓无数值型错误码枚举，错误一律以**自定义异常类 + 精确字符串消息 + `ToolResult.success=False`** 表达。全量归档 `CDPSessionError`、`ValueError`、`RuntimeError` 的产出点、下游 CDP/Chrome/守护进程错误到本仓错误的翻译，以及回放状态字面量。逐字核验结论：源码中**未找到 `degraded` 字面量**，降级一律以 `ok=False` / `status="failed"` / `status="skipped"` 表达，不虚构编号。

## 1. 异常捕获与协议状态映射规则

| 边界位置（`路径:行号`） | 捕获的内部异常类型 | 映射后的对外结构 | 是否阻断写盘或重试 |
|---|---|---|---|
| `src/octop_browser/tool_interface.py:120` | 未识别动作（非异常，前置守卫） | `_error_result`：`success=False`，`error="Unknown action '...'. Valid: [...]"` | 阻断，不建会话 |
| `src/octop_browser/tool_interface.py:167` | 会话创建任意 `Exception` | `_error_result("Failed to create session: {exc}")` | 阻断，不写 `_registry` |
| `src/octop_browser/tool_interface.py:183` | `TypeError`（参数不匹配） | `_error_result("Invalid parameters for '<action>': ...")` | 阻断，不重连 |
| `src/octop_browser/tool_interface.py:185` | 其它 `Exception` | 断线类异常重连一次，否则 `_error_result(action, str(exc))`（`:211`） | 仅断线类重试 |
| `src/octop_browser/cdp/client.py:83` | 未连接 | `CDPSessionError("Not connected")` | 阻断 |
| `src/octop_browser/cdp/client.py:99` | `asyncio.TimeoutError` | `CDPSessionError("Timeout waiting for response to {method}")` | 阻断该命令 |
| `src/octop_browser/cdp/client.py:107` | 发送阶段其它 `Exception` | `CDPSessionError("CDP send failed for {method}: {exc}")` | 阻断 |
| `src/octop_browser/cdp/client.py:113` | 响应含 `error` | `CDPSessionError("CDP error for {method}: {error}")` | 阻断 |
| `src/octop_browser/cdp/client.py:172` | `_recv_loop` 异常 | 全部 pending Future 置 `CDPSessionError("Connection lost: {exc}")` | 触发上层重连 |
| `src/octop_browser/session.py:335` | `dom_tree` 任意异常 | `ToolResult(success=False, content="", error=str(exc))` | 阻断该动作 |
| `src/octop_browser/cli.py:527` | `_run_action` 逃逸异常 | `print("ERROR: {exc}", file=sys.stderr)`，退出码 1 | 阻断 |
| `src/octop_browser/cli.py:604` | `_run_record` 任意异常 | `{"ok": False, "error": str(exc)}` | 阻断 |
| `src/octop_browser/cli.py:620` | `_run_replay` 任意异常 | `{"status": "failed", "error": str(exc)}` | 阻断 |
| `src/octop_browser/record/daemon.py:32` | `handle` 任意异常 | `{"ok": False, "error": str(exc)}` | 阻断 |

## 2. 对外接口与领域层错误全表

| 错误类型 / 精确字面量 | 产出函数与精确源码行 | 精确触发条件 | 调用方处置动作 |
|---|---|---|---|
| `CDPSessionError("Not connected")` | `src/octop_browser/cdp/client.py:84` | `self._ws is None` 时 `send` | 上层按 `not connected` 重连（`src/octop_browser/tool_interface.py:86`） |
| `CDPSessionError("Timeout waiting for response to {method}")` | `:102` | `wait_for` 超过 `cdp_timeout` | 检查 Chrome 是否卡死 |
| `CDPSessionError("CDP error for {method}: {error}")` | `:114` | CDP 响应含 `error` 键 | 回读命令 `params` |
| `CDPSessionError("Connection lost: {exc}")` | `:176` | WebSocket 接收循环异常 | 触发 `_drop_session` 重连 |
| `CDPSessionError("Ref '{ref}' not found. Call dom_tree() first.")` | `src/octop_browser/actions/interact.py:44`、`:150`、`src/octop_browser/actions/capture.py:133` | `RefCache.lookup` 返回 `None` | 重新执行 `dom_tree` |
| `CDPSessionError("Selector '{selector}' matched no elements.")` | `src/octop_browser/actions/interact.py:55` | `DOM.querySelector` 返回 `nodeId=0` | 换选择器或 ref |
| `CDPSessionError("Could not resolve ref '{ref}'.")` | `src/octop_browser/actions/interact.py:242` | `DOM.resolveNode` 缺 `objectId` | 重新取 DOM |
| `ValueError("Must provide ref, selector, or (x, y)")` | `src/octop_browser/actions/interact.py:60` | 三者皆空 | 补目标参数 |
| `ValueError("Must provide ref or selector")` | `src/octop_browser/actions/interact.py:270` | `select_value` 无目标 | 补 ref 或 selector |
| `ValueError("Invalid browser mode {value!r}. Expected one of: ...")` | `src/octop_browser/mode.py:36` | `normalize_mode` 非三态值 | 改 `BROWSER_USE_MODE` |
| `ValueError("Unknown DOM level: {level!r}")` | `src/octop_browser/dom/builder.py:184` | `build` 非四档 level | 改 `dom-tree --level` |
| `ValueError("Unknown event {event!r}. Valid: [...]")` | `src/octop_browser/hooks.py:37` | `HooksMixin.on` 非法事件名 | 用 4 个合法事件 |
| `RuntimeError("Cannot switch tabs when connected via BROWSER_USE_CDP_WS_URL")` | `src/octop_browser/session.py:108` | 直连远端 WS 时切标签 | 改用本地 launcher |
| `RuntimeError("No page target found for tab {target_id}")` | `src/octop_browser/session.py:134` | `/json` 无匹配 page | 检查标签是否存活 |
| `RuntimeError("Chrome exited immediately (returncode=...)")` | `src/octop_browser/cdp/launcher.py:377` | `process.poll()` 非空 | 读 stderr 尾部排缺库/沙箱 |
| `RuntimeError("Chrome did not start on {host}:{port} after {retries} attempts.")` | `:395` | 轮询耗尽 | 检查 `cdp_host`/端口 |
| `RuntimeError("Cannot launch Chrome on remote host ...")` | `:518` | `cdp_host` 非本地且未监听 | 用 `BROWSER_USE_CDP_WS_URL` |
| `RuntimeError("Chrome/Chromium not found. Install Google Chrome or Chromium.")` | `:527` | `find_chrome()` 返回 `None` | 跑 `install-browser` |
| `RuntimeError("No open page found in Chrome")` | `:649` | `/json` 无 page 且新建失败 | 重启 Chrome |
| `RuntimeError("Recording has no replayable steps")` / `"Recording has no executable steps"` | `src/octop_browser/record/replay.py:46`、`:284` | 回放无步骤 / 全被跳过 | 重新 `generate-steps` |
| `Navigation failed for {url}: {errorText}` | `src/octop_browser/actions/navigate.py:43` | `Page.navigate` 返回 `errorText` | 检查 URL |
| `Page.captureScreenshot returned empty data` | `src/octop_browser/actions/capture.py:176` | `data` 为空 | 检查 `cdp_max_message_size` |
| `Timeout waiting for condition` | `src/octop_browser/session.py:501` | `wait` 轮询耗尽 | 放宽 `timeout_ms` |
| `Unknown tool: {name}` | `src/octop_browser/mcp_server.py:461` | 工具名不在 `_ACTION_MAP` 且非特例 | 核对 `_TOOLS` |
| `ERROR: {result.error}` | `src/octop_browser/mcp_server.py:478` | `ToolResult.success=False` | 查 `ToolResult.error` |
| `ERROR: {result.error or '(no message)'}` | `src/octop_browser/cli.py:507` | CLI 失败结果 | 退出码 1 |
| `Unknown action '{action}'. Valid: [...]` | `src/octop_browser/tool_interface.py:122` | 动作不在 `_KNOWN_ACTIONS` | 用 20 个合法动作 |

## 3. 下游错误码 → 本仓错误翻译矩阵

| 下游系统 | 下游原始条件 | 本仓拦截位置 | 翻译后的本仓错误 / 兜底 |
|---|---|---|---|
| Chrome CDP | 响应含 `error` 键 | `src/octop_browser/cdp/client.py:113` | `CDPSessionError("CDP error for ...")` |
| Chrome CDP | WebSocket 断连 | `:172` | `CDPSessionError("Connection lost: ...")` → `browser_tool` 重连一次 |
| Chrome CDP | `Page.navigate` 的 `errorText` | `src/octop_browser/actions/navigate.py:38` | 失败 `ToolResult`，不抛异常 |
| Chrome CDP | `Runtime.evaluate` 返回 `subtype="error"` | `src/octop_browser/actions/js_eval.py:28` | 取 `description` 作 `ToolResult.error` |
| Chrome 进程 | `returncode=21` / `SingletonLock` | `src/octop_browser/cdp/launcher.py:585` | `recover_profile` 后重试一次 `Popen` |
| Chrome 进程 | `returncode=127` / 缺共享库 | `src/octop_browser/install.py:256` | `verify_chromium` 返回带 `manual_hint()` 的失败说明 |
| 录制守护 | socket 不存在 / 超时 | `src/octop_browser/record/daemon.py:152` | `{"ok": False, "error": "Record daemon is not running..."}` |
| 录制守护 | 探测 30 次未就绪 | `:198` | `{"ok": False, "error": "Daemon did not start"}` |
| 录制守护 | 已有活跃录制 / 无活跃录制 / id 不匹配 / 未知命令 | `:45`、`:66`、`:69`、`:91` | 对应 `error` 字面量，CLI 退出码 1 |
| Playwright CDN | 全部探测失败 | `src/octop_browser/playwright_download.py:138` | 回落 catalog 顺序下载，不直接判失败 |
| Linux 包管理器 | 全部库步骤失败 | `src/octop_browser/install.py:222` | `libs_ok=False`，仍继续 `verify_chromium` 报精确缺库 |

## 4. 后台状态与跳过标识字面量表（`degraded` 核验结论）

源码全量扫描结论：**未找到 `degraded` 字面量**，也无 `reason` 通用降级字段；唯一 `reason` 键是回放跳过瞬态风控 URL 时的固定值。以下为真实存在的状态字面量：

| 标识字符串字面量 | 产出位置 | 触发条件 | 系统自动兜底行为 |
|---|---|---|---|
| `"running"` | `src/octop_browser/record/replay.py:38`、`:51`、`:340` | 回放报告 / 步骤 / 验证初始化 | 无 |
| `"passed"` | `:59`、`:290`、`:345` | 步骤成功、全部验证通过 | 报告 `status="passed"`，CLI 退出 0 |
| `"failed"` | `:279`、`:293`、`src/octop_browser/cli.py:621` | 任一步骤 / 验证失败或逃逸异常 | 写 `failureArtifacts` 并短路 |
| `"skipped"` | `:213`、`:270`、`:414` | 瞬态风控 URL、未知步骤类型、不支持的验证 | 不计入 `passed` |
| `"transient_auth_or_risk_redirect"`（唯一 `reason` 值） | `src/octop_browser/record/replay.py:215` | `is_transient_auth_or_risk_url(url)` 为真 | 跳过该导航步骤 |
| `"not-found"` | `src/octop_browser/record/matcher.py:62` | 目标打分低于 45 | 触发 `_fallback_dom_action` |
| `"recording"` / `"stopped"` / `"failed"` | `src/octop_browser/record/models.py:9` | 录制生命周期 | 写 `manifest.status` |
| `"ok": False` | `src/octop_browser/record/daemon.py:33`、`:45` | 守护异常或命令前置校验失败 | CLI 退出码 1 |

## 5. 共变耦合与修改清单（Agent Co-Change Playbook）

- **新增异常类型**：定义处（如 `src/octop_browser/cdp/client.py:19`）→ `browser_tool` 的 `except` 链（`src/octop_browser/tool_interface.py:179`）→ CLI/MCP 的错误包络（`src/octop_browser/cli.py:507`、`src/octop_browser/mcp_server.py:477`）→ 本页第 2 节。
- **修改错误字面量**：`_is_disconnected_error` 依赖异常文本含 `not connected` / `connection lost`（`src/octop_browser/tool_interface.py:86`），改 `CDPSessionError` 文案会静默破坏自动重连，必须同步该谓词。
- **修改状态字面量**：`ReplayRunner.run`（`src/octop_browser/record/replay.py:25`）、`_run_verification`（`:329`）、`cli._run_replay` 的 `status == "passed"` 判定（`src/octop_browser/cli.py:623`）与 [可观测性 Runbook](../operations/runbook-and-observability.md) 联动。
- **回归**：`pytest tests/unit/test_tool_interface.py tests/unit/test_idle.py tests/unit/test_record_replay_replay_runner.py tests/unit/test_cli.py`，命令见 [构建与单测映射](../operations/dev-and-test.md)。
