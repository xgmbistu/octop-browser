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
## Classify the request before entering development SOP

- Development SOP is required for feature implementation, bug fixes, refactoring, performance work, and changes to runtime behavior, APIs, data structures, configuration, scripts, Agent rules or Skills. Design, contracts and accompanying documentation within that development request remain part of its SOP; a small change or a document-only intermediate step is not an exemption. Follow task context when the user explicitly starts/resumes SOP.
- Handle directly without creating an SOP task: questions, explanations, read-only analysis/standalone review, status checks, unrelated conversation, and purely editorial documentation work, and staging/committing existing changes (git add / git commit). Inspect the actual request and diff; the Git operation itself does not require a new SOP task or retroactive six-phase artifacts, even when existing changes include code. Honor existing development delivery gates, project commit rules and user authorization.
- Scope follows the current requested work, not question phrasing, file suffix, line count, or whether the branch already has a task. Enter SOP if consultation turns into a development request. Mixed code, runtime configuration, rule or behavior changes are not documentation exemptions. Calling an existing development delivery a commit-only operation does not waive its applicable gates. A neutral Git hook result neither proves gate completion nor grants Commit/Push authorization.

## Mandatory checkpoint for development tasks

Once the request is classified as development, small changes, simple features, or adding one page do not exempt it from SOP. Reading this root file does not complete task routing. Before investigating implementation, editing business files, or executing change commands:

1. Read `.wally/core/entry.md` and run `python3 .wally/scripts/sop_context.py` to route by the actual branch. Reuse any current routing result and look up only missing fields.
2. For a matched task, use the script output to load the task overview, bound rules, project policy, and current phase. If there is no task and the user has not chosen a branch, ask for the branch as directed by the entry and wait. Routing stops there for this turn. Resolve other issues such as missing files or ambiguous matches before implementation.
3. In the first work update, report the actual branch, task directory, rules version, and current phase. If a task is pending creation, label the version as the currently installed version. Report only verified facts.
4. Before each phase, read its artifact and required bound rules. Complete Clarify and Plan before implementing. Repeat routing after compaction, resumption, branch changes, or delegation. Explicitly pass task, bound version, and phase to subagents; they follow this checkpoint too.

5. For knowledge, start at `.wally/docs/INDEX.md`; read and update relevant pages under the task-bound `core/knowledge.md` policy. Missing indexes fall back to actual Profile documentation paths and source; record gaps.
6. Repository-managed Skills live canonically under `.agents/skills/` (`clarify`, `sop-aware-code-review`, `wally-open-cli`), with per-skill symlinks into mainstream IDE/CLI `skills/` directories. Upon entering `01 Clarify` (unless formally skipped by SOP), read `.agents/skills/clarify/SKILL.md` together with the task-bound `core/clarify.md` before asking questions or editing `01-clarify.md`.

## Phases and completion criteria

For new development tasks only. Consultation and lightweight documentation operations do not activate this workflow. Existing tasks always follow their bound version; this outline does not replace a historical task contract.

- 01 Clarify: measurable goals, scope, success criteria, key constraints, and unresolved business questions. Read `.agents/skills/clarify/SKILL.md` and this version's `clarify.md`; validate sufficient inputs without repeating interviews.
- 02 Plan: impact, call chains/state machines, data/protocol compatibility, UT/IT design, risks, and rollback.
- 03 Implement + UT + Docs: follow project rules under `.wally/rules/`, then Red → Green → Refactor → incremental coverage → Docs → incremental CR. Applicable gates must pass before Deploy.
- 04 Deploy: environment, baseline, scope, effective-version verification, and rollback. Preserve defect baselines before hot updates.
- 05 IT: execute Plan, inspect individual results and aggregate gates, and close defect A/B verification.
- 06 Review + Commit: read `.agents/skills/sop-aware-code-review/SKILL.md` (also applicable to 03 incremental CR), recheck changed evidence, time logs, and residual risk; handle authorized external systems/resources and prepare the commit before authorized Git operations.

### Phase Dependency Summary (Skills / Rules / Tools & Checkpoints)

