---
kind: downstream-contract
scope: chromium-process
status: draft
origin: generated
source_paths: [src/octop_browser/cdp/launcher.py, src/octop_browser/cdp/launch_prep.py, src/octop_browser/profile.py]
symbols: [launch_or_attach, _build_flags, _get_ws_url, terminate_browser, find_chrome, get_page_ws_url, prepare_chrome_launch, recover_profile, pkill_chrome_profile, ProfileManager]
upstream: [integrations/index.md, architecture/cdp-transport-and-storage.md]
downstream: [integrations/downstream/chrome-cdp.md]
---

# 下游出向接口契约：本地 Chromium 进程（subprocess）

本仓以 `subprocess.Popen` 拉起真实 Chrome/Chromium 并令其监听 `--remote-debugging-port`，随后用 `aiohttp` 轮询 `/json/version` 取 WebSocket 地址；关闭时优先走 CDP `Browser.close`，超时后 POSIX 强杀。出向「请求」不是网络包而是 **argv 列表 + 环境字典 + 启动标志**，本页把每个键与来源逐一展开。Chromium 二进制本体属仓库外黑盒，见 [认知边界](../../operations/boundary.md)。

## 1. 封装定位与连接契约

| 契约项 | 精确值 / 规则 | 源码锚点 |
|---|---|---|
| 主入口 | `launch_or_attach(profile, headless) -> str`（browser 级 WS URL） | `src/octop_browser/cdp/launcher.py:497` |
| 附着判定 | `_port_in_use(profile.cdp_port)` 为真时直接 `_get_ws_url` 复用既有 Chrome | `src/octop_browser/cdp/launcher.py:508` |
| 远端拒绝 | `cfg.cdp_host` 非 `localhost/127.0.0.1` 时拒绝拉起并抛 `RuntimeError` | `src/octop_browser/cdp/launcher.py:517` |
| 二进制发现顺序 | `BROWSER_USE_CHROME_BIN` → 系统路径 → `PATH` → Playwright 缓存 | `src/octop_browser/cdp/launcher.py:150` |
| 启动前自愈 | `prepare_chrome_launch(profile)` 返回 `(profile, env)`，含 XDG、锁清理、profile 可写性重定向 | `src/octop_browser/cdp/launch_prep.py:207` |
| 成功判定 | `/json/version` 返回 `webSocketDebuggerUrl`；轮询 `launch_retries=20`、间隔 `launch_delay=0.25` | `src/octop_browser/cdp/launcher.py:367` |
| 子进程分离 | `start_new_session=True`（macOS 有头模式除外），`stdout/stderr/stdin` 分别重定向 | `src/octop_browser/cdp/launcher.py:566` |

## 2. 本仓上游调用方反查表

| 本仓封装方法 | 上游调用模块与函数 | 所属流程 | 调用点锚点 |
|---|---|---|---|
| `launch_or_attach` | `_InternalCDPSession.connect` | [会话生命周期](../../business/wf-browser-session-lifecycle.md) | `src/octop_browser/session.py:59` |
| `launch_or_attach` | `RecordController._attach` | [录制采集](../../business/wf-record-capture.md) | `src/octop_browser/record/recorder.py:336` |
| `get_page_ws_url` | `_InternalCDPSession.connect` | [会话生命周期](../../business/wf-browser-session-lifecycle.md) | `src/octop_browser/session.py:60` |
| `terminate_browser` | `browser_tool(close_session, kill=True)` 无会话分支 | [动作分发](../../business/wf-action-dispatch.md) | `src/octop_browser/tool_interface.py:148` |
| `terminate_browser` | `BrowserIdleController.reap_now` | [会话引擎](../../architecture/browser-session-engine.md) | `src/octop_browser/idle.py:80` |
| `find_chrome` | `tests/integration/conftest.py` 跳过判定、安装器验证 | [构建与单测映射](../../operations/dev-and-test.md) | `tests/integration/conftest.py:8` |

## 3. 封装方法总清单

