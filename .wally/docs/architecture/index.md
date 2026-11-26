---
kind: component
scope: architecture-index
status: draft
origin: generated
source_paths: [src/octop_browser/__init__.py, src/octop_browser/record/__init__.py, src/octop_browser/models.py]
symbols: [__all__, ActionMetrics, ToolResult, TabInfo]
upstream: [INDEX.md, overview/system-architecture.md]
downstream: [architecture/module-dep-matrix.md, operations/boundary.md]
---

# 组件技术架构总表

按运行时框架模型（Archetype）汇总全仓技术模块，并把不单独成篇的 Tier 3 工具文件完整归档，确保 `src/octop_browser/` 下全部 40 个受跟踪文件 100% 纳入路由索引。包根导出 12 个符号（`src/octop_browser/__init__.py:15`），`record` 子包导出 8 个符号（`src/octop_browser/record/__init__.py:14`），三个 Pydantic 值对象定义于 `src/octop_browser/models.py:10`、`:20`、`:36`。

## 1. 全量核心组件矩阵（Tier 1 & Tier 2）

| 组件标识 | 框架模型（Archetype） | 源码路径 | 核心入口符号（`路径:行号`） | 技术能力与业务边界 | 直接上游 | 直接下游 | 详情文档 |
|---|---|---|---|---|---|---|---|
| `mcp-server` | `API Service` | `src/octop_browser/mcp_server.py` | `app` (`:22`)、`call_tool` (`:391`) | 25 个 MCP 工具注册、stdio/SSE 双传输 | MCP Client | `browser_tool`、录制控制器 | [mcp-server.md](mcp-server.md) |
| `cli` | `UI & CLI` | `src/octop_browser/cli.py` | `main` (`:631`)、`_build_parser` (`:96`) | 24 顶层 + 11 子命令 argparse 树 | 终端用户 | `browser_tool`、录制控制器 | [cli.md](cli.md) |
| `tool-interface` | `API Service` | `src/octop_browser/tool_interface.py` | `browser_tool` (`:91`)、`_KNOWN_ACTIONS` (`:20`) | 按 profile 复用会话、`getattr` 动态分发、断线重连 | CLI / MCP / Python API | `BrowserSession` | [mcp-server.md](mcp-server.md) |
| `browser-session-engine` | `Core Engine` | `src/octop_browser/session.py`、`dom/`、`actions/` | `BrowserSession` (`session.py:174`)、`DOMBuilder` (`dom/builder.py:137`) | 会话生命周期、四档 DOM、稳定 ref、统一 `ToolResult` | `browser_tool` | `CDPClient` | [browser-session-engine.md](browser-session-engine.md) |
| `cdp-transport` | `Data & Adapter` | `src/octop_browser/cdp/client.py` | `CDPClient.send` (`:75`) | 纯 asyncio CDP 帧封装、超时、事件分发 | 引擎层 / 录制层 | Chrome WebSocket | [cdp-transport-and-storage.md](cdp-transport-and-storage.md) |
| `cdp-launcher` | `Data & Adapter` | `src/octop_browser/cdp/launcher.py`、`launch_prep.py` | `launch_or_attach` (`:497`) | Chrome 拉起/附着、端口发现、自愈、优雅关闭 | `_InternalCDPSession` | Chromium 进程 | [cdp-transport-and-storage.md](cdp-transport-and-storage.md) |
| `profile-store` | `Data & Adapter` | `src/octop_browser/profile.py` | `ProfileManager.get_or_create` (`:165`) | profile 端口与目标粘性磁盘状态 | `BrowserSession` | 磁盘 JSON | [cdp-transport-and-storage.md](cdp-transport-and-storage.md) |
| `record-daemon` | `Async / Cron Worker` | `src/octop_browser/record/daemon.py`、`recorder.py` | `RecordDaemon.dispatch` (`:39`)、`RecordSession.start` (`recorder.py:83`) | 单活跃录制、注入采集、0.5s 目标轮询 | CLI / MCP | Chrome CDP、磁盘产物 | [record-daemon.md](record-daemon.md) |
| `semantic-replay` | `Core Engine` | `src/octop_browser/record/semantic.py`、`replay.py` | `SemanticProcessor.process` (`semantic.py:338`)、`ReplayRunner.run` (`replay.py:25`) | 事件折叠、变量推断、目标匹配、验证报告 | 录制产物 | `browser_tool` | [record-daemon.md](record-daemon.md) |
| `installer` | `Async Worker` | `src/octop_browser/install.py`、`playwright_download.py`、`linux_deps.py` | `ensure_chromium` (`install.py:280`) | CDN 竞速、Playwright 引导、系统依赖 | CLI / MCP | Playwright CDN / 包管理器 | [record-daemon.md](record-daemon.md) 之外的独立契约页见下 |
| `downstream-chrome-cdp` | `Downstream Wrapper` | `src/octop_browser/cdp/client.py`、`actions/` | `CDPClient.send` (`:75`) | 全量 CDP 命令字典与返回解包 | 引擎层 | Chrome | [chrome-cdp.md](../integrations/downstream/chrome-cdp.md) |
| `downstream-chromium-process` | `Downstream Wrapper` | `src/octop_browser/cdp/launcher.py`、`launch_prep.py` | `launch_or_attach` (`:497`) | Popen argv/env/flags 与关闭契约 | 会话装配 | Chromium 进程 | [chromium-process.md](../integrations/downstream/chromium-process.md) |
| `downstream-playwright` | `Downstream Wrapper` | `src/octop_browser/install.py`、`playwright_download.py` | `install_chromium_stream` (`install.py:486`) | pip/CDN/InstallEvent 字典 | 安装引导 | Playwright CDN | [playwright-installer.md](../integrations/downstream/playwright-installer.md) |
| `downstream-linux-deps` | `Downstream Wrapper` | `src/octop_browser/linux_deps.py` | `build_install_steps` (`:220`) | 6 种包管理器包名矩阵 | 安装引导 | 系统包仓库 | [linux-system-deps.md](../integrations/downstream/linux-system-deps.md) |
| `downstream-daemon-ipc` | `Downstream Wrapper` | `src/octop_browser/record/daemon.py` | `send_request` (`:140`) | Unix socket 单行 JSON 协议 | CLI / MCP | 录制守护进程 | [record-daemon-ipc.md](../integrations/downstream/record-daemon-ipc.md) |
| `downstream-mcp-transport` | `Downstream Wrapper` | `src/octop_browser/mcp_server.py` | `_main` (`:482`) | stdio / SSE 路由与包络 | MCP Client | MCP 运行时 | [mcp-transport.md](../integrations/downstream/mcp-transport.md) |

