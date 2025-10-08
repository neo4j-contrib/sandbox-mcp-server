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
    """
    Run the FastAPI server with MCP integration.

    IMPORTANT: This uses a combined lifespan approach because http_app() requires
    its lifespan to be run to initialize the task group. Simply mounting http_app
    on a FastAPI app will NOT work - you MUST combine the lifespans.

    See: https://gofastmcp.com/integrations/asgi#asgi-starlette-fastmcp
    """
    port = int(os.getenv("PORT", 9100))

    # Step 1: Create temporary FastAPI app for MCP conversion
    temp_app = FastAPI(title="SandboxApiMCP")
    temp_app.include_router(get_sandbox_api_router())

    route_maps = [
        # Exclude health endpoint from MCP tools
        RouteMap(
            methods=["GET"],
            pattern=r".*/health$",
            mcp_type=MCPType.EXCLUDE,  # Exclude from MCP
        ),
    ]

    # Step 2: Convert to MCP and get http_app
    mcp = FastMCP.from_fastapi(
        app=temp_app,
        name="Neo4j Sandbox API MCP Server",
        route_maps=route_maps,
    )
    http_app = mcp.http_app()

    # Step 3: Create combined lifespan
    @asynccontextmanager
    async def combined_lifespan(app: FastAPI):
        # Initialize JWKS public key
        app.state.jwks_public_key = await fetch_jwks_public_key(Auth0Settings().auth0_jwks_url)
        # Run MCP app lifespan (required for task group initialization)
        async with http_app.lifespan(app):
            yield

    # Step 4: Create final FastAPI app with combined lifespan
    app = FastAPI(title="SandboxApiMCP", lifespan=combined_lifespan)
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

    # Step 5: Mount HTTP app at root
    app.mount("", http_app)

    logger.info("MCP server available at:")
    logger.info("  - /mcp (HTTP transport)")

    # Authentication Note:
    # - FastAPI routes use Depends(verify_auth) which handles both:
    #   * OAuth2/JWT tokens from Auth0
    #   * API Key authentication (Authorization: Bearer ApiKey <key>)
    # - This provides backward compatibility with existing API consumers
    # - MCP clients will use the existing FastAPI auth via standard HTTP headers

    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    run()
