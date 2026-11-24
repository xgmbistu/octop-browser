---
kind: error-dict
scope: error-codes
status: draft
origin: generated
source_paths: [src/octop_browser/cdp/client.py, src/octop_browser/cdp/launcher.py, src/octop_browser/actions/interact.py, src/octop_browser/actions/capture.py, src/octop_browser/actions/js_eval.py, src/octop_browser/tool_interface.py, src/octop_browser/record/daemon.py, src/octop_browser/record/replay.py, src/octop_browser/mode.py, src/octop_browser/install.py]
symbols: [CDPSessionError, _error_result, _is_disconnected_error, _get_ws_url, _resolve_coords, normalize_mode, verify_chromium]
upstream: [api-reference.md, ../integrations/index.md]
downstream: [../operations/runbook-and-observability.md]
---

# 错误码、异常传播与降级标识字典

本仓无数字错误码表：错误以异常类型、`success=False` + `error` 字符串、或 `{"ok": false, "error": ...}` 字典三种形态传播。下表只记录源码字面存在的错误，禁止虚构编号。

## 1. 异常捕获与协议状态映射规则

| 边界位置（`路径:行号`） | 捕获/产出的内部异常 | 映射后的对外结构 | 是否阻断 |
|---|---|---|---|
| `src/octop_browser/tool_interface.py:183-212` | `TypeError` / 其他 `Exception` | `ToolResult(success=False, error=...)`，不抛出 | 阻断当前动作；断链时重试一次 |
| `src/octop_browser/cli.py:531-534` | `result.success=False` | stderr 写 `ERROR: <error>`，退出码 1 | 阻断命令行成功 |
| `src/octop_browser/mcp_server.py:476-479` | `result.success=False` | `TextContent("ERROR: <error>")` | 阻断该 Tool 调用 |
| `src/octop_browser/cli.py:604-607` | 录制分支任意异常 | `{"ok": False, "error": str(exc)}`，退出码 1 | 阻断录制命令 |
| `src/octop_browser/cli.py:620-623` | 回放分支任意异常 | `{"status": "failed", "error": str(exc)}`，退出码 1 | 阻断回放命令 |
| `src/octop_browser/record/daemon.py:28-34` | `handle()` 内任意异常 | `{"ok": False, "error": str(exc)}` 写回 socket | 仅该请求失败，daemon 继续服务 |
| `src/octop_browser/hooks.py:48-53` | hook 回调异常 | `logger.exception(...)`，动作继续 | 不阻断 |

## 2. 对外接口与领域层错误全表

| 错误字面量 / 异常类型 | 来源 | 精确触发条件 | 调用方处置 |
|---|---|---|---|
| `Unknown action '<action>'. Valid: [...]` | `src/octop_browser/tool_interface.py:120-123` | action 不在 19 项白名单 | 改用合法 action |
| `Unknown tool: <name>` | `src/octop_browser/mcp_server.py:459-461` | MCP Tool 名既不在 `_ACTION_MAP` 也非特殊工具 | 核对工具列表 |
| `Invalid parameters for '<action>': <exc>` | `src/octop_browser/tool_interface.py:183-184` | kwargs 与会话方法签名不匹配 | 修正参数名 |
| `Invalid parameters for 'close_session': [...]` | `src/octop_browser/tool_interface.py:127-131` | kill 之外还传了 kwargs | 只传 profile/kill |
| `Failed to create session: <exc>` | `src/octop_browser/tool_interface.py:167-168` | `BrowserSession.create()` 抛异常 | 检查 Chrome 与 CDP 配置 |
| `Not connected` | `src/octop_browser/cdp/client.py:83-84` | `CDPClient._ws is None` 时调用 send | 被入口识别后重建会话一次 |
| `Timeout waiting for response to <method>` | `src/octop_browser/cdp/client.py:100-104` | 超过 `cfg.cdp_timeout`（默认 30s） | 检查浏览器卡死或调大超时 |
| `CDP error for <method>: <error>` | `src/octop_browser/cdp/client.py:113-114` | CDP 响应含 `error` 键 | 按 CDP method 排查 |
| `CDP send failed for <method>: <exc>` | `src/octop_browser/cdp/client.py:107-109` | WebSocket 发送异常 | 检查连接状态 |
| `Connection lost: <exc>` | `src/octop_browser/cdp/client.py:172-177` | 接收循环异常 | 触发上层重建 |
| `Ref '<ref>' not found. Call dom_tree() first.` | `src/octop_browser/actions/interact.py:43-44,149-150,237-238`、`src/octop_browser/actions/capture.py:132-135` | `RefCache.lookup()` 返回 None | 重新 `dom_tree()` 取新 ref |
| `Selector '<selector>' matched no elements.` | `src/octop_browser/actions/interact.py:53-55` | `DOM.querySelector` 返回 nodeId=0 | 修正选择器 |
| `Could not resolve ref '<ref>'.` | `src/octop_browser/actions/interact.py:241-242` | `DOM.resolveNode` 无 objectId | 重新取快照 |
| `Must provide ref, selector, or (x, y)` | `src/octop_browser/actions/interact.py:60` | 三种定位方式都未给 | 补目标参数 |
| `Must provide ref or selector` | `src/octop_browser/actions/interact.py:270` | select 无目标 | 补 ref/selector |
| `Unknown DOM level: <level>` | `src/octop_browser/dom/builder.py:184` | 非法 level | 用四档合法值 |
| JS `result.subtype == "error"` 的 `description` | `src/octop_browser/actions/js_eval.py:27-40` | `Runtime.evaluate` 返回 JS 异常对象 | `ToolResult(success=False, error=description)` |
| `Invalid browser mode <value>. Expected one of: auto, headed, headless` | `src/octop_browser/mode.py:35-39` | `normalize_mode()` 校验失败 | 修正 mode |
| `Page.captureScreenshot returned empty data` | `src/octop_browser/actions/capture.py:172-183` | CDP 返回 data 为空 | 重试截图 |
| `Cannot switch tabs when connected via BROWSER_USE_CDP_WS_URL` | `src/octop_browser/session.py:107-110` | 直连模式下调用切标签 | 改用可控 Chrome 或去掉直连 |
| `No page target found for tab <target_id>` | `src/octop_browser/session.py:133-134` | `/json` 中找不到目标页 | 刷新标签列表 |
| `No open page found in Chrome` | `src/octop_browser/cdp/launcher.py:648-649` | 无 page target 且造页失败 | 检查 Chrome 状态 |