`installer` 一行的逐字典契约分散在 [Playwright 安装器](../integrations/downstream/playwright-installer.md) 与 [Linux 系统依赖](../integrations/downstream/linux-system-deps.md)，流程视角见 [WF-07](../business/wf-chromium-install.md)。

## 2. 轻量辅助模块归档表（Tier 3 Utilities — 全量 40 文件零遗漏兜底）

下表覆盖 `git ls-files src/` 的全部 40 个受跟踪文件；已独立成篇者在「职责说明」括注所属专页，未成篇者给出复用函数与调用方，禁止重复造轮子。

| 源码文件路径 | 核心导出函数 / 类 / 常量 | 调用方模块 | 具体职责说明 |
|---|---|---|---|
| `src/octop_browser/__init__.py` | `__all__`（12 符号） | 全仓 / 外部调用方 | 包根导出（本页 §1 锚定） |
| `src/octop_browser/actions/__init__.py` | 空包标记 | `session.py` | actions 子包声明，0 行 |
| `src/octop_browser/actions/capture.py` | `screenshot`、`_resolve_path`、`_page_context` | `BrowserSession.screenshot` | 截图写盘与 metadata（[chrome-cdp.md](../integrations/downstream/chrome-cdp.md)） |
| `src/octop_browser/actions/interact.py` | `click`、`type_text`、`fill_text`、`press_key`、`scroll`、`hover`、`select_value`、`_resolve_coords` | 各 `BrowserSession` 交互方法 | ref / selector / 坐标解析与 Input 派发（[browser-session-engine.md](browser-session-engine.md)） |
| `src/octop_browser/actions/js_eval.py` | `eval_js` | `BrowserSession.eval_js` | `Runtime.evaluate` 封装与解包 |
| `src/octop_browser/actions/navigate.py` | `navigate`、`go_back`、`go_forward`、`reload`、`_LOAD_EVENT_TIMEOUT_SECONDS` | 导航方法 | 导航与 ref 失效（[wf-browser-session-lifecycle.md](../business/wf-browser-session-lifecycle.md)） |
| `src/octop_browser/cdp/__init__.py` | 空包标记 | `session.py` | cdp 子包声明，0 行 |
| `src/octop_browser/cdp/client.py` | `CDPClient`、`CDPSessionError`、`ActivityTracker` | 引擎层 / 录制层 | CDP 帧底座（[cdp-transport-and-storage.md](cdp-transport-and-storage.md)） |
| `src/octop_browser/cdp/launch_prep.py` | `prepare_chrome_launch`、`recover_profile`、`pkill_chrome_profile`、`clear_profile_locks` | `launch_or_attach` | 启动前 XDG / 锁 / 可写性自愈 |
| `src/octop_browser/cdp/launcher.py` | `launch_or_attach`、`find_chrome`、`get_page_ws_url`、`terminate_browser`、`_build_flags` | `_InternalCDPSession` | Chrome 进程管理（[chromium-process.md](../integrations/downstream/chromium-process.md)） |
| `src/octop_browser/cli.py` | `main`、`_build_parser`、`_action_kwargs`、`_run_action`、`_run_record`、`_run_replay` | `octop-browser` 脚本 | CLI 命令树（[cli.md](cli.md)） |
| `src/octop_browser/dom/__init__.py` | 空包标记 | `session.py` | dom 子包声明，0 行 |
| `src/octop_browser/dom/builder.py` | `DOMBuilder`、`DOMLevel`、`_make_ref`、`_INTERACTIVE_TAGS` | `BrowserSession.dom_tree` | 四档 DOM 与 ref 签发（[wf-dom-ref-targeting.md](../business/wf-dom-ref-targeting.md)） |
| `src/octop_browser/dom/refs.py` | `RefCache` | `DOMBuilder`、交互动作 | ref→nodeId 缓存与失效 |
| `src/octop_browser/hooks.py` | `HooksMixin`、`_VALID_EVENTS` | `BrowserSession` | 四类事件回调，异常吞掉（[wf-action-dispatch.md](../business/wf-action-dispatch.md)） |
| `src/octop_browser/idle.py` | `BrowserIdleController`、`idle_controller_for` | `_InternalCDPSession` | 空闲回收守护（[wf-browser-session-lifecycle.md](../business/wf-browser-session-lifecycle.md)） |
| `src/octop_browser/install.py` | `ensure_chromium`、`install_chromium_stream`、`verify_chromium`、`InstallEvent` | CLI / MCP | 安装流水线（[playwright-installer.md](../integrations/downstream/playwright-installer.md)） |
| `src/octop_browser/linux_deps.py` | `build_install_steps`、`detect_package_manager`、`_PACKAGES`、`manual_hint` | `install.py` | 包管理器矩阵（[linux-system-deps.md](../integrations/downstream/linux-system-deps.md)） |
| `src/octop_browser/mcp_server.py` | `app`、`_TOOLS`、`_ACTION_MAP`、`call_tool`、`_main` | `python -m ...mcp_server` | MCP 服务（[mcp-server.md](mcp-server.md)） |
| `src/octop_browser/models.py` | `ActionMetrics`、`ToolResult`、`TabInfo` | 全仓 | Pydantic 值对象（[tool-result-and-metrics.md](../business/domain-models/tool-result-and-metrics.md)） |
| `src/octop_browser/mode.py` | `BrowserMode`、`normalize_mode`、`resolve_headless`、`has_desktop_environment` | `BrowserSession.create` / settings | 三态启动模式 |
| `src/octop_browser/playwright_download.py` | `build_download_candidates`、`race_download_sources`、`env_for_candidate`、`plain_cli_env` | `install.py` | CDN 竞速（[playwright-installer.md](../integrations/downstream/playwright-installer.md)） |
| `src/octop_browser/profile.py` | `Profile`、`ProfileManager` | `BrowserSession` / launcher | 端口与目标粘性（[cdp-transport-and-storage.md](cdp-transport-and-storage.md)） |
| `src/octop_browser/py.typed` | PEP 561 标记文件 | 类型检查器 | 声明包带类型信息，无代码 |
| `src/octop_browser/record/__init__.py` | `__all__`（8 符号） | 全仓 / 外部调用方 | 录制子包导出（本页 §1 锚定） |
| `src/octop_browser/record/daemon.py` | `RecordDaemon`、`ensure_daemon`、`send_request`、`socket_path` | CLI / MCP | 守护进程与 IPC（[record-daemon-ipc.md](../integrations/downstream/record-daemon-ipc.md)） |
| `src/octop_browser/record/injected/recorder.js` | `emit`、`describeElement`、`readValue`、`roleOf` | `RecordSession._install_on_client` | 页面注入采集脚本（[wf-record-capture.md](../business/wf-record-capture.md)） |
| `src/octop_browser/record/matcher.py` | `match_target` | `ReplayRunner` | 目标打分（[wf-replay.md](../business/wf-replay.md)） |
| `src/octop_browser/record/models.py` | `RecordingManifest`、`SemanticStep`、`StepsDocument`、`PrivacySettings` | 录制全链路 | 产物模型（[recording-artifacts.md](../business/domain-models/recording-artifacts.md)） |
| `src/octop_browser/record/privacy.py` | `redact_event`、`redact_url`、`SENSITIVE_RE`、`URL_KEYS` | `RecordSession._append` | 隐私脱敏 |
| `src/octop_browser/record/recorder.py` | `RecordController`、`RecordSession` | daemon / CLI | 采集会话（[wf-record-capture.md](../business/wf-record-capture.md)） |
| `src/octop_browser/record/replay.py` | `ReplayRunner` | CLI / MCP | 回放与报告（[wf-replay.md](../business/wf-replay.md)） |
| `src/octop_browser/record/semantic.py` | `SemanticProcessor`、`_var_for`、`_compact_target` | `RecordSession.stop` | 语义折叠（[wf-semantic-steps.md](../business/wf-semantic-steps.md)） |
| `src/octop_browser/record/settings.py` | `RecordReplaySettings`、`settings` | `RecordingStore` / daemon | 录制目录与限流配置 |
| `src/octop_browser/record/skill_generator.py` | `SkillGenerator` | `RecordSession.stop` | `draft.skill.md` 渲染（[wf-replay.md](../business/wf-replay.md)） |
| `src/octop_browser/record/store.py` | `RecordingStore` | 录制 / 回放 / CLI | 磁盘产物读写（[recording-artifacts.md](../business/domain-models/recording-artifacts.md)） |
| `src/octop_browser/record/url_filter.py` | `is_transient_auth_or_risk_url`、`is_replayable_page_url` | `SemanticProcessor` / `ReplayRunner` | URL 过滤 |
| `src/octop_browser/session.py` | `BrowserSession`、`_InternalCDPSession` | `browser_tool` | 公开会话门面（[browser-session-engine.md](browser-session-engine.md)） |
| `src/octop_browser/settings.py` | `OctopSettings`、`state_dir`、`settings` | 全仓 | 环境解析（[configuration.md](../contracts/configuration.md)） |
| `src/octop_browser/tool_interface.py` | `browser_tool`、`_KNOWN_ACTIONS`、`_error_result` | CLI / MCP / 回放 | 无状态分发（[wf-action-dispatch.md](../business/wf-action-dispatch.md)） |

