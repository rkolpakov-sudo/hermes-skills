# ezdxf + MCP Server Pitfalls (Session 2026-07-24)

## ezdxf 1.4.x Layer Discovery Bug

**Problem:** `doc.layers` returns ONLY table entries (`0`, `Defpoints`), NOT layers used by entities in the drawing. A project with 3 MEP layers (`M-PIPE-WATER`, `E-CABLE-PWR`, `HVAC-DUCT-MAIN`) appears to have only 2 empty layers.

**Root cause:** ezdxf 1.4.x does not auto-populate `doc.layers` from entity attributes. The layer table contains only explicitly defined entries.

**Fix:** Read layers from entities:
```python
from collections import Counter
layers = [e.dxf.layer for e in doc.modelspace()]
layer_counts = Counter(layers)
# → {'M-PIPE-WATER': 45, 'E-CABLE-PWR': 32, ...}
```

**Impact:** Any code that iterates `for layer in doc.layers:` or checks `if "MY-LAYER" in [l.name for l in doc.layers]` will miss all actual drawing layers. This breaks:
- MCP server `initialize_analysis()` — returns wrong layer list
- MCP server `get_layer_inventory()` — reports 2 layers instead of real count
- Layer classification modules that filter by `doc.layers`

**Verify with:**
```python
# Bad (empty for ezdxf 1.4.x):
[str(layer.name) for layer in doc.layers]
# → ['0', 'Defpoints']

# Good:
[e.dxf.layer for e in doc.modelspace()]
# → actual layer names used by entities
```

## ezdxf 1.4.x Polyline Points — numpy Arrays, Not Objects

**Problem:** `entity.get_points()` returns numpy arrays, not objects with `.x`/`.y` attributes. Code that iterates `for pt in points: (pt.x, pt.y)` raises `TypeError`.

**Fix:** Iterate as tuples directly:
```python
points = list(entity.get_points(format='xy'))  # → [(x1,y1), (x2,y2), ...]
length = sum(math.dist(p1, p2) for p1, p2 in zip(points, points[1:]))
```

## MCP Server on Windows — UTF-8 stdout Crash

**Problem:** Python MCP servers that print Cyrillic text to stdout crash with `'utf-8 codec can't decode byte 0xc8'` because Windows console uses CP1251/CP866.

**Fix (two parts):**
```python
# 1. Reconfigure stdout at startup:
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
else:
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

# 2. Use ensure_ascii=True in json.dumps() — this is the KEY fix:
print(json.dumps(response, ensure_ascii=True), flush=True)
# Cyrillic becomes \uXXXX (valid JSON). Hermes Desktop parses correctly.
```

**Without `ensure_ascii=True`:** Raw Cyrillic bytes in stdout break stdio JSON-RPC stream on Windows, causing Hermes to fail tool discovery.

## MCP Server — Hermes Requires stdio JSON-RPC

Hermes Desktop connects to MCP servers via **stdio transport only**. An HTTP server (Flask/FastAPI) will NOT be discovered by `hermes mcp add`. The server must:
1. Read JSON-RPC requests from `sys.stdin` (line-delimited JSON)
2. Write responses to `sys.stdout`
3. Handle methods: `initialize`, `tools/list`, `tools/call`

**Register via CLI:**
```bash
hermes mcp add my-server \
  --transport stdio \
  --command 'C:/path/to/.venv/Scripts/python.exe' \
  --args src/mcp_server.py
```

## Cross-Module Wiring — Import vs File Name Mismatch

**Discovered:** `main.py` imports `from src.modules.module_1_structured import ...` but the actual file is `module_2_structured_parsing.py`. Similarly, `from src.modules.main_parser import detect_scale` should be `from src.modules.module_0_preprocessing import detect_scale`.

**Audit pattern (check for this):**
```python
for py_file in glob("src/**/*.py"):
    content = open(py_file).read()
    for imp in re.findall(r"from\s+([\w.]+)\s+import", content):
        mod_path = imp.replace(".", "/") + ".py"
        if not os.path.exists(mod_path) and not os.path.isdir(imp.replace(".", "/")):
            print(f"{py_file}: imports '{imp}' but file missing → ModuleNotFoundError at runtime")
```

## Disconnected Safety Nets Pattern

Security/error-handling modules (`security.py`, `error_handling.py`) define classes/functions that are **never imported** by the main pipeline or MCP server. This creates a false sense of security — code exists, tests pass on individual units, but production never calls them.

**Check:** For each public function in a safety module, grep across all files for import/call references. Count <= 1 (the definition itself) → disconnected.

## Orphaned Code Detection

Files that exist (`cli_agent.py`) but are imported by no other file. After transitioning to MCP+Skill workflow, the CLI agent became dead code. Detect:
```python
# Collect all 'from X import Y' across project
all_imports = set()
for f in glob("src/**/*.py"):
    for imp in re.findall(r"from\s+([\w.]+)\s+import", open(f).read()):
        all_imports.add(imp)

# Check each file against imports
for f in glob("src/*.py"):
    stem = Path(f).stem
    if "src." + stem not in all_imports and stem != "main":
        print(f"{f}: orphaned — nothing imports it")
```
