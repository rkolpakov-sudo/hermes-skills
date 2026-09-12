# RFQ Pipeline — project map (C:\Projects\RFQ_Pipeline)

Canonical spec: `RFQ_PIPELINE_PLAN.md` (root; §13 = жёсткие контракты шагов, §11 = статусы фаз). Status 2026-09-09: P0–P4 done, **P5 done (оркестратор `rfq_pipeline.py` s1–s6 + прогон под локальной моделью 25/25)**, P6 pending. Пул скиллов `rfq/*` — СОСТАВ НА СОГЛАСОВАНИИ, не создавать (правило пользователя).

## Настройки агента (единый конфиг + Control Center — добавлено 2026-09-09)

- **`~/.hermes/rfq/settings.json`** — единый источник изменяемых параметров (никаких захардкоженных адресов/путей/порогов в dev-скриптах). Читается ВСЕМИ скриптами через `dev/rfq_settings.py` (schema-driven: load/save/валидация; `direction_names` = карта pricer-категория → имя направления; `suppliers` = направление → emails пула; cron_*; pricer-пути; пороги матчера score_min/jaccard_min/type_weight). Реестр проектов — `~/.hermes/rfq/projects.json` (отдельный файл, синхронизируется). Данные вне кода → пользователь меняет без работы с кодом.
- **`C:/Projects/RFQ_Pipeline/editor/`** — локальный веб Control Center (`editor_server.py` на stdlib http.server, порт 8791, только localhost, CORS для панели предпросмотра): вкладки Сводка/Проекты/Почта/Шаблон письма/Пул поставщиков/Сайты категорий/Матчер (живой тест!)/Крон+Lark/Пути; кнопки «проверить ящики IMAP», «запустить cron сейчас», «тест Lark», «тест матчера»; регистрация проектов; переименование направлений (переносит ключ пула); drag&drop сайтов категорий. GET/PUT /api/config, GET /api/dashboard|projects|offers|directions|sites|pathinfo. Данные pricer — только чтение (см. references/pricer-classification-reuse.md §3 про изоляцию).
- **`~/.hermes/rfq/site_overlay.json`** — пользовательские назначения сайтов категориям (база = таксономия pricer read-only); `taxonomy/` = снимок таксономии (categories_and_sites.yaml, matching_rules.yaml, user_overlay.yaml — оверлей БЕЗ правки pricer).
- Cron-джоба `rfq-mail-poll` id `adb2bebf4a25` (`*/30 8-20 * * 1-5`); изменение расписания через Control Center применяет к реальной джобе (`hermes cron edit/pause/resume`).

## Верификация (обязательна после изменений)
- `python dev/rfq_selfcheck.py` — 25 детерминированных проверок с захардкоженными эталонами (не зависят от модели): матчер-адверсариал, 446 строк, 425/21, Вентиляция 306/Сантехника 104 + 0 вент, sent_log 4/4, 2 оффера по 9, 7 перенесено/2 ответа, максимумы [45.5,70,78,99,112,140,58], rfq_state s1–s6 done.
- `python dev/isolation_check.py` — хэши 8 файлов pricer до/после прогона (классификация+selfcheck+settings) — PASS = pricer не изменён.
- `TEST_RUNBOOK.md` — механический перепрогон (команды + ожидания). `dev/test_send_reply.py` — имитация ответа поставщика (r.kolpakov→exontib).

## Pipeline (dev-скрипты, детерминированные, запуск venv pricer где есть approach_relevance/reportlab)

| Шаг | Скрипт (C:\Projects\RFQ_Pipeline\dev\) | Контракт |
|---|---|---|
| 1 PDF→спека | `extract_spec.py` (из скилла spec-pdf-csv) + `rows_to_xlsx.py` | → `01_спецификация_исходная.xlsx` (полный отчёт; работы/заголовки живут ТОЛЬКО тут) |
| 2 Классификация | `rfq_classify_pricer.py` (движки pricer, см. references/pricer-classification-reuse.md) | `classified_pricer.json` {classified[category/subname/source], manual}; порядок правил: duct → vent_fan → vent_finished → vent_valve → plumbing_override → duct_shape → graph |
| 3 Разбивка | `split_by_category.py` | `02_разбивка_по_направлениям/<Направление>.xlsx` (только товары) + `Ручная_классификация.xlsx` |
| 4 Рассылка | `send_rfq_test.py` (+гейт подтверждения) | тема `Запрос КП: <Направление> — <Проект>`, вложение = спека; лог `03_запросы_КП/sent_log.json` (sent_at) |
| 5 Сбор | `rfq_mail_collect.py` (крон-обёртка ~/.hermes/scripts/rfq_mail_poll.py) | фильтр «Re: Запрос КП: …», реестр ~/.hermes/rfq/projects.json, вложения → `04_ответы_поставщиков/<проект>_<направление>_<sender>_<время>/`, `offer_<поставщик>.json`, курсор `collect_cursor.json`, тихий при пустоте |
| 5.1 Lark | `rfq_notify_lark.py` | outbound Feishu API (creds ~/.hermes/.env, HOME_CHANNEL); никаких bridge-демонов/state.db |
| 5.2 КП→цены | `parse_offer_pdf.py` (fitz find_tables) + `rfq_match_offer.py` | матчер: product_words (approach_relevance) + поклассовые параметры diam/b/size; конфликт класса с обеих сторон = REJECT |
| 5.3 Заполнение | `rfq_price_fill.py` | `05_цены/<Направление>_с_ценами.xlsx` (колонки спеки + Статус «запрос отправлен/получен ответ от поставщика/цена перенесена» + «КП от» + «Цена: <поставщик>»×N + «Цена принята»=МАКС + «Источник цены») + `Сводное_сравнение_КП.xlsx` + fill_report.json; оффер→направление по максимуму успешных матчей; оригиналы 01/02 НЕ трогаются |

