---
kind: downstream-contract
scope: mcp-transport
status: draft
origin: generated
source_paths: [src/octop_browser/mcp_server.py, src/octop_browser/models.py]
symbols: [_main, app, list_tools, call_tool, stdio_server, SseServerTransport, TextContent, ToolResult, MCP_PORT, MCP_HOST]
upstream: [integrations/index.md, architecture/mcp-server.md]
downstream: []
---

# 下游出向接口契约：MCP 传输运行时（stdio / SSE）

`mcp_server._main` 默认用 `mcp.server.stdio.stdio_server()` 对接本地 Agent；当 `MCP_PORT` 设置时改用 `uvicorn` + `starlette` + `mcp.server.sse.SseServerTransport` 暴露 HTTP/SSE。本页展开这条**可选外部运行时**的路由字典、初始化参数与响应包络；`mcp`/`uvicorn`/`starlette` 的服务端内部实现不在本仓，属外部黑盒（见 [认知边界](../../operations/boundary.md)），工具级契约见 [MCP 服务组件](../../architecture/mcp-server.md) 与 [MCP 工具契约](../../contracts/api/mcp-tools.md)。

## 1. 封装定位与连接契约

| 契约项 | 精确值 / 规则 | 源码锚点 |
|---|---|---|
| 模式开关 | `mcp_port = os.environ.get("MCP_PORT")`，非空走 SSE，否则 stdio | `src/octop_browser/mcp_server.py:491` |
| stdio 分支 | `async with stdio_server() as (read_stream, write_stream): app.run(...)` | `src/octop_browser/mcp_server.py:527` |
| SSE 主机 | `MCP_HOST`，默认 `0.0.0.0` | `src/octop_browser/mcp_server.py:499` |
| SSE 传输 | `SseServerTransport("/messages/")` | `src/octop_browser/mcp_server.py:501` |
| 应用初始化 | `app.run(streams[0], streams[1], app.create_initialization_options())` | `src/octop_browser/mcp_server.py:507` |
| uvicorn 配置 | `uvicorn.Config(app=starlette_app, host=host, port=port, log_level="info")` 后 `await server.serve()` | `src/octop_browser/mcp_server.py:520` |
| 统一响应包络 | 所有工具返回 `list[TextContent]`，`TextContent(type="text", text=...)` | `src/octop_browser/mcp_server.py:479` |

## 2. 本仓上游调用方反查表

| 本仓封装入口 | 上游调用模块与函数 | 所属流程 | 调用点锚点 |
|---|---|---|---|
| `_main` | `__main__` 的 `asyncio.run(_main())` | [部署与运行时](../../operations/deployment-and-runtime.md) | `src/octop_browser/mcp_server.py:535` |
| `app.list_tools` | MCP 客户端 `tools/list` 请求 | [MCP 服务组件](../../architecture/mcp-server.md) | `src/octop_browser/mcp_server.py:367` |
| `app.call_tool` | MCP 客户端 `tools/call` 请求 | [MCP 服务组件](../../architecture/mcp-server.md) | `src/octop_browser/mcp_server.py:391` |
| `Makefile` 的 `mcp` 目标 | 开发者本地启动 | [构建与单测映射](../../operations/dev-and-test.md) | `Makefile:115` |

## 3. 传输方法与路由总清单

| 序号 | 模式 | 路由 / 方法 | 处理函数 | 入向载荷 | 定义锚点 |
|---|---|---|---|---|---|
| 1 | stdio | stdin/stdout 帧流 | `stdio_server()` | MCP JSON-RPC 帧 | `src/octop_browser/mcp_server.py:527` |
| 2 | SSE | `GET /sse` | `handle_sse` | 无（建立 SSE 流） | `src/octop_browser/mcp_server.py:503`、`:515` |
| 3 | SSE | `POST /messages/` | `sse.handle_post_message` | MCP JSON-RPC 帧 | `src/octop_browser/mcp_server.py:516` |
| 4 | 双模 | `tools/list` | `list_tools()` → `_TOOLS`（25 项） | 无参 | `src/octop_browser/mcp_server.py:367`、`:24` |
| 5 | 双模 | `tools/call` | `call_tool(name, arguments)` | `{"name": str, "arguments": dict}` | `src/octop_browser/mcp_server.py:391` |

## 4. 逐路由请求字典与响应解包契约（Full Dict Schemas）

### 4.1 SSE 路由表（`starlette` 注册字典）

