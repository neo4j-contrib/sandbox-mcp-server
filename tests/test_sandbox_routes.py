"""Tests for the FastAPI router exposed by get_sandbox_api_router().

These pin:
- the path + HTTP method for every endpoint,
- the `operation_id` (= MCP tool name) for every endpoint,
- which endpoints require auth (all except /health),
- the request-body validation behavior.

`call_sandbox_api` calls each method by name via getattr; that means the AsyncMock
fixtures spec'd against SandboxApiClient automatically expose every method as an
awaitable that returns a (configurable) MagicMock — enough to satisfy the route
without touching the network.
"""
from __future__ import annotations

import pytest

from sandbox_api_mcp_server.sandbox.routes import get_sandbox_api_router


# ---------- route registration ----------

EXPECTED_ROUTES: list[tuple[str, str, str | None]] = [
    # (method, path, operation_id_or_None)
    ("GET", "/list-sandboxes", "list_sandboxes_for_user"),
    ("POST", "/start-sandbox", "start_new_sandbox"),
    ("POST", "/terminate-sandbox", "terminate_sandbox"),
    ("POST", "/extend-sandbox", "extend_sandbox_lifetime"),
    ("GET", "/get-sandbox-details/{sandbox_hash_key}", "get_sandbox_connection_details"),
    ("POST", "/request-backup/{sandbox_hash_key}", "request_sandbox_backup"),
    ("GET", "/backups/result/{result_id}", "get_backup_result"),
    ("GET", "/list-backups/{sandbox_hash_key}", "list_sandbox_backups"),
    ("POST", "/get-backup-download-url/{sandbox_hash_key}", "get_sandbox_backup_download_url"),
    ("POST", "/upload-to-aura", "upload_sandbox_to_aura"),
    ("GET", "/aura-upload/result/{result_id}", "get_aura_upload_result"),
    ("GET", "/query/schema", "get_schema"),
    ("POST", "/query/read", "read_query"),
    ("POST", "/query/write", "write_query"),
    ("GET", "/health", "health_check"),
]


class TestRouteRegistration:
    def test_all_expected_routes_present(self):
        router = get_sandbox_api_router()
        actual = set()
        for r in router.routes:
            for method in r.methods:  # type: ignore[attr-defined]
                actual.add((method, r.path))  # type: ignore[attr-defined]
        expected = {(m, p) for m, p, _ in EXPECTED_ROUTES}
        assert actual == expected

    def test_all_operation_ids_match(self):
        router = get_sandbox_api_router()
        path_to_opid = {r.path: r.operation_id for r in router.routes}  # type: ignore[attr-defined]
        for _, path, opid in EXPECTED_ROUTES:
            assert path_to_opid[path] == opid, f"{path}: expected {opid}, got {path_to_opid[path]}"


# ---------- endpoint behavior ----------

class TestListSandboxes:
    def test_returns_2xx(self, client, mock_sandbox_client):
        mock_sandbox_client.list_sandboxes_for_user.return_value = {"sandboxes": []}
        resp = client.get("/list-sandboxes")
        assert resp.status_code == 200
        assert resp.json() == {"sandboxes": []}


class TestStartSandbox:
    def test_returns_201(self, client, mock_sandbox_client):
        mock_sandbox_client.start_sandbox.return_value = {"id": "x"}
        resp = client.post("/start-sandbox", json={"usecase": "movies"})
        assert resp.status_code == 201
        assert resp.json() == {"id": "x"}
        mock_sandbox_client.start_sandbox.assert_awaited_once_with(usecase="movies")

    def test_missing_usecase_422(self, client):
        resp = client.post("/start-sandbox", json={})
        assert resp.status_code == 422


class TestTerminateSandbox:
    def test_passes_hash_to_stop(self, client, mock_sandbox_client):
        mock_sandbox_client.stop_sandbox.return_value = None
        resp = client.post("/terminate-sandbox", json={"sandbox_hash_key": "h1"})
        assert resp.status_code == 200
        # call_sandbox_api coerces None responses (204/202) to {}.
        assert resp.json() == {}
        mock_sandbox_client.stop_sandbox.assert_awaited_once_with(sandbox_hash_key="h1")

    def test_missing_hash_422(self, client):
        resp = client.post("/terminate-sandbox", json={})
        assert resp.status_code == 422


class TestExtendSandbox:
    def test_optional_hash_key_omitted(self, client, mock_sandbox_client):
        mock_sandbox_client.extend_sandbox.return_value = {"ok": True}
        resp = client.post("/extend-sandbox", json={})
        assert resp.status_code == 200
        mock_sandbox_client.extend_sandbox.assert_awaited_once_with(sandbox_hash_key=None)

    def test_with_hash_key(self, client, mock_sandbox_client):
        mock_sandbox_client.extend_sandbox.return_value = {"ok": True}
        client.post("/extend-sandbox", json={"sandbox_hash_key": "h2"})
        mock_sandbox_client.extend_sandbox.assert_awaited_once_with(sandbox_hash_key="h2")


class TestGetSandboxDetails:
    def test_default_verify_connect(self, client, mock_sandbox_client):
        mock_sandbox_client.get_sandbox_details.return_value = {"ip": "1.2.3.4"}
        resp = client.get("/get-sandbox-details/h3")
        assert resp.status_code == 200
        mock_sandbox_client.get_sandbox_details.assert_awaited_once_with(
            sandbox_hash_key="h3", verify_connect=False
        )

    def test_verify_connect_query_param(self, client, mock_sandbox_client):
        mock_sandbox_client.get_sandbox_details.return_value = {}
        client.get("/get-sandbox-details/h3?verify_connect=true")
        mock_sandbox_client.get_sandbox_details.assert_awaited_once_with(
            sandbox_hash_key="h3", verify_connect=True
        )


