---
name: large-scale-code-recovery
description: "Recover severely broken Python files (massive corruption, lost code, multiple critical bugs) using atomic phased patching with compile-after-each-phase validation."
version: 1.0.0
author: Hermes Agent
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [code-recovery, large-scale-fix, atomic-patching, python-debugging, file-corruption]
    related_skills: [systematic-debugging, test-driven-development]
---

# Large-Scale Code Recovery

## Overview

When a Python source file has been severely corrupted (massive code loss, multiple syntax errors, broken imports), applying fixes one-by-one is error-prone — each intermediate state may be un-compileable, making it impossible to isolate which fix introduced new problems.

**Core principle:** Apply fixes in **atomic phases**, where each phase validates before proceeding. If a phase fails, you know exactly which category of fix broke things.

## When to Use

- File lost >50% of its content (accidental overwrite, bad regex replacement)
- Multiple critical bugs across different categories (imports, constants, syntax, logic)
- No git history available for recovery
- Previous "quick fix" scripts made things worse by cascading errors

**Don't use for:** Single isolated bugs — use `systematic-debugging` instead.

## The Atomic Phased Approach

### Phase Structure

Each phase targets ONE category of fixes and ends with validation:

```python
# Phase A: Fix imports → validate compile → proceed or abort
# Phase B: Fix syntax errors → validate compile → proceed or abort
# Phase C: Restore missing constants/functions → validate + functional tests
# Phase D: Update schema/config structures → validate + dispatch check
# Phase E: Wire up analytics/hooks → validate lifecycle
```

### Validation After Each Phase

After applying fixes in each phase, run ALL three checks before proceeding:

1. **`py_compile.compile(fp, doraise=True)`** — catches syntax errors immediately
2. **AST parse** (`ast.parse(content)`) — confirms valid Python structure, counts functions/classes
3. **Targeted verification** — grep for specific patterns the phase was supposed to fix/restore

Only proceed if all three pass. If validation fails, diagnose within that phase before moving on.

## Pitfalls

### "Remove Duplicates" Deletes Everything

A script that identifies duplicate lines and removes them can accidentally delete ALL instances:

```python
# WRONG — deletes ALL matching lines if len > 1
matches = [i for i, l in enumerate(lines) if 'CONSTANT =' in l]
for i in matches:
    del lines[i]  # ← deletes EVERY occurrence, not just duplicates!

# CORRECT — keep first, remove rest
if len(matches) > 1:
    for i in matches[1:]:  # skip the first match
        del lines[i]
```

**Always verify AFTER the operation:** count occurrences of the constant/pattern post-deletion. If the count is 0 when it should be ≥1, you've over-deleted and must restore from the pre-phase copy.

### String Replacement Matched Wrong Occurrence

When using `content.replace(old, new)` or regex substitution:
- Include enough surrounding context in `old_string` to make it unique
- Verify the replacement by checking the exact line numbers changed
- Don't use bare keyword matches (`'ARCHIVE_EXT ='`) — they match comments and docstrings too

### Phase Order Matters

Fix categories in this order:
1. **Imports** — everything else depends on these being correct
2. **Constants** — referenced throughout code; missing constants cause NameError at runtime even if compile passes
3. **Syntax errors** — must resolve before functional validation works
4. **Schema/config structures** — API contract correctness
5. **Logic/function bodies** — behavior fixes

Fixing logic before imports/means the file won't compile, hiding whether your logic fix was correct.

## Verification Script Pattern

After all phases complete, run a comprehensive verification that checks:

```python
import py_compile, ast, os, re

fp = "path/to/file.py"
with open(fp) as f:
    content = f.read()

# 1. Compile check
py_compile.compile(fp, doraise=True)

# 2. AST parse + count functions/classes
tree = ast.parse(content)
funcs = [n for n in ast.iter_child_nodes(tree) if isinstance(n, ast.FunctionDef)]
classes = [n for n in ast.iter_child_nodes(tree) if isinstance(n, ast.ClassDef)]

# 3. Verify each fix was applied
checks = {
    "No duplicate imports": content.count("from X import Y") == 1,
    "Constant Z defined": sum(1 for l in lines if l.startswith("Z =")) == 1,
    "Schema has param P": '"param_P"' in content.split("SCHEMA")[1],
    "Function F exists": f"def {F}(" in content,
}

passed = sum(checks.values())
print(f"{passed}/{len(checks)} checks passed")
```

## Session Pattern (from loop_tool.py recovery, 2026-07-19)

Recovery of `~/.hermes/hermes-agent/tools/loop_tool.py` from corrupted state:

| Phase | What Was Fixed | Result |
|-------|---------------|--------|
| A | Duplicate imports (`Path`, `deque/defaultdict`) | ✅ Compile passed — but accidentally deleted `ARCHIVE_EXT` and `DEFAULT_LOOP_TTL_SEC` definitions entirely (not just duplicates) |
| B | Syntax error in `loop_spawn` (`=context` → `context=context or ...`) | ✅ |
| C | Schema updated to v3.3 with P0/P1 params; `loop_resume` wired to `_restore_latest_checkpoint`; `loop_run` handles `rollback_to`/`branch_from`; analytics wired to init/run/stop lifecycle | ✅ |
| D | `check_loop_requirements` validates FS; SSE status emission implemented | ✅ |
| E | `mode_phase` clarification in schema description | ✅ |
| F | **Recovery from Phase A mistake** — restored accidentally-deleted constants `ARCHIVE_EXT` and `DEFAULT_LOOP_TTL_SEC` | ✅ |

Final result: 2,415 lines, 94.9 KB, 56 functions, all 14 modes dispatched, all 16 features present, 0 compilation errors.

Key lesson: Phase A's "remove duplicates" script used `len(matches) > 1` then deleted ALL matches instead of keeping the first. This is now codified as a pitfall above.

