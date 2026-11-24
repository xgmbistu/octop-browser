---
kind: component
scope: chromium-install-bootstrap
status: draft
origin: generated
source_paths: [src/octop_browser/install.py, src/octop_browser/playwright_download.py, src/octop_browser/linux_deps.py]
symbols: [chromium_executable, verify_chromium, ensure_chromium, install_chromium_stream, _stream_install_deps, build_download_candidates, race_download_sources, build_install_steps, detect_package_manager]
upstream: [../INDEX.md, cli.md]
downstream: [cdp-layer.md, ../integrations/downstream/playwright-cdn.md, ../business/wf-chromium-bootstrap.md]
---

# 浏览器安装引导组件

本组件是一次性引导设施：用 Playwright 作为「下载器」把 Chromium 拉入标准缓存，再用原生包管理器补齐系统库与 CJK 字体，最后以 `chrome --version` 作为唯一成功门禁。Playwright **不是运行时依赖**，浏览器始终由 CDP 直接驱动（见 [`cdp-layer.md`](cdp-layer.md)）。

## 1. 边界与成功判定不变量

1. **验证即门禁**：安装流水线每一步都是 best-effort，只有 `verify_chromium()` 返回 `(True, 版本串)` 才算成功（`src/octop_browser/install.py:230-272`）。
2. **确定性防线**：`OCTOP_SKIP_PLAYWRIGHT_PIP=1`（兼容旧名 `HARNESS_SKIP_PLAYWRIGHT_PIP`）时禁止 pip 安装，直接报可操作错误（`src/octop_browser/install.py:76-78,123-125,317-325`）。
3. **无 shell 注入**：所有子进程用 `subprocess.run(cmd_list, shell=False)` 或 `create_subprocess_exec`，命令来自代码内白名单（`src/octop_browser/install.py:159-164`、`src/octop_browser/linux_deps.py:195-204`）。
4. **不回显凭据**：安装事件只透传子进程 stdout/stderr 行，无密钥字段；包管理器的 `sudo -n` 永不交互等待（`src/octop_browser/linux_deps.py:190-206`）。

## 2. 安装流水线调用树

```text
ensure_chromium() -> src/octop_browser/install.py:280-369
  ├─ [快路径] chromium_executable() 存在且 verify_chromium() OK -> 直接返回 True : :293-300
  ├─ [修复路径] 二进制存在但坏 -> _run_install_deps() 后重新 verify : :301-313
  ├─ [引导] _playwright_available() 为假 -> _run_pip_install() : :316-330
  │    └─ uv pip install --python sys.executable 优先，python -m pip 兜底 : :128-142
  ├─ [下载] race_download_sources(build_download_candidates()) : :332-356
  │    └─ 每个候选源各跑一次 python -m playwright install chromium : :178-179,339-345
  ├─ [补依赖] _run_install_deps() -> build_install_steps() : :361,186-222
  └─ [验证] verify_chromium() -> [exe, "--version"], timeout=10 : :364-369
```

流式版本 `install_chromium_stream()`（`src/octop_browser/install.py:486-620`）与同步版本步骤一致，但每步产出 `InstallEvent` 事件字典；子进程逐行读出后立即 yield，消费者断开时通过 `is_disconnected` 回调 `proc.kill()`（`src/octop_browser/install.py:377-420`）。

## 3. CDN 竞速与请求字典

| 候选源 | 构造规则 | 探测请求 | 源码锚点 |
|---|---|---|---|
| `custom` | `PLAYWRIGHT_DOWNLOAD_HOST` 非空且非官方别名 | `GET {host}/`，Header `Range: bytes=0-1023` | `src/octop_browser/playwright_download.py:18,46-80,83-105` |
| `npmmirror` | 固定 `https://cdn.npmmirror.com/binaries/playwright` | 同上 | `src/octop_browser/playwright_download.py:16-17,62-71` |
| `official` | `host=""`，子进程环境删掉 `PLAYWRIGHT_DOWNLOAD_HOST` | `GET https://cdn.playwright.dev/` | `src/octop_browser/playwright_download.py:73-79,165-172` |

