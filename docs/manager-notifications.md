# Уведомления менеджеру

Когда агент передаёт диалог человеку, служебный бот Plumo пишет менеджеру этого бизнеса в личный Telegram. У каждого бизнеса свой подтверждённый чат; общего чата для всех бизнесов (`TELEGRAM_MANAGER_CHAT_ID`) больше нет.

## Привязка

1. Оператор в кабинете: «Интеграции» → «Уведомления менеджеру» → «Получить ссылку для менеджера». Backend создаёт одноразовый код на 15 минут; в БД только его SHA-256, сам код показывается один раз.
2. Менеджер открывает ссылку `t.me/<бот>?start=plumo_mgr_<код>` и нажимает «Запустить» (или отправляет боту команду `/start plumo_mgr_<код>`).
3. Telegram доставляет обновление на `POST /api/v1/webhooks/telegram-manager`. Подлинность — заголовок `X-Telegram-Bot-Api-Secret-Token`, HMAC от `CHANNEL_SECRET_KEY`. Код находит свой бизнес, чат сохраняется как кандидат, код гаснет. Принимаются только личные чаты людей.
4. Оператор видит имя кандидата и нажимает «Подтвердить этот чат». После commit бот отправляет контрольное сообщение; результат (`sent` / `failed` / `rejected`) виден в кабинете.

Chat id, введённый в форму, получателем не становится: его можно получить только из подлинного обновления служебного бота. Бизнес берётся из сессии оператора или из кода, никогда из тела запроса.

## Состояния

| `status` | Что значит |
|---|---|
| `not_configured` | Получателя нет. Задание уведомления закрывается с `recipient_not_configured`; о передаче менеджер узнаёт только из кабинета |
| `waiting_code` | Код выдан, менеджер ещё не нажал «Запустить» |
| `awaiting_confirmation` | Чат прислал код и ждёт подтверждения оператором |
| `ready` | Уведомления уходят в подтверждённый чат |
| `needs_attention` | Telegram отклонил отправку (бот заблокирован, чат удалён). Следующая успешная отправка снимает состояние |

Смена менеджера: новая ссылка не трогает текущего получателя. Он получает уведомления, пока новый чат не подтверждён. Отключение удаляет запись; ожидающие уведомления никуда не отправляются.

## Отправка и повторы

Передача и задание `notify_handoff` создаются в одной транзакции: откат передачи не оставляет уведомления, а остановленный worker его не теряет — задание ждёт в таблице. Повтор входящего события не создаёт второе уведомление: одно задание на передачу (уникальный индекс).

Состояние хранится на передаче (`notify_status`, миграция 014) и видно в карточке диалога:

| Состояние | Когда | Что дальше |
|---|---|---|
| `queued` | создано или ждёт повтора | worker отправит |
| `sending` | записано до вызова Telegram | — |
| `sent` | Telegram принял сообщение (не «прочитано») | кабинет пишет «Менеджер уведомлён» только теперь |
| `queued` снова | нет соединения до отправки, 429 | повтор с паузой; для 429 — не меньше `retry_after`; ограниченное число попыток, затем `failed` |
| `failed` | Telegram отказал (бот заблокирован, чат удалён) или попытки кончились | получатель → «требует внимания»; оператор может «Уведомить ещё раз» |
| `unknown` | запрос ушёл, а ответа нет; 5xx; ответ без квитанции; worker упал между `sending` и ответом | автоповтора нет; оператор выбирает «Менеджер получил» или «Уведомить ещё раз» |
| `cancelled` | у бизнеса нет подтверждённого получателя | «внешнее уведомление не настроено» |

### Ошибки и повторы

