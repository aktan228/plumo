# Plumo

Plumo — ядро AI-менеджера по продажам. Один клиент, одна карточка, одна история, даже если он пишет из WhatsApp, Instagram, Telegram и потом звонит.

Подключить бэк к кабинету, каналам или серверу: [FULLSTACK.md](FULLSTACK.md). Коротко для лида: [LEAD.md](LEAD.md). Живая модель или канал: [INTEGRATION.md](INTEGRATION.md). Звонки: [VOICE.md](VOICE.md). Какую модель брать: [docs/MODELS.md](docs/MODELS.md). Как агент разговаривает: [docs/CONVERSATION.md](docs/CONVERSATION.md). Что подключить и купить: [docs/CHECKLIST.md](docs/CHECKLIST.md).

Сейчас текстовая модель подключается через OpenRouter. При `AI_MODE=production` ядро вызывает Gemini 2.5 Flash. Телефонные звонки идут через ElevenLabs Agents, Plumo подключён к нему как Custom LLM: [VOICE.md](VOICE.md). Порты STT/TTS для голосовых сообщений в чатах пока mock. Каналы WhatsApp/Telegram ещё не живые.

## Архитектура

Сообщение с канала приходит как транспортное событие, сразу нормализуется и дальше идёт одним пайплайном:

```
канал
  → normalize
  → customer resolution
  → memory
  → knowledge
  → router
  → LLM provider
  → validator
  → actions / handoff
  → memory update
  → log
  → ответ канала
```

Ядро не знает, откуда пришёл текст. Для него это `InboundMessage`. Наружу уходит `AgentResponse`.

Код — модульный монолит, один процесс и одна PostgreSQL:

```
src/app/domain            сущности, порты, ошибки, события
src/app/application       сервисы и сценарии
src/app/infrastructure    Postgres, mock AI, каналы, логи
src/app/api               REST и схемы
src/app/container.py      единственное место сборки зависимостей
```

Внешние системы спрятаны за протоколами в `src/app/domain/ports.py`: `LLMProvider`, `STTProvider`, `TTSProvider`, `Router`, `LanguageDetector`, `HumanHandoffProvider`, `ActionExecutor`, `ChannelAdapter`, `KnowledgeRetriever`, `EventBus`.

`AgentService` зависит только от этих протоколов. Он не импортирует SDK.

Главное правило: Plumo не имеет права придумывать факт. Цена, наличие, срок, рассрочка, адрес, график и характеристики объекта берутся из базы знаний или карточки бизнеса. Если факта нет, ответ отказывается и создаётся handoff. Это проверяет `ResponseValidator`, а не конкретная модель. После подключения живой LLM правило останется.

## Как запустить

Windows, из корня проекта:

```powershell
.\dev.cmd setup   # один раз
.\dev.cmd up      # база + демо-данные + API → http://127.0.0.1:8000/docs
```

Подробнее и про ошибки PowerShell: [FULLSTACK.md](FULLSTACK.md). Ручной вариант ниже.

Нужны Python 3.12+ и PowerShell из корня репозитория. Базу можно поднять без Docker: `.\scripts\local-db.ps1 start`, или указать Supabase в `DATABASE_URL` (подробнее в [FULLSTACK.md](FULLSTACK.md)).

```powershell
docker compose up -d db   # или .\scripts\local-db.ps1 start
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
alembic upgrade head
python -m app.seed
python -m app.demo
uvicorn app.main:app --reload
```

Swagger: http://127.0.0.1:8000/docs

Проверка здоровья: http://127.0.0.1:8000/health

Весь стек одной командой, вместе с API:

```powershell
docker compose up --build
docker compose run --rm api python -m app.seed
```

API внутри compose слушает порт 8000. База с хоста доступна на `localhost:5432`.

## PostgreSQL

`docker-compose.yml` поднимает Postgres 16:

- пользователь `plumo`
- пароль `plumo`
- база `plumo`
- порт `5432`

Строка подключения:

```
postgresql+asyncpg://plumo:plumo@localhost:5432/plumo
```

Она лежит в `.env`. Образец без локальных правок — `.env.example`. Ключей AI там нет и не должно быть, пока не появится реальный адаптер.

Тесты используют отдельную базу `plumo_test` и сами создают её, если Postgres уже запущен.

## Миграции

Схема в `alembic/versions/001_initial.py`, звонки — `002_voice_calls.py`.

```powershell
alembic upgrade head
alembic downgrade base
```

Alembic читает `DATABASE_URL` из настроек приложения. В контейнере миграция применяется при старте API.

Таблицы раздельные: `businesses`, `knowledge_items`, `customers`, `customer_channels`, `conversations`, `messages`, `customer_summaries`, `handoff_requests`, `meetings`, `interaction_logs`, `ai_usage_logs`. JSONB только у metadata, контактов, actions и снимка последних сообщений.

## Seed

```powershell
python -m app.seed
```

Команда идемпотентна и сама применяет миграции. Она создаёт бизнес Demo Realty, график 09:00-18:00, адрес на проспекте Чуй и два объекта:

