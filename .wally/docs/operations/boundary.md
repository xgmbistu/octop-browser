---
kind: operations
scope: boundary
status: draft
origin: generated
source_paths: [src/octop_browser/mcp_server.py, src/octop_browser/session.py, src/octop_browser/record/recorder.py, src/octop_browser/cdp/launcher.py]
symbols: [_main, _InternalCDPSession.connect, _recorder_source, find_chrome]
upstream: [INDEX.md, overview/system-architecture.md]
downstream: []
---

# 认知边界与外部黑盒声明（Agent Anti-Hallucination Boundary）

本页界定本次 `.wally/docs/` 已核验的源码快照边界、仓库外不可见的黑盒服务、静态分析无法覆盖的动态分发点，以及生成物可信度等级。除显式标为 `origin: human` / `status: verified` 的人工页外，其余自动生成页均为 `status: draft`；Agent 改动核心逻辑前必须按页内 `path:行号` 回读源码字面核验。

## 1. 核验基准快照与生成物状态

- **Git 分支与提交**：`chore/wally-init-20261127-c114` @ `f56249214aa183648d6b684b6f39445fe438e52d`。
- **生成模式与覆盖目录**：`full`（无 `.wiki-meta.json` 基线，源码工作树干净）。已完整扫描 `src/octop_browser/` 全部 40 个受跟踪文件及 `tests/`、`scripts/`、`skills/`、`.github/workflows/`、`.githooks/`、`Makefile`、`pyproject.toml`。
- **生成物可信度声明**：所有 codewiki 管理页 `status: draft`、`origin: generated`，不自称已核验；SOP 专用页与外部权威页仅被链接、不改写，见第 5 节。
- **语言**：`zh-CN`（按「用户提问语言」锁定；目录名、YAML 键名、源码符号与字典 Key 保持原样）。

## 2. 仓库外黑盒系统清单（Out-of-Repo Black Boxes）

| 外部黑盒目标 | 本仓边界文件（`路径:行号`） | 本仓已核实的契约范围 | 不可见的远端黑盒范围 |
|---|---|---|---|
| Chrome / Chromium 浏览器进程 | `src/octop_browser/cdp/launcher.py:497`、`src/octop_browser/cdp/client.py:67` | 启动 argv、CDP 命令字典与返回解包键、`/json/version` 与 `/json` 字段（详见 [Chrome CDP 契约](../integrations/downstream/chrome-cdp.md)） | Chrome 内部渲染、zygote 沙箱行为、真实线上页面内容 |
| Playwright 安装器与 CDN | `src/octop_browser/install.py:280`、`src/octop_browser/playwright_download.py:46` | `pip`/`playwright install` 命令、候选 host、Range 探测与 `InstallEvent` 字典（[Playwright 安装器](../integrations/downstream/playwright-installer.md)） | CDN 真实限流配额、Playwright 内部下载布局细节 |
| Linux 发行版包仓库 | `src/octop_browser/linux_deps.py:220` | 6 种包管理器的包名与前缀矩阵（[Linux 系统依赖](../integrations/downstream/linux-system-deps.md)） | 各发行版仓库实际可用包名与版本 |
| MCP 客户端 / SSE 运行时 | `src/octop_browser/mcp_server.py:527`、`:501` | stdio 帧流、`GET /sse` 与 `POST /messages/` 路由、`TextContent` 包络（[MCP 传输契约](../integrations/downstream/mcp-transport.md)） | uvicorn / starlette / mcp SDK 服务端内部实现 |
| 录制守护独立进程 | `src/octop_browser/record/daemon.py:114` | 单行 JSON 请求/应答字典（[录制守护 IPC](../integrations/downstream/record-daemon-ipc.md)） | 守护进程内存中的活跃 `RecordSession` 状态，重启即丢失 |
| 宿主环境（桌面 / 路径 / sudo） | `src/octop_browser/mode.py:52`、`src/octop_browser/cdp/launcher.py:95`、`src/octop_browser/cdp/launch_prep.py:190` | `DISPLAY`/`WAYLAND_DISPLAY`、`PLAYWRIGHT_BROWSERS_PATH`、`sudo -n --` 提权规则 | 宿主机 env 文件、Chrome 安装位置、sudo 策略的具体值 |

`_main` 在 `MCP_PORT` 设置时才延迟导入 `uvicorn`/`starlette`（`src/octop_browser/mcp_server.py:493`），二者未列入 `pyproject.toml` 运行依赖；`find_chrome` 还读取 `PLAYWRIGHT_BROWSERS_PATH` 与系统安装路径（`src/octop_browser/cdp/launcher.py:95`、`:150`），这些主机侧内容不在 Git 仓内。

## 3. 动态分发与运行期注入边界

