# CODEBUDDY.md

This file provides guidance to CodeBuddy Code when working with code in this repository.

## Commands

All targets run through `uv` and the Makefile:

```bash
make all       # ship bar: format + lint + typecheck + test — what pre-commit runs
make format    # ruff check --fix + ruff format on src/ tests/ (rewrites files)
make lint      # ruff check + ruff format --check on src/ tests/
make typecheck # mypy strict on src/
make test      # full suite with coverage (uv run pytest --cov=octop_browser)
make build     # uv build → wheel + sdist
make mcp       # launch the MCP stdio server (python -m octop_browser.mcp_server)
make publish   # local uv publish (prefer /publish skill + Actions; do not use for public releases)
make clean     # remove dist/, .coverage, .mypy_cache/, .ruff_cache/
```

**Git hooks (required before committing):** run **`make install-hooks`** once per clone. It sets `core.hooksPath=.githooks`, so every `git commit` first runs **`make all`** (`format` rewrites files, then lint / typecheck / test). Staged files rewritten by `format` are re-added automatically, so the commit contains the formatted content. This replaces the `pre-commit install` route — `core.hooksPath` overrides `.git/hooks/`, and `make all` is a superset of `.pre-commit-config.yaml` (ruff + ruff-format + mypy, plus tests). Bypass only in emergencies: `SKIP_PRECOMMIT=1 git commit …` or `git commit --no-verify`; never skip hooks to land a red suite.

Useful narrower invocations:

```bash
# Unit tests only — no Chrome required
uv run pytest tests/unit/ -q

# A single test file or test
uv run pytest tests/unit/test_mode.py -q
uv run pytest tests/unit/test_settings.py::test_env_override_browser_mode -q

# Integration tests — auto-skipped when Chrome/Chromium is not on the host
uv run pytest tests/integration/ -v

# Type-check or lint just one path
uv run mypy src/octop_browser/session.py
uv run ruff check src/octop_browser/cdp/

# Install dev extras + enable the commit gate
uv sync --extra dev
make install-hooks
```

`pytest-asyncio` runs in `asyncio_mode = "auto"` (set in `pyproject.toml`) — async test functions need no decorator. `tests/integration/conftest.py` skips the whole integration suite when `find_chrome()` returns None, so unit work on machines without Chrome stays green.

## Architecture

This package wraps Chrome over **pure CDP** (WebSocket, no Playwright) and exposes it three ways: an async Python API, a stateless `browser_tool()` for AI frameworks, and an MCP server. Understanding the call chain matters when changing anything in the launch / connect / DOM path.

### Layered call chain

```
browser_tool()  ──► BrowserSession ──► _InternalCDPSession ──► CDPClient (websockets) ──► Chrome
mcp_server.py   ──┘                          │
                                             └─► launcher.launch_or_attach + get_page_ws_url
```

- `tool_interface.browser_tool(action, profile=..., mode=...)` — stateless dispatch keyed by `profile`. Maintains a `_registry: dict[str, BrowserSession]`; first call per profile creates a session, subsequent calls reuse it. Action names map directly to `BrowserSession` methods via `getattr`.
- `session.BrowserSession` — public async API. Mixes in `HooksMixin` (events: `before_action`, `after_action`, `action_error`; `page_navigated` is reserved and never fired) and accumulates running totals in `metrics_summary()`.
- `session._InternalCDPSession` — owns one `CDPClient` + one `RefCache` per page. Honors `cfg.cdp_ws_url`: if set, **bypasses the launcher entirely** and connects directly to the given WebSocket (used for remote/Docker Chrome).
- `cdp.client.CDPClient` — minimal CDP framing over `websockets.asyncio.client`. `send(method, params)` returns the result; `enable_domain()` enables `Page` / `DOM` / `Runtime` / `Input` after connect.
- `cdp.launcher` — `find_chrome()`, `launch_or_attach()` (re-attach if port is already serving CDP), `_get_ws_url()` polls `http://{cdp_host}:{port}/json/version`, `get_page_ws_url()` picks the first `type==page` target. All HTTP probes go through `aiohttp` and **always read `cdp_host` from settings** — never hardcode `localhost`.

### Configuration: OctopSettings (single source of truth)

