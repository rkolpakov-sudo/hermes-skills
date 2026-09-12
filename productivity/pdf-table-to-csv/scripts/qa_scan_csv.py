#!/usr/bin/env python3
"""QA scanner for a produced spec/CSV. Flags residual extraction artifacts.

Usage:  python qa_scan_csv.py path/to/output.csv [name-column-index]
        (name-column-index defaults to 1, i.e. the "Наименование" column)

Exit code 0 = clean, 1 = findings. Prints each finding as  row#  kind  -> value.
"""
import csv, re, sys

def scan(path, name_col=1):
    issues = []
    with open(path, newline='', encoding='utf-8-sig') as f:
        reader = list(csv.reader(f))
    header = reader[0]
    for ri, row in enumerate(reader[1:], start=2):
        if ri >= len(row):
            row = row + [''] * (len(header) - len(row))
        name = row[name_col] if name_col < len(row) else ''
        if not any(cell.strip() for cell in row):
            continue  # fully blank
        if '  ' in name:
            issues.append((ri, 'double_space', name))
        if re.search(r'\s[.,:;]', name):
            issues.append((ri, 'space_before_punct', name))
        if re.search(r'[х=]\s*$', name):
            issues.append((ri, 'dangling_separator', name))
        if re.search(r'Ø(?!\d)', name):
            issues.append((ri, 'naked_symbol', name))
        if re.search(r'х \d', name):
            issues.append((ri, 'h_space_digit', name))
        if not name.strip():
            issues.append((ri, 'empty_name', ' '.join(row)))
    return header, issues

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    path = sys.argv[1]
    name_col = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    header, issues = scan(path, name_col)
    print(f"Columns: {header}")
    if issues:
        print(f"\n{len(issues)} finding(s):")
        for ri, kind, val in issues:
            print(f"  row {ri}  {kind:20}  {val!r}")
        sys.exit(1)
    print("\nCLEAN — no residual artifacts found.")
    sys.exit(0)

if __name__ == '__main__':
    main()
