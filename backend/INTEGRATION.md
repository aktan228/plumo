# Как подключить реальный AI к Plumo

Сейчас цепочка такая:

```
AgentService
  → LLMProvider
    → MockLLMProvider
```

Чтобы поставить OpenAI, Gemini, Claude или свою модель, пишется новый класс, он регистрируется в фабрике и выбирается конфигурацией. `AgentService`, память, база знаний, роутер, API и таблицы не переписываются.

То же самое для STT, TTS, языка и, отдельно, для роутера.

## Где граница

Порты лежат в `src/app/domain/ports.py`.

Фабрика — `AIProviderFactory` в `src/app/infrastructure/ai/factory.py`.

Сборка — `build_runtime` и `build_agent` в `src/app/container.py`. Это единственное место, куда можно добавить `import` вендорного SDK.

`AgentService` просит модель так:

```python
provider = self.llm_for_tier(route.model)  # "small" или "big"
generation = await provider.generate_response(context, route)
```

Он не знает, mock это или сеть.

Пока `AI_MODE=mock`, фабрика имена провайдеров игнорирует и отдаёт mock. Это защита от случайного боевого вызова.

## LLM

### 1. Класс

Новый файл, например `src/app/infrastructure/ai/openai_llm.py`. Наследник не нужен: достаточно методов протокола.

```python
class OpenAILLMProvider:
    def __init__(self, name: str, model: str) -> None:
        self.name = name
        self.model = model

    async def generate_response(self, context, route):
        # Здесь вызывается SDK.
        # В промпт можно класть только context: инструкции, бизнес,
        # knowledge, карточку, summary, последние реплики и текущий текст.
        # Цену, которой нет в context.knowledge, модель попросить может,
        # но ResponseValidator такой ответ не выпустит.
        ...

    async def classify(self, text, labels):
        ...

    async def summarize(self, messages, previous):
        ...

    async def extract_customer_data(self, text):
        ...
```

`generate_response` возвращает `LLMGeneration`: текст, actions, confidence, имя модели, токены и стоимость. Actions — это намерение (`schedule_meeting`, `handoff`, `update_customer`, `request_phone`). В базу их применяет `ActionExecutor`, не провайдер.

Ключ API читается внутри этого класса из своего env, например `OPENAI_API_KEY`. В общий `Settings` и в логи его класть не нужно. Структурный логгер выкидывает поля, в имени которых есть key, secret, token, password.

### 2. Регистрация

В `build_runtime` в `src/app/container.py`, после создания фабрики:

```python
providers = AIProviderFactory(settings)
if not settings.mock_mode:
    providers.register_llm("openai_small", OpenAILLMProvider("openai_small", "gpt-4.1-mini"))
    providers.register_llm("openai_big", OpenAILLMProvider("openai_big", "gpt-4.1"))
```

### 3. Конфигурация

```
AI_MODE=production
SMALL_MODEL_PROVIDER=openai_small
BIG_MODEL_PROVIDER=openai_big
```

Если имя не зарегистрировано, фабрика кидает `ProviderUnavailable`, API отвечает 503. Тихого перехода на mock в production нет.

Малая и большая модели могут быть одним классом с разным `model`. Роутер по-прежнему решает, кого звать.

## Что останется даже с живой моделью

`ResponseValidator` смотрит черновик до записи ответа.

- число, которого нет в базе знаний и в карточке бизнеса, не уходит клиенту
- подтверждение рассрочки без слова «рассрочка» в базе не уходит
- подтверждение наличия без такого факта в базе не уходит
- вопрос, на который в контексте нет опоры, заменяется фразой «уточню у менеджера» и создаёт handoff

Провайдер может быть болтливым. Наружу уйдёт только то, что валидатор пропустил.

`ContextBuilder` собирает `AgentContext` без привязки к вендору. В живой промпт имеет смысл сериализовать именно его, а не всю историю клиента.

## STT

Интерфейс:

```python
async def transcribe(self, audio: AudioInput) -> Transcript:
    ...
```

`AudioInput` сейчас несёт `audio_id`. Реальный адаптер может трактовать его как путь, storage key или id звонка и вернуть `Transcript(text, language, audio_id)`.

Регистрация:

```python
providers.register_stt("google", GoogleSTTProvider())
```

```
AI_MODE=production
STT_PROVIDER=google
```

`VoiceService` не меняется. Маршрут `POST /api/v1/voice/respond` уже делает transcribe → `AgentService` → synthesize.

Mock знает фиксированные id (`mock_audio_apt` и остальные, список в README) и не декодирует байты.

## TTS

```python
async def synthesize(self, text: str) -> AudioOutput:
    ...
```

`AudioOutput.audio_id` — ссылка, которую канал потом отдаст клиенту. Байты в ядро тащить не обязательно: их может хранить сам адаптер и вернуть id.

```python
providers.register_tts("eleven", ElevenTTSProvider())
```

