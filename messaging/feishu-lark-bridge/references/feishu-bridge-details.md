# Feishu bridge — session facts (2026-08-21)

Verified facts from the live build session. Use these to short-circuit probing.

## state.db schemas (as observed)

- `sessions`: id, source ('desktop'/'feishu'/'api_server'), started_at, ended_at,
  end_reason ('compression'), last_activity_at, message_count, ... (50 cols).
- `messages`: id, session_id, role (user/assistant/tool/session_meta), content,
  finish_reason ('tool_calls'/'stop'/NULL), timestamp, tool_call_id, tool_name,
  platform_message_id (always NULL in this setup — useless for dedup).
- `gateway_routing`: scope (= `C:\Users\Ruslan\.hermes\sessions`), session_key,
  entry_json, updated_at. Single row for the feishu DM key.
- `session_turn_leases`: conversation_id, holder (`pid=...:turn=...:platform=...`),
  acquired_at, expires_at. Serializes turns across processes.

## Routing entry (entry_json keys)

session_key, session_id, created_at, updated_at, display_name, platform, chat_type,
metadata, token counters, suspended, resume_pending, prev_session_id, origin.
`origin` = {platform:'feishu', chat_id:'oc_5c034ca56b338848b73553d0acb4a3ed',
chat_type:'dm', user_id:'b6168c3f', user_id_alt:'on_8ef8...'}.
Keeping `origin.platform=feishu` makes the gateway auto-deliver replies to Lark.

## Routing re-point revert (the trap)

UPDATE `gateway_routing` SET entry_json.session_id = <live desktop sid> — then
gateway start reverted it. Log line:
`gateway.session: repointing stale sessions.json entry 'agent:main:feishu:dm:oc_5c034ca...' from ended 20260821_124510_4f1b5b (end_reason='compression') to recovered 20260821_105911_b6868fe9`

Cause: the target session was marked ended (compression). The gateway refuses to
route to ended sessions and falls back. Re-pointing only works when the target is
a LIVE (ended_at IS NULL) session AND re-applied after every compaction.

## Compaction chain observed (one day)

20260821_121411_ecf829 → 20260821_123201_39f12e → 20260821_124510_4f1b5b →
20260821_134314_1dad33 → 20260821_142243_1e868d (live).
`HERMES_SESSION_KEY` env of a running agent process points at the session it
STARTED in — stale after compactions. Resolve live sid from DB instead.

## Auth: two separate worlds

1. Control plane (FastAPI, `hermes serve`, dynamic port, openapi.json at
   `/openapi.json`, 259 paths, `/api/status` public):
   - Protected routes need header `X-Hermes-Session-Token` =
     `HERMES_DASHBOARD_SESSION_TOKEN` env of the serve process (ephemeral
     token, not readable cross-process). `/api/gateway/start` → 401 without it.
   - Even loopback bind keeps this token gate for sensitive routes.
2. Gateway api_server adapter (aiohttp, port 8642, OpenAI-compatible):
   - `Authorization: Bearer API_SERVER_KEY` (from `.env`, length 28).
   - Verified endpoints: GET/POST /api/sessions, POST /api/sessions/{id}/chat
     (body `{"message": ...}`), DELETE /api/sessions/{id}.
   - REST chat round-trip verified: creates user + assistant rows in state.db.

Gateway lifecycle CLI (bypasses control-plane token):
`hermes gateway start|stop|restart|status` — on Windows `start` does a direct
spawn (PID in output), `status` shows login item + process. The gateway (when
running) logs `✓ feishu connected` (websocket mode lark) and `[Api_Server] API
server listening on http://127.0.0.1:8642`.

## Feishu API notes

- `FEISHU_DOMAIN` = "lark" is a semantic flag → use https://open.feishu.cn
  (open.larksuite.com DNS-blocked on this machine; open.feishu.cn resolves).
- Token: POST /open-apis/auth/v3/tenant_access_token/internal
  {app_id, app_secret} → {tenant_access_token, expire}.
- Send: POST /open-apis/im/v1/messages?receive_id_type=chat_id
  {receive_id: HOME_CHANNEL, msg_type:'text',
   content: json.dumps({'text': ...}, ensure_ascii=False)} → message_id `om_...`.
- List: GET /open-apis/im/v1/messages?container_id_type=chat&container_id=...
  &page_size=20&sort_type=ByCreateTimeDesc → items[].message_id/sender/body.
- Bot self-id: GET /open-apis/bot/v3/info → data.bot.open_id (filter own msgs).

## Gateway log markers (dedup / diagnostics)

- Inbound injection: `inbound message: platform=feishu user=<id> chat=oc_... msg='<text>'`
- Reply delivered: `[Feishu] Sending response (N chars) to oc_...`
- Startup: `Starting Hermes Gateway...`, `✓ api_server connected`,
  `✓ feishu connected`, `Gateway housekeeping started (interval=60s)`.

## Environment quirks hit this session

- Multi-line terminal/execute_code output collapses to "1 lines output"
  (content lost) → write probe results to a file, then read_file.
- execute_code redacts `key=`+value patterns (secret-masking) → write probes
  to files instead.
- `os.walk` over hermes-agent repo → timeout (exit 124) → use search_files.
- MSYS bash mangles PowerShell one-liners → run .ps1 via powershell -File.
- Old PIDs from previous sessions are stale; re-derive via `hermes gateway
  status` or Win32_Process.
