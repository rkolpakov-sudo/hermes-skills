# Official cross-session mechanisms + session-switch research (2026-08-21 research pass)

Web research + gateway source reading. Hermes has NO native "one conversation on
two surfaces" — the Desktop chat and the bot DM are separate sessions BY DESIGN
(`session_key = build_session_key(platform, chat_id, user_id)`). The bridge is
custom plumbing; these are the official primitives it should use where possible.

## switch_session — the OFFICIAL re-bind primitive (replaces manual re-point)

`gateway/session.py:3471`:

```python
def switch_session(self, session_key: str, target_session_id: str) -> Optional[SessionEntry]:
```

- Re-binds a channel's session_key to an EXISTING session id (ends the current
  session like reset, re-uses target id, reopens it if previously ended).
- Used by `/resume` and by CLI→gateway `/handoff`.
- What my manual `UPDATE gateway_routing SET entry_json.session_id=...` was
  trying to do — but done in-memory with correct end/reopen semantics.
- No REST endpoint exposes it (checked web_server.py — only the CLI `/handoff`
  path and the internal watcher below).

## _handoff_watcher — the no-restart auto-rebind loop

`gateway/run.py:13363` — background task polling state.db **every 2s** for
sessions with `handoff_state='pending'` + `handoff_platform='feishu'`:

1. Claims the row (pending → running, atomic).
2. Resolves the destination platform's home channel.
3. Re-binds the session_key to the CLI session_id via `switch_session`.
4. Forges a synthetic internal MessageEvent so the agent replies on the platform.
5. Marks completed/failed.

**Implication for the bridge**: instead of manual re-point + gateway restart,
write `handoff_state='pending', handoff_platform='feishu'` (and `handoff_error`)
columns on the target `sessions` row — the gateway rebinds itself in ~2s with
NO restart and NO auto-resume revert. Columns already exist in `sessions`
schema (seen in PRAGMA output). NOT yet live-tested as the bridge mechanism —
validate before replacing the restart path.

## /handoff CLI command (same mechanism, human-driven)

`/handoff <platform>` inside a CLI session transfers the LIVE session to a
messaging platform's home channel — same session id, full transcript. Refused
mid-turn. Requires gateway running + home channel configured (`/sethome`).
Commit: NousResearch/hermes-agent@878611a ("feat(session): add /handoff
command for cross-platform session transfer"). CLI-only — not available from
the Desktop UI.

## Active-session resolution correction (important)

The live conversation session's `source` flips to `'feishu'` once the gateway
owns its routing (observed: `20260821_142243_1e868d`, parent `..._1dad33`
desktop, source='feishu'). Therefore:

- `SELECT id FROM sessions WHERE source='desktop' AND ended_at IS NULL ...`
  MISSES the real active session after a bridge re-point.
- Correct: `SELECT m.session_id FROM messages m JOIN sessions s ON s.id=m.session_id WHERE s.ended_at IS NULL AND s.source IN ('desktop','feishu') ORDER BY m.id DESC LIMIT 1` — survives compaction and chat switches with protection against api_server hijack. NOTE: bare `ORDER BY id DESC LIMIT 1` can return an `api_server`/`unknown` session (from cron or REST tests) and hijack routing.
- `HERMES_SESSION_KEY` env var points at the session the process STARTED in — stale after every compaction.
  stale after every compaction.

## Real-world cases found (Lark ↔ local agents)

| Project | Approach | Relevance |
|---|---|---|
| github.com/zarazhangrui/lark-coding-agent-bridge | Feishu ↔ Claude Code/Codex CLI: per-chat sessions, queueing, /new /cd /ws, streaming cards | closest analog: bridge as separate process; they keep per-chat sessions (no merging) |
| tokenflux.ai/docs/projects/feishu | commercial "same agent, conversations sync across platforms" | cloud backend, not comparable |
| docs.openclaw.ai/channels/feishu | OpenClaw (fork lineage), "bot does not receive messages" troubleshooting | same gateway pattern |

Nobody public does Desktop-session ↔ bot-session merging; it is a non-typical
scenario. Our bridge (outbound watcher + inbound routing to live session) is
the only working pattern found.

## Official docs pointers (local copies under website/docs/)

- `website/docs/user-guide/messaging/feishu.md` — full Feishu bot reference:
  websocket/webhook, group_sessions_per_user, home channel, FEISHU_ALLOWED_USERS,
  dedup file `~/.hermes/feishu_seen_message_ids.json`, per-chat serialization,
  "Another local Hermes gateway is already using this Feishu app_id" error.
- Sessions doc: session ids `YYYYMMDD_HHMMSS_<hex>` (6-char CLI / 8-char
  gateway), parent_session_id for compression splitting.
- Slash commands: `/handoff`, `/sethome`, `/resume`, `/new` (messaging + CLI).

## Search backend note

Web search backends are flaky in this env: Tavily/Parallel return 403 keyless,
firecrawl (`web_search`) intermittently works, `web_extract` (Exa) 403s.
`curl` to hermes-agent.nousresearch.com → Forbidden (WAF). Reliable local path:
read the docs + source directly from `C:\Users\Ruslan\.hermes\hermes-agent\`
(website/docs/, gateway/*.py). GitHub API raw README fetch worked via curl.
