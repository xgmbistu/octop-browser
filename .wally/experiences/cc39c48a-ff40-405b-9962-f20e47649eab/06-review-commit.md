# 06 Review + Commit — 原生 GET /welcome

## 审查范围
对照基线 `b3910fc50c964fabcc8a8cde6ccec7367dbb27dd`（取自阶段目录 `baseline-sha`，
`../baseline-sha` 不存在），执行 `git diff` 审查全部改动；只读核验了
`03-implement.md`、`test-output.txt`、`http-results.json`、当前源码与契约测试。

## Diff 结论
- `src/octop_browser/mcp_server.py`（核心改动）
  - 新增 `handle_welcome()`：延迟导入 `JSONResponse`，返回 `{"message":"welcome"}`。
  - 抽取 `build_http_app()`：承载 `SseServerTransport` / `handle_sse` 与路由表，
    追加 `Route("/welcome", ..., methods=["GET"])`；SSE 逻辑逐行搬迁未改写。
  - `_main()` 的 SSE 分支改为调用 `build_http_app()`；stdio 分支与延迟导入策略不变。
- `tests/test_experience_welcome.py`（新增）：3 条契约测试。
- `README.md` / `README_CN.md`：新增 HTTP 接口（SSE 模式）表格与 curl 示例。
- `runtime.json`（新增）：平台复跑 test/serve 命令契约，端口用 `{port}` 占位符，host `0.0.0.0`。
- `uv.lock`：`uv sync` 同步元数据——version `0.9.9`→`1.0.0`、`mcp<2`→`<3`、
  revision/resolution-markers 更新。经核对与 `pyproject.toml`（version `1.0.0`、
  `mcp>=1.9,<3`）一致，属修正基线陈旧 lock，非引入新依赖或改 `pyproject.toml`。
- 无前端/CLI/stdio 路径改动；无硬编码内部地址。

## 契约符合性
- 原生路由：`/welcome` 直接注册在 Starlette 路由表，不经过 MCP 工具鉴权/握手。
- 免登录：路由无鉴权依赖。
- 精确路径且追加在末尾，与 `/sse`、`/messages/` 无冲突。
- 非 GET 方法返回 405；`MCP_PORT` 未设时仍走 stdio。

## 测试 / HTTP 证据
- 单元测试（`test-output.txt`）：`python -m pytest -q tests/test_experience_welcome.py`
  → `3 passed, 2 warnings`。2 条 warning 为 pytest-asyncio 配置项与
  Starlette TestClient 弃用提示，不影响断言。覆盖：200 + content-type + body
  精确值、POST→405、三条路由仍在表中。
- 运行时 HTTP（`http-results.json` / `05-it.md`）：
  `GET http://127.0.0.1:32782/welcome` → status `200`、
  content_type `application/json`、body `{"message":"welcome"}`。
- 部署（`04-deploy.md`）：服务已启动、就绪探测 `/welcome` → 200。
- 未重跑服务、未跑全量 pytest（遵循约定）。

## 结论
改动最小、落点唯一，SSE 既有行为与 stdio 路径得到保留，契约测试与实际 HTTP
响应双重印证。未发现任何 finding。

**批准（approved=true）**。Git 提交与推送交由平台收尾。
