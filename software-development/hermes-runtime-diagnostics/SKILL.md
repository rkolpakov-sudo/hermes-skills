---
name: hermes-runtime-diagnostics
description: Use when Hermes agent loops, resets, or stalls.
version: 1.0.0
---

# Hermes Runtime Diagnostics

Diagnose "the agent misbehaves" reports — infinite looping, session resets, frozen/stalled turns, context overflow, degraded behavior after a model switch. Root-cause from local evidence: config.yaml, `~/.hermes/logs/*.log`, the provider API, and `context_length_cache.yaml`. Do not theorize from the symptom alone; the log lines below tell the real story.

## When to use
- Agent loops / repeats tool calls / user reports "зацикливание"
- Session resets, history truncated (`truncating session ... history N -> 0`), turns interrupted
- Turns take 20-60+ minutes; model "reasons a lot" / every step feels stuck
- Behavior changed after switching model or provider

## Diagnostic workflow
1. **Establish what is active**: `model.default` / `provider` in config.yaml; the `[System: ...]` banner; grep agent.log for `switch_model` to find when/how the model changed.
2. **Probe the provider API** (LM Studio):
   - `curl http://localhost:1234/v1/models` — served model list
   - `curl http://localhost:1234/api/v0/models` — per-model `state` ("loaded"/"not-loaded"), `max_context_length`, **`loaded_context_length`**, `capabilities`. The loaded value is the REAL window (VRAM-bound); max is aspirational.
3. **Read `context_length_cache.yaml`** — Hermes caches per-model context; may be stale (keyed by exact model id string) or absent for new models.
4. **Extract API call stats**: `grep "API call #" agent.log` — compare `in=`/`out=`/`latency=` across models and times. Reasoning models show out=3-7K tokens and latency=100-200s+ per call; instruct models out=150-500 and 5-30s. A 10-20× jump on the same task = model change, not a Hermes regression.
5. **Grep signature warnings** (agent.log / errors.log):
   - `Could not detect context length ... defaulting to 256,000 tokens (probe-down)` + `Using hardcoded context length 131,072` → Hermes does NOT know the real context → compression fires too late. The log itself says: "Set model.context_length in config.yaml to override."
   - `Preflight compression made insufficient progress: ~249,454 -> ~238,105` → history far exceeds context; compression (executed by the SAME model) was ineffective.
   - `Compression budget rearmed after provider-confirmed recovery` → recovery works but costs 1.5-2.5 min per pass on a slow local model.
6. **Turn ended reasons** (grep "Turn ended"): `interrupted_by_user` / `interrupted_during_api_call` plus `tui turn finished ... status=interrupted duration=NNN` = the USER aborted (impatience or resubmit), not an agent bug. `text_response(finish_reason=stop)` = healthy. Check `busy_input_mode: interrupt` in config — resubmitting a message while a turn runs KILLS the in-flight turn.
7. **Check reasoning config**: `grep -n "reasoning_effort" config.yaml`; agent.log `reasoning_config resolved for <model>: {'enabled': True, 'effort': 'high'}`. `reasoning_effort: high` + a Qwen3.x thinking model = 4-7K reasoning tokens per turn → history explodes.
8. **Check desktop/gui.log**: model load failures (`insufficient system resources`), `truncating session ... history N -> 0` (the visible "reset"), `target row_id ... not found ... refusing truncation` (desktop bug, non-fatal).
9. **Noise filter**: failing MCP servers spam warnings every ~2 min (`failed initial connection ... parking until a reconnect is requested`). Not the root cause, but pollutes logs and context — note it for cleanup.

## Fixes (priority order)
| Problem | Fix |
|---|---|
| Model reasons too long (Qwen3.x + effort high) | `/reasoning low` or `/reasoning none` in chat; disable thinking mode in LM Studio; or switch to an instruct/older model |
| Hermes wrong context assumption | `model.context_length: <real>` in config.yaml — take `loaded_context_length` from /api/v0/models, keep ~90% headroom |
| Resubmit kills turns ("сброс") | `busy_input_mode: queue` instead of `interrupt` |
| Model doesn't fit VRAM | Load smaller quant/context in LM Studio; API then reports the reduced `loaded_context_length` |
| MCP warning spam | Fix or disable failing servers (`hermes mcp remove NAME`) |

## Pitfalls
- Do NOT trust `max_context_length` from /v1/models — `loaded_context_length` (VRAM-bound) is what matters; they can differ 3×.
- `context_length_cache.yaml` keys by exact model id string; switching models invalidates it silently.
- "Looping" is often a legit agent run whose per-call latency exploded (2-4 min × 23-49 calls = 34-57 min turns). Compare out=/latency= before blaming loop logic.
- Compression uses the SAME model (auxiliary_client) — on a slow local model each compression pass takes 90-150s and may still be "insufficient progress".
- Qwen 3.x "thinking" models differ wildly by GGUF: same family name, very different reasoning behavior. Check the exact loaded id (e.g. esatapedico ...-very-high.gguf).

## References
- `references/local-model-lmstudio.md` — worked case: qwen3.8-27b-nvfp4-mtp vs qwen3.6, verbatim log signatures, LM Studio API cheatsheet.
