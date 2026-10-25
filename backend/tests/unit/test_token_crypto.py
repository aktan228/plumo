from uuid import uuid4
import pytest
from app.infrastructure.channels.token_crypto import encrypt_token, decrypt_token
from app.infrastructure.channels.base import ChannelError


def test_tokens_are_randomized_bound_to_tenant_and_connection(monkeypatch):
    monkeypatch.setenv("CHANNEL_SECRET_KEY", "unit-test-only-secret")
    business, connection = uuid4(), uuid4()
    first = encrypt_token("fictional-token", business, connection)
    second = encrypt_token("fictional-token", business, connection)
    assert first != second and "fictional-token" not in first
    assert decrypt_token(first, business, connection) == "fictional-token"
    for changed in [(uuid4(), connection), (business, uuid4())]:
        with pytest.raises(ChannelError):
            decrypt_token(first, *changed)
    with pytest.raises(ChannelError):
        decrypt_token(first[:-6] + "xxxxxx", business, connection)
    monkeypatch.setenv("CHANNEL_SECRET_KEY", "rotated-unit-key")
    with pytest.raises(ChannelError):
        decrypt_token(first, business, connection)
