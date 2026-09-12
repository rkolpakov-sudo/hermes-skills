# Multi-Module Pipeline Repair — Case Study

Session: 2026-07-24, DXF-MEP Analyzer (commit `e3ab1f6`)
Project: 8 interconnected Python modules + MCP server
Outcome: All critical runtime errors resolved; full pipeline runs end-to-end in 0.51s.

## The Problem

After a deep architectural audit, the project had **8 cascading runtime failures** spread across 6 modules. Each fix revealed the next broken seam — classic symptom of import wiring and function signature drift from incomplete refactoring.

## Pattern: Cascading Import Wiring Breakage

### Symptom
```python
ModuleNotFoundError: No module named 'module_1_structured'
```
File is actually `module_2_structured_parsing.py` (renamed during refactor).

### Repair Sequence
1. **List actual modules:** `ls src/modules/` → find real filenames
2. **Search for broken imports:** `grep -rn "import.*module_1" src/`
3. **Cross-reference function names in target file:** `grep "^def \|^class " src/modules/module_2_structured_parsing.py`
4. **Patch import + update ALL call sites** (not just the import line)

### Applied Fixes (`src/main.py`)
| Broken Import | Corrected Import |
|---------------|-----------------|
| `from src.modules import module_1_structured` | `from src.modules.module_2_structured_parsing import parse_dxf` |
| `main_parser.detect_scale()` | `module_0_preprocessing.detect_scale()` |

## Pattern: Function Signature Drift

### Symptom
```python
TypeError: quantify_dxf() got an unexpected keyword argument 'scale_info'
```
Function was renamed AND signature changed between refactors.

### Repair Sequence
1. **Read actual function signature in callee:** `grep -A 5 "^def quant" src/modules/module_3_quantification.py`
2. **Compare with caller invocation** line-by-line
3. **Map old params → new params** (names change, not just reorder)

### Applied Fix (`src/main.py`)
```python
# Before: wrong function name + wrong parameters
quant = quantify_dxf(doc=doc, scale_info=scale_info, layer_mapping_path=config.layer_mapping)

# After: correct function + correct signature
from src.modules.module_3_quantification import quantify
quant = quantify(parsed_data=structured_data, source_file=config.dxf_path)
```

## Pattern: Dataclass vs Dict Mismatch

### Symptom
```python
TypeError: generate_reports() got an unexpected keyword argument 'project_info'
```
Caller passes plain dicts (`project_info={...}`); callee expects dataclass instances.

### Root Cause
`module_7_report.generate_reports()` signature:
```python
def generate_reports(output_dir, metadata: ReportMetadata, project: ProjectInfo, summary: AnalysisSummary, ...)
```
All three are `@dataclass` types. Caller was passing ad-hoc dicts with wrong key names (`project_info` instead of `project`).

### Repair Sequence
1. Read function signature in callee module
2. Import the dataclass types into caller
3. Construct proper objects with correct field names (verify against dataclass definition)

### Applied Fix (`src/main.py`)
```python
# Before: plain dicts, wrong key names
generate_reports(output_dir=config.output_dir, metadata={...}, project_info={...}, summary={...})

# After: proper dataclass instances
from src.modules.module_7_report import generate_reports, ReportMetadata, ProjectInfo, AnalysisSummary
metadata = ReportMetadata(structured_model=..., vision_model=...)
project = ProjectInfo(name=Path(config.dxf_path).stem)
summary_obj = AnalysisSummary(total_entities_parsed=N, target_layers=[...], analysis_duration_sec=T)
generate_reports(output_dir=config.output_dir, metadata=metadata, project=project, summary=summary_obj, ...)
```

## Pattern: Logging Fallback Incompatibility

### Symptom
```python
TypeError: Logger.info() got multiple values for argument 'module'
```
When `structlog` is unavailable, fallback uses standard Python logging — which rejects keyword arguments.

### Root Cause
Standard Python logger: `logger.info("format %s", value)` (positional + format string)
Structlog style: `logger.info("event_name", key=value)` (keyword args as metadata)

These are **incompatible**. Code that passes kwargs to a stdlib logger crashes.

### Applied Fix (`src/logging_config.py`)
```python
class module_timer:
    def __exit__(self, *exc):
        elapsed = time.time() - self._start
        if structlog_available:
            self.logger.info("module_end", name=self.name, duration_sec=elapsed)  # structlog style
        else:
            try:
                self.logger.info("module_end", name=self.name, duration_sec=elapsed)
            except TypeError:
                self.logger.info("module_end [%s] %.2fs", self.name, elapsed)  # stdlib fallback
```

Also patched `MetricsTracker.increment()` — stdlib logger doesn't accept `counter_name=X` kwargs.

## Pattern: ezdxf 1.4.x API Changes (Version-Dependent)

Three breaking changes in ezdxf 1.4.x that caused runtime crashes:

| Old API (pre-1.4) | New API (1.4.x) | Error if wrong |
|-------------------|-----------------|----------------|
| `doc.layers` → layer list | `Counter(e.dxf.layer for e in doc.modelspace())` | Empty layer inventory |
| LINE `.dxf.startx/.endx` | LINE `.dxf.start_point[0,1]`, `.dxf.end_point[0,1]` | `DXFAttributeError: Invalid DXF attribute "endx"` |
| LWPOLYLINE vertices have `.x/.y` | Vertices are numpy arrays → use `pt[:2]` | `AttributeError: 'ndarray' has no attribute 'x'` |

Additionally, ASCII DXF files start with `SECTION HEADER...` not binary magic bytes. Header validation that reads only first 10 bytes and checks for `"ACAD"` rejects valid ASCII files → scan first 4KB instead.

## Verification Strategy

After fixing one module, the pipeline crashed at the NEXT module — each fix reveals the next broken seam. Normal for multi-module refactors.

**Running checklist approach:**
1. Import check: `python -c "import src.module; print('OK')"`
2. Function call check: test with minimal fixture input
3. Full pipeline check: run end-to-end until all stages complete
4. Repeat from step 1 for next failing module

Final verification ran the full analysis pipeline on a real DXF file and confirmed both JSON and Markdown reports were generated correctly.

## Lessons for Future Audits

- **Import wiring audit should be Phase 1** in multi-file code audits — broken imports cascade into false positives downstream
- **Signature mismatch is silent at import time** — functions exist with wrong parameters, so `import X` succeeds but calling fails at runtime. Need to verify call sites match actual signatures
- **Dataclass vs dict confusion** is a common refactor artifact — when modules evolve from passing dicts to using typed dataclasses, callers often lag behind
- **Library version drift** is invisible until runtime — always check installed versions against code assumptions during audit