## 3. 源码目录覆盖对账

| 源码目录 | 已归档位置 | 结论 |
|---|---|---|
| `src/octop_browser/`（根） | 本页 §1 + §2 | 14 个根级 .py 与 `py.typed` 全覆盖 |
| `src/octop_browser/actions/`、`cdp/`、`dom/` | 本页 §2 + 对应组件页 | 3 个子包全覆盖 |
| `src/octop_browser/record/`（`injected/` 含 JS） | 本页 §2 + [record-daemon.md](record-daemon.md) | 13 个文件全覆盖 |
| `tests/unit/`、`tests/integration/` | [构建与单测映射](../operations/dev-and-test.md) §2 | 24 个 test 文件全覆盖 |
| `scripts/`、`skills/`、`.github/workflows/`、`.githooks/` | [认知边界](../operations/boundary.md) §4 | 非 `src/` 目录零遗漏 |

## 4. 共变耦合与修改清单（Agent Co-Change Playbook）

- **新增源码文件**：必须加入本页 §2 全量表、`moduleTree` 与 [认知边界](../operations/boundary.md) §4；新增二级目录还要同步 §3。
- **新增组件页**：在 §1 登记 Archetype、入口符号与上下游，并在 [模块依赖矩阵](module-dep-matrix.md) 与根级 [INDEX](../INDEX.md) 的组件注册表同步。
- **删除/重命名文件**：先修正全部 `path:行号` 引用（含各页 YAML `source_paths`），再更新 `.wiki-meta.json` 的 `fileToDocs`，避免引用闭包出现未解析路径。
- **回归**：`pytest tests/unit/` 全量，命令见 [构建与单测映射](../operations/dev-and-test.md)。
