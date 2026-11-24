---
kind: operations
scope: pitfalls-and-adr
status: draft
origin: generated
source_paths: [pyproject.toml, src/octop_browser/session.py, src/octop_browser/dom/builder.py, src/octop_browser/dom/refs.py, src/octop_browser/tool_interface.py, src/octop_browser/install.py, src/octop_browser/hooks.py, src/octop_browser/record/semantic.py, src/octop_browser/cdp/launch_prep.py, src/octop_browser/cdp/launcher.py]
symbols: [browser_tool, RefCache.invalidate, DOMBuilder.build, _have_npx, _pip_install_cmd, HooksMixin.on, _USER_NS_CACHE]
upstream: [../INDEX.md, ../overview/system-architecture.md]
downstream: []
---

# 关键架构决策、高危雷区与存量死路径警示

本页汇总决定本仓结构的设计权衡，以及 Agent 修改代码时极易误踩的非直觉耦合。动手前先核对「高危雷区」，搜索到同名函数时再核对「存量死路径」确认它是否真的在生效。

## 1. 核心架构决策（Key ADRs）

| 编号 | 决策主题 | 核心实现机制与源码锚点 | Agent 修改时必须遵守的硬约束 |
|---|---|---|---|
| `ADR-01` | 运行时只用纯 CDP，不引入 Playwright/Selenium | 依赖仅 `websockets/pydantic/aiohttp/mcp` (`pyproject.toml:24-31`)；Playwright 仅作一次性下载器 (`src/octop_browser/install.py:1-41`) | 不得新增浏览器驱动依赖；安装引导与运行时驱动必须保持解耦 |
| `ADR-02` | 配置每次实例化重读环境，单例只在 import 时读一次 | `field(default_factory=lambda: _env_*)` (`src/octop_browser/settings.py:109-185`) | 测试用 `OctopSettings()` 而非 mutate 单例；新增变量要被 `tests/unit/conftest.py` 清理 |
| `ADR-03` | 稳定 ref + 导航即失效 | `RefCache` (`src/octop_browser/dom/refs.py:6-29`)，四个导航动作清缓存 (`src/octop_browser/actions/navigate.py:28,63,73,83`) | 任何新导航类动作必须清 ref；否则 Agent 拿到已销毁 nodeId |
| `ADR-04` | 登录态唯一来源是 Chrome user-data-dir | `ProfileManager` 按名字分配目录与端口 (`src/octop_browser/profile.py:33-39,165-174`) | 不要新增 cookie/token 自管理路径；profile 名即身份 |
| `ADR-05` | 回放意图而非坐标 | `SemanticProcessor` 折叠事件 (`src/octop_browser/record/semantic.py:338-593`)，`match_target()` 实时重匹配 (`src/octop_browser/record/matcher.py:19-62`) | 不得把录制时 ref/nodeId 当作可复用状态 |
| `ADR-06` | 录制 daemon 走 Unix socket，不开网络端口 | `asyncio.start_unix_server` (`src/octop_browser/record/daemon.py:107-129`) | 不改成 TCP 监听；socket 路径随 `BROWSER_RECORD_REPLAY_DIR` |
| `ADR-07` | 扁平包结构，无前端构建步骤 | 包内子目录仅 `actions/cdp/dom/record`；所有模块同进程导入 | 不引入分层框架或打包式前端资产 |
| `ADR-08` | 首包体积与隐私优先 | 事件脱敏在落盘前完成 (`src/octop_browser/record/recorder.py:240-254`)，截图返回路径不返 base64 (`src/octop_browser/actions/capture.py:1-29`) | 任何新增日志/落盘字段先过脱敏，禁止回显凭据 |

## 2. 修改高危雷区与隐式耦合

