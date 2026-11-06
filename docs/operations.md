# Запуск стенда и выпуск

Как запустить актуальный `main` на staging или production: из каких частей состоит стенд, где лежат секреты, как применить миграции, проверить запуск и откатиться. Команды локальной разработки — в [dev-checks.md](dev-checks.md).

Статус на 5 ноября 2026: staging-окружения нет. Цепочка миграций, запуск API и worker на обновлённой схеме и smoke-проверка проверены локально (раздел «Проверено»), на хостинге — нет.

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
| `VOICE_MESSAGES_ENABLED`, `STT_PROVIDER=elevenlabs`, `ELEVENLABS_API_KEY`, `VOICE_MAX_DURATION_S`, `STT_MIN_CONFIDENCE`, `STT_USD_PER_MINUTE`, `STT_COST_VERSION`, `STT_TIMEOUT_S`, `ELEVENLABS_STT_MODEL`, `ELEVENLABS_STT_ZERO_RETENTION` | worker (распознаёт), API (`/ops/status`) | голосовые Telegram, [voice-messages.md](voice-messages.md); по умолчанию выключены | тимлид включает после живой проверки и решения о согласии |
| `WORKER_CONCURRENCY` | worker | слоты worker; по умолчанию в `.env.example` — 4 | — |
| `CHANNEL_WORKER_ENABLED=false` | API | один режим worker | — |
| `MIGRATE_ON_START=false` | API | миграция — отдельный шаг выпуска; образ для отката не трогает схему (раздел «Откат») | — |
| `APP_COMMIT` | API, worker | коммит в `/ops/status`; не нужен, если хостинг сам задаёт `RENDER_GIT_COMMIT` или `SOURCE_COMMIT` — проверить на стенде | тимлид |

Проверить набор переменных без вывода значений: поле `config` в `/ops/status` показывает, задана ли каждая переменная стенда (да/нет), и список `problems`. Smoke-проверка выпуска падает, если `problems` не пуст.

### Режим модели

`AI_MODE=production` задаётся явно. Если переменная пропущена, стенд отвечает клиентам заглушкой (mock): сам API её не запрещает, но `/ops/status` показывает `ai_mode_mock` в `config.problems`, и smoke-проверка выпуска падает. Незарегистрированный провайдер или отсутствующий ключ дают 503, без тихого перехода в mock.