```
TTS_PROVIDER=eleven
```

## Язык

```python
async def detect(self, text: str) -> str:
    # "ru" | "ky" | "mixed" | "unknown"
    ...
```

```python
providers.register_language("fasttext", FastTextDetector())
```

```
LANGUAGE_DETECTOR=fasttext
```

Детектор сохраняет язык в `customers.language`. Если карточка уже была на другом языке, сервис памяти ставит `mixed`.

Mock-детектор — это словарь в `detect_language`. Его можно выбросить целиком.

## Роутер

Роутер не ходит в LLM. Сейчас это `RuleBasedRouter.select_model(context) -> RouteDecision`.

Свой роутер:

```python
class MLRouter:
    async def select_model(self, context) -> RouteDecision:
        return RouteDecision(model="big", reason="ml_router", confidence=0.81)
```

В `container._router`:

```python
if settings.router == "ml":
    return MLRouter()
```

```
ROUTER=ml
```

`AgentService` уже вызывает `self.router.select_model`. Менять его не нужно.

Порог fallback малой модели — `SMALL_MODEL_CONFIDENCE_THRESHOLD`. Если малый провайдер вернул confidence ниже порога, оркестратор сам зовёт большой и ставит reason `low_confidence_fallback`. Это поведение ядра, не провайдера.

## Канал

Два контракта.

Нормализованный, его достаточно для первой интеграции:

`POST /api/v1/messages` с полями `channel`, `external_user_id`, `text`, опционально `message_id`, `customer_id`, `timestamp`, `language_hint`, `metadata`, `business_id`.

Ответ — `AgentResponse`: текст, ids, маршрут, модель, confidence, actions, handoff, источники, usage, latency, correlation id.

Сырой, если нормализация должна жить в этом процессе:

```python
class WhatsAppAdapter:
    channel = "whatsapp"

    def normalize_inbound(self, event: dict) -> InboundMessage:
        ...

    def normalize_outbound(self, response) -> dict:
        ...
```

В `container._channels` для production положить экземпляр в словарь по имени канала. События идут на `POST /api/v1/channels/whatsapp/events`.

Mock-адаптеры показывают ожидаемую форму payload для WhatsApp (`from`, `text`, `id`), Telegram (`message.chat.id`, `message.text`), Instagram (`sender.id`, `message.text`) и голоса (`caller`, `text`). Голос с одним `audio_id` идёт через `/voice/respond`, не через этот адаптер.

## Action

Протокол:

```python
async def execute(self, actions: list[Action], ctx: ActionContext) -> list[ActionResult]:
    ...
```

`MockActionExecutor` пишет встречу в таблицу `meetings` и handoff в `handoff_requests`. Это и есть mock календаря.

Боевой исполнитель подменяется в `build_agent`:

```python
actions=GoogleCalendarActionExecutor(...)
```

или расширяется: новый `ActionType`, новая ветка. `AgentService` по-прежнему только передаёт список actions.

Встреча, созданная ядром, имеет статус `PROPOSED`. Подтверждение календарём может обновить статус, не ломая контракт `Meeting`.

## Handoff-уведомление

`HumanHandoffProvider.notify(handoff)` вызывается после записи в базу. Mock пишет structured log.

Свой транспорт:

```python
class TelegramHandoffProvider:
    async def notify(self, handoff) -> None:
        ...
```

Подключить его в `_handoff_provider`, когда `HANDOFF_PROVIDER=telegram` и `AI_MODE=production`. Создание записи, статусы `PENDING / ACCEPTED / RESOLVED / CANCELLED` и причины остаются в `HandoffService`.

## База знаний

`SimpleKnowledgeRetriever.retrieve` ищет по словам и числам среди активных записей бизнеса. `AgentService` видит только метод `retrieve`.

Эмбеддинги — новый класс с тем же методом и замена одной строки в `build_agent`. В контекст модели по-прежнему попадут `KnowledgeHit`, и валидатор будет опираться на их `content`.

## События

Внутренняя шина — `InMemoryEventBus`. События: `message_received`, `customer_created`, `customer_merged`, `message_processed`, `handoff_requested`, `meeting_scheduled`, `conversation_completed`.

Подписчик вешается через `events.subscribe(name, handler)` в `build_runtime`. Чтобы унести это в брокер, пишется другой класс с `publish` / `subscribe` и подменяется там же. Сервисы публикуют `DomainEvent` и транспорт не выбирают.

## Чего не делать

- не импортировать SDK в `AgentService`, роутер, резолвер клиента или валидатор
- не отключать валидатор, чтобы «модель сама разберётся»
- не отвечать фактом, которого нет в `knowledge` и в карточке бизнеса
- не логировать ключ
- не писать в базу из провайдера напрямую

Если после замены адаптера ломается ответ, сначала смотри `interaction_logs`: там маршрут, модель, источники, текст, handoff и стоимость одного `correlation_id`.
