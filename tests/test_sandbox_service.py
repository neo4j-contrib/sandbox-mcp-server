"""Tests for SandboxApiClient HTTP contract and call_sandbox_api retry logic.

Every test pins:
- the URL path,
- the HTTP method,
- the query/body sent upstream,
- the response shape returned to the caller.

These are the contracts that will break loudly if a refactor (or a dep upgrade)
silently changes how we talk to the Neo4j Sandbox API.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx
from fastapi import HTTPException

from sandbox_api_mcp_server.sandbox.models import FastApiReadCypherQueryResponse
from sandbox_api_mcp_server.sandbox.service import (
    BASE_BACKOFF_DELAY,
    MAX_RETRIES,
    SandboxApiClient,
    SandboxApiClientError,
    call_sandbox_api,
    get_sandbox_client,
)

from tests.conftest import SANDBOX_BASE


@pytest.fixture
async def sandbox_client():
    c = SandboxApiClient(access_token="Bearer ApiKey test")
    try:
        yield c
    finally:
        await c.close()


class TestConstructor:
    async def test_rejects_empty_token(self):
        with pytest.raises(ValueError):
            SandboxApiClient(access_token="")

    async def test_headers_set(self, sandbox_client):
        assert sandbox_client.access_token == "Bearer ApiKey test"
        assert sandbox_client.headers["Authorization"] == "Bearer ApiKey test"
        assert sandbox_client.headers["Accept"] == "application/json"
        assert sandbox_client.headers["Content-Type"] == "application/json"

    async def test_base_url_from_env(self, sandbox_client):
        assert str(sandbox_client.client.base_url).rstrip("/") == SANDBOX_BASE


# ---------- list_sandboxes_for_user ----------

class TestListSandboxesForUser:
    async def test_no_timezone(self, sandbox_client, respx_router):
        route = respx_router.get("/SandboxGetRunningInstancesForUser").mock(
            return_value=httpx.Response(200, json=[{"hashKey": "a"}])
        )
        result = await sandbox_client.list_sandboxes_for_user()
        assert result == {"sandboxes": [{"hashKey": "a"}]}
        assert route.called
        # No timezone query param sent.
        assert "timezone" not in dict(route.calls.last.request.url.params)

    async def test_with_timezone(self, sandbox_client, respx_router):
        route = respx_router.get("/SandboxGetRunningInstancesForUser").mock(
            return_value=httpx.Response(200, json=[])
        )
        await sandbox_client.list_sandboxes_for_user(timezone="America/New_York")
        assert dict(route.calls.last.request.url.params) == {"timezone": "America/New_York"}


# ---------- start_sandbox ----------

class TestStartSandbox:
    async def test_posts_usecase(self, sandbox_client, respx_router):
        import json as _json
        route = respx_router.post("/SandboxRunInstance").mock(
            return_value=httpx.Response(200, json={"id": "x"})
        )
        result = await sandbox_client.start_sandbox(usecase="movies")
        assert result == {"id": "x"}
        body = _json.loads(route.calls.last.request.content)
        assert body == {"usecase": "movies"}


# ---------- stop_sandbox ----------

class TestStopSandbox:
    async def test_posts_camel_case_key(self, sandbox_client, respx_router):
        import json as _json
        route = respx_router.post("/SandboxStopInstance").mock(
            return_value=httpx.Response(200, json={})
        )
        await sandbox_client.stop_sandbox(sandbox_hash_key="h1")
        body = _json.loads(route.calls.last.request.content)
        assert body == {"sandboxHashKey": "h1"}

    async def test_204_returns_none(self, sandbox_client, respx_router):
        respx_router.post("/SandboxStopInstance").mock(return_value=httpx.Response(204))
        result = await sandbox_client.stop_sandbox(sandbox_hash_key="h1")
        assert result is None


# ---------- extend_sandbox ----------

class TestExtendSandbox:
    async def test_empty_body_when_no_key(self, sandbox_client, respx_router):
        import json as _json
        route = respx_router.post("/SandboxExtend").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        await sandbox_client.extend_sandbox()
        body = _json.loads(route.calls.last.request.content)
        assert body == {}

    async def test_with_hash_key(self, sandbox_client, respx_router):
        import json as _json
        route = respx_router.post("/SandboxExtend").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        await sandbox_client.extend_sandbox(sandbox_hash_key="h2")
        body = _json.loads(route.calls.last.request.content)
        assert body == {"sandboxHashKey": "h2"}


# ---------- get_sandbox_details ----------

class TestGetSandboxDetails:
    async def test_default_params(self, sandbox_client, respx_router):
        route = respx_router.get("/SandboxAuthdGetInstanceByHashKey").mock(
            return_value=httpx.Response(200, json={"ip": "1.2.3.4"})
        )
        await sandbox_client.get_sandbox_details(sandbox_hash_key="h3")
        params = dict(route.calls.last.request.url.params)
        # Default verify_connect=False is sent (because the impl checks `is not None`).
        # httpx serializes bool→lowercase "false"/"true" in query strings.
        assert params == {"sandboxHashKey": "h3", "verifyConnect": "false"}

    async def test_with_verify_connect_true(self, sandbox_client, respx_router):
        route = respx_router.get("/SandboxAuthdGetInstanceByHashKey").mock(
            return_value=httpx.Response(200, json={})
        )
        await sandbox_client.get_sandbox_details(sandbox_hash_key="h3", verify_connect=True)
        assert dict(route.calls.last.request.url.params) == {
            "sandboxHashKey": "h3",
            "verifyConnect": "true",
        }


# ---------- backup endpoints ----------

class TestBackupEndpoints:
    async def test_request_backup(self, sandbox_client, respx_router):
        route = respx_router.post("/SandboxBackup/request/h1").mock(
            return_value=httpx.Response(200, json={"taskId": "t1"})
        )
        result = await sandbox_client.request_backup(sandbox_hash_key="h1")
        assert result == {"taskId": "t1"}
        assert route.called

    async def test_get_backup_result(self, sandbox_client, respx_router):
        route = respx_router.get("/SandboxBackup/result/t1").mock(
            return_value=httpx.Response(200, json={"status": "DONE"})
        )
        result = await sandbox_client.get_backup_result(result_id="t1")
        assert result == {"status": "DONE"}
        assert route.called

    async def test_list_backups(self, sandbox_client, respx_router):
        route = respx_router.get("/SandboxBackup/h1").mock(
            return_value=httpx.Response(200, json=[{"key": "a"}])
        )
        result = await sandbox_client.list_backups(sandbox_hash_key="h1")
        assert result == [{"key": "a"}]
        assert route.called

    async def test_get_backup_download_url(self, sandbox_client, respx_router):
        import json as _json
        route = respx_router.post("/SandboxBackup/h1").mock(
            return_value=httpx.Response(200, json={"url": "https://s3"})
        )
        await sandbox_client.get_backup_download_url(sandbox_hash_key="h1", key="k1")
        body = _json.loads(route.calls.last.request.content)
        assert body == {"key": "k1"}


# ---------- aura upload endpoints ----------

class TestAuraEndpoints:
    async def test_upload_to_aura_body(self, sandbox_client, respx_router):
        import json as _json
        route = respx_router.post("/SandboxAuraUpload/request/h1").mock(
            return_value=httpx.Response(200, json={"taskId": "u1"})
        )
        await sandbox_client.upload_to_aura(
            sandbox_hash_key="h1",
            aura_uri="neo4j+s://x.databases.neo4j.io",
            aura_password="pass",
        )
        body = _json.loads(route.calls.last.request.content)
        # NOTE: this endpoint deliberately uses snake_case (unlike the other sandbox endpoints).
        assert body == {
            "aura_uri": "neo4j+s://x.databases.neo4j.io",
            "aura_password": "pass",
            "aura_username": "neo4j",
        }
        assert route.called

    async def test_upload_to_aura_custom_username(self, sandbox_client, respx_router):
        import json as _json
        respx_router.post("/SandboxAuraUpload/request/h1").mock(
            return_value=httpx.Response(200, json={})
        )
        await sandbox_client.upload_to_aura(
            sandbox_hash_key="h1",
            aura_uri="x",
            aura_password="p",
            aura_username="alice",
        )
        # Last request's body
        req = respx_router.calls.last.request
        body = _json.loads(req.content)
        assert body["aura_username"] == "alice"

    async def test_get_aura_upload_result(self, sandbox_client, respx_router):
        route = respx_router.get("/SandboxAuraUpload/result/u1").mock(
            return_value=httpx.Response(200, json={"status": "DONE"})
        )
        result = await sandbox_client.get_aura_upload_result(result_id="u1")
        assert result == {"status": "DONE"}
        assert route.called


# ---------- query endpoints ----------

class TestReadQuery:
    async def test_sends_access_mode_read(self, sandbox_client, respx_router):
        import json as _json
        respx_router.post("/SandboxRunQuery").mock(
            return_value=httpx.Response(200, json=[{"n": 1}, {"n": 2}])
        )
        result = await sandbox_client.read_query(hash_key="h1", query="MATCH (n) RETURN n")
        body = _json.loads(respx_router.calls.last.request.content)
        assert body == {
            "hash_key": "h1",
            "statement": "MATCH (n) RETURN n",
            "params": None,
            "accessMode": "Read",
        }
        assert isinstance(result, FastApiReadCypherQueryResponse)
        assert result.count == 2
        assert result.data == [{"n": 1}, {"n": 2}]


class TestWriteQuery:
    async def test_omits_access_mode(self, sandbox_client, respx_router):
        import json as _json
        respx_router.post("/SandboxRunQuery").mock(
            return_value=httpx.Response(200, json=[])
        )
        await sandbox_client.write_query(
            hash_key="h1", query="CREATE (n:X)", params={"p": 1}
        )
        body = _json.loads(respx_router.calls.last.request.content)
        # write_query intentionally does NOT include accessMode.
        assert "accessMode" not in body
        assert body == {"hash_key": "h1", "statement": "CREATE (n:X)", "params": {"p": 1}}


class TestGetSchema:
    async def test_dispatches_read_query_with_apoc_meta(self, sandbox_client, respx_router):
        import json as _json
        respx_router.post("/SandboxRunQuery").mock(
            return_value=httpx.Response(200, json=[])
        )
        result = await sandbox_client.get_schema(hash_key="h1")
        body = _json.loads(respx_router.calls.last.request.content)
        assert body["hash_key"] == "h1"
        assert body["accessMode"] == "Read"
        assert "apoc.meta.data" in body["statement"]
        assert isinstance(result, FastApiReadCypherQueryResponse)


# ---------- error mapping ----------

class TestErrorMapping:
    async def test_4xx_raises_client_error(self, sandbox_client, respx_router):
        respx_router.get("/SandboxGetRunningInstancesForUser").mock(
            return_value=httpx.Response(403, json={"error": "forbidden"})
        )
        with pytest.raises(SandboxApiClientError) as exc:
            await sandbox_client.list_sandboxes_for_user()
        assert exc.value.status_code == 403

    async def test_5xx_raises_client_error(self, sandbox_client, respx_router):
        respx_router.get("/SandboxGetRunningInstancesForUser").mock(
            return_value=httpx.Response(500, text="boom")
        )
        with pytest.raises(SandboxApiClientError) as exc:
            await sandbox_client.list_sandboxes_for_user()
        assert exc.value.status_code == 500

    async def test_network_error_wrapped_as_503(self, sandbox_client, respx_router):
        respx_router.get("/SandboxGetRunningInstancesForUser").mock(
            side_effect=httpx.ConnectError("boom")
        )
        with pytest.raises(SandboxApiClientError) as exc:
            await sandbox_client.list_sandboxes_for_user()
        assert exc.value.status_code == 503


# ---------- get_sandbox_client dependency ----------

class TestGetSandboxClient:
    def test_returns_client_with_user_token(self):
        user = {"claims": {}, "token": "Bearer ApiKey hello", "type": "api_key"}
        client = get_sandbox_client(user)  # type: ignore[arg-type]
        assert isinstance(client, SandboxApiClient)
        assert client.access_token == "Bearer ApiKey hello"


# ---------- call_sandbox_api ----------

class TestCallSandboxApi:
    async def test_success_passes_through(self):
        client = AsyncMock(spec=SandboxApiClient)
        client.list_sandboxes_for_user.return_value = {"sandboxes": [1]}
        result = await call_sandbox_api("list_sandboxes_for_user", client)
        assert result == {"sandboxes": [1]}

    async def test_none_coerces_to_empty_dict(self):
        client = AsyncMock(spec=SandboxApiClient)
        client.stop_sandbox.return_value = None
        result = await call_sandbox_api("stop_sandbox", client, sandbox_hash_key="h")
        assert result == {}

    async def test_kwargs_forwarded(self):
        client = AsyncMock(spec=SandboxApiClient)
        client.start_sandbox.return_value = {"ok": True}
        await call_sandbox_api("start_sandbox", client, usecase="movies")
        client.start_sandbox.assert_awaited_once_with(usecase="movies")

    async def test_retry_on_429(self):
        client = AsyncMock(spec=SandboxApiClient)
        client.list_sandboxes_for_user.side_effect = [
            SandboxApiClientError("rate limit", status_code=429),
            SandboxApiClientError("rate limit", status_code=429),
            {"sandboxes": []},
        ]
        with patch("sandbox_api_mcp_server.sandbox.service.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            result = await call_sandbox_api("list_sandboxes_for_user", client)
        assert result == {"sandboxes": []}
        assert sleep_mock.await_count == 2
        # Each wait = BASE * 2**(retry-1) + jitter ∈ [0, 0.5].
        for i, call in enumerate(sleep_mock.await_args_list, start=1):
            wait = call.args[0]
            base = BASE_BACKOFF_DELAY * (2 ** (i - 1))
            assert base <= wait <= base + 0.5

    async def test_retry_exhausted_raises_http_exception(self):
        client = AsyncMock(spec=SandboxApiClient)
        client.list_sandboxes_for_user.side_effect = SandboxApiClientError("flake", status_code=503)
        with patch("sandbox_api_mcp_server.sandbox.service.asyncio.sleep", new=AsyncMock()):
            with pytest.raises(HTTPException) as exc:
                await call_sandbox_api("list_sandboxes_for_user", client)
        assert exc.value.status_code == 503
        assert client.list_sandboxes_for_user.await_count == MAX_RETRIES

    async def test_non_retryable_4xx_raises_immediately(self):
        client = AsyncMock(spec=SandboxApiClient)
        client.start_sandbox.side_effect = SandboxApiClientError("nope", status_code=400)
        with patch("sandbox_api_mcp_server.sandbox.service.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            with pytest.raises(HTTPException) as exc:
                await call_sandbox_api("start_sandbox", client, usecase="x")
        assert exc.value.status_code == 400
        assert sleep_mock.await_count == 0
        assert client.start_sandbox.await_count == 1

    async def test_unexpected_exception_becomes_500(self):
        client = AsyncMock(spec=SandboxApiClient)
        client.list_sandboxes_for_user.side_effect = RuntimeError("boom")
        with pytest.raises(HTTPException) as exc:
            await call_sandbox_api("list_sandboxes_for_user", client)
        assert exc.value.status_code == 500


# ---------- module constants (lock for refactors) ----------

class TestConstants:
    def test_retry_constants(self):
        assert MAX_RETRIES == 3
        assert BASE_BACKOFF_DELAY == 1.0