| Ответ Telegram / событие | Запрос дошёл? | Состояние | Автоповтор | Тест |
|---|---|---|---|---|
| квитанция `ok` с `message_id` | да | `sent` | — | `test_receipt_means_sent` |
| нет соединения (`ConnectError`, `ConnectTimeout`, `PoolTimeout`) | нет | `queued` | да, с паузой | `test_no_connection_is_safe_to_repeat`, `test_telegram_failure_is_retried_until_it_works` |
| 429 | нет (Telegram отклонил) | `queued` | да, не раньше `retry_after` | `test_429_is_repeated_no_sooner_than_telegram_asks`, `test_rate_limit_waits_as_long_as_telegram_asks` |
| попытки кончились | — | `failed` | нет | `test_notification_gives_up_after_the_last_attempt` |
| 5xx | неизвестно | `unknown` | **нет** | `test_5xx_after_sending_is_unknown_not_repeated` |
| запрос ушёл, ответа нет (read timeout) | неизвестно | `unknown` | нет | `test_read_timeout_after_sending_is_unknown`, `test_no_answer_after_sending_is_unknown_and_not_repeated` |
| ответ без квитанции | неизвестно | `unknown` | нет | `test_answer_without_a_receipt_is_unknown` |
| worker упал после `sending` | неизвестно | `unknown` | нет | `test_worker_that_died_mid_send_leaves_unknown_not_a_second_send`, `test_crashed_send_is_unknown_after_restart_not_sent_twice` |
| 400/401/403: чат удалён, бот заблокирован, токен отозван | да, отказ | `failed`, получатель → `needs_attention` | нет | `test_refusal_is_final`, `test_refusal_is_not_retried`, `test_rejected_delivery_needs_attention_until_a_send_works` |
| нет подтверждённого получателя / отключён | не отправлялось | `cancelled` | нет | `test_business_without_recipient_is_not_notified_anywhere`, `test_disconnected_recipient_gets_the_waiting_notification_nowhere` |
| повтор того же задания | — | без изменений | новой отправки нет | `test_redelivered_job_sends_nothing_more`, `test_one_notification_job_per_handoff` |
| поздний ответ старой попытки после ручного решения | — | решает новое поколение | — | `test_late_result_of_old_attempt_cannot_overwrite_a_manual_retry`, `test_canonical_notification_ignores_an_older_attempt_result` |

Ручные действия (`retry`, `mark_sent`, `mark_failed`) повышают поколение уведомления: результат старой попытки, пришедший позже, ничего не меняет.

**Политика 5xx.** Старое ТЗ предполагало повтор при 5xx. Объединённая реализация считает 5xx после отправки неопределённой доставкой: Telegram мог принять сообщение. Решение PJ-02: оставить `unknown` без автоповтора. Двойное уведомление хуже, чем ручное решение оператора. Пересмотр — только по решению тимлида; слепой повтор не включать.

Exactly-once не обещаем: двойное уведомление возможно, только если человек сам выбрал «Уведомить ещё раз» для `unknown`. Сообщение, которое Telegram уже принял, отменить нельзя. Очередь уведомлений не задерживает ответы клиенту: у неё свой ключ порядка.

Ссылка «Открыть диалог» в уведомлении ведёт на `<DASHBOARD_URL>/dashboard?conversation=<id>`; без входа страница отправляет на вход и возвращает к тому же диалогу. Диалог другого бизнеса отвечает «не найден».

Ручное решение: `POST /api/v1/handoffs/{id}/notification/resolve` с `action` = `retry` / `mark_sent` (только `unknown`) / `mark_failed`; чужая передача — 404.

## API

Кабинет, только свой бизнес; через BFF `/api/plumo/*`:

| Метод | Путь | Результат |
|---|---|---|
| GET | `/api/v1/manager-notifications` | состояние, получатель, кандидат |
| POST | `/api/v1/manager-notifications/link` | новый код: `command`, `link` (если задан `TELEGRAM_BOT_USERNAME`) |
| POST | `/api/v1/manager-notifications/confirm` | подтвердить кандидата; 409 `no_candidate`, если его нет |
| POST | `/api/v1/manager-notifications/disconnect` | отключить; 404 `recipient_not_found`, если нечего |

## Два API, один получатель

| API | Кто использует | Состояния |
|---|---|---|
| `/api/v1/manager-notifications` | кабинет («Интеграции») | `not_configured`, `waiting_code`, `awaiting_confirmation`, `ready`, `needs_attention` |
| `/api/v1/manager-recipient` | совместимость со старым Dashboard API | `not_configured`, `awaiting_confirmation` (= `waiting_code` и `awaiting_confirmation`), `ready`, `attention` (= `needs_attention`) |

