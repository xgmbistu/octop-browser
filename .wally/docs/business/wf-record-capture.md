---
kind: workflow
scope: WF-04
status: draft
origin: generated
source_paths: [src/octop_browser/record/recorder.py, src/octop_browser/record/injected/recorder.js, src/octop_browser/record/privacy.py, src/octop_browser/record/store.py]
symbols: [RecordController.start_in_process, RecordSession, _install_on_client, _recorder_source, _on_binding_called, _append, redact_event, RecordingStore.create, append_event]
upstream: [business/index.md, architecture/record-daemon.md]
downstream: [business/wf-semantic-steps.md, integrations/downstream/record-daemon-ipc.md]
---

# WF-04 · 录制采集、注入脚本与隐私脱敏闭环

触发条件为 `record start`（守护模式）、`record start --duration>0`（进程内模式）或 MCP `browser_record_start`；目标是把真实页面上的点击、输入、导航等事件经注入 JS 采集、脱敏后落盘为 `events.jsonl`，停录时可选生成 `steps.json` 与 `draft.skill.md`。主链路跨进程：CLI/MCP → Unix socket 守护 → Chrome 页面 binding → 磁盘。

## 1. 符号级端到端执行调用树

```text
Trigger: record start -> ensure_daemon() -> send_request({"command":"start", ...}) (src/octop_browser/cli.py:577)
  └─ RecordDaemon.dispatch -> RecordController.start_in_process(profile, privacy, name) (src/octop_browser/record/recorder.py:350)
       ├─ [Step 1] p, ws_url = _attach(profile) -> launch_or_attach + get_page_ws_url (:331、:339)
       ├─ [Step 2] client = CDPClient(timeout=cfg.cdp_timeout); await client.connect(ws_url) (:357)
       ├─ [Step 3] info = client.send("Runtime.evaluate", {"expression":"JSON.stringify({url,title})", "returnByValue":True}) (:359)
       ├─ [Step 4] rec_id = "rec_" + %Y%m%d_%H%M%S_ + token_hex(3) (src/octop_browser/record/recorder.py:43)
       ├─ [Step 5] manifest = RecordingManifest(recordingId, createdAt, profile, target, privacy) (:368)
       ├─ [Step 6] store.create(manifest) -> 建目录 + manifest.json + 空 events.jsonl + screenshots/snapshots/replay-reports (src/octop_browser/record/store.py:45)
       ├─ [Step 7] RecordSession.start() (:83)
       │    ├─ 记录 _baseline_target_ids 排除既有标签 (:89)
       │    ├─ _install_on_client：Runtime.addBinding / Page.addScriptToEvaluateOnNewDocument / Runtime.evaluate (:165)
       │    ├─ 注册 Runtime.bindingCalled 与 Page.frameNavigated 监听 (:176)
       │    ├─ _attach_known_targets 为其它 page 建 CDPClient (:193)
       │    └─ asyncio.create_task(_poll_targets()) 每 0.5s 巡检 (:99、:230)
       └─ [Step 8] 返回 {"ok": True, "recordingId", "store", "startUrl", "name"} (:389)

页面事件（recorder.js）-> emit(kind, data) (src/octop_browser/record/injected/recorder.js:55)
  ├─ 统一帧 {nonce, schemaVersion:"1.0", event:{localSeq, kind, ts, targetId, page, ...data}} (:60)
  ├─ 绑定 globalThis[CONFIG.bindingName] -> Runtime.bindingCalled (:57)
  └─ RecordSession._on_binding_called (:256)
       ├─ [guard] name 不符 / nonce 不符 / 字节超限 / 限流失败 -> return (:257、:264、:273)
       ├─ 补 targetId 与 page.targetId (:278)
       └─ _append(event) (:240)
            ├─ 包裹 {seq, recordingId, receivedAt, ...event} (:242)
            ├─ redact_event(record, privacy) (src/octop_browser/record/privacy.py:61)
            ├─ store.append_event -> events.jsonl 追加一行并 flush (src/octop_browser/record/store.py:82)
            └─ stats.events += 1；end_url 更新；write_manifest 原子替换 (src/octop_browser/record/recorder.py:249)

stop(generate_steps=True) (src/octop_browser/record/recorder.py:101)
  ├─ status="stopped"、ended_at=_now()；write_manifest (:110)
  └─ [if generate_steps] SemanticProcessor.process() -> write_steps -> SkillGenerator.generate() -> write_skill(draft=True) (:117、:122、:123)
```

## 2. 分阶段业务规则与分支判定表

