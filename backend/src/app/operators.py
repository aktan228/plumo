"""Administrative operator tools. Clients can also register through /register.

    python -m app.operators create --email azamat@example.kg --business "Demo Realty" --name "Азамат"
    python -m app.operators password --email azamat@example.kg
    python -m app.operators list

The password is asked interactively, or read from PLUMO_OPERATOR_PASSWORD (for scripts).
It is stored as a scrypt hash; nobody can read it back.
"""

import argparse
import asyncio
import getpass
import os
import sys
from uuid import UUID

from sqlalchemy import select

import app.config  # noqa: F401  loads backend/.env
from app.application.services.auth_service import hash_password
from app.config import get_settings
from app.infrastructure.database.channel_repositories import OperatorRepository
from app.infrastructure.database.models import BusinessRow, OperatorRow
from app.infrastructure.database.repositories import BusinessRepository
from app.infrastructure.database.session import create_engine, create_session_factory

MIN_PASSWORD = 10


def _password() -> str:
    value = os.getenv("PLUMO_OPERATOR_PASSWORD", "")
    if not value:
        value = getpass.getpass("Пароль (не меньше 10 символов): ")
        if value != getpass.getpass("Ещё раз: "):
            sys.exit("Пароли не совпали.")
    if len(value) < MIN_PASSWORD:
        sys.exit(f"Пароль короче {MIN_PASSWORD} символов.")
    return value


async def _run(args) -> None:
    engine = create_engine(get_settings().database_url, null_pool=True)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            operators = OperatorRepository(session)
            if args.command == "list":
                rows = (
                    await session.execute(
                        select(OperatorRow.email, OperatorRow.display_name, OperatorRow.active, BusinessRow.name)
                        .join(BusinessRow, BusinessRow.id == OperatorRow.business_id)
                        .order_by(OperatorRow.email)
                    )
                ).all()
                for email, name, active, business in rows:
                    print(f"{email}\t{name or '-'}\t{business}\t{'active' if active else 'disabled'}")
                return
            if args.command == "create":
                repo = BusinessRepository(session)
                business = await repo.get(args.business_id) if args.business_id else await repo.get_by_name(args.business)
                if business is None:
                    sys.exit(f"Бизнес «{args.business}» не найден. Сначала: python -m app.seed")
                if await operators.get_with_hash(args.email):
                    sys.exit("Оператор с таким email уже есть. Смена пароля: python -m app.operators password")
                operator = await operators.add(
                    business_id=business.id,
                    email=args.email,
                    password_hash=hash_password(_password()),
                    display_name=args.name or "",
                )
                await session.commit()
                print(f"Создан оператор {operator.email} для «{business.name}».")
                return
            if args.command == "password":
                found = await operators.get_with_hash(args.email)
                if found is None:
                    sys.exit("Оператор не найден.")
                await operators.set_password(found[0].id, hash_password(_password()))
                await session.commit()
                print("Пароль обновлён. Старые сессии остаются до истечения срока или выхода.")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Plumo dashboard operators")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--email", required=True)
    workspace = create.add_mutually_exclusive_group(required=True)
    workspace.add_argument("--business", help="уникальное название бизнеса")
    workspace.add_argument("--business-id", type=UUID, help="ID бизнеса, если названия повторяются")
    create.add_argument("--name", default="", help="имя, которое видно в истории диалога")
    password = sub.add_parser("password")
    password.add_argument("--email", required=True)
    sub.add_parser("list")
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
