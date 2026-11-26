---
kind: downstream-contract
scope: record-daemon-ipc
status: draft
origin: generated
source_paths: [src/octop_browser/record/daemon.py, src/octop_browser/record/models.py]
symbols: [RecordDaemon, dispatch, handle, send_request, is_running, ensure_daemon, socket_path, pid_path, PrivacySettings, RecordingManifest]
upstream: [integrations/index.md, architecture/record-daemon.md]
downstream: [business/wf-record-capture.md]
---

# 下游出向接口契约：录制守护进程 Unix Socket JSON 协议

`record` 与 `replay` 的 CLI/MCP 入口在 `record start`（无 `--duration`）时并不在本进程录制，而是把**一行 JSON 请求**写入独立守护进程的 Unix socket，读取**一行 JSON 应答**即断开。协议为「一请求一连接一响应」，无长连接、无流式帧；守护进程是跨进程黑盒边界，其内存态不在本仓文档可核验范围，见 [认知边界](../../operations/boundary.md)。

## 1. 封装定位与连接契约

| 契约项 | 精确值 / 规则 | 源码锚点 |
|---|---|---|
| 传输 | `asyncio.open_unix_connection(str(socket_path()))`，`reader.readline()` / `writer.write(line + "\n")` | `src/octop_browser/record/daemon.py:149`、`:160`、`:162` |
| socket 路径 | `settings.base_dir / "daemon.sock"`，pid 文件 `daemon.pid` | `src/octop_browser/record/daemon.py:132`、`:136` |
| 请求编码 | `json.dumps(request, ensure_ascii=False) + "\n"`，UTF-8 | `src/octop_browser/record/daemon.py:160` |
| 应答解码 | `dict(json.loads(raw.decode("utf-8")))`，单行 | `src/octop_browser/record/daemon.py:165` |
| 客户端超时 | `send_request` 默认 `timeout=5.0`，`is_running` 用 `1.0` | `src/octop_browser/record/daemon.py:140`、`:170` |
| 服务端 | `asyncio.start_unix_server(self.handle, path=str(sock))`，`serve_forever()` | `src/octop_browser/record/daemon.py:114`、`:118` |
| 公共成功判定 | 应答 `ok` 字段为真 | `src/octop_browser/record/daemon.py:41`、`:82` |
| 异常包络 | 服务端 `handle` 捕获任意异常回 `{"ok": False, "error": str(exc)}` | `src/octop_browser/record/daemon.py:32` |

## 2. 本仓上游调用方反查表

| 本仓封装方法 | 上游调用模块与函数 | 所属流程 | 调用点锚点 |
|---|---|---|---|
| `send_request` | `cli._run_record` 的 `daemon-stop/status/stop/start` | [CLI 组件](../../architecture/cli.md) | `src/octop_browser/cli.py:545`、`:547`、`:549`、`:577` |
| `send_request` | `mcp_server.call_tool` 的 `browser_record_start/stop/status` | [MCP 服务](../../architecture/mcp-server.md) | `src/octop_browser/mcp_server.py:405`、`:416`、`:426` |
| `ensure_daemon` | `cli` 的 `daemon-start`、`mcp_server` 的 `browser_record_start` | [录制采集](../../business/wf-record-capture.md) | `src/octop_browser/cli.py:543`、`src/octop_browser/mcp_server.py:401` |
| `is_running` | `ensure_daemon` 的就绪轮询 | [录制守护](../../architecture/record-daemon.md) | `src/octop_browser/record/daemon.py:191` |
| `start_daemon_process` | `ensure_daemon` 未就绪分支 | [录制守护](../../architecture/record-daemon.md) | `src/octop_browser/record/daemon.py:193` |

## 3. 请求命令总清单

| 序号 | `command` | 读写类型 | 触发入口 | 分发分支 | 定义锚点 |
|---|---|---|---|---|---|
| 1 | `ping` | 读 | `is_running()` | `:41` | `src/octop_browser/record/daemon.py:41-42` |
| 2 | `start` | 写 | CLI/MCP `record start` | `:43` | `src/octop_browser/record/daemon.py:43-63` |
| 3 | `stop` | 写 | CLI/MCP `record stop` | `:64` | `src/octop_browser/record/daemon.py:64-81` |
| 4 | `status` | 读 | CLI/MCP `record status` | `:82` | `src/octop_browser/record/daemon.py:82-83` |
| 5 | `shutdown` | 写 | CLI `record daemon-stop` | `:84` | `src/octop_browser/record/daemon.py:84-90` |
| — | 其他任意值 | — | — | `Unknown command` 错误 | `src/octop_browser/record/daemon.py:91` |

## 4. 逐命令请求字典与响应解包契约（Full Dict Schemas）

### 4.1 公共请求帧

```json
{"command": "status"}
```

| 字典键 | 类型 | 必填条件 | 默认值 | 值来源 | 组装行号 |
|---|---|---|---|---|---|
| `command` | `str` | 必填 | — | 调用方显式构造 | `src/octop_browser/record/daemon.py:40` |
| 其余键 | 依命令而定 | 见下表 | — | CLI 用 `argparse.Namespace`，MCP 用 `arguments` 字典 | `src/octop_browser/cli.py:549`、`src/octop_browser/mcp_server.py:406` |

### 4.2 `start` 请求与应答

