---
kind: downstream-contract
scope: playwright-installer
status: draft
origin: generated
source_paths: [src/octop_browser/install.py, src/octop_browser/playwright_download.py]
symbols: [ensure_chromium, install_chromium_stream, verify_chromium, chromium_executable, InstallEvent, build_download_candidates, race_download_sources, env_for_candidate, plain_cli_env]
upstream: [integrations/index.md, architecture/mcp-server.md]
downstream: [integrations/downstream/linux-system-deps.md]
---

# 下游出向接口契约：Playwright 安装器与 CDN 竞速

`install-browser` 一次性借用 Playwright 下载 Chromium 二进制，Playwright **不是**运行时依赖。出向面包括：pip/uv 子进程、`python -m playwright install chromium` 子进程、`urllib` 对 CDN 的 1 KiB Range 探测，以及 `chrome --version` 验证子进程。流式入口 `install_chromium_stream()` 逐条产出 `InstallEvent` 字典，是 MCP `install_browser` 工具的上游。远端 CDN 与 Playwright 内部实现属仓库外黑盒，见 [认知边界](../../operations/boundary.md)。

## 1. 封装定位与连接契约

| 契约项 | 精确值 / 规则 | 源码锚点 |
|---|---|---|
| 二进制落点 | `~/.cache/ms-playwright/chromium-<rev>/`（Linux）、`$PLAYWRIGHT_BROWSERS_PATH`（设置时） | `src/octop_browser/cdp/launcher.py:84` |
| 同步入口 | `ensure_chromium(quiet=True) -> bool` | `src/octop_browser/install.py:280` |
| 流式入口 | `install_chromium_stream(is_disconnected=None) -> AsyncGenerator[InstallEvent]` | `src/octop_browser/install.py:486` |
| 跳过 pip 引导 | `OCTOP_SKIP_PLAYWRIGHT_PIP` 或 legacy `HARNESS_SKIP_PLAYWRIGHT_PIP` 为真时不再装包 | `src/octop_browser/install.py:76`、`src/octop_browser/install.py:123` |
| 多 pip 候选开关 | `OCTOP_MULTI_PIP_BOOTSTRAP` / `HARNESS_MULTI_PIP_BOOTSTRAP` 为真时才尝试全部候选 | `src/octop_browser/install.py:145` |
| 下载源 | 自定义 `PLAYWRIGHT_DOWNLOAD_HOST` → npmmirror → 官方 CDN，按 TTFB 竞速排序 | `src/octop_browser/playwright_download.py:46` |
| 探测超时 | `_PROBE_TIMEOUT_S = 4.0`，`Range: bytes=0-1023` | `src/octop_browser/playwright_download.py:20`、`:86` |
| 终态门禁 | `verify_chromium()` 运行 `chrome --version`，失败即整个安装判失败 | `src/octop_browser/install.py:230` |

## 2. 本仓上游调用方反查表

| 本仓封装方法 | 上游调用模块与函数 | 所属流程 | 调用点锚点 |
|---|---|---|---|
| `ensure_chromium` | `cli.main` 的 `install-browser` 分支 | [安装引导](../../business/wf-chromium-install.md) | `src/octop_browser/cli.py:642` |
| `install_chromium_stream` | `_handle_install_browser`（MCP `install_browser`） | [MCP 服务](../../architecture/mcp-server.md) | `src/octop_browser/mcp_server.py:377` |
| `chromium_executable` | `cli.main` 快速路径、`verify_chromium` | [安装引导](../../business/wf-chromium-install.md) | `src/octop_browser/cli.py:638`、`src/octop_browser/install.py:237` |
| `race_download_sources` | `ensure_chromium` / `install_chromium_stream` 的下载阶段 | [安装引导](../../business/wf-chromium-install.md) | `src/octop_browser/install.py:332`、`:575` |
| `env_for_candidate` | 下载子进程的 env 构造 | [Chromium 进程契约](chromium-process.md) | `src/octop_browser/install.py:344` |

## 3. 封装方法总清单