| 高危源码位置（`路径:行号`） | 涉及符号 | 隐蔽陷阱机制 | 安全修改标准动作 |
|---|---|---|---|
| `src/octop_browser/tool_interface.py:17,63-68` | `_registry` | 无锁字典，依赖事件循环串行；跨进程同时用同 profile 会互相抢占端口与 target | 多进程场景强制使用不同 profile 名 |
| `src/octop_browser/cdp/launcher.py:652-669` | `get_page_ws_url` | 黏性 target 优先，但缓存 target 可能已失效；代码会 `clear_target()` 后回退 | 切标签后通过 `switch_to_target()` 主动写回，别假设 `/json` 第一项就是当前页 |
| `src/octop_browser/cdp/launch_prep.py:144-186` | `ensure_profile_writable` | `/root` 路径或不可写时把 `Profile.data_dir` 改到 `/tmp/...`，旧目录改名 `*.stale-<ts>`；登录态看似「丢失」 | 排查时先看 warning 日志中的新路径，不要直接删 `*.stale-*` |
| `src/octop_browser/cdp/launch_prep.py:144-152` | `ensure_profile_writable` 注释契约 | 只改传入的 `Profile`，绝不写全局 `BROWSER_USE_PROFILES_DIR`，否则同进程其他 profile 被连带重定向 | 与 `ProfileManager` 协同修改时必须保留局部性语义 |
| `src/octop_browser/dom/builder.py:359-393` | `_build_structured` | 输出 JSON 的 `elements[].selectorCandidates` 是录制回放匹配的唯一输入契约；改键名会让所有旧录制失效 | 字段只增不改；改后跑 `tests/unit/test_dom_builder.py` 与回放单测 |
| `src/octop_browser/dom/refs.py:15-25` | `RefCache` | ref 是每页独立计数，跨页同名 ref 指向不同 nodeId | 切标签必须重建客户端并 `invalidate()` |
| `src/octop_browser/cdp/client.py:118-122` | `send_passive` | 健康探针不刷新空闲 deadline；误改成 `send()` 会让 Chrome 永不回收 | 保留 `track_activity=False` 参数 |
| `src/octop_browser/actions/capture.py:130-168` | `screenshot` | `element_ref` 优先于 `full_page`；full_page 会生成数 MB PNG 并受 32 MiB 帧上限约束 | 默认保持 `full_page=False`；大图场景调 `BROWSER_USE_CDP_MAX_MESSAGE_SIZE` |
| `src/octop_browser/actions/interact.py:178-198` | `fill_text` | 同时发 Ctrl(2) 与 Meta(4) 的 Select-All，依赖浏览器忽略无关修饰键 | 不要简化为单一平台修饰键 |
| `src/octop_browser/cdp/launcher.py:312-347` | `_USER_NS_CACHE` | namespace 探测结果进程内缓存；启动后改内核策略不会生效 | 测试中重置该全局需显式处理 |
| `src/octop_browser/mcp_server.py:499` | `MCP_HOST` | 默认 `0.0.0.0`，启用 SSE 时对所有网卡开放且无鉴权层 | 部署到共享网络前必须外部网关保护或改回 loopback |
| `src/octop_browser/record/semantic.py:122-170` | `_var_for` | 输入值被替换为 `{{name}}`，`example` 字段保留原值；若输入是敏感值，example 可能留下明文 | 敏感分支 `example=""`，不要在日志里打印 `inputs` 字典 |
| `src/octop_browser/record/store.py:99-109` | `write_steps` | `steps.json` 全量覆盖写，与 `events.jsonl` 的 append 语义不同 | 并发生成步骤需要外部串行化 |

## 3. 存量死路径与历史兼容保留代码警示

| 存量代码位置（`路径:行号`） | 符号 / 配置名 | 当前真实状态 | 当前真正生效的主入口 |
|---|---|---|---|
| `src/octop_browser/install.py:623-625` | `_have_npx()` | 源码注释明确「Test helper; kept for symmetry」，全仓无任何调用点 | 实际安装走 `_run_pip_install()` (`src/octop_browser/install.py:152-175`) |
| `src/octop_browser/install.py:141-142` | `_pip_install_cmd()` | 仅返回候选列表首项，全仓无调用点；真正使用 `_pip_install_candidates()` | `src/octop_browser/install.py:128-138,152-175` |
| `src/octop_browser/hooks.py:14-16,27-43` | `page_navigated` 事件 | `on()` 接受注册但无任何代码路径 emit；单测只验证不会抛错 (`tests/unit/test_hooks.py:62`) | `before_action` / `after_action` / `action_error` (`src/octop_browser/session.py:895-903`) |
| `src/octop_browser/actions/capture.py:90-101`、`src/octop_browser/session.py:350-368` | `crop` 参数 | 保留位，当前无独立效果 | `element_ref` / `full_page` 两个真实裁剪分支 (`src/octop_browser/actions/capture.py:130-168`) |
| `src/octop_browser/settings.py:74-92`、`src/octop_browser/profile.py:24-30` | `.harness-browser*` 目录与文件名 | 仅作为旧版本回退读取，新安装不再创建 | `.octop-browser*` 新名 |
| `src/octop_browser/install.py:78,124,146-147` | `HARNESS_SKIP_PLAYWRIGHT_PIP` / `HARNESS_MULTI_PIP_BOOTSTRAP` | 旧环境变量名，仍兼容读取 | `OCTOP_SKIP_PLAYWRIGHT_PIP` / `OCTOP_MULTI_PIP_BOOTSTRAP` |
| `src/octop_browser/cdp/launcher.py:51-81` | `chrome-win` / `chrome-mac` 旧目录布局 | Playwright 已改用 Chrome for Testing 目录名；旧名仅为兼容老安装 | 新布局优先探测 (`src/octop_browser/cdp/launcher.py:59-81`) |
| `src/octop_browser/record/url_filter.py:11-41` | 四类风控/验证码 URL 白名单 | 刻意收窄：不过滤一般登录页，以保留显式登录流程录制 | `is_replayable_page_url()` 的完整判断 (`src/octop_browser/record/url_filter.py:44-53`) |
| 仓库根目录 `AGENTS.md.bk.20261124102147076228` | 历史备份文件 | 非源码、非运行入口，仅供历史追溯 | `AGENTS.md`（通过 `CODEBUDDY.md`/`CLAUDE.md` 软链生效） |

## 4. 共变耦合与修改清单

1. 改 `ADR-03` 相关代码：必须同步 `overview/glossary.md`、`contracts/error-codes.md` 与 `tests/unit/test_navigate_actions.py`。
2. 改 `ADR-05` 相关代码：语义步骤类型、回放分发、Skill 文档三处同改（见 `business/wf-record-replay.md` 共变清单）。
3. 删除「存量死路径」中任一符号前：先全仓 `Grep` 确认无调用，且若是公开名（`page_navigated`）需评估外部 Agent 影响。
4. 新增高危雷区条目时附上真实 `path:line`，避免下游 Agent 依据过期行号修改代码。

## 5. 关联文档

- [系统技术架构](../overview/system-architecture.md) · [模块依赖矩阵](../architecture/module-dep-matrix.md) · [排障 Runbook](runbook-and-observability.md)
