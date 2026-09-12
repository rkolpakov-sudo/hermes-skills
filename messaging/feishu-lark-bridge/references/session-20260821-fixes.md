# 2026-08-21 session: delivery root cause + daemon hardening (live-verified)

## THE root cause of "бот упал / gateway can't deliver" — FEISHU_DOMAIN

Symptom chain in gateway.log, repeating for hours:
`JSONDecodeError: Expecting value: line 1 column 1 (char 0)` →
`[Feishu] Send attempt 1/3 failed for chat ... retrying in 1s` →
`[Feishu] Failed to edit message ...` — while the bridge daemon (direct
urllib to open.feishu.cn) kept delivering fine with the SAME credentials.

Root cause: `FEISHU_DOMAIN="lark"` in `.env`. The lark_oapi SDK derives its
REST base URL from this flag:
`plugins/platforms/feishu/adapter.py:4933`
`domain = FEISHU_DOMAIN if self._domain_name != "lark" else LARK_DOMAIN`.
`LARK_DOMAIN` = https://open.larksuite.com, whose DNS is blocked on this
machine → HTTP returns an empty/non-JSON body → `JSON.unmarshal` throws
`Expecting value: line 1 column 1 (char 0)`. WebSocket inbound still
connected (`Connected in websocket mode (lark)`) — only the REST send/edit
path was dead. That inbound-works/outbound-broken asymmetry + bridge-urllib
working is the diagnostic fingerprint.

Fix (verified): set `FEISHU_DOMAIN=feishu` in `.env` (backup first:
`.env.bak_<ts>`), restart gateway. gateway.log then shows
`Connected in websocket mode (feishu)`. `FEISHU_DOMAIN` is a semantic flag
('feishu' vs 'lark' vendor), NOT a hostname — but it must match the vendor
the app is registered with; this app works on open.feishu.cn.

## Truncated messages in bot chat — send limit

Long answers (e.g. 5371-char analysis reports) arrived CUT OFF mid-word
("...b68") because the daemon sent `text[:2000]`. Feishu text content allows
~150KB; raise the cap (30000 used). Test with a >2000-char payload
(`--test-outbound`) and confirm the full text arrives.

## Daemon fixes (all in bridge_daemon.py, live-verified)

1. **active_sid() source filter** (was: plain last-message query):
   `SELECT m.session_id FROM messages m JOIN sessions s ON s.id=m.session_id
   WHERE s.ended_at IS NULL AND s.source IN ('desktop','feishu')
   ORDER BY m.id DESC LIMIT 1`.
   Without the JOIN+filter, live `api_server`/`unknown` sessions (cron, REST
   tests, `/api/sessions/{id}/chat`) hijack routing — messages from the bot
   go to the wrong session. (This CORRECTS the earlier advice in
   handoff-mechanism.md that a bare `ORDER BY id DESC LIMIT 1` "survives
   everything" — it does not.)
2. **Stale-pending mine**: `request_handoff` writes
   `handoff_state='pending', handoff_platform='feishu',
   handoff_error='__silent__'`; if the gateway is DEAD at that moment,
   `wait_handoff` times out (~25s) and the pending row survives → a later
   gateway start executes it against a stale session. Fix: on timeout run
   `UPDATE sessions SET handoff_state=NULL, handoff_platform=NULL,
   handoff_error=NULL WHERE id=? AND handoff_state IN ('pending','running')`;
   at daemon startup clear all leftover `handoff_state='pending' AND
   handoff_error='__silent__'` rows.
3. **Duplicate live sessions sharing one feishu session_key** (observed FIVE
   live at once): after a successful re-bind, retire the others:
   `UPDATE sessions SET ended_at=?, end_reason='bridge_repurposed'
   WHERE session_key=? AND id<>? AND ended_at IS NULL AND handoff_state IS
   NULL`. Without this, gateway restart-resume (`_schedule_resume_pending_sessions`)
   can resurrect a stale session over the active one. Startup also retires
   dups for the current active session.
4. **Send cap 2000 → 30000** (see truncation above).

## Dedup bug found (NOT yet fixed at session end)

Daemon dedup searches `logs/gateway.log` for the preceding user message as
`platform=feishu.*msg=<text>` — but the log format is `msg='<text>'` WITH a
quote, so the regex never matches → dedup is silently dead. While gateway
delivery was broken (domain bug) this was harmless (bridge was the only
deliverer); once gateway delivers successfully, expect DUPLICATES. Fix: make
the quote optional (`msg=['\"]?`). Also: `messages.platform_message_id` is
NULL for every row (0/82 observed) — the gateway does NOT populate it, so it
cannot be used as a dedup signal.

## Outage triage checklist (bot fully silent)

- `netstat -ano | grep 8642` empty + gateway.log frozen (no shutdown line) =
  gateway died uncleanly (SIGKILL/OOM).
- bridge.log may still be ALIVE writing (old daemon code) — check daemon
  version against the handoff-based script.
- Recovery: kill stale pythonw → `hermes gateway start` (loads patched
  code) → start handoff-based daemon → verify routing → active session,
  handoff rows all NULL, `--test-sync` noop.
- `platform_message_id` can't confirm delivery; use bridge.log `send ... OK
  om_...` lines instead.
