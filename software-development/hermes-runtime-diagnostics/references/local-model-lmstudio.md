# Local LM Studio + Hermes: worked diagnostic case (2026-08-21)

## Symptom (user report, in Russian)
"Модель рассуждает достаточно много и происходит постоянный сброс и зацикливание в ходе работы сессии! Так не было раньше."

## Environment at diagnosis
- LM Studio serving on `http://127.0.0.1:1234` (both `/v1` and `/api/v0` endpoint families)
- Loaded model: `qwen3.8-27b-nvfp4-mtp` — esatapedico GGUF, full id `esatapedico/qwen3.8-27b-nvfp4-mtp-gguf/qwen3.8-27b-nvfp4-mtp-very-high.gguf`, arch `qwen35`, capabilities `["tool_use"]`
  - `/api/v0/models`: `max_context_length: 262144`, **`loaded_context_length: 87552`** (VRAM-bound)
  - Earlier load attempt at 07:29 failed (desktop.log): HTTP 400 "Model loading was stopped due to insufficient system resources. Under the current settings, this model requires approximately 22.69 GB of memory"
- Prior stable model: `qwen3.6-27b-nvfp4-mtp` (used July 23 and again this morning 10:29-11:31)

## Evidence from logs (~/.hermes/logs/)

### API call stats (agent.log, `API call #N ... in= out= latency=`)
qwen3.6-27b-nvfp4-mtp (10:33-10:35) — healthy:
```
in=24447 out=239  latency=20.7s
in=24736 out=205  latency=5.3s
in=24943 out=154  latency=4.2s
in=26387 out=282  latency=8.4s
```
qwen3.8-27b-nvfp4-mtp (12:30-13:05) — reasoning explosion:
```
in=47318 out=6903 latency=224.6s
in=48689 out=4005 latency=128.0s
in=60437 out=3492 latency=120.2s
in=62447 out=6155 latency=187.5s
in=63684 out=3119 latency=95.6s
```
July baseline (agent.log.1, 2026-07-23): qwen3.6 `out=666 latency=31.9s` — ~10× faster than qwen3.8 today.

Note: short calls (out=50-150, latency 2-5s) are NOT failures — those are quick tool-call JSON responses. The long calls (3-7K, 100-224s) are the problem.

### Context detection failure (agent.log)
```
agent.model_metadata: Could not detect context length for model 'esatapedico/qwen3.8-27b-nvfp4-mtp-gguf/qwen3.8-27b-nvfp4-mtp-very-high.gguf' at http://127.0.0.1:1234/v1 — defaulting to 256,000 tokens (probe-down). Set model.context_length in config.yaml to override.
agent.model_metadata: Using hardcoded context length 131,072 for model '...' (custom endpoint, catalog match on 'qwen')
run_agent: LM Studio model activation was rejected or completed without a verifiable active context length; falling back to configured context
```
Hermes assumed 131K-256K; real loaded context was 87.5K → compression fired too late.

### Compression failure (errors.log / agent.log)
```
agent.turn_context: Preflight compression made insufficient progress: ~249,454 -> ~238,105 request tokens; skipping additional passes
agent.conversation_compression: context compression started: session=20260821_121411_ecf829 messages=198 tokens=~249,454
agent.conversation_compression: context compression done: session=... messages=199->179 rough_tokens=~184,963 (duration 151s)
agent.auxiliary_client: Auxiliary compression: using lmstudio (qwen3.8-27b-nvfp4-mtp) at http://127.0.0.1:1234/v1/
```
Compression runs on the SAME slow model → 90-150s per pass and barely shrinks anything.

### Interruptions / resets
```
agent.conversation_loop: Turn ended: reason=interrupted_during_api_call ... api_calls=49/60 budget=48/60 tool_turns=94 ... duration=3419.7s   (57 min turn!)
agent.conversation_loop: Turn ended: reason=interrupted_by_user ... api_calls=18/60 ... duration=420.5s
agent.conversation_loop: Turn ended: reason=interrupted_during_api_call ... api_calls=23/60 ... duration=2063.6s   (34 min)
tui_gateway.server: prompt.submit: truncating session 09be2773 history 13 -> 0 messages (ordinal=0)
tui_gateway.server: prompt.submit: target row_id 20996 not found for session 09be2773 (in-memory + durable); refusing truncation without fallback
```
`status=interrupted` in `tui turn finished` = user aborted (stop button or resubmit). With `busy_input_mode: interrupt`, resubmitting a message kills the in-flight turn, then desktop truncates history → the visible "сброс".

### Reasoning config (agent.log)
```
agent.agent_runtime_helpers: switch_model: reasoning_config resolved for qwen3.8-27b-nvfp4-mtp: {'enabled': True, 'effort': 'high'}
```
Config had global `reasoning_effort: high` (config.yaml line 66) and `busy_input_mode: interrupt` (line 257). No `model.context_length` override existed.

## Root cause chain
1. Model switched to reasoning-heavy qwen3.8 "very-high" GGUF → 4-7K reasoning tokens per call, 2-4 min latency (10-20× slower than qwen3.6).
2. Hermes assumed ctx 131K-256K (probe-down + hardcoded); real loaded ctx 87.5K → preflight compression too late and ineffective (249K→238K).
3. Legit agent turns became 34-57 min long (23-49 calls × 2-4 min) → user interrupts/resubmits → `busy_input_mode: interrupt` kills turn → desktop truncates history → "постоянный сброс".
4. Feedback loop: reasoning tokens inflate history → frequent compression by the same slow model → degraded recall → more calls → longer turns.

## Fixes applied / recommended
- `/reasoning low` or `/reasoning none` for local reasoning models (or disable Qwen3 thinking in LM Studio)
- config.yaml `model.context_length: 80000` (≈ loaded 87552 with headroom)
- `busy_input_mode: queue` to stop resubmit-kills-turn
- Or revert to qwen3.6-27b-nvfp4-mtp (proven stable)
- Clean up failing MCP servers (sqlite, context7, brave-search, dxf-mep-analyzer) that spam `failed initial connection ... parking until a reconnect is requested` every ~2 min

## LM Studio API cheatsheet
- `GET /v1/models` — served model list (ids only, no context info)
- `GET /api/v0/models` — per model: `state` ("loaded"/"not-loaded"), `max_context_length`, `loaded_context_length`, `capabilities` (e.g. tool_use), `quantization`, `arch`
- Model load failure signature: HTTP 400 `{"message": "Failed to load model \"...\". Error: Model loading was stopped due to insufficient system resources. Under the current settings, this model requires approximately 22.69 GB of memory, and continuing to load it would likely overload..."}`
