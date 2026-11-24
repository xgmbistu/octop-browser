# octop-browser · Agent 知识库总路由表（INDEX）

> **Agent 读取规程（必读）**：
> 1. **禁止一次性全量读取 `.wally/docs/`**。先查下方「任务意图路由表」或「源码路径反向索引」，只打开命中的 1–3 篇目标文档（可用 `Read(limit=15)` 先看顶部 YAML 头确认 `source_paths`、`symbols` 与 `status`）。
> 2. **弱命中与草稿核验纪律**：标记 `status: draft` 的文档为源码提取草稿；从文档拿到 `路径:行号`（`符号名`）、上下游字典结构与「共变耦合清单」后，执行修改前必须调用 `Read(path, offset, limit)` 复核源码字面实现（近邻词线索不等于原词覆盖）。
> 3. **人工精修保护**：标记 `origin: human` 或 `status: verified` 的页面为人工确认权威结论，后续重跑知识库严禁覆盖。基准提交：`chore/wally-init-20261124-c85` @ `1f4a548c6cbd63902c253ea5a96acec54fd92dec`。

**定性**：本仓是 Python 3.11+ 的 Agent 友好浏览器自动化库，直接通过 CDP WebSocket 驱动 Chromium（无 Playwright 运行时），对外提供 `browser_tool()`、25 个 MCP Tool、24 个 CLI 顶层命令以及录制/回放与 Skill 生成；核心契约是「profile → 持久 CDP 会话 → `ToolResult`」，所有状态落在用户态 profile 与录制目录，无服务端。

---

## 1. 任务意图最短路由表（Agent Intent Router）

| Agent 当前待办任务类型 | 按序必读文档（1 → 2 → 3） |
|---|---|
| **新增/修改浏览器动作或 action 参数** | [Python API 契约](contracts/api/python-api.md) → [浏览器引擎组件](architecture/browser-engine.md) → [入向接口全集](contracts/api-reference.md) |
| **新增/修改 MCP Tool 或 CLI 子命令** | [MCP Tools Schema](contracts/api/mcp-tools.md) / [CLI 命令 Schema](contracts/api/cli-commands.md) → [API 与 MCP 分发组件](architecture/api-and-mcp.md) → [CLI 组件](architecture/cli.md) |
| **改元素定位、DOM 输出或 ref 行为** | [浏览器引擎组件](architecture/browser-engine.md) → [Chrome CDP 出向契约](integrations/downstream/chrome-cdp.md) → [术语与符号映射](overview/glossary.md) |
| **改 Chrome 启动、端口、profile 或登录态** | [CDP 传输与进程底座](architecture/cdp-layer.md) → [部署与运行时目录契约](operations/deployment-and-runtime.md) → [高危雷区](operations/pitfalls-and-adr.md) |
| **改录制、脱敏、语义折叠或回放** | [录制回放 Worker](architecture/record-worker.md) → [WF-02 流程](business/wf-record-replay.md) → [领域与数据模型](business/domain-models/index.md) |
| **修改浏览器安装引导 / CDN / 系统库** | [安装引导组件](architecture/install-bootstrap.md) → [WF-03 流程](business/wf-chromium-bootstrap.md) → [CDN 出向契约](integrations/downstream/playwright-cdn.md) |
| **定位报错、异常码或降级原因** | [错误码字典](contracts/error-codes.md) → [排障 Runbook](operations/runbook-and-observability.md) → [主干调用链全景](overview/callchain-panorama.md) |
| **查环境变量、配置优先级或默认值** | [配置全集](contracts/configuration.md) → [领域与数据模型](business/domain-models/index.md) → [认知边界](operations/boundary.md) |
| **跨模块重构 / 评估联动修改与跑单测** | [模块依赖矩阵](architecture/module-dep-matrix.md) → [高危雷区与历史陷阱](operations/pitfalls-and-adr.md) → [构建与单测映射](operations/dev-and-test.md) |
| **做全系统认知或新能力规划** | [系统技术架构](overview/system-architecture.md) → [业务架构全景](overview/business-architecture.md) → [主干调用链全景](overview/callchain-panorama.md) |

---

## 2. 源码路径 → 文档反向索引表

