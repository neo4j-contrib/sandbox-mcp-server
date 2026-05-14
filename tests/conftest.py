"""Shared fixtures for the sandbox-mcp-server test suite.

All tests run offline. No real `api.sandbox.neo4j.com` or Auth0 calls.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sandbox_api_mcp_server.auth import verify_auth
from sandbox_api_mcp_server.sandbox.routes import get_sandbox_api_router
from sandbox_api_mcp_server.sandbox.service import SandboxApiClient, get_sandbox_client


SANDBOX_BASE = "https://sandbox.test"
AUTH0_DOMAIN = "tenant.example.com"
AUTH0_AUDIENCE = "https://api.example.com"


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Populate env vars so Auth0Settings() and SandboxApiClient construct cleanly."""
    monkeypatch.setenv("SANDBOX_API_HOSTNAME", SANDBOX_BASE)
    monkeypatch.setenv("AUTH0_DOMAIN", AUTH0_DOMAIN)
    monkeypatch.setenv("AUTH0_AUDIENCE", AUTH0_AUDIENCE)
    monkeypatch.setenv("AUTH0_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("AUTH0_CLIENT_SECRET", "test-client-secret")


@pytest.fixture
def respx_router():
    with respx.mock(base_url=SANDBOX_BASE, assert_all_called=False) as router:
        yield router


@pytest.fixture
def mock_sandbox_client() -> AsyncMock:
    """An AsyncMock spec'd against SandboxApiClient.

    Tests should set `.return_value` on individual methods, e.g.:
        mock_sandbox_client.list_sandboxes_for_user.return_value = {"sandboxes": []}
    """
    client = AsyncMock(spec=SandboxApiClient)
    client.access_token = "Bearer ApiKey test-token"
    return client


@pytest.fixture
def fake_user() -> dict[str, Any]:
    return {"claims": {"sub": "test"}, "token": "Bearer ApiKey test-token", "type": "api_key"}


@pytest.fixture
def fastapi_app(mock_sandbox_client, fake_user) -> FastAPI:
    app = FastAPI()
    app.include_router(get_sandbox_api_router())
    app.dependency_overrides[verify_auth] = lambda: fake_user
    app.dependency_overrides[get_sandbox_client] = lambda: mock_sandbox_client
    return app


@pytest.fixture
def client(fastapi_app) -> TestClient:
    return TestClient(fastapi_app)


def make_request(headers: dict[str, str], jwks_public_key: str | None = None) -> SimpleNamespace:
    """Build a minimal Request-like stub for direct verify_auth() calls.

    auth.verify_auth only touches request.headers.get(...) and request.app.state.jwks_public_key,
    so a SimpleNamespace is enough — no need for a real ASGI scope.
    """
    return SimpleNamespace(
        headers=headers,
        app=SimpleNamespace(state=SimpleNamespace(jwks_public_key=jwks_public_key)),
    )
