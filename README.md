# Sandbox API MCP Server

## Overview

This project provides a Model Context Protocol (MCP) server for interacting with the [Neo4j Sandbox API](https://sandbox.neo4j.com/). It allows language models or other MCP clients to easily launch, list, query, and perform other actions on Neo4j Sandbox instances using a standardized tool interface.

The server is built as a [FastAPI](https://fastapi.tiangolo.com/) application and uses [FastMCP](https://gofastmcp.com/) (v2.12.4) to expose its endpoints as MCP tools. FastMCP provides enterprise-grade OAuth 2.1 authentication with Auth0, along with backward compatibility for API key authentication. The necessary Auth0 credentials must be configured through environment variables.

## Environment Variables

The server requires the following environment variables to be set for Auth0 authentication, which is used to secure the MCP tools and interact with the Sandbox API on behalf of the user:

*   `AUTH0_DOMAIN`: Your Auth0 tenant domain (e.g., `your-tenant.auth0.com`).
*   `AUTH0_AUDIENCE`: The Audience for your Auth0 API (e.g., `https://your-tenant.auth0.com/api/v2/`).
*   `AUTH0_CLIENT_ID`: The Client ID of your Auth0 Application.
*   `AUTH0_CLIENT_SECRET`: The Client Secret of your Auth0 Application.
*   `SANDBOX_API_KEY`: Your Neo4j Sandbox API key. This is used by the underlying `neo4j-sandbox-api-client`.
*   `PORT` (optional): The port to run the server on. Defaults to `9100` if not set.

You can set these variables directly in your environment or place them in a `.env` file in the project root.

## Running the Server

1.  **Install UV (if not already installed):**
    ```bash
    # macOS/Linux
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Windows
    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```

2.  **Install dependencies:**
    UV will automatically create a virtual environment and install dependencies:
    ```bash
    uv sync
    ```

3.  **Set environment variables:**
    Ensure the `.env` file is present in the project root and populated with your Auth0 and Sandbox API credentials as described above.

4.  **Run the FastAPI application:**
    The server can be started using UV:
    ```bash
    uv run sandbox-api-mcp-server
    ```
    This will start the server on `http://0.0.0.0:9100`. The MCP server is available at two transport endpoints:
    - `http://0.0.0.0:9100/sse` - SSE transport (legacy, backward compatible)
    - `http://0.0.0.0:9100/mcp` - Streamable HTTP transport (modern, recommended for production)

## Using with MCP Clients (e.g., Claude Desktop)

To use this MCP server with an MCP client, you need to configure the client to connect to the running FastAPI server. This server uses **FastMCP 2.12.4** to expose FastAPI endpoints as MCP tools. Authentication is handled via Auth0 (OAuth2/JWT) and API keys at the FastAPI layer.

**It is recommended to use `mcp-remote`** to bridge the connection, especially if you need to handle OAuth token acquisition. `mcp-remote` can help manage authentication tokens for the HTTP requests to the server.

### Step 1: Install `mcp-remote` (if not already installed)

If you don't have `mcp-remote` (part of the `mcp-cli` package) installed globally, you can use `npx` to run it directly or install it:
```bash
npm install -g mcp-remote
```

### Step 2: Run your FastAPI MCP Server

Ensure your FastAPI MCP server is running locally (e.g., on `http://localhost:9100`):
```bash
uv run sandbox-api-mcp-server
```

The server provides two MCP transport endpoints:
- `http://localhost:9100/sse` - SSE transport (backward compatible)
- `http://localhost:9100/mcp` - Streamable HTTP transport (recommended)


### Step 3: Run `mcp-remote`

In a new terminal, start `mcp-remote`, pointing it to your local MCP server. You can choose either transport endpoint:

**Using SSE (legacy, backward compatible):**
```bash
# If mcp-cli is installed globally
mcp-remote http://localhost:9100/sse 8080

# Or using npx
npx -y mcp-remote http://localhost:9100/sse 8080
```

**Using Streamable HTTP (modern, recommended):**
```bash
# If mcp-cli is installed globally
mcp-remote http://localhost:9100/mcp 8080

# Or using npx
npx -y mcp-remote http://localhost:9100/mcp 8080
```
`mcp-remote` will now listen on `localhost:8080` and proxy requests to your actual MCP server, handling the OAuth flow.

### Step 4: Configure Claude Desktop

1.  **Locate Claude Desktop Configuration:**
    *   **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
    *   **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
    If the file doesn't exist, create it.

2.  **Configure the MCP Server in Claude Desktop:**
    Edit `claude_desktop_config.json` to point to the local port where `mcp-remote` is listening (e.g., `8080`).

    **Option A: Using SSE transport (backward compatible):**
    ```json
    {
        "mcpServers": {
            "neo4j-sandbox-mcp-via-remote": {
            "command": "npx",
            "args": [
                "-y",
                "mcp-remote",
                "http://localhost:9100/sse",
                "8080"
            ]
            }
        }
    }
    ```

    **Option B: Using Streamable HTTP transport (recommended):**
    ```json
    {
        "mcpServers": {
            "neo4j-sandbox-mcp-via-remote": {
            "command": "npx",
            "args": [
                "-y",
                "mcp-remote",
                "http://localhost:9100/mcp",
                "8080"
            ]
            }
        }
    }
    ```
    **Note:** With `mcp-remote` handling the connection to your actual server and its authentication, the Claude Desktop configuration becomes simpler, primarily needing to know where `mcp-remote` is accessible.

3.  **Restart Claude Desktop:**
    Quit and reopen Claude Desktop to load the new configuration.

4.  **Authenticate via Browser:**
    When you first try to use a tool, `mcp-remote` should open a browser window for you to complete the Auth0 login. After successful authentication, Claude Desktop will be able to use the tools.

5.  **Verify Connection:**
    Look for the MCP tools icon in Claude Desktop to confirm connection.

## Available MCP Tools

The following tools are exposed, derived from the FastAPI application's endpoints. The `operation_id` of each FastAPI route becomes the tool name.

---

### `list_sandboxes_for_user`
- **Description**: List all running sandbox instances for the authenticated user.
- **Input**: None
- **Output**: `Dict` (JSON object containing a list of sandboxes)

---

### `start_new_sandbox`
- **Description**: Starts a new sandbox instance for a specified use case.
- **Input**:
    - `usecase` (str): The name of the use case for the sandbox (e.g., 'movies', 'blank').
- **Output**: `Dict` (JSON object representing the newly started sandbox)

---

### `terminate_sandbox`
- **Description**: Stops/terminates a specific sandbox instance.
- **Input**:
    - `sandbox_hash_key` (str): The unique hash key identifying the sandbox.
- **Output**: `Dict` (Typically an empty JSON object `{}` on success, or an error object)

---

### `extend_sandbox_lifetime`
- **Description**: Extends the lifetime of a sandbox or all sandboxes for the user.
- **Input**:
    - `sandbox_hash_key` (Optional[str]): Specific sandbox to extend. If None, all user's sandboxes are extended.
- **Output**: `Dict` (JSON object with status of the extension)

---

### `get_sandbox_connection_details`
- **Description**: Gets connection details for a specific sandbox.
- **Input**:
    - `sandbox_hash_key` (str, path parameter): The unique hash key identifying the sandbox.
    - `verify_connect` (Optional[bool], query parameter, default: `False`): If true, verifies connection to the sandbox.
- **Output**: `Dict` (JSON object containing connection details for the sandbox)

---

### `request_sandbox_backup`
- **Description**: Requests a backup for a specific sandbox.
- **Input**:
    - `sandbox_hash_key` (str, path parameter): The unique hash key identifying the sandbox.
- **Output**: `Dict` (JSON object containing details of the backup request, possibly including a result ID)

---

### `get_backup_result`
- **Description**: Retrieves the result of a specific backup task.
- **Input**:
    - `result_id` (str, path parameter): The ID of the backup/upload task result.
- **Output**: `Dict` (JSON object containing the status and details of the backup task)

---

### `list_sandbox_backups`
- **Description**: Lists available backups for a specific sandbox.
- **Input**:
    - `sandbox_hash_key` (str, path parameter): The unique hash key identifying the sandbox.
- **Output**: `Dict` (JSON object containing a list of available backups)

---

### `get_sandbox_backup_download_url`
- **Description**: Gets a download URL for a specific sandbox backup file.
- **Input**:
    - `sandbox_hash_key` (str, path parameter): The unique hash key identifying the sandbox.
    - `key` (str, in request body): The S3 key of the backup file to download.
- **Output**: `Dict` (JSON object containing the download URL)

---

### `upload_sandbox_to_aura`
- **Description**: Uploads a sandbox backup to an Aura instance.
- **Input**:
    - `sandbox_hash_key` (str): The unique hash key identifying the sandbox backup to upload.
    - `aura_uri` (str): The Aura instance URI (e.g., neo4j+s://xxxx.databases.neo4j.io).
    - `aura_password` (str): Password for the Aura instance.
    - `aura_username` (Optional[str], default: `'neo4j'`): Username for the Aura instance.
- **Output**: `Dict` (JSON object containing details of the upload task, possibly including a result ID)

---

### `get_aura_upload_result`
- **Description**: Retrieves the result of a specific Aura upload task.
- **Input**:
    - `result_id` (str, path parameter): The ID of the Aura upload task result.
- **Output**: `Dict` (JSON object containing the status and details of the Aura upload task)

---

### `get_schema`
- **Description**: Retrieves the schema for a specific sandbox.
- **Input**:
    - `hash_key` (str, query parameter): The hash key of the sandbox.
- **Output**: `Dict` (JSON object containing the schema information)

---

### `read_query`
- **Description**: Executes a read-only Cypher query on a sandbox.
- **Input**:
    - `hash_key` (str): The hash key of the sandbox to query.
    - `query` (str): The Read Cypher query to execute.
    - `params` (Optional[Dict[str, Any]]): Optional parameters for the Cypher query.
- **Output**: `Dict` (JSON object containing the query results)

---

### `write_query`
- **Description**: Executes a write Cypher query on a sandbox.
- **Input**:
    - `hash_key` (str): The hash key of the sandbox to query.
    - `query` (str): The Write Cypher query to execute.
    - `params` (Optional[Dict[str, Any]]): Optional parameters for the Cypher query.
- **Output**: `Dict` (JSON object, typically empty or with summary information)

---

## Development

### Project Structure

*   The main FastAPI application logic is in `src/sandbox_api_mcp_server/server.py`.
*   API routes (which become MCP tools) are defined in `src/sandbox_api_mcp_server/sandbox/routes.py`.
*   Request/response models are primarily in `src/sandbox_api_mcp_server/sandbox/models.py` and `src/sandbox_api_mcp_server/models.py`.
*   Authentication logic is in `src/sandbox_api_mcp_server/auth.py`.
*   Auth0 OAuth provider for FastMCP is in `src/sandbox_api_mcp_server/auth_provider.py`.

### Dependency Management

This project uses [UV](https://docs.astral.sh/uv/) for fast, reliable dependency management:

*   **Adding dependencies**: `uv add <package-name>`
*   **Removing dependencies**: `uv remove <package-name>`
*   **Updating dependencies**: `uv lock --upgrade`
*   **Running scripts**: `uv run <command>`

All dependencies are defined in `pyproject.toml` and locked in `uv.lock` for reproducible builds.

### FastMCP Configuration

The server includes a `fastmcp.json` configuration file for declarative deployment. You can run the server using:

```bash
fastmcp run fastmcp.json
```

This configuration defines the source, environment, and deployment settings for the FastMCP server.

### Authentication Architecture

The server implements authentication at the **FastAPI layer** via the `verify_auth` dependency, which supports:

1. **OAuth2/JWT Tokens via Auth0**
   - Validates JWT tokens issued by Auth0
   - Verifies token signature using JWKS public keys
   - Checks audience, issuer, and other JWT claims
   - MCP clients can use these tokens via standard `Authorization: Bearer <token>` headers

2. **API Key Authentication** (backward compatibility)
   - Supports `Authorization: Bearer ApiKey <key>` header format
   - Maintained in FastAPI routes via `Depends(verify_auth)`
   - Ensures existing API consumers continue to work

**Note on MCP OAuth Support:**
Future versions may implement native MCP OAuth support via `OAuthAuthorizationServerProvider`, which would provide Dynamic Client Registration (DCR) compliance and seamless OAuth flows specifically designed for the MCP protocol. The current implementation leverages FastMCP's ability to convert FastAPI endpoints while maintaining the existing FastAPI authentication system.

### FastMCP Features

This server leverages [FastMCP 2.12.4](https://www.jlowin.dev/blog/fastmcp-2-12) features:

- **FastAPI Integration**: Seamless conversion of FastAPI endpoints to MCP tools via `FastMCP.from_fastapi()`
- **Route Filtering**: Excludes internal endpoints (like `/health`) from MCP tool exposure using `RouteMap` configurations
- **Authentication Compatibility**: Works with existing FastAPI authentication middleware (Auth0 JWT + API keys)
- **Dual Transport Support**: Provides both transport protocols for maximum compatibility
  - **SSE** at `/sse` - Legacy transport for backward compatibility with existing clients
  - **Streamable HTTP** at `/mcp` - Modern transport recommended for production deployments