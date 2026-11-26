# 02 Plan — 实现 GET /welcome

## 实现步骤
1. `src/octop_browser/mcp_server.py` 新增延迟导入 `from starlette.responses import JSONResponse`（与现有 SSE 分支一致，避免 stdio 模式强依赖）。
2. 新增 `async def handle_welcome(request: Any) -> JSONResponse:`，返回 `JSONResponse({"message": "welcome"})`。
3. 抽取 `def build_http_app() -> Any:`：把 `SseServerTransport("/messages/")`、`handle_sse` 与 `Starlette(routes=[...])` 整体移入并返回 app；`_main()` 改为 `starlette_app = build_http_app()`。逐行搬迁，不改 SSE 逻辑。
4. 在 `routes` 末尾追加 `Route("/welcome", endpoint=handle_welcome, methods=["GET"])`（精确路径，与 `/sse`、`/messages/` 无冲突）。
5. 新增 `tests/test_experience_welcome.py`：
   - `client = TestClient(build_http_app())`。
   - `r = client.get("/welcome")`；断言 `status_code == 200`、`headers["content-type"].startswith("application/json")`、`r.json() == {"message": "welcome"}`。
   - 断言 `client.post("/welcome").status_code == 405`。
   - 回归：`/sse`、`/messages/` 仍注册（存在性断言）。

## 具体文件与命令
- 修改：`src/octop_browser/mcp_server.py`（唯一源码改动）。
- 新增：`tests/test_experience_welcome.py`。
- 验证命令（后续阶段执行；本阶段不运行）：
  - `uv run pytest tests/test_experience_welcome.py -q`
  - `make all`（format + lint + typecheck + test；mypy strict、ruff line-length 88）
- 禁止：启动服务、HTTP 探测。

## runtime.json 形状（平台交付契约）
```json
{
  "service": "octop-browser-mcp-sse",
  "entrypoint": "python -m octop_browser.mcp_server",
  "env": { "MCP_PORT": "<allocated-port>", "MCP_HOST": "0.0.0.0" },
  "healthcheck": { "method": "GET", "path": "/welcome", "expect_status": 200 }
}
```
- 端口由平台分配并注入 `MCP_PORT`；`MCP_HOST` 默认 `0.0.0.0`，遵循"不硬编码内部地址"约束。

## 回滚要点
- 撤销三处源码改动：`handle_welcome` 端点、`build_http_app` 抽取（还原为 `_main()` 内联构造）、`Route("/welcome")`；删除 `tests/test_experience_welcome.py`。
- 风险与规避：
  - 抽取函数改动 `_main()` 结构 → SSE 逻辑仅移动不改写，保持逐行一致。
  - stdio 模式被新导入破坏 → starlette 导入全部放在函数/分支内延迟执行。
  - 路由冲突 → `/welcome` 为精确路径且追加在末尾，无通配冲突。