| 序号 | 函数签名 | 出向动作 | 幂等 / 重试 | 定义锚点 |
|---|---|---|---|---|
| 1 | `find_chrome() -> str \| None` | 只读探测 4 层候选路径 | 每次调用重算 | `src/octop_browser/cdp/launcher.py:150-187` |
| 2 | `_build_flags(profile, headless) -> list[str]` | 构造 Chrome 启动参数列表 | 纯函数 | `src/octop_browser/cdp/launcher.py:190-232` |
| 3 | `launch_or_attach(profile, headless=False) -> str` | `Popen` + 轮询 `/json/version` | 端口占用即附着；exit 21 触发一次恢复重试 | `src/octop_browser/cdp/launcher.py:497-615` |
| 4 | `_get_ws_url(port, retries, delay, process, stderr_file)` | `aiohttp` 轮询 | 最多 20 次 | `src/octop_browser/cdp/launcher.py:350-398` |
| 5 | `get_page_ws_url(port, profile=None) -> str` | `GET /json` 挑选 page 目标 | sticky target 优先 | `src/octop_browser/cdp/launcher.py:618-671` |
| 6 | `terminate_browser(profile, cdp_host, timeout=3.0) -> bool` | `Browser.close` + `pkill` 兜底 | 非本地 host 直接返回 `False` | `src/octop_browser/cdp/launcher.py:440-494` |
| 7 | `prepare_chrome_launch(profile) -> (Profile, env)` | 环境修复 + 锁清理 | 每次启动执行 | `src/octop_browser/cdp/launch_prep.py:207-228` |

## 4. 逐方法请求字典与响应解包契约（Full Dict Schemas）

### 4.1 `Popen` argv 与启动标志（`src/octop_browser/cdp/launcher.py:543`）

```text
cmd = [chrome, *flags, "about:blank"]
```

| argv 位置 | 键 / 值 | 类型 | 必填条件 | 值来源与转换逻辑 | 组装行号 |
|---|---|---|---|---|---|
| `[0]` | `chrome` | `str` | 必填 | `find_chrome()` 返回值，未找到抛 `RuntimeError` | `:525` |
| `[1]` | `--remote-debugging-port={profile.cdp_port}` | `str` | 必填 | `ProfileManager._assign_port` 分配，默认从 `9222` 起避让已用端口 | `:194`、`src/octop_browser/profile.py:151` |
| `[2]` | `--user-data-dir={profile.data_dir}` | `str` | 必填 | 可能被 `ensure_profile_writable` 重定向到临时根 | `:195`、`src/octop_browser/cdp/launch_prep.py:185` |
| `[3..17]` | `--disable-background-networking`、`--disable-sync`、`--disable-translate`、`--disable-extensions`、`--disable-default-apps`、`--no-first-run`、`--no-default-browser-check`、`--disable-popup-blocking`、`--metrics-recording-only`、`--safebrowsing-disable-auto-update`、`--disable-crash-reporter`、`--disable-breakpad` | `str` | 固定常量 | 硬编码列表，见 `:193-216` | `:196` |
| 条件项 | `--remote-debugging-address={cfg.cdp_host}` | `str` | `cfg.cdp_host` 非 `localhost/127.0.0.1` | Docker 端口转发时外露监听 | `:219` |
| 条件项 | `--headless=new` | `str` | `headless=True` | 由 `resolve_headless` 解析 | `:221` |
| 条件项 | `--no-sandbox` | `str` | `_should_disable_sandbox()` 为真（root / 环境变量 / 内核不允许 user namespace） | 见 `:283-309` | `:223` |
| 条件项 | `--disable-gpu` | `str` | `_should_disable_gpu(headless)` 为真 | 有头默认关，无头默认开，环境变量可强制 | `:228` |
| 条件项 | `--disable-dev-shm-usage` | `str` | `_should_disable_dev_shm()` 为真 | Linux 默认开（Docker `/dev/shm` 仅 64 MiB） | `:230` |
| 末位 | `about:blank` | `str` | 固定 | 保证启动时至少有一个 page 目标 | `:543` |

`_env_tristate`（`src/octop_browser/cdp/launcher.py:235`）把 `1/true/yes/on` 判真、`0/false/no/off` 判假、其余返回 `None` 回落自动检测，是 `BROWSER_USE_NO_SANDBOX`、`BROWSER_USE_DISABLE_GPU`、`BROWSER_USE_DISABLE_DEV_SHM_USAGE` 的共用解析器。

### 4.2 子进程 `env` 字典（`prepare_chrome_launch`）

