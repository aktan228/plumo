# Plumo backend: подключение за 15 минут

Для фуллстек-разработчика, который подключает кабинет, каналы или деплой. Устройство AI-ядра описано в [LEAD.md](LEAD.md), голос — в [VOICE.md](VOICE.md).

## 1. Запуск

```powershell
git clone <repo>; cd plumo
copy .env.example .env          # заполнить, см. таблицу ниже
docker compose up -d --build    # Postgres + API, миграции применятся сами
docker compose run --rm api python -m app.seed   # демо-бизнес и база знаний
```

Проверка: http://localhost:8000/health → `{"status":"ok"}`, Swagger: http://localhost:8000/docs.

Без Docker: Python 3.12, `pip install -e ".[dev]"`, `alembic upgrade head`, `uvicorn app.main:app --reload`.

## 2. Переменные окружения

| Переменная | Зачем | Пример |
| --- | --- | --- |
| `DATABASE_URL` | Postgres, async-драйвер | `postgresql+asyncpg://plumo:plumo@db:5432/plumo` |
| `PLUMO_API_KEY` | ключ для `/api/v1/*`, заголовок `X-API-Key`. **На сервере обязателен** | длинная случайная строка |
| `CORS_ORIGINS` | адреса фронта через запятую | `https://app.plumo.kg,http://localhost:3000` |
| `AI_MODE` | `mock` — без внешних вызовов, `production` — живая модель | `production` |
| `SMALL_MODEL_PROVIDER` / `BIG_MODEL_PROVIDER` | имена моделей в фабрике | `openrouter_small` / `openrouter_big` |
| `OPENROUTER_API_KEY` | ключ OpenRouter | `sk-or-v1-…` |
| `ELEVENLABS_LLM_TOKEN` | секрет, с которым ElevenLabs ходит к нам | случайная строка |
| `ELEVENLABS_WEBHOOK_SECRET` | HMAC post-call вебхука, берётся в ElevenLabs | `wsec_…` |
| `VOICE_USD_PER_MINUTE` | цена минуты по тарифу ElevenLabs, для метрик | `0.08` |

Секреты только в `.env` на сервере, в git не коммитятся.

## 3. Контракт

Полная схема: [docs/openapi.json](docs/openapi.json). Обновить её: `python -m app.export_openapi`. Типы для фронта: `npx openapi-typescript docs/openapi.json -o src/api/plumo.d.ts`.

Все запросы к `/api/v1/*`, кроме телефонии, идут с заголовком `X-API-Key`.

| Метод | Путь | Для чего |
| --- | --- | --- |
| POST | `/api/v1/messages` | Входящее сообщение из любого канала → ответ агента |
| GET | `/api/v1/customers/{id}` | Карточка клиента |
| GET | `/api/v1/customers/{id}/history` | Вся история по всем каналам |
| GET | `/api/v1/conversations/{id}` | Один диалог |
| GET | `/api/v1/handoffs?status=PENDING` | Очередь «передать человеку» |
| POST | `/api/v1/handoffs/{id}/accept` · `/resolve` | Менеджер взял / закрыл |
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

- `response_text` — что отправить клиенту;
- `handoff_required` + `handoff_reason` — показать в кабинете и уведомить менеджера;
- `customer_id`, `conversation_id` — ссылки для кабинета;
- `actions` — встреча, запрос телефона;
- заголовок `X-Correlation-Id` — по нему запрос находится в логах.

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

Тесты: `pytest tests/unit` — без базы; `pytest` — нужен Postgres.
