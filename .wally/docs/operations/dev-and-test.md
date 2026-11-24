---
kind: operations
scope: dev-and-test
status: draft
origin: generated
source_paths: [pyproject.toml, Makefile, .github/workflows/ci.yml, tests/unit/conftest.py, tests/integration/conftest.py, tests/unit/test_tool_interface.py, tests/unit/test_record_replay_semantic.py, scripts/record_replay_smoke.py]
symbols: [test_browser_tool_unknown_action, test_semantic_merges_click_input_and_navigation_expectation, _isolate_octop_env, pytest_collection_modifyitems, main]
upstream: [../INDEX.md]
downstream: []
---

# 构建启动与单测验证手册

Python 3.11+，`uv` 为首选依赖管理器。所有质量门禁通过 `make all` 串联，CI 在 Python 3.11/3.12 双版本执行同一套命令。集成测试在无 Chrome 时自动跳过，因此纯逻辑改动无需本机浏览器。

## 1. 环境前置与可执行命令速查

| 动作 | 精确执行命令 | 配置来源 | 备注 |
|---|---|---|---|
| 安装依赖 | `make install`（`uv sync --extra dev`，无 uv 则 `pip install -e ".[dev]"`） | `Makefile:156-163`、`pyproject.toml:33-42` | Python ≥3.11 |
| 全量门禁 | `make all` = `format + lint + typecheck + test` | `Makefile:120-121` | 提交钩子强制执行 |
| Lint | `make lint`（`ruff check src tests` + `ruff format --check src tests`） | `Makefile:123-128`、`pyproject.toml:55-71` | line-length 88，规则 E/F/I/N/W |
| 格式化 | `make format`（`ruff check --fix` + `ruff format`） | `Makefile:130-134` | 会重写文件 |
| 类型检查 | `make typecheck`（`mypy src`，strict） | `Makefile:136-139`、`pyproject.toml:73-76` | python_version=3.11 |
| 全量单测 | `make test`（`pytest --cov=octop_browser --cov-report=term-missing`） | `Makefile:141-144`、`pyproject.toml:78-83` | `asyncio_mode="auto"` |
| 仅单测 | `uv run pytest tests/unit/ -q` | `tests/unit/conftest.py:1-13` | 不需要 Chrome |
| 单文件/单用例 | `uv run pytest tests/unit/test_mode.py -q` / `uv run pytest tests/unit/test_settings.py::test_env_override_browser_mode -q` | `CODEBUDDY.md:25-31` | 改单模块优先跑精准用例 |
| 集成测试 | `uv run pytest tests/integration/ -v` | `tests/integration/conftest.py:6-12` | `find_chrome()` 为 None 则整体跳过 |
| CLI 冒烟 | `uv run python -m octop_browser --help` / `--version` | `Makefile:110-116`、`src/octop_browser/cli.py:47-52` | 预期列出全部命令 |
| MCP 启动 | `make mcp` | `Makefile:114-116` | stdio 模式 |
| 录制回放冒烟 | `python3 scripts/record_replay_smoke.py`（需真实 Chrome） | `scripts/record_replay_smoke.py:1-9,133` | 建临时表单页、录制、生成、回放 |
| 构建 | `make build`（`uv build --out-dir dist .`） | `Makefile:64-77` | 产物 wheel + sdist |
| 清理 | `make clean` | `Makefile:170-180` | 删 dist/、缓存、egg-info |

CI 配置在 `.github/workflows/ci.yml:1-38`：仅 PR 触发，矩阵 Python 3.11/3.12，先 `make install`，再 `apt-get install chromium-browser`，最后依次 `make lint`、`make typecheck`、`make test`。

## 2. 源码模块 → 必跑回归测试映射

