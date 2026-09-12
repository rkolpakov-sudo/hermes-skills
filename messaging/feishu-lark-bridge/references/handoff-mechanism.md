# Native gateway handoff — the correct inbound re-routing mechanism

Discovered 2026-08-21 while converting the bridge from manual
`gateway_routing` UPDATE + gateway kill/restart to the gateway's own
mechanism. This is the OFFICIAL way to re-bind a platform channel's session
key to a different session — no restart, no race with auto-resume.

## How it works

- The gateway spawns a supervised `_handoff_watcher` (gateway/run.py:13363)
  that polls `state.db` every ~2s for sessions with
  `handoff_state='pending'`.
- For each pending row it:
  1. `claim_handoff(session_id)` — atomic pending→running (one tick wins).
  2. `_process_handoff(row)` (run.py:13413):
     - resolves `Platform(row.handoff_platform)`; adapter must be live
       (`resolve_delivery_transport` — relay-aware);
     - requires a configured **home channel**
       (`config.get_home_channel(platform)`, from `FEISHU_HOME_CHANNEL` for
       feishu) — raises `no home channel configured` otherwise;
     - builds the destination `SessionSource` (chat_type='dm' fallback,
       user_id='system:handoff' when no thread created; Discord keys on
       thread id, others on home chat_id);
     - `session_key = build_session_key(dest_source, ...)`
       (gateway/session.py:1090; DM key = `agent:main:<platform>:dm:<chat_id>`);
     - `get_or_create_session(dest_source)` then
       `switch_session(session_key, target_session_id)`
       (gateway/session.py:3471): ends the old session in SQLite
       (promote_to_session_reset, reason 'session_switch'), reopens the
       target, updates the in-memory `_entries` cache + persists.
  3. `complete_handoff(session_id)` (or `fail_handoff(session_id, err)` →
     `handoff_error` column).
- CLI side: `/handoff <platform>` sets the row pending and poll-blocks on the
  terminal state.

## Silent mode (bridge use)

`_process_handoff` normally forges a SYNTHETIC confirmation turn
(`internal=True` MessageEvent: "Session was just handed off from CLI ...")
that makes the LLM reply on the platform. For a bridge that does its own
outbound delivery this is unwanted noise.

Patch added to gateway/run.py right after `_release_running_agent_state`:

```python
if str(row.get("handoff_error") or "") == "__silent__":
    logger.info("Handoff (silent): re-bound session_key=%s -> session %s; "
                "skipping synthetic turn", session_key, cli_session_id)
    return
```

Marker convention: bridge writes `handoff_error='__silent__'` together with
`handoff_state='pending'`. NOTE: after patching gateway code you MUST restart
the gateway (`hermes gateway start` after killing the old PID via a file
script — `hermes gateway restart` is guard-blocked from inside the tree).

## Bridge-side contract (verified live)

```sql
UPDATE sessions SET handoff_state='pending',
       handoff_platform='feishu', handoff_error='__silent__'
WHERE id=? AND (handoff_state IS NULL OR handoff_state IN ('completed','failed'));
```

- Rowcount 0 = a handoff already in flight or the row is in a terminal-ish
  state — do NOT re-request, poll instead.
- `sessions` columns confirmed: `handoff_state`, `handoff_platform`,
  `handoff_error` all exist (nullable TEXT). There is NO `platform` column
  and NO `updated_at` column in `sessions` — routing metadata (session_key,
  platform, updated_at) lives in `gateway_routing.entry_json`.
- `messages` has `timestamp` (float), NOT `created_at`/`updated_at` — the
  schema-inspection probe crashed on this; always `PRAGMA table_info` first.
- DB helper methods live in hermes_state.py: `list_pending_handoffs`
  (~13050), `claim_handoff`, `complete_handoff`, `fail_handoff`.

## Verification

`wait_handoff(sid, timeout=25)`: poll `handoff_state` until 'completed' (OK)
or 'failed' (read `handoff_error`). Then confirm `gateway_routing` entry
`entry_json.session_id == target`. In gateway.log you should see
`Handoff (silent): re-bound session_key=... -> session <sid>; skipping
synthetic turn`.

## Why not the old way

Manual `UPDATE gateway_routing.entry_json.session_id` + gateway restart was
fragile: (a) `_schedule_resume_pending_sessions` (run.py ~12000) re-points
routing to recovered sessions at startup and reverts the change; (b) the
kill/restart sync crashed the bot once — old bridge killed the gateway
mid-turn (ROUTING STALE → kill), gateway then died uncleanly (SIGKILL/OOM,
no shutdown log line), port 8642 vanished, bot went fully silent until a
manual restart. The handoff watcher has none of these problems: it is
in-process, atomic (claim), and does not restart anything.

## Bot-silent outage triage (what actually happened)

Symptoms: bridge.log stops writing, gateway.log frozen (no shutdown line),
`netstat -ano | grep 8642` empty, `tasklist` shows old gateway PIDs DEAD but
`pythonw.exe` bridge still ALIVE (running old code, silent).

Root cause chain: old daemon's ROUTING STALE sync killed gateway mid-turn →
new gateway started → died uncleanly ~6 min later (SIGKILL/OOM) → bot dead.
Fix: kill stale pythonw, restart gateway (loads patched code), restart new
handoff-based daemon, verify routing → active session, handoff states all
NULL (clean), `--test-sync` returns noop (routing already correct).

Active-session resolution that survives everything:
`SELECT m.session_id FROM messages m JOIN sessions s ON s.id=m.session_id
WHERE s.ended_at IS NULL AND s.source IN ('desktop','feishu')
ORDER BY m.id DESC LIMIT 1` — NOT bare `ORDER BY id DESC LIMIT 1`
(api_server/unknown sessions can hijack routing without the filter) and NOT
`WHERE source='desktop'` (the active session can be source='feishu', created by
the gateway when routing was re-pointed).
