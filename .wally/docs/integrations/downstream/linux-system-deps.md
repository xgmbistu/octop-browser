---
kind: downstream-contract
scope: linux-system-deps
status: draft
origin: generated
source_paths: [src/octop_browser/linux_deps.py, src/octop_browser/install.py]
symbols: [build_install_steps, detect_package_manager, with_privileges, manual_hint, InstallStep, _PACKAGES, _FONT_PACKAGES, _INSTALL_PREFIX, _run_install_deps, _stream_install_deps]
upstream: [integrations/index.md, integrations/downstream/playwright-installer.md]
downstream: []
---

# 下游出向接口契约：Linux 系统依赖与包管理器

Playwright 官方 `install-deps` 只认 Debian/Ubuntu 的 `apt-get`；本仓 `linux_deps.py` 为 TencentOS/OpenCloudOS/RHEL/SUSE/Arch/Alpine 补齐原生包管理器路径，并把 CJK 字体拆成可选步骤。出向「请求」是 `InstallStep` 字典描述的 argv 列表，经 `subprocess.run` 或 `asyncio.create_subprocess_exec` 执行。各发行版包仓库属仓库外黑盒，见 [认知边界](../../operations/boundary.md)。

## 1. 封装定位与连接契约

| 契约项 | 精确值 / 规则 | 源码锚点 |
|---|---|---|
| 主构造器 | `build_install_steps(playwright_cmd) -> list[InstallStep]` | `src/octop_browser/linux_deps.py:220` |
| 管理器探测顺序 | `apt-get` → `dnf` → `yum` → `zypper` → `pacman` → `apk`，取首个 `shutil.which` 命中 | `src/octop_browser/linux_deps.py:25`、`:182` |
| Debian 路径 | 先 Playwright `install-deps`（完整 `*t64` 名单），再原生 apt 兜底 | `src/octop_browser/linux_deps.py:238` |
| 非 Debian 路径 | 跳过 Playwright，直接用原生管理器装共享库 | `src/octop_browser/linux_deps.py:245` |
| 字体步骤 | `optional=True`，库成功后才跑，单包失败不回滚 | `src/octop_browser/linux_deps.py:263` |
| 提权 | 非 root 时前缀 `sudo -n --`，`-n` 永不提示，避免 TTY 挂死 | `src/octop_browser/linux_deps.py:190` |
| 适用范围 | `sys.platform == "linux"`；其他平台直接返回成功 | `src/octop_browser/install.py:198` |

## 2. 本仓上游调用方反查表

| 本仓封装方法 | 上游调用模块与函数 | 所属流程 | 调用点锚点 |
|---|---|---|---|
| `build_install_steps` | `install._run_install_deps`（同步安装） | [安装引导](../../business/wf-chromium-install.md) | `src/octop_browser/install.py:202` |
| `build_install_steps` | `install._stream_install_deps`（流式安装） | [Playwright 安装器](playwright-installer.md) | `src/octop_browser/install.py:439` |
| `manual_hint` | `verify_chromium` 缺库错误文案 | [Playwright 安装器](playwright-installer.md) | `src/octop_browser/install.py:266` |
| `manual_hint` | `_stream_install_deps` 无管理器 / 全失败提示 | [安装引导](../../business/wf-chromium-install.md) | `src/octop_browser/install.py:441`、`:477` |
| `with_privileges` | `_native_batch_step` 与 `_font_steps` | 本页 4.3 节 | `src/octop_browser/linux_deps.py:259`、`:281` |

## 3. 封装方法总清单

| 序号 | 函数签名 | 出向动作 | 重试 / 幂等 | 定义锚点 |
|---|---|---|---|---|
| 1 | `detect_package_manager() -> str \| None` | `shutil.which` 探测 | 每次重算 | `src/octop_browser/linux_deps.py:182-187` |
| 2 | `build_install_steps(playwright_cmd) -> list[InstallStep]` | 组装有序步骤列表 | 纯函数 | `src/octop_browser/linux_deps.py:220-248` |
| 3 | `_native_batch_step(manager) -> InstallStep` | 单次安装全部共享库 | 首个库步骤成功即跳过后续库步骤 | `src/octop_browser/linux_deps.py:251-260` |
| 4 | `_font_steps(manager) -> list[InstallStep]` | 每个字体包一步 | 均 `optional=True` | `src/octop_browser/linux_deps.py:263-285` |
| 5 | `with_privileges(cmd) -> list[str]` | 加 `sudo -n --` 前缀 | 非 root 才生效 | `src/octop_browser/linux_deps.py:190-206` |
| 6 | `manual_hint(manager=None) -> str` | 生成人工修复命令 | 纯函数 | `src/octop_browser/linux_deps.py:209-217` |

## 4. 逐方法请求字典与响应解包契约（Full Dict Schemas）

### 4.1 `InstallStep` 出向字典（`src/octop_browser/linux_deps.py:172`）

```json
{"label": "playwright install-deps", "cmd": ["python", "-m", "playwright", "install-deps", "chromium"], "env": null, "optional": false}
```

| 键 | 类型 | 必填条件 | 默认值 | 值来源与转换逻辑 | 行号 |
|---|---|---|---|---|---|
| `label` | `str` | 必填 | — | `playwright install-deps` / 管理器名 / `{manager} cjk-fonts` | `:241`、`:258`、`:280` |
| `cmd` | `list[str]` | 必填 | — | `[*_INSTALL_PREFIX[manager], *_PACKAGES[manager]]`，apt 再前缀 `env DEBIAN_FRONTEND=noninteractive`，最后经 `with_privileges` | `:252`、`:255`、`:259` |
| `env` | `dict \| None` | 可空 | `None` | 当前构造路径均不设置，保留给子进程环境注入 | `:178` |
| `optional` | `bool` | 可空 | `False` | 字体步骤显式置 `True`，库步骤保持默认 | `:179`、`:282` |

