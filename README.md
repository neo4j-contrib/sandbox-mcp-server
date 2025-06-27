# Sandbox API MCP Server

## Overview

This project provides a Model Context Protocol (MCP) server for interacting with the [Neo4j Sandbox API](https://sandbox.neo4j.com/). It allows language models or other MCP clients to easily launch, list, query, and perform other actions on Neo4j Sandbox instances using a standardized tool interface.

The server is built as a [FastAPI](https://fastapi.tiangolo.com/) application and uses the [FastAPI-MCP](https://fastapi-mcp.tadata.com/getting-started/welcome) library to expose its endpoints as MCP tools. Authentication with the Sandbox API is handled via Auth0, and the necessary Auth0 credentials must be configured through environment variables.

## Environment Variables

The server requires the following environment variables to be set for Auth0 authentication, which is used to secure the MCP tools and interact with the Sandbox API on behalf of the user:

*   `AUTH0_DOMAIN`: Your Auth0 tenant domain (e.g., `your-tenant.auth0.com`).
*   `AUTH0_AUDIENCE`: The Audience for your Auth0 API (e.g., `https://your-tenant.auth0.com/api/v2/`).
*   `AUTH0_CLIENT_ID`: The Client ID of your Auth0 Application.
*   `AUTH0_CLIENT_SECRET`: The Client Secret of your Auth0 Application.
*   `SANDBOX_API_KEY`: Your Neo4j Sandbox API key. This is used by the underlying `neo4j-sandbox-api-client`.

You can set these variables directly in your environment or place them in a `.env` file in the project root.

## Running the Server

1.  **Install dependencies:**
    It's recommended to use a virtual environment.
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows use `.venv\\Scripts\\activate`
    pip install -r requirements.txt
    # Or using uv
    # uv pip install -r requirements.txt
    ```

2.  **Set environment variables:**
    Ensure the `.env` file is present in the `mcp-server` directory and populated with your Auth0 and Sandbox API credentials as described above.

3.  **Run the FastAPI application:**
    The server can be started using Uvicorn:
    ```bash
    uvicorn src.sandbox_api_mcp_server.server:run --factory --host 0.0.0.0 --port 9100
    ```
    Alternatively, if you have `src` in your `PYTHONPATH` or are in the `mcp-server` directory:
    ```bash
    python src/sandbox_api_mcp_server/server.py
    ```
    This will typically start the server on `http://0.0.0.0:9100`. The MCP endpoint will be available at `http://0.0.0.0:9100/sse` (as configured in `server.py`).

## Using with MCP Clients (e.g., Claude Desktop)

To use this MCP server with an MCP client, you need to configure the client to connect to the running FastAPI server. Given the OAuth2 flow used for authentication, **it is highly recommended to use `mcp-remote`** to bridge the connection. `mcp-remote` will handle the browser-based login and token passing to the MCP server.

### Step 1: Install `mcp-remote` (if not already installed)

If you don't have `mcp-remote` (part of the `mcp-cli` package) installed globally, you can use `npx` to run it directly or install it:
```bash
npm install -g mcp-remote
```

### Step 2: Run your FastAPI MCP Server

Ensure your FastAPI MCP server is running locally (e.g., on `http://localhost:9100` with the MCP endpoint at `http://localhost:9100/sse`):
```bash
python src/sandbox_api_mcp_server/server.py
```
Or using uvicorn directly:
```bash
uvicorn src.sandbox_api_mcp_server.server:run --factory --host 0.0.0.0 --port 9100
```


### Step 3: Run `mcp-remote`

In a new terminal, start `mcp-remote`, pointing it to your local MCP server's `/sse` endpoint and choosing a local port for `mcp-remote` to listen on (e.g., `8080`):

```bash
# If mcp-cli is installed globally
mcp-remote http://localhost:9100/sse 8080

# Or using npx
npx -y mcp-remote http://localhost:9100/sse 8080
```
`mcp-remote` will now listen on `localhost:8080` and proxy requests to your actual MCP server, handling the OAuth flow.

### Step 4: Configure Claude Desktop

1.  **Locate Claude Desktop Configuration:**
    *   **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
    *   **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
    If the file doesn't exist, create it.

2.  **Configure the MCP Server in Claude Desktop:**
    Edit `claude_desktop_config.json` to point to the local port where `mcp-remote` is listening (e.g., `8080`).

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
    - `cease_emails` (Optional[bool], default: `False`): If true, no emails will be sent regarding this sandbox.
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
    - `profile_data` (Optional[Dict[str, Any]]): User profile information.
- **Output**: `Dict` (JSON object with status of the extension)

---

### `get_sandbox_connection_details`
- **Description**: Gets connection details for a specific sandbox.
- **Input**:
    - `sandbox_hash_key` (str, path parameter): The unique hash key identifying the sandbox.
    - `verify_connect` (Optional[bool], query parameter, default: `False`): If true, verifies connection to the sandbox.
- **Output**: `Dict` (JSON object containing connection details for the sandbox)

---

### `invite_sandbox_collaborator`
- **Description**: Invites a collaborator to a specific sandbox.
- **Input**:
    - `sandbox_hash_key` (str): The unique hash key identifying the sandbox to share.
    - `email` (str): Email address of the user to invite.
    - `message` (str): A personal message to include in the invitation.
- **Output**: `Dict` (JSON object with the status of the invitation)

---

### `get_user_information`
- **Description**: Retrieves user information for the authenticated user (from Sandbox API if needed, or use token data).
- **Input**: None
- **Output**: `Dict` (JSON object containing user information)

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

*   The main FastAPI application logic is in `src/sandbox_api_mcp_server/server.py`.
*   API routes (which become MCP tools) are defined in `src/sandbox_api_mcp_server/sandbox/routes.py`.
*   Request/response models are primarily in `src/sandbox_api_mcp_server/sandbox/models.py` and `src/sandbox_api_mcp_server/models.py`.
*   Authentication logic is in `src/sandbox_api_mcp_server/auth.py`.
*   The project uses `uv` for dependency management (see `uv.lock`) and `pip` for installation (`requirements.txt`).
*   Consider using `hatch` or `poetry` for more robust dependency management and packaging if distributing this server. (The `pyproject.toml` suggests `hatch` might be intended for future use).