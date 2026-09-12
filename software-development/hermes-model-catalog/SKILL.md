---
name: hermes-model-catalog
description: Debug/fix stale or wrong Hermes provider model-picker lists.
---

# Hermes Model Catalog Debugging

When a user reports the model picker shows wrong / stale / missing models for a
provider, the bug is almost always in one of three layers. Work top-down and
**always prove the fix with a real run** (the user requires evidence, not
description).

## The function chain (where the list actually comes from)

1. `curated_models_for_provider(provider)` → calls `provider_model_ids(normalized)`.
2. `provider_model_ids(provider)` in `hermes_cli/models.py` — the real switch.
   Tries a **live `/v1/models`** fetch for many providers, or returns a
   **static `_PROVIDER_MODELS[provider]`** list, or merges both.
3. `cached_provider_model_ids(provider)` — wraps (2) with a **disk cache**.
   The picker/UI calls THIS, not (2) directly.

## Pitfall #1 — the disk cache masks your fix (the #1 mistake)

`cached_provider_model_ids` reads `$HERMES_HOME/provider_models_cache.json`
**before** calling the live path. TTL = 1h; stale-while-revalidate serves the
old entry immediately and refreshes off-thread.

> After editing `provider_model_ids` or `_PROVIDER_MODELS`, the picker keeps
> showing the OLD list until the cache expires — UNLESS you invalidate it.

Invalidate (writes through to disk immediately):
```python
from hermes_cli.models import clear_provider_models_cache
clear_provider_models_cache("opencode-free")   # or None to clear all providers
```
Without this step your correct fix looks broken for up to an hour.

## Pitfall #2 — early `return` bypasses the live fetch

Some providers have a deliberate
`if normalized == "<slug>": return list(_PROVIDER_MODELS.get(...))`
early return that *skips* the live endpoint entirely. If a provider's list is
stuck on a hardcoded set, grep `normalized ==` inside `provider_model_ids` —
that early return is the culprit. Decide consciously whether live-first is safe
(see Pitfall #3) before removing it.

## Pitfall #3 — a live `/v1/models` dump is NOT a safe picker list

A raw catalog contains entries that are unusable in the picker context:
- OpenCode Zen `/zen/v1/models` returns 64 models, but **keyless** access
  (no API key, `Authorization: ""` header) works only for `-free`-suffixed
  ids — and even some of those 403/429/400 because promos end. Serving all 64
  would show 62 models that 401 without a paid key.
- Fix: filter by what's actually keyless-accessible, then **probe** each
  candidate with a short chat completion to drop dead ids. See
  `references/opencode-free.md` for the verified pattern + dead-model list.

## Verification recipe (prove the fix every time)

Run BOTH paths and confirm they agree, then confirm the disk cache is fresh:
```python
from hermes_cli import models as m
print(m.provider_model_ids("opencode-free", force_refresh=True))          # live path
print(m.curated_models_for_provider("opencode-free", force_refresh=True))  # alt path
m.clear_provider_models_cache("opencode-free")
print(m.cached_provider_model_ids("opencode-free", force_refresh=False))   # picker path, cold
```
Cold `cached_provider_model_ids` should return in <0.1s (from cache) and match
the live result. If it still shows the old list, the cache invalidation didn't
stick or the wrong slug was cleared.

## Live catalog endpoint reference

| Provider | Catalog URL | Keyless auth |
|---|---|---|
| opencode-free / opencode-zen | `https://opencode.ai/zen/v1/models` | `Authorization: ""` (empty, NOT `Bearer`) |
| opencode-go | `https://opencode.ai/zen/go/v1/models` | `Authorization: ""` |

`https://opencode.ai/v1/models` (no `/zen`) → **404**. Always use the `/zen` path.
