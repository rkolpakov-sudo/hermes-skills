# WS Death & Inbound Bypass (2026-08-21)

## The WS Death Problem

When gateway is killed via `taskkill /F` (SIGKILL, the only option since
`hermes gateway stop` is guard-blocked from inside the gateway process tree),
the Feishu SDK's WebSocket connection dies WITHOUT sending a WS CLOSE frame.
Feishu's server never learns the connection is dead and continues routing
inbound events to the stale endpoint. The channel goes silent for
**minutes-to-hours** until the server's CLOSE-WAIT timer expires.

**This is mentioned in the adapter code** (adapter.py ~1834):
> "Without this, Feishu's server never learns the connection is dead and
> continues routing messages to the stale endpoint — the channel goes silent
> until the server-side CLOSE-WAIT expires (minutes to hours)."

**Recovery without losing inbound**: The gateway reconnects a new WS on restart
(`Connected in websocket mode`), but Feishu's server doesn't send events to it
until it detects the old connection died. This is NOT a client-side issue —
the new WS is healthy, the server just won't route to it.

### Clean stop (the only way)
```cmd
# Run from a SEPARATE shell (cmd.exe), NOT from Hermes Desktop
cd C:\Users\Ruslan\.hermes\hermes-agent
hermes gateway stop
hermes gateway start
```

## Inbound Bypass: DB-write poll (FIX 6)

When WS is stalled, the bridge can poll Feishu IM API directly and write
user messages into `state.db` as user messages in the active session.
Messages written this way appear in the Desktop session history — the user
sees them and can respond.

### How it works

1. Poll `GET /open-apis/im/v1/messages?container_id_type=chat&container_id={HOME_CH}&sort_type=ByCreateTimeDesc&page_size=10` every 10s.
2. Filter: `msg_type='text'`, sender NOT starting with `cli_` (self-messages).
3. For each new message (dedup by `message_id` → `platform_message_id` column),
   write to state.db:
   ```python
   INSERT INTO messages (id, session_id, role, content, timestamp, platform_message_id)
   VALUES (?, ?, 'user', ?, ?, ?)
   ```
4. Update session count: `UPDATE sessions SET message_count = message_count+1 WHERE id=?`
5. The Desktop session will see the message in its message list.

### Limitations

- Does NOT trigger agent turn — only writes the user message to DB. The
  Desktop process holds the session lease and has custom provider config.
- Recalled/deleted Feishu messages appear as "This message was recalled" —
  always filter those out.
- Feishu IM API's `chat_type` returns `None` for DM messages — do NOT filter
  on it; use `container_id` instead.

### Interaction with outbound

```
Bot → (Feishu IM API poll) → inbound poll writes to state.db
  → Desktop sees new user msg → Desktop agent runs
  → outbound daemon polls state.db → new assistant msg → sends to Feishu → Bot
```

## FEISHU_DOMAIN — root cause of all delivery failures

```python
# adapter.py:4933
domain = FEISHU_DOMAIN if self._domain_name != "lark" else LARK_DOMAIN
```

When `FEISHU_DOMAIN="lark"`, SDK sends all REST calls to `open.larksuite.com`
which may be DNS-blocked → empty HTTP response → `JSONDecodeError`.

**The trap**: WS connects fine (uses a different endpoint — works regardless
of FEISHU_DOMAIN). You see `Connected in websocket mode (lark)` and assume
everything is OK. But outbound sends all fail silently (3 retries caught).

**The fix**: Set `FEISHU_DOMAIN=feishu` — both domains authenticate the same
app registration. Verify by gateway log: `Connected in websocket mode (feishu)`.