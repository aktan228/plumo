# Backend Plumo

Целевой стек: Python + FastAPI + PostgreSQL. Сейчас создана структура; сервер, зависимости и миграции ещё не реализованы.

Созданы Python-пакеты и файлы-заготовки с описаниями назначения. Они не содержат обработчиков или работающих интеграций. `app/main.py` пока не создаёт FastAPI-приложение; команды запуска появятся после реализации.

```text
backend/
├── app/
│   ├── main.py
│   ├── api/
│   │   ├── router.py
│   │   ├── dependencies.py
│   │   └── routes/{health,demo,pilot_requests,webhooks}.py
│   ├── admin/
│   │   ├── README.md
│   │   ├── router.py
│   │   ├── dependencies.py
│   │   ├── views/{businesses,knowledge,conversations,pilot_requests}.py
│   │   ├── templates/
│   │   └── static/
│   ├── core/{config,logging,security}.py
│   ├── db/{base,session}.py
│   ├── models/
│   ├── schemas/
│   ├── repositories/
│   ├── services/{conversations,pilot_requests,handoff}.py
│   ├── agent/{context,prompts,tools}.py
│   ├── integrations/
│   │   ├── llm/provider.py
│   │   └── channels/
│   └── workers/tasks.py
├── migrations/versions/
└── tests/{unit,integration,admin,fixtures}/
```

Каталоги Python-модулей содержат `__init__.py`. Пустые каталоги сохраняются через `.gitkeep`. Модели, схемы и репозитории будут добавляться вместе с соответствующими сценариями.

| Каталог | Назначение |
|---|---|
| app/api/routes | HTTP-маршруты: состояние сервиса, демо-чат, заявки |
| [app/admin](app/admin/README.md) | Внутренняя админка сотрудников: компании, знания, диалоги и заявки |
| app/core | Конфигурация, журналирование и общие ограничения |
| app/db | Подключение к PostgreSQL и управление сессиями |
| app/models | Модели хранения данных |
| app/schemas | Входные и выходные схемы API |
| app/repositories | Запросы к БД с изоляцией по бизнесу |
| app/services | Сценарии диалога, заявки и передача человеку |
| app/agent | Сбор контекста, инструкции и разрешённые действия |
| app/integrations/llm | Интерфейс и реализации провайдеров моделей |
| app/integrations/channels | Будущие адаптеры мессенджеров и телефонии |
| app/workers | Будущая фоновая обработка |
| migrations | Будущие миграции схемы PostgreSQL |
| tests/unit | Изолированные проверки логики |
| tests/integration | Проверки API, БД и интеграций |
| tests/admin | Проверки прав сотрудников и изоляции данных админки |
| tests/fixtures | Вымышленные тестовые данные |

Поток: HTTP-маршрут → сервис → агент / интеграция / репозиторий. Маршруты не должны содержать всю логику разговора.

Обращения потенциальных клиентов с лендинга и заявки покупателей внутри демо — разные сущности. Демо использует вымышленные данные; сведения из реальной формы не добавляются в публичную демо-базу.

Redis не подключён. Выбор библиотеки очереди, ORM, миграций и провайдера модели выполняется при реализации. Команды запуска появятся вместе с рабочим сервером.
