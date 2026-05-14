"""Lock-in tests for Pydantic models.

These guard against:
- pydantic 2.x → next-version field-name / required-vs-optional drift,
- accidental renames during refactors.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from sandbox_api_mcp_server.models import Auth0Settings
from sandbox_api_mcp_server.sandbox.models import (
    AuraUploadBody,
    BackupDownloadUrlBody,
    ExtendSandboxBody,
    FastApiCypherQueryBody,
    FastApiReadCypherQueryBody,
    FastApiReadCypherQueryResponse,
    FastApiWriteCypherQueryBody,
    StartSandboxBody,
    StopSandboxBody,
    USECASE_DESCRIPTION,
)


def _required(model_cls) -> set[str]:
    return {n for n, f in model_cls.model_fields.items() if f.is_required()}


def _optional(model_cls) -> set[str]:
    return {n for n, f in model_cls.model_fields.items() if not f.is_required()}


class TestStartSandboxBody:
    def test_fields(self):
        assert set(StartSandboxBody.model_fields) == {"usecase"}
        assert _required(StartSandboxBody) == {"usecase"}

    def test_roundtrip(self):
        m = StartSandboxBody(usecase="movies")
        assert m.usecase == "movies"

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            StartSandboxBody()  # type: ignore[call-arg]


class TestStopSandboxBody:
    def test_fields(self):
        assert set(StopSandboxBody.model_fields) == {"sandbox_hash_key"}
        assert _required(StopSandboxBody) == {"sandbox_hash_key"}

    def test_roundtrip(self):
        m = StopSandboxBody(sandbox_hash_key="abc123")
        assert m.sandbox_hash_key == "abc123"


class TestExtendSandboxBody:
    def test_fields_all_optional(self):
        assert set(ExtendSandboxBody.model_fields) == {"sandbox_hash_key"}
        assert _required(ExtendSandboxBody) == set()
        assert _optional(ExtendSandboxBody) == {"sandbox_hash_key"}

    def test_default_none(self):
        m = ExtendSandboxBody()
        assert m.sandbox_hash_key is None


class TestAuraUploadBody:
    def test_fields(self):
        assert set(AuraUploadBody.model_fields) == {
            "sandbox_hash_key",
            "aura_uri",
            "aura_password",
            "aura_username",
        }
        assert _required(AuraUploadBody) == {"sandbox_hash_key", "aura_uri", "aura_password"}
        assert _optional(AuraUploadBody) == {"aura_username"}

    def test_default_username(self):
        m = AuraUploadBody(
            sandbox_hash_key="h", aura_uri="neo4j+s://x", aura_password="p"
        )
        assert m.aura_username == "neo4j"


class TestBackupDownloadUrlBody:
    def test_fields(self):
        assert set(BackupDownloadUrlBody.model_fields) == {"key"}
        assert _required(BackupDownloadUrlBody) == {"key"}


class TestFastApiCypherQueryBody:
    def test_fields(self):
        assert set(FastApiCypherQueryBody.model_fields) == {"hash_key", "params"}
        assert _required(FastApiCypherQueryBody) == {"hash_key"}
        assert _optional(FastApiCypherQueryBody) == {"params"}

    def test_default_params_none(self):
        m = FastApiCypherQueryBody(hash_key="h")
        assert m.params is None


class TestFastApiReadCypherQueryBody:
    def test_fields(self):
        # Inherits hash_key, params from base; adds query.
        assert set(FastApiReadCypherQueryBody.model_fields) == {"hash_key", "params", "query"}
        assert _required(FastApiReadCypherQueryBody) == {"hash_key", "query"}
        assert _optional(FastApiReadCypherQueryBody) == {"params"}

    def test_roundtrip(self):
        m = FastApiReadCypherQueryBody(hash_key="h", query="MATCH (n) RETURN n", params={"x": 1})
        assert m.params == {"x": 1}


class TestFastApiWriteCypherQueryBody:
    def test_fields(self):
        assert set(FastApiWriteCypherQueryBody.model_fields) == {"hash_key", "params", "query"}
        assert _required(FastApiWriteCypherQueryBody) == {"hash_key", "query"}
        assert _optional(FastApiWriteCypherQueryBody) == {"params"}


class TestFastApiReadCypherQueryResponse:
    def test_fields(self):
        assert set(FastApiReadCypherQueryResponse.model_fields) == {"data", "count"}
        assert _required(FastApiReadCypherQueryResponse) == {"data", "count"}

    def test_roundtrip(self):
        r = FastApiReadCypherQueryResponse(data=[{"name": "John"}], count=1)
        assert r.count == 1
        assert r.data == [{"name": "John"}]


class TestAuth0Settings:
    def test_fields_and_defaults(self):
        names = set(Auth0Settings.model_fields)
        assert names == {"auth0_domain", "auth0_audience", "auth0_client_id", "auth0_client_secret"}

    def test_reads_env(self, monkeypatch):
        monkeypatch.setenv("AUTH0_DOMAIN", "example.auth0.com")
        monkeypatch.setenv("AUTH0_AUDIENCE", "https://api.example.com")
        monkeypatch.setenv("AUTH0_CLIENT_ID", "cid")
        monkeypatch.setenv("AUTH0_CLIENT_SECRET", "sec")
        s = Auth0Settings()
        assert s.auth0_domain == "example.auth0.com"
        assert s.auth0_audience == "https://api.example.com"
        assert s.auth0_client_id == "cid"
        assert s.auth0_client_secret == "sec"

    def test_jwks_and_metadata_urls(self, monkeypatch):
        monkeypatch.setenv("AUTH0_DOMAIN", "example.auth0.com")
        s = Auth0Settings()
        assert s.auth0_jwks_url == "https://example.auth0.com/.well-known/jwks.json"
        assert s.auth0_oauth_metadata_url == "https://example.auth0.com/.well-known/openid-configuration"


class TestUsecaseDescription:
    """Locks the use-case list — the autocomplete value-set most callers depend on."""

    def test_contains_known_usecases(self):
        for uc in ["movies", "blank-sandbox", "recommendations", "fraud-detection"]:
            assert uc in USECASE_DESCRIPTION
