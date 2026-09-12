# OpenCode Free (`opencode-free`) — verified catalog behavior

Captured 2026-08-22 against live `https://opencode.ai/zen/v1/models`.

## Keyless access requirement
- Header must be `Authorization: ""` (empty string, NOT `Bearer <key>`).
  A placeholder Bearer key → 401.
- `HTTP-Referer: https://hermes-agent.nousresearch.com`, `X-Title: Hermes Agent`,
  `User-Agent: HermesAgent/<ver>` are sent by the profile's `default_headers`.

## Catalog shape
`GET /zen/v1/models` → 200, `{"object":"list","data":[{id,object,created,owned_by}, ...]}`.
**No `pricing` field** — so `fetch_models_with_pricing()` returns `{}` for this
endpoint (it requires `pricing` to be a dict). Don't rely on it for opencode.

## Live count vs keyless-usable
- 64 total models in the dump.
- Only `-free`-suffixed ids are reachable without a paid key.
- Of the 8 `-free` ids, **only 2 actually answer 200** (verified by chat probe):
  - `hy3-free` → "PONG"
  - `x-preview-f-free` → 200 (empty content, but reachable)
- The other 6 `-free` ids are DEAD (verified, UA-independent):
  - `laguna-s-2.1-free` → 403
  - `nemotron-3-ultra-free` → 403
  - `nemotron-3.5-lightning-free` → 403
  - `muse-spark-1.2-contributor-free` → 403
  - `mimo-v2.5-free` → 429 (even with `User-Agent: opencode/latest` → still 403)
  - `deepseek-v4-flash-free` → 400
- Non-free ids (claude/gpt/gemini/...) → 401 without a paid key.

## Recommended live-first pattern (what was implemented)
`_opencode_free_live_models()`:
1. keyless GET `/zen/v1/models`
2. keep only ids ending in `-free`
3. parallel ThreadPoolExecutor chat-probe (timeout ~7s) per candidate
4. return only ids whose probe returned HTTP 200; fall back to static
   `_PROVIDER_MODELS["opencode-free"]` if the catalog or every probe failed.

This self-updates: when opencode rotates free models, the picker follows
without a Hermes release — unlike the old hardcoded 6-item list (4 of which
were already 403 on 2026-08-22).

## Note on UA gating (debunked)
The pre-fix code comment claimed some models were UA-gated (429 unless
`User-Agent: opencode/latest`). Testing proved false: `mimo-v2.5-free` returns
403 under BOTH `opencode/latest` and `HermesAgent/...`. Dead `-free` ids are
server-side delisted, not UA-blocked. Don't impersonate the opencode UA.
