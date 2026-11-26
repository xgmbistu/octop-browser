---
kind: config-dict
scope: configuration
status: draft
origin: generated
source_paths: [src/octop_browser/settings.py, src/octop_browser/record/settings.py, src/octop_browser/mode.py, src/octop_browser/cdp/launcher.py, src/octop_browser/install.py, src/octop_browser/playwright_download.py, src/octop_browser/mcp_server.py, src/octop_browser/cdp/launch_prep.py]
symbols: [OctopSettings, _env_path, _env_int, _env_float, _env_str, state_dir, RecordReplaySettings, normalize_mode, _env_tristate, _skip_pip_bootstrap, build_download_candidates, _main]
upstream: [INDEX.md, overview/system-architecture.md]
downstream: [operations/deployment-and-runtime.md, architecture/cdp-transport-and-storage.md]
---

# 配置项、环境变量与动态开关全集

配置唯一权威源是 `OctopSettings` dataclass（`src/octop_browser/settings.py:110`），每个字段用 `field(default_factory=lambda: _env_*(...))`，**每次实例化都重读环境变量**；模块级 `settings` 单例在 import 时构造一次（`:185`）。录制子系统另有 `RecordReplaySettings`（`src/octop_browser/record/settings.py:22`）。全仓无配置文件解析器、无数据库配置表。

## 1. 配置覆盖优先级链

`BrowserSession.create(settings=显式对象)`（`src/octop_browser/session.py:206`） > `进程环境变量 os.environ.get`（`src/octop_browser/settings.py:67`） > `state_dir()` 派生的路径默认值（`:78`） > 代码硬编码常量。CLI/MCP 的工具 schema 不承载这些键，由客户端配置 `mcpServers.<name>.env` 注入（`src/octop_browser/mcp_server.py:28`）。`--headed/--headless/--auto` 与 `mode` 参数只在首次建会话生效（`src/octop_browser/tool_interface.py:110`）。

## 2. 进程环境变量全集（100% 扫描 `getenv` / `environ`）

| 环境变量名 | 类型 | 代码默认值 | 必填 | 控制行为与边界影响 | 读取锚点 |
|---|---|---|---|---|---|
| `BROWSER_USE_PROFILES_DIR` | `Path` | `state_dir()/profiles` | 否 | Chrome user-data-dir 基目录 | `src/octop_browser/settings.py:130` |
| `BROWSER_USE_SCREENSHOTS_DIR` | `Path` | `state_dir()/screenshots` | 否 | 截图 PNG 落点 | `:135` |
| `BROWSER_USE_CDP_HOST` | `str` | `localhost` | 否 | CDP HTTP/WS 主机；非本地时禁止本地拉起 | `:141`、`src/octop_browser/cdp/launcher.py:517` |
| `BROWSER_USE_CDP_PORT_START` | `int` | `9222` | 否 | 首个 profile 的调试端口 | `:145` |
| `BROWSER_USE_CHROME_BIN` | `str \| None` | `None`（自动探测） | 否 | 显式 Chrome 二进制路径 | `:148`、`src/octop_browser/cdp/launcher.py:163` |
| `BROWSER_USE_CDP_TIMEOUT` | `float` | `30.0` | 否 | 单条 CDP 命令 `wait_for` 上限 | `:151`、`src/octop_browser/cdp/client.py:99` |
| `BROWSER_USE_LAUNCH_RETRIES` | `int` | `20` | 否 | `/json/version` 轮询次数 | `:154`、`src/octop_browser/cdp/launcher.py:367` |
| `BROWSER_USE_LAUNCH_DELAY` | `float` | `0.25` | 否 | 轮询间隔秒 | `:157`、`:368` |
| `BROWSER_USE_CDP_WS_URL` | `str \| None` | `None` | 否 | 直连远端 Chrome WS，绕过 launcher 且禁用切标签 | `:160`、`src/octop_browser/session.py:55` |
| `BROWSER_USE_IDLE_TIMEOUT_MINUTES` | `float` | `0.0`（关闭） | 否 | 本地 Chrome 空闲回收分钟数 | `:163`、`src/octop_browser/idle.py:137` |
| `BROWSER_USE_VIEWPORT_WIDTH` / `BROWSER_USE_VIEWPORT_HEIGHT` | `int` | `1440` / `900` | 否 | `Emulation.setDeviceMetricsOverride` 尺寸 | `:166`、`:169` |
| `BROWSER_USE_CDP_MAX_MESSAGE_SIZE` | `int` | `33554432`（`0` → `None`） | 否 | WebSocket 帧上限，防截图触发 1009 | `:174`、`src/octop_browser/cdp/client.py:69` |
| `BROWSER_USE_MODE` | `BrowserMode` | `auto` | 否 | `auto/headed/headless` 三态 | `:179`、`src/octop_browser/mode.py:26` |
| `BROWSER_USE_NO_SANDBOX` | tri-state | 自动检测 | 否 | `1/true/yes/on` 强制 `--no-sandbox`，`0/...` 强制关闭 | `src/octop_browser/cdp/launcher.py:302` |
| `BROWSER_USE_DISABLE_GPU` | tri-state | 无头默认开、有头默认关 | 否 | 控制 `--disable-gpu` | `:263` |
| `BROWSER_USE_DISABLE_DEV_SHM_USAGE` | tri-state | Linux 默认开 | 否 | 控制 `--disable-dev-shm-usage` | `:277` |
| `BROWSER_RECORD_REPLAY_DIR` | `Path` | `state_dir()/record-replay` | 否 | 录制产物、socket、pid 根目录 | `src/octop_browser/record/settings.py:26` |
| `BROWSER_RECORD_MAX_EVENT_BYTES` | `int` | `65536` | 否 | 单事件字节上限，超限丢弃 | `:31`、`src/octop_browser/record/recorder.py:265` |
| `BROWSER_RECORD_MAX_EVENTS_PER_SECOND` | `int` | `100` | 否 | 每秒事件限流 | `:34`、`src/octop_browser/record/recorder.py:238` |
| `MCP_PORT` | `str` | 未设置（走 stdio） | 否 | 设置后启用 SSE HTTP 服务 | `src/octop_browser/mcp_server.py:491` |
| `MCP_HOST` | `str` | `0.0.0.0` | 否 | SSE 监听主机 | `:499` |
| `OCTOP_SKIP_PLAYWRIGHT_PIP` | tri-state | 关 | 否 | 跳过 `pip install playwright` 引导 | `src/octop_browser/install.py:76`、`:124` |
| `HARNESS_SKIP_PLAYWRIGHT_PIP` | tri-state | 关 | 否 | 上一项的 legacy 别名 | `:78` |
| `OCTOP_MULTI_PIP_BOOTSTRAP` | tri-state | 关 | 否 | 允许尝试全部 pip 候选命令 | `:146` |
| `HARNESS_MULTI_PIP_BOOTSTRAP` | tri-state | 关 | 否 | 上一项的 legacy 别名 | `:147` |
| `PLAYWRIGHT_BROWSERS_PATH` | `str` | `~/.cache/ms-playwright` 等 | 否 | Playwright 二进制缓存根 | `src/octop_browser/cdp/launcher.py:95` |
| `PLAYWRIGHT_DOWNLOAD_HOST` | `str` | 未设置（官方 CDN） | 否 | 自定义下载镜像，参与 CDN 竞速 | `src/octop_browser/playwright_download.py:18`、`:51` |
| `DISPLAY` / `WAYLAND_DISPLAY` | `str` | 未设置 | 否 | Linux `auto` 模式判定有无桌面 | `src/octop_browser/mode.py:52` |
| `PROGRAMFILES` / `PROGRAMFILES(X86)` / `LOCALAPPDATA` | `str` | 未设置 | 否 | Windows Chrome 安装路径与缓存根 | `src/octop_browser/cdp/launcher.py:138`、`:139`、`:102` |
| `USERNAME` / `USER` | `str` | `default` | 否 | Windows 无 `getuid` 时临时目录后缀 | `src/octop_browser/cdp/launch_prep.py:49` |

