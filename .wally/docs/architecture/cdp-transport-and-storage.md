---
kind: component
scope: cdp-transport-and-storage
status: draft
origin: generated
source_paths: [src/octop_browser/cdp/client.py, src/octop_browser/profile.py, src/octop_browser/settings.py, src/octop_browser/mode.py, src/octop_browser/record/store.py, src/octop_browser/record/settings.py]
symbols: [CDPClient, CDPSessionError, send, send_passive, enable_domain, Profile, ProfileManager, OctopSettings, RecordingStore, RecordReplaySettings, normalize_mode]
upstream: [architecture/browser-session-engine.md, contracts/configuration.md]
downstream: [integrations/index.md, integrations/downstream/chrome-cdp.md]
---

# CDP 传输底座、Profile 持久化与配置解析组件（数据 / 适配层）

本页聚焦**通用 CDP WebSocket 传输底座、Chrome profile 端口与目标粘性的磁盘状态、进程级配置解析、录制产物目录树**。各外部下游系统「发什么请求字典、解包什么返回键」一律在 [上下游集成总览](../integrations/index.md) 下属的 [Chrome CDP 契约](../integrations/downstream/chrome-cdp.md)、[Chromium 进程契约](../integrations/downstream/chromium-process.md) 与 [录制守护 IPC](../integrations/downstream/record-daemon-ipc.md) 独立展开，本页不替代逐字典契约。

## 1. 本地持久化契约（磁盘文件与状态字典）

| 磁盘文件 / 状态路径 | 唯一约束 | 权威读写函数（`路径:行号`） | 事务、锁与安全约束 |
|---|---|---|---|
| `<profiles_dir>/.octop-browser-profiles.json` | profile 名 → 端口字典，按名排序写回 | `ProfileManager._load_ports` (`src/octop_browser/profile.py:123`)、`_save_ports` (`:143`)、`_assign_port` (`:151`) | `mkdir(parents=True)` 后整文件覆盖写；读取时非 `dict` 或非 `int` 值直接丢弃 (`:135`) |
| `<profile_dir>/.octop-browser-target.json` | 单键 `target_id` 字符串 | `Profile.load_target` (`src/octop_browser/profile.py:49`)、`save_target` (`:69`)、`clear_target` (`:86`) | 读失败返回 `None`，写失败仅记 debug 日志，属 best-effort；跨进程粘性靠此文件 |
| `<profiles_dir>/<name>/` | 一个 profile 一个 Chrome `--user-data-dir` | `ProfileManager.get_or_create` (`src/octop_browser/profile.py:165`) | `delete` 用 `shutil.rmtree` 整目录删除 (`:180`) |
| `<record-replay>/recordings/<id>/manifest.json` | `recordingId` 主键 | `RecordingStore.write_manifest` (`src/octop_browser/record/store.py:64`) | 先写 `.json.tmp` 再 `replace()` 原子替换 (`:67`)，目录 `chmod 0o700`、事件文件 `chmod 0o600` (`:52`) |
| `<record-replay>/recordings/<id>/events.jsonl` | 逐行追加 JSON | `append_event` (`src/octop_browser/record/store.py:82`)、`read_events` (`:88`) | `open("a")` 每行 `flush()`；按 `seq` 排序由 `SemanticProcessor` 承担 |
| `<record-replay>/recordings/<id>/steps.json`、`draft.skill.md`、`final.skill.md` | 单录制单文件 | `write_steps` (`:99`)、`write_skill` (`:116`) | 全量覆盖写；`skill_path(draft=True)` 固定 `draft.skill.md` (`:40`) |
| `<record-replay>/daemon.sock`、`daemon.pid` | 单实例 Unix socket | `socket_path` / `pid_path` (`src/octop_browser/record/daemon.py:132`) | `run()` 启动前先 `unlink()` 陈旧 socket (`:108`) |

`state_dir()` 优先 `~/.octop-browser`，若仅存在旧目录 `~/.harness-browser` 则复用以免遗留登录 cookie 与录制失联（`src/octop_browser/settings.py:78`）；对应 legacy 状态文件名常量见 `src/octop_browser/profile.py:29`。

## 2. CDP WebSocket 传输底座契约

`CDPClient`（`src/octop_browser/cdp/client.py:30`）是仓内唯一 CDP 帧封装，所有动作与录制共用。

