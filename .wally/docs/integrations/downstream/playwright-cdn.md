---
kind: downstream-contract
scope: playwright-cdn-and-os-packages
status: draft
origin: generated
source_paths: [src/octop_browser/playwright_download.py, src/octop_browser/install.py, src/octop_browser/linux_deps.py]
symbols: [build_download_candidates, probe_source, race_download_sources, env_for_candidate, install_chromium_stream, verify_chromium, build_install_steps]
upstream: [../index.md, ../topology-and-mapping.md]
downstream: []
---

# 下游出向接口契约：`playwright-cdn` 与宿主包管理器

这是本仓唯一的一次性引导下游，不参与运行时浏览器驱动。下载阶段对 Playwright CDN 发 HTTP 探测与 `playwright install chromium` 子进程；依赖阶段按宿主包管理器发安装命令。服务端内部实现不在本仓，属外部黑盒。

## 1. 封装定位与连接契约

| 契约项 | 精确值 / 规则 | 源码锚点 |
|---|---|---|
| 业务封装文件 | `src/octop_browser/playwright_download.py`（CDN 竞速）、`src/octop_browser/linux_deps.py`（系统包）、`src/octop_browser/install.py`（编排与验证） | `src/octop_browser/install.py:57-64` |
| 底层传输 | `urllib.request.urlopen` 探测 + `subprocess.run` / `create_subprocess_exec` 安装 | `src/octop_browser/playwright_download.py:11-12,92-105`、`src/octop_browser/install.py:385-390` |
| 官方 CDN | `https://cdn.playwright.dev` | `src/octop_browser/playwright_download.py:16` |
| 镜像 CDN | `https://cdn.npmmirror.com/binaries/playwright` | `src/octop_browser/playwright_download.py:17` |
| 公共成功判定 | 单步以子进程返回码 0 为准；整体以 `verify_chromium()` 的 `(True, 版本串)` 为准 | `src/octop_browser/install.py:252-254,364-369` |
| 安装缓存目录 | Playwright 标准位置：`~/.cache/ms-playwright` 或 `$PLAYWRIGHT_BROWSERS_PATH` | `src/octop_browser/cdp/launcher.py:95-106` |

## 2. 本仓上游调用方反查表

| 本仓封装方法 | 上游调用方 | 所属业务流 | 调用点锚点 |
|---|---|---|---|
| `install_chromium_stream()` | MCP `_handle_install_browser` | [`WF-03`](../../business/wf-chromium-bootstrap.md) | `src/octop_browser/mcp_server.py:377-388` |
| `ensure_chromium()` | CLI `install-browser` | WF-03 | `src/octop_browser/cli.py:637-643` |
| `race_download_sources()` | `ensure_chromium` 与 stream 版 | WF-03 | `src/octop_browser/install.py:332`、`src/octop_browser/install.py:575-577` |
| `build_install_steps()` | `_run_install_deps`、`_stream_install_deps` | WF-03 | `src/octop_browser/install.py:202`、`src/octop_browser/install.py:439` |
| `chromium_executable()` | CLI 幂等短路、`verify_chromium` | WF-03 | `src/octop_browser/cli.py:638`、`src/octop_browser/install.py:237` |

## 3. 封装方法总清单

| 序号 | 封装函数签名 | 下游目标 | 读写 | 幂等/重试 | 定义锚点 |
|---|---|---|---|---|---|
| 1 | `build_download_candidates() -> list[DownloadCandidate]` | 无网络，构造候选 | — | — | `src/octop_browser/playwright_download.py:46-80` |
| 2 | `probe_source(url, timeout_s) -> float` | HTTP GET Range 探测 | 读 | 5xx 抛错，4xx 容忍 | `src/octop_browser/playwright_download.py:83-105` |
| 3 | `race_download_sources(candidates, probe, timeout_s) -> list[...]` | 并发探测 3 候选 | 读 | 全失败退回原序 | `src/octop_browser/playwright_download.py:108-148` |
| 4 | `python -m playwright install chromium` | CDN 下载二进制 | 写 | 逐候选重试直到成功 | `src/octop_browser/install.py:178-179,332-358` |
| 5 | `build_install_steps(playwright_cmd) -> list[InstallStep]` | 无网络，构造命令 | — | 首个库步骤成功即跳过后续 | `src/octop_browser/linux_deps.py:220-248` |
| 6 | 各包管理器 `install` 命令 | 宿主系统库/字体 | 写 | 字体步骤 optional | `src/octop_browser/linux_deps.py:251-285` |
| 7 | `verify_chromium() -> (bool, str)` | 本地 `--version` 子进程 | 读 | 超时 10s | `src/octop_browser/install.py:230-272` |

## 4. 逐方法请求字典与响应解包契约

### 4.1 CDN 竞速探测（`src/octop_browser/playwright_download.py:83-105`）

```json
{"method": "GET", "url": "https://cdn.npmmirror.com/binaries/playwright/", "headers": {"Range": "bytes=0-1023"}, "timeout_s": 4.0}
```

| 字典键 | 类型 | 值来源与转换 | 组装行号 |
|---|---|---|---|
| `url` | `str` | `DownloadCandidate.probe_url`，custom 来自 `PLAYWRIGHT_DOWNLOAD_HOST` | `src/octop_browser/playwright_download.py:51-79` |
| `headers.Range` | `str` | 固定 `"bytes=0-1023"`，只读 1 KiB | `src/octop_browser/playwright_download.py:86-90` |
| `timeout` | `float` | `probe_source` 默认 4.0 秒 | `src/octop_browser/playwright_download.py:20,83-84` |

