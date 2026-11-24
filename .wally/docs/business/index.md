---
kind: workflow
scope: business-index
status: draft
origin: generated
source_paths: [src/octop_browser/tool_interface.py, src/octop_browser/session.py, src/octop_browser/record/recorder.py, src/octop_browser/record/replay.py, src/octop_browser/install.py]
symbols: [browser_tool, BrowserSession, RecordController, ReplayRunner, ensure_chromium]
upstream: [../INDEX.md, ../overview/business-architecture.md]
downstream: [domain-models/index.md, wf-browser-action.md, wf-record-replay.md, wf-chromium-bootstrap.md, ../contracts/api-reference.md]
---

# 业务能力与核心流程总清单

本仓对外提供三条端到端业务闭环：无状态工具调用、录制到回放、浏览器引导安装。全部流程共用 Profile 持久化与 CDP 会话底座，逐流程的符号调用树与规则见专页。

## 1. 全量业务流程路由总表

| 流程 ID | 业务域 | 流程名称 | 触发入口（`路径:行号`） | 串联模块与外部下游链 | 变更的核心实体/状态 | 专页 |
|---|---|---|---|---|---|---|
| `WF-01` | 浏览器自动化 | 无状态工具调用与会话复用 | `browser_tool()` (`src/octop_browser/tool_interface.py:91-212`)、CLI `_run_action` (`src/octop_browser/cli.py:514-534`)、MCP `call_tool` (`src/octop_browser/mcp_server.py:391-479`) | 入向适配 → `_registry` → `BrowserSession` (`src/octop_browser/session.py:174-196`) → `actions/*` → CDP → Chrome | `ToolResult`、`RefCache`、Profile target | [`wf-browser-action.md`](wf-browser-action.md) |
| `WF-02` | 录制与回放 | 录制→语义折叠→Skill→重放 | `RecordController.start_in_process` (`src/octop_browser/record/recorder.py:350-395`)、`ReplayRunner.run` (`src/octop_browser/record/replay.py:25-298`) | daemon → 注入 JS → events.jsonl → SemanticProcessor → SkillGenerator / ReplayRunner → CDP | `RecordingManifest`、`StepsDocument`、回放报告 | [`wf-record-replay.md`](wf-record-replay.md) |
| `WF-03` | 运行环境引导 | Chromium 安装与验证 | `ensure_chromium()` (`src/octop_browser/install.py:280-369`)、`install_chromium_stream()` (`:486-620`) | pip 引导 → CDN 竞速 → 下载 → 系统库/字体 → `chrome --version` | `InstallEvent`、Playwright 缓存目录 | [`wf-chromium-bootstrap.md`](wf-chromium-bootstrap.md) |

## 2. 业务域 ↔ 接口组 ↔ 错误码 ↔ 配置键交叉速查

| 业务域 | 入向接口前缀 | 调用的外部下游封装 | 专属错误标识 | 核心控制配置键 |
|---|---|---|---|---|
| 浏览器自动化 | CLI 动作子命令、MCP `browser_*`、Python `browser_tool` | [`chrome-cdp`](../integrations/downstream/chrome-cdp.md) | `CDPSessionError`、`Ref '<ref>' not found`、`Chrome did not start` | `BROWSER_USE_MODE`、`BROWSER_USE_CDP_WS_URL`、`BROWSER_USE_IDLE_TIMEOUT_MINUTES` |
| 录制与回放 | CLI `record ...` / `replay run`、MCP `browser_record_*` / `browser_replay_run` | [`chrome-cdp`](../integrations/downstream/chrome-cdp.md) + 仓内 daemon socket | `A recording is already active`、`Could not match target for <step>`、`transient_auth_or_risk_redirect` | `BROWSER_RECORD_REPLAY_DIR`、`BROWSER_RECORD_MAX_EVENT_BYTES`、`BROWSER_RECORD_MAX_EVENTS_PER_SECOND` |
| 环境引导 | CLI `install-browser`、MCP `install_browser` | [`playwright-cdn`](../integrations/downstream/playwright-cdn.md) | `Chromium binary not found`、`Chromium verification timed out` | `PLAYWRIGHT_DOWNLOAD_HOST`、`OCTOP_SKIP_PLAYWRIGHT_PIP`、`OCTOP_MULTI_PIP_BOOTSTRAP` |

三域的配置全集见 [`../contracts/configuration.md`](../contracts/configuration.md)，错误字面量见 [`../contracts/error-codes.md`](../contracts/error-codes.md)，实体字段字典见 [`domain-models/index.md`](domain-models/index.md)。

## 3. 全局业务不变量速查

1. **会话按 profile 隔离**：同一 profile 复用会话，不同 profile 各自持有 CDP 端口与 user-data-dir（`src/octop_browser/tool_interface.py:63-68`、`src/octop_browser/profile.py:165-174`）。
2. **导航即失效**：任何跨文档导航都必须清 ref 缓存（`src/octop_browser/actions/navigate.py:28,63,73,83`）。
3. **录制先脱敏**：事件落盘前统一经 `redact_event()`（`src/octop_browser/record/recorder.py:248-249`）。
4. **回放重匹配**：重放不复用录制时的 nodeId，按实时 structured DOM 打分匹配（`src/octop_browser/record/replay.py:112-118`）。
5. **安装以验证为准**：下载/装库失败不直接宣布成功，必须 `verify_chromium()` 通过（`src/octop_browser/install.py:364-369`）。

## 4. 共变耦合与修改清单

- 任一流程的入向命令变更：同步 [`../contracts/api-reference.md`](../contracts/api-reference.md) 与 CLI/MCP 两侧 Schema。
- 任一流程的下游字典变更：同步 [`../integrations/topology-and-mapping.md`](../integrations/topology-and-mapping.md) 与对应 downstream 专页。
- 任一流程的实体字段变更：同步 [`domain-models/index.md`](domain-models/index.md) 与 `../overview/glossary.md`。
