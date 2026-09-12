# Middleware v3 Refactoring — Hard Loop Enforcement (2026-07-18)

## Фундаментальная проблема middleware v2

Middleware v2 (L4709-4776 `conversation_loop.py`) выполнял **background side-effect**: детектировал многошаговые задачи, создавал loop journal на диске, но результат выбрасывался. Модель НЕ получала loop ID → не вызывала `loop(mode='run')` → orphaned `.json`, enforcement не работал.

**Root cause:** Loop — коллаборативный инструмент. Фоновая инициализация без обратной связи с моделью бесполезна. Модель должна ВИДЕТЬ loop ID и инструкцию продолжать работу через journal.

## Архитектурное решение: Two-Phase Injection (v3)

### Phase 1 (до `_execute_tool_calls`, L4709+)
Детекция многошаговых задач + init/resume loop на диске. Результат сохраняется в `agent._loop_enforce_inject`.

### Phase 2 (после `_execute_tool_calls`, L4907+)
Инъекция assistant message в `messages[]` массив. Модель получает loop ID и инструкцию → вызывает `loop(mode='run', id=...)` на следующем turn'е.

```
Model response → tool calls detected → Phase 1: init/resume on disk
    ↓
_execute_tool_calls() — tools execute, results appended to messages[]
    ↓
Phase 2: inject "[LOOP-ENFORCE: Loop autoed — id=XXX...]" into messages[]
    ↓
Next API call sees injection → model calls loop(mode='run', id='XXX')
```

## Исправленные баги Middleware v3

### BUG MIDDLEWARE-1 (CRITICAL): Результат init выбрасывался
**ДО:** `loop_handler(mode='init')` создавал journal, но результат не сохранялся. `_enforced_loop_id = None` → Phase 2 никогда не срабатывал.
**ПОСЛЕ:** Парсит JSON-ответ init и извлекает `id`. Если parse failed — fail-open без краша dispatch chain.

### BUG MIDDLEWARE-2 (CRITICAL): `_last_user_content` не определён
**ДО:** `agent._last_user_content[:200]` обращался к несуществующему атрибуту. Fallback использовал `assistant_message.content` — семантически неверно для извлечения user intent.
**ПОСЛЕ:** Итерирует `reversed(messages)`, ищет последний `role="user"` message, извлекает content (поддержка и string, и list формат).

### BUG MIDDLEWARE-3 (MEDIUM): Статус resume игнорировался
**ДО:** `_loop_h({"mode": "status", "id": _lid})` читал статус journal, но результат не инжектился в контекст модели.
**ПОСЛЕ:** При resume существующего loop сохраняет `_enforced_loop_id` и передаёт в Phase 2 injection с `mode="resume"`.

### BUG MIDDLEWARE-4 (MEDIUM): Race condition на double-init
**ДО:** Два параллельных turn'а могли одновременно обнаружить отсутствие активных loop и создать два independent orphaned journal.
**ПОСЛЕ:** 
1. Dedup check: проверяет, содержит ли текущий batch tool calls уже `_auto_enforced=True` маркер
2. При init добавляет `"_auto_enforced": True` в аргументы — следующие turn'а видят этот маркер

## Исправленные баги loop_tool.py

### ROBUST-1: Atomic Journal Write (L98-L124)
**Проблема:** Прямой `open(path, 'w')` → краш процесса mid-write → corrupted JSON journal.
**Исправление:** Write to `.tmp` → `fsync()` → `rename()` (atomic on POSIX/NTFS). Fallback на прямой write если atomic path failed.

### SEC-7: Regex Path Sanitization (L381-L385)
**Проблема:** `_normalize_sig()` санитизировал только префикс "path/..." → Windows пути `C:\Users\...` и Unix `/home/...` оставались в сигнатуре, создавая false negatives при pattern detection.
**Исправление:** 5 regex паттернов покрывают все форматы путей: Windows absolute, Unix absolute, relative (`./foo`, `../bar`), tilde (`~/.hermes/...`), explicit prefix.

### PERF-1: Ancestors Cache (L413-L427)
**Проблема:** `_detect_repeated_patterns()` вызывал `_get_ancestors()` O(n²) раз внутри nested loop → worst case O(n³) на графах 50+ узлов.
**Исправление:** Pre-compute `ancestors_cache = {nid: frozenset(_get_ancestors(...)) for nid in node_ids}` → O(1) lookup per pair. Worst case O(n²).

### ROBUST-2: File Locking в cleanup (L2154-L2230)
**Проблема:** `cleanup_abandoned_loops()` сканировал и удалял файлы без защиты от concurrent sessions → активный journal мог быть удалён.
**Исправление:**
1. Advisory lock file `.cleanup.lock` через `os.O_CREAT | os.O_EXCL` — если другой session держит lock, skip gracefully
2. Double-check mtime: если файл модифицирован <60 секунд назад → skip (другой session может быть активен)
3. Clean lock release в `finally` блоке

## Точная точка внедрения в dispatch chain (`conversation_loop.py`)

| Строка | Действие |
|--------|----------|
| L4709+ | Phase 1: middleware v3 detection + init/resume |
| L4850 | `messages.append(assistant_msg)` — assistant message добавлен |
| L4857 | `_flush_messages_to_session_db()` — сохранение в БД |
| L4907 | `_execute_tool_calls()` — выполнение инструментов (mutates messages[]) |
| **L4908+** | **Phase 2: post-exec injection** — inject loop context into messages[] |
| L4930+ | Guardrail check, retry counters, next API call iteration |

## Файлы и хеши после рефакторинга

| Файл | Размер | SHA-256 (first 16) |
|------|--------|---------------------|
| `conversation_loop.py` | 320,892 bytes | `05b7ebc12efadf5b` |
| `loop_tool.py` | 101,568 bytes | `1f9377fa075bc0c0` |

## Верификация

- ✅ py_compile: оба файла syntax OK
- ✅ Middleware v3: все 6 компонентов подтверждены (Phase 1/2, task desc, dedup, inject dict, post-exec)
- ✅ Loop tool: все 4 фикса подтверждены (atomic write, regex paths, ancestors cache, lock file + mtime)