```json
{"routes": [{"path": "/sse", "endpoint": "handle_sse"}, {"path": "/messages/", "methods": ["POST"], "endpoint": "sse.handle_post_message"}]}
```

| 字典键 | 类型 | 必填 | 值来源 | 行号 |
|---|---|---|---|---|
| `Route.path` | `str` | 是 | `"/sse"` 与 `"/messages/"` 字面量 | `src/octop_browser/mcp_server.py:515`、`:516` |
| `Route.methods` | `list[str]` | 否（仅 POST 路由显式） | `["POST"]` | `:516` |
| `SseServerTransport` 构造参数 | `str` | 是 | `"/messages/"`，与 POST 路由严格一致 | `:501` |
| `uvicorn.Config.host` | `str` | 是 | `MCP_HOST` 或 `0.0.0.0` | `:499`、`:521` |
| `uvicorn.Config.port` | `int` | 是 | `int(MCP_PORT)` | `:498`、`:521` |
| `uvicorn.Config.log_level` | `str` | 是 | 固定 `"info"` | `:521` |

### 4.2 `tools/list` 与 `tools/call` 包络

| 请求 / 应答键 | 类型 | 解包规则 | 行号 |
|---|---|---|---|
| `name`（`tools/call`） | `str` | 先匹配 `install_browser` 与 `browser_record_*` 特例，再查 `_ACTION_MAP`，未命中返回 `Unknown tool: {name}` | `src/octop_browser/mcp_server.py:459`、`:461` |
| `arguments`（`tools/call`） | `dict` | 用 `.get(key, default)` 逐键取值，未知键透传给 `browser_tool(**arguments)` | `:395`、`:475` |
| `_TOOLS` 元素 | `Tool` | `name`、`description`、`inputSchema`（`type/properties/required/default/enum`） | `:24`、`:28` |
| 成功应答 | `list[TextContent]` | `text` 取 `ToolResult.content`（定义于 `src/octop_browser/models.py:20`）字符串，dict 用 `str(...)` | `:476`、`:479` |
| 失败应答 | `list[TextContent]` | `text = f"ERROR: {result.error}"` | `:477`、`:478` |
| 安装器应答 | `list[TextContent]` | 聚合 `InstallEvent` 的 `log` 行，终态拼 `OK` 或 `FAILED: {error}` | `:378`、`:386`、`:388` |

### 4.3 错误与降级翻译

| 下游条件 | 本仓行为 | 行号 |
|---|---|---|
| `MCP_PORT` 为空 | 走 stdio，不导入 uvicorn/starlette（延迟导入在函数体内） | `src/octop_browser/mcp_server.py:492`、`:526` |
| `MCP_PORT` 非整数 | `int(mcp_port)` 抛 `ValueError`，进程退出 | `:498` |
| 工具名不在 `_ACTION_MAP` 且非特例 | 返回文本 `Unknown tool: {name}`，不抛异常 | `:460` |
| `browser_tool` 返回 `success=False` | 文本改写为 `ERROR: ...`，不传播异常 | `:477` |

## 5. 共变耦合与修改清单（Agent Co-Change Playbook）

- **新增 SSE 路由**：`Starlette(routes=[...])`（`src/octop_browser/mcp_server.py:513`）与 `SseServerTransport("/messages/")` 的路径常量（`:501`）必须成对修改，任一侧改名会让 POST 消息无处投递。
- **修改传输开关**：`MCP_PORT` / `MCP_HOST` 的读取（`:491`、`:499`）与 [配置手册](../../contracts/configuration.md) 同步；`pyproject.toml` 未声明 `uvicorn`/`starlette` 依赖，SSE 模式依赖宿主环境另装，见 [部署与运行时](../../operations/deployment-and-runtime.md)。
- **修改工具包络**：`_TOOLS`（`:24`）、`call_tool`（`:391`）、`_ACTION_MAP`（`:349`）与 [入向接口契约全集](../../contracts/api-reference.md) 四处联动。
- **特殊协议陷阱**：SSE 与 stdio 共用同一个 `app` 实例，`app.run` 每次传入新建的 stream 对；`uvicorn`/`starlette` 为延迟导入，缺包时只在设置 `MCP_PORT` 后才报错。
- **回归**：`pytest tests/unit/test_mcp_server.py tests/unit/test_tool_interface.py`，命令见 [构建与单测映射](../../operations/dev-and-test.md)。
