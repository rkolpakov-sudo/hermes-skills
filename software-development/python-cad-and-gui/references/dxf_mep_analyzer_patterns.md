# DXF-MEP Analyzer Patterns

Session: 2026-07-23, project `dxf-mep-analyzer` (Enterprise Analyzer v1.0.0)

## Scale Detection Priority Chain

Four methods in order of confidence:

1. **Title Block ATTRIB** — Search INSERT blocks named "TitleBlock"/"Штамп"/etc. for attributes matching `[МM]\s*1\s*:?\s*(\d+)`. Returns `method="title_block"`, confidence=0.95.

2. **Free TEXT on TITLE layer** — Free TEXT/MTEXT entities whose layer name contains 'TITLE' or 'ШТАМП'. Same method/confidence as above.

3. **Generic text search** — Any free TEXT/MTEXT matching the scale pattern, regardless of layer. Returns `method="text_search"`, confidence=0.85.

4. **Dimension analysis** — Compare dimension display text vs geometric length. Median ratio rounded to standard scale. Returns `method="dimension"`.

5. **Heuristic from bbox** — Building-sized geometry (10k-100k mm) → assume 1:100. Smaller → still 1:100 but lower confidence. Returns `method="heuristic"`.

## Layer Scanning Pattern

```python
# ezdxf does NOT auto-register layers in doc.layers
used_layers = set()
for ent in doc.modelspace():
    layer = getattr(ent.dxf, 'layer', '') or ''
    if layer:
        used_layers.add(layer)
```

## Block Attribute Binding (ezdxf 1.4.x)

Attributes do NOT auto-populate from ATTRDEF definitions. Must bind explicitly:

```python
br = msp.add_blockref('BLOCK_NAME', insert_point, dxfattribs={'layer': 'name'})
br.add_attrib('TAG_1', 'value_1')
br.add_attrib('TAG_2', 'value_2')
```

Reading: `for attrib in entity.attribs: attrib.dxf.tag, attrib.dxf.text`

## Spatial Edge Algorithms (§6.5)

### CROSSES (Liang-Barsky segment-BBOX intersection)
For each LINE/LWPOLYLINE segment vs INSERT block bbox: parametric clipping returns t0,t1. If 0≤t0<t1≤1 → segment crosses bbox.

### NEAR (Euclidean distance, threshold=200.0mm)
Distance between element centroids/bboxes. Weight = `max(0.1, 1.0 - dist / (threshold * 2))`. Connects nearby equipment to pipes/ducts.

## JSON Serialization for Graph Data

```python
def _make_serializable(obj):
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_make_serializable(item) for item in obj]
    elif hasattr(obj, '__dataclass_fields__'):
        return _make_serializable(asdict(obj))
    else:
        return obj

# Usage: json.dump(_make_serializable(structured_data), f, indent=2)
```

## Background Entity Filtering (ARCH_BG)

Entities beyond drawing bbox + 5% margin are considered architectural background and excluded from MEP analysis. Uses `is_background_entity(entity, drawing_bbox, margin_ratio=0.05)`.

## Layer Classification Engine (M1, §5.2)

```python
from module_1_layer_classification import parse_categories, classify_layer, discover_layers

# Parse YAML config → CategoryDef list with fuzzy matching thresholds
categories = parse_categories(yaml_config)  # {"patterns": [...], "fuzzy_threshold": 0.8, ...}

# Classify one layer name → LayerAssignment(category_key, match_type, confidence)
assignment = classify_layer("ВК_Трубы", categories)  # → PLUMB_PIPE, exact, 1.0

# Batch: discover layers from DXF doc + classify all at once
layers = discover_layers(doc)
result = classify_layers(layers, yaml_config_path, dxf_path)
```

Key design: `classify_layer()` returns UNKNOWN with confidence=0.0 when fuzzy score < threshold — never misclassifies ambiguous layers. Fallback strategy: exact → prefix (e.g., "ВК_" matches PLUMB patterns first) → full-name substring → fuzzy string similarity → unknown.

## Quantification Pipeline (M3, §7)

Three-phase aggregation from structured parsing output (`parse_dxf()` result):

1. **`aggregate_pipes_by_system()`** — Groups pipe/duct/cable segments by layer→category mapping; labels diameters as `DN{mm}` (PLUMB) or `{width}mm` (HVAC).
2. **`aggregate_equipment_by_system()`** — Counts equipment blocks per type, excluding `Штамп` layer from totals.
3. **`build_system_quantification()`** — Groups by system prefix (`HVAC_DUCT` → `HVAC`, `PLUMB_PIPE` → `PLUMB`), accumulating pipe lengths and equipment counts.

Report output: `QuantificationReport.systems[]` (per-category breakdown) + `summary_by_system{}` (condensed per-system totals). Text report via `format_text_report()` shows equipment types sorted by count descending.

## CLI Entry Point (`main.py`)

Single-file mode with quantification:
```bash
python main.py drawing.dxf --quantify -q  # → *_analysis.json + *_quant.json
```

Batch mode (glob expansion, separate outputs):
```bash
python main.py *.dxf --batch -q -o ./results/  # → batch_summary.json + per-file reports
```

Key flags: `--config`, `--units`, `--output-dir`, `--summary-only`, `--no-workspace` (skip XREF workspace), `--quantify/-q`, `--quant-output`.
