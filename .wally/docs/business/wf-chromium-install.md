---
kind: workflow
scope: WF-07
status: draft
origin: generated
source_paths: [src/octop_browser/install.py, src/octop_browser/playwright_download.py, src/octop_browser/linux_deps.py, src/octop_browser/cli.py]
symbols: [ensure_chromium, install_chromium_stream, verify_chromium, chromium_executable, build_download_candidates, race_download_sources, build_install_steps, detect_package_manager, _handle_install_browser]
upstream: [business/index.md, contracts/api-reference.md]
downstream: [integrations/downstream/playwright-installer.md, integrations/downstream/linux-system-deps.md]
---

# WF-07 · Chromium 一次性安装引导闭环

`install-browser` / MCP `install_browser` 触发 5 阶段流水线：命中已装且可运行的二进制即短路；否则按需 `pip install playwright`、竞速 CDN 下载 `chromium`、装 Linux 系统依赖与 CJK 字体、最后跑 `chrome --version` 验证。Playwright 仅作下载器，不是运行时依赖（`src/octop_browser/install.py:35`）。同步与流式两条入口共用同一阶段定义。

## 1. 符号级端到端执行调用树

```text
Trigger: octop-browser install-browser -> cli.main (src/octop_browser/cli.py:637)
  ├─ [fast path] existing = chromium_executable()；非空即 print 路径并 return 0 (:638)
  └─ ok = ensure_chromium(quiet=args.quiet) (src/octop_browser/install.py:280)
       ├─ [Stage 1] existing = chromium_executable(); verify_chromium() 成功即 return True (:294)
       │    └─ 二进制存在但损坏 -> _run_install_deps 后重验，仍坏 return False (:301、:313)
       ├─ [Stage 2] if not _playwright_available() (:316)
       │    ├─ [if _skip_pip_bootstrap()] 报「未安装且跳过 pip」并 return False (:317)
       │    └─ _run_pip_install(quiet=quiet) 试 uv/pip 候选 (:328)
       ├─ [Stage 3] ordered = race_download_sources(build_download_candidates()) (:332)
       │    └─ 逐个 cand 跑 _playwright_install_cmd()，env=env_for_candidate(cand)，首个 rc==0 即 downloaded=True (:334、:349)
       ├─ [Stage 4] _run_install_deps(quiet=quiet)（Linux best-effort）(:361)
       ├─ [Stage 5] ok, msg = verify_chromium()；失败 logger.error 后 return ok (:364、:368)
       └─ [return] bool -> CLI 退出码 0/1 (src/octop_browser/cli.py:643)

Trigger: MCP install_browser -> _handle_install_browser (src/octop_browser/mcp_server.py:372)
  └─ async for event in install_chromium_stream() (src/octop_browser/install.py:486)
       ├─ [fast path] 已装且验证成功 -> {"log": "Chromium already installed: ..."} + {"done": True, "success": True} (:512、:516)
       ├─ [Stage pip] 缺失则 _stream_subprocess 逐行产出 log (:537、:555)
       ├─ [Stage 下载] race_download_sources 经 asyncio.to_thread (:575)；逐源 _stream_subprocess (:585)
       ├─ [Stage 系统依赖] _stream_install_deps（Linux）(:605)
       ├─ [Stage 验证] verify_chromium 经 asyncio.to_thread (:614)
       └─ [终态] {"done": True, "success": True/False, "error": msg?} (:617、:620)
```

## 2. 分阶段业务规则与分支判定表

| 阶段 | 负责函数（`路径:行号`） | 精确布尔条件 / 阈值 | 命中分支行为 | 状态或数据副作用 |
|---|---|---|---|---|
| 短路判定 | `ensure_chromium` (`src/octop_browser/install.py:294`) | `chromium_executable()` 非空且 `verify_chromium()` 返回 `ok=True` | 直接成功，不联网 | 无 |
| 跳过 pip | `_skip_pip_bootstrap` (`:123`) | `OCTOP_SKIP_PLAYWRIGHT_PIP` 或 `HARNESS_SKIP_PLAYWRIGHT_PIP` 为真 | 未装 playwright 时直接失败 | 无 |
| 包探测 | `_playwright_available` (`:108`) | `importlib.util.find_spec("playwright") is not None` | 探测前先 `invalidate_caches()` 以免 pip 后缓存未刷新（`:119`） | 无 |
| pip 候选 | `_pip_install_candidates` (`:128`) | `shutil.which("uv")` 命中则追加 `uv pip install --python sys.executable` | 默认只试首个候选（`:155`） | 无 |
| CDN 竞速 | `race_download_sources` (`src/octop_browser/playwright_download.py:108`) | `ThreadPoolExecutor(max_workers=min(n,3))`，按 TTFB 升序 | 全部探测失败回落 catalog 原顺序（`:138`） | 返回排序后的候选列表 |
| 下载成功 | `ensure_chromium` (`:349`) | `result.returncode == 0` | `downloaded=True` 并 break | 二进制落入 Playwright 缓存 |
| 系统依赖准入 | `_run_install_deps` (`:198`) | `sys.platform != "linux"` 直接 `return True` | Debian 先 `playwright install-deps`，其余用原生管理器 | 无硬失败阻断 |
| 终态门禁 | `verify_chromium` (`:230`) | `[exe, "--version"]` 且 `timeout=10` | `returncode==0` 才成功；127/缺库给 `manual_hint()` | 决定整个安装成败 |
| 流式断连 | `_stream_subprocess` (`:401`) | `is_disconnected()` 为真 | `proc.kill()` 并结束产出 | 不写残缺状态 |

