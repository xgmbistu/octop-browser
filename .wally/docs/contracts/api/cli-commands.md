---
kind: api-contract
scope: cli-commands
status: draft
origin: generated
source_paths: [src/octop_browser/cli.py, src/octop_browser/tool_interface.py, src/octop_browser/record/daemon.py, src/octop_browser/install.py]
symbols: [_build_parser, _action_kwargs, _format_result, _run_action, _run_record, _run_replay, main]
upstream: [../api-reference.md]
downstream: [../../integrations/topology-and-mapping.md, ../../contracts/error-codes.md]
---

# CLI 命令逐接口 Schema

CLI 由 `_build_parser()` 一次性构造（`src/octop_browser/cli.py:96-404`），`main()` 按命令族分派（`src/octop_browser/cli.py:631-649`）。所有动作子命令共享 `--profile`（默认 `default`）与 `--json` 输出开关（`src/octop_browser/cli.py:55-67`）。

## 1. 公共约定

| 维度 | 规则 | 锚点 |
|---|---|---|
| 命令名 | `octop-browser`，由 `[project.scripts]` 指向 `cli:main` | `pyproject.toml:49-50`、`src/octop_browser/cli.py:631-649` |
| 通用选项 | `--profile <name>`、`--json` | `src/octop_browser/cli.py:55-67` |
| 模式选项 | `--headed` / `--headless` / `--auto` 互斥，仅首次调用生效 | `src/octop_browser/cli.py:70-93` |
| 输出 | 成功写 stdout，失败写 stderr；`--json` 输出完整 `ToolResult` | `src/octop_browser/cli.py:502-511,531-534` |
| 退出码 | 动作失败 1；录制 `ok=False` 为 1；回放非 `passed` 为 1 | `src/octop_browser/cli.py:531-534,604-607,620-623` |
| 命令名到 action | `_ACTION_ALIAS` 处理 9 个连字符命令，`open` 特例改 `list_tabs` | `src/octop_browser/cli.py:413-423,518-522` |

## 2. 安装与元信息命令

| 命令 | 位置参数 | 选项 | 行为与退出码 | 锚点 |
|---|---|---|---|---|
| `install-browser` | 无 | `--quiet` | 已有二进制打印路径退出 0；否则 `ensure_chromium(quiet=...)` (`src/octop_browser/install.py:280-369`) 决定 0/1 | `src/octop_browser/cli.py:124-138,637-643` |
| `--version` | 无 | — | `importlib.metadata.version("octop-browser")`，未安装显示 `unknown` | `src/octop_browser/cli.py:47-52,111-116` |
| `--help` | 无 | — | argparse 内建，含 4 条 epilog 示例 | `src/octop_browser/cli.py:97-122` |

## 3. 浏览器动作命令（21 项）

| 命令 | 位置参数 | 专属选项 | 传入 `browser_tool` 的 kwargs | 定义锚点 |
|---|---|---|---|---|
| `navigate` | `url` | 通用 + 模式 | `url` | `src/octop_browser/cli.py:140-144,433-434` |
| `open` | `urls...`（`nargs="+"`） | 通用 + 模式 | `urls`，action 改为 `list_tabs` | `src/octop_browser/cli.py:146-164,431-432,520-522` |
| `dom-tree` | 无 | `--level`（minimal/interactive/full/structured，默认 interactive） | `level` | `src/octop_browser/cli.py:166-185,435-436` |
| `screenshot` | 无 | `--full-page`、`--element-ref`、`--path` | `full_page` / `element_ref` / `path` 仅真值时写入 | `src/octop_browser/cli.py:187-198,437-443` |
| `click` | 无 | `--ref` / `--selector` / `--xy X Y` 三选一必填 | `ref` / `selector` / `x`,`y` | `src/octop_browser/cli.py:200-209,444-450` |
| `type` | `text` | `--ref` / `--selector` | `text` + 可选目标 | `src/octop_browser/cli.py:211-218,451-456` |
| `fill` | `text` | `--ref` / `--selector` | `text` + 可选目标 | `src/octop_browser/cli.py:220-227,457-462` |
| `press` | `key` | 通用 + 模式 | `key` | `src/octop_browser/cli.py:229-233,463-464` |
| `wait` | 无 | `--url-contains`、`--text`、`--selector`、`--timeout-ms`（默认 10000） | 三个条件真值 + `timeout_ms` | `src/octop_browser/cli.py:235-242,465-472` |
| `select` | `value` | `--ref` / `--selector` 二选一必填 | `value` + 目标 | `src/octop_browser/cli.py:244-251,473-478` |
| `scroll` | 无 | `--direction`（up/down/left/right，默认 down）、`--amount`（默认 300） | `direction`, `amount` | `src/octop_browser/cli.py:253-260,479-481` |
| `hover` | `ref` | 通用 + 模式 | `ref` | `src/octop_browser/cli.py:262-266,482-483` |
| `eval-js` | `expression` | 通用 + 模式 | `expression` | `src/octop_browser/cli.py:268-272,484-485` |
| `go-back` | 无 | 通用 + 模式 | 无 | `src/octop_browser/cli.py:274-282` |
| `go-forward` | 无 | 通用 + 模式 | 无 | `src/octop_browser/cli.py:274-282` |
| `reload` | 无 | 通用 + 模式 | 无 | `src/octop_browser/cli.py:274-282` |
| `new-tab` | 无 | `--url` | `url` 非空时写入 | `src/octop_browser/cli.py:285-288,486-488` |
| `switch-tab` | `tab_id` | 通用 + 模式 | `tab_id` | `src/octop_browser/cli.py:290-293,489-490` |
| `close-tab` | 无 | `--tab-id` | `tab_id` 非空时写入 | `src/octop_browser/cli.py:295-298,491-493` |
| `list-tabs` | 无 | 通用 + 模式 | 无 | `src/octop_browser/cli.py:300-302` |
| `close-session` | 无 | `--kill`（终止 Chrome）、`--profile`、`--json`（无模式选项） | `kill` 真值时写入 | `src/octop_browser/cli.py:304-317,494-496` |

