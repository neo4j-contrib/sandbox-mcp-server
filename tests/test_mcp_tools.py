"""Tests for the MCP tool inventory exposed by FastMCP.from_fastapi().

If the OpenAPI parser, route-map handling, or tool-naming logic changes (e.g.
across a fastmcp upgrade), this file catches it.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastmcp import FastMCP
from fastmcp.server.providers.openapi import MCPType, RouteMap

from sandbox_api_mcp_server.sandbox.routes import get_sandbox_api_router


EXPECTED_TOOLS = {
    "list_sandboxes_for_user",
    "start_new_sandbox",
    "terminate_sandbox",
    "extend_sandbox_lifetime",
    "get_sandbox_connection_details",
    "request_sandbox_backup",
    "get_backup_result",
    "list_sandbox_backups",
    "get_sandbox_backup_download_url",
    "upload_sandbox_to_aura",
    "get_aura_upload_result",
    "get_schema",
    "read_query",
    "write_query",
}


@pytest.fixture
def mcp() -> FastMCP:
    app = FastAPI()
    app.include_router(get_sandbox_api_router())
    return FastMCP.from_fastapi(
        app=app,
        name="Neo4j Sandbox API MCP Server",
        route_maps=[
            RouteMap(methods=["GET"], pattern=r".*/health$", mcp_type=MCPType.EXCLUDE),
        ],
    )


async def _tools_by_name(mcp):
    # list_tools returns Sequence[Tool]; index by name for assertions.
    tools = await mcp.list_tools()
    return {t.name: t for t in tools}


async def test_exact_tool_set(mcp):
    by_name = await _tools_by_name(mcp)
    assert set(by_name) == EXPECTED_TOOLS, (
        f"missing: {EXPECTED_TOOLS - set(by_name)}, extra: {set(by_name) - EXPECTED_TOOLS}"
    )
    assert len(by_name) == 14


async def test_health_check_excluded(mcp):
    by_name = await _tools_by_name(mcp)
    assert "health_check" not in by_name


async def test_every_tool_has_a_name_attribute(mcp):
    by_name = await _tools_by_name(mcp)
    for key, tool in by_name.items():
        assert hasattr(tool, "name"), f"tool {key} missing .name"
        assert tool.name == key, f"tool {key} has mismatched .name={tool.name!r}"


async def test_query_tools_take_expected_inputs(mcp):
    """Lock the input schemas for the three query tools — these are the most-used."""
    by_name = await _tools_by_name(mcp)

    read = by_name["read_query"]
    props = read.parameters.get("properties", {})
    required = set(read.parameters.get("required", []))
    assert {"hash_key", "query"} <= required
    assert {"hash_key", "params", "query"} <= set(props)

    write = by_name["write_query"]
    props = write.parameters.get("properties", {})
    required = set(write.parameters.get("required", []))
    assert {"hash_key", "query"} <= required
    assert {"hash_key", "params", "query"} <= set(props)

    schema = by_name["get_schema"]
    props = schema.parameters.get("properties", {})
    assert "hash_key" in props


async def test_sandbox_management_tools_take_expected_inputs(mcp):
    by_name = await _tools_by_name(mcp)

    start = by_name["start_new_sandbox"]
    assert "usecase" in set(start.parameters.get("required", []))

    term = by_name["terminate_sandbox"]
    assert "sandbox_hash_key" in set(term.parameters.get("required", []))

    ext = by_name["extend_sandbox_lifetime"]
    assert "sandbox_hash_key" not in set(ext.parameters.get("required", []))
    assert "sandbox_hash_key" in ext.parameters.get("properties", {})

    aura = by_name["upload_sandbox_to_aura"]
    aura_required = set(aura.parameters.get("required", []))
    assert {"sandbox_hash_key", "aura_uri", "aura_password"} <= aura_required


async def test_get_sandbox_connection_details_takes_path_param(mcp):
    by_name = await _tools_by_name(mcp)
    tool = by_name["get_sandbox_connection_details"]
    props = tool.parameters.get("properties", {})
    assert "sandbox_hash_key" in props
    assert "sandbox_hash_key" in set(tool.parameters.get("required", []))
