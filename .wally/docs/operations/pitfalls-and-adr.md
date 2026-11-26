---
kind: operations
scope: pitfalls-and-adr
status: draft
origin: generated
source_paths: [src/octop_browser/session.py, src/octop_browser/install.py, src/octop_browser/hooks.py, src/octop_browser/profile.py, src/octop_browser/dom/builder.py, src/octop_browser/actions/capture.py, src/octop_browser/record/store.py, pyproject.toml, README.md]
symbols: [BrowserSession, _have_npx, HooksMixin, ProfileManager, DOMBuilder, screenshot, skill_path, ScreenshotPolicy, cdp_max_message_size]
upstream: [INDEX.md, overview/system-architecture.md]
downstream: [operations/boundary.md, operations/dev-and-test.md]
---

# 关键架构决策（ADR）、修改高危雷区与存量死路径警示

本页汇总决定本仓结构的硬性设计权衡、Agent 改代码时极易误踩的隐式耦合，以及**源码中存在但当前主链路未挂载或仅作历史兼容**的函数/参数/枚举。所有「未挂载」结论均以 `Grep` 字面核验：产品代码与测试中的调用点逐项列出，未找到调用点才判为死路径。

## 1. 核心架构决策与不可违背的工程约束（Key ADRs）

| 编号 | 决策主题 | 核心实现机制与源码锚点 | Agent 修改时必须遵守的硬约束 |
|---|---|---|---|
| `ADR-01` | 纯 CDP 直连，Playwright 非运行时依赖 | 手写 `CDPClient` over `websockets`（`src/octop_browser/cdp/client.py:30`）；`pyproject.toml:24` 仅列 `websockets/pydantic/aiohttp/mcp`；`README.md:40` | 禁止把 Playwright/Selenium 重新引入运行时动作链，仅允许 `install-browser` 一次性下载 |
| `ADR-02` | ref 稳定定位 + 导航即失效 | `RefCache`（`src/octop_browser/dom/refs.py:6`）签发 `ref→nodeId`；4 个导航动作调用 `invalidate()`（`src/octop_browser/actions/navigate.py:28`） | 任何新增导航类动作必须显式清空 ref 缓存，禁止把过期 `nodeId` 交给 Agent |
| `ADR-03` | Profile 级登录态持久化 | 一个 `profile` 名固定映射一个 `--user-data-dir`（`src/octop_browser/profile.py:169`） | 禁止为 cookie/auth 另造路径；跨进程粘性靠 `.octop-browser-target.json`（`:24`） |
| `ADR-04` | `localhost` 不硬编码 | 所有 CDP HTTP 探测取 `cfg.cdp_host`（`src/octop_browser/cdp/launcher.py:369`、`src/octop_browser/session.py:121`）；`README.md:344` 配置表 | 新增端口/主机拼接必须走 `OctopSettings.cdp_host`，否则远程/Docker 场景回归失败 |
| `ADR-05` | 配置每次实例化重读环境 | `OctopSettings` 每个字段用 `field(default_factory=lambda: _env_*(...))`（`src/octop_browser/settings.py:128`） | 单测用 `monkeypatch.setenv` 新建对象，禁止改 import 期 `settings` 单例 |
| `ADR-06` | 统一 `ToolResult` 包络 + hooks | `src/octop_browser/models.py:20`、`HooksMixin._fire`（`src/octop_browser/hooks.py:45`）、`_record`（`src/octop_browser/session.py:895`） | 新增动作不得直接抛裸异常到调用方，必须包成 `success=False` 并触发 `action_error` |
| `ADR-07` | `mcp<3` 版本天花板 | `pyproject.toml:28` 注释：mcp 2.x 移除 `Server.list_tools()/call_tool()` 装饰器；依赖写 `mcp>=1.9,<3` | 升级 `mcp` 到 2.x 会令 `mcp_server.py:367`/`:391` 的装饰器在 import 期失效 |
| `ADR-08` | 旧状态目录/文件兼容保留 | `state_dir()` 回退 `~/.harness-browser`（`src/octop_browser/settings.py:89`）；legacy 文件名常量 `src/octop_browser/profile.py:29` | 删除 legacy 回退会孤立既有登录态与录制，必须与迁移方案一起做 |
| `ADR-09` | 录制回放按语义意图而非坐标 | `SemanticProcessor`（`src/octop_browser/record/semantic.py:333`）折叠为 `SemanticStep`，回放用 `match_target`（`src/octop_browser/record/matcher.py:19`） | 禁止把旧 `ref`/`nodeId`/坐标写进 `steps.json`，页面改版即失效 |

