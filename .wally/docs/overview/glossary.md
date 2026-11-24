---
kind: panorama
scope: glossary
status: draft
origin: generated
source_paths: [src/octop_browser/models.py, src/octop_browser/dom/builder.py, src/octop_browser/dom/refs.py, src/octop_browser/record/models.py, src/octop_browser/mode.py, src/octop_browser/settings.py]
symbols: [ToolResult, ActionMetrics, TabInfo, DOMLevel, RefCache, RecordingManifest, StepsDocument, SemanticStep, BrowserMode, OctopSettings]
upstream: [../INDEX.md]
downstream: [../business/domain-models/index.md, ../architecture/browser-engine.md, ../contracts/configuration.md]
---

# 领域术语与代码符号精确映射表

本表把需求话术、CLI 文案与底层符号对齐，供 Agent 把自然语言请求翻译为可直读的源码锚点。所有术语均来自本仓源码字面，未出现的能力不做推断。

## 1. 自然语言术语 ↔ 源码符号映射字典

| 需求/业务常见叫法 | 精确技术与业务定义 | 源码对应类 / 字段 / 枚举 | 权威定义位置（`路径:行号`） |
|---|---|---|---|
| 工具结果 / 返回值 | 所有会话方法与 `browser_tool()` 的统一包络，`content` 为短文本或字典，附加 `metadata` 侧信道 | `ToolResult` (`success`, `content`, `error`, `metrics`, `metadata`) | `src/octop_browser/models.py:20-33` |
| 指标 / token 统计 | 单次动作的耗时、扫描节点数、估算 token、截图 KB | `ActionMetrics` (`duration_ms`, `dom_nodes_scanned`, `estimated_tokens`, `screenshot_size_kb`) | `src/octop_browser/models.py:10-17` |
| 标签页信息 | CDP `page` target 的展示模型 | `TabInfo` (`tab_id`, `url`, `title`, `active`) | `src/octop_browser/models.py:36-42` |
| DOM 层级 / 四档快照 | 从同一 CDP DOM 树产出的四种视图 | `DOMLevel = minimal \| interactive \| full \| structured` | `src/octop_browser/dom/builder.py:10` |
| 元素引用 / ref | 稳定短引用到 CDP `nodeId` 的映射，`btn_2`、`inp_search` 这类前缀+序号 | `RefCache.store / lookup / invalidate` | `src/octop_browser/dom/refs.py:6-29` |
| 录制清单 / 元数据 | 一次录制的身份、状态、隐私策略与事件计数 | `RecordingManifest` (`recordingId`, `status`, `privacy`, `stats`) | `src/octop_browser/record/models.py:32-43` |
| 语义步骤 | 从原始事件折叠出的可重放意图，不是坐标或瞬时 ref | `SemanticStep` (`id`, `kind`, `target`, `value`, `expect`) | `src/octop_browser/record/models.py:69-77` |
| 步骤文档 | 录制的重放脚本整体结构 | `StepsDocument` (`startUrl`, `inputs`, `steps`, `verification`) | `src/octop_browser/record/models.py:80-88` |
| 脱敏策略 | 输入、URL query、截图三条独立策略 | `PrivacySettings` (`input_policy`, `url_query_policy`, `screenshot_policy`) | `src/octop_browser/record/models.py:14-17` |
| 启动模式 | 有头/无头/自动三态 | `BrowserMode = Literal["auto", "headed", "headless"]` | `src/octop_browser/mode.py:21` |
| 配置对象 | 每次实例化都重读环境变量的运行时配置 | `OctopSettings` (`dataclass` + `field(default_factory=...)`) | `src/octop_browser/settings.py:109-180` |
| 状态目录 | 配置文件、录制、截图的统一根，兼容旧目录名 | `state_dir()` → `.octop-browser` / `.harness-browser` | `src/octop_browser/settings.py:74-92` |

## 2. 易混概念严格辨析

| 概念 A | 概念 B | 关键差异与混用后果 | 对照源码锚点 |
|---|---|---|---|
| `RefCache` 的 ref（`btn_1`） | CDP `nodeId` | ref 是本仓发给 Agent 的短字符串，nodeId 是浏览器内部整数；导航后 ref 必须整体失效，直接缓存 nodeId 会指向已销毁节点 | `src/octop_browser/dom/refs.py:15-25` vs `src/octop_browser/dom/builder.py:229-230` |
| `dom_tree(level="structured")` | `dom_tree(level="full")` | structured 输出 JSON 且只含交互元素，供程序解析；full 输出缩进文本且含结构标签，供人阅读。回放目标匹配只吃 structured | `src/octop_browser/dom/builder.py:359-399` vs `src/octop_browser/dom/builder.py:337-357` |
| `browser_tool()` 的 `profile` | `BrowserSession.create(profile=...)` | 前者按名字复用进程内 `_registry` 会话；后者每次显式创建新会话。两者共用同一套 ProfileManager 端口/目录分配 | `src/octop_browser/tool_interface.py:17,63-68` vs `src/octop_browser/session.py:198-250` |
| `close_session` 默认行为 | `close_session(kill=True)` | 默认只断开 CDP、Chrome 仍驻留以便后续命令重连；`kill=True` 终止本地 Chrome 并释放端口 | `src/octop_browser/tool_interface.py:125-161` |
| 录制事件 `kind=input` | 语义步骤 `kind=fill` | input 是逐 300ms 去抖的浏览器原始事件；fill 是语义折叠后的变量化步骤，值已替换为 `{{name}}` | `src/octop_browser/record/injected/recorder.js:264-269` vs `src/octop_browser/record/semantic.py:614-624` |
| `RecordingManifest.status` | `ReplayRunner` 报告的 `status` | 前者是录制生命周期 `recording\|stopped\|failed`；后者是回放结论 `running\|passed\|failed` | `src/octop_browser/record/models.py:9` vs `src/octop_browser/record/replay.py:35-43` |
| `OctopSettings` 单例 `settings` | 新构建的 `OctopSettings()` | 单例在 import 时读一次环境；新实例逐个字段重新读环境，测试隔离依赖这一点 | `src/octop_browser/settings.py:183-185` |

