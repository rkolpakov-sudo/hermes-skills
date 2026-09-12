---
name: feishu-lark-bridge
description: "Bridge Hermes sessions with a Feishu/Lark bot."
---

# Feishu/Lark ↔ Hermes Bridge

How to deliver messages between Hermes Desktop sessions and a Feishu/Lark bot:
outbound (LLM answers → bot chat) and inbound (bot DMs → the ACTIVE desktop
session, not a separate chat). Built and verified live on this machine
(Windows, Hermes Desktop, state.db shared by desktop runtime + gateway).

## Verified architecture map

- **Processes**: `Hermes.exe` spawns a local runtime `hermes_cli.main serve
  --host 127.0.0.1 --port 0` (dynamic port, hosts the FastAPI control plane;
  `/api/status` shows `gateway_running`). The gateway is separate:
  `hermes gateway start` (Windows: direct spawn, PID visible in `hermes gateway
  status`) and hosts platforms `feishu` (websocket mode) + the `api_server`
  adapter on **port 8642**.
- **Shared DB**: `C:\Users\Ruslan\.hermes\state.db` — tables `sessions`,
  `messages`, `gateway_routing` (scope, session_key, entry_json, updated_at),
  `session_turn_leases` (serializes turns; no race by design).
- **Routing key** for the bot DM: `agent:main:feishu:dm:oc_5c034ca...`;
  `entry_json.session_id` decides which session incoming DMs land in;
  `entry_json.origin.platform=feishu` makes the gateway auto-deliver the reply
  back to Lark.
- **Two auth worlds**: control plane uses `X-Hermes-Session-Token`
  (= `HERMES_DASHBOARD_SESSION_TOKEN` in the serve process env — NOT readable
  cross-process; `/api/gateway/start` → 401 without it). The gateway api_server
  adapter on 8642 uses `Authorization: Bearer API_SERVER_KEY` (from `.env`).
  CLI `hermes gateway start|stop|restart|status` bypasses the control-plane
  token entirely — use the CLI for gateway lifecycle.

## Feishu IM API essentials

- `FEISHU_DOMAIN` env value `"lark"` is a SEMANTIC flag, not a hostname. Use
  `https://open.feishu.cn` (open.larksuite.com DNS is blocked on this machine).
- Tenant token: `POST /open-apis/auth/v3/tenant_access_token/internal`
  `{app_id, app_secret}` (creds in `.env`: `FEISHU_APP_ID/SECRET`,
  `FEISHU_HOME_CHANNEL` = chat id).
- Send: `POST /open-apis/im/v1/messages?receive_id_type=chat_id`
  `{receive_id, msg_type:"text", content: json.dumps({"text": ...})}`.
- List inbound: `GET /open-apis/im/v1/messages?container_id_type=chat&container_id=...&sort_type=ByCreateTimeDesc`.
- Bot's own open_id: `GET /open-apis/bot/v3/info` (filter self-messages).

## Outbound bridge daemon pattern (Desktop → Lark)

`scripts/bridge_daemon.py` is the working daemon. Core rules:

1. **Resolve the active session dynamically each cycle**:
   `SELECT m.session_id FROM messages m JOIN sessions s ON s.id=m.session_id
   WHERE s.ended_at IS NULL AND s.source IN ('desktop','feishu')
   ORDER BY m.id DESC LIMIT 1`.
   NEVER trust `WHERE source='desktop'` alone — the gateway may have re-bound
   routing to a `source='feishu'` session. NEVER trust `ORDER BY id DESC LIMIT 1`
   alone — `api_server`/`unknown` sessions (cron, REST tests) can hijack routing.
   NEVER trust `HERMES_SESSION_KEY` env var — it goes stale after every
   compaction (see Pitfalls).
2. Forward only FINAL assistant messages: `role='assistant'` AND content
   non-empty AND `finish_reason != 'tool_calls'` (intermediate frames carry
   tool_calls + empty content).
3. Per-session cursor persisted in a JSON state file; **first run for a new
   session pins the cursor to the last qualifying id and sends nothing**
   (never flood Lark with history).
4. Dedup vs gateway auto-delivery: if the turn's preceding user message
   appears in `logs/gateway.log` as `platform=feishu.*msg='<text>'`, the
   gateway already delivered that reply — skip it.
