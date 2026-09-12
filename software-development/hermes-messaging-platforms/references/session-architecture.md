# Messaging Platform Session Architecture

Source: `gateway/session.py` (2901 lines), `gateway/run.py`, analyzed 2026-07-24.

## Session Key Construction

`build_session_key()` in `gateway/session.py` is the single source of truth:

```
Format: agent:{profile}:{platform}:{chat_type}:{chat_id}[:{thread_id}]
        agent:{profile}:{platform}:{chat_type}:{chat_id}[:{thread_id}][:{user_id}]  (groups)
```

- Namespace prefix: `agent:main` for default profile, `agent:{name}` for named profiles (`_session_key_namespace()`)
- DM isolation: each private chat gets its own session keyed on `chat_id`
- Group/channel: per-chat by default; optional `group_sessions_per_user` splits per participant within a group
- Threads: shared across all participants by default (`thread_sessions_per_user=False`)

## Session Store

`SessionStore` class (line 1033) manages lifecycle:
- `_entries` dict keyed by session_key, backed by SQLite (`hermes_state.SessionDB`)
- `get_or_create_session()` uses single-flight pattern — concurrent calls for same key share one result
- Auto-recovery: ended sessions with matching routing keys are reopened unless force_new
- Reset policy: configurable per-platform (stale detection, resume_pending expiry, suspended state)

## Why Sessions Cannot Be Merged

1. **Prompt caching** — long-lived conversations reuse cached prefix every turn; mutating past context invalidates the cache and multiplies API cost
2. **Strict role alternation** — two same-role messages in a row breaks the model contract; merging streams from Desktop + Lark risks interleaving violations
3. **System prompt stability** — must be byte-stable for life of conversation; different platforms may inject different context

## Channel Directory

`gateway/channel_directory.py` builds from live adapters + session history:
- Discord/Slack: enumerated via SDK APIs
- Other platforms (Feishu, Telegram, etc.): discovered from `state.db` gateway session rows (`_build_from_sessions_db`)
- Persisted to `~/.hermes/channel_directory.json`, rebuilt every 5 minutes

## Profile Routing

`gateway/profile_routing.py`: hierarchical matching by platform → guild_id → chat_id → thread_id. Each route points to a different profile (model, tools, memory), but sessions remain isolated within profiles. Config: `config.yaml` → `gateway.profile_routes`.