Оба читают и меняют одну строку `manager_recipients` и считают состояние одной функцией `status_of`. Подтверждение и отключение в совместимом API выполняет тот же `ManagerRecipients`. Любое изменение повышает `version`, поэтому устаревшая вкладка старого API получает 409. Оба webhook служебного бота принимают оба формата кода (`plumo_mgr_…` и `mgr_…`). Проверка: `test_both_manager_apis_report_the_same_state_through_a_binding`.

## Настройка служебного бота

Единственный рекомендуемый способ — один служебный бот, переменные `TELEGRAM_BOT_*`, webhook `/api/v1/webhooks/telegram-manager`:

```bash
# backend/.env (реальные значения — только в .env стенда, не в Git)
HANDOFF_PROVIDER=telegram
TELEGRAM_BOT_TOKEN=<токен служебного бота из @BotFather>   # не токен бота бизнеса
TELEGRAM_BOT_USERNAME=<имя бота без @>
CHANNEL_SECRET_KEY=<случайная строка>                        # из неё выводится секрет webhook
PUBLIC_BASE_URL=https://<публичный адрес API>
DASHBOARD_URL=https://<адрес кабинета>                        # ссылка «Открыть диалог»

cd backend && .venv/bin/python -m app.manager_bot          # setWebhook, печатает имя бота
.venv/bin/python -m app.manager_bot --check                # куда сейчас смотрит webhook
```

Один токен не используется сразу для служебного бота и бота бизнеса.

Совместимость. `MANAGER_BOT_TOKEN` и `MANAGER_BOT_USERNAME`, если заданы, имеют приоритет над `TELEGRAM_BOT_*`: так продолжает работать стенд, настроенный по старой инструкции Dashboard. На новом стенде их не задавать. `MANAGER_WEBHOOK_SECRET` нужен только прежнему webhook `/api/v1/webhooks/manager-telegram`, который ставит `python -m app.setup_manager_bot`. Telegram держит один webhook на бота, поэтому на стенде работает только один из двух адресов; оба обрабатывают привязку одинаково. Отправка уведомлений, готовность в кабинете и ссылка для менеджера используют один и тот же токен и имя (`service_bot_token`, `service_bot_username`).

Миграции: `013_manager_recipients`, `014_handoff_notify_status`. Существующие бизнесы после неё в состоянии `not_configured`, пока оператор не привяжет менеджера.

## Проверки

`backend/tests/integration/test_handoff_notify.py`: откат, повтор задания, остановленный worker, 429 с `retry_after`, ограниченные повторы, неоднозначный таймаут, worker упал посреди отправки, ручное решение, чужой бизнес. `backend/tests/integration/test_manager_recipients.py`: полный путь через API, изоляция двух бизнесов, чужая сессия, просроченный и повторный код, поддельное и неподписанное обновление, групповой чат, бизнес без получателя, смена и отключение при ожидающем уведомлении, `needs_attention`. Frontend: `tests/manager-notifications.test.mjs`, whitelist прокси в `tests/api-proxy.test.mjs`.

`backend/tests/unit/test_telegram_handoff_provider.py`: разбор ответов Telegram (квитанция, нет соединения, 429, 5xx, read timeout, нет квитанции, отказ). `backend/tests/integration/test_merge_manager_contract.py`: два API, одно состояние на всём пути привязки, поколение уведомления.

## Не проверено на staging

Пункты 4–5 PJ-02 вживую не выполнены: staging нет. Нужно от тимлида: стенд с публичным HTTPS-адресом API и кабинета, отдельная БД, служебный бот и два тестовых бизнеса с ботами. План проверки:

1. Настроить бота по разделу выше, привязать менеджера каждому бизнесу.
2. Остановить worker → клиент просит менеджера → передача видна в кабинете, уведомление `queued`.
3. Запустить worker → уведомление приходит только менеджеру своего бизнеса; второй бизнес ничего не получает.
4. Открыть ссылку «Открыть диалог» в чистом браузере → вход → тот же диалог.
5. Отказы имитировать на изолированном стенде, не трогая бота реальных клиентов: неверный токен (отказ → `needs_attention`), заблокированный бот, остановленный worker во время `sending` (→ `unknown`, затем `retry` / `mark_sent` / `mark_failed`).
