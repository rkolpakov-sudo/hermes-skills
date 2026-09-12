---
name: python-cad-and-gui
description: Python-based CAD/GUI application development — ezdxf, Shapely geometry, PySide6 (Qt) patterns, and DXF I/O quirks. Load when working with DXF import/export, CAD geometry processing, or Qt signal/slot wiring in Python desktop apps.
---

# Python CAD & GUI Development

Class-level techniques for building Python applications that process CAD geometry (ezdxf/Shapely) and provide interactive Qt-based GUIs (PySide6).

## When to Use

- Reading/writing DXF files with ezdxf
- Processing geometric data (walls, rooms, polygons) with Shapely
- Building PySide6 desktop apps with custom signals/slots
- Implementing spatial indexes (R-Tree) for geometry queries

## ezdxf Quirks & Fixes

### Title Block Scale Does NOT Transform Geometry (§6.4.4)
**CRITICAL:** The title block scale (1:N, e.g., "М 1:100") is a print/display parameter — it does **NOT** transform DXF coordinates. Drawing geometry is always in real-world units regardless of stamp scale.

**Bug pattern:** Dividing pipe/duct lengths by `scale.ratio` produces values N× too small for mm-drawings (e.g., 8000mm becomes 0.08m instead of 8.0m). This was the #1 cause of benchmark failure in dxf-mep-analyzer project.

**Fix — unit conversion only, no scale division:**
```python
def calculate_pipe_length_mm_to_m(raw_length_mm):
    """DXF geometry is real-world coords. Only convert units."""
    return raw_length_mm / 1000.0  # mm → m, NO scale.ratio division

# WRONG (breaks everything for mm drawings):
# length_m = (raw_mm / scale_ratio) / 1000.0
```

**Unit mapping per spec:** `{'mm': 1000.0, 'centimeters': 100.0, 'meters': 1.0}` — divide raw by the unit divisor only.

### Detecting Scale from Title Block
Scale text may be in ATTRIB (inside INSERT TitleBlock) or free TEXT/MTEXT on a TITLE/ШТАМП layer. Search both:

```python
# Priority order for detect_scale():
# 1. INSERT block named "TitleBlock"/"Штамп" → scan entity.attribs for 'М 1:XXX'
#    → return method="title_block", confidence=0.95
# 2. Free TEXT/MTEXT on layer containing 'TITLE' or 'ШТАМП' in name
#    → return method="title_block", confidence=0.95
# 3. Free TEXT/MTEXT elsewhere (generic text search)
#    → return method="text_search", confidence=0.85
# 4. DIMENSION analysis → method="dimension"
# 5. Heuristic from bounding box size → method="heuristic"

# Regex that handles both 'М 1:100' and 'М 1 100':
re.search(r'[МM]\s*1\s*:?\s*(\d+)', txt)
```

### Layer Registration — `doc.layers` Is Incomplete
In ezdxf, `doc.layers` does **NOT** auto-register layers. It only returns explicitly created layer records ('0', 'Defpoints'). To find all used layers:

```python
# WRONG — returns only ['0', 'Defpoints']:
layers = [l.name for l in doc.layers]

# CORRECT — scan entity .dxf.layer attributes:
used_layers = set()
for ent in doc.modelspace():
    layer = getattr(ent.dxf, 'layer', '') or ''
    if layer:
        used_layers.add(layer)
```

### Block Attribute Binding (ezdxf 1.4.x)
Attributes on INSERT blocks require **explicit binding** — they don't auto-populate from block definition ATTRDEFs:

```python
# Create blockref then explicitly bind each attribute:
br = msp.add_blockref('BLOCK_NAME', (x, y), dxfattribs={'layer': 'layer_name'})
for tag_text in [('TAG1', 'value1'), ('TAG2', 'value2')]:
    br.add_attrib(tag_text[0], tag_text[1])

# Reading attributes:
for attrib in entity.attribs:
    print(attrib.dxf.tag, attrib.dxf.text)  # Use .attribs iterator
```

### Block Definition Parsing (nested + dynamic blocks)
Parse `doc.blocks` for block definitions. Skip space-defining blocks ("*", "*0", "*PaperSpace"). Track nested INSERTs and dynamic parameters:

