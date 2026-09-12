---
name: hermes-messaging-platforms
description: "Configure, troubleshoot, and verify Hermes messaging platform integrations (Feishu/Lark, Telegram, Slack, etc.)."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [messaging, gateway, feishu, lark, telegram, platform-integration, configuration]
    related_skills: [hermes-agent, systematic-debugging]
---

# Hermes Messaging Platform Integration

## Overview

Hermes supports messaging platforms (Feishu/Lark, Telegram, Slack, WhatsApp, Teams, etc.) through a separate **Gateway** process. Desktop mode does NOT run the Gateway automatically — it must be started independently.

## Architecture

- **Desktop/TUI mode**: Runs `web_server` + cron scheduler only. No messaging platform adapters are loaded.
- **Gateway mode**: Separate process (`hermes gateway run`) that loads platform adapters, connects via WebSocket/webhook, and routes messages to the agent via API server.
- `.env` file: Platform credentials live here (not in `config.yaml`). Read at Gateway startup only.

## Configuration Checklist

### 1. Credentials in `~/.hermes/.env`

Each platform requires specific env vars. Example for Feishu/Lark:
```bash
FEISHU_APP_ID=cli_xxx...
FEISHU_APP_SECRET=xxx...
FEISHU_DOMAIN=lark    # Critical! "lark" for international, "feishu" for China
GATEWAY_ALLOW_ALL_USERS=true  # For testing; set FEISHU_ALLOWED_USERS= for production
API_SERVER_KEY=some-key      # Required for message routing (any value works)
```

**Domain mapping:**
| Env Value | Endpoint | Region |
|-----------|----------|--------|
| `feishu` (default) | `https://open.feishu.cn` | China |
| `lark` | `https://open.larksuite.com` | International |

Error `1000040351: Incorrect domain name` = domain mismatch. Fix with `FEISHU_DOMAIN=lark`.

### 2. Start the Gateway (Manual)

```bash
hermes gateway run          # Foreground (recommended for debugging)
```

The Desktop app does NOT start the Gateway automatically. Cron jobs in Desktop mode use an embedded scheduler, but messaging requires a full Gateway process.

### 3. Install Persistent Gateway (Auto-start)

To keep the bot running across sessions and reboots:

```bash
hermes gateway install --start-on-login    # Windows Scheduled Task / systemd / launchd
hermes gateway status                      # Verify installation
```

**Windows note:** If UAC prompt is skipped, Hermes falls back to a Startup folder entry (`.vbs` launcher) — works for per-user auto-start. Accept the UAC prompt during install for a full Scheduled Task with admin privileges.

⚠️ **Process conflict pitfall on Windows**: When Gateway is installed as `--start-on-login`, it spawns at login. If you then run `hermes gateway run` from terminal, **both processes compete for port 8642** — the new one fails silently while the old one keeps running with stale `.env`. Symptoms: `gateway status` shows a different PID than your terminal process; logs don't reflect recent changes.

Fix: Kill ALL gateway python processes first, then start fresh:
```bash
# Windows (from PowerShell or cmd): taskkill //F //IM python.exe   # nuclear option
# Or use MCP Process tool to kill the specific PID from `gateway status`
hermes gateway stop          # May silently fail if process is zombie — verify with status
hermes gateway run           # Only after confirming old PID is gone and port 8642 is free
```

### 4. Configure Home Channel (Optional)

A **home channel** designates a specific chat/channel as the delivery target for cron jobs, system notifications, and background task results. Without it, scheduled deliveries have nowhere to go (`Channel directory built: 0 targets`).

For Feishu/Lark, add to `~/.hermes/.env`:
```bash
FEISHU_HOME_CHANNEL=oc_xxx...        # Your DM chat ID (from gateway.log inbound messages)
FEISHU_HOME_CHANNEL_NAME=Ruslan      # Display name for logging
```

**Finding your chat ID:** Send a message to the bot, then check logs:
```bash
tail -20 ~/.hermes/logs/gateway.log | grep 'Inbound dm'
# Shows: chat_id=oc_xxx... sender=user:ou_xxx... text='...'
```

After setting, restart Gateway. Verify in logs: `Channel directory built: 1 target(s)` (was 0 before).

Similarly available for other platforms (e.g., `TELEGRAM_HOME_CHANNEL`, `TEAMS_HOME_CHANNEL`).

### 4. Verify Connection

Check logs for platform connection:
```bash
tail -20 ~/.hermes/logs/gateway.log | grep -i 'connected\|✓'
```

Expected output pattern:
```
[Platform] Connected in websocket mode (lark)
✓ feishu connected
Gateway running with 2 platform(s)   # api_server + messaging platform
Press Ctrl+C to stop
```

## Common Pitfalls

### FEISHU_DOMAIN default causes error 1000040351
Default is `"feishu"` (China). If app was created on Lark Developer Console (international), set `FEISHU_DOMAIN=lark` or connection fails with `err: 1000040351: Incorrect domain name`.

