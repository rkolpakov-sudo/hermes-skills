# LM Studio provider-only switch → OOM + phantom model in dropdown (post-mortem, 2026-08-21)

## Symptom (user report, Russian)
"При работе, Hermes загружает самостоятельно модель в LM Studio вызывая OOM так как я уже загрузил модель до запуска Hermes! Кроме того, в выпадающем меню списка моделей LM Studio появилась модель Deepseek V4 Flash — это вообще ОШИБКА!"

## What happened
An earlier session changed ONLY `model.provider: lmstudio` + `model.base_url: http://127.0.0.1:1234/v1` in config.yaml (plus `model.default` to a qwen GGUF id). The user's existing Feishu/desktop session had NOT been reset, so `state.db` still held `sessions.model = deepseek/deepseek-v4-flash` for it. On session resume, Hermes combined:
- **model from the session row** (`state.db` → `sessions.model`, `sessions.model_config`)
- **provider/base_url from config.yaml** (`lmstudio` / 127.0.0.1:1234)

→ every request and probe went to LM Studio with the cloud model id `deepseek/deepseek-v4-flash`.

## Evidence trail (how to confirm this failure mode)
1. `~/.hermes/logs/agent.log`:
   ```
   run_agent: OpenAI client created (agent_init, ...) provider=lmstudio base_url=http://127.0.0.1:1234/v1 model=deepseek/deepseek-v4-flash
   agent.model_metadata: Could not detect context length for model 'deepseek/deepseek-v4-flash' at http://127.0.0.1:1234/v1 — defaulting to 256,000 tokens (probe-down)
   agent.agent_runtime_helpers: Model switched in-place: deepseek/deepseek-v4-flash (lmstudio) -> deepseek/deepseek-v4-flash (custom:routerai-flash)
   ```
2. `~/.lmstudio/server-logs/YYYY-MM/YYYY-MM-DD.N.log` (LM Studio's own log):
   ```
   Received request: GET to /v1/models/deepseek/deepseek-v4-flash
   Error: Model with identifier 'deepseek/deepseek-v4-flash' not found
   ```
3. LM Studio settings `~/.lmstudio/.internal/http-server-config.json` had `"justInTimeModelLoading": true` — so an unknown requested id is NOT rejected cleanly; LM Studio tries to load/import it → OOM ("insufficient system resources", `Failed to load model ... requires approximately 22.69 GB`) and adds the phantom id to its model dropdown.
4. Desktop/gui log: `Auxiliary title generation failed: HTTP 400: Failed to load model "esatapedico/...-very-high.gguf" ... insufficient system resources` — auxiliary tasks (title generation, vision) auto-inherited the main provider `lmstudio` and picked a quant variant that was NOT on disk (`-very-high`, 22.69 GB) while only `-very-low` was installed.

## Root cause chain
1. Provider-only switch (config) + old session model (state.db) = mismatched pair sent to the local server.
2. LM Studio `justInTimeModelLoading: true` tries to load ANY requested id → OOM / phantom dropdown entry.
3. Auxiliary tasks (`Auxiliary auto-detect: using main provider lmstudio`) also route to the local server and may pick non-installed quants → secondary OOM.

## Fix applied
- `hermes config unset model.context_length` (leftover from the attempted switch)
- `hermes config unset providers.lmstudio` (custom-provider entry created by mistake during the attempt)
- Restored `model.provider: custom:routerai-flash`, `model.base_url: https://routerai.ru/api/v1`, `model.default: deepseek/deepseek-v4-flash`
- Verified: `grep -in "lmstudio|1234" ~/.hermes/config.yaml` → clean; `curl http://localhost:1234/v1/models` → no deepseek id; `hermes chat -q` → answered by deepseek-v4-flash.
- The phantom dropdown entry vanished from `/v1/models` + `/api/v0/models` (it was a JIT runtime entry, not a downloaded file — nothing to delete on disk).

## Correct switch procedure (the DO this instead)
1. Pick the exact model id whose `/api/v0/models` entry shows `state: "loaded"` (e.g. `qwen3.6-27b-nvfp4-mtp`). Never use an id that is `not-loaded` or not on disk.
2. Change BOTH together: `hermes config set model.provider lmstudio` + `hermes config set model.default "<loaded-id>"` (+ `model.base_url` if not the built-in default `http://127.0.0.1:1234/v1`). Prefer the built-in `lmstudio` provider over `custom:lmstudio` (see `references/lmstudio-model-switch.md`).
3. Start a NEW session (`/new` or `/reset`). Old sessions keep their stored model from state.db and will keep hitting the wrong endpoint.
4. Optionally pin auxiliary models so they don't auto-inherit lmstudio: set `auxiliary.title_generation.model` / `auxiliary.vision.model` to the loaded id (or keep main provider cloud).

## General rule
The active model for a resumed session comes from `state.db` (sessions table), NOT config.yaml alone. Config `model.*` drives NEW sessions. When diagnosing "wrong model / OOM / phantom id", check BOTH:
```sql
SELECT id, model, source, model_config FROM sessions WHERE id='<session_id>';
```
and the `[System: ...]` banner / agent.log `switch_model` lines.
