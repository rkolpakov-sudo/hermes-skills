---
name: deep-codebase-study
description: "Study a whole project and confirm understanding."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [codebase-study, project-comprehension, code-reading, onboarding]
    related_skills: [code-audit, codebase-inspection]
---

# Deep Codebase Study (Project Comprehension)

When the user asks to study a project "полностью и досконально" / confirm full understanding — deliver verified comprehension backed by actual reads, not a description of intent. The final report must state what was read line-by-line vs structurally and flag anomalies found.

## When to Use
- User asks for a complete/thorough study of a codebase with confirmation of understanding
- Taking over maintenance of an unfamiliar project
- Preparing deep work on a project you have not seen before (user has many projects under C:\Projects)

## Phase 1: Recon (cheap, fast)
```bash
# Tree without .git, depth-limited
find . -maxdepth 3 -not -path './.git/*' | head -100
# Project code volume — ALWAYS exclude venvs and caches
find . -name '*.py' -not -path './.git/*' -not -path '*/venv/*' -not -path '*mineru_venv*' | xargs wc -l | sort -rn
```
Read in this order: README/AGENTS.md → configs (settings.yaml, requirements.txt, pytest.ini) → `git log --oneline -30` + `git status --short`. Docs and git state are small but reveal intent, WIP, and recent direction.

## Phase 2: Reading plan by importance
1. Entry point (`main.py`) and the "heart" module first — usually the largest file in `src/` (central loop/engine).
2. Supporting modules next, batched; GUI last (largest, least critical for core-logic understanding).
3. Tests: read `conftest.py` fully + structure via `grep -h 'def test_' tests/*.py | sort`, not every assertion.

## Phase 3: Batched reading (critical on large codebases)
Tool iteration budget is finite — one tool call per file blows it. Techniques that worked on a ~23k-line project:
- **Batch small files (<400 lines):** several `read_file` calls inside ONE `execute_code` script, printing each with a header separator. 4–6 files per call.
- **Chunk large files:** `read_file(offset=N, limit=...)` until covered; track offsets so chunks don't overlap or skip.
- For >10k-line codebases this batching is the difference between finishing and hitting "max tool-calling iterations" mid-task (observed: an unbatched study of Pricer_Vision hit that limit).

## Phase 4: Anomaly resolution
When something looks wrong (import of a missing module, file referenced but absent):
```bash
grep -rn 'module_name' --include='*.py' . | grep -v venv    # who references it?
git log --oneline --all -- path/to/file.py                   # was it ever in git?
git show HEAD:path/to/file.py                                # in HEAD but deleted from disk?
```
Classification:
- Missing from disk AND never in git → check who imports the importer. If nothing imports it, it is **dead code** — report as an anomaly (crash risk only if reachable), not a blocker.
- In git history but gone from disk → deleted without commit; check `git status`.

## Phase 5: Git state + honest coverage report
- `git status --short` — uncommitted WIP is an anomaly to surface in the report.
- Report coverage honestly: line-by-line vs structural (tests, runtime logs); offer to finish the remainder explicitly.
- Never claim "complete understanding" without having actually read; this user demands evidence via real tool output, not descriptions.

## Pitfalls
1. **Tool budget:** one call per file on a large codebase = guaranteed iteration-limit hit mid-task. Batch 4–6 files per `execute_code` call; chunk big reads with offset/limit.
2. **venv pollution in counts:** `find`/`wc` without exclusions returns thousands of dependency lines and misleads the reading plan. Always exclude `.git`, `*/venv/*`, `*mineru_venv*`, `__pycache__`.
3. **Windows/MSYS paths:** terminal runs git-bash — native tools need `C:/...` forward-slash paths; `read_file` accepts both styles.
4. **Don't claim 100% without it:** distinguish line-by-line vs structural coverage in the final report and list what remains unread.

## References
- `references/pricer-vision-architecture.md` — condensed architecture map of C:\Projects\Pricer_Vision (studied 2026-08-21): module roles, data flow, known anomalies. Reuse instead of re-reading ~23k lines; verify against git log before relying on it.