`_env_tristate`（`src/octop_browser/cdp/launcher.py:235`）把 `1/true/yes/on` 判真、`0/false/no/off` 判假、其余返回 `None`；`_skip_pip_bootstrap`（`src/octop_browser/install.py:123`）与 `_multi_pip_bootstrap_enabled`（`:145`）用同一真值集合但只读自身键。

## 3. 动态运行时 / 单实例策略开关表

| 所属配置域 | 配置键 | 类型 | 默认值 | 允许范围 | 生效时机与副作用 | 读写校验锚点 |
|---|---|---|---|---|---|---|
| `OctopSettings` | `browser_mode` | `BrowserMode` | `auto` | `auto/headed/headless` | 建会话时解析为布尔 headless | `src/octop_browser/settings.py:178`、`src/octop_browser/mode.py:55` |
| `OctopSettings` | `cdp_ws_url` | `str \| None` | `None` | 任意 WS URL | 非空即绕过 launcher、禁用 `switch_to_target` | `:159`、`src/octop_browser/session.py:55` |
| `OctopSettings` | `idle_timeout_minutes` | `float` | `0.0` | `>= 0` | `<= 0` 或非本地 host 不启空闲回收 | `src/octop_browser/idle.py:137` |
| `OctopSettings` | `cdp_max_message_size` | `int \| None` | `33554432` | `0` 转 `None` | 影响 `websockets.connect(max_size=...)` | `src/octop_browser/settings.py:171` |
| `PrivacySettings` | `input_policy` | `InputPolicy` | `mask-sensitive` | `none/mask-sensitive/mask-all` | 录制写盘前决定 `value` 是否脱敏 | `src/octop_browser/record/models.py:15`、`src/octop_browser/record/privacy.py:74` |
| `PrivacySettings` | `url_query_policy` | `InputPolicy` | `mask-sensitive` | 同上 | `none` 时 URL 原样落盘 | `src/octop_browser/record/privacy.py:28` |
| `PrivacySettings` | `screenshot_policy` | `ScreenshotPolicy` | `off` | `off/on-error/on-step-or-error/every-event` | 当前采集链路不产出截图，由 daemon 固定传 `off` | `src/octop_browser/record/models.py:17`、`src/octop_browser/cli.py:583` |
| `RecordReplaySettings` | `base_dir` | `Path` | `state_dir()/record-replay` | 任意可写路径 | 决定 socket/pid/录制目录树 | `src/octop_browser/record/settings.py:24` |
| 子进程 env | `XDG_RUNTIME_DIR` | `str` | `/tmp/runtime-octop-browser-{uid}` | — | `prepare_chrome_launch` 写入并 `chmod 0o700` | `src/octop_browser/cdp/launch_prep.py:76` |
| 子进程 env | `BROWSER_USE_PROFILES_DIR` | `str` | `profile.data_dir.parent` | — | 仅对 Chrome 子进程生效，不改全局 settings | `:216` |
| 子进程 env | `NO_COLOR` / `FORCE_COLOR` / `NODE_DISABLE_COLORS` | `str` | `1` / `0` / `1` | — | 禁止 Playwright Node 安装器输出 ANSI | `src/octop_browser/playwright_download.py:159` |
| 子进程 env | `DEBIAN_FRONTEND` | `str` | `noninteractive` | — | apt 原生批次免交互 | `src/octop_browser/linux_deps.py:256` |

