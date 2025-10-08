FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ADD . /app
WORKDIR /app

# Install dependencies using UV
RUN uv sync --frozen --no-dev

CMD ["uv", "run", "sandbox-api-mcp-server"]