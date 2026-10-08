# Голос и телефония

Решение: звонки ведёт **ElevenLabs Agents**, а Plumo подключён к нему как **Custom LLM**. Speech-to-speech модель (OpenAI Realtime) не берём.

## Почему так

| | ElevenLabs Agents + Plumo как Custom LLM | OpenAI Realtime (speech-to-speech) |
| --- | --- | --- |
| Один мозг для чата и звонка | Да. Каждая реплика идёт через `AgentService`: память, база знаний, роутер, валидатор, handoff | Нет. Модель слышит и говорит сама, наше ядро становится тулом сбоку |
| «Не выдумывать цены» | Валидатор проверяет ответ **до** синтеза | Голос генерируется сразу, проверить цену до того, как её услышат, нельзя |
| Роутер small/big | Работает: дешёвая модель на типовых репликах | Одна дорогая модель на каждую реплику |
| Кыргызский | Scribe распознаёт кыргызский. Синтез: Eleven v3 (есть «Kirghiz»), Flash v2.5 кыргызский **не** поддерживает | Кыргызский официально не заявлен |
| SIP / номер | SIP-транк: Zadarma/Telnyx → ElevenLabs | SIP есть (`sip.api.openai.com`) |
| Перебивание, VAD, паузы | Из коробки | Из коробки |
| Задержка | Выше: STT → наш HTTP → LLM → TTS | Ниже всех |
| Цена | Платформа за минуту + наша LLM с роутером | Аудиотокены: $32 / 1M на вход, $64 / 1M на выход |
| Замена провайдера | Голос меняется, ядро нет | Переписывать логику под модель |

Главный аргумент — правило продукта: факты только из базы. В STS-модели между «модель решила» и «клиент услышал» нет места для валидатора. Второй аргумент — экономика роутера: STS убивает его целиком.

Риск: кыргызский синтез в реалтайме. Если тест (неделя 1–2, 50 записей, WER на смешанной речи до ~20%) не пройдёт, работаем по запасному плану из продуктового документа: голос на русском, кыргызский в голосовых сообщениях чатов. Ядро от этого не меняется.

## Как идёт звонок

```
Покупатель → номер бизнеса → переадресация → номер Zadarma/Telnyx
  → SIP-транк → ElevenLabs Agent (STT, паузы, перебивание)
     ├─ initiation webhook → Plumo: кто звонит → приветствие + «в прошлый раз вы спрашивали…»
     ├─ каждая реплика → Plumo /v1/chat/completions → AgentService (channel=voice) → SSE
     └─ после звонка → Plumo post-call webhook → voice_calls (длительность, стоимость)
  ← TTS ← ответ
```

Ответ уходит в ElevenLabs одним куском после валидатора. Токены не стримим нарочно: иначе непроверенная цена успеет прозвучать.

## Эндпоинты Plumo

| Путь | Кто зовёт | Авторизация |
| --- | --- | --- |
| `POST /api/v1/telephony/elevenlabs/v1/chat/completions` | Custom LLM, каждая реплика | `Authorization: Bearer $ELEVENLABS_LLM_TOKEN` |
| `POST /api/v1/telephony/elevenlabs/initiation` | Начало входящего звонка | тот же Bearer (или `X-Plumo-Token`) |
| `POST /api/v1/telephony/elevenlabs/post-call` | После звонка | HMAC `ElevenLabs-Signature`, секрет `$ELEVENLABS_WEBHOOK_SECRET` |

Код: `src/app/api/routes/telephony.py` (HTTP), `src/app/infrastructure/telephony/elevenlabs.py` (формат), `src/app/application/services/call_service.py` (логика). Звонки лежат в таблице `voice_calls` (миграция `002_voice_calls`), реплики — в обычных `messages` того же клиента.

## Настройка ElevenLabs

