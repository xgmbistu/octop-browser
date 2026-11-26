---
kind: operations
scope: deployment-and-runtime
status: draft
origin: generated
source_paths: [pyproject.toml, Makefile, src/octop_browser/mcp_server.py, src/octop_browser/profile.py, src/octop_browser/settings.py, src/octop_browser/record/store.py, src/octop_browser/record/settings.py]
symbols: [hatchling, state_dir, ProfileManager, RecordingStore, RecordReplaySettings, _main, socket_path, pid_path]
upstream: [INDEX.md, contracts/configuration.md]
downstream: [operations/runbook-and-observability.md, operations/boundary.md]
---

# 部署产物、进程拓扑与持久化目录契约

本仓是 PyPI Python 库（`octop-browser` 1.0.0），**不是常驻 Web 服务**：无 Dockerfile、无 Compose、无 Kubernetes/Helm 清单、无部署脚本（`.wally/config.json` 的 deploy `gaps` 已如实登记该事实）。运行形态是短命 CLI 进程、MCP stdio/SSE 进程、可选录制守护进程与 Chromium 子进程，持久化全部落在用户主目录的状态目录。

## 1. 构建资产清单

| 构建文件（`路径`） | 构建产物 | 注入的关键目录与运行用户约束 |
|---|---|---|
| `pyproject.toml`（`hatchling`，`:5`） + `Makefile build`（`Makefile:65`） | wheel + sdist，输出到 `dist/` | `packages = ["src/octop_browser"]`（`pyproject.toml:52`），含 `py.typed` 与 `record/injected/recorder.js` |
| `[project.scripts]`（`pyproject.toml:49`） | `octop-browser` 控制台脚本 | 入口 `octop_browser.cli:main` |
| `Makefile mcp`（`:115`） | 无产物，直接 `python -m octop_browser.mcp_server` | 需安装运行依赖；SSE 模式另需宿主提供 `uvicorn`/`starlette`（未列入 `pyproject.toml:24`） |
| `make publish` / `make publish-test`（`Makefile:82`、`:104`） | 上传到 PyPI / TestPyPI | 读 `PYPI_TOKEN` 或交互输入（`Makefile:21`、`pyproject.toml:44`） |
| `skills/octop-browser/SKILL.md`、`skills/octop-browser-zh/SKILL.md` | Agent 技能文件 | 随源码发布，需与公开接口同步 |

## 2. 运行期持久化数据目录树契约（Disk Layout Contract）

```text
$HOME/.octop-browser/                       # state_dir() 首选（src/octop_browser/settings.py:78）
├── profiles/                              # BROWSER_USE_PROFILES_DIR 默认
│   ├── .octop-browser-profiles.json       # profile 名 → cdp_port（src/octop_browser/profile.py:25）
│   └── <profile>/
│       ├── <Chrome user-data-dir 内容>     # cookies / storage / login 状态
│       └── .octop-browser-target.json     # 粘性 page targetId（src/octop_browser/profile.py:24）
├── screenshots/                           # BROWSER_USE_SCREENSHOTS_DIR 默认
│   └── octop-<timestamp_ms>.png           # 或 screenshot(path=...) 指定路径
└── record-replay/                         # BROWSER_RECORD_REPLAY_DIR 默认
    ├── daemon.sock / daemon.pid           # 录制守护 IPC（src/octop_browser/record/daemon.py:132）
    └── recordings/<recording_id>/
        ├── manifest.json                  # 临时文件 + replace() 原子写
        ├── events.jsonl                   # 追加写，chmod 0o600
        ├── steps.json                     # 语义步骤
        ├── draft.skill.md / final.skill.md
        ├── screenshots/  snapshots/  replay-reports/
        └── replay-reports/
            ├── replay_<Ymd_HM_S>.json
            └── failure_<stamp>_<step_id>/{reason.txt, dom_snapshot.json, screenshot.png}
```

录制根目录由 `RecordReplaySettings.base_dir` 决定（`src/octop_browser/record/settings.py:24`），其 `daemon.sock` 与 `daemon.pid` 由 `socket_path` / `pid_path` 定位（`src/octop_browser/record/daemon.py:132`、`:136`）。旧安装若仅存在 `$HOME/.harness-browser`，`state_dir()` 会复用该目录以免遗留登录态与录制失联（`src/octop_browser/settings.py:89`）；对应 legacy 状态文件名见 `src/octop_browser/profile.py:29`。容器/根会话下 `prepare_chrome_launch` 可能把 profile 重定向到 `/tmp/octop-browser-profiles-{uid}/<name>`（`src/octop_browser/cdp/launch_prep.py:123`、`:166`），此时 Chrome 的 `--user-data-dir` 不再位于上图的 `profiles/` 下。

