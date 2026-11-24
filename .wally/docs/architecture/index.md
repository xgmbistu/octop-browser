---
kind: component
scope: architecture-index
status: draft
origin: generated
source_paths: [src/octop_browser/__init__.py, src/octop_browser/settings.py, src/octop_browser/mode.py, src/octop_browser/models.py, src/octop_browser/tool_interface.py, src/octop_browser/cli.py, src/octop_browser/mcp_server.py, src/octop_browser/session.py, src/octop_browser/cdp/client.py, src/octop_browser/cdp/launcher.py, src/octop_browser/cdp/launch_prep.py, src/octop_browser/dom/builder.py, src/octop_browser/record/recorder.py, src/octop_browser/record/daemon.py, src/octop_browser/install.py, scripts/record_replay_smoke.py]
symbols: [browser_tool, main, _main, BrowserSession, CDPClient, DOMBuilder, RecordController, RecordDaemon, ensure_chromium]
upstream: [../INDEX.md, ../overview/system-architecture.md]
downstream: [module-dep-matrix.md, browser-engine.md, cdp-layer.md, record-worker.md]
---

# 组件技术架构总表

本仓按运行时框架模型分为 6 个 Tier 1/2 组件，其余辅助模块、脚本与资产统一在 Tier 3 归档。下方对账表覆盖全部顶层与二级源码目录，确保未映射目录为 0。

## 1. 全量核心组件矩阵

| 组件标识 | 框架模型 | 源码路径 | 核心入口符号（`路径:行号`） | 技术能力与业务边界 | 直接上游 | 直接下游 | 详情 |
|---|---|---|---|---|---|---|---|
| `api-and-mcp` | `API Service` | `src/octop_browser/tool_interface.py`、`src/octop_browser/mcp_server.py` | `browser_tool` (`src/octop_browser/tool_interface.py:91`)、`call_tool` (`src/octop_browser/mcp_server.py:392`) | 动作白名单、profile 会话注册表、25 个 MCP Tool、断链一次重连 | CLI、MCP 客户端 | `browser-engine`、`record-worker` | [`api-and-mcp.md`](api-and-mcp.md) |
| `cli` | `UI & CLI` | `src/octop_browser/cli.py`、`skills/` | `main` (`src/octop_browser/cli.py:631`)、`_build_parser` (`:96`) | 24 顶层命令、10 个 record 子命令、replay run、退出码语义 | 用户终端 / Agent Skill | `api-and-mcp`、`install-bootstrap`、`record-worker` | [`cli.md`](cli.md) |
| `browser-engine` | `Core Engine` | `src/octop_browser/session.py`、`actions/`、`dom/`、`hooks.py`、`models.py` | `BrowserSession.create` (`src/octop_browser/session.py:199`)、`DOMBuilder.build` (`src/octop_browser/dom/builder.py:160`) | 19 个动作、hook 洋葱链、四档 DOM、稳定 ref、指标累计 | `api-and-mcp` | `cdp-layer` | [`browser-engine.md`](browser-engine.md) |
| `cdp-layer` | `Data & Adapter` | `src/octop_browser/cdp/`、`profile.py`、`idle.py` | `CDPClient.send` (`src/octop_browser/cdp/client.py:75`)、`launch_or_attach` (`src/octop_browser/cdp/launcher.py:497`) | WebSocket 帧协议、进程启动/重连/终止、profile 与端口、空闲回收 | `browser-engine`、`record-worker` | Chrome / CDP | [`cdp-layer.md`](cdp-layer.md) |
| `record-worker` | `Async/Cron Worker` | `src/octop_browser/record/`（含 `injected/`） | `RecordController.start_in_process` (`src/octop_browser/record/recorder.py:350`)、`ReplayRunner.run` (`src/octop_browser/record/replay.py:25`) | daemon 长会话、注入 JS 事件、语义折叠、Skill 生成、目标重匹配回放 | CLI、MCP | `cdp-layer`、`api-and-mcp` | [`record-worker.md`](record-worker.md) |
| `install-bootstrap` | `Data & Adapter` | `src/octop_browser/install.py`、`playwright_download.py`、`linux_deps.py` | `ensure_chromium` (`src/octop_browser/install.py:280`)、`build_install_steps` (`src/octop_browser/linux_deps.py:220`) | pip 引导、CDN 竞速、系统库/字体安装、`--version` 验证门禁 | CLI、MCP | Playwright CDN / 包管理器 | [`install-bootstrap.md`](install-bootstrap.md) |

## 2. Tier 3 轻量模块与资产归档表（零遗漏兜底）

