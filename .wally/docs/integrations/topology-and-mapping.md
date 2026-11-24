---
kind: mapping
scope: inbound-to-outbound-mapping
status: draft
origin: generated
source_paths: [src/octop_browser/cli.py, src/octop_browser/mcp_server.py, src/octop_browser/tool_interface.py, src/octop_browser/session.py, src/octop_browser/dom/builder.py, src/octop_browser/record/replay.py]
symbols: [_action_kwargs, call_tool, browser_tool, BrowserSession.click, BrowserSession.screenshot, DOMBuilder.build, ReplayRunner._resolve_value]
upstream: [../contracts/api-reference.md, index.md]
downstream: [downstream/chrome-cdp.md, ../business/wf-browser-action.md]
---

# 上下游参数组装与字段映射矩阵

本页追踪一个字段从 CLI/MCP 入参到 CDP 请求字典、再从 CDP 返回值回填到 `ToolResult` 的完整变形链。所有 Key 均为源码字面，字典骨架见 [`downstream/chrome-cdp.md`](downstream/chrome-cdp.md)，入向接口全集见 [`contracts/api-reference.md`](../contracts/api-reference.md)。

## 1. 上游入口 → 下游扇出编排顺序表

| 上游入口 | 主编排函数（`路径:行号`） | 按序调用的下游方法链 | 短路/聚合规则 |
|---|---|---|---|
| CLI `click --ref` | `_run_action` (`src/octop_browser/cli.py:514-534`) → `_action_kwargs` (`:426-450`) | `browser_tool("click")` (`src/octop_browser/tool_interface.py:91-212`) → `BrowserSession.click` → `interact.click` → `CDPClient.send` | ref 未命中抛 `CDPSessionError`，不继续发鼠标事件 |
| MCP `browser_click` | `call_tool` (`src/octop_browser/mcp_server.py:391-479`) | `_ACTION_MAP` → `browser_tool(action, **arguments)` | 失败时把 `ERROR: <error>` 写回 `TextContent` |
| CLI `screenshot --full-page` | `_action_kwargs` (`src/octop_browser/cli.py:437-443`) | `browser_tool("screenshot")` → `capture.screenshot` → `Page.getLayoutMetrics` → `Page.captureScreenshot` → 写盘 | `data` 为空直接返回失败，不写文件 |
| CLI `dom-tree --level structured` | `_action_kwargs` (`src/octop_browser/cli.py:435-436`) | `BrowserSession.dom_tree` → `DOM.getDocument` + `Runtime.evaluate` → `DOMBuilder.build` | 构建异常兜底空 ToolResult |
| `replay run --input k=v` | `_run_replay` (`src/octop_browser/cli.py:610-623`) → `ReplayRunner.run` (`src/octop_browser/record/replay.py:25-298`) | 每步 `browser_tool` 链；`{{key}}` 占位先由 `_resolve_value` (`:566-570`) 替换 | URL 命中风控跳转则 `skipped`，步骤失败整体 `break` |

## 2. 核心场景字段级映射矩阵

### 场景 A：交互类动作（click / type / fill / hover / select）

#### A.1 入参 → CDP 请求字典键

| 上游入参字段（类型） | 转换/校验/默认值注入 | 下游方法与 CDP 命令 | CDP 请求字典精确 Key | 组装锚点 |
|---|---|---|---|---|
| `--ref` (`str`) | `argparse` 三者互斥必填其一 | `interact._resolve_coords` → `DOM.getBoxModel` | `{"nodeId": <RefCache.lookup(ref)>}` | `src/octop_browser/actions/interact.py:41-46,21-29` |
| `--selector` (`str`) | 与 ref/x-y 互斥 | `DOM.getDocument {"depth":0}` → `DOM.querySelector` | `{"nodeId": root_id, "selector": selector}` | `src/octop_browser/actions/interact.py:47-57` |
| `--xy X Y` (`int,int`) | 拆成 `x`/`y` 两个 kwargs | `Input.dispatchMouseEvent` | `{"x","y"}` 直接透传 | `src/octop_browser/cli.py:449-450`、`src/octop_browser/actions/interact.py:58-59` |
| `text`/`value` (`str`) | type/fill 逐字符；fill 先发 Ctrl+A/Meta+A+Backspace | `Input.dispatchKeyEvent` | `{"type":"char","text": ch}` | `src/octop_browser/actions/interact.py:103-104,178-198` |
| `select.value` (`str`) | 包装成 JS 函数实参 | `Runtime.callFunctionOn` | `{"objectId","functionDeclaration","arguments":[{"value": value}],"returnByValue":true}` | `src/octop_browser/actions/interact.py:243-257` |

