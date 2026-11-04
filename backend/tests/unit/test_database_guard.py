"""Integration tests drop every table, so they must refuse a database that may hold working data."""

import pytest

from database_guard import guard_test_database

WORKING = "postgresql+asyncpg://plumo:plumo@localhost:5432/plumo"


def test_separate_test_database_is_accepted() -> None:
    guard_test_database("postgresql+asyncpg://plumo:plumo@localhost:5432/plumo_test", WORKING)


def test_working_database_is_refused() -> None:
    with pytest.raises(RuntimeError, match="working database"):
        guard_test_database("postgresql+asyncpg://plumo:plumo@127.0.0.1/plumo_test", "postgresql+asyncpg://u:p@localhost/plumo_test")


def test_database_without_test_in_name_is_refused() -> None:
    with pytest.raises(RuntimeError, match="test"):
        guard_test_database("postgresql+asyncpg://user:secret@db.example.com:6543/postgres", WORKING)


def test_refusal_does_not_print_the_password() -> None:
    with pytest.raises(RuntimeError) as refused:
        guard_test_database("postgresql+asyncpg://user:secret@db.example.com:6543/postgres", WORKING)
    assert "secret" not in str(refused.value)