| Phase | Skill (`.agents/skills/`) | Rules (Bound Version / Task Snapshot) | Tools / Checkpoints |
|---|---|---|---|
| 01 Clarify | `clarify/SKILL.md` | `core/clarify.md`, `core/gates.md`, `core/knowledge.md` | `sop_context.py`, `create_task.py`, `date` |
| 02 Plan | — | `core/workflow.md`, `core/gates.md`, `core/knowledge.md` | `.wally/docs/INDEX.md`, `date` |
| 03 Implement + UT + Docs | `sop-aware-code-review/SKILL.md` (incremental CR) | `.wally/rules/`, `core/gates.md`, `core/knowledge.md` | `sop_context.py --checkpoint implement`, UT/coverage commands |
| 04 Deploy | Optional `wally-open-cli/SKILL.md` | `core/gates.md` | `sop_context.py --checkpoint deploy`, task snapshot `execution.json` |
| 05 IT | Optional `wally-open-cli/SKILL.md` | `core/gates.md` | `sop_context.py --checkpoint it`, task snapshot `execution.json` |
| 06 Review + Commit | `sop-aware-code-review/SKILL.md` | `.wally/review.md`, `.wally/commit.md`, `core/gates.md` | Client `token_report.py`, `git`, `date` |

New tasks always retain all six phases 01–06. A method explicitly marked `readiness: pending` is incomplete even with a guide/command: mark it BLOCKED and request the missing `gaps` from the user; do not auto-skip it. Only ready methods (or legacy configurations without readiness) use the command/guide rule below; ready does not mean execution passed. Before Deploy/IT read this task's `execution.json`: when both command and guide are empty, automatically skip without preparing environments or invoking tools; retain the generated SKIPPED records and zero-duration rows. If either method is set, execute the customer instructions. Missing environment, permission, or tools and execution failures must not be disguised as unconfigured skips. Skipped is not passed: disclose missing deployment/integration verification in Review and enforce other applicable gates. Historical tasks continue under their own bound rules.

Before actual Implement, Deploy or IT work, run `python3 .wally/scripts/sop_context.py --checkpoint implement`, `--checkpoint deploy` or `--checkpoint it`, respectively. If Clarify/Plan is incomplete or still an empty template, or the user intends to execute Deploy/IT without a configured method, explain the missing evidence, proposed action and impact, then wait for explicit user confirmation. Automatically skipping an unconfigured Deploy/IT phase requires no confirmation. An exception does not supply an execution method: obtain real commands/guidance rather than guessing.

Checkpoint exit code 3 means awaiting confirmation. Show the reason and `CONFIRM SOP <id>` once in the reply. Do not also call a question tool or emit another question card for the same decision; the chat UI turns that text into one decision card. The user must still explicitly send that exact text in chat for the input Hook to record approval. Never send it on the user's behalf, edit `.wally/local/sop-confirmations.json`, fabricate artifacts or retry in a loop. Rejection, silence, invalid or stale IDs are not approval. Do not ask again for the same task/phase with unchanged evidence; recheck after changes to branch, task, phase, bound rules or relevant evidence. Without the input Hook, remain pending or satisfy the prerequisites; never claim automatic approval.

Confirmation permits continuation with the stated gaps. Record the actual user authorization, missing evidence and unverified scope in the overview. Do not auto-complete prerequisites or turn SKIPPED/unverified work into a pass; all other acceptance criteria still apply. Phase checks and Review continue to evaluate quality. General tools are not denied by an SOP command allowlist or context error. Shell/MCP are not comprehensively intercepted: the Agent must invoke phase checkpoints explicitly. Existing client permissions and user authorization remain effective.

The Hook loads context and requests the two scoped confirmations for recognized business edits. General Shell, Git and date commands are not restricted by an SOP allowlist. Explicitly run the corresponding --checkpoint before Implement/Deploy/IT, then await user confirmation or satisfy the prerequisites. Confirmation permits disclosed gaps, never a false completion claim. Without enabled, trusted, supported Hooks these remain instructions, not comprehensive interception. Existing client permissions, user constraints and authorization remain effective.
<!-- wally-init:entry:end -->
