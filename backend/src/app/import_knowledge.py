"""Load a business's knowledge base from a CSV file or a Google Sheet.

    python -m app.import_knowledge --business "Demo Realty" knowledge.csv
    python -m app.import_knowledge --business "Demo Realty" "https://docs.google.com/spreadsheets/d/<id>/edit#gid=0"
    python -m app.import_knowledge --business "Demo Realty" knowledge.csv --deactivate-missing --dry-run

Columns (first row is the header): `category`, `title`, `content`, optional `active`
(да/нет, yes/no, 1/0). Rows are matched by title inside the business: a changed row is
updated, a new one is added. `--deactivate-missing` switches off titles that are no
longer in the sheet, so a sold listing disappears from answers without being deleted.

A Google Sheet must be shared as "anyone with the link can view"; it is read as CSV
export, no Google credentials are used. Only fictional data belongs in git.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import httpx

from app.config import get_settings
from app.domain.models import KnowledgeItem, utcnow
from app.infrastructure.database.repositories import BusinessRepository, KnowledgeRepository
from app.infrastructure.database.session import create_engine, create_session_factory
from app.migrate import upgrade_database

_SHEET = re.compile(r"docs\.google\.com/spreadsheets/d/([A-Za-z0-9_-]+)")
_GID = re.compile(r"[#&?]gid=(\d+)")
_FALSE = {"0", "нет", "no", "false", "off", "жок", "-"}
_MAX_ROWS = 2000


@dataclass(slots=True)
class Row:
    category: str
    title: str
    content: str
    active: bool


@dataclass(slots=True)
class ImportReport:
    added: list[str]
    updated: list[str]
    unchanged: list[str]
    deactivated: list[str]


def sheet_csv_url(source: str) -> str | None:
    """CSV export URL of a Google Sheet link, or None for anything else."""

    match = _SHEET.search(source)
    if not match:
        return None
    gid = _GID.search(source)
    return f"https://docs.google.com/spreadsheets/d/{match.group(1)}/export?format=csv&gid={gid.group(1) if gid else 0}"


def parse_rows(text: str) -> list[Row]:
    """Validate the table. Errors name the line, so whoever fills the sheet can fix it."""

    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    header = {name.strip().lower() for name in reader.fieldnames or []}
    missing = {"category", "title", "content"} - header
    if missing:
        raise ValueError(f"нет колонок: {', '.join(sorted(missing))}")
    rows: list[Row] = []
    seen: set[str] = set()
    for line, raw in enumerate(reader, start=2):
        item = {str(key).strip().lower(): (value or "").strip() for key, value in raw.items() if key}
        if not any(item.values()):
            continue
        title, content = item.get("title", ""), item.get("content", "")
        if not title or not content:
            raise ValueError(f"строка {line}: пустые title или content")
        if len(title) > 300:
            raise ValueError(f"строка {line}: title длиннее 300 символов")
        if title in seen:
            raise ValueError(f"строка {line}: title «{title}» повторяется")
        seen.add(title)
        rows.append(
            Row(
                category=(item.get("category") or "faq")[:64],
                title=title,
                content=content,
                active=item.get("active", "").lower() not in _FALSE,
            )
        )
        if len(rows) > _MAX_ROWS:
            raise ValueError(f"больше {_MAX_ROWS} строк — это не похоже на базу знаний одного бизнеса")
    return rows


async def apply_rows(session, business_id, rows: list[Row], *, deactivate_missing: bool) -> ImportReport:
    repo = KnowledgeRepository(session)
    existing = {item.title: item for item in await repo.list_items(business_id)}
    report = ImportReport([], [], [], [])
    now = utcnow()
    for row in rows:
        current = existing.get(row.title)
        if current is None:
            await repo.add(
                KnowledgeItem(uuid4(), business_id, row.category, row.title, row.content, {"source": "import"}, row.active, now, now)
            )
            report.added.append(row.title)
            continue
        if (current.category, current.content, current.active) == (row.category, row.content, row.active):
            report.unchanged.append(row.title)
            continue
        current.category, current.content, current.active, current.updated_at = row.category, row.content, row.active, now
        await repo.save(current)
        report.updated.append(row.title)
    if deactivate_missing:
        listed = {row.title for row in rows}
        for title, item in existing.items():
            if title not in listed and item.active:
                item.active, item.updated_at = False, now
                await repo.save(item)
                report.deactivated.append(title)
    return report


async def _read(source: str) -> str:
    url = sheet_csv_url(source)
    if url is None and source.startswith(("http://", "https://")):
        url = source
    if url is None:
        return Path(source).read_text(encoding="utf-8-sig")
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        response = await client.get(url)
    if response.status_code != 200 or "text/html" in response.headers.get("content-type", ""):
        raise ValueError("таблица не открылась как CSV: откройте доступ «всем, у кого есть ссылка»")
    return response.content.decode("utf-8-sig")


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Импорт базы знаний бизнеса из CSV или Google-таблицы")
    parser.add_argument("source", help="путь к CSV или ссылка на Google-таблицу")
    parser.add_argument("--business", required=True, help="имя бизнеса в базе")
    parser.add_argument("--deactivate-missing", action="store_true", help="выключить объекты, которых нет в таблице")
    parser.add_argument("--dry-run", action="store_true", help="показать изменения, ничего не записывать")
    args = parser.parse_args(argv)

    try:
        rows = parse_rows(await _read(args.source))
    except (OSError, ValueError, httpx.HTTPError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    settings = get_settings()
    engine = create_engine(settings.database_url)
    try:
        async with create_session_factory(engine)() as session:
            business = await BusinessRepository(session).get_by_name(args.business)
            if business is None:
                print(f"Ошибка: бизнес «{args.business}» не найден", file=sys.stderr)
                return 1
            report = await apply_rows(session, business.id, rows, deactivate_missing=args.deactivate_missing)
            if args.dry_run:
                await session.rollback()
            else:
                await session.commit()
    finally:
        await engine.dispose()
    print(f"{'Проверка, ничего не записано. ' if args.dry_run else ''}Бизнес: {args.business}")
    for label, titles in (
        ("добавлено", report.added),
        ("обновлено", report.updated),
        ("без изменений", report.unchanged),
        ("выключено", report.deactivated),
    ):
        print(f"  {label}: {len(titles)}" + (f" — {', '.join(titles[:10])}" if titles else ""))
    return 0


if __name__ == "__main__":
    # Alembic runs its own event loop, so migrations go before ours.
    upgrade_database()
    raise SystemExit(asyncio.run(main()))
