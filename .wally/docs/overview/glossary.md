---
kind: panorama
scope: glossary
status: draft
origin: generated
source_paths: [src/octop_browser/models.py, src/octop_browser/tool_interface.py, src/octop_browser/dom/builder.py, src/octop_browser/dom/refs.py, src/octop_browser/record/models.py, src/octop_browser/settings.py]
symbols: [ToolResult, ActionMetrics, TabInfo, _KNOWN_ACTIONS, DOMLevel, RefCache, RecordingManifest, SemanticStep, StepsDocument, OctopSettings]
upstream: [INDEX.md]
downstream: [business/domain-models/index.md, contracts/api-reference.md]
---

# 领域术语与代码符号精确映射表

本页消除「浏览器动作 / 录制回放 / 配置」需求话术与底层类名、字段名、枚举字面量之间的命名鸿沟。所有符号均可在标注的 `路径:行号` 回读核验；业务场景词表见 [业务能力总表](../business/index.md)，对外接口词表见 [入向接口契约全集](../contracts/api-reference.md)。

## 1. 自然语言术语 ↔ 源码符号映射字典

| 需求常见叫法（含别名） | 精确技术与业务定义 | 源码对应类 / 字段 / 枚举 | 权威定义位置 |
|---|---|---|---|
| 无状态工具调用 / `browser_tool` | 按 `profile` 名查找或懒创建 `BrowserSession` 并分发单个动作 | `browser_tool()`、`_registry`、`_KNOWN_ACTIONS` | `src/octop_browser/tool_interface.py:91`、`src/octop_browser/tool_interface.py:17`、`src/octop_browser/tool_interface.py:20` |
| 浏览器会话 / 登录态保持 | 一个 Chrome `--user-data-dir` 对应一条持久会话，跨进程可重连 | `BrowserSession`、`Profile`、`ProfileManager` | `src/octop_browser/session.py:174`、`src/octop_browser/profile.py:33` |
| 元素引用 / ref / 稳定节点号 | 形如 `btn_2`、`inp_search` 的短串，映射到 CDP `nodeId` | `RefCache`、`DOMBuilder._make_ref` | `src/octop_browser/dom/refs.py:6`、`src/octop_browser/dom/builder.py:124` |
| DOM 层级 / 省 token | `minimal/interactive/full/structured` 四档输出 | `DOMLevel` 字面量类型、`DOMBuilder.build` | `src/octop_browser/dom/builder.py:10`、`src/octop_browser/dom/builder.py:160` |
| 动作结果 / 工具返回 | 每个动作统一返回成功位、正文、错误、指标与旁路元数据 | `ToolResult`、`ActionMetrics`、`TabInfo` | `src/octop_browser/models.py:20`、`src/octop_browser/models.py:10`、`src/octop_browser/models.py:36` |
| 录制清单 / manifest | 一次录制的元数据：状态、时间、隐私策略、事件与步数 | `RecordingManifest`、`RecordingStatus` | `src/octop_browser/record/models.py:32`、`src/octop_browser/record/models.py:9` |
| 语义步骤 / steps | 由原始事件折叠出的可回放意图序列 | `SemanticStep`、`StepsDocument` | `src/octop_browser/record/models.py:69`、`src/octop_browser/record/models.py:80` |
| 配置 / 环境变量 | 进程级 `OctopSettings` 单例，每个字段用 `default_factory` 重读环境 | `OctopSettings`、`settings` | `src/octop_browser/settings.py:110`、`src/octop_browser/settings.py:185` |
| 启动模式 / 有头无头 | `auto/headed/headless` 三态解析为布尔 `--headless=new` | `BrowserMode`、`resolve_headless` | `src/octop_browser/mode.py:21`、`src/octop_browser/mode.py:55` |

## 2. 易混概念严格辨析