| 底座能力 | 统一规则 | 源码锚点 |
|---|---|---|
| 连接 | `websockets.connect(ws_url, max_size=_settings.cdp_max_message_size)`，默认 32 MiB 防止 `Page.captureScreenshot` 触发 1009 | `src/octop_browser/cdp/client.py:67` |
| 出向帧 | `{"id": msg_id, "method": method, "params": params or {}}` 经 `json.dumps` 后 `ws.send` | `src/octop_browser/cdp/client.py:91` |
| 应答匹配 | `_pending[msg_id] = Future`，`_recv_loop` 按 `msg["id"]` 弹栈并 `set_result` | `src/octop_browser/cdp/client.py:95`、`src/octop_browser/cdp/client.py:159` |
| 返回解包 | `result.get("result", {})` 为内层字典；含 `error` 键即抛 `CDPSessionError` | `src/octop_browser/cdp/client.py:113` |
| 超时与短路 | `asyncio.wait_for(future, timeout=self._timeout)`，超时抛 `CDPSessionError("Timeout waiting for response to ...")` | `src/octop_browser/cdp/client.py:99` |
| 事件分发 | `elif "method" in msg` 时向 `_listeners[method]` 注入 `"__client"` 键后回调 | `src/octop_browser/cdp/client.py:163` |
| 断线清理 | `_recv_loop` 异常时把全部未完成 Future 置为 `CDPSessionError("Connection lost: ...")` | `src/octop_browser/cdp/client.py:172` |
| 被动探测 | `send_passive()` 以 `track_activity=False` 调用 `send`，不刷新空闲截止期 | `src/octop_browser/cdp/client.py:118` |
| 域使能 | `enable_domain(domain)` 发送 `"{domain}.enable"`；`Input` 域不使能 | `src/octop_browser/cdp/client.py:124` |

`ActivityTracker` 协议（`src/octop_browser/cdp/client.py:23`）由 `BrowserIdleController` 实现，`activity_started/activity_finished` 包住每次 `send`（`:86`、`:112`），是空闲回收判定「真实 CDP 活动」的唯一数据源。

## 3. 配置解析与启动模式

`OctopSettings` 是 `@dataclass`，每个字段用 `field(default_factory=lambda: _env_*(...))`，因此**每次实例化都重读环境变量**（`src/octop_browser/settings.py:128`）；模块级 `settings` 单例在 import 时构造一次（`:185`），单测须新建对象而非改单例。

| 解析函数 | 行为与默认值 | 源码锚点 |
|---|---|---|
| `_env_path` / `_env_float` / `_env_int` / `_env_str` | 环境变量缺失即回落默认；路径用 `Path(val)`，字符串用 `os.environ.get(key, default)` | `src/octop_browser/settings.py:66`、`src/octop_browser/settings.py:95`、`src/octop_browser/settings.py:100`、`src/octop_browser/settings.py:105` |
| `cdp_max_message_size` | 值为 `0` 时转 `None`（禁用上限），否则原值 | `src/octop_browser/settings.py:171` |
| `normalize_mode` | 空值回落 `auto`，非法值抛 `ValueError("Invalid browser mode ...")` | `src/octop_browser/mode.py:26` |
| `has_desktop_environment` | macOS/Windows 恒为真；Linux 需 `DISPLAY` 或 `WAYLAND_DISPLAY` | `src/octop_browser/mode.py:43` |
| `resolve_headless` | `headless→True`、`headed→False`、`auto→not has_desktop_environment()` | `src/octop_browser/mode.py:55` |
| `RecordReplaySettings` | `BROWSER_RECORD_REPLAY_DIR` 默认 `state_dir()/record-replay`，事件上限 65536 字节、每秒 100 条 | `src/octop_browser/record/settings.py:22` |

完整环境变量表与覆盖优先级见 [配置手册](../contracts/configuration.md)，启动模式三态在 `BrowserSession.create` 的优先级见 [会话引擎](browser-session-engine.md)。

## 4. 共变耦合与修改清单（Agent Co-Change Playbook）

- **新增持久化状态文件**：`RecordingStore.create` 的子目录清单（`src/octop_browser/record/store.py:49`）与 `recording_summary` 的返回键（`:135`）必须同步扩列，否则 `record show` 看不到新产物。
- **修改 profile 状态文件名**：`_TARGET_STATE_FILE` / `_PROFILE_PORTS_FILE`（`src/octop_browser/profile.py:24`）与两条 legacy 回退（`:29`）成组修改，缺失回退会导致老 profile 端口漂移、重连到错误标签。
- **修改 CDP 帧结构**：`send` 的 `json.dumps`（`src/octop_browser/cdp/client.py:91`）与 `_recv_loop` 的 `msg["id"]` 解包（`:159`）必须对称；新增 `id` 复用或漏弹栈会挂死 `wait_for`。
- **修改配置字段**：`OctopSettings` 字段（`src/octop_browser/settings.py:128`）、`tests/unit/conftest.py` 的 `dataclasses.fields` 重置循环（`tests/unit/conftest.py:33`）与 [配置手册](../contracts/configuration.md) 三处联动。
- **必跑回归**：`pytest tests/unit/test_settings.py tests/unit/test_mode.py tests/unit/test_profile.py tests/unit/test_idle.py tests/unit/test_record_replay_store_skill.py`。
