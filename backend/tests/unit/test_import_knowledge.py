"""Knowledge import: table validation and Google Sheet links. No database, no network."""

import pytest

from app.import_knowledge import parse_rows, sheet_csv_url


def test_sheet_link_becomes_csv_export() -> None:
    url = sheet_csv_url("https://docs.google.com/spreadsheets/d/abc_DEF-1/edit#gid=42")
    assert url == "https://docs.google.com/spreadsheets/d/abc_DEF-1/export?format=csv&gid=42"
    assert sheet_csv_url("knowledge.csv") is None


def test_rows_are_parsed_and_inactive_marks_are_understood() -> None:
    text = "﻿Category,Title,Content,Active\nproperty,Чуй,\"2 комнаты, 85 000 USD\",да\n,,,\nfaq,Парковка,Есть,нет\n"
    rows = parse_rows(text)
    assert [(row.title, row.active) for row in rows] == [("Чуй", True), ("Парковка", False)]
    assert rows[0].content == "2 комнаты, 85 000 USD"


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("title,content\nA,B\n", "нет колонок: category"),
        ("category,title,content\nfaq,,текст\n", "строка 2"),
        ("category,title,content\nfaq,A,x\nfaq,A,y\n", "повторяется"),
    ],
)
def test_bad_tables_name_the_problem(text: str, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        parse_rows(text)