#### A.2 下游返回 → ToolResult 回填

| CDP 返回键路径 | 判空/兜底/转换 | 回填目标 | 解包锚点 |
|---|---|---|---|
| `DOM.getBoxModel.model.content` | 8 点数组，取 `(content[0]+content[4])/2` 算中心 | `click` 的 `x`,`y` | `src/octop_browser/actions/interact.py:21-29` |
| `DOM.querySelector.nodeId` | `0` 视为未匹配，抛 `Selector '...' matched no elements.` | 失败分支 | `src/octop_browser/actions/interact.py:53-55` |
| `Runtime.callFunctionOn.result.value` | 不读取，只以调用成功为准 | `content="Selected <value>"` | `src/octop_browser/actions/interact.py:249-272` |

### 场景 B：DOM 快照与 ref 生成

| 上游入参字段 | 转换逻辑 | 下游字典键 | 回填目标 | 锚点 |
|---|---|---|---|---|
| `--level` (`str`，四档) | `DOMBuilder.build()` 分支路由 | `DOM.getDocument {"depth": -1}`、`Runtime.evaluate {"expression": JSON.stringify({url,title}), "returnByValue": true}` | page url/title 写入输出首行 | `src/octop_browser/session.py:306-326` |
| CDP 节点 `attributes` 扁平数组 | `zip(attrs[::2], attrs[1::2])` 转字典 | 交互元素记录 `tag/type/role/label/placeholder/text` | interactive/full/structured 三档输出 | `src/octop_browser/dom/builder.py:66-68,228-258` |
| 元素标签 + 前缀计数 | `_make_ref()` 生成 `btn_2` 一类 ref | `RefCache.store(ref, nodeId)` | `structured` 输出的 `ref`、`node_id` | `src/octop_browser/dom/builder.py:124-134,359-393` |

### 场景 C：回放占位符解析

| 上游入参字段 | 转换逻辑 | 目标 | 锚点 |
|---|---|---|---|
| `--input sensitive_value=xxx` | CLI 按首个 `=` 切分合成 `inputs` 字典 | `ReplayRunner.run(inputs=...)` | `src/octop_browser/cli.py:610-618` |
| `{{name}}` 占位 | `value[2:-2].strip()` 取 key 后查 inputs，缺失回填空串 | `fill/select` 的 `text`/`value` | `src/octop_browser/record/replay.py:566-570` |
| `inputs["query"]` | 命中 baidu→`wd`、google/bing→`q`，用 `quote_plus` 重写 query | `navigate` 的 `url` | `src/octop_browser/record/replay.py:606-645` |

## 3. 通用字典拼装模式与共变清单

- **公共帧构造器**：`CDPClient.send()` 固定包裹 `{"id": int, "method": str, "params": dict}`（`src/octop_browser/cdp/client.py:89-93`）；所有业务封装只填 `method` 与 `params`。
- **公共返回包络**：所有动作最终返回 `ToolResult(success, content, error, metrics, metadata)`（`src/octop_browser/models.py:20-33`）；截图把 url/title/size 放 `metadata` 而不塞进 `content`（`src/octop_browser/actions/capture.py:205-228`）。
- **新增透传字段标准改动链**：
  1. 入向 Schema：CLI argparse（`src/octop_browser/cli.py:96-404`）与 MCP `inputSchema`（`src/octop_browser/mcp_server.py:24-347`）。
  2. 参数翻译：`_action_kwargs()`（`src/octop_browser/cli.py:426-499`）。
  3. 动作签名：`BrowserSession` 对应方法（`src/octop_browser/session.py:262-869`）。
  4. CDP 字典：对应 `actions/*.py` 封装方法（详见下游契约页）。
  5. 回显：更新 `ToolResult.metadata` 构造与 `contracts/api-reference.md` → 跑相关单测。

## 4. 关联文档与共变入口

- [入向接口全集](../contracts/api-reference.md) · [集成总览](index.md) · [Chrome CDP 出向契约](downstream/chrome-cdp.md)
