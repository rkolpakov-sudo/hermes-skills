---
name: python-env-troubleshooting
description: "Diagnose and fix Python environment issues: venv conflicts, PYTHONPATH pollution, C-extension version mismatches, sys.path ordering."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [python, environment, venv, pip, sys.path, PYTHONPATH, numpy, importerror]
---

# Python Environment Troubleshooting

## When to Use

- `ModuleNotFoundError` or `ImportError` for packages that "should be installed"
- C-extension version mismatch (`cp311` `.pyd` loaded by Python 3.14)
- Tests pass locally but fail through the agent's execution context
- Package reports wrong version after install
- `pip show X` says one location but imports resolve elsewhere

## Hermes-Specific PYTHONPATH Pollution (Critical)

**The problem:** Hermes runtime injects its own venv into `PYTHONPATH`:
```
PYTHONPATH=C:\Users\Ruslan\.hermes\hermes-agent;C:\Users\Ruslan\.hermes\hermes-agent\venv\Lib\site-packages
```

This causes the agent's cp311 packages to shadow project .venv (cp314) packages, producing errors like:
```
ImportError: No module named 'numpy._core._multiarray_umath'
* _multiarray_umath.cp311-win_amd64.pyd  # ← wrong Python version!
```

### Diagnostic

```python
# Check if Hermes paths appear BEFORE project .venv in sys.path:
import sys
for p in sys.path:
    print(p)

# Verify which numpy/shapely/etc actually loads:
import numpy
print(numpy.__file__)  # Should be inside project's .venv, NOT hermes-agent/venv
```

**Red flag:** `~/.hermes/hermes-agent/venv/Lib/site-packages` appearing before `<project>/.venv/Lib/site-packages`.

### Fix

Run with clean environment:

```bash
# Bash (Linux/WSL/Git-Bash):
unset PYTHONPATH && unset VIRTUAL_ENV && .venv/bin/python your_script.py

# PowerShell:
$env:PYTHONPATH=""; $env:VIRTUAL_ENV="" ; & .venv\Scripts\python.exe your_script.py
```

For pytest: `unset PYTHONPATH && .venv/Scripts/python.exe -m pytest ...`

### Why --target pip install Doesn't Help Alone

Installing with `pip install --target <project>/.venv/Lib/site-packages` puts the correct package in project venv, but if `PYTHONPATH` still points to Hermes venv first, Python still loads the wrong one. **Always unset PYTHONPATH when running the project.**

## General sys.path Troubleshooting

1. **Check ordering:** Earlier paths win. Use `python -c "import sys; [print(i,p) for i,p in enumerate(sys.path)]"`
2. **Identify pollution source:** Check env vars: `echo $PYTHONPATH`, `env | grep PYTHONPATH`
3. **Verify package location:** `pip show <package>` vs actual import path (`import X; print(X.__file__)`)

## C-Extension Version Mismatch

When you see `_multiarray_umath.cp311-win_amd64.pyd` for Python 3.14:
1. The `.pyd` was compiled for a different Python minor version
2. Root cause is almost always wrong venv being loaded via PYTHONPATH or incorrect `VIRTUAL_ENV`
3. Fix by ensuring correct venv activation (see above)

## Known Library Bugs (Session-Verified)

| Library | Version | Bug | Impact | Workaround |
|---------|---------|-----|--------|------------|
| **tcod** | v21.x | `AStar.get_path()` returns `[]` for paths >5 steps on small/medium grids — no error raised, just empty result | Pathfinding silently fails; indistinguishable from "no path exists" | Write custom A* (heapq + numpy). Both AStar and Dijkstra affected — library-wide issue |
| **ezdxf** | v1.x | `Layer.name` does not exist after `doc.layers.new()` | DXF export crashes with `AttributeError` | Skip return value; pass layer name as string: `msp.add_line(p1, p2, dxfattribs={"layer": "NAME"})` |
| **ezdxf** | v1.x | `ezdxf.read_dxf()` removed → use `ezdxf.readfile()` | DXF re-opening in tests fails | Update all read patterns to `readfile()` |
| **ezdxf** | 1.4.x | `doc.layers` returns ONLY table entries (`0`, `Defpoints`) — NOT layers used by entities | Layer discovery / inventory is empty or wrong | Read from entities: `Counter(e.dxf.layer for e in doc.modelspace())` |
| **ezdxf** | 1.4.x | LINE `.dxf.startx/.starty/.endx/.endy` raise `DXFAttributeError` | Line length / intersection code crashes | Use `.dxf.start_point[0,1]`, `.dxf.end_point[0,1]` (tuple of floats) |
| **ezdxf** | 1.4.x | LWPOLYLINE vertex iteration returns numpy arrays, not objects with `.x/.y` attrs | Polyline length calculation crashes with `AttributeError` | Check `hasattr(pt, 'x')`; otherwise use `pt[:2]` to get (x,y) tuple |
| **ezdxf** | 1.4.x | ASCII DXF starts with `SECTION HEADER...` not binary magic bytes `ACAD` | Header validation rejects valid ASCII files | Read first 4KB and check for `"SECTION"` or `"$ACADVER"` markers instead of fixed-byte magic |

## Quick Reference

| Symptom | Likely Cause | Diagnostic Command |
|---------|-------------|-------------------|
| cp311 `.pyd` for Python 3.14 | PYTHONPATH points to wrong venv | `python -c "import sys; print(sys.path[:5])"` |
| Package installed but not found | Wrong venv active | `pip show <pkg>` vs `import X; print(X.__file__)` |
| Works locally, fails in agent | Agent runtime PYTHONPATH injection | `echo $PYTHONPATH` before running |

## Related Skills

- `systematic-debugging` — for the broader 4-phase debugging methodology