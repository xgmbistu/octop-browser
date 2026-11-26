---
kind: workflow
scope: business-index
status: draft
origin: generated
source_paths: [src/octop_browser/tool_interface.py, src/octop_browser/session.py, src/octop_browser/record/recorder.py, src/octop_browser/record/semantic.py, src/octop_browser/record/replay.py, src/octop_browser/install.py]
symbols: [browser_tool, BrowserSession.create, RecordController.start_in_process, SemanticProcessor.process, ReplayRunner.run, ensure_chromium]
upstream: [INDEX.md, overview/business-architecture.md]
downstream: [business/domain-models/index.md, contracts/api-reference.md]
---

# 业务能力与核心流程总清单

全量归档 8 条端到端业务闭环（`WF-*`），覆盖「会话建立 → 动作执行 → DOM 定位 → 录制 → 语义折叠 → 回放 → 安装引导 → 标签管理」。所有流程共享 `browser_tool` 单一分发入口与 `ToolResult` 统一返回，业务域划分以源码子包为界：浏览器交互域（`session/actions/dom/cdp`）、录制回放域（`record/`）、安装运维域（`install/linux_deps/playwright_download`）。

## 1. 全量业务流程路由总表（Complete Workflow Inventory）

| 流程 ID | 业务域 | 流程名称 | 触发入口（`路径:行号`） | 串联模块与外部下游链 | 变更的核心实体 / 状态 | 专页路径 |
|---|---|---|---|---|---|---|
| `WF-01` | 浏览器交互 | 会话创建、连接与关闭 | `BrowserSession.create` (`src/octop_browser/session.py:198`) | `browser_tool → ProfileManager → launch_or_attach → CDPClient → Chrome` | `_InternalCDPSession._connected`、`profile target 文件` | [wf-browser-session-lifecycle.md](wf-browser-session-lifecycle.md) |
| `WF-02` | 浏览器交互 | 单动作分发与结果归一化 | `browser_tool` (`src/octop_browser/tool_interface.py:91`) | `CLI/MCP → _registry → getattr(sess, action) → ToolResult → hooks` | `ToolResult`、`_action_count/_total_tokens/_errors` | [wf-action-dispatch.md](wf-action-dispatch.md) |
| `WF-03` | 浏览器交互 | DOM 快照、ref 签发与交互 | `BrowserSession.dom_tree` (`src/octop_browser/session.py:300`) | `DOM.getDocument → DOMBuilder → RefCache → Input.dispatch*` | `RefCache._refs`、四档 DOM 文本 | [wf-dom-ref-targeting.md](wf-dom-ref-targeting.md) |
| `WF-04` | 录制回放 | 录制采集与隐私脱敏 | `RecordController.start_in_process` (`src/octop_browser/record/recorder.py:350`) | `daemon IPC → CDP 注入 → bindingCalled → redact_event → events.jsonl` | `RecordingManifest.stats.events`、`end_url` | [wf-record-capture.md](wf-record-capture.md) |
| `WF-05` | 录制回放 | 语义折叠与变量推断 | `SemanticProcessor.process` (`src/octop_browser/record/semantic.py:338`) | `read_events → 过滤 → 折叠 → 变量化 → 期望挂载 → steps.json` | `StepsDocument.steps/inputs/verification` | [wf-semantic-steps.md](wf-semantic-steps.md) |
| `WF-06` | 录制回放 | 回放、目标匹配与报告 | `ReplayRunner.run` (`src/octop_browser/record/replay.py:25`) | `read_steps → browser_tool → match_target → verification → replay 报告` | `report.status`、`failureArtifacts` | [wf-replay.md](wf-replay.md) |
| `WF-07` | 安装运维 | Chromium 安装引导 | `ensure_chromium` (`src/octop_browser/install.py:280`) | `pip → CDN 竞速 → playwright install → install-deps → chrome --version` | Playwright 缓存二进制 | [wf-chromium-install.md](wf-chromium-install.md) |
| `WF-08` | 浏览器交互 | 标签管理与目标粘性 | `BrowserSession.new_tab` (`src/octop_browser/session.py:563`) | `Target.createTarget → switch_to_target → /json → save_target` | `.octop-browser-target.json`、CDP page WS | [wf-tab-management.md](wf-tab-management.md) |

## 2. 业务域 ↔ 接口组 ↔ 错误码 ↔ 配置键交叉速查

