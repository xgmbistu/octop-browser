---
kind: component
scope: mcp-server
status: draft
origin: generated
source_paths: [src/octop_browser/mcp_server.py, src/octop_browser/tool_interface.py, src/octop_browser/models.py]
symbols: [app, _TOOLS, _ACTION_MAP, list_tools, call_tool, _handle_install_browser, _main, browser_tool, ToolResult]
upstream: [contracts/api-reference.md, INDEX.md]
downstream: [integrations/index.md, architecture/browser-session-engine.md]
---

# MCP 服务与无状态工具接入组件（API / 协议接入）

`mcp_server.py` 用 `mcp.server.Server`（`app`，`src/octop_browser/mcp_server.py:22`）在 stdio 上注册 25 个 `Tool`，把每个 MCP 工具名映射到 `browser_tool` 动作或录制回放控制器；`tool_interface.py` 的 `browser_tool` 以 `profile` 为键维持会话注册表并统一返回 `ToolResult`。执行模型为协程直出，无鉴权层，凭据一律由外部环境注入。

## 1. 请求处理洋葱链（Middleware & Dispatch Call Tree）

```text
MCP Client -> stdio_server / SSE 双传输 -> app.call_tool() (src/octop_browser/mcp_server.py:391)
  ├─ [1. name 路由] install_browser -> _handle_install_browser() (src/octop_browser/mcp_server.py:372) -> 聚合 InstallEvent 日志
  ├─ [2. name 路由] browser_record_* / browser_replay_run -> RecordController / ReplayRunner / RecordingStore (src/octop_browser/mcp_server.py:395)
  ├─ [3. 映射] _ACTION_MAP.get(name) (src/octop_browser/mcp_server.py:349) -> None 则返回 "Unknown tool: {name}" (src/octop_browser/mcp_server.py:461)
  ├─ [4. 特例] browser_open -> browser_tool(action="list_tabs", urls=..., mode=...) (src/octop_browser/mcp_server.py:464)
  ├─ [5. 执行] browser_tool(action, **arguments) (src/octop_browser/mcp_server.py:475) -> ToolResult
  └─ [6. 包络] success 取 content 文本，失败置 "ERROR: {error}" (src/octop_browser/mcp_server.py:477) -> TextContent(type="text", text=...)
```

## 2. 工具分组与并发执行模型表

| 工具组 | 工具数 | 分发目标 | 执行模式 | 结果包络 | 下游模块 |
|---|---|---|---|---|---|
| `browser_*` 浏览器动作 | 15 | `_ACTION_MAP` → `browser_tool` | 同步协程直出（受 `CDPClient` 超时控制） | `TextContent.text` 取 `ToolResult.content` | [会话引擎](browser-session-engine.md) |
| `browser_open` | 1 | `browser_tool(list_tabs, urls=...)` | 首次调用按 `urls` 开多标签 | 同上 | [会话引擎](browser-session-engine.md) |
| `browser_record_*` 与 `browser_replay_run` | 9 | `RecordController` / `ReplayRunner` / `RecordingStore` | 同步协程或 `ensure_daemon` 拉起子进程 | `str(data)` 字典文本 | [录制守护](record-daemon.md) |
| `install_browser` | 1 | `install_chromium_stream()` 异步生成器 | 逐条收集 `InstallEvent` 后汇总 | `OK` 或 `FAILED` 加日志 | [Playwright 安装器](../integrations/downstream/playwright-installer.md) |

25 个工具的逐项 `inputSchema` 全量下沉至 [MCP 工具契约](../contracts/api/mcp-tools.md)，响应与错误字典见 [错误码字典](../contracts/error-codes.md)。`_TOOLS` 直接由 `list_tools` 原样返回（`src/octop_browser/mcp_server.py:367`），无运行时过滤。

## 3. 核心源码文件与符号表

| 源码文件 | 核心符号（`行号`） | 职责边界 |
|---|---|---|
| `src/octop_browser/mcp_server.py` | `app` (`:22`)、`_TOOLS` (`:24`)、`_ACTION_MAP` (`:349`)、`list_tools` (`:367`)、`call_tool` (`:391`)、`_main` (`:482`) | 工具注册、名到动作映射、stdio/SSE 双传输启动 |
| `src/octop_browser/tool_interface.py` | `_registry` (`:17`)、`_KNOWN_ACTIONS` (`:20`)、`browser_tool` (`:91`)、`_error_result` (`:46`) | 按 profile 懒创建或复用会话、`getattr` 动态分发、断线自动重连 |
| `src/octop_browser/models.py` | `ToolResult` (`:20`)、`ActionMetrics` (`:10`) | 统一成功位、正文、错误、指标与 `metadata` 旁路 |

`browser_tool` 的重连铁律：仅当异常文本含 `not connected` 或 `connection lost` 时（`src/octop_browser/tool_interface.py:83`）才 `_drop_session` 并重建会话重试一次（`:186`），其余异常直接包成 `success=False`（`:211`），避免掩盖真实参数错误。

## 4. 上下游调用关系

- **上游调用方**：MCP-capable Agent（stdio）；设置 `MCP_PORT` 时改由 uvicorn/starlette 暴露 `GET /sse` 与 `POST /messages/`（`src/octop_browser/mcp_server.py:515`），详见 [部署与运行时](../operations/deployment-and-runtime.md)。
- **下游被调模块**：仓内 [会话引擎](browser-session-engine.md) 与 [录制守护](record-daemon.md)；外部协议边界见 [上下游集成总览](../integrations/index.md) 与 [Chrome CDP 契约](../integrations/downstream/chrome-cdp.md)。
- **工具入参不含环境键**：首个 `inputSchema` 仅声明 `url` 与 `profile`（`src/octop_browser/mcp_server.py:28`），`OctopSettings` 的 `BROWSER_USE_*` 由客户端配置 `mcpServers.<name>.env` 注入，禁止加入工具 schema。

## 5. 共变耦合与新增接口清单（Agent Co-Change Playbook）

1. 在 `_TOOLS` 追加 `Tool(...)` 并写完整 `inputSchema`：`src/octop_browser/mcp_server.py:24`。
2. 若属于浏览器动作，同步 `_ACTION_MAP` (`src/octop_browser/mcp_server.py:349`) 与 `_KNOWN_ACTIONS` (`src/octop_browser/tool_interface.py:20`)，并保证 `BrowserSession` 存在同名方法 (`src/octop_browser/session.py:262`)。
3. 在 `call_tool` 增加 `name` 分支或走通用映射：`src/octop_browser/mcp_server.py:391`。
4. 更新 [入向接口契约全集](../contracts/api-reference.md)、[MCP 工具契约](../contracts/api/mcp-tools.md) 与 [术语表](../overview/glossary.md)。
5. 跑 `pytest tests/unit/test_mcp_server.py tests/unit/test_tool_interface.py`，命令对照 [构建与单测映射](../operations/dev-and-test.md)。
