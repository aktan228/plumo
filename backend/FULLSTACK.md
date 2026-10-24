# Plumo backend: подключение за 15 минут

Для фуллстек-разработчика, который подключает кабинет, каналы или деплой. Устройство AI-ядра описано в [LEAD.md](LEAD.md), голос — в [VOICE.md](VOICE.md).

## 1. Запуск

Нужен Python 3.12+ ([python.org](https://www.python.org/downloads/), галочка «Add to PATH»). Все команды из корня проекта.

### Windows: одна команда

```powershell
cd C:\путь\к\Plumo
.\dev.cmd setup     # первый раз: .venv, зависимости, .env
.\dev.cmd up        # база + миграции + демо-данные + API → http://127.0.0.1:8000/docs
```

`dev.cmd` сам берёт Python из `.venv`, активировать окружение не нужно, и политику выполнения PowerShell менять не нужно. Остальные команды: `.\dev.cmd db | db-stop | seed | run | demo | test | eval`.

Частые ошибки:

| Ошибка | Причина | Что делать |
| --- | --- | --- |
| `Имя ".\scripts\..." не распознано` | команда запущена не из папки проекта | `cd` в корень Plumo |
| `выполнение сценариев отключено` | PowerShell блокирует `.ps1` | `.\dev.cmd ...`, он обходит это сам |
| `python` печатает «Python» и молчит | заглушка Microsoft Store вместо Python | установить Python с python.org или запускать через `.\dev.cmd` |
| `uvicorn не распознано` | `.venv` не активировано | `.\dev.cmd run` |
| `Connection refused :5432` | база не запущена | `.\dev.cmd db` |

### База: варианты

| Вариант | Как | Когда |
| --- | --- | --- |
| Локально без Docker (Windows) | `.\dev.cmd db` | по умолчанию. Скачает Postgres 16 в `.tools/` один раз |
| Docker | `docker compose up -d db` | если Docker уже стоит |
| Supabase | в `.env`: `DATABASE_URL=<строка "Transaction pooler" из Supabase как есть>` | общая база для команды без сервера |

### macOS / Linux

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
cp .env.example .env
docker compose up -d db        # или Supabase в DATABASE_URL
python -m app.seed && uvicorn app.main:app --reload
```

### Проверить ядро целиком

```powershell
.\dev.cmd test                       # все тесты, нужна база
.\dev.cmd eval                       # живая модель: 10 реплик, тон, цена, задержка
```

## 2. Переменные окружения

| Переменная | Зачем | Пример |
| --- | --- | --- |
| `DATABASE_URL` | Postgres, async-драйвер | `postgresql+asyncpg://plumo:plumo@db:5432/plumo` |
| `APP_ENV` | `stand` / `production`: без `PLUMO_API_KEY` и `CHANNEL_SECRET_KEY` API не стартует | `stand` |
| `PLUMO_API_KEY` | ключ для `/api/v1/*`, заголовок `X-API-Key`; его знает только сервер Next.js. **На сервере обязателен** | длинная случайная строка |
| `CORS_ORIGINS` | прямой доступ браузера к API; кабинету не нужен (он ходит через Next.js) | пусто |
| `PUBLIC_BASE_URL`, `CHANNEL_SECRET_KEY`, `CHANNEL_CREDENTIALS_FILE` | каналы Telegram/Instagram, см. [../docs/dashboard-channels.md](../docs/dashboard-channels.md) | `https://api.plumo.kg` |
| `AI_MODE` | `mock` — без внешних вызовов, `production` — живая модель | `production` |
| `SMALL_MODEL_PROVIDER` / `BIG_MODEL_PROVIDER` | семейство моделей, см. [docs/MODELS.md](docs/MODELS.md) | `none` / `openrouter_big` |
| `OPENROUTER_BIG_MODEL` | модель | `anthropic/claude-haiku-5.5` |
| `OPENROUTER_API_KEY` | ключ OpenRouter, если модели через него | `sk-or-v1-…` |
| `HANDOFF_PROVIDER` | `telegram` — карточка менеджеру в Telegram | `telegram` |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_MANAGER_CHAT_ID` | бот уведомлений менеджерам (не клиентский бот) | `123:ABC…` / `-100…` |
| `ELEVENLABS_LLM_TOKEN` | секрет, с которым ElevenLabs ходит к нам | случайная строка |
| `ELEVENLABS_WEBHOOK_SECRET` | HMAC post-call вебхука, берётся в ElevenLabs | `wsec_…` |
| `VOICE_USD_PER_MINUTE` | цена минуты по тарифу ElevenLabs, для метрик | `0.08` |

Секреты только в `.env` на сервере, в git не коммитятся.

## 3. Контракт

Полная схема: [docs/openapi.json](docs/openapi.json). Обновить её: `python -m app.export_openapi`. Типы для фронта: `npx openapi-typescript docs/openapi.json -o src/api/plumo.d.ts`.

Все запросы к `/api/v1/*`, кроме телефонии и webhook, идут с заголовком `X-API-Key`. Маршруты кабинета требуют ещё сессию оператора и ограничены его бизнесом; браузер обращается к ним только через сервер Next.js (`frontend/src/app/api/plumo`). Полный список и политика доставки — [../docs/dashboard-channels.md](../docs/dashboard-channels.md).

| Метод | Путь | Для чего |
| --- | --- | --- |
| POST | `/api/v1/messages` | Входящее сообщение из любого канала → ответ агента |
| GET | `/api/v1/customers/{id}` | Карточка клиента |
| GET | `/api/v1/customers/{id}/history` | Вся история по всем каналам |
| GET | `/api/v1/conversations` · `/{id}` | Диалоги бизнеса: поиск, фильтры, курсор; история со статусами доставки |
| POST | `/api/v1/conversations/{id}/takeover` · `/resume` | Взять диалог (агент замолкает) / вернуть агенту |
| GET | `/api/v1/handoffs?status=PENDING` | Очередь «передать человеку» |
| POST | `/api/v1/handoffs/{id}/accept` · `/resolve` | То же через конкретную передачу |
| POST | `/api/v1/conversations/{id}/messages` | Ответ менеджера: одна операция отправки в канал (`idempotency_key`) |
| GET · POST · PATCH | `/api/v1/integrations…` | Подключение Telegram/Instagram, проверка, агент вкл/выкл, отключение |
| POST | `/api/v1/webhooks/telegram/{id}` · `/webhooks/instagram` | Только для провайдеров, своя проверка подлинности |
| GET · POST | `/api/v1/knowledge` | База знаний бизнеса |
| POST | `/api/v1/meetings` | Встреча вручную |
| GET | `/api/v1/metrics` | Цифры для еженедельного отчёта клиенту |
| POST | `/api/v1/telephony/elevenlabs/*` | Только для ElevenLabs, своя авторизация |

### Канал → ядро

Адаптер канала (WhatsApp Cloud API, Telegram Bot API, Instagram) принимает вебхук провайдера, приводит его к этому виду и отправляет ответ `response_text` обратно в тот же чат:

```bash
curl -X POST https://api.example.com/api/v1/messages \
  -H "X-API-Key: $PLUMO_API_KEY" -H "Content-Type: application/json" \
  -d '{"channel":"whatsapp","external_user_id":"+996555123456","text":"Еще продается?","message_id":"wamid.HBg..."}'
```

`channel` — `whatsapp | telegram | instagram | voice`. Для WhatsApp и звонков `external_user_id` — телефон, это ключ клиента. Для Telegram и Instagram — id в канале; когда клиент назовёт номер, карточки склеятся сами.

В ответе важно:

- `send_reply` — **если `false`, ничего не отправлять**: диалог ведёт менеджер;
- `response_text` — что отправить клиенту;
- `duplicate` — провайдер прислал тот же `message_id` повторно. Ответ взят из истории, модель не вызывалась. Отправлять повторно не нужно, если первый ответ уже ушёл;
- `handoff_required` + `handoff_reason` — показать в кабинете и уведомить менеджера;
- `customer_id`, `conversation_id` — ссылки для кабинета;
- `actions` — встреча, запрос телефона;
- заголовок `X-Correlation-Id` — по нему запрос находится в логах.

### Менеджер забирает диалог

1. Агент создал передачу → карточка в Telegram-боте менеджеров и в `GET /handoffs?status=PENDING`; в кабинете диалог «Нужен менеджер».
2. Менеджер жмёт «Взять диалог» → `POST /conversations/{id}/takeover` (работает и без передачи). Агент на новые сообщения не отвечает, но пишет их в историю; неотправленные ответы агента отменяются.
3. Менеджер пишет клиенту: `POST /conversations/{id}/messages` создаёт одну отправку, worker доставляет её в Telegram/Instagram и пишет статус.
4. Закончил → `POST /conversations/{id}/resume`: агент снова отвечает и видит в истории доставленные реплики менеджера; недоставленные в контекст модели не попадают.

### Ошибки

Всегда JSON: `{"error": "<code>", "message": "...", "correlation_id": "..."}`. Коды: 401 — нет ключа, 404 — нет клиента или бизнеса, 422 — пустой текст или неизвестный канал, 503 — не настроен провайдер (модель, ключ ElevenLabs).

## 4. Деплой

1. VPS с публичным IP или доменом и HTTPS: Caddy или nginx + Let's Encrypt перед портом 8000. ElevenLabs без HTTPS не работает.
2. `.env` с `PLUMO_API_KEY`, `AI_MODE=production`, ключами.
3. `docker compose up -d --build`, затем `docker compose run --rm api python -m app.seed` для демо.
4. URL `https://<домен>/api/v1/telephony/elevenlabs/...` вписать в ElevenLabs (шаги в [VOICE.md](VOICE.md)).

Для локальной отладки звонков хватит `ngrok http 8000`.

## 5. Что где в коде

| Хочу | Файл |
| --- | --- |
| Новый роут | `src/app/api/routes/`, подключить в `src/app/main.py` |
| Поменять, как агент говорит | `src/app/domain/phrases.py` |
| Логика одного сообщения | `src/app/application/services/agent_service.py` |
| Звонки | `src/app/application/services/call_service.py`, `src/app/infrastructure/telephony/` |
| Таблицы | `src/app/infrastructure/database/models.py` + новая миграция в `alembic/versions/` |
| Сборка зависимостей | `src/app/container.py` |

## 6. Git

Работаем по git flow: ветка `feature/<что-делаем>` от `develop`, PR в `develop`. В `develop` и `main` напрямую не пушим.

Тесты: `pytest tests/unit` — без базы; `pytest` — нужен Postgres. Worker: `.\dev.cmd worker` (или `python -m app.worker`), в отдельном окне рядом с API.


## Самостоятельная регистрация MVP

`/register` → Next.js `POST /api/auth/register` → backend `POST /api/v1/auth/register`.
Тело: `{ "name": "Айжан", "email": "owner@example.com", "password": "example-passphrase", "locale": "ru" }`.
Имя после обрезки пробелов — 1–100 символов без управляющих символов, почта валидируется и приводится к нижнему регистру,
пароль — 10–128 символов, не только пробелы. Поля `business_id` и другие дополнительные поля backend отклоняет.
Сервер создаёт бизнес «Мой бизнес» / «My business», оператора, `onboarding_drafts` (step=0, data={}) и сессию одной транзакцией.
Ответ backend: 201 с форматом `LoginOut`; Next.js убирает token из JSON и ставит HttpOnly/SameSite cookie (Secure на HTTPS).
Ошибки: 422 — поля, 409 — аккаунт не создан (повторная почта), 429 — лимит 10 попыток за час на адрес клиента.
Лимит пока в памяти одного API-процесса, сбрасывается при рестарте. В production нужен общий limiter до масштабирования.
`x-plumo-client-ip` передаёт сервер Next.js под сервисным ключом; браузер не выбирает его в форме.
Двойное нажатие блокируется формой; уникальная почта в PostgreSQL защищает от конкурентных запросов без лишних бизнесов.

При деплое сначала обновить backend и применить миграцию `007_self_service_registration` (`alembic upgrade head`), затем frontend.
Новых переменных окружения не требуется: прежние `DATABASE_URL` на backend, `PLUMO_API_URL` и совпадающий `PLUMO_API_KEY` на Next.js.
Названия бизнесов больше не уникальны; административные команды `app.operators create` и `app.import_knowledge` принимают `--business-id UUID`.
`--business` работает только при однозначном названии, чтобы импорт не попал в чужой бизнес.
Подтверждение почты/сброс пароля и сохранение шагов мастера — следующие отдельные этапы; регистрация пока сразу выдаёт сессию.