**响应解包**：读前 16 字节触发 TTFB，`status >= 500` 抛 `OSError`；`HTTPError.code >= 500` 重抛，4xx 视为成功；返回 `time.monotonic() - started`（`src/octop_browser/playwright_download.py:92-105`）。`race_download_sources` 按 TTFB 升序排序，胜出者记录 `kind` 与秒数到日志（`src/octop_browser/playwright_download.py:137-148`）。

### 4.2 下载子进程环境字典（`src/octop_browser/playwright_download.py:165-172`）

| 环境变量键 | 类型 | 值来源 | 组装行号 |
|---|---|---|---|
| `PLAYWRIGHT_DOWNLOAD_HOST` | `str` | `cand.host` 非空则设；official 候选则 `pop` 删除 | `src/octop_browser/playwright_download.py:167-171` |
| `NO_COLOR` | `str` | 固定 `"1"` | `src/octop_browser/playwright_download.py:159` |
| `FORCE_COLOR` | `str` | 固定 `"0"` | `src/octop_browser/playwright_download.py:160` |
| `NODE_DISABLE_COLORS` | `str` | 固定 `"1"` | `src/octop_browser/playwright_download.py:161` |

### 4.3 pip 引导命令字典（`src/octop_browser/install.py:128-175`）

| 候选命令 | 触发条件 | 源码锚点 |
|---|---|---|
| `uv pip install playwright --python <sys.executable>` | `shutil.which("uv")` 命中（列在首位） | `src/octop_browser/install.py:131-136` |
| `<sys.executable> -m pip install playwright` | 兜底；默认只试第一条，置 `OCTOP_MULTI_PIP_BOOTSTRAP=1` 才全试 | `src/octop_browser/install.py:137-149,152-175` |

### 4.4 系统依赖步骤字典（`src/octop_browser/linux_deps.py:172-285`）

`InstallStep` 字段：`label`（步骤名）、`cmd`（argv 列表）、`env`、`optional`（`src/octop_browser/linux_deps.py:172-179`）。

| 管理器 | `cmd` 骨架 | 非 root 前缀 | 源码锚点 |
|---|---|---|---|
| `apt-get` | `["env","DEBIAN_FRONTEND=noninteractive","apt-get","install","-y", <16 库>]`，Playwright `install-deps` 先行 | `sudo -n --` | `src/octop_browser/linux_deps.py:238-260,190-206` |
| `dnf` / `yum` | `[mgr, "install", "-y", <16 库>]` | 同上 | `src/octop_browser/linux_deps.py:47-82,160-169` |
| `zypper` | `["zypper","--non-interactive","install","-y", <库>]` | 同上 | `src/octop_browser/linux_deps.py:83-100,166` |
| `pacman` / `apk` | `["pacman","-S","--noconfirm","--needed", <库>]` / `["apk","add","--no-cache", <库>]` | 同上 | `src/octop_browser/linux_deps.py:101-137,167-168` |

**响应解包**：`subprocess.run(check=False)` 看 `returncode == 0`；库步骤首个成功即置 `libs_ok=True`，字体步骤独立置 `fonts_ok`，二者互不影响（`src/octop_browser/install.py:200-222`）。流式版逐行 yield `InstallEvent`，终态 `{"done": true, "success": <libs_ok>}`（`src/octop_browser/install.py:423-478`）。

### 4.5 验证子进程字典（`src/octop_browser/install.py:230-272`）

| 键 | 值 |
|---|---|
| `argv` | `[chromium_executable(), "--version"]` |
| `timeout` | `10` 秒 |
| 返回码 0 | `(True, "Chromium <stdout>" 或 "Chromium OK")` |
| 返回码 127 / stderr 含 `shared libraries` | 提取首个含 `.so` 的行拼入诊断，附 `manual_hint()` |
| 其他返回码 | `(False, "Chromium exited with code <n>: <stderr or stdout>")` |

## 5. 错误翻译与黑盒边界

| 下游原始条件 | 本仓拦截位置 | 翻译结果 |
|---|---|---|
| CDN 探测全失败 | `src/octop_browser/playwright_download.py:138-140` | 退回目录顺序继续尝试完整下载 |
| 所有候选下载返回非 0 | `src/octop_browser/install.py:357-358` / `:600-602` | 同步版返回 `False`；流式版发 `done/success=false, error="Chromium download failed"` |
| 缺系统库 | `src/octop_browser/install.py:256-267` | `manual_hint()` 给出当前管理器前 6 个包名 |
| Playwright 未装且 `OCTOP_SKIP_PLAYWRIGHT_PIP=1` | `src/octop_browser/install.py:317-325` | 明确要求人工 `pip install playwright` 后重试 |

远端 CDN 的真实配额、CDN 返回体内部结构、包管理器仓库内容均不在本仓，禁止脑补；本仓只核实请求键与返回码语义。

## 6. 共变耦合与修改清单

- **改 CDN 候选**：同步 `_OFFICIAL_HOST_ALIASES` 排除集合（`src/octop_browser/playwright_download.py:21-27`）并跑 `tests/unit/test_playwright_download.py`。
- **改包集合**：`manual_hint()` 展示片段与 `contracts/configuration.md` 环境变量表需同步，跑 `tests/unit/test_linux_deps.py`。
- **改流式事件字段**：MCP `_handle_install_browser` 只识别 `log` / `done` / `success` / `error`（`src/octop_browser/mcp_server.py:372-388`），新增键需同步消费端。
- **改验证命令**：保持返回二元组 `(bool, str)` 不变，否则所有调用点需重构；跑 `tests/unit/test_install.py`。

## 7. 关联文档

- [集成总览](../index.md) · [WF-03 安装验证](../../business/wf-chromium-bootstrap.md) · [配置全集](../../contracts/configuration.md)