`settings.OctopSettings` is a `dataclass` whose every field uses `field(default_factory=lambda: _env_*(...))`. This means **each instantiation re-reads env vars**, which is what `monkeypatch.setenv` in tests relies on. The module-level `settings` singleton (read at import time) is the default everywhere; tests should construct a fresh `OctopSettings()` rather than mutating it.

Env vars (all optional):

| Variable | Default | Used in |
|---|---|---|
| `BROWSER_USE_PROFILES_DIR` | `~/.octop-browser/profiles` | `ProfileManager.__init__` |
| `BROWSER_USE_CDP_HOST` | `localhost` | `launcher._get_ws_url`, `_port_in_use`, `get_page_ws_url`, `session.list_tabs`; also drives `--remote-debugging-address` when non-loopback |
| `BROWSER_USE_CDP_PORT_START` | `9222` | `ProfileManager` port assignment |
| `BROWSER_USE_MODE` | `auto` | resolved via `mode.resolve_headless()` |
| `BROWSER_USE_CHROME_BIN` | auto-detect | `launcher.find_chrome` (checked before path search) |
| `BROWSER_USE_CDP_TIMEOUT` | `30.0` | `CDPClient` send timeout |
| `BROWSER_USE_LAUNCH_RETRIES` / `BROWSER_USE_LAUNCH_DELAY` | `20` / `0.25` | launcher polling |
| `BROWSER_USE_CDP_WS_URL` | — | `_InternalCDPSession.connect` direct-connect path |
| `BROWSER_USE_IDLE_TIMEOUT_MINUTES` | `0` | local profile idle reaper; real CDP commands refresh the deadline |

The MCP server has no per-tool `inputSchema` field for these — they are passed via the standard `mcpServers.<name>.env` block in client config. Do not add them to the tool schema.

### Browser mode resolution (octop_browser/mode.py)

Three modes — `auto` / `headed` / `headless`. Resolution priority in `BrowserSession.create()`:

1. Explicit `headless=True/False` argument (legacy escape hatch, wins outright)
2. Explicit `mode=` argument
3. `cfg.browser_mode` (from `OctopSettings`, which reads `BROWSER_USE_MODE`)

`auto` calls `has_desktop_environment()`: True on macOS/Windows always; on Linux requires `$DISPLAY` or `$WAYLAND_DISPLAY`. The result is fed to `resolve_headless()`. `_build_flags` only appends `--headless=new` when the resolved bool is True.

### DOM output: 4 levels and the ref system

- `dom.builder.DOMBuilder` produces `minimal` (~50 tok) / `interactive` (~200–500 tok) / `full` (~1000–3000 tok) / `structured` (JSON) views from a CDP `DOM.getDocument` snapshot.
- `dom.refs.RefCache` issues stable refs like `btn_2`, `inp_search` mapping `ref → CDP nodeId`. **Refs are invalidated on navigation** — `nav_actions.navigate` / `go_back` / `go_forward` / `reload` clear the cache. Any new navigation-class action MUST do the same or you'll hand the agent stale node IDs.
- Token estimate is `len(content) // 4` — keep this when adding new actions that build text content.

### Profiles and login persistence

`profile.ProfileManager` allocates one `Chrome --user-data-dir` per profile name under `cfg.profiles_dir`, with `cdp_port = cfg.cdp_port_start + index`. This is the entire login-persistence story: same profile name → same data dir → cookies and storage reused. Don't add ad-hoc paths for cookies/auth — go through `Profile`.

### Hooks and metrics

`HooksMixin` is what `BrowserSession` mixes in. Every action goes:

```
_fire("before_action", {...}) → action body → _record(result)
                                                  └─► _fire("after_action", metrics)  (or "action_error")
```

`ActionMetrics` (`models.py`) carries `duration_ms`, `dom_nodes_scanned`, `estimated_tokens`, `screenshot_size_kb`. `BrowserSession.metrics_summary()` aggregates totals across the session.

### Skill files (Claude Code / agent-facing)

Live at `skills/octop-browser/SKILL.md` (English) and `skills/octop-browser-zh/SKILL.md` (Chinese). They use the standard YAML-frontmatter format (`name`, `description`, `allowed-tools`) and are designed to be `cp -r`'d into other agent projects. Keep these in sync when the public surface (env vars, modes, action list) changes.

