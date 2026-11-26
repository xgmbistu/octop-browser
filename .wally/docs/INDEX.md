# octop-browser · Agent 知识库总路由表（INDEX）

> **Agent 读取规程（必读）**：
> 1. **禁止一次性全量读取 `.wally/docs/`**。先查「任务意图路由表」或「源码路径反向索引表」，只打开命中的 1–3 篇目标文档（可用 `Read(limit=15)` 先看顶部 YAML 头确认 `source_paths`、`symbols` 与 `status`）。
> 2. **弱命中与草稿核验纪律**：`status: draft` 的文档为源码提取草稿；从文档拿到 `路径:L起-L止`（`符号名`）、上下游字典结构与「共变耦合清单」后，执行修改前必须调用 `Read(path, offset, limit)` 复核源码字面实现（近邻词线索不等于原词覆盖）。
> 3. **人工精修保护**：`origin: human` 或 `status: verified` 的页面为人工确认权威结论，后续重跑知识库严禁覆盖。基准提交：`chore/wally-init-20261127-c114` @ `f56249214aa183648d6b684b6f39445fe438e52d`。
> 4. **语言与模式**：本套知识库锁定 `zh-CN`，Mode B 本地 `.wally/docs/` 模式，`workspaceMode = single-repo`；目录名、YAML 键名、源码符号与字典 Key 保持原样。

2 句高密度定性：`octop-browser` 是 Python 3.11+ 的 Agent-first 浏览器自动化库，以 `websockets` 手写 CDP 客户端直连真实 Chromium（不依赖 Playwright 运行时），对外暴露 Python API、CLI 与 MCP stdio/SSE 三种接口；核心输入输出契约为统一 `ToolResult` 包络、四档 token 友好 DOM 与稳定 `ref` 定位，并附带注入式录制、语义折叠与意图回放能力。

---

## 1. Agent 读取规程

| 步骤 | 动作 | 依据 |
|---|---|---|
| 1 | 按待办任务类型查第 2 节意图路由表，或按用户给出的源码路径查第 3 节反向索引 | 本页 |
| 2 | 打开命中的 1–3 篇文档，先读 YAML 头（`kind/scope/status/origin/source_paths/symbols/upstream/downstream`） | 各页顶部 |
| 3 | 依文档内 `路径:行号`（`符号名`）回读源码全文，确认字面实现 | [术语与符号映射](overview/glossary.md)、[认知边界](operations/boundary.md) |
| 4 | 修改代码后按页尾「共变耦合与修改清单」跑对应回归 | [构建与单测映射](operations/dev-and-test.md) |

## 2. 任务意图路由表（Agent Intent Router）

| Agent 当前待办任务类型 | 按序必读文档（1 → 2 → 3） |
|---|---|
| **上游加字段透传 / 组装给下游**（高频网关 / 编排需求） | [参数组装与字段映射](integrations/topology-and-mapping.md) → [Chrome CDP 契约](integrations/downstream/chrome-cdp.md) → [入向接口契约全集](contracts/api-reference.md) |
| **新增 / 修改本仓对外接口或命令** | [入向接口契约全集](contracts/api-reference.md) → [MCP 服务组件](architecture/mcp-server.md) + [CLI 组件](architecture/cli.md) → [错误码字典](contracts/error-codes.md) |
| **对接新下游接口 / 修改下游返回解析** | [上下游集成总览](integrations/index.md) → 对应 [下游契约页](integrations/downstream/chrome-cdp.md) → [错误码字典](contracts/error-codes.md) |
| **修改业务校验规则 / 状态流转逻辑** | [业务能力总表](business/index.md) → 对应 `business/wf-*.md` → [录制产物模型](business/domain-models/recording-artifacts.md) |
| **新增 / 修改定时任务或后台异步队列** | [录制守护组件](architecture/record-daemon.md) → [配置手册](contracts/configuration.md) → [排障 Runbook](operations/runbook-and-observability.md) |
| **定位报错 / 异常码 / 降级原因** | [错误码字典](contracts/error-codes.md) → [主干调用链全景](overview/callchain-panorama.md) → [排障 Runbook](operations/runbook-and-observability.md) |
| **跨模块重构 / 评估联动修改与跑单测** | [模块依赖矩阵](architecture/module-dep-matrix.md) → [高危雷区与历史陷阱](operations/pitfalls-and-adr.md) → [构建与单测映射](operations/dev-and-test.md) |
| **理解全局分层与启动装配** | [系统技术架构](overview/system-architecture.md) → [组件技术架构总表](architecture/index.md) → [业务架构全景](overview/business-architecture.md) |
| **排查部署产物、磁盘目录或外部黑盒** | [部署与运行时](operations/deployment-and-runtime.md) → [认知边界](operations/boundary.md) → [上下游集成总览](integrations/index.md) |
| **处理环境 / 配置 / 模式问题** | [配置手册](contracts/configuration.md) → [CDP 传输与存储](architecture/cdp-transport-and-storage.md) → [排障 Runbook](operations/runbook-and-observability.md) |

