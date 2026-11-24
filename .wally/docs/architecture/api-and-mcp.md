---
kind: component
scope: inbound-api-and-mcp-dispatch
status: draft
origin: generated
source_paths: [src/octop_browser/tool_interface.py, src/octop_browser/mcp_server.py]
symbols: [browser_tool, _KNOWN_ACTIONS, _get_or_create_session, _drop_session, _is_disconnected_error, _TOOLS, _ACTION_MAP, list_tools, call_tool, _main]
upstream: [../INDEX.md, cli.md]
downstream: [browser-engine.md, record-worker.md, ../integrations/topology-and-mapping.md, ../contracts/api/mcp-tools.md]
---

# 入向 API 与 MCP 分发组件

两种入向协议共用同一个无状态入口：Python 侧 `browser_tool()` 按 profile 复用会话并把 action 字符串反射到 `BrowserSession` 方法；MCP 侧把 25 个工具拆成独立 Tool 后仍回落到同一入口。CLI 只是第三层薄封装，见 [`cli.md`](cli.md)。

## 1. 请求处理洋葱链

```text
browser_tool(action, profile, ...) -> src/octop_browser/tool_interface.py:91-212
  ├─ [1. 白名单] action 不在 _KNOWN_ACTIONS -> _error_result(带合法集合) : :120-123
  ├─ [2. 特殊命令] close_session -> 弹注册表 + 可选 terminate_browser : :125-161
  ├─ [3. 会话获取] _get_or_create_session 按 profile 命中 _registry : :57-68
  │    └─ 创建失败 -> _error_result("Failed to create session: ...") : :167-168
  ├─ [4. 补开标签] urls 已存在会话时首 URL navigate，其余 new_tab(force_new) : :170-177
  ├─ [5. 反射执行] getattr(sess, action)(**kwargs) : :179-182
  └─ [6. 错误翻译]
       ├─ TypeError -> "Invalid parameters for '<action>': ..." : :183-184
       ├─ 断链错误(_is_disconnected_error) -> 丢弃旧会话并重建后重试一次 : :185-210
       └─ 其他异常 -> 记日志并 _error_result(str(exc)) : :211-212
```

`_is_disconnected_error()` 只识别消息含 `not connected` 或 `connection lost` 的 `CDPSessionError`（`src/octop_browser/tool_interface.py:83-88`），其他异常不触发自动重连，避免重复执行有副作用的动作。

## 2. 路由分组与并发模型表

| 分组 | 端点数 | 鉴权/隔离机制 | 执行模型 | 下游落点 |
|---|---|---|---|---|
| 浏览器动作（Python `browser_tool`） | 19 | `profile` 键隔离 `_registry` | 协程直出；每 profile 首次调用创建会话 | `BrowserSession` 对应方法 |
| MCP 浏览器工具 | 14 | Tool 名映射到 `_ACTION_MAP` | `call_tool` 协程直出，参数原样透传 | `browser_tool()` |
| MCP 录制/回放工具 | 10 | Unix socket 请求 daemon 或本地 Store | daemon 长连接 / 同步读盘 | `RecordController`、`ReplayRunner` |
| MCP 安装工具 | 1 | 异步生成器逐行转发安装日志 | `install_chromium_stream()` 流 | `install.py` |
| 自定义工具兜底 | 1 | `_ACTION_MAP.get(name) is None` | 返回 `Unknown tool: <name>` | 无 |

MCP 工具总数 25（定义于 `src/octop_browser/mcp_server.py:24-347`）；`_ACTION_MAP` 仅覆盖 14 个浏览器动作（`src/octop_browser/mcp_server.py:349-364`），其余 11 个在 `call_tool()` 中按名称显式分支（`src/octop_browser/mcp_server.py:393-457`）。`browser_open` 特化为 `list_tabs` 动作 + `urls` 参数（`src/octop_browser/mcp_server.py:464-473`）。

## 3. 核心源码符号表

| 源码文件 | 核心符号与行号 | 职责边界 |
|---|---|---|
| `src/octop_browser/tool_interface.py` | `_registry` (`:17`), `_KNOWN_ACTIONS` (`:20-43`), `browser_tool` (`:91-212`) | 会话注册表、动作白名单、异常翻译与一次性重连 |
| `src/octop_browser/mcp_server.py` | `app = Server("octop-browser")` (`:22`), `_TOOLS` (`:24-347`), `list_tools` (`:367-369`), `call_tool` (`:391-479`), `_main` (`:482-530`) | MCP Tool Schema 注册、工具分发、stdio/SSE 传输选择 |

MCP 传输由 `MCP_PORT` 决定：未设置走 `stdio_server()`（`src/octop_browser/mcp_server.py:526-530`）；设置则加载 `uvicorn` + `SseServerTransport`，挂载 `/sse` 与 `/messages/` 路由，监听 `MCP_HOST` 默认 `0.0.0.0`（`src/octop_browser/mcp_server.py:491-525`）。每个工具调用返回 `TextContent`；浏览器动作失败时把 `ERROR: <error>` 写回文本（`src/octop_browser/mcp_server.py:476-479`）。

## 4. 上下游调用关系

- **上游调用方**：CLI `_run_action()`（`src/octop_browser/cli.py:514-534`）、MCP 客户端、Python 直接 import。
- **下游被调模块**：核心动作引擎 [`browser-engine.md`](browser-engine.md)；录制回放 [`record-worker.md`](record-worker.md)；字段流转向 [`../integrations/topology-and-mapping.md`](../integrations/topology-and-mapping.md)；逐工具 Schema 见 [`../contracts/api/mcp-tools.md`](../contracts/api/mcp-tools.md)。

## 5. 共变耦合与新增接口清单

1. 新增 action：改 `BrowserSession` → `_KNOWN_ACTIONS`（`src/octop_browser/tool_interface.py:20-43`）→ `_TOOLS` 与 `_ACTION_MAP`（`src/octop_browser/mcp_server.py:24-347,349-364`）→ CLI 别名与参数转换（`src/octop_browser/cli.py:413-499`）。
2. 新增录制类 MCP 工具：必须在 `call_tool()` 里显式加分支，因为 `_ACTION_MAP` 不覆盖它；跑 `tests/unit/test_mcp_server.py`。
3. 修改断链识别条件：会影响自动重连次数，`close_session` 等非幂等动作需单独确认；跑 `tests/unit/test_tool_interface.py`。
4. 改 MCP 传输默认值：`MCP_HOST` 默认 `0.0.0.0` 是网络暴露面，调整前核对 `operations/boundary.md` 的网络边界声明。