| 动态机制位置（`路径:行号`） | 机制说明 | Agent 注意事项 |
|---|---|---|
| `src/octop_browser/tool_interface.py:180` | `getattr(sess, action)` 按字符串动态分发到 `BrowserSession` 方法 | 静态调用图在此断链；新增/重命名动作需查 `_KNOWN_ACTIONS` 白名单（`:20`） |
| `src/octop_browser/mcp_server.py:391` | `call_tool(name, arguments)` 按工具名分发到 `_ACTION_MAP` 或录制控制器 | 工具名与动作名的映射是运行时字典，非静态 import |
| `src/octop_browser/record/recorder.py:152` | `_recorder_source` 把 `CONFIG` JSON 拼进注入 JS，由 `Runtime.bindingCalled` 回传 | 页面侧事件由 `globalThis[CONFIG.bindingName]` 动态调用，静态搜索看不到调用边 |
| `src/octop_browser/session.py:55` | `cfg.cdp_ws_url` 非空时绕过 launcher 直连远端 WS | 该分支下 `switch_to_target` 被禁用（`src/octop_browser/session.py:107`），运行期行为随环境切换 |
| `src/octop_browser/record/daemon.py:114` | `start_unix_server` + 独立子进程，`start_new_session=True` | 跨进程，静态分析无法连接 CLI 投递点与守护消费入口，见 [主干调用链](../overview/callchain-panorama.md) 桥接表 |
| `src/octop_browser/cdp/launcher.py:578` | `subprocess.Popen(cmd, env=chrome_env, start_new_session=True)` | argv 与 env 在运行期拼装，Chrome 二进制不在仓内 |
| `src/octop_browser/record/injected/recorder.js:55` | `emit()` 用 `globalThis[CONFIG.bindingName]` 反射调用 | 绑定名含随机 `__hbr_emit_<hex>`，无法静态枚举 |

## 4. 仓库目录覆盖对账（未映射源码目录 = 0）

| 顶层 / 二级目录 | 归档位置 | 说明 |
|---|---|---|
| `src/octop_browser/`（根包，14 个根级 .py 与 `py.typed`） | [组件技术架构总表](../architecture/index.md) Tier 2/3 + `moduleTree` | `__init__.py`、`cli.py`、`session.py`、`tool_interface.py`、`mcp_server.py`、`settings.py`、`mode.py`、`models.py`、`hooks.py`、`idle.py`、`profile.py`、`install.py`、`linux_deps.py`、`playwright_download.py`、`py.typed` |
| `src/octop_browser/actions/`、`cdp/`、`dom/`、`record/` | 同上 + `architecture/*.md` 各组件页 | 4 个二级子包，`record/injected/recorder.js` 亦在 Tier 3 表 |
| `tests/unit/`、`tests/integration/` | [构建与单测映射](dev-and-test.md) 第 2 节 | 24 个 test 文件与 2 个 conftest 全部纳入「源码模块 → 必跑测试」映射 |
| `scripts/` | [部署与运行时](deployment-and-runtime.md)、[录制采集流程](../business/wf-record-capture.md) | `record_replay_smoke.py` |
| `skills/` | [部署与运行时](deployment-and-runtime.md) 第 1 节 | 中英两份 SKILL.md |
| `.github/workflows/`、`.githooks/` | [构建与单测映射](dev-and-test.md) 第 1、4 节 | CI 矩阵与提交门禁 |
| `assets/`、`.agent/`、`.agents/`、`.claude/`、`.codex/`、`.cursor/`、`.windsurf/`、`.codebuddy/` 配置目录 | [部署与运行时](deployment-and-runtime.md) 第 4 节 | 非源码资产与 IDE 配置，列入外部/配置边界，不参与代码契约 |
| `.wally/`（SOP 任务与配置） | 本页第 5 节 + [部署与运行时](deployment-and-runtime.md) 第 4 节 | SOP 专用，不属于 codewiki 管理页 |

## 5. 外部权威页与排除理由

以下 `.wally/docs/` 页面属 wally-init 生成的 SOP 专用 / 外部权威页，CodeWiki 仅从 [INDEX](../INDEX.md) 链接、不复制正文、不改写为 8 键 YAML 生成页，故不计入 `.wiki-meta.json` 的 `pageOrder`/`pageCount`：

| 外部页 | 排除理由 |
|---|---|
| `apis/index.md`、`apis/_template.md` | SOP API 索引与模板，未由 codewiki 生成 |
| `devops/env.md`、`devops/test-env-deploy.md` | SOP 部署环境文档，deploy 阶段 readiness 为 pending |
| `integration_test/integration_test.md` | SOP 集成测试执行规范 |
| `sqls/README.md` | SOP 数据库模板；本仓无 SQL |
| `unittest/unittest.md` | SOP 单元测试规范 |

## 6. 共变耦合与修改清单（Agent Co-Change Playbook）

- **推进基准快照**：仅在源码工作树干净且全量门禁通过后，才由服务端把 `.wiki-meta.json` 的 `commitHash` 推进到新 HEAD；本次生成的 docs 本身为未提交变更，基线仍指向上述已提交源码 SHA。
- **新增外部黑盒**：在本页第 2 节登记，并在 `integrations/downstream/` 下补一篇完整请求/返回字典契约页，禁止只写「外部黑盒」带过。
- **新增动态分发点**：在第 3 节登记，并在 [主干调用链全景](../overview/callchain-panorama.md) 的静态跳转桥接表补投递方与消费入口。
- **新增源码目录**：在 [组件技术架构总表](../architecture/index.md) Tier 3 表与 `moduleTree` 同步，确保未映射目录恒为 0。
