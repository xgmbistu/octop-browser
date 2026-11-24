---
kind: operations
scope: deployment-and-runtime
status: draft
origin: generated
source_paths: [pyproject.toml, Makefile, src/octop_browser/settings.py, src/octop_browser/profile.py, src/octop_browser/record/settings.py, src/octop_browser/record/store.py, src/octop_browser/cdp/launcher.py, src/octop_browser/mcp_server.py]
symbols: [state_dir, ProfileManager.get_or_create, socket_path, RecordingStore.create, launch_or_attach, _main]
upstream: [../INDEX.md, ../contracts/configuration.md]
downstream: [runbook-and-observability.md, boundary.md]
---

# 部署产物、进程拓扑与持久化目录契约

本仓是 Python 库 + CLI + MCP 服务，不产出容器镜像：发布物是 wheel 与 sdist。运行期状态全部落在用户态目录，浏览器作为独立子进程常驻，MCP 可选以 SSE 模式监听端口。

## 1. 构建资产清单

| 构建文件 | 构建产物 | 注入的关键约束 | 锚点 |
|---|---|---|---|
| `pyproject.toml` | `octop-browser` 1.0.0 wheel + sdist | hatchling `<1.33`；`requires-python >=3.11`；wheel 只含 `src/octop_browser` | `pyproject.toml:1-13,49-53` |
| `pyproject.toml` | 运行依赖 | `websockets>=12.0`、`pydantic>=2.0`、`aiohttp>=3.9`、`mcp>=1.9,<3`（mcp 2.x 删了低层装饰器） | `pyproject.toml:24-31` |
| `Makefile` | `dist/` 产物 | `uv build --out-dir dist .`，无 uv 时 `python -m build --no-isolation` | `Makefile:64-77` |
| `Makefile` | PyPI 发布 | `twine upload --username __token__ --password "$PYPI_TOKEN"`；`publish-test` 走 testpypi | `Makefile:80-106` |
| `.github/workflows/release.yml` | 标签发布 | 与 `release/* → main` 流程配套 | `.github/workflows/release.yml:1` |

运行入口：CLI `[project.scripts] octop-browser = "octop_browser.cli:main"`（`pyproject.toml:49-50`）；MCP `python -m octop_browser.mcp_server` 或 `make mcp`（`Makefile:114-116`）。

## 2. 运行期持久化数据目录树契约

```text
<HOME>/.octop-browser/                    # state_dir()，旧目录 .harness-browser 自动回退
├── profiles/
│   ├── .octop-browser-profiles.json      # profile 名 → CDP 端口账本（旧名 .harness-browser-* 回退）
│   └── <profile-name>/
│       ├── .octop-browser-target.json    # 黏性的 page target id
│       └── <Chrome user-data-dir 内容>    # cookies / localStorage / 登录态
├── screenshots/
│   └── octop-<timestamp_ms>.png          # 或显式 --path 指定的绝对路径
└── record-replay/
    ├── daemon.sock / daemon.pid          # 录制 daemon 的 Unix socket 与 pid
    └── recordings/
        └── <recording_id>/
            ├── manifest.json              # 录制清单（原子写）
            ├── events.jsonl               # 原始事件（append，0600）
            ├── steps.json                 # 语义步骤
            ├── draft.skill.md / final.skill.md
            ├── screenshots/ snapshots/
            └── replay-reports/
                ├── replay_<timestamp>.json
                └── failure_<ts>_<step_id>/{reason.txt,dom_snapshot.json,screenshot.png}
```

权威路径来源：`state_dir()` 双名回退（`src/octop_browser/settings.py:74-92`）、`ProfileManager` 目录与端口分配（`src/octop_browser/profile.py:119-174`）、录制根目录与子目录（`src/octop_browser/record/settings.py:22-38`、`src/octop_browser/record/store.py:28-62`）、daemon socket/pid（`src/octop_browser/record/daemon.py:132-137`）、失败工件目录（`src/octop_browser/record/replay.py:425-467`）。目录权限：`base_dir` 与 `recordings` 为 0700、events.jsonl 为 0600（`src/octop_browser/record/store.py:20-26,56-61`）。

