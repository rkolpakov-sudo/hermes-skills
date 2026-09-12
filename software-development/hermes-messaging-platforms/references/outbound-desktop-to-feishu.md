# Outbound Desktop → Feishu/Lark Script

Created 2026-07-24. Session: `20260724_225007_1f1de2`.

## Problem

Desktop mode does not load messaging platform adapters. There is no built-in `send_message` tool or `/api/send` endpoint for pushing outbound messages from a Desktop session to Feishu/Lark. The cron job system (`/api/jobs`) also failed because the MSYS environment could not resolve `open.larksuite.com`.

## Root Cause

- **MSYS DNS block:** Python running in git-bash venv cannot resolve `open.larksuite.com` (error `[Errno 11001] getaddrinfo failed`).
- **Domain workaround:** `open.feishu.cn` resolves fine on the same host — both domains accept identical API calls for Lark international apps.
- **Execution context matters:** The script must run via Windows native Python (`venv\Scripts\python.exe`) invoked from PowerShell, NOT through MSYS bash/terminal tool which inherits the DNS block.

## Working Approach

Direct HTTP POST to Feishu REST API (no SDK needed):

1. Get tenant token: `POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal`
2. Send message: `POST https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id`

Read credentials from `~/.hermes/.env`. Use `urllib.request` (stdlib, no extra deps).

## Script Location

The verified script lives at:
```
C:\Users\Ruslan\.hermes\scripts\_send_feishu.py
```

Run via PowerShell:
```powershell
C:\Users\Ruslan\.hermes\hermes-agent\venv\Scripts\python.exe C:\Users\Ruslan\.hermes\scripts\_send_feishu.py
```

Expected output on success:
```
[+] Token OK (len=42)
[+] Message SENT: om_xxxxxxxxxx...
```

## Key Details

- Chat ID for delivery target: `oc_5c034ca56b338848b73553d0acb4a3ed`
- The script uses ASCII-only text in the message body to avoid encoding issues with PowerShell/curl pipelines
- For custom messages, edit the `"text"` field inside `json.dumps({"text": "..."})`

## What Was Tried (and Failed)

| Approach | Result |
|----------|--------|
| `lark-oapi` SDK sync call | Event loop conflict in async agent context |
| HTTP via MSYS Python to `open.larksuite.com` | DNS `[Errno 11001] getaddrinfo failed` |
| Native Windows `curl.exe` | Works but encoding/JSON parsing issues with UTF-8 payloads |
| Internal cron `/api/jobs` mechanism | Job created but scheduler rejected due to invalid token / config mismatch |
| **Direct HTTP via Windows Python to `open.feishu.cn`** | ✅ **Works** |
