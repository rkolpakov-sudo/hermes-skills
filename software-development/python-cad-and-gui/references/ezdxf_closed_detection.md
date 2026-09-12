# ezdxf LWPOLYLINE Closed Detection — Debug Notes

## Problem
`ent.dxf.closed` returned `None` even when `close=True` was passed to `msp.add_lwpolyline()`. Tests failed because rooms weren't detected as closed.

## Investigation (VDAS session, 2026-07-15)
Created debug script (`_debug_dxf.py`) → ran through venv:

```python
doc = ezdxf.new(dxfversion="R2018")
msp = doc.modelspace()
pts = [(500,500), (4500,500), (4500,2500), (500,2500)]
msp.add_lwpolyline(pts, close=True)

ent = list(msp)[0]
print(ent.dxf.closed)      # → None (!)
print(dir(ent.dxf))         # found 'flags' attribute
print(getattr(ent.dxf, "flags", 0))  # → 1 (bit 0 set = closed)
```

## Root Cause
ezdxf stores the closed flag in `dxf.flags` bit 0 (value 1), NOT in a separate `closed` attribute. The `close=True` parameter sets the flags bitmask, but `.closed` remains unset in some ezdxf versions.

## Fix
```python
# Correct: check flags bit 0
is_closed = bool(getattr(ent.dxf, "flags", 0) & 1)

# Fallback for near-closed polylines (first ≈ last vertex within tolerance)
if not is_closed and len(pts) > 1:
    dx, dy = pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]
    if (dx*dx + dy*dy) < 1.0:  # 1mm² tolerance
        is_closed = True
```

## Also Found: Vertex Type Variance
In the same environment, LWPOLYLINE vertices returned as **numpy arrays** instead of objects with `.x/.y`. Code must branch on type:
```python
for p in ent:
    if hasattr(p, "x"):
        pts.append((float(p.x), float(p.y)))
    else:
        pts.append((float(p[0]), float(p[1])))  # numpy array
```

## Also Found: Entity Query Syntax
`msp.query("DXF_TYPE == 'LINE'")` — fails on some ezdxf versions. Use direct iteration:
```python
[e for e in msp if e.dxftype() == "LINE"]
```
