# Промпт: свой телефонный мост → ElevenLabs Agents

Скопируйте блок ниже в кодового агента (Claude Code и т. п.), открытого в корне репозитория. Блок самодостаточен. Факты об API ElevenLabs сверены с документацией 9 октября 2026; поля, помеченные «проверить», агент обязан подтвердить живым запросом.

---

```text
Ты работаешь в репозитории Plumo (ветка от develop по gitflow, только backend/, в main не пушить).
Прочитай AGENTS.md, backend/README.md, backend/VOICE.md, backend/src/app/api/routes/telephony.py,
backend/src/app/infrastructure/telephony/elevenlabs.py, backend/src/app/application/services/call_service.py.

## Задача

Сделать отдельный телефонный мост (bridge): он принимает звонок от телефонного провайдера,
держит медиапоток звонка и передаёт голос в ElevenLabs Agents по WebSocket, а голос агента
возвращает в звонок. Мозг не меняется: ElevenLabs по-прежнему зовёт Plumo как Custom LLM
(/api/v1/telephony/elevenlabs/v1/chat/completions), каждая реплика идёт через AgentService
с валидатором. Мост не думает и не отвечает сам — он только возит звук и управляет звонком.

Зачем, если SIP-транк Zadarma/Telnyx → ElevenLabs уже описан в VOICE.md:
- плечо звонка у нас: перевод на живого менеджера, отбой, запись, таймауты — наши;
- провайдер не обязан уметь SIP-транк в ElevenLabs, достаточно медиапотока по WebSocket;
- caller ID, набранный номер и id звонка мы знаем сами и передаём явно.
Существующий SIP-путь не ломать: оба режима должны работать параллельно.

## Схема

  Покупатель → номер бизнеса → переадресация → номер провайдера
    → webhook провайдера → bridge: ответить, открыть медиапоток (μ-law 8 кГц, base64, кадры ~20 мс)
    → bridge ⇄ wss ElevenLabs Agent (STT, паузы, перебивание, TTS)
                      └─ каждая реплика → Plumo Custom LLM → AgentService (channel=voice)
    → после звонка ElevenLabs шлёт post-call webhook в Plumo, как сейчас.

## Проверенные факты ElevenLabs (официальная документация)

- WebSocket: wss://api.elevenlabs.io/v1/convai/conversation?agent_id=<id>.
  Приватный агент: сервер получает подписанный URL
  GET https://api.elevenlabs.io/v1/convai/conversation/get-signed-url?agent_id=<id>
  с заголовком xi-api-key → {"signed_url": "wss://..."}. Ключ только на сервере моста.
- Первым сообщением после открытия сокета клиент шлёт:
  {"type":"conversation_initiation_client_data",
   "dynamic_variables": {...},
   "conversation_config_override": {"agent": {"first_message": "...", "language": "ru|ky"}},
   "custom_llm_extra_body": {...}}
- Звук от звонящего: {"user_audio_chunk": "<base64>"} (без поля type).
- От сервера:
  conversation_initiation_metadata → conversation_initiation_metadata_event.{conversation_id,
      user_input_audio_format, agent_output_audio_format};
  audio → audio_event.{audio_base_64, event_id, is_final};
  interruption → interruption_event.event_id;
  ping → ping_event.{event_id, ping_ms} — отвечать {"type":"pong","event_id":<тот же>};
  client_tool_call → client_tool_call.{tool_name, tool_call_id, parameters, expects_response};
  user_transcript, agent_response — для логов и метрик.
- Ответ на инструмент: {"type":"client_tool_result","tool_call_id":"...","result":"...","is_error":false}.
- Форматы: pcm_8000 … pcm_48000, ulaw_8000. Для телефонии агенту ставится ulaw_8000
  и на вход (Advanced), и на выход (Voice/TTS) — тогда транскодинг не нужен.
  Мост обязан сверить оба формата из conversation_initiation_metadata и закрыть звонок
  с ошибкой в логе, если это не ulaw_8000.

## Проверить до кода (не выдумывать, записать результат в VOICE.md)

1. Провайдер. Нужен двусторонний медиапоток по WebSocket + API перевода звонка + номер,
   на который бизнес в Кыргызстане может переадресовать звонок.
   Кандидаты: Telnyx (Media Streaming / TeXML <Stream>), Twilio (Media Streams).
   Zadarma медиапоток по WebSocket, насколько известно, не даёт — для неё вариант
   SIP → свой Asterisk/FreeSWITCH (AudioSocket / mod_audio_stream) → bridge; это отдельная
   оценка. По каждому кандидату: номера +996 или переадресация на зарубежный номер,
   цена минуты, сохраняется ли caller ID при переадресации, формат кадров, перевод звонка.
   Выбор провайдера согласовать с пользователем, не решать самому.
2. custom_llm_extra_body: приходит ли он в Custom LLM как body["elevenlabs_extra_body"]
   (parse_llm_request уже читает оттуда caller_id, conversation_id, called_number, business_id).
   Подтвердить логом одного живого запроса. Может требоваться включить
   «Custom LLM extra body» в настройках агента.
3. Что подставляется в {{system__caller_id}} / {{system__called_number}} в WebSocket-сессии
   (вероятно, пусто). Вызывается ли workspace initiation webhook для WebSocket-разговоров
   (вероятно, нет — тогда приветствие берёт сам мост, см. ниже).
4. Что приходит в post-call webhook для WebSocket-разговора: нет metadata.phone_call,
   значит caller/called надо брать из conversation_initiation_client_data.dynamic_variables.
5. Задержка: регион, где поставить мост, относительно ElevenLabs и провайдера.

## Как устроить код

Один репозиторий, отдельный процесс (долгие WebSocket-соединения не держать в API-процессе).
Не микросервис с собственной БД: мост не ходит в PostgreSQL, всё про бизнес и клиента
знает Plumo.

backend/src/app/bridge/
  __init__.py
  __main__.py          — запуск: uvicorn app.bridge.server:app --port 8010
  server.py            — FastAPI: webhook провайдера (ответ на звонок) + WS медиапотока
  session.py           — CallBridge: две корутины (провайдер→EL, EL→провайдер), состояние звонка
  elevenlabs_ws.py     — формат сообщений EL: чистые функции parse/build, без I/O (как elevenlabs.py)
  providers/base.py    — Protocol MediaProvider: parse_inbound_event, build_audio, build_clear,
                         answer_call_response, transfer(call_id, number), hangup(call_id)
  providers/<выбранный>.py
  plumo_client.py      — httpx-клиент к Plumo: start_call(), позже can_transfer()

Поток одного звонка:
1. Webhook провайдера «входящий звонок» (call_id, from, to). Проверить подпись провайдера.
   Идемпотентность: повтор webhook с тем же call_id не открывает вторую сессию
   (словарь активных звонков в процессе; для нескольких процессов — позже, не сейчас).
   Ответить провайдеру командой «ответить и открыть двусторонний поток на wss://<bridge>/media».
2. На открытие медиапотока, параллельно:
   а) POST в Plumo /api/v1/telephony/elevenlabs/initiation с Bearer ELEVENLABS_LLM_TOKEN
      и телом {"caller_id": from, "called_number": to, "call_sid": call_id} —
      это уже существующий эндпоинт, он отдаёт first_message, language, dynamic_variables
      по карточке клиента и бизнесу набранного номера. Таймаут ~1 с; при сбое — нейтральное
      приветствие из domain/phrases.py, звонок не ронять.
   б) Получить signed URL и открыть WS ElevenLabs (ELEVENLABS_BRIDGE_AGENT_ID).
3. Отправить conversation_initiation_client_data: ответ Plumo + 
   custom_llm_extra_body {"caller_id", "called_number", "conversation_id": call_id провайдера}
   + те же значения в dynamic_variables (plumo_caller, plumo_called, plumo_call) для post-call.
   Аудио звонящего, пришедшее до готовности EL, буферизовать (ограничить, напр. 2 с), не терять.
4. Провайдер→EL: каждый media-кадр → {"user_audio_chunk": payload}. Без перекодирования.
5. EL→провайдер: audio → кадр провайдера в исходном порядке. interruption → команда провайдера
   «очистить буфер воспроизведения» (у Twilio это event "clear"), иначе агент договорит поверх
   перебившего клиента. ping → pong сразу.
6. Конец: отбой любой стороны закрывает обе стороны, отменяет обе корутины, снимает звонок
   из активных. Ни одна задача не должна висеть после звонка.

Сбои (обязательно, AGENTS.md):
- EL не открылся / упал в середине: проиграть короткую заранее синтезированную фразу
  «Извините, не слышу вас, менеджер перезвонит» (μ-law файл в репо можно, это не персональные
  данные) и создать заявку на обратный звонок через Plumo — не через модель; затем отбой.
  Если такого эндпоинта в Plumo нет — добавить минимальный, с business_id из набранного номера.
- Plumo недоступен на initiation — см. 2а. Custom LLM при сбое уже говорит voice_failure_phrase.
- Лимиты: максимальная длительность звонка, таймаут тишины на стороне моста как страховка,
  ограниченные повторы подключения к EL (1 повтор, не цикл).

Изоляция бизнесов: мост не выбирает бизнес сам. Он передаёт набранный номер, Plumo
определяет бизнес по contacts.voice_numbers. Номер провайдера должен быть в voice_numbers.

## Перевод на менеджера (вторая фаза, отдельный PR)

Сейчас перевода нет нигде. В мосте он становится возможен:
- на агенте EL клиентский инструмент transfer_to_manager (client tool, expects_response=true);
- мост получает client_tool_call → спрашивает Plumo (plumo_client.can_transfer: бизнес,
  режим диалога, номер дежурного менеджера, рабочее время) — решение принимает сервер,
  не модель;
- разрешено → провайдер переводит звонок, мост закрывает EL-сессию, Plumo отмечает handoff;
- запрещено или перевод не удался → client_tool_result с is_error, агент говорит, что менеджер
  перезвонит. Не обещать соединение, пока провайдер не подтвердил перевод.

## Конфигурация (.env.example — только имена, без значений)

TELEPHONY_PROVIDER=            # выбранный провайдер
<PROVIDER>_API_KEY=, <PROVIDER>_WEBHOOK_SECRET=
BRIDGE_PUBLIC_URL=             # https/wss адрес моста для провайдера
PLUMO_INTERNAL_URL=            # куда мост ходит в Plumo
ELEVENLABS_BRIDGE_AGENT_ID=    # отдельный агент с ulaw_8000 in/out; SIP-агент не трогать
ELEVENLABS_API_KEY=            # уже есть; теперь нужен и работающему мосту (signed URL)
Расширить app.elevenlabs_setup флагом --bridge: создаёт/обновляет второго агента с ulaw_8000,
теми же Custom LLM и post-call webhook, без initiation webhook.

## Логи и данные

- Не логировать аудио и полные номера: маскировать (+996 555 ***222). Не сохранять записи в git.
- Логировать: call_id провайдера, conversation_id EL, время ответа на звонок, время до первого
  аудио агента, число interruption, причина завершения.
- parse_post_call: если нет metadata.phone_call, брать caller/called из dynamic_variables
  plumo_caller/plumo_called. Покрыть тестом.

## Тесты

- Чистые функции elevenlabs_ws.py и провайдера: разбор каждого события, сборка кадров,
  неизвестные события игнорируются.
- CallBridge на фейковых WebSocket обеих сторон: порядок аудио сохраняется; interruption даёт
  clear; ping → pong; отбой клиента закрывает EL и наоборот; повтор webhook не создаёт вторую
  сессию; EL упал → фраза + заявка на обратный звонок; initiation Plumo таймаут → звонок идёт.
- Существующие тесты telephony не должны поменяться (SIP-путь цел).
- Живой звонок: RU, KY, смешанная речь; перебивание посреди ответа; молчание; отбой посреди
  ответа агента. Замерить: время до первого звука агента, задержку реплики
  (voice_calls.metadata.latency), сравнить с SIP-путём из VOICE.md.

## Готово, когда

- звонок через мост проходит целиком, реплики в messages того же клиента, voice_calls заполнен
  с правильным business_id;
- SIP-режим работает как раньше;
- VOICE.md: новый раздел «Свой мост» — схема, запуск, выбор провайдера с источниками,
  что проверено живым звонком и что нет; README backend обновлён по запуску;
- в отчёте: что изменено, какие тесты прогнаны (реальный вывод), что осталось
  неподтверждённым. Не выдумывать результаты.

Работай небольшими коммитами: (1) формат EL WS + тесты, (2) провайдер + тесты,
(3) CallBridge + сбои, (4) post-call/setup/доки, (5) перевод — отдельно, после согласования.
```

---

## Источники

- [WebSocket Agents](https://elevenlabs.io/docs/agents-platform/libraries/web-sockets), [справочник событий](https://elevenlabs.io/docs/agents-platform/api-reference/agents-platform/websocket)
- [Twilio register call](https://elevenlabs.io/docs/agents-platform/phone-numbers/twilio-integration/register-call) — требование ulaw_8000 на входе и выходе; перевод звонка при своём сервере ElevenLabs не делает
- [Custom LLM](https://elevenlabs.io/docs/eleven-agents/customization/llm/custom-llm); имя `elevenlabs_extra_body` подтверждено только сторонним [гайдом Zep](https://help.getzep.com/elevenlabs) — отсюда пункт «проверить»
