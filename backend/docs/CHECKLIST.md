# Что подключить: аккаунты, ключи, подписки

Ключи и пароли кладём только в `.env`. В чат, git и issues не отправляем. Порядок соответствует плану MVP ([../../README.md](../../README.md#mvp)): мессенджеры, телефония отложена. Цены и условия провайдеров сверять с их официальными страницами перед оплатой.

## Этап 1 — разработка (≈ $5–10)

- [ ] **OpenRouter** — ключ и баланс $5–10. В `.env`: `AI_MODE=production`, `SMALL_MODEL_PROVIDER=none`, `BIG_MODEL_PROVIDER=openrouter_big`, `OPENROUTER_API_KEY=…`, модели — как в `.env.example` ([MODELS.md](MODELS.md)). Проверка: `python -m app.ping_llm --repeat 3`.
- [ ] **Telegram-бот для менеджеров** — в Telegram @BotFather → `/newbot` → токен. Создать группу «Plumo менеджеры», добавить туда бота, написать любое сообщение, открыть `https://api.telegram.org/bot<ТОКЕН>/getUpdates` и взять `chat.id` (число с минусом).
      В `.env`: `HANDOFF_PROVIDER=telegram`, `TELEGRAM_BOT_TOKEN=…`, `TELEGRAM_MANAGER_CHAT_ID=-100…`.
- [ ] **Тестовый Telegram-бот бизнеса** — отдельный бот через @BotFather, подключается в кабинете ([../../docs/dashboard-channels.md](../../docs/dashboard-channels.md), раздел 4).
- [ ] **Временный публичный HTTPS** — `cloudflared` или ngrok, чтобы Telegram и Meta доставляли webhook на локальный стенд.

## Этап 2 — постоянный стенд (≈ €5–10 в месяц)

- [ ] **Сервер** — VPS (например, Hetzner CX22 или аналог) + домен + HTTPS. Деплой — [FULLSTACK.md](../FULLSTACK.md), раздел 4. Сгенерировать `PLUMO_API_KEY` и `CHANNEL_SECRET_KEY`.
- [ ] **Резервное копирование базы** и наблюдение за worker.

## Этап 3 — Meta: Instagram и WhatsApp (начать сразу)

Верификация и проверки Meta занимают дни, поэтому их запускаем параллельно с разработкой.

- [ ] **Meta Business** (https://business.facebook.com) — бизнес-аккаунт и верификация бизнеса.
- [ ] **Meta app** (https://developers.facebook.com) — одно приложение для Instagram и WhatsApp; роли тестировщиков; при необходимости App Review и режим Live. Что нужно для Instagram — [../../docs/dashboard-channels.md](../../docs/dashboard-channels.md), раздел 5.
- [ ] **WhatsApp Cloud API** — продукт WhatsApp в приложении, тестовый номер. Проверить: можно ли подключить номер, уже работающий в приложении WhatsApp Business, или нужен отдельный; ставки для Кыргызстана; правила окна ответа и шаблонов. Адаптер канала ещё нужно написать.

## Этап 4 — пилот с реальными клиентами

- [ ] **Юрист** — договор поручения обработки персональных данных с клиентом-бизнесом, сроки хранения и удаления переписки.
- [ ] **Носитель кыргызского** — вычитать фразы в `src/app/domain/phrases.py` и ответы модели из `app.bench`.
- [ ] **Условия обработки данных** у OpenRouter и провайдера модели — допустимы ли для данных реальных клиентов.

## Отложено: телефония

ElevenLabs (тариф Creator), номер Zadarma или Telnyx, 50 записей звонков для проверки кыргызского распознавания — см. [VOICE.md](../VOICE.md). Не покупаем до решения вернуться к звонкам.

## Сколько стоит один диалог (оценка)

| Что | Цена |
| --- | --- |
| Текст, Claude Haiku 5.5 через OpenRouter | ≈ $0.0003 за реплику, ≈ $0.003 за диалог из 8–10 реплик (замер 9 октября, [MODELS.md](MODELS.md)) |
| WhatsApp | по ставке Meta для KG — проверить |
| Telegram, Instagram Direct | плата канала за сообщения не ожидается — подтвердить по официальным условиям |