- Квартира на Чуй, 2 комнаты, 58 м², 5 этаж, 85000 USD
- Квартира на Киевской, 3 комнаты, 76 м², 8 этаж, 110000 USD

Рассрочки в базе нет. Это специально: вопрос про рассрочку должен уйти человеку.

Также появляются два клиента: Айгуль в WhatsApp `+996555111222` и Нурлан в Instagram `ig_nurlan`.

## Demo / чат в терминале

```powershell
python -m app.ping_llm
python -m app.demo
python -m app.demo --interactive
```

`ping_llm` бьёт в OpenRouter без базы: проверка ключа и Gemini. `demo` нужен Postgres. Без флага прогоняет два сообщения:

```
Client > Еще продается квартира за 85000?
Plumo > Да, объект за 85 000 USD ещё доступен...

Client > А рассрочка есть?
Plumo > У меня нет информации о рассрочке. Я передам вопрос менеджеру.
[HANDOFF CREATED]
```

Под каждым ответом печатаются customer id, conversation id, канал, язык, решение роутера, модель, источники знаний, стоимость и задержка.

Интерактивный режим читает строки, пока не придёт пустая строка.

## API

Базовый префикс `/api/v1`. Схемы запроса и ответа описаны в Swagger, модели не текут наружу.

| Метод | Путь | Зачем |
| --- | --- | --- |
| POST | `/api/v1/messages` | нормализованное сообщение → `AgentResponse` |
| POST | `/api/v1/channels/{channel}/events` | сырое mock-событие канала |
| POST | `/api/v1/voice/transcribe` | mock STT по `audio_id` |
| POST | `/api/v1/voice/respond` | аудио → агент → mock audio id |
| GET | `/api/v1/customers/{id}` | карточка |
| GET | `/api/v1/customers/{id}/history` | история по всем каналам |
| GET | `/api/v1/conversations/{id}` | один диалог |
| GET | `/api/v1/handoffs` | очередь человеку |
| POST | `/api/v1/handoffs/{id}/accept` | взять диалог |
| POST | `/api/v1/handoffs/{id}/resolve` | закрыть передачу |
| GET | `/api/v1/knowledge` | база знаний |
| POST | `/api/v1/knowledge` | добавить факт |
| POST | `/api/v1/meetings` | создать встречу |
| GET | `/api/v1/metrics` | сводка, включая минуты и стоимость звонков |
| POST | `/api/v1/telephony/elevenlabs/v1/chat/completions` | реплика звонящего (Custom LLM, SSE) |
| POST | `/api/v1/telephony/elevenlabs/initiation` | приветствие входящего звонка |
| POST | `/api/v1/telephony/elevenlabs/post-call` | итог звонка (HMAC) |

Пример, с которым канал может начать интеграцию, не дожидаясь своего адаптера:

```json
{
  "channel": "whatsapp",
  "external_user_id": "+996555123456",
  "text": "Еще продается квартира за 85000?",
  "message_id": "wamid.1",
  "language_hint": "ru"
}
```

Каждый ответ несёт заголовки `X-Correlation-Id` и `X-Request-Id`. Тот же id пишется в лог и в `interaction_logs`, так что один запрос можно пройти от API до роутера, модели и базы.

Если задан `PLUMO_API_KEY`, все `/api/v1/*` кроме телефонии требуют заголовок `X-API-Key`.

Ошибки приходят JSON-ом: `error`, `message`, `correlation_id`. Нет ключа — 401. Пустой текст — 422 `invalid_message`. Нет клиента — 404. Незарегистрированный провайдер в production — 503.

Известные mock audio id: `mock_audio_apt`, `mock_audio_installment`, `mock_audio_hello`, `mock_audio_meeting`, `mock_audio_manager`.

## Где лежат AI-интерфейсы

| Интерфейс | Файл |
| --- | --- |
| Порты | `src/app/domain/ports.py` |
| Фабрика | `src/app/infrastructure/ai/factory.py` |
| Mock LLM и язык | `src/app/infrastructure/ai/mock_llm.py` |
| Mock STT/TTS | `src/app/infrastructure/ai/mock_speech.py` |
| Сборка | `src/app/container.py` |
| Оркестратор | `src/app/application/services/agent_service.py` |

Подключение живых провайдеров расписано в [INTEGRATION.md](INTEGRATION.md).

## Как подключить настоящую LLM

1. Реализовать `LLMProvider`: `generate_response`, `classify`, `summarize`, `extract_customer_data`.
2. Зарегистрировать экземпляр: `runtime.providers.register_llm("openai_small", provider)`.
3. Поставить `AI_MODE=production` и `SMALL_MODEL_PROVIDER=openai_small`. Для большой модели — своё имя и `BIG_MODEL_PROVIDER`.

`AgentService` не меняется. Фабрика в mock-режиме имена из env игнорирует и всегда отдаёт mock.

## Как подключить настоящий STT

Реализовать `STTProvider.transcribe(audio) -> Transcript`, вызвать `register_stt("google", provider)`, выставить `AI_MODE=production` и `STT_PROVIDER=google`. `VoiceService` остаётся тем же: аудио → текст → `AgentService` → текст → аудио.