构建期另有 `PYPI_TOKEN`（`Makefile:21`，`make publish` 交互输入或环境注入）与 `SKIP_PRECOMMIT`（`.githooks/pre-commit:8`，跳过 `make all` 门禁），二者不进入运行时 `OctopSettings`。`scripts/record_replay_smoke.py:142` 单独读 `BROWSER_USE_CDP_PORT_START`，默认 `19550`。

## 4. 下游服务端点与凭据安全规则

| 下游目标 | 地址 / 模型配置来源 | 凭据存储与脱敏规则 | 未配置时的默认回退 | 源码锚点 |
|---|---|---|---|---|
| Chrome CDP | `cfg.cdp_host` + `cdp_port_start + index` | 无凭据；`localhost` 禁止硬编码 | 默认 `localhost:9222` 起避让 | `src/octop_browser/cdp/launcher.py:369`、`src/octop_browser/profile.py:158` |
| 远端 Chrome | `BROWSER_USE_CDP_WS_URL` | 无凭据 | 未设置走本地 launcher | `src/octop_browser/settings.py:159` |
| Playwright CDN | 常量 `https://cdn.playwright.dev`、`https://cdn.npmmirror.com/binaries/playwright` 或 `PLAYWRIGHT_DOWNLOAD_HOST` | 无凭据 | 三个候选按 TTFB 竞速 | `src/octop_browser/playwright_download.py:16`、`:17`、`:46` |
| MCP SSE | `MCP_HOST`/`MCP_PORT` | 无鉴权层，暴露即全网可达 | 未设置走 stdio | `src/octop_browser/mcp_server.py:499` |
| 录制隐私 | `PrivacySettings` | 敏感值落盘前替换为 `{{sensitive_value}}`，URL query 键命中 `URL_KEYS` 改 `***` | 默认 `mask-sensitive` | `src/octop_browser/record/privacy.py:79`、`:35` |

诚实核验：源码中不存在 `*.woa.com` 或内部平台地址硬编码，也无处回显或写日志的密钥；`PYPI_TOKEN` 仅用于 `Makefile` 发布目标且未打印。两个 CDN 常量是公开地址，按 `PLAYWRIGHT_DOWNLOAD_HOST` 配置优先覆盖。

## 5. 共变耦合与修改清单（Agent Co-Change Playbook）

- **新增环境变量**：`OctopSettings` 字段（`src/octop_browser/settings.py:128`）→ `tests/unit/conftest.py` 的 `BROWSER_USE_` 前缀清理循环（`tests/unit/conftest.py:20`、`:25`）→ README 配置表与本页 → `skills/octop-browser/SKILL.md` 与 `skills/octop-browser-zh/SKILL.md` 的对外说明。
- **修改默认值**：`_env_*` 助手（`:66`、`:95`、`:100`、`:105`）、`tests/unit/test_settings.py` 断言与 [领域模型](../business/domain-models/tool-result-and-metrics.md) 的字段字典联动。
- **修改 tri-state 键**：`_env_tristate`（`src/octop_browser/cdp/launcher.py:235`）、`_skip_pip_bootstrap`（`src/octop_browser/install.py:123`）、`_multi_pip_bootstrap_enabled`（`:145`）三处真值集合必须一致。
- **修改子进程 env**：`prepare_chrome_launch`（`src/octop_browser/cdp/launch_prep.py:207`）、`plain_cli_env`（`src/octop_browser/playwright_download.py:151`）与 [Chromium 进程契约](../integrations/downstream/chromium-process.md) 联动。
- **回归**：`pytest tests/unit/test_settings.py tests/unit/test_mode.py tests/unit/test_launcher.py tests/unit/test_install.py tests/unit/test_playwright_download.py`，命令见 [构建与单测映射](../operations/dev-and-test.md)。