| 源码路径 | 核心导出符号 / 内容 | 调用方模块 | 具体职责 | 归属文档 |
|---|---|---|---|---|
| `src/octop_browser/__init__.py` | 13 个包根导出 | 外部调用方 | 公共 API 门面 | [`../contracts/api/python-api.md`](../contracts/api/python-api.md) (`src/octop_browser/__init__.py:15-28`) |
| `src/octop_browser/settings.py` | `OctopSettings`、`settings`、`state_dir` | 全仓 | 环境变量读取与状态目录解析 | [`../contracts/configuration.md`](../contracts/configuration.md) (`src/octop_browser/settings.py:109-185`) |
| `src/octop_browser/mode.py` | `BrowserMode`、`normalize_mode`、`resolve_headless` | `session.py`、`settings.py` | 三态启动模式解析 | [`../contracts/configuration.md`](../contracts/configuration.md) (`src/octop_browser/mode.py:26-75`) |
| `src/octop_browser/models.py` | `ToolResult`、`ActionMetrics`、`TabInfo` | 全部动作 | 统一返回模型 | [`../business/domain-models/index.md`](../business/domain-models/index.md) (`src/octop_browser/models.py:10-42`) |
| `src/octop_browser/hooks.py` | `HooksMixin.on`、`_fire` | `BrowserSession` | 四事件回调注册与异常隔离 | [`browser-engine.md`](browser-engine.md) (`src/octop_browser/hooks.py:19-53`) |
| `src/octop_browser/profile.py` | `Profile`、`ProfileManager` | `session.py`、`launcher.py`、`record/recorder.py` | 目录/端口分配与跨进程 target 黏性 | [`cdp-layer.md`](cdp-layer.md) (`src/octop_browser/profile.py:33-39,95-190`) |
| `src/octop_browser/idle.py` | `BrowserIdleController`、`idle_controller_for` | `_InternalCDPSession` | 本机 profile 空闲回收 | [`cdp-layer.md`](cdp-layer.md) (`src/octop_browser/idle.py:22-151`) |
| `src/octop_browser/actions/__init__.py`、`cdp/__init__.py`、`dom/__init__.py`、`py.typed` | 空包标记 / 类型标记 | 包导入 | 无逻辑 | [`browser-engine.md`](browser-engine.md) |
| `src/octop_browser/cdp/launch_prep.py` | `prepare_chrome_launch`、`ensure_profile_writable` | `cdp/launcher.py` | XDG 目录、SingletonLock、`/root` 重定位等启动前自愈 | [`cdp-layer.md`](cdp-layer.md) (`src/octop_browser/cdp/launch_prep.py:207-228`) |
| `src/octop_browser/record/daemon.py` | `RecordDaemon`、`send_request`、`ensure_daemon` | CLI、MCP | Unix socket 常驻录制守护进程 | [`record-worker.md`](record-worker.md) (`src/octop_browser/record/daemon.py:18-23`) |
| `src/octop_browser/record/injected/recorder.js` | `emit`、`describeElement`、`redactUrl` | 注入页面 | 浏览器事件采集与隐私脱敏 | [`record-worker.md`](record-worker.md) (`src/octop_browser/record/injected/recorder.js:55-73,201-248`) |
| `scripts/record_replay_smoke.py` | `main` (`scripts/record_replay_smoke.py:133`) | 开发者手工执行 | 真实 Chrome 录制回放冒烟 | [`../operations/dev-and-test.md`](../operations/dev-and-test.md) |
| `tests/unit/`、`tests/integration/` | 24 个单测文件 + 2 个集成测试 | CI / 开发者 | 回归验证 | [`../operations/dev-and-test.md`](../operations/dev-and-test.md) |
| `skills/octop-browser/SKILL.md`、`skills/octop-browser-zh/SKILL.md` | Agent Skill 资产 | 外部 Agent | 固化安全使用规约 | [`cli.md`](cli.md) (`skills/octop-browser/SKILL.md:13-24`) |
| `.github/workflows/`、`dependabot.yml` | CI / 发布 / 安全扫描 | GitHub Actions | PR 质量门禁与发布 | [`../operations/dev-and-test.md`](../operations/dev-and-test.md) (`.github/workflows/ci.yml:1-38`) |
| `.githooks/pre-commit` | `make all` 提交门禁 | git | 格式化后重新暂存 | [`../operations/dev-and-test.md`](../operations/dev-and-test.md) (`.githooks/pre-commit:14-37`) |
| `assets/images/banner.jpeg`、`README*.md`、`CHANGELOG.md`、`CONTRIBUTING.md`、`LICENSE`、`SECURITY.md` | 文档与静态资产 | 人 / 仓库平台 | 非运行时行为，见 [`../operations/boundary.md`](../operations/boundary.md) | [`../operations/boundary.md`](../operations/boundary.md) |

## 3. 源码目录零遗漏对账

| 顶层/二级源码目录 | 是否在组件表或 Tier 3 表登记 | 关联文档 |
|---|---|---|
| `src/octop_browser/actions/` | 是 | [`browser-engine.md`](browser-engine.md) |
| `src/octop_browser/cdp/` | 是 | [`cdp-layer.md`](cdp-layer.md) |
| `src/octop_browser/dom/` | 是 | [`browser-engine.md`](browser-engine.md) |
| `src/octop_browser/record/` | 是 | [`record-worker.md`](record-worker.md) |
| `src/octop_browser/record/injected/` | 是 | [`record-worker.md`](record-worker.md)、[`../operations/boundary.md`](../operations/boundary.md) |
| `tests/unit/` | 是 | [`../operations/dev-and-test.md`](../operations/dev-and-test.md) |
| `tests/integration/` | 是 | [`../operations/dev-and-test.md`](../operations/dev-and-test.md) |
| `scripts/` | 是 | [`../operations/dev-and-test.md`](../operations/dev-and-test.md) |
| `skills/` | 是 | [`cli.md`](cli.md) |
| `.github/workflows/` | 是 | [`../operations/dev-and-test.md`](../operations/dev-and-test.md) |
| `.githooks/` | 是 | [`../operations/dev-and-test.md`](../operations/dev-and-test.md) |
| `assets/` | 是（非源码资产） | [`../operations/boundary.md`](../operations/boundary.md) |

## 4. 共变耦合与修改清单

- 新增源码目录：必须在本页 Tier 1/2 或 Tier 3 表登记一行，并在 [`module-dep-matrix.md`](module-dep-matrix.md) 补依赖边。
- 改组件边界：同步 [`../overview/system-architecture.md`](../overview/system-architecture.md) 的分层拓扑与 [`../INDEX.md`](../INDEX.md) 的组件注册表。
- 改包根导出：同步 [`../contracts/api/python-api.md`](../contracts/api/python-api.md) 与 `src/octop_browser/__init__.py:15-28`。