| 业务域 | 入向接口前缀 | 调用的外部下游封装 | 专属错误码 / 降级标识 | 核心控制配置键 |
|---|---|---|---|---|
| 浏览器交互 | 20 个 `browser_tool` 动作、21 个 CLI 动作命令、15 个 `browser_*` MCP 工具（见 [入向接口契约全集](../contracts/api-reference.md)） | [Chrome CDP](../integrations/downstream/chrome-cdp.md)、[Chromium 进程](../integrations/downstream/chromium-process.md) | `Not connected`、`Connection lost`、`Ref '...' not found`、`Timeout waiting for response to ...`（见 [错误码字典](../contracts/error-codes.md)） | `BROWSER_USE_MODE`、`BROWSER_USE_CDP_HOST`、`BROWSER_USE_CDP_PORT_START`、`BROWSER_USE_CDP_WS_URL`、`BROWSER_USE_CDP_TIMEOUT`（见 [配置手册](../contracts/configuration.md)） |
| 录制回放 | `record` 10 个子命令、`replay run`、9 个 `browser_record_*` 与 `browser_replay_run` 工具、5 个 daemon JSON 命令 | [录制守护 IPC](../integrations/downstream/record-daemon-ipc.md)、[Chrome CDP](../integrations/downstream/chrome-cdp.md) | `A recording is already active`、`No active recording`、`Record daemon is not running`、`Could not match target for ...` | `BROWSER_RECORD_REPLAY_DIR`、`BROWSER_RECORD_MAX_EVENT_BYTES`、`BROWSER_RECORD_MAX_EVENTS_PER_SECOND` |
| 安装运维 | `install-browser`、MCP `install_browser` | [Playwright 安装器](../integrations/downstream/playwright-installer.md)、[Linux 系统依赖](../integrations/downstream/linux-system-deps.md) | `Chromium binary not found`、`Chromium verification timed out`、`missing system library` | `OCTOP_SKIP_PLAYWRIGHT_PIP`、`OCTOP_MULTI_PIP_BOOTSTRAP`、`PLAYWRIGHT_DOWNLOAD_HOST`、`PLAYWRIGHT_BROWSERS_PATH` |
| 传输与运行时 | `GET /sse`、`POST /messages/`（SSE 模式） | [MCP 传输](../integrations/downstream/mcp-transport.md) | `Unknown tool: {name}`、`ERROR: {result.error}` | `MCP_PORT`、`MCP_HOST` |

## 3. 流程依赖顺序与共享不变量

```text
WF-07（安装二进制） ──前置──> WF-01（会话创建）
WF-01 ──产出会话──> WF-02（动作分发） ──调用──> WF-03（DOM 与 ref）
WF-01 ──复用标签状态──> WF-08（标签管理）
WF-04（采集 events） ──编译──> WF-05（steps.json） ──执行──> WF-06（回放报告）
WF-06 每一步 ──回到──> WF-02（browser_tool）
```

| 全局不变量 | 源码强制校验位置 |
|---|---|
| 动作名唯一白名单，CLI/MCP/回放三方共用 | `src/octop_browser/tool_interface.py:20` |
| 每个动作统一 `ToolResult`，失败不抛裸异常到调用方 | `src/octop_browser/tool_interface.py:211`、`src/octop_browser/session.py:895` |
| 导航后 `RefCache` 必失效，防止过期 `nodeId` | `src/octop_browser/actions/navigate.py:28`、`src/octop_browser/session.py:141` |
| 录制事件写盘前一律 `redact_event` | `src/octop_browser/record/recorder.py:248` |
| 回放只按语义目标匹配，不复用旧 ref / 坐标 | `src/octop_browser/record/replay.py:112`、`src/octop_browser/record/matcher.py:19` |
| `localhost` 不硬编码，主机一律取 `cfg.cdp_host` | `src/octop_browser/cdp/launcher.py:369`、`src/octop_browser/session.py:121` |

## 4. 共变耦合与修改清单（Agent Co-Change Playbook）

- **新增流程**：本表登记新 `WF-*`，并在 [业务架构全景](../overview/business-architecture.md) 的 `WF-*` 主索引、[主干调用链全景](../overview/callchain-panorama.md) 与根级 [INDEX](../INDEX.md) 同步路由。
- **修改 `WF-*` ID 或入口**：`business/index.md`、各流程专页 YAML 头、[INDEX 意图路由表](../INDEX.md) 与 `.wiki-meta.json` 的 `moduleTree` 一起改。
- **修改跨域共享入口**：`browser_tool`（`src/octop_browser/tool_interface.py:91`）被 WF-02、WF-03、WF-06、WF-08 共同依赖，签名变更必须跑全量 `pytest tests/unit/`，命令见 [构建与单测映射](../operations/dev-and-test.md)。
- **修改错误码 / 配置键**：[错误码字典](../contracts/error-codes.md)、[配置手册](../contracts/configuration.md) 与 [术语表](../overview/glossary.md) 联动。