## 3. 进程、子进程与外部网络边界

| 边界类型 | 方向与端口 / 协议 | 调用模块（`路径:行号`） | 安全与超时约束 |
|---|---|---|---|
| CLI 主进程 | 短命，`asyncio.run(_run_action/...)` | `src/octop_browser/cli.py:645` | 退出后 Chrome 因 `start_new_session` 存活 |
| MCP stdio | stdin/stdout JSON-RPC 帧 | `src/octop_browser/mcp_server.py:527` | 无鉴权 |
| MCP SSE | `GET /sse` + `POST /messages/`，`MCP_HOST:MCP_PORT` | `:515`、`:516`、`Makefile:115` | 默认监听 `0.0.0.0`，无鉴权层 |
| 录制守护 | Unix socket `daemon.sock`，单行 JSON | `src/octop_browser/record/daemon.py:114`、`:160` | `timeout=5.0`，socket 启动前 `unlink` |
| Chrome 子进程 | `subprocess.Popen(cmd, env, start_new_session)` | `src/octop_browser/cdp/launcher.py:578` | argv 固定列表、禁 `shell=True`；stderr 写临时文件 |
| CDP HTTP | `aiohttp GET /json/version`、`/json`、`PUT /json/new` | `:369`、`:677`、`:695` | 主机取 `cfg.cdp_host`，超时 1–5s |
| CDP WebSocket | `websockets.connect(ws_url, max_size=...)` | `src/octop_browser/cdp/client.py:67` | 帧上限 32 MiB，命令超时 30s |
| Playwright 安装子进程 | `pip` / `playwright install` / 包管理器 | `src/octop_browser/install.py:159`、`:339` | `sudo -n --` 免挂起 |
| 出向下载 | `urllib` Range GET 到 Playwright CDN | `src/octop_browser/playwright_download.py:86` | `timeout=4.0` |
| 强杀兜底 | `pkill -9 -f user-data-dir=<dir>` | `src/octop_browser/cdp/launch_prep.py:195` | 仅 POSIX，`shell=False`，`timeout=5` |

## 4. 部署就绪度与外部权威页边界

`.wally/config.json` 的 `deploy` 段 `readiness: "pending"` 且列出 5 项 `gaps`：无部署入口、无目标测试环境、无部署后验证、无回滚路径、部署凭据来源未定义；`it` 段 `readiness: "ready"`，命令 `uv run pytest tests/integration/ -v`。对应 SOP 外部页仅作链接、不由 CodeWiki 改写：[开发环境](../devops/env.md)、[测试环境部署](../devops/test-env-deploy.md)、[集成测试](../integration_test/integration_test.md)、[单元测试规范](../unittest/unittest.md)、[API 索引](../apis/index.md)、[数据库与 SQL](../sqls/README.md)。这些页与 `.wally/docs/INDEX.md` 的排除理由统一登记在 `.wiki-meta.json` 的 `excludedPages`。

## 5. 共变耦合与修改清单（Agent Co-Change Playbook）

- **新增磁盘状态文件**：`RecordingStore.create`（`src/octop_browser/record/store.py:45`）、`recording_summary`（`:135`）与本页目录树同步；若该状态影响概览，还需在 [认知边界](boundary.md) 声明。
- **修改 `state_dir()`**：`src/octop_browser/settings.py:78` 的 legacy 回退（`:89`）与 `profile.py` 的 legacy 文件名（`:29`）一起核查，否则老安装端口与目标绑定漂移。
- **修改进程边界**：`launch_or_attach` 的 `popen_kwargs`（`src/octop_browser/cdp/launcher.py:566`）与 [Chromium 进程契约](../integrations/downstream/chromium-process.md) 的 argv 表联动；macOS 有头模式故意不设 `start_new_session`（`:575`）。
- **修改 SSE 依赖**：`MCP_PORT`/`MCP_HOST`（`src/octop_browser/mcp_server.py:491`、`:499`）、`pyproject.toml` 依赖表与本页第 3 节同步；当前 `uvicorn`/`starlette` 未在依赖中声明，SSE 模式属宿主环境约定。