| 被修改的源码文件/目录 | 必跑测试文件 | 关键覆盖点 | 精确命令 |
|---|---|---|---|
| `src/octop_browser/tool_interface.py` | `tests/unit/test_tool_interface.py` | 非法 action、缺参、断链一次重连 (`tests/unit/test_tool_interface.py:19,27,37`) | `uv run pytest tests/unit/test_tool_interface.py -q` |
| `src/octop_browser/cli.py` | `tests/unit/test_cli.py` | navigate 分发、连字符映射、截图可选参数 (`tests/unit/test_cli.py:57,71,78`) | `uv run pytest tests/unit/test_cli.py -q` |
| `src/octop_browser/mcp_server.py` | `tests/unit/test_mcp_server.py` | mcp 版本范围、Tool 注册、action map 命中 (`tests/unit/test_mcp_server.py:27,43,78`) | `uv run pytest tests/unit/test_mcp_server.py -q` |
| `src/octop_browser/session.py`、`actions/*` | `tests/integration/test_session.py` | 真实导航、DOM 层级 (`tests/integration/test_session.py:26,32,39`) | `uv run pytest tests/integration/test_session.py -v` |
| `src/octop_browser/dom/*` | `tests/unit/test_dom_builder.py`、`tests/unit/test_refs.py` | 四档输出、ref 失效 | `uv run pytest tests/unit/test_dom_builder.py tests/unit/test_refs.py -q` |
| `src/octop_browser/cdp/*` | `tests/unit/test_launcher.py`、`tests/unit/test_launch_prep.py` | Playwright 版本排序、terminate 拒绝 remote host (`tests/unit/test_launcher.py:37,134`) | `uv run pytest tests/unit/test_launcher.py tests/unit/test_launch_prep.py -q` |
| `src/octop_browser/install.py`、`linux_deps.py`、`playwright_download.py` | `tests/unit/test_install.py`、`tests/unit/test_linux_deps.py`、`tests/unit/test_playwright_download.py` | 幂等短路、skip pip、CDN 候选 (`tests/unit/test_install.py:49,66`) | `uv run pytest tests/unit/test_install.py tests/unit/test_linux_deps.py tests/unit/test_playwright_download.py -q` |
| `src/octop_browser/settings.py`、`mode.py`、`profile.py` | `tests/unit/test_settings.py`、`tests/unit/test_mode.py`、`tests/unit/test_profile.py` | 环境覆盖、模式解析、端口分配 | `uv run pytest tests/unit/test_settings.py tests/unit/test_mode.py tests/unit/test_profile.py -q` |
| `src/octop_browser/record/semantic.py` | `tests/unit/test_record_replay_semantic.py` | click+input+navigation 合并、空白页点击改写、低信号过滤 (`tests/unit/test_record_replay_semantic.py:4,47,126`) | `uv run pytest tests/unit/test_record_replay_semantic.py -q` |
| `src/octop_browser/record/replay.py` | `tests/unit/test_record_replay_replay_runner.py` | 回放步骤分派与失败留证 | `uv run pytest tests/unit/test_record_replay_replay_runner.py -q` |
| `src/octop_browser/record/daemon.py` | `tests/unit/test_record_daemon_client.py` | socket 请求/响应 | `uv run pytest tests/unit/test_record_daemon_client.py -q` |
| `src/octop_browser/record/store.py`、`skill_generator.py` | `tests/unit/test_record_replay_store_skill.py` | 目录与文件落盘 | `uv run pytest tests/unit/test_record_replay_store_skill.py -q` |
| 录制回放端到端 | `tests/integration/test_record_replay_e2e.py` | 真实表单录制→生成→回放 (`tests/integration/test_record_replay_e2e.py:34`) | `uv run pytest tests/integration/test_record_replay_e2e.py -v` |

## 3. 测试环境隔离与 Mock 规范

1. **环境变量清洗**：`tests/unit/conftest.py:8-13` 的 autouse fixture 删除所有 `BROWSER_USE_*` 变量；作用范围仅限 unit，integration 保留宿主环境。
2. **单例重置**：同一 fixture 用 `dataclasses.fields()` 把模块级 `settings` 逐字段恢复为新建 `OctopSettings()` 的值（`tests/unit/conftest.py:15-24`），不要直接 mutate 单例后不还原。
3. **Chrome 缺失跳过**：`tests/integration/conftest.py:6-12` 通过 `find_chrome()` 为整个 integration 套件打 skip 标记；新增集成测试无需自行判断。
4. **无 Chrome 优先单测**：断言 CDP 行为时用 `FakeClient`/`monkeypatch` 替换 `CDPClient.send`，参考 `tests/unit/test_tool_interface.py:37` 的断链重连测试。
5. **子进程 Mock**：安装相关单测 patch `subprocess.run` 与 `asyncio.create_subprocess_exec`，参考 `tests/unit/test_install.py:49,66`。
6. **落盘隔离**：录制测试用 `tmp_path` 构造 `RecordReplaySettings(base_dir=...)`，禁止写真实 `~/.octop-browser`。
7. **提交禁令**：不提交 `dist/`、`.coverage`、`htmlcov/`、测试临时录制或 profile 数据；`make clean` 可清理构建缓存。

## 4. 提交门禁

`make install-hooks` 把 `core.hooksPath` 指向 `.githooks`，pre-commit 执行 `make all` 并自动把被 format 改写的已暂存文件重新 `git add`（`.githooks/pre-commit:14-37`）。紧急绕过用 `SKIP_PRECOMMIT=1`，但禁止在红灯状态下提交。

## 5. 共变耦合与修改清单

- 改测试框架配置：同步 `pyproject.toml:78-83` 与 CI（`Makefile:141-144`）。
- 新增源码模块：在上表补一行「模块 → 必跑测试」，否则 Agent 可能漏跑回归。
- 改环境隔离前缀：同步 `tests/unit/conftest.py:6` 与 `contracts/configuration.md`。

## 6. 关联文档

- [组件技术架构总表](../architecture/index.md) · [模块依赖矩阵](../architecture/module-dep-matrix.md) · [构建产物与运行时](deployment-and-runtime.md)
