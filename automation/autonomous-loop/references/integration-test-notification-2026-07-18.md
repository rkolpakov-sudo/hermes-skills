# Integration Test + Notification Design (2026-07-18)

## Интеграционный тест Middleware v3 — 6/6 PASS

Full dispatch chain test. Real `loop_handler()` calls, real journal on disk.

### Тестовая среда
- Python 3.11, Windows sandbox
- 178 loop файлов на диске (базовая линия) → 179 после теста (+1)

### Test Run Results

| # | Описание | Результат | Детали |
|---|----------|-----------|--------|
| 1 | `read_file` + `patch` → `_needs_loop=True` | ✅ | Iterative markers: `{'read_file', 'patch'}` matched. `_has_loop=False`, `_is_iterative=True`. |
| 2 | Init loop_handler → journal on disk | ✅ | ID: `loop_01b38a9f`, file: `loop_01b38a9f.json`, state=running, graph с root node. |
| 3 | Phase 2 messages[] injection | ✅ | `[LOOP-ENFORCE: Loop autod — id=loop_01b38a9f...]` appended to messages array. Model sees ID + instruction. |
| 4 | Resume (не double init) | ✅ | Second turn scan finds same `loop_01b38a9f.json`. Same ID, no duplicate created. |
| 5 | Single tool → no loop needed | ✅ | `memory()` alone: `_needs_loop=False`. Correctly does not trigger enforcement. |
| 6 | Run mode → graph node added | ✅ | Nodes before=1 (root), after=2 (plan). Edges: 0→1. |

### Journal Structure After Test
```json
{
  "id": "loop_01b38a9f",
  "state": "running",
  "task": "Интеграционный тест middleware v3 — turn 1",
  "graph": {
    "nodes": {
      "root_b21810d1": {"type": "init"},
      "plan_8c2216c6": {"type": "plan"}
    },
    "edges": [["root...", "plan..."]]
  }
}
```

---

## User Notification Mechanism — Architecture Analysis

### UI Stack Investigation Results

**Desktop components relevant to status display:**
- `apps/desktop/src/components/assistant-ui/thread/status.tsx` (178 lines) — spinner, compaction hint, background resume notice
- `apps/desktop/src/store/compaction.ts` — per-session atom flag (`$compactingSessions`)
- `apps/desktop/src/store/background-delegation.ts` — parked subagent status
- `apps/desktop/src/store/coding-status.ts` — live repo status (git porcelain)

**Backend → Frontend pipeline:**
- `conversation_loop.py`: `_emit_status()` called 18 times. No SSE event types found in chat_completions.py.
- Status flows through `final_response` string or `messages[]` assistant messages rendered by UI layer.
- `agent._build_assistant_message()` builds the message structure (called at L1955, L4467, L4569, L4675, L4806, L5145, L5186, L5264, L5329, L5357).

**Notification infrastructure:**
- `apps/desktop/src/store/notifications.ts` — toast feed (`$notifications`, atom of `AppNotification[]`). Auto-dismiss 5s for info/success. Error/warning persistent. Placement: 'default' (top-center) vs 'bottom-right'.
- `apps/desktop/src/store/native-notifications.ts` — OS-level Electron notifications. Kinds: approval, input, turnDone, turnError, backgroundDone.

### Three-Level Design

**Level 1: Inline status in final_response** (5 min)
```python
# conversation_loop.py L4927+ or L5028
if agent._loop_enforce_inject and isinstance(agent._loop_enforce_inject, dict):
    _inj = agent._loop_enforce_inject
    loop_status_line = f"[🔄 Loop active: {_inj['id']} · strategy={_inj.get('strategy','adaptive')}]"
    # Prepend to final_response or inject as separate status line
```

**Level 2: Dedicated UI component** (~30 min)
- Create `store/loop-status.ts`: atom with `{active: bool, loopId, iteration, maxIterations, state}`.
- Frontend polls backend via SSE/websocket for active loop state OR set from middleware response.
- React component in `status.tsx` alongside `BackgroundResumeNotice`. Pattern: nanostore computed + conditional render.

**Level 3: Toast notifications** (~45 min)
- Init event: `{kind:'info', title:'Loop started', message:...}` → bottom-right toast, auto-dismiss 5s.
- Completion: `{kind:'success', ...}` 
- Timeout/Stuck: `{kind:'warning', placement:'default'}` — persistent until dismissed.

### Trigger Points in conversation_loop.py

| Event | Line | Action |
|-------|------|--------|
| Phase 1 init (new loop) | L4778+ | Show "Loop initialized" toast |
| Phase 2 injection complete | L4920+ | Update inline status |
| Loop completion detected | After tool call check | Show "Task completed in N iterations" toast |
| Timeout/stuck | Status check after run | Warning toast with action button ("extend budget") |