## 2. 修改高危雷区与隐式耦合表（Danger Zones & Hidden Couplings）

| 高危源码位置（`路径:行号`） | 涉及符号 | 隐蔽陷阱机制 | 安全修改标准动作 |
|---|---|---|---|
| `src/octop_browser/tool_interface.py:180` | `method = getattr(sess, action)` | **动态反射分发**：动作字符串必须逐字等于 `BrowserSession` 方法名，重命名方法会静默让某个动作变成 `Invalid parameters` | 改名时同步 `_KNOWN_ACTIONS`、CLI `_ACTION_ALIAS`、MCP `_ACTION_MAP` 与全部文档 |
| `src/octop_browser/tool_interface.py:83` | `_is_disconnected_error` | **依赖异常文本字面量** `not connected` / `connection lost`；改 `CDPSessionError` 文案会静默关闭自动重连 | 改异常文案必须同步该谓词与 `src/octop_browser/cdp/client.py:176` |
| `src/octop_browser/profile.py:143` | `_save_ports` | **整文件覆盖写**，不是增量 Patch；并发写会丢失其它 profile 的端口分配 | 先 `_load_ports()` 读全量、合并新键再 `_save_ports()` |
| `src/octop_browser/dom/builder.py:359` | `_build_structured` | 输出的 `elements` 字段名被 `matcher.match_target`（`src/octop_browser/record/matcher.py:19`）与 `_compact_target`（`src/octop_browser/record/semantic.py:44`）硬消费 | 改字段名必须三处同步，否则所有回放目标匹配归零 |
| `src/octop_browser/record/injected/recorder.js:2` | `globalThis.__HBR_RECORDER_CONFIG__` | 注入脚本靠全局配置 + `__hbrRecorderInstalled`（`:4`）去重；改键名或去重逻辑会双监听或不采集 | 与 `RecordSession._recorder_source`（`src/octop_browser/record/recorder.py:152`）同步 |
| `src/octop_browser/mcp_server.py:501` | `SseServerTransport("/messages/")` | 路径必须与 `Route("/messages/")`（`:516`）逐字一致，改名后 POST 消息无处投递 | 两处同时改，并核对 [MCP 传输契约](../integrations/downstream/mcp-transport.md) |
| `src/octop_browser/cdp/client.py:67` | `websockets.connect(max_size=...)` | 默认 1 MiB 会被 `Page.captureScreenshot` 的 base64 PNG 触发 1009；本仓靠 `cdp_max_message_size` 放宽 | 调 `BROWSER_USE_CDP_MAX_MESSAGE_SIZE`，勿移除 `max_size` 参数 |
| `src/octop_browser/record/daemon.py:160` | 单行 JSON + `\n` | 协议用 `reader.readline()` 只读一行，请求值含换行会截断帧 | 序列化前转义或拒绝含换行值 |
| `src/octop_browser/cdp/launch_prep.py:216` | `env["BROWSER_USE_PROFILES_DIR"]` | 只改子进程 env，**不改进程全局 `settings.profiles_dir`**；误改全局会让同进程其它 profile 被重定向 | 保持「profile 级重定向」语义 |
| `src/octop_browser/session.py:141` | `ref_cache.invalidate()` | `switch_to_target` 重建 `CDPClient` 时必须清空 ref，否则旧页面 nodeId 混入新页 | 新增切页路径复制该清理顺序 |

## 3. 存量死路径与历史兼容保留代码警示（Legacy / Unmounted Code Traps）

