# Plumo AI Core — руководство для лида и главного разработчика

Документ для людей, которые принимают архитектуру и подключают каналы, кабинет и живые провайдеры. Здесь не «как запустить docker», а что сделано в ядре, зачем так, и что происходит с одним сообщением под капотом.

Код: репозиторий [aktan228/plumo](https://github.com/aktan228/plumo), ветка `feature/ai-integration`, каталог `backend/`. Локальная рабочая копия — этот репозиторий. Интеграция адаптеров — `INTEGRATION.md`. Команды запуска — `README.md`.

Автор ядра не трогает фронт, лендинг и прод-каналы. Контракт для них — REST `/api/v1`.

---

## 1. Что это за продукт

Plumo — **AI-менеджер по продажам недвижимости** (демо-бизнес Demo Realty). Клиент пишет из WhatsApp, Instagram, Telegram или звонит — для ядра это одно и то же: нормализованное `InboundMessage`. Ответ всегда `AgentResponse`.

Правило продукта, которое ядро **гарантирует независимо от модели**:

> Цена, наличие, рассрочка, адрес, график, метраж, этаж — только из базы знаний и карточки бизнеса. Нет факта → отказ и (если вопрос фактический) handoff человеку. Модель не имеет права «додумать».

Это не чат-бот с промптом. Это **модульный монолит**: оркестратор + порты + адаптеры. Заменить Gemini на Qwen или OpenAI — новый класс за `LLMProvider`. Переписать продажную логику из-за смены SDK не нужно.

---

## 2. Что сделано сейчас (границы поставки)

| Слой | Состояние |
| --- | --- |
| Пайплайн сообщения (клиент → память → KB → роутер → LLM → валидатор → actions → лог) | Работает |
| PostgreSQL, Alembic, репозитории | Работает |
| Один клиент, merge по телефону, история по всем каналам | Работает |
| Rule-based роутер small/big | Работает |
| Валидатор фактов + grounded fallback | Работает |
| Handoff очередь PENDING → ACCEPTED → RESOLVED | Работает |
| Встречи со статусом PROPOSED (без Google Calendar) | Работает |
| REST + Swagger | Работает |
| OpenRouter (Gemini 2.5 Flash или `openrouter/free`) | Подключён адаптером |
| STT / TTS | Mock (`audio_id` → текст / текст → `audio_id`) |
| WhatsApp / Telegram / Instagram SDK | Mock-адаптеры формы payload |
| Кабинет менеджера / лендинг | Вне этого репозитория |
| Эмбеддинги, ML-роутер, fine-tune Qwen | Не в этой поставке; порты уже есть |

---

## 3. Стек

| Зачем | Чем |
| --- | --- |
| Язык | Python 3.12+ |
| HTTP | FastAPI, Uvicorn |
| БД | PostgreSQL 16, SQLAlchemy 2 async, asyncpg |
| Миграции | Alembic (`001_initial`) |
| Конфиг | pydantic-settings, `.env` (секреты не в Settings-логах) |
| LLM HTTP | httpx → OpenRouter Chat Completions |
| Тесты | pytest + pytest-asyncio |
| Контейнеры | Docker Compose: `db` + `api` |
| Стиль кода | Ports & adapters, composition root в `container.py` |

Зависимости — `pyproject.toml`. Ключ `OPENROUTER_API_KEY` читает только `OpenRouterLLMProvider` из окружения, в structured logs поля с `key`/`secret`/`token` вычищаются.

---

## 4. Карта кода

```
src/app/
  domain/           сущности, enum, ошибки, события, порты (контракты)
  application/      сервисы: агент, роутер, KB, валидатор, handoff, память
  infrastructure/   Postgres, OpenRouter, mock LLM/STT/TTS, mock-каналы
  api/              REST-схемы и роуты
  container.py      ЕДИНСТВЕННОЕ место, где собираются адаптеры
  config.py         имена провайдеров, не ключи
  demo.py           терминальный чат
  ping_llm.py       проверка ключа без БД
  seed.py           Demo Realty + 2 квартиры
```

`AgentService` **не импортирует** OpenRouter, httpx, SQLAlchemy-модели строк. Он зависит от протоколов из `domain/ports.py`.

Порты (сокращённо): `LLMProvider`, `STTProvider`, `TTSProvider`, `Router`, `LanguageDetector`, `KnowledgeRetriever`, `ActionExecutor`, `ChannelAdapter`, `HumanHandoffProvider`, `EventBus` + store-протоколы.

---

## 5. Пайплайн одного сообщения

```
канал / REST
  → InboundMessage
  → CustomerResolver          # кто это
  → Memory + Conversation     # история
  → KnowledgeRetriever        # что можно говорить
  → ContextBuilder            # единственный контекст для модели
  → RuleBasedRouter           # small или big, без LLM
  → LLMProvider.generate      # черновик текста
  → ядро правит текст         # human / unknown / junk / role
  → ResponseValidator         # цифры и факты
  → evaluate_handoff          # звать ли человека
  → ActionExecutor            # встреча, телефон, handoff в БД
  → Memory.summarize          # сжатие карточки (локально, без HTTP)
  → interaction_logs + usage
  → AgentResponse
```

Оркестратор: `src/app/application/services/agent_service.py`, метод `process_message`.

### Контракт на входе

```python
InboundMessage(
    channel="whatsapp",
    external_user_id="+996555123456",
    text="Еще продается квартира за 85000?",
    message_id="wamid.1",
    language_hint="ru",
)
```

Ядро не знает, WhatsApp это или кабинет. Канал — строка из enum.

### Контракт на выходе

`AgentResponse`: текст, `customer_id`, `conversation_id`, маршрут (`small`/`big` + reason), модель, confidence, actions, handoff, источники KB, usage (токены, стоимость, latency), `correlation_id`.

Тот же id лежит в заголовке `X-Correlation-Id`, в логе и в `interaction_logs`. Один запрос можно пройти от API до модели.

---

## 6. Под капотом: разбор реальных реплик

Seed кладёт два объекта Demo Realty:

1. Чуйская, 2 комнаты, 58 м², 5 этаж, **85 000 USD**
2. Киевская, 3 комнаты, 76 м², 8 этаж, **110 000 USD**

Рассрочки в KB **нет** специально.

### Пример A. «Какие есть квартиры?»

1. `analyze_message` ставит `property_details=True` → вопрос фактический.
2. Retriever: мало ключевых совпадений → **fallback: все активные объекты** каталога (иначе модель не увидит список).
3. Роутер: два хита без конкретной цифры → `big / comparison`.
4. OpenRouter получает system prompt: инструкции + карточка бизнеса + оба объекта + последние реплики. Ответ жёстко JSON:

```json
{
  "text": "В нашей базе сейчас две квартиры: ...",
  "actions": [],
  "handoff_required": false,
  "confidence": 0.8
}
```

5. Валидатор сверяет числа `85000`, `110000`, `58`, `76` с корпусом KB. Лишняя цифра → `invented_number`, текст заменяется отказом.
6. Handoff не создаётся: факт есть в базе.

### Пример B. «Есть рассрочка?»

1. Сигнал `installment`.
2. В корпусе KB нет «рассроч» / «ипотек» → `answerable=False`, topic=`installment`.
3. Ядро **не доверяет** модели подтвердить рассрочку. Подставляется фиксированная фраза из `phrases.py`, создаётся handoff `no_knowledge`.
4. Если модель всё же напишет «да, рассрочка есть», валидатор режет это как `invented_installment`.

### Пример C. «Нужна более дешёвая квартира для двух человек»

Раньше ломалось: в лексиконе HUMAN было голое слово «человек», ядро думало «позовите человека» и сразу слало менеджеру.

Сейчас HUMAN — явные фразы: `менеджер`, `оператор`, `позовите человека`, `живой оператор`, `соедините`, `адам`. «Для двух человек» **не** human_request.

Роутер видит `money` («дешевле») → `big`. Модель сравнивает два объекта. Валидатор пропускает 85 000, потому что число есть в KB.

### Пример D. «Расскажи, как тебя создали как ИИ»

Вопрос **не фактический** (нет цены, объекта, адреса). Если модель отвечает мусором (`User Safety`, короткий JSON, английский отказ), `is_unusable_reply` ловит черновик.

- фактический вопрос + есть KB → цитата объектов (`quote_knowledge`);
- **не** фактический → `ROLE_PHRASE_RU`: «я ассистент по объектам, про модель не рассказываю, давайте к квартирам».

Раньше любой junk падал в цитату каталога — отсюда дамп квартир на вопрос про ИИ. Это починено в `agent_service` + `grounded_reply.py`.

### Пример E. Клиент просит менеджера

«Позовите оператора» → `human_request` → фиксированная фраза «передам диалог менеджеру» + `HandoffRequest` со статусом `PENDING`. Модель здесь не нужна для текста.

---

## 7. Как устроена «голова» без нейросети

Лексикон `src/app/domain/text_signals.py` — не ML. Явные маркеры RU/KY: приветствие, рассрочка, цена, объект, возражение, эмоция, встреча, горячий лид.

Им пользуются **три независимых места**:

| Кто | Зачем |
| --- | --- |
| `RuleBasedRouter` | small vs big |
| `ResponseValidator.assess` | можно ли ответить из KB |
| `evaluate_handoff` | звать ли человека |

Роутер **никогда не вызывает LLM**. Это дёшево и предсказуемо.

**Small** (дешёвый тир): привет, прощание, да/нет, график, адрес, контакты, один простой факт KB, запрос человека.

**Big**: возражение, сравнение, деньги, рассрочка, mixed RU+KY, эмоция, нет уверенного хита.

Если small вернул `confidence < 0.7` (`SMALL_MODEL_CONFIDENCE_THRESHOLD`), агент **один раз** зовёт big, reason=`low_confidence_fallback`. Оба вызова пишутся в `ai_usage_logs`.

Позже `MLRouter` с тем же `select_model` ставится через `ROUTER=ml` в `container._router`. Агент не меняется.

---

## 8. База знаний и контекст модели

`SimpleKnowledgeRetriever` — лексический score: совпадение чисел (+5), токены ≥4 символов (+1), каталожный запрос про квартиры (+2). Если score всех нулевой, в контекст всё равно кладутся объекты бизнеса (маленький каталог). Выдумки по-прежнему режет валидатор.

`ContextBuilder` отдаёт модели только:

- `AGENT_INSTRUCTIONS` (не выдумывать факты);
- карточку бизнеса (имя, описание, часы, контакты, правила);
- hits KB;
- summary клиента + important_facts;
- последние 8 сообщений;
- текущую реплику и язык.

Не отдаётся весь архив клиента и не отдаются чужие бизнесы.

Эмбеддинги = новый класс с методом `retrieve` и одна строка в `build_agent`. Форма `KnowledgeHit` та же.

---

## 9. Валидатор — последний шлюз

`ResponseValidator.validate(draft, context)`:

- любая группа цифр ≥4 знаков в ответе должна быть в KB/карточке (`85 000` нормализуется в `85000`);
- «76 м² / 8 этаж» без этих цифр в корпусе → `invented_detail`;
- утверждение рассрочки без слова в KB → `invented_installment`;
- «ещё продаётся» без маркеров наличия в корпусе → `invented_availability`.

Небезопасный фактический ответ с KB заменяется цитатой объектов и проверяется ещё раз. Если и это плохо — фраза «уточню у менеджера».

**Нельзя выключать валидатор «потому что Gemini умный».** Бесплатные и коммерческие модели одинаково галлюцинируют цены.

---

## 10. Клиент: один человек — одна карточка

`CustomerResolver` модель не вызывает.

- WhatsApp / голос: ключ — телефон в `external_user_id`.
- Telegram / Instagram без номера: ключ `(channel, external_id)`, отдельная карточка.
- Клиент в Telegram написал `+996…`, а WhatsApp с этим номером уже есть → **merge**. Выживает карточка с телефоном. Каналы, диалоги, сообщения, встречи, handoff и логи переезжают. Старая карточка: `status=merged`, `merged_into_id`.

Историю в кабинете читать у **выжившего** `customer_id`: `GET /api/v1/customers/{id}/history`.

---

## 11. Handoff и действия

Чистое решение `evaluate_handoff` (без I/O). Причины по силе: hot_lead, встреча, просьба человека, нет знания, небезопасный ответ, недовольство, два «непонятых» хода.

`ActionExecutor` пишет в БД, модель сама в таблицы не ходит. Типы: `schedule_meeting`, `request_phone`, `handoff`, `update_customer`.

Встреча = `PROPOSED` локально. Google Calendar — другой executor с тем же `execute`, подмена в `build_agent`.

Уведомление менеджеру в Telegram — порт `HumanHandoffProvider.notify`. Сейчас mock пишет лог.

---

## 12. Как подключена живая модель

```
AI_MODE=production
SMALL_MODEL_PROVIDER=openrouter_small
BIG_MODEL_PROVIDER=openrouter_big
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_SMALL_MODEL=google/gemini-2.5-flash
OPENROUTER_BIG_MODEL=google/gemini-2.5-flash
```

`AI_MODE=mock` — фабрика **игнорирует** имена и всегда отдаёт `MockLLMProvider` (скрипты по ключевым словам). Это защита от случайного боевого биллинга.

В production незарегистрированное имя → `ProviderUnavailable` → HTTP **503**, тихого отката на mock нет.

`OpenRouterLLMProvider.generate_response` — один HTTP POST. `summarize` и `extract_customer_data` считаются **локально** (mock-логика), чтобы не жечь второй/третий запрос на каждое сообщение.

Парсер ответа: JSON, JSON в markdown-fence, или сырой текст как `text`.

Если на ключе нет кредитов, Gemini отвечает **402**. Для отладки можно `OPENROUTER_*_MODEL=openrouter/free` — бесплатно, но 2–15 секунд на реплику и нестабильный JSON.

Проверка ключа без Postgres: `python -m app.ping_llm`.

Чат: `python -m app.demo --interactive` (нужен Postgres + seed).

---

## 13. База данных

Таблицы: `businesses`, `knowledge_items`, `customers`, `customer_channels`, `conversations`, `messages`, `customer_summaries`, `handoff_requests`, `meetings`, `interaction_logs`, `ai_usage_logs`.

JSONB только у metadata, contacts, actions, снимка последних сообщений. Факты объектов — обычный text, не «магия в json».

Seed идемпотентен: бизнес Demo Realty, график 09:00–18:00, адрес на пр. Чуй, две квартиры, клиенты Айгуль (WA `+996555111222`) и Нурлан (IG `ig_nurlan`).

---

## 14. API, которое можно отдавать каналам сегодня

Префикс `/api/v1`. Swagger: `/docs`.

Главный вход, **без** написания адаптера в этом процессе:

`POST /api/v1/messages`

```json
{
  "channel": "whatsapp",
  "external_user_id": "+996555123456",
  "text": "Еще продается квартира за 85000?",
  "message_id": "wamid.1",
  "language_hint": "ru"
}
```

Сырой webhook: `POST /api/v1/channels/{channel}/events` — нормализует mock-адаптер.

Ещё: voice transcribe/respond (mock), карточка и история клиента, очередь handoff accept/resolve, CRUD знаний, создание встречи, `/metrics`, `/health`.

Пустой текст → 422. Нет бизнеса → 404. Нет провайдера в production → 503.

---

## 15. Как бэкенду подключать своё (коротко)

Детальные сниппеты — `INTEGRATION.md`. Принцип:

1. Реализовать протокол (`LLMProvider`, `ChannelAdapter`, …).
2. `register_*` в фабрике **или** положить экземпляр в `container.py`.
3. Имя в `.env`.
4. Не импортировать SDK в `AgentService`, роутер, валидатор, резолвер.

Канал: либо сами нормализуете и бьёте в `/messages`, либо кладёте адаптер в `runtime.channels`.

---

## 16. Что сознательно mock и что уже «настоящее»

Настоящее: клиенты, merge, память, KB, роутер, валидатор, handoff, встречи в Postgres, логи, метрики, REST, OpenRouter-адаптер.

Mock: STT/TTS, детектор языка (словари), уведомление человеку, WhatsApp/Telegram SDK, календарь снаружи, скриптовый LLM при `AI_MODE=mock`.

---

## 17. Ограничения, о которых лиду нужно знать

- Поиск по KB лексический: «двушка у Филармонии» не найдёт объект без этих слов. Лечится эмбеддингами за тем же портом.
- Роутер на словах: опечатки и редкие формулировки улетают в `big / no_confident_answer`.
- Бесплатная модель медленная и иногда отдаёт safety-мусор — ядро это глушит, но тон ответов хуже, чем у Gemini с кредитами (~$5 на OpenRouter).
- Голос и мессенджеры ещё не прод.
- Fine-tune Qwen / LoRA — следующий этап, не часть текущего монолита.
- Не коммитить `.env` и ключи.

---

## 18. Как проверить за 10 минут

```powershell
# Postgres на 5432, venv, pip install -e ".[dev]"
alembic upgrade head
python -m app.seed
python -m app.ping_llm
python -m app.demo --interactive
uvicorn app.main:app --reload   # http://127.0.0.1:8000/docs
pytest
```

Минимальный сценарий в демо:

1. «какие есть квартиры» → две из seed, без handoff.
2. «есть рассрочка?» → отказ + `[HANDOFF CREATED]`.
3. «дешевле для двух человек» → двушка 85 000, **без** handoff.
4. «как тебя создали» → роль ассистента, **не** дамп каталога.

Смотреть `logs` в ответе API и таблицу `interaction_logs`: `route`, `route_reason`, `model`, `knowledge_sources`, `handoff`.

---

## 19. Как это стыкуется с остальной командой

| Команда | Что делать с ядром |
| --- | --- |
| Backend каналов | Нормализовать webhook → `POST /messages` или адаптер. Не класть продажи в адаптер. |
| Кабинет | Читать customers/history/handoffs/knowledge/meetings/metrics. Accept/resolve handoff. |
| Лид / ML | Менять провайдеров и retriever. Не отключать валидатор. |
| Продукт | Факты только через `knowledge_items` и карточку бизнеса. Рассрочка появится в ответах, когда появится в KB. |

События шины (in-memory): `message_received`, `customer_created`, `customer_merged`, `message_processed`, `handoff_requested`, `meeting_scheduled`. Брокер — другой `EventBus`, подписка та же.
