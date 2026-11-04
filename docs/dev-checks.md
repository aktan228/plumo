# Проверки разработчика

Точные команды для запуска и проверок на Linux и macOS. Windows: те же подкоманды через `.\dev.cmd`. Всё запускается без production-доступа и без ключей внешних сервисов.

Нужно: Python 3.12+, Docker с Compose v2, Node.js 22.18+ (для `node --test` с импортом TypeScript).

## Backend (из `backend/`)

| Что | Команда | Ожидаемо |
|---|---|---|
| Окружение | `./dev.sh setup` | `.venv`, зависимости, `.env` из `.env.example` |
| PostgreSQL | `./dev.sh db` | контейнер `db` в статусе healthy |
| Миграции и демо-данные | `./dev.sh seed` | `seeded business … (Demo Realty)` |
| API | `./dev.sh run` | http://127.0.0.1:8000/health → `{"status":"ok"}`, Swagger на `/docs` |
| Worker | `./dev.sh worker` | лог `worker_started`; остановка Ctrl+C |
| Worker один проход | `.venv/bin/python -m app.worker --once` | обработает готовые задания и выйдет |
| Unit-тесты, без БД | `./dev.sh test tests/unit` | все проходят |
| Все тесты, нужна БД | `./dev.sh test` | все проходят, около 5 минут |
| Линт | `./dev.sh lint` | `All checks passed!` |
| Приёмочный набор, без сети | `.venv/bin/python -m app.acceptance --mock` | отчёт в `work/acceptance/`; качество — только на живой модели, [ACCEPTANCE.md](../backend/docs/ACCEPTANCE.md) |

`.venv`, созданный через `uv`, не содержит pip: `./dev.sh setup` тогда ставит зависимости через `uv pip`.

### Миграции на пустой БД

Проверка, что цепочка миграций собирается с нуля, на отдельной временной базе:

```bash
docker compose exec -T db psql -U plumo -d plumo -c "CREATE DATABASE plumo_migcheck;"
DATABASE_URL=postgresql+asyncpg://plumo:plumo@localhost:5432/plumo_migcheck .venv/bin/alembic upgrade head
DATABASE_URL=postgresql+asyncpg://plumo:plumo@localhost:5432/plumo_migcheck .venv/bin/alembic downgrade base
docker compose exec -T db psql -U plumo -d plumo -c "DROP DATABASE plumo_migcheck;"
```

Ожидаемо: 21 миграция, head — `021_scenario_revisions`. Миграции 013–017 из main сохранены; Dashboard добавляет 018–021.

### Тестовая база

Integration-тесты удаляют и пересоздают все таблицы. По умолчанию они берут хост из `DATABASE_URL` и базу `plumo_test`, создавая её при необходимости. Другую базу задаёт `TEST_DATABASE_URL`.

Тесты отказываются запускаться, если в имени тестовой базы нет `test` или она совпадает с рабочей базой из настроек приложения (`DATABASE_URL` или `backend/.env`). Защита — `backend/tests/database_guard.py`.

## Frontend (из `frontend/`)

| Что | Команда | Ожидаемо |
|---|---|---|
| Зависимости | `npm install` | без ошибок |
| TypeScript | `npm run typecheck` | без ошибок |
| Сборка | `npm run build` | `Compiled successfully` |
| Тесты | `npm test` | 74 теста, 0 падений |

`npm run build` и `npm run dev` по очереди переписывают пути в `frontend/next-env.d.ts`. Это изменение не коммитим.

## Mock и live режим модели

`AI_MODE` выбирает, куда идут вызовы модели, распознавания и синтеза речи и определения языка:

- `mock` (по умолчанию в коде и в `.env.example`) — встроенные заглушки, без сети и расходов. Имена провайдеров из `.env` игнорируются.
- `production` — провайдеры по именам из `SMALL_MODEL_PROVIDER` и `BIG_MODEL_PROVIDER`. Незарегистрированное имя или отсутствующий ключ дают 503; тихого перехода в mock нет.

Уведомления менеджеру от `AI_MODE` не зависят: `HANDOFF_PROVIDER=telegram` отправляет настоящие сообщения и в mock-режиме.

Тесты всегда работают в mock: фикстура `settings` в `tests/conftest.py` задаёт его явно, независимо от `.env`.

Ваш `backend/.env` может описывать живой стенд (`AI_MODE=production`). Тогда `./dev.sh run`, `worker` и `demo` расходуют средства, а worker сразу берёт задания из очереди. Для локальной проверки без расходов переопределите режим на запуск: `AI_MODE=mock HANDOFF_PROVIDER=mock ./dev.sh worker`.

Как не включить mock на рабочем стенде: при `APP_ENV`, отличном от `development`, API проверяет только наличие `PLUMO_API_KEY` и `CHANNEL_SECRET_KEY`. Запрета на `AI_MODE=mock` нет, и при пропущенной переменной стенд ответит клиентам заглушкой. Поэтому в `.env` стенда задавайте `AI_MODE=production` явно и проверяйте его после деплоя.

## Встроенный и отдельный worker

Задания очереди выполняет отдельный процесс `python -m app.worker` (`./dev.sh worker`, сервис `worker` в `docker-compose.yml`). Число слотов задаёт `WORKER_CONCURRENCY`, по умолчанию 4.

При `CHANNEL_WORKER_ENABLED=true` тот же worker запускается внутри процесса API, с 1–2 слотами, и останавливается вместе с ним. По умолчанию флаг выключен: `./dev.sh run` без отдельного worker не отвечает в каналы и не шлёт уведомления менеджеру.

Несколько worker можно запускать одновременно: задания забираются через `SKIP LOCKED`, задание упавшего worker берётся снова после lease (120 с).