```python
for blk in doc.blocks:
    if blk.name in ("*", "*0", "*PaperSpace"):
        continue
    # Nested blocks: look for INSERT entities inside the block def
    # Dynamic params: PARAMETER, ACTION, CONSTRAINT dxftypes
    base_point = blk.get_base_point()  # Returns ezdxf.math.Vector
```

### LWPOLYLINE Closed Detection
`ent.dxf.closed` is often `None`. Use flags bit 0 instead:
```python
is_closed = bool(getattr(ent.dxf, "flags", 0) & 1)
# Fallback: check if first/last points are within tolerance
if not is_closed and len(pts) > 1:
    dx, dy = pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]
    is_closed = (dx*dx + dy*dy) < 1.0  # 1mm tolerance
```

### Vertex Format Variance
LWPOLYLINE vertices may be numpy arrays or objects with `.x/.y`:
```python
for p in ent:
    if hasattr(p, "x"):
        pts.append((float(p.x), float(p.y)))
    else:  # numpy array / tuple-like
        pts.append((float(p[0]), float(p[1])))
```

### Entity Filtering (Version Compatibility)
Avoid `msp.query("DXF_TYPE == 'LINE'")` — it fails on some ezdxf versions. Use direct iteration instead:
```python
def _filter_by_type(entities, dxftype):
    return [e for e in entities if e.dxftype() == dxftype]
```

## Shapely Gotchas

### Negative Buffer Degeneracy
`buffer(-thickness/2)` on a short segment returns an empty geometry. Always check:
```python
result = line.buffer(-thickness/2)
if result.is_empty:
    return LineString()  # degenerate case
```

### Polygon Splitting Thresholds
After `difference()` or splitting, filter by minimum area — but **parameterize the threshold**, never hardcode values like `1_000_000` (1 m²). Small rooms (bathrooms) will be excluded.

## PySide6 / Qt Patterns

### Signals Require QObject Inheritance
Custom classes need to inherit `QObject` to use `Signal`:
```python
from PySide6.QtCore import QObject, Signal as QtSignal

class WallTool(QObject):  # MUST inherit QObject
    wall_created = QtSignal(float, float, float, float)  # x1,y1,x2,y2
    
    def __init__(self, canvas, renderer):
        super().__init__()  # Call QObject.__init__
```

### Signal Lifecycle: Prevent "Signal source has been deleted"
**CRITICAL:** Two independent causes produce this crash:

1. **Missing `QObject.__init__()` call.** If a QObject subclass uses an aliased import (`from PySide6.QtCore import QObject as _QObject`) and forgets to call `_QObject.__init__(self)`, PySide6 reports `libshiboken: '__init__' method of object's base class not called` on repr, and ALL signal emits crash with "Signal source has been deleted" — even though the object is alive. **Always call the super constructor.**

2. **Object garbage-collected between tests.** Test fixtures create/destroy widgets; Qt event loop still references destroyed slots.

**Fix — Three-Layer Defense:**

1. **QObject subclass: Call parent `__init__` AND add `cleanup()` with receiver loop**
```python
from PySide6.QtCore import QObject as _QObject, Signal as _QtSignal

class WallTool(_QObject):
    wall_created = _QtSignal(float, float, float, float)

    def __init__(self, canvas, renderer):
        _QObject.__init__(self)  # CRITICAL — omitting this crashes ALL signals
        self.canvas = canvas
        self.renderer = renderer

    def cleanup(self) -> None:
        try:
            for r in list(self.wall_created.receivers()):
                self.wall_created.disconnect(r)  # ONE at a time, never bare .disconnect()
        except Exception:
            pass
        self.canvas = None    # type: ignore[assignment]  -- use actual attr names
        self.renderer = None  # type: ignore[assignment]
```

2. **QMainWindow: Override `closeEvent` with receiver loop (NOT bare `.disconnect()`)**
Calling `.disconnect()` without arguments raises "Failed to disconnect (None)" on PySide6. Always enumerate receivers first via `.receivers()`.

3. **pytest: Per-test `teardown_method`** (not just `teardown_class`)

