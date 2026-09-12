---
name: agent-middleware-audit
description: "Audit and implement agent middleware — code that intercepts, modifies, or injects into the tool-call dispatch pipeline between LLM output and execution. Anti-patterns for discarded handler results, orphaned state, race conditions, and performance traps on hot paths."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [middleware, agent-architecture, dispatch-pipeline, tool-call-interception, enforcement, audit]
    related_skills: [systematic-debugging, autonomous-loop, requesting-code-review]
---

# Agent Middleware Audit

## Overview

Agent middleware is code that sits between model-generated tool calls and their execution — intercepting, modifying, injecting, or enforcing behavior in the dispatch pipeline. Common locations: `conversation_loop.py` (Hermes), tool call routers, post-generation hooks.

**Core risk:** middleware creates side-effects on disk/network but never communicates them back to the model. Result = orphaned state that no one uses.

## When to Use

- Auditing any code that intercepts/modifies `tool_calls` before execution
- Implementing enforcement mechanisms (mandatory tool usage, auto-init)
- Reviewing middleware that creates resources on behalf of the agent
- Diagnosing "why does this middleware not actually change behavior?"

---

## The 5 Critical Anti-Patterns

### 1. Discarded Handler Results → Orphaned State (CRITICAL)

**Pattern:** Middleware calls a handler function but ignores/drops the return value.

```python
# BROKEN — creates orphaned state on disk, model never knows
_loop_h({"mode": "init", "task": "..."})  # ← result discarded!
```

**Why it fails:** The handler returns `{id, status, message}`. Without injecting this back into `messages`, the model cannot:
- Reference the resource ID in future tool calls
- Know that state was created
- Receive instructions to use the new resource

**Fix:** Inject result as a synthetic tool message or append to conversation history:

```python
result = json.loads(_loop_h({"mode": "init", "task": "..."}))
messages.append({
    "role": "tool",
    "content": (
        f"Auto-initialized loop {result['id']}. "
        f"Call loop(mode='run', id='{result['id']}') on each iteration."
    ),
})
```

### 2. Nonexistent Attribute Access (CRITICAL)

**Pattern:** `hasattr(agent, '_some_attr')` → always FALSE because the attribute was never defined on the class.

```python
# BROKEN — _last_user_content never set anywhere in agent class
if hasattr(agent, '_last_user_content'):  # ← always False
    desc = agent._last_user_content[:200]
```

**Fix:** Trace where data actually lives:
- User message → `messages` array (find last `role="user"` entry)
- Check actual class attributes via search (`grep '_user' conversation_loop.py`)

### 3. No-Observable-Effect Operations (MEDIUM)

**Pattern:** Calling a function that reads state and discards the result — filesystem I/O with zero behavioral change.

```python
# BROKEN — reads status, returns JSON string, middleware ignores it
_loop_h({"mode": "status", "id": _lid})  # ← what does this achieve?
```

**Fix:** Either inject into messages or skip if no side-effect is needed.

### 4. Race Condition on Double-Init (MEDIUM)

**Pattern:** Two turns both scan disk, find nothing, and each create independent resources.

**Fix:** Use atomic check-or-create (`os.O_CREAT | os.O_EXCL`) OR session-level state tracking:
```python
if not hasattr(agent, '_enforced_loop_id'):
    agent._enforced_loop_id = _create_new_loop()
# Subsequent turns reuse the cached ID
```

### 5. Lifecycle Leak — Auto-Resources Never Cleaned Up (MEDIUM)

**Pattern:** Auto-created resources persist indefinitely until timeout/cleanup job runs days later.

**Fix:** Track auto-created resources and clean them up when:
- Task completes (check for success signal)
- N consecutive turns with no tool calls referencing the resource
- Session ends

---

## Audit Checklist

Run this checklist on any middleware that intercepts tool calls or creates resources behind the model's back:

| # | Check | Why |
|---|-------|-----|
| 1 | Handler results injected back to `messages` array? | Model must see created state IDs |
| 2 | Resource IDs visible to model's next turn? | Cannot use what you don't know exists |
| 3 | No nonexistent attributes (`hasattr` alone is insufficient)? | Dead code path → wrong fallback data |
| 4 | Atomic check-or-create or session-level locking? | Prevents duplicate resources on concurrent turns |
| 5 | Auto-resources have cleanup/lifecycle management? | Prevents disk accumulation over sessions |
| 6 | No heavy I/O (filesystem scan, JSON parse) on hot dispatch path? | Hot path runs every tool turn — cache state in memory |
| 7 | Fail-open: middleware errors never break main execution chain? | Middleware is advisory, not critical |
| 8 | Imports outside hot path (or cached at module level)? | Avoid repeated import overhead per turn |

---

## Performance Traps on Hot Paths

Middleware runs on **every tool call turn**. Treat it like a database query optimizer — O(n) where n could be hundreds of turns.

**Anti-patterns:**
- `os.listdir()` + `json.load()` every turn → cache in `agent._state` dict
- `import X as _x` inside middleware block → module-level import or lazy cache
- Scanning all loop files when only one is active → store ID at init, reuse

---

## Implementation Pattern: Correct Enforcement Middleware

```python
# ── CORRECT enforcement pattern ───────────────────────
try:
    # 1. Check cached state first (fast path)
    if not getattr(agent, '_enforced_loop_id', None):
        # 2. Create resource
        result = json.loads(_handler({"mode": "init", ...}))
        agent._enforced_loop_id = result["id"]

        # 3. INJECT into messages so model sees it
        messages.append({
            "role": "tool",
            "content": (
                f"[ENFORCE] Auto-initialized loop {result['id']}. "
                f"Use loop(mode='run', id='{result['id']}') each turn."
            ),
        })
    else:
        # 4. Resume existing — inject status reminder
        agent._enforced_loop_id  # already cached

except Exception as exc:
    logger.debug("Middleware failed (non-fatal): %s", exc)
# ← Fail-open: execution continues regardless
```

---

## Related Session Detail

See `references/middleware-audit-2026-07-18.md` for the full audit transcript of loop enforcement middleware in conversation_loop.py (critical bugs, specific line references, test results).
