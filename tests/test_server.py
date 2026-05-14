"""Tests for server.py wiring.

run() is not called directly (it blocks in uvicorn.run). Instead we build the
FastMCP object the same way run() does and assert the seams the upgrade path
is most likely to move: from_fastapi, http_app, list_tools, lifespan.
"""
from __future__ import annotations

import inspect

import pytest
from fastapi import FastAPI
from fastmcp import FastMCP
from fastmcp.server.providers.openapi import MCPType, RouteMap

from sandbox_api_mcp_server import server
from sandbox_api_mcp_server.sandbox.routes import get_sandbox_api_router


def _build_mcp() -> FastMCP:
    app = FastAPI(title="SandboxApiMCP")
    app.include_router(get_sandbox_api_router())
    route_maps = [
        RouteMap(methods=["GET"], pattern=r".*/health$", mcp_type=MCPType.EXCLUDE),
    ]
    return FastMCP.from_fastapi(app=app, name="Neo4j Sandbox API MCP Server", route_maps=route_maps)


class TestRunEntryPoint:
    def test_run_is_callable(self):
        assert callable(server.run)

    def test_build_app_is_callable(self):
        assert callable(server.build_app)

    def test_module_exposes_run_via_init(self):
        from sandbox_api_mcp_server import server as srv, main
        # Locks the [project.scripts] entry-point in pyproject.toml.
        assert callable(srv.run)
        assert callable(main)


class TestBuildApp:
    def test_returns_fastapi_app(self):
        app = server.build_app()
        assert isinstance(app, FastAPI)

    def test_app_has_sandbox_routes(self):
        app = server.build_app()
        paths = {r.path for r in app.routes}  # type: ignore[attr-defined]
        assert "/health" in paths
        assert "/list-sandboxes" in paths
        assert "/query/read" in paths

    def test_app_has_sse_redirect(self):
        app = server.build_app()
        paths = {r.path for r in app.routes}  # type: ignore[attr-defined]
        assert "/sse" in paths


class TestFastMCPConversion:
    def test_from_fastapi_returns_object_with_required_helpers(self):
        mcp = _build_mcp()
        assert hasattr(mcp, "http_app")
        assert hasattr(mcp, "list_tools")

    def test_http_app_sse_transport_returns_asgi_app(self):
        mcp = _build_mcp()
        app = mcp.http_app(transport="sse")
        assert callable(app)

    def test_http_app_returns_asgi_app_with_lifespan(self):
        mcp = _build_mcp()
        app = mcp.http_app()
        assert callable(app)
        # server.run composes http_app.lifespan(app) as an async context manager.
        assert hasattr(app, "lifespan")

    def test_health_endpoint_excluded(self):
        import asyncio

        mcp = _build_mcp()
        tools = asyncio.run(mcp.list_tools())
        names = {t.name for t in tools}
        assert "health_check" not in names


class TestMiddlewareClasses:
    def test_proxy_headers_middleware_constructable(self):
        async def fake_app(scope, receive, send):
            pass
        mw = server.ProxyHeadersMiddleware(fake_app)
        assert mw.app is fake_app

    def test_security_headers_middleware_class_exists(self):
        from starlette.middleware.base import BaseHTTPMiddleware
        assert issubclass(server.SecurityHeadersMiddleware, BaseHTTPMiddleware)
        sig = inspect.signature(server.SecurityHeadersMiddleware.dispatch)
        assert list(sig.parameters) == ["self", "request", "call_next"]