| 序号 | 函数签名 | 出向动作 | 幂等 / 重试 | 定义锚点 |
|---|---|---|---|---|
| 1 | `_pip_install_candidates() -> list[list[str]]` | 构造 pip 引导命令 | 纯函数 | `src/octop_browser/install.py:128-138` |
| 2 | `_playwright_install_cmd() -> list[str]` | `[sys.executable, "-m", "playwright", "install", "chromium"]` | 纯函数 | `src/octop_browser/install.py:178-179` |
| 3 | `_playwright_install_deps_cmd() -> list[str]` | `[sys.executable, "-m", "playwright", "install-deps", "chromium"]` | 纯函数 | `src/octop_browser/install.py:182-183` |
| 4 | `build_download_candidates()` | 生成 `DownloadCandidate(kind, host, probe_url)` 列表 | 每次重读环境 | `src/octop_browser/playwright_download.py:46-80` |
| 5 | `race_download_sources(candidates, probe, timeout_s)` | `ThreadPoolExecutor` 并发探测，按 TTFB 升序 | 全失败回落原顺序 | `src/octop_browser/playwright_download.py:108-148` |
| 6 | `_stream_subprocess(cmd, is_disconnected, env)` | `asyncio.create_subprocess_exec` 逐行产出 `InstallEvent` | 断连即 `proc.kill()` | `src/octop_browser/install.py:377-420` |
| 7 | `verify_chromium() -> tuple[bool, str]` | `[exe, "--version"]`，`timeout=10` | 每次调用重算 | `src/octop_browser/install.py:230-272` |

## 4. 逐方法请求字典与响应解包契约（Full Dict Schemas）

### 4.1 pip 引导命令候选（`_pip_install_candidates`）

| 顺序 | argv 列表 | 触发条件 | 行号 |
|---|---|---|---|
| 1 | `["uv", "pip", "install", "playwright", "--python", sys.executable]` | `shutil.which("uv")` 命中 | `src/octop_browser/install.py:131` |
| 2 | `[sys.executable, "-m", "pip", "install", "playwright"]` | 恒追加 | `src/octop_browser/install.py:137` |

`_run_pip_install` 默认只取 `candidates[:1]`（`src/octop_browser/install.py:155`），仅当多引导开关打开才逐个尝试；成功条件是 `returncode == 0` 且 `_playwright_available()` 为真（`:168`），后者用 `importlib.invalidate_caches()` 后再 `find_spec("playwright")`（`:119`）。

### 4.2 下载候选字典与竞速返回（`build_download_candidates` / `race_download_sources`）

```json
{"kind": "npmmirror", "host": "https://cdn.npmmirror.com/binaries/playwright", "probe_url": "https://cdn.npmmirror.com/binaries/playwright/"}
```

| 字段 | 类型 | 必填条件 | 默认值 / 固定值 | 值来源 | 行号 |
|---|---|---|---|---|---|
| `kind` | `str` | 必填 | `custom` / `npmmirror` / `official` | 按候选来源枚举 | `src/octop_browser/playwright_download.py:54`、`:66`、`:75` |
| `host` | `str` | 官方候选为 `""` | 自定义取 `PLAYWRIGHT_DOWNLOAD_HOST` 去尾斜杠；镜像为 `https://cdn.npmmirror.com/binaries/playwright` | `_normalize_host` | `:51`、`:42`、`:16`、`:17` |
| `probe_url` | `str` | 必填 | `f"{host}/"` 或 `https://cdn.playwright.dev/` | 供 `probe_source` 发 Range GET | `:57`、`:68`、`:77` |

`_OFFICIAL_HOST_ALIASES`（`src/octop_browser/playwright_download.py:21`）含官方 CDN 与两个 Azure 别名，命中时不再重复追加 custom 候选。`probe_source` 用 `Request(url, headers={"Range": "bytes=0-1023"}, method="GET")`（`:86`），`status >= 500` 抛 `OSError`；`race_download_sources` 用 `min(len(candidates), 3)` 个 worker（`:122`），`ttfb >= 0` 才入榜，最终返回 `[item[1] for item in ranked]`（`:148`）。

