---
kind: config-dict
scope: configuration
status: draft
origin: generated
source_paths: [src/octop_browser/settings.py, src/octop_browser/mode.py, src/octop_browser/cdp/launcher.py, src/octop_browser/cdp/launch_prep.py, src/octop_browser/record/settings.py, src/octop_browser/playwright_download.py, src/octop_browser/install.py, src/octop_browser/mcp_server.py, pyproject.toml, Makefile]
symbols: [OctopSettings, state_dir, normalize_mode, _env_tristate, RecordReplaySettings, build_download_candidates, _skip_pip_bootstrap, _main]
upstream: [../INDEX.md, ../overview/system-architecture.md]
downstream: [../operations/deployment-and-runtime.md, ../business/domain-models/index.md]
---

# 配置项、环境变量与动态开关全集

本仓配置全部来自进程环境变量与显式构造的 `OctopSettings` / `RecordReplaySettings` 对象，无数据库配置表。除发布用的 `PYPI_TOKEN` 外，无任何密钥字段；所有外部地址都走 `cdp_host` / CDN 常量，不在业务代码硬编码内网地址。

## 1. 配置覆盖优先级链

`显式构造对象字段` > `进程环境变量（os.environ / os.getenv）` > `state_dir() 派生的默认路径` > `代码硬编码默认值`。

关键陷阱：`OctopSettings` 每个字段用 `field(default_factory=lambda: _env_*(...))`，**每次实例化都重读环境**；模块级 `settings` 单例在 import 时读一次（`src/octop_browser/settings.py:109-185`）。`ProfileManager` 在 `base_dir` 被覆盖时若不传 `settings`，端口仍来自全局单例（`src/octop_browser/profile.py:98-117`）。

## 2. 进程环境变量全集

### 2.1 浏览器与 CDP（`BROWSER_USE_*`）

| 环境变量 | 类型 | 代码默认值 | 必填 | 控制行为与边界 | 读取锚点 |
|---|---|---|---|---|---|
| `BROWSER_USE_MODE` | str 枚举 | `auto` | 否 | `auto/headed/headless`，经 `normalize_mode()` 校验 | `src/octop_browser/settings.py:178-180`、`src/octop_browser/mode.py:26-40` |
| `BROWSER_USE_PROFILES_DIR` | path | `~/.octop-browser/profiles` | 否 | Chrome user-data-dir 根目录 | `src/octop_browser/settings.py:128-132` |
| `BROWSER_USE_SCREENSHOTS_DIR` | path | `~/.octop-browser/screenshots` | 否 | 截图 PNG 输出目录 | `src/octop_browser/settings.py:133-138` |
| `BROWSER_USE_CDP_HOST` | str | `localhost` | 否 | HTTP/WebSocket 探测 host；非 loopback 禁止本地启动/终止 | `src/octop_browser/settings.py:139-143`、`src/octop_browser/cdp/launcher.py:516-523` |
| `BROWSER_USE_CDP_PORT_START` | int | `9222` | 否 | profile 端口分配起始值 | `src/octop_browser/settings.py:144-146` |
| `BROWSER_USE_CHROME_BIN` | path | 空（自动探测） | 否 | 显式 Chrome 路径，查找顺序第一位 | `src/octop_browser/settings.py:147-149`、`src/octop_browser/cdp/launcher.py:163-164` |
| `BROWSER_USE_CDP_WS_URL` | url | 空 | 否 | 非空时跳过 launcher 直连远端 CDP，且禁用切标签 | `src/octop_browser/settings.py:159-161`、`src/octop_browser/session.py:55-57,107-110` |
| `BROWSER_USE_CDP_TIMEOUT` | float | `30.0` | 否 | 单条 CDP 命令等待秒数 | `src/octop_browser/settings.py:150-152`、`src/octop_browser/cdp/client.py:48` |
| `BROWSER_USE_LAUNCH_RETRIES` | int | `20` | 否 | `/json/version` 轮询次数 | `src/octop_browser/settings.py:153-155`、`src/octop_browser/cdp/launcher.py:367` |
| `BROWSER_USE_LAUNCH_DELAY` | float | `0.25` | 否 | 轮询间隔秒 | `src/octop_browser/settings.py:156-158`、`src/octop_browser/cdp/launcher.py:368` |
| `BROWSER_USE_CDP_MAX_MESSAGE_SIZE` | int | `33554432`（32 MiB） | 否 | WebSocket 帧上限，`0` → `None`（不设上限） | `src/octop_browser/settings.py:171-177`、`src/octop_browser/cdp/client.py:67-70` |
| `BROWSER_USE_VIEWPORT_WIDTH` | int | `1440` | 否 | `Emulation.setDeviceMetricsOverride` 宽度 | `src/octop_browser/settings.py:165-167`、`src/octop_browser/session.py:83-94` |
| `BROWSER_USE_VIEWPORT_HEIGHT` | int | `900` | 否 | 同上，高度 | `src/octop_browser/settings.py:168-170` |
| `BROWSER_USE_IDLE_TIMEOUT_MINUTES` | float | `0.0`（关闭） | 否 | 本机 profile 空闲回收分钟数，仅本机 host 生效 | `src/octop_browser/settings.py:162-164`、`src/octop_browser/idle.py:137-139` |
| `BROWSER_USE_NO_SANDBOX` | 三态 | 未设置 | 否 | `1/true/yes/on` 强制 `--no-sandbox`；`0/false/no/off` 强制关闭自动探测 | `src/octop_browser/cdp/launcher.py:302-309` |
| `BROWSER_USE_DISABLE_GPU` | 三态 | 跟随 headless | 否 | 强制或禁止 `--disable-gpu` | `src/octop_browser/cdp/launcher.py:263-266` |
| `BROWSER_USE_DISABLE_DEV_SHM_USAGE` | 三态 | Linux 为真 | 否 | 强制或禁止 `--disable-dev-shm-usage` | `src/octop_browser/cdp/launcher.py:277-280` |