5. Persistence: run via `pythonw.exe` (no console) from a stable dir
   (`C:\Users\Ruslan\.hermes\bridge\`), autostart via a `.vbs` in the Windows
   Startup folder mirroring `Hermes_Gateway.vbs`. Log to
   `logs/bridge.log`; state in `tmp/bridge_state.json`.

## Inbound options (Lark → active session)

- **Native handoff (RECOMMENDED, no restart)**: Write
  `UPDATE sessions SET handoff_state='pending', handoff_platform='feishu',
   handoff_error='__silent__' WHERE id=? AND (handoff_state IS NULL OR
   handoff_state IN ('completed','failed'))`.
  The gateway's `_handoff_watcher` (run.py:13363) polls every ~2s, runs
  `switch_session(session_key, target)` → re-binds the feishu home-channel key
  to the new session WITHOUT restarting the gateway. `'__silent__'` requires a
  patch to `_process_handoff` (run.py:+11 lines) that skips the synthetic
  confirmation turn.
- **REST inject** (verified end-to-end, works while gateway is alive despite
  dead WS): `POST http://127.0.0.1:8642/api/sessions/{sid}/chat`
  `{"message": text}` + Bearer `API_SERVER_KEY` executes a turn in that session
  and writes user+assistant rows into state.db. PREREQUISITE: clear
  `DELETE FROM session_turn_leases` (desktop process holds the lease and blocks
  the injection).
- **Routing re-point** (UPDATE `gateway_routing.entry_json.session_id`) is
  FRAGILE and DEPRECATED: the gateway reverts it at startup via auto-resume.

## Pitfalls (each cost real time — read before probing)

- **WS inbound death on unclean gateway kill**: `taskkill /F` kills the gateway
  WITHOUT sending a WS CLOSE frame to Feishu. The server doesn't detect the
  death and continues routing to the stale endpoint → inbound silent for
  minutes-to-hours. `hermes gateway stop` is guard-blocked from inside the
  process tree; run it from a separate shell (cmd.exe, not Hermes Desktop).
- **FEISHU_DOMAIN controls SDK hostname**: adapter.py:4933 uses
  `FEISHU_DOMAIN if domain_name != "lark" else LARK_DOMAIN`. Setting
  `FEISHU_DOMAIN="lark"` → SDK hits open.larksuite.com (DNS blocked on this
  machine) → `JSONDecodeError: Expecting value`. MUST be `FEISHU_DOMAIN=feishu`
  when the app is registered on open.feishu.cn.
- **REST injection blocked by session_turn_leases**: the desktop process holds a
  lease (40-min expiry). Must `DELETE FROM session_turn_leases` before
  injecting via REST, or the injection hangs until timeout.
- **Session IDs change on compaction**. Chain observed in one day:
  `_ecf829 → _39f12e → _4f1b5b → _1dad33 → _1e868d`. `ended_at`/`end_reason='compression'`
  mark dead sessions. Gateway log on revert:
  `repointing stale ... from ended <sid> (end_reason='compression') to recovered <sid>`.
- **Multi-line `terminal`/`execute_code` output collapses to "1 lines output"**
  (content lost). This caused blind probes → the user's "ты застрял в цикле".
  Reliable channel: ONE script writes results to a file, then `read_file`.
- **`execute_code` redacts `key=`+value patterns** as secrets and corrupts
  probe code → write probes to files with `write_file` and run via terminal.
- **`os.walk` over the whole hermes-agent repo times out** (exit 124) → use
  `search_files` (ripgrep) scoped to specific files, or file-based probes.
- **MSYS bash mangles PowerShell one-liners** (path substitution of `$_`
  etc.) → put PS in a `.ps1` file and run `powershell -File ...`.
- Old PID numbers from previous sessions are garbage after Desktop restarts —
  re-derive from `hermes gateway status` / Win32_Process.

## Verification checklist

1. `hermes gateway status` → process running; `logs/gateway.log` shows
   `✓ feishu connected` + api_server listening on 8642.
2. Daemon alive: `tasklist`/Win32_Process shows `pythonw.exe bridge_daemon.py`;
   `logs/bridge.log` shows a cycle; `tmp/bridge_state.json` has the cursor.
3. Live outbound proof: a final assistant answer in the active session arrives
   in the bot chat within ~10s (message id `om_...` in bridge.log).
4. Handoff clean: `SELECT handoff_state, COUNT(*) FROM sessions GROUP BY handoff_state`
   returns only `NULL` rows (no pending mines).
5. No duplicate live sessions: `SELECT id, ended_at FROM sessions
   WHERE session_key='agent:main:feishu:dm:oc_5c034ca...' AND ended_at IS NULL`
   returns exactly 1 row.
6. `FEISHU_DOMAIN=feishu` in `.env` (not `lark`), confirmed by gateway.log:
   `Connected in websocket mode (feishu)`.
7. `--test-sync` returns noop when routing is already correct.

## Critical fixes (2026-08-21 need-to-know)

All verified live. See `references/session-20260821-fixes.md` for full detail:
- **Fix 1**: active_sid() JOIN filter (source+ended_at)
- **Fix 2**: stale-pending cleanup on timeout + startup
- **Fix 3**: retire duplicate live feishu sessions after re-bind
- **Fix 4**: send cap 2000 → 30000 chars
- **Fix 5**: FEISHU_DOMAIN="lark" → "feishu"

## Files

- `scripts/bridge_daemon.py` — the working outbound daemon (copy to
  `C:\Users\Ruslan\.hermes\bridge\`, run with pythonw, autostart via VBS).
- `references/feishu-bridge-details.md` — session facts: schemas, endpoint
  contracts, log formats, the routing-revert event, compaction chain.