## 3. 源码路径反向索引表（Source-to-Doc Reverse Index）

> 当用户直接指定修改某个源码目录或文件时，由此表 O(1) 反查对应知识文档：

| 仓库源码路径（前缀或关键文件） | 架构模型 / 角色 | 首选关联文档 | 关联上下游 / 业务文档 |
|---|---|---|---|
| `src/octop_browser/cli.py` | `UI & CLI` | [CLI 组件](architecture/cli.md) | [CLI 动作契约](contracts/api/browser-actions.md)、[WF-02](business/wf-action-dispatch.md) |
| `src/octop_browser/mcp_server.py` | `API Service` | [MCP 服务组件](architecture/mcp-server.md) | [MCP 工具契约](contracts/api/mcp-tools.md)、[MCP 传输契约](integrations/downstream/mcp-transport.md) |
| `src/octop_browser/tool_interface.py` | `API Service` | [MCP 服务组件](architecture/mcp-server.md) | [WF-02](business/wf-action-dispatch.md)、[入向接口契约全集](contracts/api-reference.md) |
| `src/octop_browser/session.py` | `Core Engine` | [会话引擎](architecture/browser-session-engine.md) | [WF-01](business/wf-browser-session-lifecycle.md)、[WF-08](business/wf-tab-management.md) |
| `src/octop_browser/dom/`、`actions/` | `Core Engine` | [WF-03](business/wf-dom-ref-targeting.md) | [Chrome CDP 契约](integrations/downstream/chrome-cdp.md) |
| `src/octop_browser/cdp/client.py`、`launcher.py`、`launch_prep.py` | `Data & Adapter` | [CDP 传输与存储](architecture/cdp-transport-and-storage.md) | [Chromium 进程契约](integrations/downstream/chromium-process.md) |
| `src/octop_browser/profile.py`、`settings.py`、`mode.py`、`idle.py` | `Data & Adapter` | [CDP 传输与存储](architecture/cdp-transport-and-storage.md) | [配置手册](contracts/configuration.md) |
| `src/octop_browser/record/daemon.py` | `Async Worker` | [录制守护组件](architecture/record-daemon.md) | [录制守护 IPC](integrations/downstream/record-daemon-ipc.md) |
| `src/octop_browser/record/recorder.py`、`injected/recorder.js`、`privacy.py` | `Downstream Wrapper` | [WF-04](business/wf-record-capture.md) | [录制产物模型](business/domain-models/recording-artifacts.md) |
| `src/octop_browser/record/semantic.py`、`replay.py`、`matcher.py`、`skill_generator.py` | `Core Engine` | [WF-05](business/wf-semantic-steps.md)、[WF-06](business/wf-replay.md) | [录制回放契约](contracts/api/record-replay.md) |
| `src/octop_browser/record/store.py`、`models.py`、`settings.py` | `Data & Adapter` | [录制产物模型](business/domain-models/recording-artifacts.md) | [部署与运行时](operations/deployment-and-runtime.md) |
| `src/octop_browser/install.py`、`linux_deps.py`、`playwright_download.py` | `Async Worker` | [WF-07](business/wf-chromium-install.md) | [Playwright 安装器](integrations/downstream/playwright-installer.md)、[Linux 系统依赖](integrations/downstream/linux-system-deps.md) |
| `src/octop_browser/models.py`、`hooks.py`、`__init__.py` | `Value Object` | [工具结果与指标模型](business/domain-models/tool-result-and-metrics.md) | [术语表](overview/glossary.md) |
| `tests/`、`scripts/`、`.github/workflows/`、`.githooks/` | `Verification` | [构建与单测映射](operations/dev-and-test.md) | [认知边界](operations/boundary.md) |
| `Makefile`、`pyproject.toml`、`README.md` | `Build / Contract` | [构建与单测映射](operations/dev-and-test.md) | [配置手册](contracts/configuration.md) |

完整 40 文件归档（含空 `__init__.py` 与 `py.typed`）见 [组件技术架构总表](architecture/index.md) 第 2 节 Tier 3 表，未映射源码目录为 0。

## 4. 模块技术能力清单（Component Registry）

| 组件标识 | 框架模型（Archetype） | 核心源码路径 | 核心入口符号（`路径:行号`） | 上游调用方 | 下游依赖 | 文档 |
|---|---|---|---|---|---|---|
| `mcp-server` | `API` | `src/octop_browser/mcp_server.py` | `call_tool` (`:391`) | MCP Client | `browser_tool` | [查看](architecture/mcp-server.md) |
| `cli` | `UI-CLI` | `src/octop_browser/cli.py` | `main` (`:631`) | 终端用户 | `browser_tool` | [查看](architecture/cli.md) |
| `tool-interface` | `API` | `src/octop_browser/tool_interface.py` | `browser_tool` (`:91`) | CLI / MCP / 回放 | `BrowserSession` | [查看](architecture/mcp-server.md) |
| `browser-session-engine` | `Engine` | `src/octop_browser/session.py` | `BrowserSession` (`:174`) | `browser_tool` | `CDPClient` | [查看](architecture/browser-session-engine.md) |
| `cdp-transport-and-storage` | `DAO` | `src/octop_browser/cdp/`、`profile.py` | `CDPClient.send` (`cdp/client.py:75`) | 引擎层 | Chrome | [查看](architecture/cdp-transport-and-storage.md) |
| `record-daemon` | `Worker` | `src/octop_browser/record/daemon.py` | `dispatch` (`:39`) | CLI / MCP | Chrome / 磁盘 | [查看](architecture/record-daemon.md) |
| `installer` | `Worker` | `src/octop_browser/install.py` | `ensure_chromium` (`:280`) | CLI / MCP | Playwright CDN | [查看](business/wf-chromium-install.md) |