`race_download_sources()` 用 `ThreadPoolExecutor(max_workers=3)` 并发测 TTFB 并按秒数升序返回；全失败时退回原目录顺序（`src/octop_browser/playwright_download.py:108-148`）。5xx 探测视为失败，HTTPError 4xx 不算失败（`src/octop_browser/playwright_download.py:92-105`）。子进程环境再叠加 `NO_COLOR=1`、`FORCE_COLOR=0`、`NODE_DISABLE_COLORS=1` 防止 Node 安装器输出 ANSI 干扰日志解析（`src/octop_browser/playwright_download.py:151-162`）。

## 4. 系统依赖与字体包矩阵

`build_install_steps()` 先探测包管理器，按 `apt-get → dnf → yum → zypper → pacman → apk` 顺序取首个可用项（`src/octop_browser/linux_deps.py:23-25,182-187`）。

| 管理器 | 库集合规模 | 安装前缀 | CJK 字体步骤 | 源码锚点 |
|---|---|---|---|---|
| `apt-get` | 16 个库 | `apt-get install -y` + `DEBIAN_FRONTEND=noninteractive` | `fonts-noto-cjk` | `src/octop_browser/linux_deps.py:28-46,143-144,251-260` |
| `dnf` / `yum` | 各 16 个库 | `dnf/yum install -y` | 3 个候选字体逐个 optional 安装 | `src/octop_browser/linux_deps.py:47-82,145-154` |
| `zypper` / `pacman` / `apk` | 各 15–16 个库 | 各自 native 前缀 | 单字体包 optional | `src/octop_browser/linux_deps.py:83-137,155-157,160-169` |

`apt-get` 环境先跑 `playwright install-deps chromium`（它知道 Ubuntu 24 的 `*t64` 包名），再跑原生 apt 兜底（`src/octop_browser/linux_deps.py:238-248`）。字体步骤全部标 `optional=True`，任一包缺失不翻转整体结果（`src/octop_browser/linux_deps.py:263-285`）。

## 5. 流式事件字典与下游消费

`InstallEvent` 是 `TypedDict(total=False)`，四键互斥语义：`log` 为增量日志行；终态只发 `done` + `success`，可附 `error`（`src/octop_browser/install.py:81-91`）。MCP 侧 `_handle_install_browser()` 聚合所有 `log` 行，终态拼成 `OK` 或 `FAILED: <error>` 返回（`src/octop_browser/mcp_server.py:372-388`）。CLI `install-browser` 使用同步版本，不消费事件流（`src/octop_browser/cli.py:637-643`）。

出向依赖的协议与包管理器边界见 [`../integrations/downstream/playwright-cdn.md`](../integrations/downstream/playwright-cdn.md)，业务闭环见 [`../business/wf-chromium-bootstrap.md`](../business/wf-chromium-bootstrap.md)。

## 6. 共变耦合与修改清单

- **改包集合**：同步 `manual_hint()` 展示的前 6 个包名（`src/octop_browser/linux_deps.py:209-217`）并跑 `tests/unit/test_linux_deps.py`。
- **改 CDN 竞速算法**：`PLAYWRIGHT_DOWNLOAD_HOST` 官方别名集合必须保持排除（`src/octop_browser/playwright_download.py:21-27`），跑 `tests/unit/test_playwright_download.py`。
- **改验证命令**：`verify_chromium()` 的返回码 127 / `shared libraries` 分支给出缺失 `.so` 提示，改命令时保留该诊断（`src/octop_browser/install.py:256-272`），跑 `tests/unit/test_install.py`。
- **改事件字段**：同步 MCP 聚合逻辑与 `operations/runbook-and-observability.md` 的安装失败决策树。