三态解析函数 `_env_tristate()` 对未识别值返回 `None`（即沿用默认），见 `src/octop_browser/cdp/launcher.py:235-249`。

### 2.2 录制与回放（`BROWSER_RECORD_*`）

| 环境变量 | 类型 | 默认值 | 控制行为 | 读取锚点 |
|---|---|---|---|---|
| `BROWSER_RECORD_REPLAY_DIR` | path | `~/.octop-browser/record-replay` | 录制根目录（含 `daemon.sock`、`recordings/`） | `src/octop_browser/record/settings.py:24-29` |
| `BROWSER_RECORD_MAX_EVENT_BYTES` | int | `65536` | 单条 JS 事件 payload 字节上限 | `src/octop_browser/record/settings.py:30-32`、`src/octop_browser/record/recorder.py:264-268` |
| `BROWSER_RECORD_MAX_EVENTS_PER_SECOND` | int | `100` | 每秒事件数上限 | `src/octop_browser/record/settings.py:33-35`、`src/octop_browser/record/recorder.py:232-238` |

### 2.3 安装引导与镜像

| 环境变量 | 默认值 | 控制行为 | 读取锚点 |
|---|---|---|---|
| `PLAYWRIGHT_DOWNLOAD_HOST` | 空 | 自定义下载镜像；官方别名集合被排除，正式候选优先 | `src/octop_browser/playwright_download.py:18,21-27,51-59` |
| `PLAYWRIGHT_BROWSERS_PATH` | 空 | Playwright 浏览器缓存根，影响二进制查找 | `src/octop_browser/cdp/launcher.py:95-98` |
| `OCTOP_SKIP_PLAYWRIGHT_PIP` | 空 | 真值时跳过 pip 自动引导 | `src/octop_browser/install.py:76,123-125` |
| `HARNESS_SKIP_PLAYWRIGHT_PIP` | 空 | 上述变量的旧名，仍兼容 | `src/octop_browser/install.py:78,124` |
| `OCTOP_MULTI_PIP_BOOTSTRAP` | 空 | 真值时依次尝试 uv 与 python -m pip | `src/octop_browser/install.py:145-149` |
| `HARNESS_MULTI_PIP_BOOTSTRAP` | 空 | 上述变量的旧名 | `src/octop_browser/install.py:146-147` |

### 2.4 MCP 服务与宿主环境

| 环境变量 | 默认值 | 控制行为 | 读取锚点 |
|---|---|---|---|
| `MCP_PORT` | 空 | 非空则启用 SSE HTTP 模式而非 stdio | `src/octop_browser/mcp_server.py:491-498` |
| `MCP_HOST` | `0.0.0.0` | SSE 监听地址，非空端口时生效 | `src/octop_browser/mcp_server.py:499` |
| `DISPLAY` / `WAYLAND_DISPLAY` | 空 | `auto` 模式下 Linux 判定有无桌面 | `src/octop_browser/mode.py:50-52,72-73` |
| `XDG_RUNTIME_DIR` | 由代码强制写入 | Linux 启动前自愈为 `/tmp/runtime-octop-browser-<uid>` | `src/octop_browser/cdp/launch_prep.py:38-79` |
| `PROGRAMFILES` / `PROGRAMFILES(X86)` / `LOCALAPPDATA` | 空 | Windows Chrome 标准安装路径探测 | `src/octop_browser/cdp/launcher.py:102,135-147` |
| `USERNAME` / `USER` | 空 | Windows 下临时目录 scope token 兜底 | `src/octop_browser/cdp/launch_prep.py:49-52` |
| `NO_COLOR` / `FORCE_COLOR` / `NODE_DISABLE_COLORS` | 子进程内固定 `1`/`0`/`1` | 抑制 Node/Chalk 安装器 ANSI 输出 | `src/octop_browser/playwright_download.py:151-162` |
| `PYPI_TOKEN` | 空 | 仅发布 Makefile 使用，不明文落库 | `Makefile:20-21,88-101` |

