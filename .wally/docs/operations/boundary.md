---
kind: operations
scope: boundary
status: draft
origin: generated
source_paths: [src/octop_browser/session.py, src/octop_browser/cdp/client.py, src/octop_browser/cdp/launcher.py, src/octop_browser/install.py, src/octop_browser/record/daemon.py, src/octop_browser/mcp_server.py]
symbols: [_InternalCDPSession.connect, CDPClient.send, get_page_ws_url, install_chromium_stream, send_request, _main]
upstream: [../INDEX.md]
downstream: []
---

# 认知边界与外部黑盒声明

本套文档只覆盖当前工作树内可字面核验的源码。以下边界用于防止 Agent 把远端服务内部实现、宿主环境配置或动态分发结果当作本仓可见事实。

## 1. 核验基准快照与生成物状态

- **Git 分支**：`chore/wally-init-20261124-c85`
- **提交 SHA**：`1f4a548c6cbd63902c253ea5a96acec54fd92dec`
- **生成模式与覆盖目录**：`FULL`；已完整扫描 `src/octop_browser/`（含 `actions/`、`cdp/`、`dom/`、`record/` 与 `record/injected/`）、`tests/unit/`、`tests/integration/`、`scripts/`、`skills/`、`pyproject.toml`、`Makefile`、`.github/workflows/`、`.githooks/`。
- **生成物可信度**：除显式标为 `origin: human` 或 `status: verified` 的页面外，全部为 `status: draft`、`origin: generated`。Agent 改动核心逻辑前必须按页内 `path:行号` 回读源码字面核验。
- **未作为源码纳入**：`assets/images/banner.jpeg`（图片）、`AGENTS.md.bk.20261124102147076228`（历史备份）、`.wally/` 内 SOP 资产、`.git/`、依赖锁文件 `uv.lock`。这些文件不承载运行时行为。

## 2. 仓库外黑盒系统清单

| 外部黑盒目标 | 本仓边界文件（`路径:行号`） | 本仓已核实的契约范围 | 不可见的远端黑盒范围 |
|---|---|---|---|
| Chrome DevTools Protocol 服务端 | `src/octop_browser/cdp/client.py:75-116`、`src/octop_browser/session.py:63-68` | 帧信封、13 类命令的请求键、返回解包键、超时与错误字面量 | Chrome 内部实现、真实页面事件时序、CDP 协议未使用的域 |
| CDP HTTP 发现端点 | `src/octop_browser/cdp/launcher.py:350-398,618-712` | `/json/version`、`/json`、`/json/new` 的读取字段与 host 来源 | Chrome 版本差异导致的字段缺失、远端防火墙策略 |
| Playwright CDN | `src/octop_browser/playwright_download.py:16-17,46-148` | 三个候选 host、1 KiB Range 探测、TTFB 排序、PHP 环境变量覆盖规则 | CDN 真实配额、返回体结构、镜像可用性 |
| 宿主包管理器与仓库源 | `src/octop_browser/linux_deps.py:182-285` | 六种管理器的探测顺序、包集合、提权命令骨架 | 发行版仓库中包名是否存在、企业镜像策略、sudo 权限 |
| 录制 daemon 的外部客户端 | `src/octop_browser/record/daemon.py:107-165` | Unix socket 单行 JSON 请求/响应字典 | 其他进程是否同时连接、客户端身份与鉴权（本仓无） |
| MCP 客户端 | `src/octop_browser/mcp_server.py:22,367-479,482-530` | 25 个 Tool Schema、stdio/SSE 传输选择 | 客户端侧工具编排、外部 Agent 的记忆与策略 |
| 用户浏览器页面内容 | `src/octop_browser/record/injected/recorder.js:201-248` | 注入脚本采集的 DOM 描述字段与脱敏规则 | 页面自身脚本逻辑、跨站 Cookie 内容、表单后端行为 |

出向请求/返回字典契约已按本仓代码记录于 [`../integrations/index.md`](../integrations/index.md) 及其 downstream 专页；远端内部逻辑严禁猜测。

## 3. 动态分发与运行期注入边界

| 动态机制位置（`路径:行号`） | 机制说明 | Agent 注意事项 |
|---|---|---|
| `src/octop_browser/tool_interface.py:179-182` | `getattr(sess, action)` 按字符串反射调用 | 静态搜索无法枚举实际被调方法；白名单是唯一可信集合 |
| `src/octop_browser/mcp_server.py:391-479` | 按 Tool 名分支，未命中 `_ACTION_MAP` 才查显式分支 | 新增 Tool 必须同时改两处 |
| `src/octop_browser/record/recorder.py:152-175` | 从包内读 `record/injected/recorder.js` 并以字符串注入页面 | 改 JS 后无需重新构建，但需同步 Python 侧 nonce/binding 逻辑 |
| `src/octop_browser/cdp/client.py:152-177` | 接收循环按 CDP `method` 名动态派发 listener | 事件名来自浏览器，不写死在调用点 |
| `src/octop_browser/record/semantic.py:396-593` | 按事件 `kind` 字符串逐分支折叠 | 新 kind 必须进 `_filter_events()` 白名单 |
| `src/octop_browser/install.py:51-59,167-171` | `PLAYWRIGHT_DOWNLOAD_HOST` 在子进程环境注入 | 环境变量来自宿主 shell / MCP 客户端配置，不在 Git 仓内 |
| `src/octop_browser/profile.py:49-92` | 跨进程 target 黏性来自磁盘 JSON，不是进程内状态 | 宿主机上手工编辑该文件会让 CLI 连到意料之外的标签 |

## 4. 静态分析局限

1. `browser_tool()` 的反射调用无法被普通 `Grep` 完整追踪，需结合 `_KNOWN_ACTIONS` 与 `BrowserSession` 方法表。
2. 录制daemon 与 CLI/MCP 之间通过 Unix socket 通信，静态调用图在 `send_request()` / `dispatch()` 处断链；消息字典见 `contracts/api/cli-commands.md`。
3. 注入 JS 在浏览器上下文执行，其事件字段不受 Python 类型检查约束；以 `record/injected/recorder.js` 原文为准。
4. `BROWSER_USE_*`、`MCP_*`、`PLAYWRIGHT_*` 的实际值来自运行环境，文档只记录默认值与读取位置，不记录本机当前值。
5. 集成测试需要真实 Chrome；无浏览器环境下 `tests/integration/conftest.py:6-12` 整体跳过，不能据此断言功能已验证。

## 5. 共变耦合与修改清单

- 新增外部下游系统：在 `../integrations/index.md` 登记并在 `integrations/downstream/` 独立成篇，同时更新本页黑盒清单。
- 新增动态分发点：在本页第 3 节补一行，避免 Agent 用静态搜索误判为死代码。
- 基准快照更新：仅在全部源码变更已被文档覆盖且无未解决漂移时推进 `.wiki-meta.json` 的 `commitHash`。

## 6. 关联文档

- [系统技术架构](../overview/system-architecture.md) · [集成总览](../integrations/index.md) · [部署与运行时](deployment-and-runtime.md)
