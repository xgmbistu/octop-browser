---
kind: component
scope: cli-and-agent-skill-assets
status: draft
origin: generated
source_paths: [src/octop_browser/cli.py, skills/octop-browser/SKILL.md, skills/octop-browser-zh/SKILL.md]
symbols: [main, _build_parser, _ACTION_ALIAS, _action_kwargs, _format_result, _run_action, _run_record, _run_replay]
upstream: [../INDEX.md]
downstream: [api-and-mcp.md, record-worker.md, ../contracts/api/cli-commands.md]
---

# CLI 交互与 Agent Skill 资产组件

`octop-browser` 是一个无构建的 argparse 命令树：所有浏览器动作最终汇入 `browser_tool()`，录制/回放/安装走独立分支；随仓发布的两份 Skill 文件把「先 dom-tree 再 click、用 ref 不用坐标、命名 profile 保登录态」的使用规约固化给外部 Agent。逐命令参数见 [`../contracts/api/cli-commands.md`](../contracts/api/cli-commands.md)。

## 1. 子命令分发表

| 命令族 | 子命令 | 入口函数 | 源码锚点 | 交互闭环 |
|---|---|---|---|---|
| 安装 | `install-browser` | `main()` 直接处理 | `src/octop_browser/cli.py:637-643` | 已有二进制打印路径退出 0，否则 `ensure_chromium()` |
| 浏览器动作 | `navigate/open/dom-tree/screenshot/click/type/fill/press/wait/select/scroll/hover/eval-js/go-back/go-forward/reload/new-tab/switch-tab/close-tab/list-tabs/close-session` | `_run_action()` | `src/octop_browser/cli.py:514-534` | 解析 → `browser_tool()` → `_format_result()` |
| 录制 | `record doctor/daemon-start/daemon-stop/status/start/stop/list/show/generate-steps/generate-skill` | `_run_record()` | `src/octop_browser/cli.py:537-607` | 多数命令经 Unix socket 发给 daemon；`--duration` 走进程内会话 |
| 回放 | `replay run` | `_run_replay()` | `src/octop_browser/cli.py:610-623` | `ReplayRunner.run()` 输出报告，`status=passed` 才返回 0 |
| 元信息 | `--version` / `--help` | `argparse` 内建 | `src/octop_browser/cli.py:111-116` | `_package_version()` 用 `importlib.metadata.version` |

`--profile` 与 `--json` 由 `_add_common_args()` 注入动作子命令（`src/octop_browser/cli.py:55-67`）；`--headed/--headless/--auto` 互斥组由 `_add_mode_args()` 注入且只在每 profile 首次调用生效（`src/octop_browser/cli.py:70-93`）。

## 2. 状态容器与动作委托机制

- **无持久状态**：CLI 进程短生命周期，会话连续性依赖 CDP 端口重连与 profile 目标黏性文件，而非 CLI 内部变量（`src/octop_browser/cli.py:1-19`）。
- **命令名到 action 的别名表**：`_ACTION_ALIAS` 把 9 个连字符命令映射为下划线 action（`src/octop_browser/cli.py:413-423`），`open` 特例改为 `list_tabs`（`src/octop_browser/cli.py:518-522`）。
- **参数翻译**：`_action_kwargs()` 按 `args.command` 分支把 argparse Namespace 转成 `browser_tool` kwargs，例如 `click --xy X Y` 拆成 `x`/`y`（`src/octop_browser/cli.py:426-499`）。
- **输出分流**：`--json` 走 `result.model_dump(mode="json")`；失败写 stderr 并返回退出码 1（`src/octop_browser/cli.py:502-511,531-534`）。
- **录制 JSON 包络**：`_run_record()` / `_run_replay()` 统一 `json.dumps(ensure_ascii=False)`，缩进由 `as_json` 决定（`src/octop_browser/cli.py:604-607,620-623`）。

## 3. 动作 → 后端 API 绑定矩阵

| CLI 子命令 | 处理函数（`路径:行号`） | 调用的后端接口 | 反馈机制 |
|---|---|---|---|
| `navigate` | `_run_action` (`src/octop_browser/cli.py:514-534`) | `browser_tool("navigate", url=...)` | ToolResult 文本或完整 JSON |
| `open` | `_run_action` (`src/octop_browser/cli.py:520-522`) | `browser_tool("list_tabs", urls=[...])` | 返回打开后的标签列表 |
| `screenshot` | `_action_kwargs` (`src/octop_browser/cli.py:437-443`) | `browser_tool("screenshot", full_page/element_ref/path)` | 返回 PNG 路径 |
| `record start --duration N` | `_run_record` (`src/octop_browser/cli.py:557-571`) | `RecordController.start_in_process()` + `session.stop()` | 进程内录制，不依赖 daemon |
| `record start`（默认） | `_run_record` (`src/octop_browser/cli.py:572-585`) | `ensure_daemon()` → `send_request({"command":"start",...})` | daemon 不可用时回传可操作错误 |
| `replay run --input k=v` | `_run_replay` (`src/octop_browser/cli.py:610-623`) | `ReplayRunner.run(recording_id, inputs)` | 回放报告落盘 + stdout 摘要 |

## 4. 随仓 Agent Skill 资产

| 资产路径 | 语言 | 固化规约 | 锚点 |
|---|---|---|---|
| `skills/octop-browser/SKILL.md` | 英文 | 9 条核心规则：先 dom-tree、默认 interactive、禁硬编码坐标、命名 profile、结束关会话 | `skills/octop-browser/SKILL.md:13-24` |
| `skills/octop-browser-zh/SKILL.md` | 中文 | 同规约中文版，供中文 Agent 直接复制 | `skills/octop-browser-zh/SKILL.md:13-24` |

两份 Skill 使用标准 frontmatter（`name`/`description`/`allowed-tools`），设计为可 `cp -r` 到其他 Agent 项目；`record generate-skill` 产出的草稿沿用同一格式（`src/octop_browser/record/skill_generator.py:46-52`）。

## 5. 共变耦合与修改清单

1. 新增 CLI 子命令：`_build_parser()` 注册 → `_ACTION_ALIAS`/`_action_kwargs()` 补充映射 → `contracts/api/cli-commands.md` → `tests/unit/test_cli.py`。
2. 改公开动作列表或环境变量：必须同步两份 Skill 文件与 `overview/glossary.md`，否则外部 Agent 仍按旧规约调用。
3. 改输出格式：影响脚本消费方，`--json` 字段与 `ToolResult` 模型保持一致（`src/octop_browser/models.py:20-33`），跑 `tests/unit/test_cli.py`。
4. 改录制命令参数：同步 daemon `dispatch()` 可识别的键（`src/octop_browser/record/daemon.py:39-91`），跑 `tests/unit/test_record_daemon_client.py`。

## 6. 关联文档

- [API 与 MCP 分发组件](api-and-mcp.md) · [CLI 命令 Schema](../contracts/api/cli-commands.md) · [入向接口全集](../contracts/api-reference.md)
