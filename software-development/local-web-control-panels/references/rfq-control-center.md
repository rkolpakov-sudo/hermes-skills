# RFQ Control Center — working instance (2026-09-09)

Concrete deployment of the local-web-control-panels pattern.

## Files
- `C:/Projects/RFQ_Pipeline/dev/rfq_settings.py` — schema module (8 groups / ~26 fields).
  File: `~/.hermes/rfq/settings.json`; registry mirror `~/.hermes/rfq/projects.json`.
- `C:/Projects/RFQ_Pipeline/editor/editor_server.py` — server, port 8791, 127.0.0.1.
- `C:/Projects/RFQ_Pipeline/editor/index.html` — single-page dark UI, 8 tabs.
- `C:/Projects/RFQ_Pipeline/editor/Запустить_редактор_настроек.bat` — `chcp 65001`,
  `start http://127.0.0.1:8791`, then run server.

## Endpoints
GET `/`, `/api/config`, `/api/dashboard`, `/api/projects`, `/api/offers`, `/api/pathinfo`;
PUT `/api/config`; POST `/api/projects`, `/api/mail/check`, `/api/lark/test`,
`/api/cron/run`, `/api/matcher/test`; DELETE `/api/projects?name=…`.

## Tabs and data sources (all read real artifacts)
- Сводка: totals from per-project summary (rows/classified/manual/sent/offers/priced) + cfg badges.
- Проекты: registry CRUD; details from `rfq_state.json` stages, `03/sent_log.json`,
  `04/offer_*.json` (items/priced), `05/fill_report.json` (rows/filled/answered), file lists.
- Почта: himalaya account roles from settings; emails parsed from config.toml `[accounts.*]`;
  IMAP counts via `himalaya envelope list --account X --output json`.
- Шаблон письма: `body_template` textarea with {direction}/{project}/{n}/{deadline}
  placeholders + live preview; deadline = today + `deadline_days`.
- Матчер: thresholds score_min/jaccard_min/type_weight; live test calls real `rfq_match_offer.match`.
- Крон/Lark: cron_enabled/schedule/job_id; run-now via `hermes cron run <id>`;
  Lark test posts to FEISHU_HOME_CHANNEL (creds in `~/.hermes/.env`).
- Пути: pricer_project/pricer_python/overlay_file/downloads_dir + existence check.

## Settings consumed by pipeline scripts (no more hardcoding)
`send_rfq_test.py` (mode test→test_recipient / real→suppliers pool per direction,
subject_prefix, body_template, deadline_days, sender_account), `rfq_mail_collect.py`
(collect_account, own_address, downloads_dir, attachment_window_s, lark_enabled),
`rfq_match_offer.py` (score_min/jaccard_min/type_weight), `rfq_notify_lark.py`
(lark_channel_override), `test_send_reply.py` (reply_account/email).
Cron changes applied to the real hermes job only when cron fields changed
(`hermes cron edit|pause|resume <job_id>`).

## Restart recipe
Kill background server process, then:
`cd C:/Projects/RFQ_Pipeline/editor && python editor_server.py --port 8791` (background).
Health: `curl http://127.0.0.1:8791/api/config`. Selfcheck of pipeline: `python rfq_selfcheck.py`
→ 25/25 expected.