| 请求键 | 类型 | 必填 | 默认 | 服务端消费逻辑 | 行号 |
|---|---|---|---|---|---|
| `command` | `str` | 是 | — | 固定 `"start"` | `:43` |
| `profile` | `str` | 否 | `"default"` | 传给 `RecordController.start_in_process` | `:56` |
| `privacy` | `str` | 否 | `"mask-sensitive"` | 写入 `PrivacySettings.input_policy` | `:51`、`src/octop_browser/record/models.py:15` |
| `name` | `str` | 否 | `None` | 保存为 `active_name`，供停录时 `skill_name` | `:58`、`:61` |
| `screenshots` | `str` | 否 | `"off"` | 写入 `PrivacySettings.screenshot_policy` | `:53` |

服务端把 `url_query_policy` 硬编码为 `"mask-sensitive"`（`src/octop_browser/record/daemon.py:52`），不接受请求覆盖。应答在 `start_in_process` 返回的 `{"ok", "recordingId", "store", "startUrl", "name"}` 上追加 `daemon: True`（`:62`），字段字典见 [录制领域模型](../../business/domain-models/recording-artifacts.md)。

### 4.3 `stop` 请求与应答

| 请求键 | 类型 | 必填 | 默认 | 服务端消费逻辑 | 行号 |
|---|---|---|---|---|---|
| `command` | `str` | 是 | — | 固定 `"stop"` | `:64` |
| `recording_id` | `str` | 否 | `None` | 非空且不等于活跃 id 时返回错误（`:68`） | `:67` |
| `name` | `str` | 否 | `active_name` | 停录时 `skill_name` 覆盖 | `:75` |
| `generate_steps` | `bool` | 否 | `True` | 为假时不生成 `steps.json` 与 skill 草稿 | `:74` |

应答为 `RecordSession.stop` 结果加 `ok: True`（`src/octop_browser/record/daemon.py:80`）：`recordingId`、`events`，以及 `generate_steps` 为真时的 `steps`、`stepsPath`、`skillDraft`。

### 4.4 `status` / `ping` / `shutdown` 应答字典

| 命令 | 应答键 | 含义与解包 | 行号 |
|---|---|---|---|
| `status` | `{"ok": True, "active": dict \| None}` | `active` 为 `_active_info()`：`recordingId`、`profile`、`startUrl`、`events` | `:82`、`:93` |
| `ping` | `{"ok": True, "active": dict \| None}` | 仅用于 `is_running` 的布尔判定 | `:41`、`:170` |
| `shutdown` | `{"ok": True, "shutdown": True}` | 先停活跃录制再 `call_soon(_close_server)` | `:84`、`:89` |

### 4.5 错误码与不可达降级翻译

| 下游返回 / 条件 | 本仓转换 | 代码行号 |
|---|---|---|
| `{"ok": False, "error": "A recording is already active", "active": {...}}` | CLI/MCP 原样打印，退出码 1 | `src/octop_browser/record/daemon.py:45` |
| `{"ok": False, "error": "No active recording"}` | 同上 | `:66` |
| `{"ok": False, "error": "Active recording is {id}, not {rec_id}"}` | 同上 | `:69` |
| `{"ok": False, "error": "Unknown command: {command}"}` | 同上 | `:91` |
| socket 不存在或连接超时 | `send_request` 返回 `{"ok": False, "error": "Record daemon is not running. Start it with `octop-browser record daemon-start`."}` | `:152` |
| `ensure_daemon` 30 次探活失败 | `{"ok": False, "error": "Daemon did not start", ...}` | `:198` |
| `shutdown` 时存在活跃录制 | 自动 `stop(generate_steps=True)` 再关闭，不丢已采集事件 | `:85` |

## 5. 共变耦合与修改清单（Agent Co-Change Playbook）

- **新增命令**：`dispatch` 分支（`src/octop_browser/record/daemon.py:39`）、CLI `record` 子解析器（`src/octop_browser/cli.py:320`）、MCP `_TOOLS`（`src/octop_browser/mcp_server.py:156`）与本页第 3、4 节同步；请求键必须逐项展开，禁止只写「同 `start`」。
- **修改 `start` 请求键**：三处组装点（`src/octop_browser/cli.py:577`、`src/octop_browser/mcp_server.py:406`、`src/octop_browser/record/daemon.py:50`）与 [参数组装映射](../topology-and-mapping.md) 联动；`PrivacySettings` 字段名与 `InputPolicy` 枚举见 `src/octop_browser/record/models.py:14`。
- **修改应答键**：`_active_info`（`src/octop_browser/record/daemon.py:93`）、`RecordSession.stop`（`src/octop_browser/record/recorder.py:101`）与 `cli._run_record` 的 `data.get("ok", True)` 判定（`src/octop_browser/cli.py:607`）一起检查。
- **特殊协议陷阱**：协议是**单行 JSON + 换行符**，`reader.readline()` 只读一行；请求里任何值含换行都会截断帧。守护进程全部状态在内存，重启即丢失活跃录制（`src/octop_browser/record/daemon.py:20`）。
- **回归**：`pytest tests/unit/test_record_daemon_client.py tests/unit/test_cli.py tests/unit/test_mcp_server.py`，命令见 [构建与单测映射](../../operations/dev-and-test.md)。
