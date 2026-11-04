"""Refuses a test database that may hold working data. Integration fixtures drop every table."""

from sqlalchemy.engine import make_url

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _place(url: str) -> tuple[str, int, str]:
    parsed = make_url(url)
    host = parsed.host or "localhost"
    return ("localhost" if host in LOCAL_HOSTS else host, parsed.port or 5432, parsed.database or "")


def guard_test_database(test_url: str, working_url: str) -> None:
    host, port, name = _place(test_url)
    where = f"{name} on {host}:{port}"
    if "test" not in name.lower():
        raise RuntimeError(f"Test database {where} has no 'test' in its name; set TEST_DATABASE_URL to a separate database")
    if (host, port, name) == _place(working_url):
        raise RuntimeError(f"Test database {where} is the working database from DATABASE_URL")
