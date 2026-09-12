# Unified Sessions: Feishu DM ↔ Desktop TUI

Session: 2026-07-25 (initial), 2026-07-27 (auto-unification added). Patched files: `gateway/session.py`, `gateway/run.py`.

## Problem

Desktop and Gateway run as separate processes with different AIAgent instances. By default, each has its own session in state.db — Feishu DM uses `session_key=agent:...` while Desktop stores `session_key=None`. Messages from each platform never share conversation history or agent memory.

User requirement: "Я хочу, чтобы бот работал в той же сессии, что и desktop!!!"

## Architecture Discovery

Key findings:
- **Desktop**: Uses `PTY_REGISTRY` in `conversation_loop.py`, connects to api_server at localhost:8642. Sessions stored with `source='desktop'`, `session_key=None`.
- **Gateway (Feishu)**: Separate process, uses SessionStore + AIAgent cache. Sessions use deterministic keys via `build_session_key()`.
- **Shared state**: Both processes read/write the same SQLite file (`state.db`). Agent context (`_session_messages`) is loaded from DB per turn — NOT held purely in memory. This means unifying session_key across both platforms DOES share conversation history.

## Implementation (Variant 1)

### Step 1: `gateway/config.yaml`
Add empty redirect config block:
```yaml
# Session redirects for cross-platform session sharing
session_redirects: []
```

### Step 2: `gateway/session.py::SessionStore._generate_session_key()`
After generating the key, unify with active Desktop session:
```python
def _generate_session_key(self, source):
    # ... existing redirect check + build_session_key ...
    key = build_session_key(source, ...)

    if self._should_unify_desktop(source) and source.platform.value == "feishu" and source.chat_type == "dm":
        self._unify_desktop_session(key, source)

    return key

def _should_unify_desktop(self, source):
    return getattr(self.config, "unify_desktop_feishu_dm", False)

def _unify_desktop_session(self, feishu_key, source):
    # Find active Desktop session (source='desktop', end_reason IS NULL)
    # Write feishu_key into its session_key column
    cur.execute("UPDATE sessions SET session_key=? WHERE id=?", (feishu_key, desktop_id))
```

### Step 3: `gateway/run.py::GatewayRunner.__init__`
After SessionStore wireup:
```python
self._register_desktop_session_redirect()

def _register_desktop_session_redirect(self):
    self.config.unify_desktop_feishu_dm = True
```

## Auto-Unification for Desktop Restarts

When Desktop restarts, it creates a new session row with `session_key=NULL`. The on-first-contact unification won't fire until another Feishu message arrives. To handle this gap:

**Step 4:** Add `_auto_unify_desktop_sessions()` to `gateway/run.py` (before `_start_gateway_housekeeping`) and call it from the housekeeping loop every ~10 ticks (~10 minutes):

```python
def _auto_unify_desktop_sessions() -> None:
    """Housekeeping: find Desktop sessions with key=None and unify them."""
    state_db = Path(hc.get_state_dir()) / "state.db"
    if not state_db.exists():
        return
    conn = sqlite3.connect(str(state_db), timeout=5)
    cur = conn.cursor()
    
    # Find active Desktop sessions with NULL key
    rows = cur.execute(
        "SELECT id FROM sessions WHERE source='desktop' AND session_key IS NULL "
        "AND end_reason IS NULL ORDER BY started_at DESC LIMIT 3"
    ).fetchall()
    if not rows:
        return
    
    # Get Feishu DM key from most recent feishu dm session (even if ended)
    feishu_row = cur.execute(
        "SELECT session_key FROM sessions WHERE source='feishu' AND chat_type='dm' "
        "AND end_reason IS NULL ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    
    # Fallback: use key from any completed feishu dm session with compression
    if feishu_row is None:
        feishu_row = cur.execute(
            "SELECT session_key FROM sessions WHERE source='feishu' AND chat_type='dm' "
            "AND end_reason='compression' ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
    
    if feishu_row is None:
        return
    
    shared_key = str(feishu_row[0])
    for (desktop_id,) in rows:
        cur.execute("UPDATE sessions SET session_key=? WHERE id=?", (shared_key, desktop_id))
    conn.commit()
```

In the housekeeping loop (`_start_gateway_housekeeping`), add before the Curator tick:
```python
if tick_count % 10 == 0:  # Every ~10 minutes
    try:
        _auto_unify_desktop_sessions()
    except Exception as e:
        logger.debug("Desktop auto-unification error: %s", e)
```

## How to Verify Unification

After sending a Feishu message, check state.db:
```sql
SELECT id, source, session_key FROM sessions 
WHERE source IN ('desktop','feishu') AND end_reason IS NULL;
-- Both should share the same session_key value
```

Check gateway logs for: `Desktop↔Feishu unified`

## Pitfalls

- **Race conditions**: If Desktop and Feishu send messages simultaneously, interleaving could break role alternation in the conversation stream. For single-user setups where the user doesn't type on both platforms at once, this is acceptable.
- **OC-ID dynamism**: The user's Feishu OC-ID (`oc_5c034ca...`) comes from webhook events — cannot be hardcoded. The dynamic approach (unifying on first contact) avoids this problem entirely.
- **Desktop session_key=None**: Desktop sessions store `session_key=NULL` in state.db by design. Writing a key into this column is the mechanism for unification. Verify with: `SELECT id, source, session_key FROM sessions WHERE source='desktop' AND end_reason IS NULL`.
- **Flag propagation**: The `unify_desktop_feishu_dm` flag must live on `self.config` (not `self._gateway_runner`) because SessionStore only has access to config, not the GatewayRunner instance.
- **Feishu DM session compression**: Feishu DM sessions get compressed (`end_reason=compression`). When looking for a shared key in auto-unification, check BOTH active (`end_reason IS NULL`) AND completed feishu dm sessions with `end_reason='compression'`.
- **Gateway logs on Windows direct spawn**: New Gateway processes spawned via `hermes gateway restart` (direct spawn mode) write to `gateway-stdio.log`, NOT `gateway.log`. Check both: `tail ~/.hermes/logs/gateway-stdio.log | grep -i "feishu.*connect\|housekeep"`.