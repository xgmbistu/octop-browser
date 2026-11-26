---
kind: api-contract
scope: api-record-replay
status: draft
origin: generated
source_paths: [src/octop_browser/cli.py, src/octop_browser/record/daemon.py, src/octop_browser/mcp_server.py, src/octop_browser/record/recorder.py]
symbols: [_run_record, _run_replay, RecordDaemon.dispatch, send_request, ensure_daemon, start_daemon_process, handle_sse, RecordController, ReplayRunner]
upstream: [contracts/api-reference.md]
downstream: [integrations/downstream/record-daemon-ipc.md, business/wf-record-capture.md]
---

# 录制回放、守护命令与 SSE 路由逐接口契约

本页展开 [入向接口契约全集](../api-reference.md) 中 `record` 10 个子命令、`replay run`、录制守护 5 个 JSON 命令与 SSE 2 条路由的逐项入参 / 出参字典。录制主链路跨进程：CLI/MCP 组装请求 → Unix socket 守护 → `RecordSession` → 磁盘产物，见 [录制守护 IPC](../../integrations/downstream/record-daemon-ipc.md)。

## 1. 公共协议与响应包络

| 维度 | 精确规则 | 源码锚点 |
|---|---|---|
| CLI 输出 | `_run_record` / `_run_replay` 统一 `print(json.dumps(data, ensure_ascii=False, indent=None if as_json else 2))` | `src/octop_browser/cli.py:606`、`:622` |
| CLI 退出码 | `data.get("ok", True)`（record）或 `data.get("status") == "passed"`（replay）决定 0/1 | `:607`、`:623` |
| 异常兜底 | `_run_record` / `_run_replay` 的 `except` 把异常转为 `{"ok": False, "error": str(exc)}` 或 `{"status": "failed", "error": str(exc)}` | `:604`、`:620` |
| daemon 帧 | 单行 `json.dumps(request) + "\n"`，应答单行 `json.loads(raw.decode())` | `src/octop_browser/record/daemon.py:160`、`:165` |
| daemon 超时 | `send_request(timeout=5.0)`，`is_running` 用 `1.0` | `:140`、`:170` |
| 公共成功位 | daemon 应答 `ok`，回放报告 `status == "passed"` | `:41`、`src/octop_browser/record/replay.py:290` |

## 2. `record` 子命令逐项契约（10 项）

| 子命令 | 位置参数 / 选项 | 组装的请求 / 调用 | 应答关键键 | 锚点 |
|---|---|---|---|---|
| `doctor` | `--profile`、`--json` | `RecordController().doctor(profile=...)` | `ok`、`profile`、`cdpPort`、`pageWsUrl` | `src/octop_browser/cli.py:540`、`src/octop_browser/record/recorder.py:341` |
| `daemon-start` | `--json` | `ensure_daemon()` | `ok`、`alreadyRunning`、`socket`、`pid` | `src/octop_browser/cli.py:543`、`src/octop_browser/record/daemon.py:190` |
| `daemon-stop` | `--json` | `send_request({"command": "shutdown"})` | `ok`、`shutdown` | `:545`、`:84` |
| `status` | `--json` | `send_request({"command": "status"})` | `ok`、`active` | `:547`、`:82` |
| `stop` | `--recording-id`、`--name`、`--no-generate-steps`、`--json` | `send_request({"command":"stop","recording_id":...,"generate_steps": not no_generate_steps,"name":...})` | `ok`、`recordingId`、`events`、`steps`、`stepsPath`、`skillDraft` | `:549`、`:553` |
| `start` | `--profile`、`--name`、`--duration`（float，默认 0）、`--privacy`（`none/mask-sensitive/mask-all`）、`--json` | `duration>0` 走 `RecordController.start_in_process`（`PrivacySettings(input_policy=..., url_query_policy="mask-sensitive", screenshot_policy="off")`）；否则 `ensure_daemon()` + `send_request({"command":"start",...,"screenshots":"off"})` | `ok`、`recordingId`、`store`、`startUrl`、`name`、`daemon` | `:557`、`:559`、`:577` |
| `list` | `--json` | `RecordingStore().list_recordings()` → `model_dump(mode="json", by_alias=True)` | `recordings[]` | `:586` |
| `show` | `recording_id`、`--json` | `RecordingStore().recording_summary(recording_id)` | `recordingId/status/profile/createdAt/endedAt/startUrl/endUrl/events/steps/recordingDir/*Path/hasSteps/hasSkillDraft/latestReplayReport` | `:593`、`src/octop_browser/record/store.py:135` |
| `generate-steps` | `recording_id`、`--json` | `RecordController().generate_steps(recording_id)` | `ok`、`recordingId`、`steps`、`stepsPath` | `:595`、`src/octop_browser/record/recorder.py:397` |
| `generate-skill` | `recording_id`、`--name`、`--json` | `RecordController().generate_skill(recording_id, skill_name=...)` | `ok`、`recordingId`、`skillDraft` | `:597`、`:411` |

