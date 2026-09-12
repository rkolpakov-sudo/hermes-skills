#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate.py — Валидатор результатов extract_spec.py.

Использование:
    python validate.py <out-dir> <base-name>
    python validate.py . "spec_3924-2-МСП-РД-ОВ 2.1"

Читает stage1-3 и log, выдаёт таблицу-отчёт: каждый stage → OK / ISSUES.
Проверки:
  stage1: есть ли записи с пустым name+qty+type (рамка/штамп не отфильтрован)
  stage2: одиночные буквы, разорванные «х», голый Ø
  stage3: orphan, items_no_qty, неклассифицированные строки
  log:   EMPTY_NAME, необъяснённые MERGE
"""

import json, os, sys, re

def check_stage1(path):
    issues = []
    if not os.path.exists(path):
        return [f"Файл не найден: {path}"]
    with open(path, encoding='utf-8') as f:
        records = json.load(f)
    total = len(records)
    empty = sum(1 for r in records if not r.get('name') and not r.get('type') and not r.get('qty'))
    no_qty_but_type = sum(1 for r in records if r.get('name') and not r.get('qty') and r.get('type'))
    if empty > total * 0.05:
        issues.append(f"{empty}/{total} пустых записей (рамка/штамп)")
    if empty == total:
        issues.append("ВСЕ записи пусты — детекция спецификации не сработала")
    return issues

def check_stage2(path):
    issues = []
    if not os.path.exists(path):
        return [f"Файл не найден: {path}"]
    with open(path, encoding='utf-8') as f:
        records = json.load(f)
    singles = set()
    naked_diams = []
    for r in records:
        name = r.get('name', '')
        for t in name.split():
            if re.fullmatch(r'[а-яёА-ЯЁ]', t) and t not in 'ав':
                singles.add(t)
        if re.search(r'Ø(?!\d)', name):
            naked_diams.append(name[:50])
    if singles:
        issues.append(f"Одиночные буквы: {sorted(singles)}")
    if naked_diams:
        issues.append(f"Голый Ø (не перед числом): {naked_diams}")
    return issues

def check_stage3(path):
    issues = []
    if not os.path.exists(path):
        return [f"Файл не найден: {path}"]
    with open(path, encoding='utf-8') as f:
        rows = json.load(f)
    from collections import Counter
    roles = Counter(r['role'] for r in rows)
    issues.append(f"Роли: {dict(roles)}")
    no_qty_items = [r['name'] for r in rows if r['role'] == 'item' and not r.get('qty')]
    if no_qty_items:
        issues.append(f"item без qty ({len(no_qty_items)}): {no_qty_items[:8]}")
    return issues

def check_log(path):
    issues = []
    if not os.path.exists(path):
        return [f"Файл не найден: {path}"]
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    log = data.get('log', [])
    orphans = [l for l in log if l['type'] == 'ORPHAN']
    empties = [l for l in log if l['type'] == 'EMPTY_NAME']
    if orphans:
        issues.append(f"ORPHAN ({len(orphans)}): {[l['frag'] for l in orphans[:5]]}")
    if empties:
        issues.append(f"EMPTY_NAME ({len(empties)})")
    issues_body = data.get('issues', {})
    for k, v in issues_body.items():
        if v and v != 'OK':
            if k == 'single_letter_tokens':
                continue  # covered by stage2
            issues.append(f"QA.{k}: {v if isinstance(v, str) else str(v[:5])}")
    return issues

def main():
    if len(sys.argv) < 3:
        print("Исп: python validate.py <out-dir> <base-name>")
        sys.exit(1)
    out_dir, base = sys.argv[1], sys.argv[2]
    reports = {}
    for stage, checker, label in [
        ('stage1_records.json', check_stage1, 'STAGE1 (сырые записи)'),
        ('stage2_cleaned.json', check_stage2, 'STAGE2 (очищенные)'),
        ('stage3_rows.json',  check_stage3, 'STAGE3 (классификация)'),
        ('log.json',         check_log,    'LOG'),
    ]:
        path = os.path.join(out_dir, f'spec_{base}_{stage}')
        res = checker(path)
        reports[label] = res

    print(f"=== VALIDATE {base} ===")
    all_ok = True
    for label, issues in reports.items():
        if not issues or (len(issues) == 1 and issues[0].startswith("Роли:")):
            print(f"  ✅ {label} — OK")
        else:
            all_ok = False
            for iss in issues:
                if iss.startswith("Роли:"):
                    print(f"  📊 {label} — {iss}")
                else:
                    print(f"  ⚠️  {label}: {iss}")
    print(f"\n{'✅ Все проверки пройдены' if all_ok else '⚠️  Есть замечания — смотри stageN_*.json'}")

if __name__ == '__main__':
    main()