---
kind: component
scope: cli
status: draft
origin: generated
source_paths: [src/octop_browser/cli.py, src/octop_browser/tool_interface.py]
symbols: [_build_parser, _ACTION_ALIAS, _action_kwargs, _run_action, _run_record, _run_replay, main, browser_tool]
upstream: [INDEX.md, contracts/api-reference.md]
downstream: [architecture/mcp-server.md, business/index.md]
---

# CLI 命令树与动作委托组件（UI / CLI）

`cli.py` 用 `argparse` 构造 24 个顶层命令、`record` 下 10 个子命令与 `replay run` 共 35 条入口。每个动作命令经 `_ACTION_ALIAS` 归一化后委托给 `browser_tool`，输出由 `--json` 决定人类文本或完整 `ToolResult` 序列化。CLI 进程短命，会话靠 launcher 附着既有 CDP 端口实现跨调用复用（`src/octop_browser/cli.py:10`）。

## 1. 命令与子命令分发表

| 命令 / 子命令 | 入口函数 | 源码锚点 | 核心闭环 | 备注 |
|---|---|---|---|---|
| `install-browser` | `main` 直分支 | `src/octop_browser/cli.py:637` | `chromium_executable()` 命中即退出，否则 `ensure_chromium(quiet=...)` | Playwright 仅作一次性下载器 |
| `navigate` / `dom-tree` / `click` 等 21 个动作命令 | `_run_action` | `src/octop_browser/cli.py:514` | `_action_kwargs` 组装参数 → `browser_tool` → `_format_result` | `open` 强制改走 `list_tabs` 加 `urls` |
| `record doctor/daemon-start/daemon-stop/status/stop/start/list/show/generate-steps/generate-skill` | `_run_record` | `src/octop_browser/cli.py:537` | `RecordController` / `ensure_daemon` / `send_request` / `RecordingStore` | `start --duration>0` 走进程内会话 |
| `replay run <id>` | `_run_replay` | `src/octop_browser/cli.py:610` | `--input key=value` 聚合为 `inputs` → `ReplayRunner().run` | 退出码取决于 `status == "passed"` |
| `--version` | `_package_version` | `src/octop_browser/cli.py:47` | `importlib.metadata.version("octop-browser")`，缺失回退 `"unknown"` | 注册于 `src/octop_browser/cli.py:111` |

全量入向命令与参数字典见 [入向接口契约全集](../contracts/api-reference.md) 与 [CLI 动作契约](../contracts/api/browser-actions.md)。

## 2. 状态容器与动作委托机制

- **公共参数**：`_add_common_args` 为所有动作命令注入 `--profile`（默认 `"default"`）与 `--json`（`dest="as_json"`），见 `src/octop_browser/cli.py:55`；`_add_mode_args` 用互斥组提供 `--headed/--headless/--auto`，仅首次建会话生效，见 `src/octop_browser/cli.py:70`。
- **别名委托**：`_ACTION_ALIAS` 把连字符命令转为下划线动作（如 `dom-tree → dom_tree`、`eval-js → eval_js`），见 `src/octop_browser/cli.py:413`；未列入的命令名原样传给 `getattr(sess, action)`，见 `src/octop_browser/tool_interface.py:180`。
- **参数翻译**：`_action_kwargs` 逐命令把 `argparse.Namespace` 转为 `browser_tool` 关键字参数，例如 `click --xy X Y` 拆成 `x` 与 `y`，见 `src/octop_browser/cli.py:444`；`go-back/go-forward/reload/list-tabs` 不附加参数，见 `src/octop_browser/cli.py:497`。
- **互斥目标**：`click` 与 `select` 的目标组为 `required=True`（`src/octop_browser/cli.py:202`、`src/octop_browser/cli.py:247`），`type/fill` 的目标组可缺省（`:215`、`:223`），差异直接影响 `_action_kwargs` 是否注入 `ref` 或 `selector`。

## 3. 动作 → 后端绑定矩阵

| CLI 命令 | 处理函数 | 后端调用 | 输出与反馈 |
|---|---|---|---|
| 21 个动作命令 | `_action_kwargs` (`src/octop_browser/cli.py:426`) | `browser_tool(action=..., profile=..., mode=..., **kwargs)` (`src/octop_browser/cli.py:523`) | `--json` 输出 `result.model_dump(mode="json")`；否则正文或 `ERROR: {error}` (`src/octop_browser/cli.py:502`) |
| `record start` | `_run_record` (`src/octop_browser/cli.py:557`) | `ensure_daemon()` 加 `send_request({"command":"start", ...})` | 打印 JSON 字典，`ok` 为假时退出码 1 |
| `replay run` | `_run_replay` (`src/octop_browser/cli.py:610`) | `ReplayRunner().run(..., inputs=inputs)` | 打印回放报告，`status != "passed"` 退出码 1 |

结果渲染的失败分支统一走 `sys.stderr` 且退出码 1（`src/octop_browser/cli.py:532`）；`_run_action` 还保留一层兜底 `except` 把任何逃逸异常打印为 `ERROR:` 并返回 1（`:527`）。

## 4. 共变耦合与修改清单（Agent Co-Change Playbook）

1. 在 `_build_parser` 增加 `sub.add_parser` 与参数：`src/octop_browser/cli.py:96`。
2. 若为新动作，登记 `_ACTION_ALIAS` (`src/octop_browser/cli.py:413`) 并在 `_action_kwargs` 写翻译分支 (`src/octop_browser/cli.py:426`)，同时保证 `_KNOWN_ACTIONS` 与 `BrowserSession` 存在同名项。
3. 同步 [入向接口契约全集](../contracts/api-reference.md)、[CLI 动作契约](../contracts/api/browser-actions.md) 与 MCP `_TOOLS`（[MCP 工具契约](../contracts/api/mcp-tools.md)）。
4. 补 CLI 回归 `pytest tests/unit/test_cli.py`；录制回放分支核对 [录制守护](record-daemon.md) 的请求字典，命令清单见 [构建与单测映射](../operations/dev-and-test.md)。
