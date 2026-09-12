---
name: deep-project-study
description: Use when asked to fully study a project/codebase.
---

# Deep Project Study (full codebase comprehension)

Use when the user asks to study a project "fully and thoroughly" (e.g. 'изучи проект полностью и досконально') and confirm understanding, or when working in an unfamiliar codebase requires a complete mental model first. User standard: confirmation must be backed by actual reading (tool output), not description; partial coverage must be stated honestly.

## Workflow

1. **Inventory** — full file list with line counts, excluding venvs and .git:
   ```bash
   find . -name '*.py' -not -path './.git/*' -not -path '*/venv/*' | xargs wc -l | sort -rn
   ```
   Total LOC sets the reading plan. If nested env dirs exist (e.g. `mineru_venv/`), add `-not -path '*/<name>/*'`.

2. **Docs and config first** — README, AGENTS.md, requirements.txt, pytest.ini, config/*.yaml, `git log --oneline -30 | cat`. Establishes purpose, stack, conventions before touching code.

3. **Core modules in priority order** — entry point (main.py) → largest/most central files → supporting modules. Files over ~2000 lines or 100K chars: `read_file` with offset/limit pagination until `truncated: false`.

4. **Batch small related files** (<~15K chars each) into one `execute_code` call to save round-trips. Verify stdout came back in full — if the result shows a truncation marker, re-read those files via direct `read_file` instead of guessing content.

5. **Track progress with todo** (inventory / core / details / report). Context compression preserves the task list; after compression continue from preserved state and do NOT re-read what is already done.

6. **Final report** — architecture map: purpose + key classes/functions per module, data flow, config/data files. Then an explicit coverage statement: which files were read line-by-line vs known only from imports/structure. Offer to finish reading the remainder. Never claim "full understanding" without having actually read everything; honest partial coverage beats a false claim.

## Pitfalls

- **Nested venv dirs pollute find/wc** — always exclude `*/venv/*` and any project-local env dir, or LOC totals are inflated by orders of magnitude (this user's projects under C:\Projects commonly contain nested venvs).
- **execute_code stdout cap (~50KB)**: batch-printing several large files loses content (result shows a truncation marker like "N lines output"). Use `read_file` pagination for anything >~30K chars; keep batched prints small and verify they came back.
- **Context compression mid-task**: long study sessions get compacted. Keep the todo list current so the preserved task list restores state; after compaction, re-check what remains from the summary instead of starting over.
- **User standard (Ruslan)**: "полностью и досконально" means actual line-by-line reading of core code + evidence-based confirmation. A plausible-sounding architecture description without having read the files is a failure for this user.

## Project maps

Condensed module maps for studied projects live in `references/` — check there before re-studying:
- `references/pricer-vision-map.md` — C:\Projects\Pricer_Vision (PySide6 price-collection app, ~23K LOC)
- `references/pricer-classification-reuse.md` — pricer detection/classification ENGINES (ductwork_calculator.is_ductwork_row слои + regex, graph classify_product_type, product_types схема БД, insulation-категория), внешний запуск через venv, проверенный слоёный порядок категоризации (95%), схема rows json extract_spec.py, pitfalls (reuse > reimplement, склейка «огнезащита», товар = qty|component). Нужно при работе с pricer-классификацией или RFQ-подобных конвейерах.
- `references/rfq-pipeline-map.md` — C:\Projects\RFQ_Pipeline (RFQ/КП конвейер: dev-скрипты шагов 1–5.3 с контрактами, правила пользователя, проверенный статус на 2026-09-09, pitfalls почты/reportlab/матчера). План-канон: RFQ_PIPELINE_PLAN.md (§13 контракты).
