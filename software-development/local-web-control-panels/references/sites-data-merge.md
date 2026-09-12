# Donor catalog merge: sites per category (Pricer Vision → RFQ Control Center)

Instance: RFQ Control Center «Сайты категорий» tab, `editor/editor_server.py`
`sites_data()`. Lesson generalized under SKILL.md «Donor catalog lists».

## Problem observed (user report, verbatim)
«Пожарная безопасность (fire_safety)… Изоляция (insulation)… Не имеют принадлежащих
доменов, хотя в pricer vision бд есть! Проведи инспекцию.»

## Root cause
`sites_data()` built the base list ONLY from the taxonomy snapshot
`~/.hermes/rfq/taxonomy/categories_and_sites.yaml`:
- `fire_safety`, `tools_general` — present in YAML `category_map` but with NO `sites:`
  section (only keywords) → empty list;
- `insulation` — absent from the YAML entirely.
Their sites existed only in the donor DB via the join
`product_types → product_sites → sites`.

## Donor schema (pricer.db, read-only via `file:...?mode=ro`)
```
sites:          [id, name, base_url, group_name, source, created_at]
product_sites:  [product_type_id, site_id, priority, consecutive_failures]
product_types:  [id, name, category, keywords, created_at, source]
categories:     [id, name, priority, focus, source, created_at]
```

## Working query (category → dedup sites → best numeric priority)
```sql
SELECT pt.category, s.name, MIN(ps.priority) mp
FROM product_types pt
JOIN product_sites ps ON ps.product_type_id = pt.id
JOIN sites s ON s.id = ps.site_id
WHERE s.name IS NOT NULL
GROUP BY pt.category, s.name
```

## Priority mapping (taken from donor source, not assumed)
`src/graph_engine.py` line ~1160: `priority = {"primary": 0, "secondary": 1}.get(p, 2)`
→ numeric `product_sites.priority` decodes as **0 = primary, 1 = secondary, else (2+) =
all**. DISTINCT values observed: 0, 1, 2.

## Dirty DB values found (normalize on read, don't propagate)
- `https://proconsim.ru` (plumbing_heating) — protocol prefix
- `вентиляция-топ (ventilyacia-top.ru)` (electrical) — annotation in parens
Normalizer: `re.search(r"(?:https?://)?([a-z0-9а-яё.-]+(?:\.[a-zа-яё]{2,}))", site)` then
`.rstrip(".")`. Lowercase + strip before matching.

## Result after fix (read-back, /api/sites)
8 categories all populated: fire_safety=5, insulation=15, tools_general=16,
instruments_automation=16, plumbing_heating=20, cables=9, electrical=6,
ventilation_climate=8. YAML ∪ DB dedupe keeps best priority per site.

## Sources of truth ordering for base lists
1. donor YAML taxonomy (subcategory sites),
2. donor DB join (categories the YAML misses),
3. user overlay (assignments) + hidden lists — applied last, never written to donor.
Also seed `base` with every `categories.id` row so YAML-absent categories render.
