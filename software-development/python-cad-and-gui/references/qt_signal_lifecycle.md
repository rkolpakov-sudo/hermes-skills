# PySide6 Qt Signal Lifecycle Management

## The Problem: "Signal source has been deleted"

When a QObject that owns a Signal is garbage-collected while receivers still hold references, or when the signal's internal receiver list contains deleted objects, Qt raises `RuntimeError: Signal source has been deleted`. This is especially common in pytest test suites where fixtures create and destroy widgets between tests.

## Root Causes (from VDAS debug session)

1. **Missing `_QObject.__init__(self)`** — If a QObject subclass uses aliased imports (`from PySide6.QtCore import QObject as _QObject`) and forgets to call the parent constructor, ALL signal emits crash with "Signal source has been deleted" even though the object is clearly alive. PySide6 also reports: `libshiboken: '__init__' method of object's base class (MyClass) not called`. **This is the most common cause.**

2. **Test objects destroyed between tests** — Each test creates WallTool/MainWindow instances; when the next test starts, Qt's event loop may still try to deliver pending signals from destroyed objects.

3. **Signal emission after object deletion** — WallTool emits `wall_created.emit()` in mouse_press handlers; if MainWindow (the receiver) is already destroyed, this crashes.

## The Fix Pattern

### 1. QObject Subclass: Call parent __init__ AND add cleanup() with receiver loop

```python
from PySide6.QtCore import QObject as _QObject, Signal as _QtSignal

class WallTool(_QObject):
    wall_created = _QtSignal(float, float, float, float)

    def __init__(self, canvas, renderer):
        _QObject.__init__(self)  # CRITICAL — omitting this crashes ALL signals
        self.canvas = canvas
        self.renderer = renderer

    def cleanup(self) -> None:
        """Disconnect all signals and release references BEFORE deletion."""
        try:
            for receiver in list(self.wall_created.receivers()):
                self.wall_created.disconnect(receiver)  # disconnect ONE at a time
        except Exception:
            pass
        # Release attribute refs — use ACTUAL attribute names (canvas, not _canvas)
        self.canvas = None    # type: ignore[assignment]
        self.renderer = None  # type: ignore[assignment]
```

### 2. QMainWindow: Override closeEvent with receiver loop (NOT bare .disconnect())

Calling `.disconnect()` without arguments on PySide6 raises "Failed to disconnect (None)". Always enumerate receivers first:

```python
def closeEvent(self, event):
    if self._wall_tool is not None:
        try:
            for r in list(self._wall_tool.wall_created.receivers()):
                self._wall_tool.wall_created.disconnect(r)
        except Exception:
            pass
        try:
            self._wall_tool.cleanup()
        except Exception:
            pass
    event.accept()
```

### 3. Test Class: Per-Test Teardown with teardown_method

```python
class TestWallTool:
    _refs = []          # Keep objects alive during test execution
    _last_tool = None   # Track most recent tool for teardown

    def _register_tool(self, tool):
        self._last_tool = tool
        self._refs.append(tool)

    def teardown_method(self):
        """Disconnect signals after EACH test — not just at class end."""
        try:
            if self._last_tool and hasattr(self._last_tool, "cleanup"):
                self._last_tool.cleanup()
        except Exception:
            pass
        self._last_tool = None

    @classmethod
    def teardown_class(cls):
        for obj in cls._refs:
            try:
                if hasattr(obj, "cleanup"):
                    obj.cleanup()
            except Exception:
                pass
        cls._refs.clear()
```

## Key Rules

1. **Always call the QObject parent `__init__`** — even with aliased imports (`_QObject.__init__(self)`). This is the #1 cause of "Signal source has been deleted" crashes that are actually about missing constructor calls, not lifecycle issues.
2. **Disconnect one receiver at a time via `.receivers()` loop** — bare `.disconnect()` raises warnings on PySide6.
3. **Use actual attribute names in cleanup()** — `self.canvas = None`, not `self._canvas = None`.
4. **Always disconnect signals BEFORE the emitting object is garbage-collected.** Use `cleanup()` on QObject subclasses and call it from both test teardowns AND widget closeEvent handlers. Never rely on Python GC alone to clean up Qt signal connections — the event loop may still reference destroyed objects.