## 3. 动态运行时开关表

| 配置域 | 键 | 默认值 | 取值范围 | 生效时机与副作用 | 锚点 |
|---|---|---|---|---|---|
| 单例配置 | `settings` | import 时构造 | `OctopSettings` 实例 | 模块级共享；测试应新建 `OctopSettings()` 而非改单例 | `src/octop_browser/settings.py:183-185` |
| Profile 端口账本 | `.octop-browser-profiles.json` | `{}` | `str → int` | 同名复用、新名取最小空闲端口 | `src/octop_browser/profile.py:123-163` |
| 页面目标黏性 | `.octop-browser-target.json` | 无文件 | `{"target_id": str}` | 跨 CLI 调用重连同一标签 | `src/octop_browser/profile.py:45-92` |
| 录制隐私 | `PrivacySettings.input_policy` | `mask-sensitive` | `none\|mask-sensitive\|mask-all` | 事件落盘前脱敏 | `src/octop_browser/record/models.py:14-17`、`src/octop_browser/record/privacy.py:74-81` |
| 录制隐私 | `PrivacySettings.url_query_policy` | `mask-sensitive` | 同上 | query 中 11 类敏感键替换为 `***` | `src/octop_browser/record/privacy.py:12-40` |
| 录制隐私 | `PrivacySettings.screenshot_policy` | `off` | 四态 | CLI 固定传 `off`，daemon 取请求 `screenshots` 键 | `src/octop_browser/cli.py:559-563`、`src/octop_browser/record/daemon.py:50-54` |
| 空闲控制器缓存 | `_controllers` 字典 | `{}` | `(Path, host, port) → controller` | 同 key 复用，回收后注销 | `src/octop_browser/idle.py:19,141-151` |

## 4. 端点与凭据安全规则

| 目标 | 地址/路径来源 | 凭据与脱敏 | 未配置时行为 | 锚点 |
|---|---|---|---|---|
| Chrome CDP | `cfg.cdp_host` + profile 端口，或 `cfg.cdp_ws_url` | 无凭据；事件中的敏感值在落盘前替换 | 自动探测 Chrome；找不到报可操作安装提示 | `src/octop_browser/settings.py:139-161`、`src/octop_browser/record/privacy.py:61-81` |
| Playwright CDN | 三个候选常量 + `PLAYWRIGHT_DOWNLOAD_HOST` | 无凭据；探测只发 1 KiB Range GET | 全失败退回原候选顺序 | `src/octop_browser/playwright_download.py:16-17,46-148` |
| 系统包管理器 | PATH 探测得到的二进制 | `sudo -n` 免交互；无密码提示 | 无管理器时报 `manual_hint()` | `src/octop_browser/linux_deps.py:182-217` |
| MCP SSE | `MCP_HOST:MCP_PORT` | 无鉴权层，默认绑定 `0.0.0.0`，属网络暴露面 | 未设端口走 stdio | `src/octop_browser/mcp_server.py:491-525` |
| PyPI 发布 | `PYPI_REPO` / `PYPI_TOKEN` | 仅 Makefile 使用，不进文档与日志 | 未设时交互式读取 | `Makefile:20-21,88-101` |

## 5. 共变耦合与修改清单

- 新增 `BROWSER_USE_*` 变量：会被 `tests/unit/conftest.py` 的 `_ENV_PREFIX` 自动清理；同步本表与 `overview/glossary.md`。
- 改配置默认值：同步 `pyproject.toml` 文档描述与 `tests/unit/test_settings.py` 断言。
- 改 `MCP_HOST` 默认值：涉及对外网络暴露，需同步 `../operations/boundary.md`。
- 改脱敏策略：Python 正则（`src/octop_browser/record/privacy.py:11-24`）与注入 JS（`src/octop_browser/record/injected/recorder.js:13-17`）两处必须一致。

## 6. 关联文档

- [系统技术架构](../overview/system-architecture.md) · [核心数据模型](../business/domain-models/index.md) · [部署与运行时](../operations/deployment-and-runtime.md)
