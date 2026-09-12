# Loop Tool Integration Verification

## Visibility Chain (4 levels must all be correct)

1. **Registry** — `tools/loop_tool.py` line ~2467: `registry.register(name="loop", ...)` with handler + check_fn
2. **_HERMES_CORE_TOOLS** — `toolsets.py` line 69: `"loop"` in the core tools list (position #14). All platforms inherit this.
3. **TOOLSETS["loop"]** — `toolsets.py` lines 247-253: `{tools: ["loop"], includes: [], description: "..."}`
4. **CONFIGURABLE_TOOLSETS** — `hermes_cli/tools_config.py` line 66: `("loop", "🔄 Autonomous Loop", "...")`

If loop is not visible to agent, check all 4 levels. Missing #2 or #3 hides the tool even if registry shows it.

## End-to-End Test Procedure (Python)

```python
from tools.loop_tool import loop_init, loop_run, loop_status, loop_recommend_next, loop_history, loop_stop

# Init
r = loop_init(task="Test", max_iterations=5, strategy="adaptive")
lid = r["id"]

# Plan → Act → Check(continue) cycle
loop_run(lid, mode="plan", plan="Step 1")
loop_run(lid, mode="act", action_result="Did something")
loop_run(lid, mode="check", check_verdict="continue", check_details="What was verified")

# Status — verify context survival fields
s = loop_status(lid)
assert s["task"] == "Test"
assert s["path_timeline"]  # non-empty list of node summaries
assert s["recent_actions"]  # last 5 ACT nodes

# Recommend — verify metrics + budget adjustment present
rec = loop_recommend_next(lid)
assert "metrics" in rec
assert "budget_adjustment" in rec
assert rec.get("task") == "Test"

# History — verifies iteration grouping
h = loop_history(lid)
assert h["returned_count"] >= 1

# Complete the loop
loop_run(lid, mode="check", check_verdict="done", check_details="Final verification")
stop_result = loop_stop(lid, reason="test complete")

# Verify journal persisted on disk
import json
with open(stop_result["journal_path"]) as f:
    saved = json.load(f)
assert saved["state"] == "stopped"
```

## Key Config Locations (for troubleshooting)

| File | Purpose | Path |
|------|---------|------|
| `loop_tool.py` | Tool logic + registry registration | `~/.hermes/hermes-agent/tools/` |
| `toolsets.py` | `_HERMES_CORE_TOOLS` list + `TOOLSETS` dict | `~/.hermes/hermes-agent/toolsets.py` |
| `tools_config.py` | `CONFIGURABLE_TOOLSETS` tuple for GUI/CLI menu | `~/.hermes/hermes-agent/hermes_cli/tools_config.py` |
