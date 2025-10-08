import os
import uvicorn

from anyio import get_cancelled_exc_class
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastmcp import FastMCP
from fastmcp.server.openapi import RouteMap, MCPType
from uvicorn._types import ASGI3Application, ASGIReceiveCallable, ASGISendCallable, Scope
from starlette.middleware.base import BaseHTTPMiddleware
from .auth import fetch_jwks_public_key
from .models import Auth0Settings
from .sandbox.routes import get_sandbox_api_router
from .helpers import get_logger

logger = get_logger(__name__)

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.jwks_public_key = await fetch_jwks_public_key(Auth0Settings().auth0_jwks_url)
    yield


class ProxyHeadersMiddleware:
    def __init__(self, app: ASGI3Application) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: ASGIReceiveCallable, send: ASGISendCallable) -> None:
        if scope["type"] == "lifespan":
            return await self.app(scope, receive, send)

        if scope["server"][0] == "127.0.0.1" or scope["server"][0] == "localhost":
            return await self.app(scope, receive, send)

        headers = dict(scope["headers"])
        if b"x-forwarded-proto" in headers:
            x_forwarded_proto = headers[b"x-forwarded-proto"].decode("latin1").strip()

            if x_forwarded_proto in {"http", "https", "ws", "wss"}:
                if scope["type"] == "websocket":
                    scope["scheme"] = x_forwarded_proto.replace("http", "ws")
                else:
                    scope["scheme"] = x_forwarded_proto

        if b"x-forwarded-for" in headers:
            x_forwarded_for = headers[b"x-forwarded-for"].decode("latin1")

            if x_forwarded_for:
                # If the x-forwarded-for header is empty then host is an empty string.
                # Only set the client if we actually got something usable.
                # See: https://github.com/encode/uvicorn/issues/1068

                # We've lost the connecting client's port information by now,
                # so only include the host.
                port = 0
                scope["client"] = (x_forwarded_for, port)

        return await self.app(scope, receive, send)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        # Clickjacking protection
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response


def close_on_double_start(app):
    async def wrapped(scope, receive, send):
        start_sent = False

        async def check_send(message):
            nonlocal start_sent
            if message["type"] == "http.response.start":
                if start_sent:
                    raise get_cancelled_exc_class()()
                start_sent = True
            await send(message)

        await app(scope, receive, check_send)

    return wrapped


def run():
    app = FastAPI(title="SandboxApiMCP", lifespan=lifespan)
    app.include_router(get_sandbox_api_router())
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(ProxyHeadersMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    # Get port from environment or use default
    port = int(os.getenv("PORT", 9100))

    # Define route maps to exclude health_check endpoint from MCP tools
    route_maps = [
        # Exclude health endpoint from MCP tools
        RouteMap(
            methods=["GET"],
            pattern=r".*/health$",
            mcp_type=MCPType.EXCLUDE,  # Exclude from MCP
        ),
        # Map all other endpoints to tools (default behavior)
    ]

    # Convert FastAPI app to MCP server using from_fastapi
    # This will expose FastAPI endpoints as MCP tools
    mcp = FastMCP.from_fastapi(
        app=app,
        name="Neo4j Sandbox API MCP Server",
        route_maps=route_maps,
    )

    # Mount MCP transports - support both for maximum compatibility

    # SSE transport for backward compatibility with existing clients
    sse_app = mcp.sse_app()
    app.mount("/sse", sse_app)

    # Streamable HTTP transport for modern clients (recommended for production)
    streamable_app = mcp.streamable_http_app()
    app.mount("/mcp", streamable_app)

    logger.info("MCP server available at multiple transports:")
    logger.info("  - /sse (SSE transport - legacy, backward compatible)")
    logger.info("  - /mcp (Streamable HTTP transport - modern, recommended)")

    # Authentication Note:
    # - FastAPI routes use Depends(verify_auth) which handles both:
    #   * OAuth2/JWT tokens from Auth0
    #   * API Key authentication (Authorization: Bearer ApiKey <key>)
    # - This provides backward compatibility with existing API consumers
    # - MCP clients will use the existing FastAPI auth via standard HTTP headers

    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    run()