## 5. 业务流程与下游依赖速查

- **全景认知**：[系统技术架构](overview/system-architecture.md) · [业务架构全景](overview/business-architecture.md) · [主干调用链全景](overview/callchain-panorama.md) · [领域术语与符号映射](overview/glossary.md)
- **组件与依赖**：[组件技术架构总表](architecture/index.md) · [模块依赖矩阵](architecture/module-dep-matrix.md) · [上下游集成总览](integrations/index.md) · [参数组装与字段映射](integrations/topology-and-mapping.md)
- **下游契约（6 篇逐字典展开）**：[Chrome CDP](integrations/downstream/chrome-cdp.md) · [Chromium 进程](integrations/downstream/chromium-process.md) · [Playwright 安装器](integrations/downstream/playwright-installer.md) · [Linux 系统依赖](integrations/downstream/linux-system-deps.md) · [录制守护 IPC](integrations/downstream/record-daemon-ipc.md) · [MCP 传输](integrations/downstream/mcp-transport.md)
- **业务流程（8 篇 WF）**：[总表](business/index.md) · [WF-01 会话](business/wf-browser-session-lifecycle.md) · [WF-02 分发](business/wf-action-dispatch.md) · [WF-03 DOM ref](business/wf-dom-ref-targeting.md) · [WF-04 录制](business/wf-record-capture.md) · [WF-05 语义折叠](business/wf-semantic-steps.md) · [WF-06 回放](business/wf-replay.md) · [WF-07 安装](business/wf-chromium-install.md) · [WF-08 标签](business/wf-tab-management.md)
- **数据模型**：[总览](business/domain-models/index.md) · [工具结果与指标](business/domain-models/tool-result-and-metrics.md) · [录制产物](business/domain-models/recording-artifacts.md)
- **入向契约**：[全量接口总表](contracts/api-reference.md) · [浏览器动作与 CLI](contracts/api/browser-actions.md) · [MCP 工具](contracts/api/mcp-tools.md) · [录制回放与守护命令](contracts/api/record-replay.md) · [错误码字典](contracts/error-codes.md) · [配置手册](contracts/configuration.md)
- **验证、雷区与边界**：[构建与单测映射](operations/dev-and-test.md) · [部署与运行时](operations/deployment-and-runtime.md) · [排障 Runbook](operations/runbook-and-observability.md) · [高危雷区与历史陷阱](operations/pitfalls-and-adr.md) · [认知边界声明](operations/boundary.md)

## 6. 外部权威页与 SOP 文档（仅链接，不改写）

以下为 wally-init 生成的 SOP 专用 / 外部权威页，**不属于 codewiki 管理页**，不复制正文、不强加 8 键 YAML 头，也不计入 `.wiki-meta.json` 的 `pageOrder` / `pageCount`；排除理由见 [认知边界](operations/boundary.md) 第 5 节与 [部署与运行时](operations/deployment-and-runtime.md) 第 4 节：

| 外部页 | 用途 |
|---|---|
| [API 索引](apis/index.md)、[API 模板](apis/_template.md) | SOP API 索引与模板 |
| [开发环境](devops/env.md)、[测试环境部署](devops/test-env-deploy.md) | SOP 部署环境文档（deploy `readiness: pending`） |
| [集成测试](integration_test/integration_test.md)、[单元测试规范](unittest/unittest.md) | SOP 测试执行规范 |
| [数据库与 SQL](sqls/README.md) | SOP 数据库模板（本仓无 SQL） |

## 7. 基准快照与生成物状态

- **基准**：分支 `chore/wally-init-20261127-c114` @ `f56249214aa183648d6b684b6f39445fe438e52d`，源码工作树干净。
- **模式与语言**：`full` / `zh-CN` / `single-repo`；生成物 `generator = wally-codewiki`。
- **可信度**：全部 43 篇 codewiki 管理页均为 `status: draft`、`origin: generated`，无 `origin: human` 或 `status: verified` 页面被覆盖；`.wiki-meta.json` 记录 `pageOrder`、`fileToDocs`、`moduleTree` 与 G1–G5 核验结论。
- **最终门禁**：G1 路由头与元数据双射、G2 源码覆盖与双向字典契约、G3 引用闭包与事实锚定、G4 防截断防重复与语言一致性、G5 Mermaid 与 AST 真实性，全绿后方可收工。