**自愈重定位**：`/root/...` 下的 profile 或不可写目录会被重定位到 `/tmp/octop-browser-profiles-<uid>/<name>`，旧目录改名 `*.stale-<ts>`，且**不**修改全局 `BROWSER_USE_PROFILES_DIR`（`src/octop_browser/cdp/launch_prep.py:123-186`）。

## 3. 进程、子进程与外部网络边界

| 边界类型 | 方向与端口/协议 | 调用模块 | 安全与超时约束 |
|---|---|---|---|
| Chrome 子进程 | `subprocess.Popen([chrome, flags..., "about:blank"])`，本地 `--remote-debugging-port=<port>` | `src/octop_browser/cdp/launcher.py:541-578` | stdout 丢弃、stderr 写未链接临时文件；Linux/Windows 设 `start_new_session=True`，macOS headed 不设以免窗口失焦 |
| CDP WebSocket | 浏览器级与页面级 `ws://<host>:<port>/devtools/...` | `src/octop_browser/cdp/client.py:56-73`、`src/octop_browser/cdp/launcher.py:618-671` | 帧上限由 `cdp_max_message_size` 控制；host 非 loopback 时拒绝启动 |
| CDP HTTP 探测 | `GET /json/version`、`/json`、`/json/new?about:blank`（PUT 优先） | `src/octop_browser/cdp/launcher.py:350-398,674-712` | aiohttp 超时 1–5s；host 全部来自 settings |
| 录制 daemon | `asyncio.start_unix_server` 监听 `daemon.sock`；`start_new_session=True` 拉起 | `src/octop_browser/record/daemon.py:107-129,176-198` | 仅本机文件系统可见；启动前 unlink 旧 socket |
| MCP stdio | 标准输入输出流 | `src/octop_browser/mcp_server.py:526-530` | 默认模式，无端口暴露 |
| MCP SSE（可选） | `MCP_HOST:MCP_PORT`，`/sse` + `/messages/`，uvicorn + Starlette | `src/octop_browser/mcp_server.py:491-525` | 无鉴权层；默认 `0.0.0.0`，部署到共享网络前需外部网关保护 |
| 安装子进程 | `pip`/`uv pip`、`python -m playwright install`、`sudo -n <pkgmgr> install` | `src/octop_browser/install.py:152-175,339-356`、`src/octop_browser/linux_deps.py:190-206` | argv 列表、`shell=False`、`sudo -n` 免交互，失败不回显凭据 |
| Playwright CDN | HTTPS Range 探测 + 二进制下载 | `src/octop_browser/playwright_download.py:46-148` | 4s 探测超时；官方/npmmirror/自定义三源竞速 |

## 4. 生命周期与停机序列

```text
BrowserSession.create() -> launch_or_attach -> CDP connect -> enable Page/DOM/Runtime -> viewport override -> idle controller start
  src/octop_browser/session.py:49-72
close(kill=False) -> CDPClient.close；Chrome 驻留，端口与 target 黏性保留
close(kill=True)  -> idle.reap_now() 或 terminate_browser() -> Browser.close -> 3s 后 pkill 兜底
  src/octop_browser/session.py:149-163、src/octop_browser/cdp/launcher.py:440-494
record daemon shutdown -> 自动 stop 当前录制并生成步骤 -> server.close -> unlink sock/pid
  src/octop_browser/record/daemon.py:84-90,116-129
```

## 5. 共变耦合与修改清单

- 改状态目录名：保留旧名回退（`src/octop_browser/settings.py:74-92`、`src/octop_browser/profile.py:24-30`）并同步本节目录树与 `business/domain-models/index.md`。
- 改 Chrome flag：核对 `BROWSER_USE_NO_SANDBOX/GPU/DEV_SHM_USAGE` 三态与 macOS headed 不 detach 的约束，跑 `tests/unit/test_launcher.py`。
- 改录制目录结构：`RecordingStore` 的 `manifest_path/events_path/steps_path/skill_path` 四处都要改，旧录制会失联，需迁移策略。
- 改 MCP SSE 默认 host：属安全边界变更，同步 `boundary.md` 与 `contracts/configuration.md`。

## 6. 关联文档

- [配置全集](../contracts/configuration.md) · [排障 Runbook](runbook-and-observability.md) · [认知边界](boundary.md)