### 4.2 管理器 → 包名与前缀字典全表

| 管理器 | `_INSTALL_PREFIX` | `_PACKAGES`（共享库，按序） | `_FONT_PACKAGES`（CJK 字体） | 行号 |
|---|---|---|---|---|
| `apt-get` | `["apt-get","install","-y"]` | `libnss3, libnspr4, libatk1.0-0, libatk-bridge2.0-0, libcups2, libdrm2, libgbm1, libxkbcommon0, libxcomposite1, libxdamage1, libxfixes3, libxrandr2, libasound2, libpango-1.0-0, libx11-6, libxext6` | `fonts-noto-cjk` | `:29`、`:144`、`:161` |
| `dnf` | `["dnf","install","-y"]` | `nss, nspr, atk, at-spi2-atk, cups-libs, libdrm, mesa-libgbm, libX11, libXcomposite, libXdamage, libXext, libXfixes, libXrandr, libxkbcommon, pango, alsa-lib` | `google-noto-sans-cjk-ttc-fonts, google-noto-cjk-fonts, wqy-zenhei-fonts` | `:47`、`:145`、`:164` |
| `yum` | `["yum","install","-y"]` | 与 `dnf` 同集（独立常量副本） | 与 `dnf` 同集 | `:65`、`:150`、`:165` |
| `zypper` | `["zypper","--non-interactive","install","-y"]` | `mozilla-nss, mozilla-nspr, libatk-1_0-0, libatk-bridge-2_0-0, libcups2, libdrm2, Mesa-libgbm1, libX11-6, libXcomposite1, libXdamage1, libXext6, libXfixes3, libXrandr2, libxkbcommon0, libpango-1_0-0, alsa` | `noto-sans-cjk-fonts` | `:83`、`:155`、`:166` |
| `pacman` | `["pacman","-S","--noconfirm","--needed"]` | `nss, nspr, atk, at-spi2-atk, libcups, libdrm, mesa, libx11, libxcomposite, libxdamage, libxext, libxfixes, libxrandr, libxkbcommon, pango, alsa-lib` | `noto-fonts-cjk` | `:101`、`:156`、`:167` |
| `apk` | `["apk","add","--no-cache"]` | `nss, nspr, atk, at-spi2-core, cups-libs, libdrm, mesa-gbm, libx11, libxcomposite, libxdamage, libxext, libxfixes, libxrandr, libxkbcommon, pango, alsa-lib` | `font-noto-cjk` | `:119`、`:157`、`:168` |

### 4.3 执行返回与失败翻译

| 下游条件 | 本仓解包 / 兜底 | 行号 |
|---|---|---|
| 非 Linux | `_run_install_deps` 直接 `return True`（不适用） | `src/octop_browser/install.py:198` |
| 某个库步骤 `returncode == 0` | `libs_ok = True`，跳过后续库步骤 | `src/octop_browser/install.py:217`、`:203` |
| 某个字体步骤 `returncode == 0` | `fonts_ok = True`，其余字体步骤跳过 | `src/octop_browser/install.py:219`、`:205` |
| 全部库步骤失败 | `return False`，但调用方仍继续 `verify_chromium` 以给出精确缺库信息 | `src/octop_browser/install.py:222`、`:364` |
| 未检测到任何包管理器 | 流式路径产出 `{"log": "No package manager detected. ..."}` 后 `{"done": True, "success": False}` | `src/octop_browser/install.py:440`、`:442` |
| `manual_hint` 无管理器 | 返回 `Run: sudo playwright install-deps chromium` | `src/octop_browser/linux_deps.py:212` |
| `manual_hint` 有管理器 | `Run: sudo {prefix} {前 6 个包名} ...` | `src/octop_browser/linux_deps.py:214`、`:216` |

刻意不使用 `dnf --skip-unavailable`：TencentOS 3 / RHEL 8 的 yum-compat dnf 会因未知参数静默跳过全部 CJK 字体（`src/octop_browser/linux_deps.py:269`），因此字体改为每包独立可选步骤。

## 5. 共变耦合与修改清单（Agent Co-Change Playbook）

- **新增包管理器**：`_MANAGERS`（`src/octop_browser/linux_deps.py:25`）、`_PACKAGES`（`:28`）、`_FONT_PACKAGES`（`:143`）、`_INSTALL_PREFIX`（`:160`）四处必须同时补键，缺一会让 `build_install_steps` 抛 `KeyError`。
- **修改包名单**：`manual_hint` 只展示前 6 个包名（`:216`），排在最前的必须是真正阻塞 Chrome 启动的库；同步更新 [Playwright 安装器](playwright-installer.md) 的缺库文案。
- **修改 `InstallStep` 字段**：`_run_install_deps` 的 `step.cmd/step.env/step.optional`（`src/octop_browser/install.py:202`）与 `_stream_install_deps` 的同名访问（`:448`）成对修改。
- **特殊协议陷阱**：`with_privileges` 用 `sudo -n --`，非交互环境若 sudo 需密码会立即失败而非挂起；`pkill` 与包管理器仅 POSIX 有效。
- **回归**：`pytest tests/unit/test_linux_deps.py tests/unit/test_install.py`，命令见 [构建与单测映射](../../operations/dev-and-test.md)。