## Project conventions

- **Commit gate**: `make install-hooks` once per clone; `make all` must be green before every commit (the hook enforces it). See [Commands](#commands).
- **Docs language**: README is bilingual (`README.md` canonical English + `README_CN.md`); `CHANGELOG.md` and `CONTRIBUTING.md` are Chinese-only by deliberate choice.
- **ruff**: `line-length = 88`, lint selects `E F I N W`. Do not raise the line length to dodge wraps.
- **mypy**: `strict = true`, `python_version = "3.11"`. New code must type-check under strict mode; reach for `from __future__ import annotations` (already used everywhere) before adding `# type: ignore`.
- **No Playwright, no Selenium**: the dependency story is just `websockets`, `aiohttp`, `pydantic`, `mcp`. Don't add browser drivers.
- **`localhost` is never hardcoded** — always go through `cfg.cdp_host`. A dedicated regression hazard if you forget.
- **Repository URL** in docs is `https://github.com/TencentCloud/octop-browser.git`.

## Branching & release

Follow Octop-style flow documented in `CONTRIBUTING.md`:

```
feature/* ──PR──► develop ──► release/x.y.z ──PR──► main ──tag v*──► publish
```

Agent publish: `.cursor/skills/publish` (`/publish <version>`). Never push directly to `main`/`develop`.



<!-- wally-init:entry:start -->
## 先判断是否属于开发任务

- 必须走开发 SOP：实现功能、修复缺陷、重构、性能优化，以及改变程序行为的接口、数据结构、配置、脚本、Agent 规则/Skill 等修改。开发需求中的方案、契约和配套文档也属于该任务；不能因为改动少或暂时只写文档而豁免。用户明确要求开始/继续 SOP 时按任务上下文执行。
- 直接处理、不创建 SOP 任务：问题咨询、原理解释、只读分析/独立审阅、状态查询、与开发无关的对话，以及纯文档措辞整理，以及暂存/提交已有改动（git add / git commit）。先核对实际请求和 diff；提交操作本身不要求新建 SOP 任务，不因已有改动包含代码而倒补六阶段产物；仍须遵守已有开发任务的交付门禁、项目提交规范与用户授权。
- 是否进入 SOP 取决于当前请求的工作性质，不取决于问句形式、文件扩展名、改动行数或当前分支是否已有任务。咨询过程中用户转而要求开发修改时，再进入开发 SOP；混有代码、运行配置、规则或行为变更时不套用纯文档豁免。已有开发任务的代码交付也不能通过改称“只做提交”绕过适用门禁；工具 Hook 对 Git 操作中立放行不代表门禁已完成或已获得 Commit/Push 授权。

## 开发任务的 SOP 启动检查

确认属于开发任务后，任务简单、改动少、只加一个页面都不是跳过 SOP 的理由。读取本入口不代表已完成任务路由；在探索实现方案、编辑业务文件或执行变更命令前，必须完成：

1. 读取 `.wally/core/entry.md`，运行 `git branch --show-current`，按分支定位任务。无任务时先读 `.wally/profiles/project.md`，询问用户是否为本次 SOP 新切一条分支，等答复后再用 `.wally/scripts/create_task.py` 在选定分支上创建任务。不要猜测任务目录、套用其他任务，或把当前分支直接当成任务分支。
2. 运行 `python3 .wally/scripts/sop_context.py`，读取它实际输出的任务 overview、版本规则、项目配置和当前阶段。输出缺文件、多任务匹配或其他错误时先修复；不能绕过并继续实现。
3. 在首次工作说明中报告真实的分支、任务目录、规则版本和当前阶段；无任务时如实说明需要创建。不得未读取就声称已读取。
4. 进入每个阶段前读取对应阶段文件与所需绑定规则，填写 Clarify 和 Plan 后再实现。压缩上下文、恢复会话、切换分支及委派子 Agent 后重新定位；委派时明确传入任务目录、规则版本和阶段，子 Agent 也执行本检查。

5. 知识库先读 `.wally/docs/INDEX.md`，按任务绑定版本的 `core/knowledge.md` 读取、更新和验收相关页。索引缺失时回查 Profile 的实际文档路径与源码，并记录缺口。

## 阶段与完成条件

仅用于已确认属于开发工作的新任务；咨询与轻量文档操作不激活本流程，已有开发任务始终以其绑定版本为准，本概览不能替代历史任务契约。

- 01 Clarify：目标、范围、成功判据、关键约束、未决业务问题。先读本规则版本中的 `clarify.md`；已有用户输入可直接整理与校验，不重复访谈。
- 02 Plan：影响范围、调用链/状态机、数据及协议兼容性、UT 和 IT 设计、风险与回滚。
- 03 Implement + UT + Docs：先遵守本任务快照 `_rules/rules/` 中的项目规则，再 Red → Green → Refactor → 增量覆盖率 → Docs → 增量 CR。适用门禁未通过不得 Deploy。
- 04 Deploy：环境、基线、部署范围、生效验证、回滚。热更前保留缺陷基线。
- 05 IT：按 Plan 执行，核验逐用例结果与总体门禁，完成缺陷 A/B。
- 06 Review + Commit：复核变更后的证据、时间记录和遗留风险，完成外部系统/资源处置及提交准备，再按授权执行 Git。

新任务始终保留 01–06 六阶段。 显式标记 `readiness: pending` 的方法即使有 guide/command 也不完整，标记 BLOCKED 并按 `gaps` 向用户询问补齐，不能自动跳过；只有 ready 方法（或未带 readiness 的旧配置）按下述 command/guide 规则判断，ready 不等于执行通过。每次进入 Deploy/IT 前读取本任务 `execution.json`：对应 command 与 guide 都为空时自动跳过，不准备环境、不调用工具；使用创建任务时已生成的 SKIPPED 记录与零耗时行。配置了任一方法则按客户实际命令/指南执行，缺环境、权限、工具或执行失败均不得伪装成未配置而跳过。跳过不是通过，必须在 Review 说明未完成部署/集成验证；其他适用门禁继续执行。历史任务按自己的绑定版本恢复，不因新规则改写。

在开始 Implement、Deploy、IT 的实际操作前，分别运行 `python3 .wally/scripts/sop_context.py --checkpoint implement`、`--checkpoint deploy`、`--checkpoint it`。Clarify/Plan 未记录完成或仍为空模板，以及用户准备执行未配置方法的 Deploy/IT 时，必须先展示缺失项、拟执行操作和影响，等待用户确认后才继续。默认自动跳过未配置的 Deploy/IT 不需要确认；确认例外也不提供执行方法，仍须取得真实命令/指南，不能猜测。

检查点退出码 3 表示等待确认。使用提问工具或对话清楚展示原因与 `CONFIRM SOP <编号>`；用户需在聊天中明确发送该文本，输入 Hook 才会记录确认。Agent 不得自行发送确认、修改 `.wally/local/sop-confirmations.json`、伪造产物或反复重试。拒绝、无回复、无效或过期编号均不视为确认。同任务/阶段且相关材料未变时不重复询问；分支、任务、阶段、绑定规则或相关材料变化后重新检查。缺少输入 Hook 的环境只能保留等待状态或先补齐前置材料，不能声称自动确认。

确认允许带缺项继续当前阶段，须在 overview 记录实际用户授权、缺失证据和未验证范围；不自动勾选前置阶段，不把 SKIPPED/未验证改为通过，不免除其他适用验收。质量要求由阶段检查与 Review 持续核验。普通工具操作不因 SOP 白名单或上下文错误被强制拒绝；Shell/MCP 不做全面拦截，阶段检查点由 Agent 主动调用，已有客户端权限和用户授权继续生效。

Hook 负责加载上下文，并仅对已识别业务编辑触发上述两类确认；普通 Shell、Git、date 等不做 SOP 白名单拦截。实现/部署/IT 前必须主动运行对应 `--checkpoint`，等待明确用户确认或补齐前置条件后继续。确认只允许带已披露缺项继续，不能把未验证阶段记为完成。Hook 未启用、不支持或未受信任时保留指令约束，不声称强制覆盖。已有客户端权限、用户约束与授权边界继续生效。
<!-- wally-init:entry:end -->