### Desktop mode doesn't load messaging adapters
The Desktop web_server runs a cron ticker but does NOT connect to messaging platforms. Gateway must be started separately via CLI (`hermes gateway run`).

### Missing API_SERVER_KEY blocks message routing
Recent Hermes versions require `API_SERVER_KEY` in `.env`. Without it:
```
ERROR gateway.platforms.api_server: Refusing to start: API_SERVER_KEY is required
✗ api_server failed to connect
```
Gateway shows "1 platform(s)" instead of 2, and incoming messages won't reach the agent. Set any value: `API_SERVER_KEY=hermes-gateway-key`.

### Session isolation per platform
Each messaging channel (Feishu DM, Telegram user, etc.) gets its **own isolated session** — independent from your Hermes Desktop chat. The bot chat does NOT share history with the Desktop session by default. In-bot commands to manage that channel's context: `/new` (fresh session), `/reset` (clear history), `/stop` (cancel in-flight request).

The session key is deterministic: `agent:{profile}:{platform}:{chat_type}:{chat_id}` (see `gateway/session.py::build_session_key()`). Desktop uses UUID-based sessions stored with `session_key=None` in state.db. By default, these are separate.

#### Unified sessions across platforms (Feishu DM ↔ Desktop)
If you need Feishu DM and Desktop TUI to share the same conversation context, this IS achievable via session key unification:

1. **Patch `gateway/session.py::SessionStore._generate_session_key()`** — after generating a key for a Feishu DM message, call `_unify_desktop_session(key)` which finds the active Desktop session (`source='desktop'`, `end_reason IS NULL`) in state.db and writes the same `session_key` into it.
2. **Patch `gateway/run.py::GatewayRunner.__init__`** — set a config flag (e.g., `config.unify_desktop_feishu_dm = True`) so `_generate_session_key()` knows to perform unification.
3. **Result**: Both Desktop and Gateway processes load `_session_messages` from the same SQLite row per turn, sharing conversation history and agent memory.

See `references/session-architecture.md` → "Unified sessions across platforms" for implementation details and pitfalls (race conditions between simultaneous streams).

**Alternative workarounds (no code changes):**
1. **FEISHU_HOME_CHANNEL** — directs cron notifications and background task results to your Lark/Feishu DM.
2. **send_message from Desktop agent** — push results directly: `send_message(target="feishu:Ruslan")`.
3. **Profile routing** (`config.yaml` → `gateway.profile_routes`) — routes platform/chat_id combos to different profiles, but sessions remain isolated within profiles.

### .env changes require Gateway restart
Platform config is read at startup only. After changing `.env`, kill and restart the Gateway process — no hot reload.

### No user allowlist = all users denied
Gateway denies messages from unknown users by default. For testing: `GATEWAY_ALLOW_ALL_USERS=true` in `.env`. For production, set platform-specific allowlists (e.g., `FEISHU_ALLOWED_USERS=user_id`).

## Troubleshooting Flow

1. **Check Gateway is running**: `hermes gateway status` or look for process
2. **Verify .env vars**: `grep 'PLATFORM_PREFIX' ~/.hermes/.env` — confirm domain, credentials present
3. **Read gateway.log**: `tail -40 ~/.hermes/logs/gateway.log` — look for connection errors
4. **Check errors.log**: `tail -20 ~/.hermes/logs/errors.log` — SDK-level errors
5. **Test with a message**: Send `/ping` to bot, watch logs for inbound event handling

## Platform-Specific Notes

### Feishu/Lark
- Uses `lark-oapi` Python SDK (websocket mode by default)
- App IDs from CLI registration have `cli_` prefix — works fine
- Connection URL: `wss://msg-frontier-sg.larksuite.com/ws/v2` (Lark) or `open.feishu.cn` (Feishu)

**DNS pitfall on Windows/MSYS:** On some Windows hosts, the MSYS2/git-bash environment and its Python venv **cannot resolve `open.larksuite.com`** (`[Errno 11001] getaddrinfo failed`). The domain `open.feishu.cn` resolves fine even when `FEISHU_DOMAIN=lark` is set. If you see DNS failures from agent scripts targeting Lark API, switch the base URL to `https://open.feishu.cn/open-apis/` — both domains accept the same API calls for international (Lark) apps.

**Outbound messages from Desktop session:** Desktop mode does NOT connect messaging platforms. To send a message from a Desktop agent to Feishu/Lark, use direct HTTP API via **Windows native Python** (PowerShell), not MSYS bash:
```python
# Authenticate: POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal
# Send: POST https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id
```
See `references/outbound-desktop-to-feishu.md` for a working script template. Run via PowerShell using the Hermes venv python: `hermes-agent\venv\Scripts\python.exe script.py`.

### Telegram  
- Uses long polling by default; webhook mode optional via `TELEGRAM_WEBHOOK_URL`

## Verification

Successful integration = Gateway shows platform connected AND inbound messages trigger agent responses. Watch logs for:
```
✓ [platform] connected
Gateway running with 2 platform(s)
# After sending a message:
[Platform] received event type=im.message.receive_v1
```