## 3. 进程/启动错误与翻译

| 错误字面量 | 产出位置 | 触发条件 | 处置 |
|---|---|---|---|
| `Chrome exited immediately (returncode=<n>) before binding to <host>:<port>` | `src/octop_browser/cdp/launcher.py:374-380` | 轮询期间进程已退出 | 读 stderr tail 找真实原因 |
| `Chrome did not start on <host>:<port> after <N> attempts` | `src/octop_browser/cdp/launcher.py:393-398` | 20×0.25s 内 `/json/version` 无响应 | 检查依赖库/沙箱/DISPLAY |
| `Cannot launch Chrome on remote host '<host>'` | `src/octop_browser/cdp/launcher.py:516-523` | host 非 loopback 且未设 CDP_WS_URL | 远端手工启动或设直连 |
| `Chrome/Chromium not found. Install Google Chrome or Chromium.` | `src/octop_browser/cdp/launcher.py:525-531` | 四级查找全失败 | 跑 `install-browser` |
| `A recording is already active` | `src/octop_browser/record/daemon.py:45-49` | 重复 start | 先 stop 当前录制 |
| `No active recording` | `src/octop_browser/record/daemon.py:65-66` | 无录制时 stop | 先 start |
| `Active recording is <id>, not <id>` | `src/octop_browser/record/daemon.py:67-72` | stop 指定 ID 不符 | 用活动 ID |
| `Record daemon is not running. Start it with ...` | `src/octop_browser/record/daemon.py:152-159` | socket 连接失败/超时 | 跑 `record daemon-start` |
| `Daemon did not start` | `src/octop_browser/record/daemon.py:198` | 30×0.1s 仍不可达 | 查 pid/socket 路径 |
| `Chromium binary not found` | `src/octop_browser/install.py:237-239` | `chromium_executable()` 为 None | 跑安装流程 |
| `Chromium verification timed out` | `src/octop_browser/install.py:247-248` | `--version` 超过 10s | 检查二进制是否卡死 |
| `Chromium binary exists but cannot start (missing system library...)` | `src/octop_browser/install.py:256-267` | 返回码 127 或 stderr 含 shared libraries | 按 `manual_hint()` 装库 |
| `Playwright is not installed and OCTOP_SKIP_PLAYWRIGHT_PIP is set` | `src/octop_browser/install.py:317-325,538-545` | 跳过引导且包缺失 | 手工 `pip install playwright` |

## 4. 回放与录制降级标识

| 标识字面量 | 产出位置（`路径:行号`） | 触发条件 | 自动兜底行为 |
|---|---|---|---|
| `Recording has no replayable steps` | `src/octop_browser/record/replay.py:45-46` | `steps.json` 步骤为空 | 报告 `status=failed` |
| `Recording has no executable steps` | `src/octop_browser/record/replay.py:282-284` | 过滤 skipped 后为空 | 报告 `status=failed` |
| `Could not match target for <step>: <target>` | `src/octop_browser/record/replay.py:154-168` | `match_target()` 返回 None 且回退失败 | 写 `failureArtifacts` 并 break |
| `transient_auth_or_risk_redirect` | `src/octop_browser/record/replay.py:210-219` | URL 命中四类风控/验证码跳转 | 步骤标 `skipped`，继续后续步骤 |
| `Unsupported verification: <typ>` | `src/octop_browser/record/replay.py:412-415` | 验证类型不在六项之内 | 该验证标 `skipped` |
| `Verification failed: <typ>=<value>` | `src/octop_browser/record/replay.py:417-422` | 验证项失败 | 整体报告 `status=failed` |
| `{{sensitive_value}}` / `{{redacted_value}}` | `src/octop_browser/record/privacy.py:79`、`src/octop_browser/record/injected/recorder.js:245-248` | 命中脱敏策略或敏感字段 | 以占位符落盘，回放时由 `--input` 注入 |
| `not-found` | `src/octop_browser/record/matcher.py:62` | 目标匹配得分 <45 | 触发 selector/xpath/bbox 回退 |

## 5. 共变耦合与排障入口

- 所有 `ToolResult` 失败最终可在 CLI `--json` 输出中拿到完整 `error` 与 `metrics`（`src/octop_browser/cli.py:502-511`）。
- 启动类错误的 stderr tail 由 `_tail_stderr()` 提供，最多 4096 字节（`src/octop_browser/cdp/launcher.py:401-417`）。
- 确定性排查决策树见 [`../operations/runbook-and-observability.md`](../operations/runbook-and-observability.md)；新增错误字面量必须同步本页与对应单测断言。

## 6. 关联文档

- [排障 Runbook](../operations/runbook-and-observability.md) · [入向接口全集](api-reference.md) · [Chrome CDP 出向契约](../integrations/downstream/chrome-cdp.md)