Текущая рекомендуемая настройка из `.env.example`: малой модели нет (`SMALL_MODEL_PROVIDER=none`), большая — через выбранного провайдера. Выбор модели подтверждается тестами на русском, кыргызском и смешанной речи ([backend/docs/MODELS.md](../backend/docs/MODELS.md)). `TURN_RESERVE_USD` подбирается под модель по таблице в [limits.md](limits.md#резерв-против-максимального-расхода-хода).

## Первое развёртывание: Supabase + Render + Vercel

Supabase хранит только PostgreSQL. API и worker — Python-процессы: на Supabase и Vercel они не запускаются, их держит Render ([render.yaml](../render.yaml)). Кабинет остаётся на Vercel.

1. **Supabase.**
   - Project Settings → Database → Connection string → **Session pooler**. Превратить в `postgresql+asyncpg://…` — это `DATABASE_URL`. Пароль в Git и чаты не вставлять.
   - Если в этой БД уже есть таблицы, сначала выполнить `alembic current` с этим `DATABASE_URL`. Ответ одной из ревизий `001`…`022` этой цепочки — можно продолжать. Неизвестная ревизия (например, `006_channels_dashboard` старого стенда) или таблицы без `alembic_version` — остановиться: нужен отдельный план переноса или новая пустая БД.
   - Сделать backup до первой миграции (Database → Backups или `pg_dump`).
2. **Секреты.** Каждый генерируется один раз и хранится только в панелях хостингов:
   ```sh
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
   Так создаются `PLUMO_API_KEY` (одно значение на Render и Vercel), `CHANNEL_SECRET_KEY` (не менять после подключения ботов) и `OPS_TOKEN`.
3. **Render.**
   - New → Blueprint → репозиторий, ветка `main` → Render прочитает `render.yaml`, создаст `plumo-api` и `plumo-worker` и спросит значения с `sync: false`. Одинаковые значения вводятся обоим сервисам.
   - После создания адрес API — `https://plumo-api.onrender.com` или имя, которое назначит Render. Это `PUBLIC_BASE_URL`.
   - `DASHBOARD_URL` и `AUTH_PUBLIC_URL` — адрес сайта на Vercel без пути.
   - Миграции выполняет `preDeployCommand`. Если миграция падает, деплой останавливается, прежняя версия продолжает работать.
4. **Vercel.** Settings → Environment Variables (Production): `PLUMO_API_URL` = адрес API без `/api/v1`, `PLUMO_API_KEY` = то же значение, что на Render. Затем Redeploy.
5. **Почта.** Resend: добавить свой домен, внести DNS-записи у регистратора и дождаться Verified. `AUTH_EMAIL_FROM` — адрес на этом домене. Без своего домена письма уходят только на адрес владельца аккаунта Resend.
6. **Служебный бот уведомлений.** `TELEGRAM_BOT_TOKEN` и `TELEGRAM_BOT_USERNAME` от @BotFather. Затем в Render Shell у `plumo-api` выполнить `python -m app.manager_bot` (ставит webhook и печатает имя бота для `TELEGRAM_BOT_USERNAME`), потом `python -m app.manager_bot --check`: webhook должен указывать на `<PUBLIC_BASE_URL>/api/v1/webhooks/telegram-manager`.
7. **Smoke** — раздел «Проверки после запуска». Для автоматического smoke после push в GitHub задать `STAGING_API_URL`, `STAGING_FRONTEND_URL` и `STAGING_OPS_TOKEN`.
8. **Внешний монитор.** Любой сервис HTTP-проверок с уведомлением в Telegram или на почту: `https://<api>/health` и `https://<api>/health/db` раз в минуту. Для `/ops/status` нужен монитор, который умеет передавать заголовок `Authorization`.

Один стенд — он же пилотный: отдельного staging и production для первого пилота нет. Тогда тестовые данные двух проверочных бизнесов останутся в той же БД, что и данные пилотного бизнеса; изоляция по `business_id` это допускает. Отдельный staging — второй проект Supabase и вторая пара сервисов Render.

## Миграции

Цепочка: `001` … `017` (main), `018`–`021` (Dashboard). Миграция `022_rate_windows` добавится после принятия PJ-01. Head проверяется в `/ops/status` (`schema_version`).

- Все миграции после `017` только добавляют таблицы, индексы и колонки со значениями по умолчанию. Поэтому код предыдущей версии, вероятно, работает на новой схеме, но это не доказано автоматически и проверяется для каждого выпуска (раздел «Откат»).
- Ранее применённые миграции не переписываются. Схема старого локального стенда Dashboard с иными `013`–`016` — не эта цепочка. К ней не применять `upgrade` и `stamp` вслепую; перенос делается отдельным планом.
- Образ по умолчанию применяет `alembic upgrade head` при старте (`MIGRATE_ON_START=true`, для запуска одним контейнером). На staging и production задаётся `MIGRATE_ON_START=false`: миграция — явный шаг выпуска после backup. Production-миграции выполняет тимлид.

Проверить, какая схема на стенде: `alembic current` в контейнере API или `schema_version` в `/ops/status`.

## Выпуск

1. Проверки на коммите выпуска зелёные: CI и команды из [dev-checks.md](dev-checks.md) (backend-тесты, линт, frontend typecheck, тесты, сборка).
2. Записать текущее состояние для отката: коммит и `schema_version` из `/ops/status`, идентификатор текущего деплоя API, worker и frontend на хостинге.
3. Если в выпуске есть новые миграции — проверка совместимости отката (раздел «Откат»).
4. Backup БД стенда средствами провайдера; убедиться, что он появился и восстанавливается.
5. `alembic upgrade head` против БД стенда (из контейнера API: `alembic upgrade head`).
6. Деплой API, затем worker, затем frontend.
7. Smoke-проверка и ручные проверки (ниже).
8. Записать в отчёт выпуска: commit, `schema_version`, время, кто выпускал, результаты проверок.

## Проверки после запуска

### Автоматическая smoke-проверка

[backend/scripts/staging_smoke.py](../backend/scripts/staging_smoke.py) — только стандартная библиотека Python; ничего не отправляет клиентам и менеджерам, токен берёт из окружения и не печатает.

```sh
cd backend
OPS_TOKEN=<ops-токен staging> python scripts/staging_smoke.py \
  --api https://<api> --frontend https://<кабинет> --expect-commit <коммит выпуска> [--wait-s 900]
```

`--expect-schema` по умолчанию — head миграций этого checkout (нужен установленный Alembic) или явная ревизия. `--wait-s` ждёт, пока хостинг выкатит `--expect-commit` на API и worker. Код выхода 0 — все проверки прошли.

| Проверка | Ожидаемо |
|---|---|
| адреса API и кабинета | HTTPS |
| `/health`, `/health/db` | 200, `ok` |
| `/api/v1/auth/me` без сервисного ключа | 401 `unauthorized`: API закрыт для посторонних |
| `/ops/status` без токена | 401 (404 — `OPS_TOKEN` на API не задан) |
| `/ops/status` с токеном | 200, `status: ok`; `commit` = выпущенный; `schema_version` = head; `workers.alive ≥ 1`; `workers.commits` = коммит API; `config.problems` пуст |
| страница кабинета | 200, в HTML нет ops-токена |
| вход с несуществующим адресом через кабинет | 401 `not_authenticated`: сервер кабинета дошёл до API с верным ключом (`unauthorized` — ключ кабинета и API различаются) |

После push в `main` то же выполняет [staging-smoke](../.github/workflows/staging-smoke.yml): ждёт до 15 минут появления коммита на staging и запускает скрипт. Пока переменные staging в GitHub не заданы, задание пропускается (skipped, а не passed). Вручную: Actions → staging-smoke → Run workflow.

### Ручные проверки

| Что | Как | Ожидаемо |
|---|---|---|
| Режим модели | тест-чат в кабинете («Тестирование») | ответ модели, а не заглушка |
| Служебный бот | `python -m app.manager_bot --check` | webhook на `<PUBLIC_BASE_URL>/api/v1/webhooks/telegram-manager`, без `last_error` |
| Вход и почта | регистрация тестового бизнеса | письмо подтверждения дошло, вход работает |
| Бот бизнеса | подключение в «Интеграциях», сообщение боту | ответ агента, событие в «Диалогах» |
| Передача менеджеру | «позовите менеджера» | уведомление пришло менеджеру этого бизнеса |

Поля `/ops/status` и пороги тревог — [monitoring.md](monitoring.md). Подключение внешнего монитора делает тимлид.

## Откат

Обычный откат — только приложение. Схема остаётся новой.

1. Решение об откате принимает тимлид; записать время и причину.
2. API и worker: вернуть предыдущий деплой на хостинге (Render: Manual Deploy → предыдущий коммит или Rollback к прошлому деплою). Сначала worker, затем API.
3. У API должно быть `MIGRATE_ON_START=false`. **Образы до PJ-03 эту переменную не знают** и при старте выполняют `alembic upgrade head`. Если в БД ревизия новее, чем знает старый код, Alembic завершается ошибкой «Can't locate revision» и API не стартует. Для такого образа заменить команду запуска на `uvicorn app.main:app --host 0.0.0.0 --port 8000` (Render: Settings → Docker Command).
4. Frontend: предыдущий деплой (Vercel: Deployments → Promote to Production / Instant Rollback).
5. Smoke-проверка с `--expect-commit <прежний коммит> --expect-schema <текущая ревизия БД>`.
6. Записать в отчёт: коммиты до и после, `schema_version`, результат smoke.

**Совместимость старого кода с новой схемой не доказана автоматически.** Миграции только добавляют объекты, но старый код может, например, не заполнять новую обязательную колонку. Перед выпуском с новыми миграциями проверить на копии БД:

```sh
# копия БД staging (или свежая БД), обновлённая новым кодом
DATABASE_URL=<копия> alembic upgrade head          # из checkout нового выпуска
# из checkout предыдущего выпуска, без миграции при старте:
DATABASE_URL=<копия> APP_ENV=development AI_MODE=mock OPS_TOKEN=<любой> \
  uvicorn app.main:app --port 8001 &
DATABASE_URL=<копия> APP_ENV=development AI_MODE=mock python -m app.worker --once
```

Затем `/health/db` и `/ops/status` старого API на `:8001`, и основные действия старого кабинета против этого API (вход, диалоги, сообщение через тестовый чат). Если старый код ломается на новой схеме, откат приложения без отката схемы невозможен — это записать в описание PR выпуска до выпуска.

- **Схема.** `alembic downgrade <ревизия>` удаляет новые таблицы и колонки вместе с данными в них. Это не обычный откат: выполняется только по решению тимлида, после backup и с записью, какие данные теряются.
- **Данные.** Восстановление из backup — инфраструктурная операция тимлида. Сообщения, пришедшие после backup, при этом теряются: события webhook хранятся в той же БД.

## CI и защита выпуска

CI ([ci.yml](../.github/workflows/ci.yml)) запускается на каждый pull request и push в `main` и `develop`: backend — ruff, миграции на пустой БД вверх-вниз-вверх, pytest; frontend — typecheck, тесты, сборка. Само по себе красное задание выпуск не блокирует: это делает защита ветки.

Настройки, которые делает тимлид (GitHub → Settings):

| Где | Настройка |
|---|---|
| Rules → Rulesets → New branch ruleset, цель `main` | Restrict deletions; Block force pushes |
| то же | Require a pull request before merging; при одном разработчике — 0 одобрений, но только через PR |
| то же | Require status checks to pass: `backend`, `frontend` (имена заданий из `ci.yml`); Require branches to be up to date before merging |
| то же | Bypass list пуст (иначе администратор вливает в обход проверок) |
| Secrets and variables → Actions | `STAGING_API_URL`, `STAGING_FRONTEND_URL` (variables), `STAGING_OPS_TOKEN` (secret) |
| Environments (по желанию) | `production` с обязательным подтверждением тимлида, если деплой production пойдёт через GitHub |
| Хостинг | автодеплой staging из `main`; production — только вручную тимлидом |

Проверка, что блокировка работает: PR с заведомо падающим тестом должен показывать «Merging is blocked» до исправления. PR после проверки закрыть без слияния.

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

5 ноября 2026, локально (Windows, PostgreSQL 16.4):

| Проверка | Результат |
|---|---|
| Backend: `ruff check src tests alembic scripts`, `pytest` | чисто; 442 passed |
| Smoke против локальных API, worker и кабинета (`next dev`), `AI_MODE=mock` | прошли проверки HTTP, ключа, ops-токена, коммита, схемы, worker и связи кабинета с API; упали ожидаемо: не HTTPS и `config.problems` (`app_env_development`, `ai_mode_mock`, `handoff_provider_mock`, `missing:…`) |
| Smoke с неверным `--expect-commit` и с неверным ops-токеном | падает с понятной причиной; токен в выводе отсутствует |
| БД на `022_rate_windows` (ветка PJ-01), затем `alembic upgrade head` кодом `main` | `Can't locate revision identified by '022_rate_windows'` — старый образ с миграцией при старте не запустится; отсюда `MIGRATE_ON_START` и шаг 3 отката |
| Код `main` на этой БД без миграции: API (`uvicorn`) и `python -m app.worker --once` | `/health/db` ok, `/ops/status` — `schema_version` 022, worker без ошибок. Ход клиента и действия кабинета старым кодом не проверялись |
| Логика запуска образа (`sh -c …` из Dockerfile) | `true` — миграция и запуск; `false` — только запуск; ошибка миграции — API не стартует. Сборка образа не проверялась: Docker недоступен |

## Не проверено и что нужно

Staging нет. Для приёмки PJ-03 нужно от тимлида:
- хостинг API, worker и frontend с HTTPS-адресами;
- отдельная БД staging и доступ к её backup;
- секреты стенда;
- служебный бот и два тестовых бота бизнеса;
- Resend и DNS для почты.
- настройки GitHub из раздела «CI и защита выпуска».

После этого пройти «Выпуск» и «Проверки после запуска» на staging и приложить отчёт. Обновление с текущей схемы staging проверяется там же, после `alembic current`. Не проверено и на хостинге: задаёт ли Render `RENDER_GIT_COMMIT` в работающем контейнере, названия пунктов меню Render/Vercel для отката, блокировка слияния красным CI.