## Как подключить настоящий TTS

То же для `TTSProvider.synthesize(text) -> AudioOutput`, `register_tts` и `TTS_PROVIDER`. Mock возвращает `audio_id`, не байты. Реальный адаптер может вернуть ссылку на файл или storage key в том же поле.

## Как добавить канал

Канал — это адаптер с `normalize_inbound` и `normalize_outbound`. Готовые mock-классы: `MockWhatsAppAdapter`, `MockTelegramAdapter`, `MockInstagramAdapter`, `MockVoiceAdapter` в `src/app/infrastructure/channels/mock_adapters.py`.

Два способа отдать сообщение в ядро:

- сам привести событие к `InboundMessage` и вызвать `POST /api/v1/messages`
- положить адаптер в `runtime.channels["whatsapp"]` и слать сырой payload на `POST /api/v1/channels/whatsapp/events`

Продажная логика в адаптер не кладётся.

## Как добавить модель

Малая и большая модели — два имени в фабрике, не два класса в `AgentService`. Роутер возвращает `small` или `big`, фабрика резолвит провайдера. Новый провайдер регистрируется под новым именем. Если нужна третья ступень, это уже смена `RouteDecision` и роутера, не смена оркестратора под конкретный SDK.

## Как добавить action

Модель (или политика ядра) возвращает `Action(type, payload)`. Пишет в базу `ActionExecutor`, не модель.

Сейчас `MockActionExecutor` умеет `schedule_meeting`, `request_phone`, `handoff`, `update_customer`. Новый тип добавляется в enum и в исполнитель. Для Google Calendar или CRM пишется другой класс с тем же методом `execute` и подменяется в `build_agent` в `container.py`.

## Как работает customer merge

`CustomerResolver` не вызывает модель.

- WhatsApp и телефон: номер во `external_user_id` — основной ключ. Повторный контакт с тем же номером находит ту же карточку.
- Telegram и Instagram без номера — отдельная карточка, ключ `(channel, external_id)`.
- Если в тексте появляется номер и карточка с этим номером уже есть, профили сливаются. Выживает карточка с телефоном.
- После merge каналы, диалоги, сообщения, встречи, handoff и логи смотрят на один `customer_id`. Исходная карточка остаётся со статусом `merged` и `merged_into_id`.

Историю нужно читать у выжившего id.

## Как работает router

`RuleBasedRouter` смотрит на текст и на то, сколько фактов нашлось. LLM он не вызывает.

В малую модель идут приветствие, прощание, да/нет, график, адрес, контакты, подтверждение времени и один простой факт из базы.

В большую — возражение, сравнение, деньги, рассрочка, смешанный язык, эмоция и отсутствие уверенного ответа.

Если малая модель вернула confidence ниже `SMALL_MODEL_CONFIDENCE_THRESHOLD` (по умолчанию 0.7), `AgentService` один раз переспрашивает большую. Причина маршрута станет `low_confidence_fallback`.

Позже рядом можно поставить `MLRouter` с тем же методом `select_model` и переключить `ROUTER`, не трогая агента.

Поиск по базе сейчас лексический: `SimpleKnowledgeRetriever`. Метод `retrieve(business_id, query)` можно заменить на эмбеддинги в `build_agent`.

## Как работает handoff

`evaluate_handoff` решает, звать ли человека. Поводы: клиент просит человека, горячий лид, готовность к встрече, вопрос вне базы, небезопасный ответ, недовольство, два непонятых хода подряд.

Запись `HandoffRequest` получает статус `PENDING`, затем `ACCEPTED` и `RESOLVED`. `MockHandoffProvider` только пишет лог. Telegram-уведомление потом реализуется тем же портом `notify`.

Встреча при этом всё равно сохраняется локально со статусом `PROPOSED`. Календаря нет.

## Что сейчас mock

- малая и большая LLM (`mock_small` = 0.001, `mock_big` = 0.01 за ответ)
- STT и TTS
- детектор языка (словарная эвристика за интерфейсом)
- уведомление человеку
- каналы
- календарь внутри `schedule_meeting`

Не mock, а настоящая логика на Postgres: клиенты, merge, память, база знаний, роутер, валидатор фактов, handoff, встречи, логи, метрики, API.

## Тесты

```powershell
pytest
```

Нужен запущенный Postgres. Юнит-тесты роутера и валидатора базу не спрашивают, но фикстуры интеграционных тестов поднимают `plumo_test`.

## Конфигурация

`AI_MODE=mock` включает mock LLM, STT, TTS, язык и каналы. `AI_MODE=production` берёт имена из `SMALL_MODEL_PROVIDER`, `BIG_MODEL_PROVIDER`, `STT_PROVIDER`, `TTS_PROVIDER`, `LANGUAGE_DETECTOR`, `HANDOFF_PROVIDER`. Незарегистрированное имя даёт 503, а не тихий откат в mock.

`ROUTER=rules` — текущий роутер. `DEFAULT_LANGUAGE=ru`. `DEFAULT_BUSINESS_ID` необязателен: если бизнес в базе один, берётся он.
