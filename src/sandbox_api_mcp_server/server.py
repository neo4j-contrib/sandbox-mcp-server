import os
import uvicorn

from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi_mcp import AuthConfig, FastApiMCP
from uvicorn._types import ASGI3Application, ASGIReceiveCallable, ASGISendCallable, Scope
from starlette.middleware.base import BaseHTTPMiddleware
from auth import fetch_jwks_public_key, verify_auth
from models import Auth0Settings
from sandbox.routes import get_sandbox_api_router
from helpers import get_logger

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
    fastapi_mcp = FastApiMCP(
        app,
        name="Neo4j Sandbox API MCP Server",
        description="Neo4j Sandbox API MCP Server.",
        exclude_operations=["health_check"],
        auth_config=AuthConfig(
            issuer=f"https://{Auth0Settings().auth0_domain}/",
            authorize_url=f"https://{Auth0Settings().auth0_domain}/authorize",
            oauth_metadata_url=Auth0Settings().auth0_oauth_metadata_url,
            audience=Auth0Settings().auth0_audience,
            default_scope="read:account-info openid email profile user_metadata",
            client_id=Auth0Settings().auth0_client_id,
            client_secret=Auth0Settings().auth0_client_secret,
            dependencies=[Depends(verify_auth)],
            setup_proxies=True,
        ),
    )

    # Mount the MCP server
    fastapi_mcp.mount(mount_path="/sse")

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 9100)))


if __name__ == "__main__":
    run()