### 4.3 子进程 env 字典（`env_for_candidate` / `plain_cli_env`）

| env 键 | 值 | 作用 | 行号 |
|---|---|---|---|
| `PLAYWRIGHT_DOWNLOAD_HOST` | `cand.host`（非空时写入，否则 `pop`） | 指定下载镜像 | `src/octop_browser/playwright_download.py:168`、`:171` |
| `NO_COLOR` | `"1"` | 禁止 Chalk ANSI 转义 | `:159` |
| `FORCE_COLOR` | `"0"` | 同上 | `:160` |
| `NODE_DISABLE_COLORS` | `"1"` | 同上 | `:161` |

`plain_cli_env` 以 `os.environ.copy()`（或传入 env）为基线，再覆盖三个键（`:158`）；`_stream_subprocess` 把该结果传给 `asyncio.create_subprocess_exec(..., env=plain_cli_env(env))`（`src/octop_browser/install.py:385`）。

### 4.4 `InstallEvent` 事件字典与终态

| 键 | 类型 | 必填条件 | 含义 | 产出行号 |
|---|---|---|---|---|
| `log` | `str` | 每行 stdout/stderr 一条 | 子进程输出，UTF-8 `errors="replace"` | `src/octop_browser/install.py:411`、`:412` |
| `done` | `bool` | 终态事件必填 | 恒为 `True` | `:415`、`:395` |
| `success` | `bool` | 终态事件必填 | `returncode == 0` | `:415` |
| `error` | `str` | 失败终态可选 | 异常文本或验证失败信息 | `:394`、`:420`、`:619` |

约定 `log` 与 `done/success` 互斥（`src/octop_browser/install.py:81`）。MCP `_handle_install_browser` 聚合：`if "log" in event` 收集日志，`if event.get("done")` 取 `success` 与 `error`，最终文本为 `OK` 或 `FAILED: {error}`（`src/octop_browser/mcp_server.py:378`、`:386`）。

### 4.5 `verify_chromium` 返回与错误翻译

| 下游条件 | 返回 `(ok, message)` | 行号 |
|---|---|---|
| 二进制不存在 | `(False, "Chromium binary not found")` | `src/octop_browser/install.py:238` |
| `--version` 超时 | `(False, "Chromium verification timed out")` | `:247` |
| `returncode == 0` | `(True, f"Chromium {stdout.strip()}")` | `:252` |
| `returncode == 127` 或 stderr 含 `shared libraries` | `(False, "Chromium binary exists but cannot start (missing system library...)" + manual_hint())` | `:256`、`:264` |
| 其他非零 | `(False, f"Chromium exited with code {rc}: {stderr or stdout}")` | `:269` |

## 5. 共变耦合与修改清单（Agent Co-Change Playbook）

- **新增下载源**：`build_download_candidates`（`src/octop_browser/playwright_download.py:46`）、`_OFFICIAL_HOST_ALIASES`（`:21`）与 [配置手册](../../contracts/configuration.md) 的 `PLAYWRIGHT_DOWNLOAD_HOST` 表同步；`kind` 字符串会被日志与 `winner=` 输出引用（`:579`）。
- **修改 `InstallEvent` 键**：`TypedDict`（`src/octop_browser/install.py:81`）、`_stream_subprocess` 的两处 yield（`:394`、`:415`）、`_handle_install_browser` 的聚合判断（`src/octop_browser/mcp_server.py:378`）四处联动。
- **修改 env 注入**：`plain_cli_env`（`src/octop_browser/playwright_download.py:151`）同时服务同步 `ensure_chromium`（`src/octop_browser/install.py:344`）与流式路径（`:588`），不可只改一侧。
- **特殊协议陷阱**：官方候选 `host` 为 `""`，`env_for_candidate` 会 `pop("PLAYWRIGHT_DOWNLOAD_HOST")` 而非设空串，否则 Playwright 会去连空主机。
- **回归**：`pytest tests/unit/test_install.py tests/unit/test_playwright_download.py tests/unit/test_mcp_server.py`，命令见 [构建与单测映射](../../operations/dev-and-test.md)。