## Ключевые факты/правила (решения пользователя)
- Только товары (qty|component) в спеках направлений; работы/заголовки — только в 01 (финальный отчёт).
- Дубли позиций между направлениями допустимы; при нескольких ценах на позицию «Цена принята» = максимум (колонки поставщиков сохраняются).
- Цены заполняются ТОЛЬКО в отдельный выходной файл со статусами — никогда в исходную спецификацию.
- Неклассифицированные → Ручная классификация + ask-режим (отдельный пул, отложен).
- Пользователь: не предлагать ему проверять почту/файлы самому (доступ есть у агента); тесты финальной реализации — его.

## Проверено на реальном проекте (Одинцово_вент17.07, 72МБ PDF)
- 249 стр., спеки на стр. 37–51, ~20 таблиц с нумерацией-сбросами. 446 строк → классификация 425/446 = 95% (после слоёного порядка); Сантехника 104 (вент-строк 0), Вентиляция 306, Изоляция 9, Инструменты 6, manual 21.
- Почтовый контур: exontib (отправка/сбор) ↔ r.kolpakov (тест-получатель); КП-ответы ТС/ИзолТех распознаны → 7 «цена перенесена»/2 «получен ответ»; крон rfq-mail-poll активен.

## Pitfalls (найдены и проверены; детали — в плане §11 статусах)
- **Изоляция от pricer**: GraphEngine.build() ПИШЕТ в переданную БД (CREATE/ALTER/WAL) — классификатору подавать свежую копию (~/.hermes/rfq/work/), sqlite-чтения через `mode=ro` URI, см. references/pricer-classification-reuse.md §3. Проверка: isolation_check.py.
- **Web UI (editor/index.html)**: async-рендер вкладок — исключения в async-функциях НЕ ловятся try/catch (нужен .catch + window.onerror/unhandledrejection, иначе «рендерится только футер» и выглядит как мёртвая страница); nav-кнопки пересоздаются при каждом render — координаты кликов панели предпросмотра устаревают (проверять через URL-хэш #tab=…, добавлен hashchange); кириллица в curl -d уходит cp1251 (сервер должен пробовать utf-8→cp1251→cp866); set-значения не JSON-сериализуемы (конвертер в endpoint); himalaya config.toml — структура `[accounts.<name>]`, парсить через tomllib.
- Модель-агента меняли (frontier → локальная qwen lmstudio): ядро детерминированное → результаты идентичны (25/25); перепрогон проверяет воспроизводимость агентских действий. Локальный браузер (не Chromium) не даёт screenshot/DOM — для визуальной проверки веб-UI использовать панель предпросмотра Hermes + curl API, не browser_exec local.
- reportlab: Type1-шрифты БЕЗ кириллицы («IIIIII») — регистрировать TTF (C:/Windows/Fonts/arial.ttf) в FontFamily.
- himalaya MML: атрибуты filename/name в кавычках; путь as_posix (backslash ломает); account-флаг после подкоманды; русские имена папок Gmail; attachment download → ~/Downloads; delete без `--folder sent` = INBOX.
- Матчер: «N мм» при b= — толщина, не диаметр (иначе «9» маскирует diam-конфликт); b= матчить по несхлопнутому lower (схлопывание убивает \b); «под/для трубы 6,35» без p-нотации — диаметр (дробные числа); tie по score между офферами — собирать ВСЕ совпадения по строке, максимум по ним.
- Омонимия классификации: «Пластиковый диффузор» (пластик), «Вентилятор КРОВ…-ДУ400» (ДУ в марке), вент-клапаны ДК/ОК/ОГ → слои вент-оборудования ДО plumbing-override.
