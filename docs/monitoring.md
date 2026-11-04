# Мониторинг API, базы, worker и очереди

Проверки не вызывают модель, ничего не отправляют и не показывают тексты, адреса БД, токены и персональные данные.

| Путь | Доступ | Ответ |
|---|---|---|
| `GET /health` | открыт | `{"status":"ok"}` — процесс жив; базу не трогает |
| `GET /health/db` | открыт | 200 `{"status":"ok"}` или 503 `{"status":"unavailable"}`; таймаут 2 с, причина только в логе |
| `GET /ops/status` | `Authorization: Bearer $OPS_TOKEN` | сводка ниже; без `OPS_TOKEN` на сервере — 404, с неверным — 401 |

`/ops/status` не проксируется кабинетом (BFF): его вызывает система мониторинга напрямую.

## Поля `/ops/status`

| Поле | Значение | Тревога |
|---|---|---|
| `status` | `ok` / `degraded` (нет живого worker или старейшее готовое задание старше 5 мин) / `unavailable` (503, нет БД) | не `ok` |
| `app_version`, `schema_version` | версия API и head миграций (`null` — схема не из миграций) | `schema_version` не равен ожидаемому |
| `commit` | первые 12 символов коммита API из `APP_COMMIT` или переменной хостинга (`RENDER_GIT_COMMIT` и др.); `unknown` — не задан | не равен выпущенному |
| `workers.alive` | worker с heartbeat моложе `stale_after_s` (45 с; пишется раз в 15 с) | `0` |
| `workers.commits` | коммиты живых worker (коммит — начало `worker_id`) | отличается от `commit` |
| `workers.last_heartbeat_age_s` | возраст последнего heartbeat любого worker | > 45 |
| `jobs.due`, `jobs.oldest_due_age_s` | задания, которые пора выполнять, и возраст старейшего | возраст растёт |
| `jobs.delayed_retries` | повторы с будущим `run_at` — это не просрочка | — |
| `jobs.expired_leases` | `running` с истёкшей арендой: worker умер на задании | > 0 долго |
| `jobs.failed_24h` | окончательно упавшие задания за сутки | рост |
| `deliveries_unknown` | ответы клиентам в `unknown`, ждут решения человека | > 0 |
| `notifications_failed_or_unknown_24h` | уведомления менеджеру `failed`/`unknown` за сутки | > 0 |
| `limits.service_spent_usd` / `service_limit_usd` | расход модели за UTC-сутки ([limits.md](limits.md)) | близко к пределу |
| `config` | режим окружения и модели, имена провайдеров, `present` — заданы ли переменные стенда (только да/нет), `problems` — что не годится для стенда | `problems` не пуст |

`config.problems`: `app_env_development`, `ai_mode_mock`, `model_provider_mock`, `handoff_provider_mock`, `worker_inside_api`, `public_base_url_not_https`, `missing:<ПЕРЕМЕННАЯ>`. Значения переменных в ответ не попадают. На `status` они не влияют: это проверка выпуска (smoke), а не тревога о сбое.

## Как воспроизвести отказы

- Нет БД: `docker compose stop db` → `/health` 200, `/health/db` и `/ops/status` 503.
- Worker остановлен: остановить `./dev.sh worker` → через 45 с `workers.alive = 0`, `status = degraded`.
- Задания копятся: worker остановлен, написать боту → `jobs.due` и `oldest_due_age_s` растут.
- Повтор с задержкой: 429 от Telegram → `delayed_retries`, без тревоги.

Проверки: `backend/tests/integration/test_ops_status.py`. Миграция `016_worker_heartbeats`.