## 3. 枚举与状态字面量集合

| 枚举名 | 允许字面量 | 定义位置 | 消费位置 |
|---|---|---|---|
| `DOMLevel` | `minimal` / `interactive` / `full` / `structured` | `src/octop_browser/dom/builder.py:10` | `src/octop_browser/dom/builder.py:176-184` |
| `BrowserMode` | `auto` / `headed` / `headless` | `src/octop_browser/mode.py:21-23` | `src/octop_browser/mode.py:55-75` |
| `RecordingStatus` | `recording` / `stopped` / `failed` | `src/octop_browser/record/models.py:9` | `src/octop_browser/record/recorder.py:110` |
| `InputPolicy` | `none` / `mask-sensitive` / `mask-all` | `src/octop_browser/record/models.py:10` | `src/octop_browser/record/privacy.py:27-81` |
| `ScreenshotPolicy` | `off` / `on-error` / `on-step-or-error` / `every-event` | `src/octop_browser/record/models.py:11` | `src/octop_browser/record/recorder.py:50-54` 中 CLI 固定传 `off` |
| 语义步骤 `kind` | `open` / `click` / `fill` / `select` / `set_checked` / `press` / `navigate` / `new_tab` / `scroll_to` | `src/octop_browser/record/semantic.py:396-593` | `src/octop_browser/record/replay.py:53-268` |
| 验证类型 | `url_contains` / `text_contains` / `selector_exists` / `title_contains` / `element_text_contains` / `input_value_equals` | `src/octop_browser/record/replay.py:341-415` | `src/octop_browser/record/semantic.py:665-669` |

## 4. 代码命名与前缀惯例

- **ref 前缀表**：`input→inp`、`button→btn`、`a→lnk`、`select→sel`、`textarea→txt`，其余取标签名前 3 字符；序号按前缀独立自增（`src/octop_browser/dom/builder.py:124-134`）。
- **状态目录双名兼容**：新名 `.octop-browser`、旧名 `.harness-browser`；profile target 与端口文件同样保留 `.harness-browser-*` 回退（`src/octop_browser/settings.py:74-92`、`src/octop_browser/profile.py:24-30`）。
- **录制 ID 格式**：`rec_` + `%Y%m%d_%H%M%S_` + 3 字节十六进制随机数（`src/octop_browser/record/recorder.py:43-44`）。
- **脱敏占位符**：敏感输入统一写 `{{sensitive_value}}`（`src/octop_browser/record/privacy.py:79`），长值/命中正则写 `{{redacted_value}}`（`src/octop_browser/record/injected/recorder.js:243-249`）。
- **内部绑定名**：每次录制随机 `__hbr_<hex>`，配合 nonce 校验防止误收其他页面事件（`src/octop_browser/record/recorder.py:72-73`、`src/octop_browser/record/recorder.py:273-274`）。

## 5. 共变耦合与修改清单

1. 新增对外返回字段：先改 `src/octop_browser/models.py:20-33`，再同步 `contracts/api-reference.md` 与所有断言 `ToolResult` 的单测。
2. 新增 DOM 输出档位：改 `src/octop_browser/dom/builder.py:160-184` 枚举分支 → CLI choices（`src/octop_browser/cli.py:179-183`）→ MCP schema（`src/octop_browser/mcp_server.py:43-47`）→ 本表。
3. 新增语义步骤类型：改 `src/octop_browser/record/semantic.py:396-593` → `src/octop_browser/record/replay.py:53-268` 分发 → `src/octop_browser/record/skill_generator.py:113-174` 文档生成 → `tests/unit/test_record_replay_semantic.py`。
4. 重命名环境变量：必须同时保留旧名读取回退，并更新 `contracts/configuration.md` 与 `tests/unit/conftest.py` 的隔离前缀。

## 6. 关联文档

- [核心数据模型](../business/domain-models/index.md) · [配置全集](../contracts/configuration.md) · [浏览器引擎组件](../architecture/browser-engine.md)