| 存量代码位置（`路径:行号`） | 符号 / 参数 / 配置名 | 当前真实状态（字面核验结论） | 当前真正生效的主入口 |
|---|---|---|---|
| `src/octop_browser/install.py:623` | `_have_npx()` | **完全未挂载**：全仓 `src/`、`tests/`、`scripts/` 中无调用点，docstring 自述「Test helper; kept for symmetry」 | 无；安装流水线走 `_pip_install_candidates`（`:128`） |
| `src/octop_browser/hooks.py:15`、`:33` | `page_navigated` 事件 | **注册但不触发**：`_VALID_EVENTS` 接受该名，产品代码无 `_fire("page_navigated")`，仅 `tests/unit/test_hooks.py:62` 手工触发 | `before_action`/`after_action`/`action_error` 由 `src/octop_browser/session.py:901` 触发 |
| `src/octop_browser/actions/capture.py:101` | `screenshot(crop=...)` 参数 | **保留参数但无独立效果**：`BrowserSession.screenshot` 仍透传（`src/octop_browser/session.py:364`），`capture.py` docstring 明写「Reserved for future use; currently has no independent effect」 | 实际裁切由 `element_ref` 与 `full_page` 决定（`:130`、`:150`） |
| `src/octop_browser/record/models.py:11` | `ScreenshotPolicy` 的 `on-error`/`on-step-or-error`/`every-event` | **枚举值未挂载**：全部产品调用点固定传 `off`（`src/octop_browser/cli.py:562`、`src/octop_browser/record/daemon.py:53`、`scripts/record_replay_smoke.py:87`） | `screenshot_policy="off"` |
| `src/octop_browser/record/store.py:42` | `final.skill.md` | **只读不写**：`skill_path(draft=False)` 定义在 `:40`，`recording_summary` 读 `skillFinal`（`:140`），但全部 `write_skill` 调用均 `draft=True`（`src/octop_browser/record/recorder.py:124`、`:416`） | `draft.skill.md`（`:40`） |
| `src/octop_browser/cdp/client.py:118` | `send_passive()` | **仅单测使用**：产品代码无调用点，`tests/unit/test_idle.py:108` 用于验证不刷新空闲截止期 | 常规路径走 `send`（`:75`） |
| `src/octop_browser/install.py:78`、`:147` | `HARNESS_SKIP_PLAYWRIGHT_PIP` / `HARNESS_MULTI_PIP_BOOTSTRAP` | **历史兼容别名**：与 `OCTOP_*` 同名键并列读取，仅旧部署脚本仍用 | `OCTOP_SKIP_PLAYWRIGHT_PIP`（`:76`）、`OCTOP_MULTI_PIP_BOOTSTRAP`（`:146`） |
| `src/octop_browser/settings.py:75`、`src/octop_browser/profile.py:29` | `.harness-browser` 目录与 `.harness-browser-*.json` 文件名 | **仅旧安装回退**：`state_dir()`（`:89`）与 `load_target/_load_ports`（`src/octop_browser/profile.py:57`、`:126`）在新路径缺失时读取 | `.octop-browser` 与 `.octop-browser-*.json` |
| `src/octop_browser/profile.py:176`、`:180` | `list_profiles()` / `delete()` | **仅单测使用**：产品链路无调用点，仅 `tests/unit/test_profile.py:107`、`:118` | `get_or_create`（`:165`） |

## 4. 共变耦合与修改清单（Agent Co-Change Playbook）

- **清理死代码**：删除前先用 `Grep` 复核上表每个符号的调用点，尤其 `_have_npx` 与 `page_navigated`；`page_navigated` 还出现在 `README.md` 的 hooks 表（`README.md:327`），需同步文档与 [术语表](../overview/glossary.md)。
- **新增导航类动作**：复制 `src/octop_browser/actions/navigate.py:28` 的 `ref_cache.invalidate()`，并在 [会话引擎](../architecture/browser-session-engine.md) 不变量表登记。
- **升级 `mcp` 依赖**：`pyproject.toml:30` 的 `<3` 天花板与 `mcp_server.py:367`/`:391` 装饰器写法是同一约束的两面，升级需整体重写工具注册方式。
- **回归**：`pytest tests/unit/test_hooks.py tests/unit/test_install.py tests/unit/test_profile.py tests/unit/test_record_replay_store_skill.py tests/unit/test_idle.py`，命令见 [构建与单测映射](dev-and-test.md)。