| 阶段 | 负责函数（`路径:行号`） | 精确布尔条件 / 阈值 | 命中分支行为 | 状态或数据副作用 |
|---|---|---|---|---|
| 录制 id 生成 | `_recording_id` (`src/octop_browser/record/recorder.py:43`) | `datetime.now().strftime("%Y%m%d_%H%M%S_") + secrets.token_hex(3)` | 同秒并发靠 3 字节随机区分 | `manifest.recording_id` |
| binding 名与 nonce | `RecordSession.__init__` (`:72`) | `__hbr_emit_{token_hex(8)}`、`token_urlsafe(32)` | 每会话唯一 | 防止跨录制串扰 |
| 事件字节上限 | `_on_binding_called` (`:264`) | `len(raw.encode("utf-8")) > max_event_bytes`（默认 65536） | 静默丢弃 | 不写盘 |
| 每秒限流 | `_rate_limit_ok` (`:232`) | 同一整数秒内 `_tick_events > 100` | 静默丢弃 | `_tick_events` 每秒清零 |
| nonce 校验 | `_on_binding_called` (`:273`) | `payload.get("nonce") != self.nonce` | 丢弃伪造事件 | 无 |
| 目标补齐 | `_on_binding_called` (`:278`) | `client_target_id` 非空且事件无 `targetId` | 写入 `event["targetId"]` 与 `page["targetId"]` | 多标签归属 |
| 输入防抖 | `onInput` (`src/octop_browser/record/injected/recorder.js:264`) | `clearTimeout(old)` 后 `setTimeout(..., 300)` | 300ms 内合并为一条 `input` | `WeakMap` |
| 滚动节流 | `onScroll` (`:289`) | `now - lastScrollAt < 500` | 直接 return | 每 500ms 至多一条 |
| URL query 脱敏 | `redact_url` (`src/octop_browser/record/privacy.py:27`) | `key.lower() in URL_KEYS`（11 键） | 值改 `"***"` | `page.url`、`url`、`urlBefore`、`urlAfter` |
| 输入值脱敏 | `redact_event` (`:74`) | `input_policy == "mask-all"` 或（`mask-sensitive` 且 `is_sensitive_target` 为真） | `value = "{{sensitive_value}}"`、`redacted=True` | 敏感词正则见 `:11` |

## 3. 事件 `kind` 全集与落盘字典

| `kind` | 载荷附加键 | 触发点（recorder.js 行号） |
|---|---|---|
| `recorder_installed` | `url` | `:348` |
| `page_opened` | `targetId`、`url`、`title`、`initial` | `src/octop_browser/record/recorder.py:210` |
| `click` / `dblclick` | `target`、`mouse`（仅 click） | `:251`、`:257` |
| `input` / `change` | `target`、`value`、`redacted` | `:260`、`:270` |
| `keydown` | `key`、`target`、`modifiers` | `:281` |
| `submit` | `target` | `:276` |
| `scroll` | `scroll`（`x`/`y`）、`target` | `:289` |
| `navigation` | `urlAfter`（`_on_frame_navigated`，`src/octop_browser/record/recorder.py:288`） | 帧导航 |
| `history.pushState` / `history.replaceState` / `popstate` / `hashchange` | `urlBefore`、`urlAfter` | `:304`、`:340` |

`describeElement` 产出 18 个目标描述键（`src/octop_browser/record/injected/recorder.js:201`），`readValue` 对敏感字段或超 2000 字符值返回 `{{sensitive_value}}` / `{{redacted_value}}` 并置 `redacted=True`（`:243`）。落盘的每行记录还带 `seq`、`recordingId`、`receivedAt`（`src/octop_browser/record/recorder.py:242`）。

## 4. 幂等、并发互斥与异常补偿回滚表

| 边界 / 故障场景 | 源码检测条件 | 保护 / 回滚 / 降级动作 |
|---|---|---|
| 已有活跃录制 | `dispatch` 中 `self.active is not None`（`src/octop_browser/record/daemon.py:44`） | 返回 `A recording is already active`，不覆盖在途会话 |
| `stop` 指定错误 id | `rec_id != active.manifest.recording_id`（`:68`） | 拒绝停录并回报活跃 id |
| 注入脚本重复执行 | `globalThis.__hbrRecorderInstalled.recordingId === CONFIG.recordingId`（`src/octop_browser/record/injected/recorder.js:5`） | 直接 return，避免双监听 |
| 守护进程不可达 | `OSError`/`TimeoutError`（`src/octop_browser/record/daemon.py:152`） | 返回 `Record daemon is not running...`，不裸抛 errno |
| 事件 JSON 非法 | `json.JSONDecodeError`（`src/octop_browser/record/recorder.py:269`） | 丢弃该条，不中断录制 |
| manifest 写失败 | `OSError`（`src/octop_browser/record/store.py:83`） | 仅 debug 日志，属 best-effort |

## 5. 共变耦合与修改清单（Agent Co-Change Playbook）

- **修改事件 `kind`**：`recorder.js` 各 emit 点、`SemanticProcessor._filter_events` 白名单（`src/octop_browser/record/semantic.py:353`）、`_build_steps` 分支（`:396`）与 [录制守护](../architecture/record-daemon.md) 的任务表联动。
- **修改脱敏键集**：`URL_KEYS` 与 `SENSITIVE_RE`（`src/octop_browser/record/privacy.py:11`、`:12`）必须和 `recorder.js` 的同名常量（`:13`、`:14`）逐字一致，否则前端已脱敏、后端又二次处理或漏脱敏。
- **修改落盘目录**：`RecordingStore.create` 的子目录清单（`src/octop_browser/record/store.py:49`）与 `recording_summary` 返回键（`:135`）同步；新增文件影响 [录制领域模型](../business/domain-models/recording-artifacts.md)。
- **必跑流程闭环回归**：`pytest tests/unit/test_record_replay_store_skill.py tests/unit/test_record_daemon_client.py tests/unit/test_record_replay_semantic.py`，端到端用 `scripts/record_replay_smoke.py:57`，命令见 [构建与单测映射](../operations/dev-and-test.md)。
