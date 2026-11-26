---
kind: operations
scope: dev-and-test
status: draft
origin: generated
source_paths: [Makefile, pyproject.toml, tests/unit/conftest.py, tests/integration/conftest.py, .github/workflows/ci.yml, .githooks/pre-commit, scripts/record_replay_smoke.py]
symbols: [make_all, asyncio_mode, pytest_collection_modifyitems, _isolate_octop_env, run_smoke]
upstream: [INDEX.md, contracts/configuration.md]
downstream: [operations/pitfalls-and-adr.md]
---

# 构建启动与单测验证手册（Agent Verification Playbook）

运行时要求 Python `>=3.11`（`pyproject.toml:14`），依赖仅 `websockets/pydantic/aiohttp/mcp`（`:24`），开发期用 `uv` + Makefile 驱动 ruff、mypy、pytest。CI 在 Python 3.11/3.12 矩阵跑 `make lint/typecheck/test`（`.github/workflows/ci.yml:21`），提交前由 `make install-hooks` 挂 `make all` 门禁。

## 1. 环境前置与可执行命令速查

| 动作 | 精确执行命令 | 配置来源（`路径:行号`） | 备注 / 前置环境变量 |
|---|---|---|---|
| 安装依赖 | `make install`（`uv sync --extra dev`，无 uv 时 `pip install -e ".[dev]"`） | `Makefile:157`、`pyproject.toml:33` | Python 3.11+、`uv` 可选 |
| 启动 CLI | `octop-browser --help` / `octop-browser --version` | `pyproject.toml:50`、`src/octop_browser/cli.py:111` | 首次动作需 Chromium |
| 启动 MCP | `make mcp` → `python -m octop_browser.mcp_server` | `Makefile:115` | 设 `MCP_PORT` 走 SSE |
| 格式化 | `make format`（`ruff check --fix` + `ruff format`） | `Makefile:131` | 会改写文件 |
| Lint | `make lint`（`ruff check src tests` + `ruff format --check`） | `Makefile:124`、`pyproject.toml:55` | `line-length=88`、`select=E F I N W` |
| 类型检查 | `make typecheck`（`mypy src`） | `Makefile:137`、`pyproject.toml:73` | `strict=true`、`python_version=3.11` |
| 全量单测 | `make test`（`pytest --cov=octop_browser --cov-report=term-missing`） | `Makefile:142`、`pyproject.toml:78` | `asyncio_mode="auto"` |
| 仅单测 | `uv run pytest tests/unit/ -q` | `pyproject.toml:79` | 无需 Chrome |
| 单文件 / 单用例 | `uv run pytest tests/unit/test_settings.py::test_env_override_browser_mode -q` | `pyproject.toml:79` | 精准回归 |
| 集成测试 | `uv run pytest tests/integration/ -v` | `tests/integration/conftest.py:6` | `find_chrome()` 为 `None` 时整组 skip（`:8`） |
| 端到端冒烟 | `python scripts/record_replay_smoke.py --json` | `scripts/record_replay_smoke.py:133` | 需真实 Chrome，默认 `cdp_port_start=19550`（`:142`） |
| 构建产物 | `make build`（`uv build` → wheel + sdist） | `Makefile:65`、`pyproject.toml:52` | 输出到 `dist/` |
| 提交门禁 | `make install-hooks` 后每次 `git commit` 自动跑 `make all` | `Makefile:149`、`.githooks/pre-commit:24` | `SKIP_PRECOMMIT=1` 仅应急 |

## 2. 源码模块 → 必跑回归测试映射表（Module-to-Test Map）