| 仓库源码路径（前缀或关键文件） | 架构模型 / 角色 | 首选关联文档 | 关联上下游/业务文档 |
|---|---|---|---|
| `src/octop_browser/tool_interface.py` | API Service | [API 与 MCP 分发](architecture/api-and-mcp.md) | [字段映射](integrations/topology-and-mapping.md)、[WF-01](business/wf-browser-action.md) |
| `src/octop_browser/mcp_server.py` | API Service (MCP) | [API 与 MCP 分发](architecture/api-and-mcp.md) | [MCP Tools Schema](contracts/api/mcp-tools.md) |
| `src/octop_browser/cli.py` | UI & CLI | [CLI 组件](architecture/cli.md) | [CLI 命令 Schema](contracts/api/cli-commands.md) |
| `src/octop_browser/session.py` | Core Engine | [浏览器引擎](architecture/browser-engine.md) | [Python API](contracts/api/python-api.md)、[Chrome CDP 契约](integrations/downstream/chrome-cdp.md) |
| `src/octop_browser/actions/` | Action 层 | [浏览器引擎](architecture/browser-engine.md) | [Chrome CDP 契约](integrations/downstream/chrome-cdp.md) |
| `src/octop_browser/dom/` | DOM / ref 引擎 | [浏览器引擎](architecture/browser-engine.md) | [术语表](overview/glossary.md)、[目标匹配雷区](operations/pitfalls-and-adr.md) |
| `src/octop_browser/cdp/` | Data & Adapter | [CDP 传输与进程底座](architecture/cdp-layer.md) | [Chrome CDP 出向契约](integrations/downstream/chrome-cdp.md) |
| `src/octop_browser/profile.py`、`idle.py` | Profile / 空闲回收 | [CDP 传输与进程底座](architecture/cdp-layer.md) | [运行时目录契约](operations/deployment-and-runtime.md) |
| `src/octop_browser/record/`（含 `injected/`） | Async Worker | [录制回放 Worker](architecture/record-worker.md) | [WF-02](business/wf-record-replay.md)、[数据模型](business/domain-models/index.md) |
| `src/octop_browser/install.py`、`playwright_download.py`、`linux_deps.py` | Install Bootstrap | [安装引导组件](architecture/install-bootstrap.md) | [WF-03](business/wf-chromium-bootstrap.md)、[CDN 出向契约](integrations/downstream/playwright-cdn.md) |
| `src/octop_browser/settings.py`、`mode.py`、`models.py` | 配置 / 模型 | [配置全集](contracts/configuration.md) | [数据模型](business/domain-models/index.md)、[术语表](overview/glossary.md) |
| `tests/`、`scripts/record_replay_smoke.py` | 验证资产 | [构建与单测映射](operations/dev-and-test.md) | [排障 Runbook](operations/runbook-and-observability.md) |
| `skills/`、`.github/`、`.githooks/` | Agent / CI 资产 | [CLI 组件](architecture/cli.md) | [构建与单测映射](operations/dev-and-test.md)、[认知边界](operations/boundary.md) |
| `assets/`、`README*.md`、`AGENTS.md.bk.*` | 非源码资产 | [认知边界](operations/boundary.md) | — |

---

## 3. 模块技术能力清单（Component Registry）

| 组件标识 | 框架模型 | 核心源码路径 | 核心入口符号（`路径:行号`） | 上游调用方 | 下游依赖 | 文档 |
|---|---|---|---|---|---|---|
| `api-and-mcp` | `API Service` | `tool_interface.py`, `mcp_server.py` | `browser_tool` (`src/octop_browser/tool_interface.py:91`), `call_tool` (`src/octop_browser/mcp_server.py:392`) | CLI / MCP 客户端 | `browser-engine`, `record-worker` | [查看](architecture/api-and-mcp.md) |
| `cli` | `UI & CLI` | `cli.py`, `skills/` | `main` (`src/octop_browser/cli.py:631`) | 用户终端 / Agent Skill | `api-and-mcp`, `install-bootstrap` | [查看](architecture/cli.md) |
| `browser-engine` | `Core Engine` | `session.py`, `actions/`, `dom/`, `hooks.py`, `models.py` | `BrowserSession.create` (`src/octop_browser/session.py:199`), `DOMBuilder.build` (`src/octop_browser/dom/builder.py:160`) | `api-and-mcp` | `cdp-layer` | [查看](architecture/browser-engine.md) |
| `cdp-layer` | `Data & Adapter` | `cdp/`, `profile.py`, `idle.py` | `CDPClient.send` (`src/octop_browser/cdp/client.py:75`), `launch_or_attach` (`src/octop_browser/cdp/launcher.py:497`) | `browser-engine`, `record-worker` | Chrome CDP | [查看](architecture/cdp-layer.md) |
| `record-worker` | `Async/Cron Worker` | `record/` | `RecordController.start_in_process` (`src/octop_browser/record/recorder.py:350`), `ReplayRunner.run` (`src/octop_browser/record/replay.py:25`) | CLI / MCP | `cdp-layer`, `api-and-mcp` | [查看](architecture/record-worker.md) |
| `install-bootstrap` | `Data & Adapter` | `install.py`, `playwright_download.py`, `linux_deps.py` | `ensure_chromium` (`src/octop_browser/install.py:280`) | CLI / MCP | Playwright CDN / 包管理器 | [查看](architecture/install-bootstrap.md) |

---

## 4. 业务流程与下游依赖速查

- **全景认知**：[系统技术架构](overview/system-architecture.md) · [业务架构全景](overview/business-architecture.md) · [主干调用链全景](overview/callchain-panorama.md) · [领域术语与符号映射](overview/glossary.md)
- **架构与依赖**：[组件技术架构总表](architecture/index.md) · [模块依赖矩阵](architecture/module-dep-matrix.md)
- **上下游与契约**：[上下游集成总览](integrations/index.md) · [参数组装映射](integrations/topology-and-mapping.md) · [Chrome CDP 出向契约](integrations/downstream/chrome-cdp.md) · [CDN 出向契约](integrations/downstream/playwright-cdn.md)
- **业务与数据**：[业务流程总表](business/index.md) · [WF-01 工具调用](business/wf-browser-action.md) · [WF-02 录制回放](business/wf-record-replay.md) · [WF-03 安装验证](business/wf-chromium-bootstrap.md) · [核心数据模型](business/domain-models/index.md)
- **接口与规则**：[入向接口全集](contracts/api-reference.md) · [错误码字典](contracts/error-codes.md) · [配置全集](contracts/configuration.md)
- **验证、雷区与边界**：[构建与单测映射](operations/dev-and-test.md) · [部署与运行时](operations/deployment-and-runtime.md) · [排障 Runbook](operations/runbook-and-observability.md) · [高危雷区与历史陷阱](operations/pitfalls-and-adr.md) · [认知边界声明](operations/boundary.md)
