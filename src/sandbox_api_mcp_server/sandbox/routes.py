from fastapi import APIRouter
from typing import Annotated, Dict, Optional
from fastapi import Depends
from fastapi import Query, Path, status
from fastapi.responses import PlainTextResponse

from .models import StartSandboxBody, StopSandboxBody, ExtendSandboxBody, AuraUploadBody, BackupDownloadUrlBody, FastApiReadCypherQueryBody, FastApiWriteCypherQueryBody, FastApiReadCypherQueryResponse
from ..helpers import get_logger
from .service import call_sandbox_api, SandboxApiClient, get_sandbox_client

logger = get_logger(__name__)


def get_sandbox_api_router() -> APIRouter:
    router = APIRouter()

    # Each operation_id will be the MCP tool name as per fastapi-mcp docs.
    @router.get("/list-sandboxes", operation_id="list_sandboxes_for_user", tags=["Sandbox"], response_model=Dict)
    async def list_sandboxes(
        client: Annotated[SandboxApiClient, Depends(get_sandbox_client)],
    ):
        """List all running sandbox instances for the authenticated user."""
        # timezone: Optional[str] = Query(None, description="User's timezone for accurate expiration calculation.")
        # The original tool didn't expose timezone, keeping it simple here.
        try:
            return await call_sandbox_api("list_sandboxes_for_user", client)
        except Exception as e:
            logger.error(f"Error listing sandboxes: {e}")
            raise e

    @router.post("/start-sandbox", operation_id="start_new_sandbox", tags=["Sandbox"], response_model=Dict, status_code=status.HTTP_201_CREATED)
    async def start_sandbox(
        body: StartSandboxBody,
        client: Annotated[SandboxApiClient, Depends(get_sandbox_client)],
    ):
        """Starts a new sandbox instance for a specified use case."""
        try:
            return await call_sandbox_api("start_sandbox", client, usecase=body.usecase)
        except Exception as e:
            logger.error(f"Error starting sandbox: {e}")
            raise e

    @router.post("/terminate-sandbox", operation_id="terminate_sandbox", tags=["Sandbox"], response_model=Dict)
    async def terminate_sandbox(
        body: StopSandboxBody,
        client: Annotated[SandboxApiClient, Depends(get_sandbox_client)],
    ):
        """Stops/terminates a specific sandbox instance."""
        try:
            return await call_sandbox_api("stop_sandbox", client, sandbox_hash_key=body.sandbox_hash_key)
        except Exception as e:
            logger.error(f"Error stopping sandbox: {e}")
            raise e

    @router.post("/extend-sandbox", operation_id="extend_sandbox_lifetime", tags=["Sandbox"], response_model=Dict)
    async def extend_sandbox(
        body: ExtendSandboxBody,
        client: Annotated[SandboxApiClient, Depends(get_sandbox_client)],
    ):
        """Extends the lifetime of a sandbox or all sandboxes for the user."""
        try:
            return await call_sandbox_api("extend_sandbox", client, sandbox_hash_key=body.sandbox_hash_key)
        except Exception as e:
            logger.error(f"Error extending sandbox: {e}")
            raise e

    @router.get("/get-sandbox-details/{sandbox_hash_key}", operation_id="get_sandbox_connection_details", tags=["Sandbox"], response_model=Dict)
    async def get_sandbox_details(
        sandbox_hash_key: Annotated[str, Path(description="The unique hash key identifying the sandbox.")],
        client: Annotated[SandboxApiClient, Depends(get_sandbox_client)],
        *,  # Make subsequent parameters keyword-only
        verify_connect: Annotated[Optional[bool], Query(description="If true, verifies connection to the sandbox.")] = False
    ):
        """Gets connection details for a specific sandbox."""
        try:
            return await call_sandbox_api("get_sandbox_details", client, sandbox_hash_key=sandbox_hash_key, verify_connect=verify_connect)
        except Exception as e:
            logger.error(f"Error getting sandbox details: {e}")
            raise e

    # --- Backup Related Endpoints ---
    @router.post("/request-backup/{sandbox_hash_key}", operation_id="request_sandbox_backup", tags=["Backup"], response_model=Dict)
    async def request_backup_ep(
        sandbox_hash_key: Annotated[str, Path(description="The unique hash key identifying the sandbox.")],
        client: Annotated[SandboxApiClient, Depends(get_sandbox_client)],
    ):
        """Requests a backup for a specific sandbox."""
        try:
            return await call_sandbox_api("request_backup", client, sandbox_hash_key=sandbox_hash_key)
        except Exception as e:
            logger.error(f"Error requesting backup: {e}")
            raise e

    @router.get("/backups/result/{result_id}", operation_id="get_backup_result", tags=["Backup"], response_model=Dict)
    async def get_backup_result_ep(
        result_id: Annotated[str, Path(description="The ID of the backup/upload task result.")],
        client: Annotated[SandboxApiClient, Depends(get_sandbox_client)],
    ):
        """Retrieves the result of a specific backup task."""
        try:
            return await call_sandbox_api("get_backup_result", client, result_id=result_id)
        except Exception as e:
            logger.error(f"Error getting backup result: {e}")
            raise e

    @router.get("/list-backups/{sandbox_hash_key}", operation_id="list_sandbox_backups", tags=["Backup"], response_model=Dict)
    async def list_backups_ep(
        sandbox_hash_key: Annotated[str, Path(description="The unique hash key identifying the sandbox.")],
        client: Annotated[SandboxApiClient, Depends(get_sandbox_client)],
    ):
        """Lists available backups for a specific sandbox."""
        try:
            return await call_sandbox_api("list_backups", client, sandbox_hash_key=sandbox_hash_key)
        except Exception as e:
            logger.error(f"Error listing backups: {e}")
            raise e

    @router.post("/get-backup-download-url/{sandbox_hash_key}", operation_id="get_sandbox_backup_download_url", tags=["Backup"], response_model=Dict)
    async def get_backup_download_url_ep(
        sandbox_hash_key: Annotated[str, Path(description="The unique hash key identifying the sandbox.")],
        body: BackupDownloadUrlBody,
        client: Annotated[SandboxApiClient, Depends(get_sandbox_client)],
    ):
        """Gets a download URL for a specific sandbox backup file."""
        try:
            return await call_sandbox_api("get_backup_download_url", client, sandbox_hash_key=sandbox_hash_key, key=body.key)
        except Exception as e:
            logger.error(f"Error getting backup download URL: {e}")
            raise e

    # --- Aura Upload Related Endpoints ---
    @router.post("/upload-to-aura", operation_id="upload_sandbox_to_aura", tags=["Aura"], response_model=Dict)
    async def upload_to_aura_ep(
        body: AuraUploadBody,
        client: Annotated[SandboxApiClient, Depends(get_sandbox_client)],
    ):
        """Uploads a sandbox backup to an Aura instance."""
        try:
            return await call_sandbox_api(
                "upload_to_aura",
                client,
                sandbox_hash_key=body.sandbox_hash_key,
                aura_uri=body.aura_uri,
                aura_password=body.aura_password,
                aura_username=body.aura_username,
            )
        except Exception as e:
            logger.error(f"Error uploading to Aura: {e}")
            raise e

    @router.get("/aura-upload/result/{result_id}", operation_id="get_aura_upload_result", tags=["Aura"], response_model=Dict)
    async def get_aura_upload_result_ep(
        result_id: Annotated[str, Path(description="The ID of the Aura upload task result.")],
        client: Annotated[SandboxApiClient, Depends(get_sandbox_client)],
    ):
        """Retrieves the result of a specific Aura upload task."""
        try:
            return await call_sandbox_api("get_aura_upload_result", client, result_id=result_id)
        except Exception as e:
            logger.error(f"Error getting Aura upload result: {e}")
            raise e

    @router.get("/query/schema", operation_id="get_schema", tags=["Query"], response_model=FastApiReadCypherQueryResponse)
    async def get_schema(hash_key: str, client: Annotated[SandboxApiClient, Depends(get_sandbox_client)]):
        try:
            return await call_sandbox_api("get_schema", client, hash_key=hash_key)
        except Exception as e:
            logger.error(f"Error getting schema: {e}")
            raise e

    @router.post("/query/read", operation_id="read_query", tags=["Query"], response_model=FastApiReadCypherQueryResponse)
    async def read(cypher_query: FastApiReadCypherQueryBody, client: Annotated[SandboxApiClient, Depends(get_sandbox_client)]):
        try:
            return await call_sandbox_api("read_query", client, hash_key=cypher_query.hash_key, query=cypher_query.query, params=cypher_query.params)
        except Exception as e:
            logger.error(f"Error reading query: {e}")
            raise e

    @router.post("/query/write", operation_id="write_query", tags=["Query"], response_model=FastApiReadCypherQueryResponse)
    async def write(cypher_query: FastApiWriteCypherQueryBody, client: Annotated[SandboxApiClient, Depends(get_sandbox_client)]):
        try:
            return await call_sandbox_api("write_query", client, hash_key=cypher_query.hash_key, query=cypher_query.query, params=cypher_query.params)
        except Exception as e:
            logger.error(f"Error writing query: {e}")
            raise e

    @router.get("/health", tags=["Management"], operation_id="health_check")
    async def health_check_endpoint() -> PlainTextResponse:
        return PlainTextResponse("Ok", status_code=200)

    return router
