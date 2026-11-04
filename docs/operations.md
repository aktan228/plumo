# Запуск стенда и выпуск

Как запустить актуальный `main` на staging или production: из каких частей состоит стенд, где лежат секреты, как применить миграции, проверить запуск и откатиться. Команды локальной разработки — в [dev-checks.md](dev-checks.md).

Статус на 4 ноября 2026: staging-окружения нет. Цепочка миграций и запуск API и worker на обновлённой схеме проверены локально (раздел «Проверено»), на хостинге — нет.

## Состав

```
браузер ──> Next.js: кабинет + BFF /api/plumo/*  ──X-API-Key──>  FastAPI API ──> PostgreSQL
                                                                     ▲   ▲
Telegram / Instagram ──webhook (HTTPS)───────────────────────────────┘   │
                                                   worker (python -m app.worker) ──> модель, Telegram, Instagram
```

| Часть | Запуск | Где (ориентир) | Конфигурация |
|---|---|---|---|
| Frontend и BFF | `npm ci && npm run build && npm start` (Node 22.18+) | Vercel | `PLUMO_API_URL`, `PLUMO_API_KEY`, `NEXT_PUBLIC_*` — переменные проекта Vercel |
| API | образ `backend/Dockerfile`: `alembic upgrade head && uvicorn app.main:app` | Render, Web Service | `backend/.env` или переменные сервиса |
| Worker | тот же образ, команда `python -m app.worker` | Render, Background Worker | те же переменные, что у API |
| PostgreSQL 16 | управляемая БД, отдельная для staging и production | Render PostgreSQL или иной провайдер | `DATABASE_URL` (`postgresql+asyncpg://…`) |

Хостинг — ориентир из [telegram-self-service.md](telegram-self-service.md). Окончательный выбор, домены и доступы предоставляет тимлид. Бесплатные тарифы, которые усыпляют сервис при простое, для пилота не подходят: webhook клиента ждёт пробуждения, а worker не работает.

### Режим worker: отдельный процесс

Выбран один режим: отдельный процесс `python -m app.worker`. У API `CHANNEL_WORKER_ENABLED=false`.

Причины: деплой и перезапуск API не обрывают ходы клиентов, число слотов (`WORKER_CONCURRENCY`) настраивается отдельно, heartbeat в `/ops/status` показывает именно этот процесс.

Образ Docker по умолчанию включает worker внутри API (`CHANNEL_WORKER_ENABLED=true`, 1 слот) для хостинга одним контейнером. На стенде это значение переопределяется на `false`, иначе работают два режима сразу. `docker-compose.yml` уже задаёт `false` и запускает сервис `worker`.

Несколько worker одновременно безопасны: задания забираются через `SKIP LOCKED`, лимиты считаются в БД.

**Действие при выпуске.** Если API на Render сейчас работает одним контейнером со встроенным worker, нужно создать Background Worker из того же образа и задать API `CHANNEL_WORKER_ENABLED=false`. Порядок: сначала запустить отдельный worker, затем выключить встроенный, иначе останется период без обработки.

## Секреты и настройки

Реальные значения хранятся только в переменных хостинга или в `.env` на сервере; в Git — только [backend/.env.example](../backend/.env.example) без значений. Одинаковые переменные задаются API и worker.

