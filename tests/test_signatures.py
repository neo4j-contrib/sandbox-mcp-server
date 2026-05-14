"""Signature lock-in tests.

These assert the public surface of every module hasn't drifted. They catch:
- renamed parameters,
- removed/added required parameters,
- changed defaults.

Each check pins parameter NAMES and the set of REQUIRED params (i.e. those with
no default). We deliberately do NOT pin annotations — those can be tightened
without changing observable behavior.
"""
from __future__ import annotations

import inspect

from sandbox_api_mcp_server import auth, helpers, server
from sandbox_api_mcp_server.auth_provider import get_auth0_settings
from sandbox_api_mcp_server.sandbox import routes as routes_mod
from sandbox_api_mcp_server.sandbox import service as service_mod
from sandbox_api_mcp_server.sandbox.service import SandboxApiClient


def _required_params(fn) -> list[str]:
    sig = inspect.signature(fn)
    return [
        name
        for name, p in sig.parameters.items()
        if p.default is inspect.Parameter.empty
        and p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        and name != "self"
    ]


def _param_names(fn) -> list[str]:
    return [
        name
        for name, p in inspect.signature(fn).parameters.items()
        if p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        and name != "self"
    ]


# ---------- auth.py ----------

class TestAuthSignatures:
    def test_verify_auth(self):
        assert inspect.iscoroutinefunction(auth.verify_auth)
        assert _param_names(auth.verify_auth) == ["request"]
        assert _required_params(auth.verify_auth) == ["request"]

    def test_fetch_jwks_public_key(self):
        assert inspect.iscoroutinefunction(auth.fetch_jwks_public_key)
        assert _param_names(auth.fetch_jwks_public_key) == ["url"]
        assert _required_params(auth.fetch_jwks_public_key) == ["url"]


# ---------- auth_provider.py ----------

def test_get_auth0_settings_takes_no_args():
    assert _param_names(get_auth0_settings) == []


# ---------- helpers.py ----------

def test_get_logger_signature():
    assert _param_names(helpers.get_logger) == ["name"]
    assert _required_params(helpers.get_logger) == ["name"]


# ---------- sandbox/service.py ----------

class TestSandboxApiClientSignatures:
    def test_constructor(self):
        assert _required_params(SandboxApiClient.__init__) == ["access_token"]

    def test_close(self):
        assert inspect.iscoroutinefunction(SandboxApiClient.close)
        assert _param_names(SandboxApiClient.close) == []

    def test_list_sandboxes_for_user(self):
        m = SandboxApiClient.list_sandboxes_for_user
        assert inspect.iscoroutinefunction(m)
        assert _param_names(m) == ["timezone"]
        assert _required_params(m) == []  # timezone has default None

    def test_start_sandbox(self):
        m = SandboxApiClient.start_sandbox
        assert inspect.iscoroutinefunction(m)
        assert _param_names(m) == ["usecase"]
        assert _required_params(m) == ["usecase"]

    def test_stop_sandbox(self):
        m = SandboxApiClient.stop_sandbox
        assert _param_names(m) == ["sandbox_hash_key"]
        assert _required_params(m) == ["sandbox_hash_key"]

    def test_extend_sandbox(self):
        m = SandboxApiClient.extend_sandbox
        assert _param_names(m) == ["sandbox_hash_key"]
        assert _required_params(m) == []

    def test_get_sandbox_details(self):
        m = SandboxApiClient.get_sandbox_details
        assert _param_names(m) == ["sandbox_hash_key", "verify_connect"]
        assert _required_params(m) == ["sandbox_hash_key"]

    def test_request_backup(self):
        m = SandboxApiClient.request_backup
        assert _param_names(m) == ["sandbox_hash_key"]
        assert _required_params(m) == ["sandbox_hash_key"]

    def test_get_backup_result(self):
        m = SandboxApiClient.get_backup_result
        assert _param_names(m) == ["result_id"]
        assert _required_params(m) == ["result_id"]

    def test_list_backups(self):
        m = SandboxApiClient.list_backups
        assert _param_names(m) == ["sandbox_hash_key"]
        assert _required_params(m) == ["sandbox_hash_key"]

    def test_get_backup_download_url(self):
        m = SandboxApiClient.get_backup_download_url
        assert _param_names(m) == ["sandbox_hash_key", "key"]
        assert _required_params(m) == ["sandbox_hash_key", "key"]

    def test_upload_to_aura(self):
        m = SandboxApiClient.upload_to_aura
        assert _param_names(m) == ["sandbox_hash_key", "aura_uri", "aura_password", "aura_username"]
        assert _required_params(m) == ["sandbox_hash_key", "aura_uri", "aura_password"]

    def test_get_aura_upload_result(self):
        m = SandboxApiClient.get_aura_upload_result
        assert _param_names(m) == ["result_id"]
        assert _required_params(m) == ["result_id"]

    def test_get_schema(self):
        m = SandboxApiClient.get_schema
        assert _param_names(m) == ["hash_key"]
        assert _required_params(m) == ["hash_key"]

    def test_read_query(self):
        m = SandboxApiClient.read_query
        assert _param_names(m) == ["hash_key", "query", "params"]
        assert _required_params(m) == ["hash_key", "query"]

    def test_write_query(self):
        m = SandboxApiClient.write_query
        assert _param_names(m) == ["hash_key", "query", "params"]
        assert _required_params(m) == ["hash_key", "query"]


class TestServiceFunctionSignatures:
    def test_get_sandbox_client(self):
        # `user: Annotated[..., Depends(verify_auth)]` — the param exists and is required.
        assert _param_names(service_mod.get_sandbox_client) == ["user"]

    def test_call_sandbox_api(self):
        # Async; takes (api_method_name, client, **kwargs).
        assert inspect.iscoroutinefunction(service_mod.call_sandbox_api)
        params = inspect.signature(service_mod.call_sandbox_api).parameters
        assert list(params.keys())[:2] == ["api_method_name", "client"]
        # last param must be **kwargs
        last = list(params.values())[-1]
        assert last.kind == inspect.Parameter.VAR_KEYWORD

    def test_error_class_constructor(self):
        ctor = service_mod.SandboxApiClientError.__init__
        # message required; status_code optional
        assert _required_params(ctor) == ["message"]
        assert "status_code" in _param_names(ctor)


# ---------- sandbox/routes.py ----------

def test_get_sandbox_api_router_signature():
    assert _param_names(routes_mod.get_sandbox_api_router) == []


# ---------- server.py ----------

def test_server_run_signature():
    assert _param_names(server.run) == []


def test_module_level_lifespan_takes_app():
    assert _param_names(server.lifespan) == ["app"]


def test_close_on_double_start_signature():
    assert _param_names(server.close_on_double_start) == ["app"]
