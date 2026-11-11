import asyncio
import importlib
from unittest.mock import Mock

import pytest
from neo4j.exceptions import AuthError, ServiceUnavailable


api = importlib.import_module("source.api.app")


def test_startup_waits_for_database_and_closes_driver(monkeypatch):
    check = Mock()
    close = Mock()
    monkeypatch.setattr(api, "check_connection", check)
    monkeypatch.setattr(api, "close_driver", close)

    async def run():
        async with api.lifespan(api.app):
            check.assert_called_once_with()
            close.assert_not_called()

    asyncio.run(run())
    close.assert_called_once_with()


@pytest.mark.parametrize("error", [
    ServiceUnavailable("Connection refused"),
    AuthError("Invalid credentials"),
    RuntimeError("Missing Neo4j configuration: NEO4J_URI"),
])
def test_unavailable_database_prevents_startup_and_closes_driver(monkeypatch, error):
    close = Mock()
    monkeypatch.setattr(api, "check_connection", Mock(side_effect=error))
    monkeypatch.setattr(api, "close_driver", close)

    async def run():
        async with api.lifespan(api.app):
            pytest.fail("API must not finish startup before Neo4j is ready")

    with pytest.raises(RuntimeError, match="python -m source.db.connection") as failure:
        asyncio.run(run())
    assert failure.value.__cause__ is error
    close.assert_called_once_with()
