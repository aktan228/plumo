# Что подключить: аккаунты, ключи, подписки

Ключи и пароли кладём только в `.env`. В чат, git и issues не отправляем.

## Этап 1 — сейчас, локально (≈ $0)

- [ ] **Gemini API key** — https://aistudio.google.com/apikey → Create API key. Бесплатный лимит хватит на разработку.
      В `.env`: `GEMINI_API_KEY=…`, `AI_MODE=production`, `SMALL_MODEL_PROVIDER=none`, `BIG_MODEL_PROVIDER=gemini_big`.
      Проверка: `python -m app.ping_llm --repeat 3` (модель, задержка, цена), затем `.\dev.cmd eval --provider gemini`.
      Gemini 2.5 Flash отключается 20.10.2026 — по умолчанию стоит 3.8 Flash с запасными, см. [MODELS.md](MODELS.md).
- [ ] **Telegram-бот для менеджеров** — в Telegram @BotFather → `/newbot` → токен. Создать группу «Plumo менеджеры», добавить туда бота, написать любое сообщение, открыть `https://api.telegram.org/bot<ТОКЕН>/getUpdates` и взять `chat.id` (число с минусом).
      В `.env`: `HANDOFF_PROVIDER=telegram`, `TELEGRAM_BOT_TOKEN=…`, `TELEGRAM_MANAGER_CHAT_ID=-100…`.
- [ ] **GitHub** — ссылка на репозиторий и доступ на запись, чтобы запушить `feature/voice-elevenlabs`.
- [ ] *(по желанию)* **Supabase** — https://supabase.com → New project, регион Frankfurt (eu-central-1) → Connect → «Transaction pooler» → строку целиком в `DATABASE_URL`. Бесплатный проект засыпает после недели без запросов.
- [ ] *(по желанию)* **OpenRouter** — пополнить на $10, чтобы сравнивать модели через `.\dev.cmd eval --provider openrouter --small … --big …`.

## Этап 2 — тест звонков (≈ $25–35 в месяц)

- [ ] **ngrok** — https://ngrok.com, бесплатный аккаунт → authtoken → `ngrok http 8000`. Даёт публичный HTTPS-адрес без сервера.
- [ ] **ElevenLabs** — https://elevenlabs.io, тариф Creator ($22 в месяц, первый месяц со скидкой). Звонки ≈ $0.08 за минуту поверх тарифа — проверить на странице цен.
      Настройка агента — 6 шагов в [VOICE.md](../VOICE.md). В `.env`: `ELEVENLABS_LLM_TOKEN` (придумать длинную случайную строку), `ELEVENLABS_WEBHOOK_SECRET` (из ElevenLabs), `VOICE_USD_PER_MINUTE=0.08`.
      На первом шаге можно звонить агенту прямо из браузера в ElevenLabs, номер не нужен.
- [ ] **Номер** — Zadarma (https://zadarma.com): городской номер Бишкека (312). Заранее спросить у них, какие документы нужны. Переадресация на ElevenLabs — в [VOICE.md](../VOICE.md), раздел «Номер». Альтернатива — Telnyx, если у них есть номера +996.

## Этап 3 — пилот с реальными клиентами

- [ ] **Биллинг Google Cloud** для Gemini (платный Tier 1). На бесплатном тарифе Google может использовать запросы для улучшения продуктов, с данными клиентов так нельзя.
- [ ] **WhatsApp Cloud API** — Meta Business (https://business.facebook.com) → верификация бизнеса → приложение на https://developers.facebook.com с продуктом WhatsApp. Номер не должен быть занят обычным WhatsApp. С 1 октября 2026 ответы платные: проверить ставку для Кыргызстана. Адаптер канала ещё нужно написать (вебхук → `POST /api/v1/messages` → отправка ответа).
- [ ] **Сервер** — VPS (Hetzner CX22 ≈ €5 в месяц или аналог) + домен + HTTPS. Деплой — [FULLSTACK.md](../FULLSTACK.md), раздел 4. Сгенерировать `PLUMO_API_KEY`.
- [ ] **Юрист** — договор поручения обработки персональных данных с клиентом-бизнесом, текст предупреждения о записи разговора.
- [ ] **Носитель кыргызского** — вычитать фразы в `src/app/domain/phrases.py`.
- [ ] **50 записей звонков** с согласия — тест распознавания кыргызского (WER).

## Сколько стоит один диалог (оценка)

| Что | Цена |
| --- | --- |
| Текст, Gemini Flash-Lite + Flash | ≈ $0.002–0.003 за диалог из 8–10 реплик |
| Звонок, ElevenLabs | ≈ $0.08 за минуту + текст |
| WhatsApp | по ставке Meta для KG, с октября 2026 |