1. Agent → **LLM: Custom LLM**. Server URL: `https://<host>/api/v1/telephony/elevenlabs/v1`, Model ID: `plumo`, API key: значение `ELEVENLABS_LLM_TOKEN`.
2. **System prompt** агента — только маркеры, логика живёт в Plumo:
   `plumo_caller={{system__caller_id}} plumo_call={{system__conversation_id}}`
3. **Security → Overrides**: разрешить first message и language. Включить conversation initiation webhook на `/initiation` с заголовком `Authorization: Bearer <token>`.
4. **Post-call webhook** на `/post-call`, секрет положить в `ELEVENLABS_WEBHOOK_SECRET`.
5. Голос и поведение — таблица в разделе «Чтобы звучало как человек».
6. **Phone numbers → SIP trunk**: импортировать номер, в ElevenLabs ACL или digest-авторизация. Звук 48 кГц — транк должен уметь ресемплинг.

## Чтобы звучало как человек

Слова и тон задаёт Plumo (`src/app/domain/phrases.py`), всё остальное — настройки агента в ElevenLabs:

| Настройка | Значение | Почему |
| --- | --- | --- |
| Голос | живой женский голос с русским/кыргызским акцентом из Voice Library, не «дикторский» | персона — Айпери, говорит в женском роде |
| TTS model | v3 Conversational (если тест кыргызского пройдёт), иначе Flash v2.5 для ru | v3 выразительнее, Flash быстрее |
| Stability | 0.4–0.5 | ниже — живее интонация, выше — монотоннее |
| Text normalisation | ElevenLabs | цифры «85 000» читает словами; модель пишет цифры, их проверяет валидатор |
| Turn eagerness | Normal | не перебивает человека на паузе |
| Interruptions | включены | клиент перебил — агент замолкает |
| Soft timeout | ~1.5 с, сообщение «Так, секунду, смотрю…» | наш ответ идёт через валидатор, пауза закрывается живой фразой |
| Silence / end call | ~15 с тишины → «Алло, вы меня слышите?» | как делает живой менеджер |
| Background sound | лёгкий офисный фон (по желанию) | меньше ощущение «робота в вакууме» |

## Номер

- **Zadarma**: виртуальный номер 312 (Бишкек) → настройки номера → External server → SIP URI `+<номер>@<sip-хост ElevenLabs>`. Неотвеченные переадресации должны отклоняться, а не возвращаться. SIP REFER у Zadarma по отзывам отдаёт 501, так что перевод на живого менеджера через REFER надо проверить заранее.
- **Telnyx**: у ElevenLabs есть готовая интеграция. Сначала проверить, есть ли номера +996 и какие документы нужны.
- Бизнес ставит переадресацию с обычного номера на виртуальный: «если не ответил» или «всегда». Для пилота «пропущенный звонок» хватит «если не ответил / занято».

## Локальная проверка

```powershell
$env:ELEVENLABS_LLM_TOKEN="dev"
uvicorn app.main:app --reload
ngrok http 8000   # https-адрес → Server URL в ElevenLabs
```

```powershell
curl -N -X POST http://127.0.0.1:8000/api/v1/telephony/elevenlabs/v1/chat/completions `
  -H "Authorization: Bearer dev" -H "Content-Type: application/json" `
  -d '{"messages":[{"role":"system","content":"plumo_caller=+996555111222 plumo_call=test1"},{"role":"user","content":"Еще продается квартира за 85000?"}]}'
```

## Чего пока нет

- Перевод звонка на живого менеджера (`transfer_to_number`). Сейчас агент говорит «передам менеджеру», handoff уходит в очередь, менеджер перезванивает.
- Привязка номера к бизнесу: пока берётся бизнес по умолчанию. Нужно, когда будет больше одного клиента.
- `VOICE_USD_PER_MINUTE` — заполнить по тарифу ElevenLabs, иначе `voice_cost_per_minute` в `/metrics` будет 0.
- Тексты приветствия на кыргызском должен вычитать носитель.