| 被修改的源码文件 / 目录 | 必跑测试文件 | 关键覆盖契约点 | 精确运行命令 |
|---|---|---|---|
| `src/octop_browser/settings.py`、`mode.py` | `tests/unit/test_settings.py`、`test_mode.py` | 环境变量重读、三态解析、桌面环境判定 | `pytest tests/unit/test_settings.py tests/unit/test_mode.py` |
| `src/octop_browser/tool_interface.py`、`models.py`、`hooks.py` | `tests/unit/test_tool_interface.py`、`test_models.py`、`test_hooks.py` | 动作白名单、断线重连、hooks 异常吞掉 | `pytest tests/unit/test_tool_interface.py tests/unit/test_models.py tests/unit/test_hooks.py` |
| `src/octop_browser/session.py` | `tests/integration/test_session.py`、`tests/unit/test_tool_interface.py` | 会话创建、标签管理、结果归一化 | `pytest tests/integration/test_session.py tests/unit/test_tool_interface.py` |
| `src/octop_browser/cli.py` | `tests/unit/test_cli.py` | 命令树、别名映射、`--json` 渲染、退出码 | `pytest tests/unit/test_cli.py` |
| `src/octop_browser/mcp_server.py` | `tests/unit/test_mcp_server.py` | 工具注册、`call_tool` 分发、安装器聚合 | `pytest tests/unit/test_mcp_server.py` |
| `src/octop_browser/cdp/client.py`、`idle.py` | `tests/unit/test_idle.py` | CDP 帧超时、活动追踪、回收 | `pytest tests/unit/test_idle.py` |
| `src/octop_browser/cdp/launcher.py` | `tests/unit/test_launcher.py` | 端口探测、flag 构造、优雅关闭 | `pytest tests/unit/test_launcher.py` |
| `src/octop_browser/cdp/launch_prep.py`、`profile.py` | `tests/unit/test_launch_prep.py`、`test_profile.py` | XDG 自愈、锁清理、端口分配、目标粘性 | `pytest tests/unit/test_launch_prep.py tests/unit/test_profile.py` |
| `src/octop_browser/dom/builder.py`、`refs.py` | `tests/unit/test_dom_builder.py`、`test_refs.py` | 四档 DOM、ref 前缀、导航失效 | `pytest tests/unit/test_dom_builder.py tests/unit/test_refs.py` |
| `src/octop_browser/actions/*` | `tests/unit/test_capture.py`、`test_navigate_actions.py` | 截图路径、导航 ref 失效 | `pytest tests/unit/test_capture.py tests/unit/test_navigate_actions.py` |
| `src/octop_browser/install.py`、`playwright_download.py`、`linux_deps.py` | `tests/unit/test_install.py`、`test_playwright_download.py`、`test_linux_deps.py` | 安装阶段、CDN 竞速、包管理器矩阵 | `pytest tests/unit/test_install.py tests/unit/test_playwright_download.py tests/unit/test_linux_deps.py` |
| `src/octop_browser/record/daemon.py` | `tests/unit/test_record_daemon_client.py` | 单行 JSON 协议、不可达降级 | `pytest tests/unit/test_record_daemon_client.py` |
| `src/octop_browser/record/semantic.py`、`replay.py` | `tests/unit/test_record_replay_semantic.py`、`test_record_replay_replay_runner.py` | 事件折叠、变量推断、目标匹配、验证 | `pytest tests/unit/test_record_replay_semantic.py tests/unit/test_record_replay_replay_runner.py` |
| `src/octop_browser/record/store.py`、`skill_generator.py` | `tests/unit/test_record_replay_store_skill.py`、`tests/integration/test_record_replay_e2e.py` | 目录树、manifest 原子写、skill 渲染 | `pytest tests/unit/test_record_replay_store_skill.py tests/integration/test_record_replay_e2e.py` |

## 3. 测试环境隔离与 Mock / Fixture 编写规范

1. **环境变量隔离**：`tests/unit/conftest.py` 的 autouse fixture `_isolate_octop_env` 删除所有 `BROWSER_USE_` 前缀变量（`tests/unit/conftest.py:20`、`:25`），再用 `dataclasses.fields(OctopSettings())` 逐字段重置模块级 `settings` 单例（`:33`）；集成测试刻意不走该 fixture，保留宿主环境。
2. **settings 单例铁律**：单测应新建 `OctopSettings()` 而非改 `settings`（`src/octop_browser/settings.py:184` 注释），否则 import 时捕获的旧值污染断言。
3. **无 Chrome 自动跳过**：`tests/integration/conftest.py:6` 的 `pytest_collection_modifyitems` 在 `find_chrome() is None` 时给所有 integration 项打 skip 标记（`:8`）；空跑或全跳过不算通过。
4. **下游隔离**：录制守护单测只覆盖客户端协议（`tests/unit/test_record_daemon_client.py`），不真起 `start_new_session` 子进程；端到端用临时目录 `TemporaryDirectory(prefix="hbr-smoke-")`（`scripts/record_replay_smoke.py:148`），并把 `profiles_dir`/`screenshots_dir`/`base_dir` 全部指向该临时根（`:65`、`:72`）。
5. **提交禁令**：禁止提交测试生成的临时数据库、日志、向量快照或会话记录；`.coverage`、`htmlcov/`、`dist/`、`__pycache__` 由 `make clean` 清理（`Makefile:170`）。

## 4. 共变耦合与修改清单（Agent Co-Change Playbook）

- **新增源码模块**：在 `src/octop_browser/` 下新建文件必须纳入 `pyproject.toml` 的 `mypy files`（`pyproject.toml:76`）与 `tool.ruff.lint.per-file-ignores` 评估（`:61`），并补对应 `tests/unit/test_*.py` 与本页第 2 节映射。
- **改 CI 矩阵**：`.github/workflows/ci.yml:21` 的 Python 版本与 `pyproject.toml:14` 的 `requires-python` 必须一致。
- **改提交门禁**：`Makefile:121` 的 `all` 目标与 `.githooks/pre-commit:24` 的 `make all` 调用成对修改；`SKIP_PRECOMMIT=1`（`:8`）仅应急，不能用来落红套件。
- **改依赖**：`pyproject.toml:24` 运行依赖与 `uv.lock` 联动；按仓库约定不得新增 Playwright/Selenium 等浏览器驱动作为运行时依赖（`README.md:40`）。

交叉引用：接口变更先看 [入向接口契约全集](../contracts/api-reference.md)，配置键变更看 [配置手册](../contracts/configuration.md)，改死路径前核对 [高危雷区与历史陷阱](pitfalls-and-adr.md)，主机侧黑盒范围见 [认知边界声明](boundary.md)，提交门禁与 SOP 外部页见 [部署与运行时](deployment-and-runtime.md)。