| env 键 | 值来源 | 副作用 | 组装行号 |
|---|---|---|---|
| `os.environ.copy()` 全量 | 继承父进程 | 基线 | `src/octop_browser/cdp/launch_prep.py:209` |
| `XDG_RUNTIME_DIR` | `ensure_xdg_runtime_dir` 写入 `/tmp/runtime-octop-browser-{uid}` 并 `chmod 0o700` | 避免容器/根会话无运行时目录导致 crashpad 退出 | `:210`、`:63` |
| `BROWSER_USE_PROFILES_DIR` | 改为 `profile.data_dir.parent` | 仅对子进程生效，不改进程全局 `settings.profiles_dir` | `:216` |
| `USERNAME` / `USER` | `_temp_scope_token` 在 Windows 无 `getuid` 时取二者之一 | 稳定临时目录后缀 | `:49` |
| `DEBIAN_FRONTEND=noninteractive` | `_native_batch_step` 为 apt 命令注入 | 安装系统依赖时免交互 | `src/octop_browser/linux_deps.py:256` |

`pkill_chrome_profile` 以 `subprocess.run(["pkill","-9","-f", f"user-data-dir={profile_dir}"], shell=False, timeout=5)` 清理残留进程（`src/octop_browser/cdp/launch_prep.py:189`）；`clear_profile_locks` 删除 `SingletonLock`/`SingletonCookie`/`SingletonSocket` 三个键（`:82`）。

### 4.3 优雅关闭与强杀（`terminate_browser`）

| 步骤 | 出向字典 / 命令 | 返回解包 | 行号 |
|---|---|---|---|
| 1 本地守卫 | `cdp_host` 不在 `{localhost, 127.0.0.1, ::1}` 时返回 `False` | — | `:452` |
| 2 端口探测 | `GET /json/version`，`resp.status == 200` | `webSocketDebuggerUrl` | `:462`、`:468` |
| 3 优雅关闭 | browser 级 WS `ws.send_json({"id": 1, "method": "Browser.close"})` | 无返回体 | `:471` |
| 4 轮询确认 | 每 `0.1s` 探测端口，最长 `timeout=3.0` | 端口消失即 `True` | `:479` |
| 5 强杀兜底 | `pkill_chrome_profile(profile.data_dir)` 经 `asyncio.to_thread` 调用，成功后 `clear_profile_locks` | `killed or not _port_in_use_at(...)` | `:490` |

### 4.4 启动轮询与失败翻译

| 下游条件 | 本仓行为 | 代码行号 |
|---|---|---|
| `process.poll()` 非空（Chrome 立即退出） | 读取 stderr 尾部 4096 字节，抛 `RuntimeError("Chrome exited immediately (returncode=...)")` | `:374`、`:401` |
| 轮询耗尽 | `RuntimeError("Chrome did not start on {host}:{port} after {retries} attempts.")` | `:395` |
| stderr 含 `returncode=21` / `ProcessSingleton` / `SingletonLock` | `recover_profile` 重命名旧目录并重试一次 `Popen` | `:585`、`:599` |
| `GET /json` 无 page 目标 | `PUT`（回退 `GET`）`/json/new?about:blank` 新建空白页 | `:642`、`:685` |
| 无 page 且新建失败 | `RuntimeError("No open page found in Chrome")` | `:649` |

## 5. 共变耦合与修改清单（Agent Co-Change Playbook）

- **新增启动 flag**：`_build_flags`（`src/octop_browser/cdp/launcher.py:190`）与 [配置手册](../../contracts/configuration.md) 的三态开关表同步；`--remote-debugging-address` 分支必须始终读 `cfg.cdp_host`。
- **修改端口分配**：`ProfileManager._assign_port`（`src/octop_browser/profile.py:151`）与 `.octop-browser-profiles.json` 的整文件覆盖写（`:143`）联动，新增键需兼容旧 JSON 缺键。
- **修改 profile 重定向**：`ensure_profile_writable`（`src/octop_browser/cdp/launch_prep.py:144`）返回值被 `prepare_chrome_launch` 用于构造 `--user-data-dir`，切勿改回全局 `settings.profiles_dir`，否则多 profile 相互污染。
- **特殊协议陷阱**：macOS 有头模式故意不设 `start_new_session`（`src/octop_browser/cdp/launcher.py:575`），否则窗口无法获得前台焦点；`pkill` 仅 POSIX 有效（`:191`）。
- **回归**：`pytest tests/unit/test_launcher.py tests/unit/test_launch_prep.py tests/unit/test_profile.py`，命令见 [构建与单测映射](../../operations/dev-and-test.md)。