`close-session` 默认只断开 CDP，Chrome 继续驻留以便后续命令重连（`src/octop_browser/cli.py:305-316`、`src/octop_browser/tool_interface.py:125-161`）。

## 4. 录制子命令（10 项）

| 命令 | 位置参数 | 选项 | 处理路径 | 定义锚点 |
|---|---|---|---|---|
| `record doctor` | 无 | `--profile`、`--json` | `RecordController.doctor()` | `src/octop_browser/cli.py:323-325,540-541` |
| `record daemon-start` | 无 | `--json` | `ensure_daemon()` | `src/octop_browser/cli.py:327-330,542-543` |
| `record daemon-stop` | 无 | `--json` | `send_request({"command":"shutdown"})` | `src/octop_browser/cli.py:332-335,544-545` |
| `record status` | 无 | `--json` | `send_request({"command":"status"})` | `src/octop_browser/cli.py:337-338,546-547` |
| `record start` | 无 | `--profile`、`--name`、`--duration`（默认 0.0）、`--privacy`（none/mask-sensitive/mask-all，默认 mask-sensitive）、`--json` | 有 duration 走进程内会话；否则经 daemon | `src/octop_browser/cli.py:346-366,557-585` |
| `record stop` | 无 | `--recording-id`、`--name`、`--no-generate-steps`、`--json` | `send_request({"command":"stop",...})` | `src/octop_browser/cli.py:340-344,548-556` |
| `record list` | 无 | `--json` | `RecordingStore().list_recordings()` | `src/octop_browser/cli.py:368-369,586-592` |
| `record show` | `recording_id` | `--json` | `RecordingStore().recording_summary()` | `src/octop_browser/cli.py:371-375,593-594` |
| `record generate-steps` | `recording_id` | `--json` | `RecordController.generate_steps()` | `src/octop_browser/cli.py:377-381,595-596` |
| `record generate-skill` | `recording_id` | `--name`、`--json` | `RecordController.generate_skill()` | `src/octop_browser/cli.py:383-388,597-598` |

`record start --duration N` 在进程内录制 N 秒后自动 `stop(generate_steps=True, skill_name=...)`，不依赖 daemon（`src/octop_browser/cli.py:557-571`）。默认路径若 daemon 启动失败则回传其错误字典而不发 start 请求（`src/octop_browser/cli.py:572-585`）。

## 5. 回放子命令（1 项）

| 命令 | 位置参数 | 选项 | 行为 | 锚点 |
|---|---|---|---|---|
| `replay run` | `recording_id` | `--profile`、`--input key=value`（可重复）、`--json` | 按首个 `=` 切分 inputs → `ReplayRunner.run()`；仅 `status=passed` 退出 0 | `src/octop_browser/cli.py:390-402,610-623` |

回放时敏感值通过 `--input sensitive_value="$MY_PASSWORD"` 注入，录制中只保存 `{{sensitive_value}}` 占位符，不回显原值（`src/octop_browser/record/privacy.py:74-81`）。

## 6. 共变耦合与修改清单

- 新增子命令：`_build_parser()` 注册 → `_ACTION_ALIAS`/`_action_kwargs()` 映射 → [`api-reference.md`](../api-reference.md) → `tests/unit/test_cli.py`。
- 改通用选项：影响全部动作子命令，同步 MCP 侧默认值（`src/octop_browser/mcp_server.py:24-347`）与 [`mcp-tools.md`](mcp-tools.md)。
- 改录制命令键：必须同步 daemon `dispatch()` 可识别键（`src/octop_browser/record/daemon.py:39-91`）与 MCP 构造的请求字典。
- 改退出码语义：影响 CI 与脚本消费，跑 `tests/unit/test_cli.py` 并核对 `.github/workflows/ci.yml` 的 `make test` 步骤。