> Never rely on Python GC alone to clean up Qt signal connections. See `references/qt_signal_lifecycle.md` for full patterns with code examples.

### Headless Testing
Set `QT_QPA_PLATFORM=offscreen` before importing PySide6:
```python
import os; os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
QApplication.instance() or QApplication([])
```

## Spatial Index (R-Tree)

### Safe Removal Pattern
`get_bounds()` fails if the object was already removed. Wrap in try-except:
```python
def remove(self, obj_id):
    try:
        bounds = self._tree.get_bounds(obj_id)
        self._tree.delete(obj_id, bounds)
    except Exception:
        pass
    self._objects.pop(obj_id, None)
```

## DXF → MEP Pipeline Architecture

Multi-module pipeline for CAD drawing analysis (§4–§7 Enterprise Analyzer):

```
M0 Preprocessing (§4) → M1 Layer Classification (§5.2) → M2 Structured Parsing (§6) → M3 Quantification (§7)
```

- **M0**: Scale detection, unit discovery, XREF resolution, metadata extraction, validation.
- **M1**: `discover_layers()` scans modelspace entities → `classify_layer()` matches against YAML config categories (exact/fuzzy/unknown). Output: `layer_to_category` mapping + `LayerAssignment` dataclass per layer.
- **M2**: Block/text/polyline extraction, pipe length calculation (NO scale division), spatial graph construction (§6.5 CROSSES/NEAR edges), JSON export. Imports M1 for classification; falls back to inline matching if M1 unavailable.
- **M3**: Material takeoff — aggregates pipes by diameter (`DN{mm}`) and equipment by block type, groups by system prefix (HVAC/PLUMB/ELEC/FIRE/GAS). Output: `QuantificationReport` with per-system breakdowns + text/JSON export.

See `references/dxf_mep_analyzer_patterns.md` for M0–M2 details; M3 patterns documented below.

## Quantification Patterns (§7)

```python
from module_3_quantification import quantify, format_text_report, quantify_and_export

# Full pipeline: parsed data → quantification report
report = quantify(parsed_data, source_file="drawing.dxf")
print(format_text_report(report))  # Human-readable console output
quantify_and_export(parsed_data, output_path="quant.json")  # JSON + report in one call
```

Key design decisions:
- **Stamp/title block exclusion**: Equipment on `Штамп` layer is always excluded from quantification totals.
- **Pipe diameter labeling**: PLUMB pipes use `DN{mm}` format; HVAC ducts use `{width}mm`; unspecified layers fall back to mark label or `"UNSPECIFIED"`.
- **System grouping**: Category prefix before `_` determines system name (`HVAC_DUCT` → `HVAC`, `PLUMB_PIPE` → `PLUMB`).

## CLI Entry Point Patterns

Single file with quantification:
```bash
python main.py drawing.dxf --quantify
```

Batch mode (all DXF files, separate outputs + quant reports):
```bash
python main.py *.dxf --batch -q --output-dir ./results/
```

## Pitfalls

1. **EventBus Singleton** — A global EventBus (via `get_event_bus()`) creates shared state across test runs. Reset or inject a fresh instance per test session.
2. **No coordinate validation** — DXF imports can produce negative/zero-length segments. Validate before creating geometry objects.
3. **Memory leaks** — Spatial indexes grow unbounded; clear stale entries when model objects are deleted.

## References

- `references/ezdxf_closed_detection.md` — Debug session details on LWPOLYLINE flags behavior across ezdxf versions.
- `references/qt_signal_lifecycle.md` — "Signal source has been deleted" crash: root causes, cleanup() pattern for QObject subclasses, closeEvent teardown, and pytest per-test teardown_method strategy.
- `references/dxf_mep_analyzer_patterns.md` — DXF-MEP Analyzer patterns (M0–M3): scale detection priority chain, layer classification engine, block attribute binding, spatial edge algorithms (CROSSES/NEAR), quantification pipeline, JSON serialization of graph data.
- `references/dxf-mep-testing-pitfalls.md` — Testing infrastructure code: logger compatibility (stdlib vs structlog), binary file I/O without `encoding=`, regex pitfalls in security validation, cross-sheet duplicate detection edge cases.
