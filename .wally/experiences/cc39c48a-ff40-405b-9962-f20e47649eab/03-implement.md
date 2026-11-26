# 03 Implement + UT + Docs — 原生 GET /welcome

## 目标
在现有 MCP SSE HTTP 服务中注册原生 `GET /welcome`，返回 `200` +
`application/json` + `{"message":"welcome"}`，免登录、免 MCP 握手。

## 改动文件
- `src/octop_browser/mcp_server.py`
  - 新增 `handle_welcome(request)`，返回 `JSONResponse({"message": "welcome"})`。
  - 抽取 `build_http_app()`：承载 `SseServerTransport`、`handle_sse` 与
    Starlette 路由表，追加 `Route("/welcome", endpoint=handle_welcome,
    methods=["GET"])`。
  - `_main()` 的 SSE 分支改为 `starlette_app = build_http_app()`；SSE 逻辑
    逐行搬迁、未改写，stdio 分支与延迟导入策略不变。
- `tests/test_experience_welcome.py`（新增）：3 条契约测试。
- `README.md` / `README_CN.md`：新增 "HTTP 接口（SSE 模式）" 说明，列出
  `/welcome`、`/sse`、`/messages/` 及 `MCP_PORT` 启动示例。
- `.wally/.../runtime.json`（新增）：平台复跑测试与启动服务的命令契约。

## 测试
环境：`uv sync --extra dev` 创建 `/workspace/.venv`（CPython 3.11.18），
安装项目与 dev 依赖；Starlette / uvicorn / httpx 由 `mcp` 传递依赖提供。

命令（仅契约测试文件，未跑全量 pytest）：
```bash
python -m pytest -q tests/test_experience_welcome.py
```

结果：
```text
...                                                                      [100%]
3 passed, 2 warnings in 0.49s
```

覆盖点：
- `GET /welcome` → 200、`Content-Type: application/json`、body 精确等于
  `{"message": "welcome"}`。
- `POST /welcome` → 405（仅接受 GET）。
- `/sse`、`/messages/`、`/welcome` 均仍在路由表中（SSE 行为回归）。

2 条 warning 分别为 pytest-asyncio 配置项与 Starlette `TestClient` 的弃用
提示，不影响断言结果。

## runtime.json 契约
- `test`: `python3 -m pytest -q tests/test_experience_welcome.py`
- `serve`: `env MCP_HOST=0.0.0.0 MCP_PORT={port} python3 -m octop_browser.mcp_server`
- 端口由平台注入 `{port}`；host 显式 `0.0.0.0`。

## 备注
- `uv sync --extra dev` 同步刷新了 `uv.lock` 的元数据（revision、版本号、
  `mcp<3` 约束），使其与现有 `pyproject.toml` 一致；未改 `pyproject.toml`。
- 未启动长时服务、未做 HTTP 压测，按约定交由平台复跑与临时服务验证。
- 未改前端资源与 CLI/stdio 路径。