`record start --privacy` 的默认值 `mask-sensitive` 定义在 `src/octop_browser/cli.py:364`；`record stop` 的 `generate_steps` 由 `--no-generate-steps` 取反（`:553`）。`doctor` 的返回字典在 `src/octop_browser/record/recorder.py:343` 构造。

## 3. `replay run` 契约

| 位置 | 字段 | 类型 / 默认 | 含义 | 锚点 |
|---|---|---|---|---|
| 位置参数 | `recording_id` | `str`（必填） | 录制 id | `src/octop_browser/cli.py:394` |
| 选项 | `--profile` | `str="default"` | 回放所用 profile | `:395` |
| 选项 | `--input key=value` | 可重复，默认 `[]` | 仅含 `=` 的项并入 `inputs` 字典 | `:396`、`src/octop_browser/cli.py:612` |
| 选项 | `--json` | flag | 紧凑 JSON 输出 | `:402` |

调用 `ReplayRunner().run(args.recording_id, profile=..., inputs=inputs)`（`src/octop_browser/cli.py:617`）；报告键 `recordingId/startedAt/status/inputs/stepsLoaded/steps/verification/endedAt/reportPath`，失败时附 `error` 与 `failureArtifacts`（`src/octop_browser/record/replay.py:35`、`:293`）。CLI 仅在 `status == "passed"` 时退出 0。

## 4. 守护 JSON 命令（5 项）与 SSE 路由（2 项）

### 4.1 daemon `dispatch` 请求 / 应答字典

| `command` | 请求键（默认值） | 应答键 | 分发行号 |
|---|---|---|---|
| `ping` | 无 | `ok=True`、`active` | `src/octop_browser/record/daemon.py:41` |
| `start` | `profile="default"`、`privacy="mask-sensitive"`、`screenshots="off"`、`name=None` | `ok`、`recordingId`、`store`、`startUrl`、`name`、`daemon=True` | `:43`、`:50` |
| `stop` | `recording_id=None`、`name=None`、`generate_steps=True` | `ok=True`、`recordingId`、`events`、`steps`、`stepsPath`、`skillDraft` | `:64`、`:73` |
| `status` | 无 | `ok=True`、`active` | `:82` |
| `shutdown` | 无 | `ok=True`、`shutdown=True` | `:84` |
| 其它 | — | `ok=False`、`error="Unknown command: {command}"` | `:91` |

`start` 的 `url_query_policy` 服务端硬编码 `"mask-sensitive"`（`:52`），`PrivacySettings` 字段定义见 `src/octop_browser/record/models.py:14`。错误应答（已有活跃录制、无活跃录制、id 不匹配、守护未运行）全表见 [录制守护 IPC](../../integrations/downstream/record-daemon-ipc.md)。

### 4.2 SSE 路由

| 方法 | 路径 | 处理函数 | 载荷 | 锚点 |
|---|---|---|---|---|
| `GET` | `/sse` | `handle_sse` | 无，建立 SSE 流 | `src/octop_browser/mcp_server.py:503`、`:515` |
| `POST` | `/messages/` | `sse.handle_post_message` | MCP JSON-RPC 帧 | `:516` |

`SseServerTransport("/messages/")`（`:501`）必须与 POST 路由路径一致；`Starlette(routes=[...])` 在 `:513` 注册。仅当 `MCP_PORT` 设置时启用，见 [MCP 传输契约](../../integrations/downstream/mcp-transport.md)。

## 5. 共变耦合与修改清单（Agent Co-Change Playbook）

- **新增 daemon 命令**：`RecordDaemon.dispatch`（`:39`）、CLI `record` 子解析器（`src/octop_browser/cli.py:320`）、`_run_record` 分支（`:537`）、MCP `_TOOLS`（`src/octop_browser/mcp_server.py:156`）与本页四处同步。
- **修改请求键**：CLI 组装（`src/octop_browser/cli.py:549`、`:577`）、MCP 组装（`src/octop_browser/mcp_server.py:406`、`:416`）与 `dispatch` 的 `request.get(key, default)`（`:50`）逐键核对；缺失键会静默取默认而非报错。
- **修改应答键**：`_active_info`（`:93`）、`RecordSession.stop`（`src/octop_browser/record/recorder.py:101`）、`recording_summary`（`src/octop_browser/record/store.py:135`）与 `data.get("ok", True)` 判定（`src/octop_browser/cli.py:607`）联动。
- **回归**：`pytest tests/unit/test_record_daemon_client.py tests/unit/test_cli.py tests/unit/test_mcp_server.py tests/unit/test_record_replay_replay_runner.py`，命令见 [构建与单测映射](../../operations/dev-and-test.md)。