| Переменная | Кто | Зачем | Ответственный |
|---|---|---|---|
| `DATABASE_URL` | API, worker | своя БД стенда; тесты отказываются работать с ней | тимлид |
| `APP_ENV=stand` / `production` | API, worker | без `development` API не стартует без `PLUMO_API_KEY` и `CHANNEL_SECRET_KEY`, mock-канал выключен | тимлид |
| `PLUMO_API_KEY` | API и Vercel (одно значение) | сервисный ключ BFF → API; браузер его не видит | тимлид |
| `CHANNEL_SECRET_KEY` | API, worker | шифрование токенов каналов и секреты webhook; смена требует переподключить боты | тимлид |
| `PUBLIC_BASE_URL` | API | публичный HTTPS-адрес API для webhook | тимлид |
| `DASHBOARD_URL` | worker | ссылка «Открыть диалог» в уведомлении менеджеру | тимлид |
| `AI_MODE=production`, `SMALL_MODEL_PROVIDER`, `BIG_MODEL_PROVIDER`, ключ провайдера (`OPENROUTER_API_KEY` и т. п.), модели | API, worker | режим и модель; см. ниже | тимлид выбирает модель |
| `HANDOFF_PROVIDER=telegram`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME` | API, worker | служебный бот уведомлений менеджеру, [manager-notifications.md](manager-notifications.md) | тимлид |
| `RESEND_API_KEY`, `AUTH_EMAIL_FROM`, `AUTH_PUBLIC_URL` | API | письма подтверждения и сброса пароля, [account-auth.md](account-auth.md) | тимлид (Resend, DNS) |
| `INSTAGRAM_APP_SECRET`, `INSTAGRAM_VERIFY_TOKEN` | API | только если пилот на Instagram | тимлид |
| `OPS_TOKEN` | API | доступ внешнего монитора к `/ops/status` | тимлид |
| `LIMIT_*`, `TURN_RESERVE_USD`, `TEST_CHAT_*` | API, worker | пределы частоты и расходов, [limits.md](limits.md) | значения утверждает тимлид |
| `WORKER_CONCURRENCY` | worker | слоты worker; по умолчанию в `.env.example` — 4 | — |
| `CHANNEL_WORKER_ENABLED=false` | API | один режим worker | — |

### Режим модели

`AI_MODE=production` задаётся явно. Если переменная пропущена, стенд молча отвечает клиентам заглушкой (mock): запрета на mock вне `development` нет. Незарегистрированный провайдер или отсутствующий ключ дают 503, без тихого перехода в mock.

Текущая рекомендуемая настройка из `.env.example`: малой модели нет (`SMALL_MODEL_PROVIDER=none`), большая — через выбранного провайдера. Выбор модели подтверждается тестами на русском, кыргызском и смешанной речи ([backend/docs/MODELS.md](../backend/docs/MODELS.md)). `TURN_RESERVE_USD` подбирается под модель по таблице в [limits.md](limits.md#резерв-против-максимального-расхода-хода).

## Миграции

Цепочка: `001` … `017` (main), `018`–`021` (Dashboard). Миграция `022_rate_windows` добавится после принятия PJ-01. Head проверяется в `/ops/status` (`schema_version`).

- Все миграции после `017` только добавляют таблицы, индексы и колонки со значениями по умолчанию. Код предыдущей версии работает на новой схеме, поэтому откат приложения не требует отката схемы.
- Ранее применённые миграции не переписываются. Схема старого локального стенда Dashboard с иными `013`–`016` — не эта цепочка. К ней не применять `upgrade` и `stamp` вслепую; перенос делается отдельным планом.
- API применяет `alembic upgrade head` при старте контейнера. На staging и production миграцию лучше выполнять явным шагом выпуска после backup (см. ниже), чтобы старт API её только подтверждал. Production-миграции выполняет тимлид.

Проверить, какая схема на стенде: `alembic current` в контейнере API или `schema_version` в `/ops/status`.

## Выпуск

1. Проверки на коммите выпуска зелёные: CI и команды из [dev-checks.md](dev-checks.md) (backend-тесты, линт, frontend typecheck, тесты, сборка).
2. Backup БД стенда средствами провайдера; убедиться, что он появился и восстанавливается.
3. `alembic upgrade head` против БД стенда (из контейнера API: `alembic upgrade head`).
4. Деплой API, затем worker, затем frontend.
5. Проверки после запуска (ниже).
6. Записать в отчёт выпуска: commit, `schema_version`, время, кто выпускал, результаты проверок.

## Проверки после запуска

| Что | Как | Ожидаемо |
|---|---|---|
| API жив | `curl https://<api>/health` | `{"status":"ok"}` |
| БД | `curl https://<api>/health/db` | `{"status":"ok"}` |
| Схема, worker, очередь, расход | `curl -H "Authorization: Bearer $OPS_TOKEN" https://<api>/ops/status` | `status: ok`, `schema_version` = ожидаемый head, `workers.alive ≥ 1` |
| Режим модели | тест-чат в кабинете («Тестирование») | ответ модели, а не заглушка |
| Служебный бот | `python -m app.manager_bot --check` | webhook на `<PUBLIC_BASE_URL>/api/v1/webhooks/telegram-manager`, без `last_error` |
| Вход и почта | регистрация тестового бизнеса | письмо подтверждения дошло, вход работает |
| Бот бизнеса | подключение в «Интеграциях», сообщение боту | ответ агента, событие в «Диалогах» |
| Передача менеджеру | «позовите менеджера» | уведомление пришло менеджеру этого бизнеса |

Поля `/ops/status` и пороги тревог — [monitoring.md](monitoring.md). Подключение внешнего монитора делает тимлид.

## Откат

- **Приложение.** Вернуть предыдущий образ API и worker и предыдущий деплой frontend. Схему не откатывать: новые таблицы и колонки предыдущая версия не читает.
- **Схема.** `alembic downgrade <ревизия>` удаляет новые таблицы и колонки вместе с данными в них. Выполняется только по решению тимлида и после backup.
- **Данные.** Восстановление из backup — инфраструктурная операция тимлида. Сообщения, пришедшие после backup, при этом теряются: события webhook хранятся в той же БД.

## Ответственность

| Junior | Тимлид |
|---|---|
| код, миграции, эта инструкция, проверки перед выпуском, отчёт | хостинг, домены, отдельная БД staging, секреты, Resend/DNS, боты |
| подготовка выпуска и порядка отката | production-миграции, выпуск, решение о запуске |
| проверки мониторинга и восстановления | подключение внешнего монитора, доступ к backup |

## Проверено

4 ноября 2026, локально, PostgreSQL 16.15:

| Проверка | Результат |
|---|---|
| Пустая БД: `alembic upgrade head`, затем `downgrade base` | 21 / 21 ревизия, head `021_scenario_revisions` |
| Схема локальной БД на `017_leads` против свежей цепочки до `017_leads` (`pg_dump --schema-only`) | совпадают: это схема main, а не старого стенда Dashboard |
| Копия этой БД с данными (2 бизнеса, 110 клиентов, 1 390 сообщений, 158 передач, 47 заданий): `upgrade 017_leads → head` | 4 ревизии за 1,1 с; число строк до и после совпадает |
| API на обновлённой копии (`AI_MODE=mock`) | `/health` ok, `/health/db` ok, `/ops/status` — `schema_version` 021, `database` ok (`degraded` только из-за остановленного worker) |
| `python -m app.worker --once` на обновлённой копии | запуск без ошибок, 0 заданий |
| `docker compose config` с `CHANNEL_WORKER_ENABLED=false` у API | конфигурация валидна |

## Не проверено и что нужно

Staging нет. Для приёмки PJ-03 нужно от тимлида:
- хостинг API, worker и frontend с HTTPS-адресами;
- отдельная БД staging и доступ к её backup;
- секреты стенда;
- служебный бот и два тестовых бота бизнеса;
- Resend и DNS для почты.

После этого пройти «Выпуск» и «Проверки после запуска» на staging и приложить отчёт. Обновление с текущей схемы staging проверяется там же, после `alembic current`.
