# 01 Clarify — 原生 GET /welcome 路由

## 目标与验收契约
- 在现有 Web 服务暴露原生 HTTP 路由 `GET /welcome`（免登录、不经过 MCP 鉴权）。
- 响应：`200` + `Content-Type: application/json` + body `{"message":"welcome"}`。
- 契约测试位置：`tests/test_experience_welcome.py`（后续阶段实现）。

## 框架与路由位置（已确认，不再全仓探查）
- 仓库为 `octop-browser`（纯 CDP 浏览器封装），无独立 Flask/FastAPI 应用、无 `app.py`。
- 唯一对外 HTTP 服务是 `src/octop_browser/mcp_server.py::_main()` 中的 SSE 模式：
  - 触发条件：环境变量 `MCP_PORT` 存在；否则走 stdio（`mcp_server.py:491-492, 526-530`）。
  - 协议栈：Starlette `Route` + `uvicorn.Server`（`mcp_server.py:493-496, 520-523`）。
  - 路由注册处：`mcp_server.py:513-518` 的 `Starlette(routes=[...])`，现有 `/sse`、`/messages/` 两条。
  - host/port：`MCP_HOST`（默认 `0.0.0.0`）/ `MCP_PORT`（`mcp_server.py:498-499`）。

## 改动范围
- 仅改 `src/octop_browser/mcp_server.py`：新增端点 `handle_welcome(request)`，返回 `JSONResponse({"message": "welcome"})`；在 `Starlette(routes=...)` 追加 `Route("/welcome", endpoint=handle_welcome, methods=["GET"])`。
- 为可测试性做最小重构：把 `starlette_app` 构造抽成模块级 `build_http_app()`，由 `_main()` 调用；SSE 行为逐行搬迁、不改写。
- 依赖：Starlette/uvicorn 由 `mcp` 传递依赖提供且已在 SSE 分支内导入，无需新增运行依赖、不改 `pyproject.toml`。
- 不改前端 `static/`、不改 CLI/stdio 路径。

## 验收条件
1. `GET /welcome` → 200 / `application/json` / `{"message":"welcome"}`。
2. 非 GET 方法（如 POST）不被该路由接受（405）。
3. `/sse`、`/messages/` 行为不变；未设 `MCP_PORT` 时仍走 stdio。
4. `tests/test_experience_welcome.py` 用 Starlette `TestClient` 覆盖上述断言。

## 结论
- 契约明确、落点唯一（SSE 模式的 Starlette 路由表）、改动可控。
- 可进入 02 Plan。
