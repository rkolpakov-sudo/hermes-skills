# Budget Adjustment Early Exit Bug (v3.1, 2026-07-15)

**Bug:** `loop_recommend_next()` строка 1090-1097 — early return при успешном вердикте не включал `budget_adjustment` в ответ. Downstream код ожидал это поле → crash с `action=None`.

## Reproduction

```python
# Только с verify_config, который возвращает verdict='pass'
init = loop_init(task='T', max_iterations=20, strategy='adaptive',
    verify_config={'mode': 'command', 'command': 'echo ok'})

# 3+ итерации plan/act/check → verify → recommend
run({'mode':'verify','id':lid})       # verdict='pass' активирует early exit
rec = run({'mode':'recommend','id':lid})
assert rec.get('budget_adjustment',{}).get('action') is not None  # FAIL: None
```

Без `verify_config` баг не проявлялся — self-judge возвращал `continue`, код доходил до строки 1128-1132 где budget_adj присваивается правильно.

## Debugging Technique (Reusable)

Когда результат через handler отличается от прямого вызова функции:

1. **Прямой вызов** → правильный результат ✓
2. **Через handler** → неправильный ✗  
3. **Вывод:** либо handler dispatch вызывает другую функцию, либо промежуточные операции в session изменяют состояние (journal/graph), которое влияет на логику целевой функции

Конкретно здесь: `loop_verify()` записал verdict='pass' в journal → последующий `loop_recommend_next()` загрузил этот judge и ушёл в early exit path.

## Fix

```python
# Строка 1095 — добавлено:
"budget_adjustment": budget_adj,  # v3.1: include budget signal even on success
```

## Lesson

**Всегда проверяйте ВСЕ return paths на наличие обязательных полей.** Early exit ветки (особенно при успешном завершении) часто обходят финальные enrichment-блоки, которые добавляют метаданные в основной путь выполнения.