class TestBackupRoutes:
    def test_request_backup(self, client, mock_sandbox_client):
        mock_sandbox_client.request_backup.return_value = {"taskId": "t1"}
        resp = client.post("/request-backup/h1")
        assert resp.status_code == 200
        mock_sandbox_client.request_backup.assert_awaited_once_with(sandbox_hash_key="h1")

    def test_get_backup_result(self, client, mock_sandbox_client):
        mock_sandbox_client.get_backup_result.return_value = {"status": "DONE"}
        resp = client.get("/backups/result/r1")
        assert resp.status_code == 200
        mock_sandbox_client.get_backup_result.assert_awaited_once_with(result_id="r1")

    def test_list_backups(self, client, mock_sandbox_client):
        mock_sandbox_client.list_backups.return_value = {"items": []}
        resp = client.get("/list-backups/h1")
        assert resp.status_code == 200
        mock_sandbox_client.list_backups.assert_awaited_once_with(sandbox_hash_key="h1")

    def test_get_backup_download_url(self, client, mock_sandbox_client):
        mock_sandbox_client.get_backup_download_url.return_value = {"url": "https://s3"}
        resp = client.post("/get-backup-download-url/h1", json={"key": "k1"})
        assert resp.status_code == 200
        mock_sandbox_client.get_backup_download_url.assert_awaited_once_with(
            sandbox_hash_key="h1", key="k1"
        )

    def test_get_backup_download_url_missing_key_422(self, client):
        resp = client.post("/get-backup-download-url/h1", json={})
        assert resp.status_code == 422


class TestAuraRoutes:
    def test_upload_to_aura(self, client, mock_sandbox_client):
        mock_sandbox_client.upload_to_aura.return_value = {"taskId": "u1"}
        resp = client.post(
            "/upload-to-aura",
            json={
                "sandbox_hash_key": "h1",
                "aura_uri": "neo4j+s://x",
                "aura_password": "pw",
            },
        )
        assert resp.status_code == 200
        mock_sandbox_client.upload_to_aura.assert_awaited_once_with(
            sandbox_hash_key="h1",
            aura_uri="neo4j+s://x",
            aura_password="pw",
            aura_username="neo4j",
        )

    def test_upload_to_aura_missing_required_422(self, client):
        resp = client.post("/upload-to-aura", json={"sandbox_hash_key": "h1"})
        assert resp.status_code == 422

    def test_get_aura_upload_result(self, client, mock_sandbox_client):
        mock_sandbox_client.get_aura_upload_result.return_value = {"status": "DONE"}
        resp = client.get("/aura-upload/result/u1")
        assert resp.status_code == 200
        mock_sandbox_client.get_aura_upload_result.assert_awaited_once_with(result_id="u1")


class TestQueryRoutes:
    def test_get_schema(self, client, mock_sandbox_client):
        from sandbox_api_mcp_server.sandbox.models import FastApiReadCypherQueryResponse
        mock_sandbox_client.get_schema.return_value = FastApiReadCypherQueryResponse(
            data=[{"label": "Movie"}], count=1
        )
        resp = client.get("/query/schema?hash_key=h1")
        assert resp.status_code == 200
        assert resp.json() == {"data": [{"label": "Movie"}], "count": 1}
        mock_sandbox_client.get_schema.assert_awaited_once_with(hash_key="h1")

    def test_get_schema_missing_hash_key_422(self, client):
        resp = client.get("/query/schema")
        assert resp.status_code == 422

    def test_read_query(self, client, mock_sandbox_client):
        from sandbox_api_mcp_server.sandbox.models import FastApiReadCypherQueryResponse
        mock_sandbox_client.read_query.return_value = FastApiReadCypherQueryResponse(
            data=[{"n": 1}], count=1
        )
        resp = client.post(
            "/query/read",
            json={"hash_key": "h", "query": "MATCH (n) RETURN n"},
        )
        assert resp.status_code == 200
        mock_sandbox_client.read_query.assert_awaited_once_with(
            hash_key="h", query="MATCH (n) RETURN n", params=None
        )

    def test_write_query(self, client, mock_sandbox_client):
        from sandbox_api_mcp_server.sandbox.models import FastApiReadCypherQueryResponse
        mock_sandbox_client.write_query.return_value = FastApiReadCypherQueryResponse(
            data=[], count=0
        )
        resp = client.post(
            "/query/write",
            json={"hash_key": "h", "query": "CREATE (n:X)", "params": {"p": 1}},
        )
        assert resp.status_code == 200
        mock_sandbox_client.write_query.assert_awaited_once_with(
            hash_key="h", query="CREATE (n:X)", params={"p": 1}
        )

    def test_read_query_missing_query_422(self, client):
        resp = client.post("/query/read", json={"hash_key": "h"})
        assert resp.status_code == 422


class TestHealthCheck:
    def test_returns_200_plain_text(self, fastapi_app):
        from fastapi.testclient import TestClient
        resp = TestClient(fastapi_app).get("/health")
        assert resp.status_code == 200
        # PlainTextResponse — not JSON.
        assert resp.text == "Ok"
        assert "text/plain" in resp.headers.get("content-type", "")
