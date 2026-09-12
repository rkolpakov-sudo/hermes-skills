# Middleware Audit — loop enforcement in conversation_loop.py (2026-07-18)

## Context

Attempted "hard enforcement" of `loop` tool usage via middleware hook at L4709–L4775 in `conversation_loop.py`. Deep audit revealed fundamental architectural failure.

## Bugs Found

### CRITICAL: Discarded init result (L4762-4768)
```python
_loop_h({"mode": "init", "task": _task_desc, ...})  # ← returns {"id":"loop_xxx","status":"initialized"} — DISCARDED
logger.info("[LOOP-ENFORCE] Auto-init loop for multi-step task")
```
Model never receives loop ID. Cannot call `loop(mode='run', id=...)` without knowing the ID. Loop journal created on disk but agent is unaware → orphaned state.

### CRITICAL: _last_user_content does not exist (L4754-4760)
Attribute `agent._last_user_content` never defined in class. Only 1 reference exists (this middleware). Always falls through to `assistant_message.content` which is model output, not user input → wrong task description injected into loop init.

### MEDIUM: Resume status call has no effect (L4749)
```python
_loop_h({"mode": "status", "id": _lid})  # ← returns JSON string — DISCARDED
```
Reads disk, parses journal, computes topology → throws away result. Zero behavioral change for agent.

## Architecture Verdict

Middleware **cannot enforce** loop usage through background init alone. Loop is a collaborative tool requiring the model to call `loop(mode='run')` each turn with plan/act/check phases. Background state creation without model notification = useless orphaned journal files accumulating in `~/.hermes/loops/`.

### Correct enforcement requires ONE of:
1. **Inject result into messages** → model sees loop ID + instruction on next turn
2. **Auto-inject loop tool call** into `assistant_message.tool_calls` list (append, not just background init)
3. **Cache in agent state** (`agent._enforced_loop_id`) and inject synthetic tool response

## Performance Issues Found

| Issue | Location | Impact |
|-------|----------|--------|
| Full filesystem scan every qualifying turn | L4726-4739 | O(n·m) — n loop files × m tool turns |
| `import os, json` inside hot path | L4726 | Repeated module import per turn |
| `import uuid` inside nested branch | L4752 | Same |

## Additional loop_tool.py Findings

- SEC-7: `_normalize_sig` regex (L356) misses Windows paths (`C:\Users\...`) — only catches text containing literal "path/" or "path\"
- ROBUST-1: `_save_journal` (L98-103) writes directly without temp+rename → corrupted journal on crash mid-write
- PERF-1: `_detect_repeated_patterns` (L384-407) — O(n³) worst case; each pair of same-sig nodes triggers full BFS ancestor traversal