| 概念 A | 概念 B | 关键差异 | 对照锚点 |
|---|---|---|---|
| `browser_tool()`（无状态分发） | `BrowserSession`（有状态会话） | 前者按 `profile` 复用 `_registry` 且自带断线重连，后者持有单个 `_InternalCDPSession` 与逐会话指标累计；改签名必须同时核对两处 | `src/octop_browser/tool_interface.py:17` 对比 `src/octop_browser/session.py:189` |
| `RefCache`（ref→nodeId） | CDP `nodeId` 本身 | ref 是仓内字符串别名，导航后整体失效；`nodeId` 是 Chrome 侧数值，跨文档即变 | `src/octop_browser/dom/refs.py:23` 对比 `src/octop_browser/dom/builder.py:230` |
| `events.jsonl`（原始事件） | `steps.json`（语义步骤） | 前者逐条追加、含隐私脱敏后的全字段；后者经 `SemanticProcessor` 折叠、变量化并附 `verification` | `src/octop_browser/record/store.py:34` 对比 `src/octop_browser/record/semantic.py:338` |
| `status: draft`（文档状态） | `RecordingStatus`（录制状态） | 前者是 CodeWiki 生成物可信度标签；后者是 `recording/stopped/failed` 业务枚举，二者同名不同域 | `src/octop_browser/record/models.py:9` |
| `cdp_ws_url`（直连远端） | `launch_or_attach`（本地拉起或附着） | 配置前者时完全绕过 launcher 且禁止切标签；后者走端口探测与 `Popen` | `src/octop_browser/session.py:55` 对比 `src/octop_browser/cdp/launcher.py:497` |

## 3. 代码命名与枚举惯例

- **包内前缀**：`actions/`、`cdp/`、`dom/`、`record/` 为四个二级子包；`_` 前缀函数为模块内部实现（如 `_resolve_coords`、`_env_int`），不应被外部直接调用。见 `src/octop_browser/actions/interact.py:32`、`src/octop_browser/settings.py:100`。
- **动作字面量集合**：`_KNOWN_ACTIONS` 是 20 个动作的唯一白名单，CLI 通过 `_ACTION_ALIAS` 把连字符命令映射为下划线动作，MCP 通过 `_ACTION_MAP` 把 `browser_*` 工具名映射为动作。见 `src/octop_browser/tool_interface.py:20`、`src/octop_browser/cli.py:413`、`src/octop_browser/mcp_server.py:349`。
- **状态与策略字面量**：`InputPolicy` 取 `none/mask-sensitive/mask-all`，`ScreenshotPolicy` 取 `off/on-error/on-step-or-error/every-event`，`DOMLevel` 为四档。见 `src/octop_browser/record/models.py:10`、`src/octop_browser/record/models.py:11`、`src/octop_browser/dom/builder.py:10`。
- **CDP 字典 Key 大小写**：出向 `params` 使用驼峰（`deviceScaleFactor`、`returnByValue`、`captureBeyondViewport`），返回用 `result`/`error` 包裹，禁止臆造 snake_case 键。见 `src/octop_browser/session.py:86`、`src/octop_browser/actions/capture.py:125`。
- **隐私占位符**：脱敏值统一写为 `{{sensitive_value}}` 或 `{{redacted_value}}`，回放时由 `--input key=value` 注入。见 `src/octop_browser/record/privacy.py:79`。

## 4. 术语变更的共变耦合与修改清单

新增动作字面量时必须同步：`_KNOWN_ACTIONS` (`src/octop_browser/tool_interface.py:20`) → `BrowserSession` 方法 (`src/octop_browser/session.py:262`) → CLI `_ACTION_ALIAS` 与 `_action_kwargs` (`src/octop_browser/cli.py:413`) → MCP `_TOOLS` 与 `_ACTION_MAP` (`src/octop_browser/mcp_server.py:24`) → 本术语表与 [入向接口契约全集](../contracts/api-reference.md)；最后跑 `pytest tests/unit/test_tool_interface.py tests/unit/test_cli.py tests/unit/test_mcp_server.py`，验证命令见 [构建与单测映射](../operations/dev-and-test.md)。