## 3. 阶段与产物字典

| 阶段 | 关键命令 / 产物 | 配置键 | 源码锚点 |
|---|---|---|---|
| pip 引导 | `uv pip install playwright --python <sys.executable>` 或 `python -m pip install playwright` | `OCTOP_SKIP_PLAYWRIGHT_PIP`、`OCTOP_MULTI_PIP_BOOTSTRAP` | `:128`、`:76`、`:145` |
| 二进制下载 | `python -m playwright install chromium` | `PLAYWRIGHT_DOWNLOAD_HOST`、`PLAYWRIGHT_BROWSERS_PATH` | `:178`、`:332` |
| 系统依赖 | `python -m playwright install-deps chromium` 或 `apt-get/dnf/yum/zypper/pacman/apk` 原生批次 | `DEBIAN_FRONTEND=noninteractive` | `:182`、`src/octop_browser/linux_deps.py:220` |
| CJK 字体 | 每包独立可选步骤 | `_FONT_PACKAGES` | `src/octop_browser/linux_deps.py:263` |
| 验证 | `chrome --version` | 无 | `:230` |
| 流式事件 | `InstallEvent{log\|done,success,error}` | `is_disconnected` 回调 | `:81`、`:486` |

## 4. 幂等、并发互斥与异常补偿回滚表

| 边界 / 故障场景 | 源码检测条件 | 保护 / 回滚 / 降级动作 |
|---|---|---|
| 二进制已装 | `_find_playwright_chromium()` 命中（`src/octop_browser/cdp/launcher.py:84`） | 短路返回路径，不重复下载 |
| 二进制存在但不可运行 | `verify_chromium()` 返回 `False`（`:296`） | 先补系统依赖再重验，仍坏则重新走完整下载 |
| 所有 CDN 探测失败 | `ranked` 为空（`src/octop_browser/playwright_download.py:138`） | 回落 catalog 顺序逐个尝试下载，不直接判失败 |
| 全部下载源失败 | `downloaded` 仍为 `False`（`:357`） | `return False`，不进入系统依赖与验证 |
| 系统依赖全失败 | `libs_ok` 为假（`src/octop_browser/install.py:222`） | 仍继续 `verify_chromium`，以便报出精确缺库名 |
| apt 不支持的发行版 | `detect_package_manager()` 非 `apt-get`（`src/octop_browser/linux_deps.py:236`） | 跳过 Playwright `install-deps`，直接原生管理器 |
| sudo 需密码 | `with_privileges` 用 `sudo -n --`（`:203`） | 立即失败而非提示挂起，字体步骤可选不阻断 |

## 5. 共变耦合与修改清单（Agent Co-Change Playbook）

- **新增阶段**：同步 `ensure_chromium`（`:280`）与流式 `install_chromium_stream`（`:486`）两条管线必须同构，并同步 [Playwright 安装器](../integrations/downstream/playwright-installer.md) 与 [Linux 系统依赖](../integrations/downstream/linux-system-deps.md) 契约页。
- **修改 CDN 候选**：`build_download_candidates`（`src/octop_browser/playwright_download.py:46`）、`_OFFICIAL_HOST_ALIASES`（`:21`）与 [配置手册](../contracts/configuration.md) 联动。
- **修改验证门禁**：`verify_chromium`（`:230`）返回的 `(ok, msg)` 被 `_handle_install_browser` 拼成 `OK/FAILED`（`src/octop_browser/mcp_server.py:386`），文案键不可随意删。
- **必跑流程闭环回归**：`pytest tests/unit/test_install.py tests/unit/test_linux_deps.py tests/unit/test_playwright_download.py tests/unit/test_mcp_server.py`，命令见 [构建与单测映射](../operations/dev-and-test.md)。
