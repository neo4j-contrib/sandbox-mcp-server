import asyncio
import httpx
import os
import random
from typing import Annotated, Optional, Dict, Any
from fastapi import HTTPException, status, Depends

from auth import verify_auth
from helpers import get_logger
from .models import FastApiReadCypherQueryResponse

MAX_RETRIES = 3
BASE_BACKOFF_DELAY = 1.0
logger = get_logger(__name__)


class SandboxApiClientError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class SandboxApiClient:
    def __init__(self, access_token: str):
        if not access_token:
            raise ValueError("access_token cannot be empty.")
        hostname = os.getenv("SANDBOX_API_HOSTNAME", "https://api.sandbox.neo4j.com")
        self.access_token = access_token
        self.client = httpx.AsyncClient(base_url=hostname, timeout=30.0)
        self.headers = {
            "Authorization": self.access_token,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    async def _request(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None, json_data: Optional[Dict[str, Any]] = None) -> Any:
        logger.info(f"Requesting {method} {endpoint} with params: {params} and json_data: {json_data}")
        try:
            response = await self.client.request(method, endpoint, params=params, json=json_data, headers=self.headers)
            response.raise_for_status()
            if response.status_code == 204 or response.status_code == 202:
                return None  # Or an empty dict, depending on desired non-content response
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error: {e.response.status_code} - {e.response.text}")
            try:
                error_details = e.response.json()
                err_msg = error_details.get("error") or error_details.get("Error") or error_details.get("errorString") or str(error_details.get("errors", {}))
                raise SandboxApiClientError(f"Sandbox API Error ({e.response.status_code}): {err_msg}", status_code=e.response.status_code) from e
            except Exception:
                raise SandboxApiClientError(f"Sandbox API Error ({e.response.status_code}): {e.response.text}", status_code=e.response.status_code) from e
        except httpx.RequestError as e:
            logger.error(f"Request error: {e}")
            raise SandboxApiClientError(f"Request failed: {e}", status_code=503) from e  # Service Unavailable
        except Exception as e:
            logger.error(f"Unexpected error in API client: {e}", exc_info=True)
            raise SandboxApiClientError(f"An unexpected error occurred: {e}", status_code=500) from e

    async def close(self):
        await self.client.aclose()

    async def list_sandboxes_for_user(self, timezone: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieves details of all running sandbox instances for the authenticated user.
        Corresponds to GET /SandboxGetRunningInstancesForUser in swagger.

        Args:
            timezone (Optional[str]): User's timezone for accurate expiration calculation (e.g., 'America/New_York').

        Returns:
            Dict[str, Any]: A list of the user's running sandbox instances.
                            See #/components/schemas/RunningInstances in swagger.
        """
        params: Dict[str, Any] = {}
        if timezone is not None:
            params["timezone"] = timezone

        return {
            "sandboxes": await self._request("GET", "/SandboxGetRunningInstancesForUser", params=params),
        }

    async def start_sandbox(self, usecase: str) -> Dict[str, Any]:
        """
        Creates and deploys a new sandbox instance or returns an existing one if duplicates are not allowed and one exists.
        Corresponds to POST /SandboxRunInstance in swagger.

        Args:
            usecase (str): The name of the use case for the sandbox. Possible values are:
                blank-sandbox,bloom,citations,contact-tracing,cybersecurity,entity-resolution,fincen,
                fraud-detection,graph-data-science,graph-data-science-blank-sandbox,healthcare-analytics,
                icij-offshoreleaks,icij-paradise-papers,legis-graph,movies,network-management,
                openstreetmap,pole,recommendations,twitch,twitter-trolls,wwc2019,yelp,twitter-v2

        Returns:
            Dict[str, Any]: Sandbox instance details or draft confirmation.
                            See #/components/schemas/RunInstanceResponse in swagger.
        """
        return await self._request("POST", "/SandboxRunInstance", json_data={"usecase": usecase})

    async def stop_sandbox(self, sandbox_hash_key: str) -> Optional[Dict[str, Any]]:
        """
        Stops a running sandbox instance.
        Corresponds to POST /SandboxStopInstance in swagger.

        Args:
            sandbox_hash_key (str): The unique hash key identifying the sandbox to stop.

        Returns:
            Optional[Dict[str, Any]]: Successfully stopped the instance (often an empty object or None if 204/202)
                                     or no running tasks found. See #/components/schemas/StopInstanceResponse.
        """
        json_data = {"sandboxHashKey": sandbox_hash_key}
        return await self._request("POST", "/SandboxStopInstance", json_data=json_data)

    async def extend_sandbox(self, sandbox_hash_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Extends the lifetime of a user's sandbox(es). User profile details can be submitted with this request.
        Corresponds to POST /SandboxExtend in swagger.

        Args:
            sandbox_hash_key (Optional[str]): Specific sandbox to extend. If not provided, all user's sandboxes are extended.

        Returns:
            Dict[str, Any]: Sandbox lifetime extension status. See #/components/schemas/ExtendResponse.
        """
        json_data: Dict[str, Any] = {}
        if sandbox_hash_key:
            json_data["sandboxHashKey"] = sandbox_hash_key
        return await self._request("POST", "/SandboxExtend", json_data=json_data)

    async def get_sandbox_details(self, sandbox_hash_key: str, verify_connect: Optional[bool] = False) -> Dict[str, Any]:
        """
        Retrieves details of a specific sandbox instance for the authenticated user.
        Corresponds to GET /SandboxAuthdGetInstanceByHashKey in swagger.

        Args:
            sandbox_hash_key (str): The unique hash key identifying the sandbox.
            verify_connect (Optional[bool]): If true, verifies connection to the sandbox. (default: false)

        Returns:
            Dict[str, Any]: Sandbox details. See #/components/schemas/AuthdGetInstanceByHashKeyResponse.
                            Can also be plain text 'ip:port'.
        """
        params = {"sandboxHashKey": sandbox_hash_key}
        if verify_connect is not None:
            params["verifyConnect"] = verify_connect
        return await self._request("GET", "/SandboxAuthdGetInstanceByHashKey", params=params)

    async def request_backup(self, sandbox_hash_key: str) -> Dict[str, Any]:
        """
        Initiates a backup process for a specific sandbox.
        Corresponds to POST /SandboxBackup/request/{sandboxHashKey} in swagger.

        Args:
            sandbox_hash_key (str): The unique hash key identifying the sandbox to back up.

        Returns:
            Dict[str, Any]: Backup task initiation status. See #/components/schemas/BackupTaskStatus.
        """
        endpoint = f"/SandboxBackup/request/{sandbox_hash_key}"
        return await self._request("POST", endpoint)

    async def get_backup_result(self, result_id: str) -> Dict[str, Any]:
        """
        Retrieves the result of a specific backup task.
        Corresponds to GET /SandboxBackup/result/{result_id} in swagger.

        Args:
            result_id (str): The ID of the backup task.

        Returns:
            Dict[str, Any]: Backup task status and result (if completed).
                            See #/components/schemas/BackupResultResponse.
        """
        endpoint = f"/SandboxBackup/result/{result_id}"
        return await self._request("GET", endpoint)

    async def list_backups(self, sandbox_hash_key: str) -> Dict[str, Any]:
        """
        Retrieves a list of available backups for a specific sandbox.
        Corresponds to GET /SandboxBackup/{sandboxHashKey} in swagger.

        Args:
            sandbox_hash_key (str): The unique hash key identifying the sandbox.

        Returns:
            Dict[str, Any]: A list of backup files. See #/components/schemas/BackupListResponse.
                            Returns an empty list if no backups or sandbox not accessible.
        """
        endpoint = f"/SandboxBackup/{sandbox_hash_key}"
        return await self._request("GET", endpoint)

    async def get_backup_download_url(self, sandbox_hash_key: str, key: str) -> Dict[str, Any]:
        """
        Generates a pre-signed download URL for a specific backup file.
        Corresponds to POST /SandboxBackup/{sandboxHashKey} in swagger.

        Args:
            sandbox_hash_key (str): The unique hash key identifying the sandbox owning the backup.
            key (str): The S3 key of the backup file.

        Returns:
            Dict[str, Any]: Pre-signed download URL. See #/components/schemas/BackupDownloadUrlResponse.
        """
        endpoint = f"/SandboxBackup/{sandbox_hash_key}"
        json_data = {"key": key}
        return await self._request("POST", endpoint, json_data=json_data)

    async def upload_to_aura(self, sandbox_hash_key: str, aura_uri: str, aura_password: str, aura_username: Optional[str] = "neo4j") -> Dict[str, Any]:
        """
        Initiates an upload of a sandbox backup to an Aura instance.
        Corresponds to POST /SandboxAuraUpload/request/{sandboxHashKey} in swagger.

        Args:
            sandbox_hash_key (str): The unique hash key identifying the sandbox backup to upload.
            aura_uri (str): The Aura instance URI.
            aura_password (str): Password for the Aura instance.
            aura_username (Optional[str]): Username for the Aura instance (default: 'neo4j').

        Returns:
            Dict[str, Any]: Aura upload task initiation status. See #/components/schemas/AuraUploadTaskStatus.
        """
        endpoint = f"/SandboxAuraUpload/request/{sandbox_hash_key}"
        json_data = {
            "aura_uri": aura_uri,
            "aura_password": aura_password,
            "aura_username": aura_username
        }
        return await self._request("POST", endpoint, json_data=json_data)

    async def get_aura_upload_result(self, result_id: str) -> Dict[str, Any]:
        """
        Retrieves the result of a specific Aura upload task.
        Corresponds to GET /SandboxAuraUpload/result/{result_id} in swagger.

        Args:
            result_id (str): The ID of the Aura upload task.

        Returns:
            Dict[str, Any]: Aura upload task status and result (if completed).
                            See #/components/schemas/AuraUploadResultResponse.
        """
        endpoint = f"/SandboxAuraUpload/result/{result_id}"
        return await self._request("GET", endpoint)

    async def get_schema(self, hash_key: str) -> FastApiReadCypherQueryResponse:
        """
        Retrieves the schema of the Neo4j database.
        Corresponds to POST /SandboxQuery in swagger.
        """
        schema_query = (
            "call apoc.meta.data() yield label, property, type, other, unique, index, elementType "
            "where elementType = 'node' and not label starts with '_' "
            "with label, collect(case when type <> 'RELATIONSHIP' "
            "then [property, type + case when unique then ' unique' else '' end + "
            "case when index then ' indexed' else '' end] end) as attributes, "
            "collect(case when type = 'RELATIONSHIP' then [property, head(other)] end) as relationships "
            "return label, apoc.map.fromPairs(attributes) as attributes, "
            "apoc.map.fromPairs(relationships) as relationships"
        )
        return await self.read_query(hash_key, schema_query)

    async def read_query(self, hash_key: str, query: str, params: Optional[Dict[str, Any]] = None) -> FastApiReadCypherQueryResponse:
        """
        Executes a read query on the Neo4j database.
        Corresponds to POST /SandboxQuery in swagger.
        """
        return await self._request("POST", "/SandboxRunQuery", json_data={"hash_key": hash_key, "statement": query, "params": params, "accessMode": "Read"})

    async def write_query(self, hash_key: str, query: str, params: Optional[Dict[str, Any]] = None) -> FastApiReadCypherQueryResponse:
        """
        Executes a write query on the Neo4j database.
        Corresponds to POST /SandboxQuery in swagger.
        """
        return await self._request("POST", "/SandboxRunQuery", json_data={"hash_key": hash_key, "statement": query, "params": params})


def get_sandbox_client(user: Annotated[Dict[str, Any], Depends(verify_auth)]) -> SandboxApiClient:
    return SandboxApiClient(user["token"])


async def call_sandbox_api(api_method_name: str, client: SandboxApiClient, **kwargs):
    logger.info(f"Calling {api_method_name} with kwargs: {kwargs}")

    retries = 0
    last_exception = None
    method_to_call = getattr(client, api_method_name)

    while retries < MAX_RETRIES:
        try:
            result = await method_to_call(**kwargs)
            return result if result is not None else {}  # Ensure consistent empty dict for 204/202
        except SandboxApiClientError as e:
            last_exception = e
            # Check for rate limit or specific retryable errors (e.g., 503)
            # This is a simplified check; real rate limit headers (X-Rate-Limit-Reset) should be handled if available
            is_retryable = e.status_code == 429 or (e.status_code and 500 <= e.status_code < 600)
            if is_retryable:
                retries += 1
                if retries >= MAX_RETRIES:
                    logger.error(f"API call {api_method_name} failed after {MAX_RETRIES} retries. Last error: {e}")
                    raise HTTPException(status_code=e.status_code or 503, detail=str(e))

                wait_time = BASE_BACKOFF_DELAY * (2 ** (retries - 1)) + random.uniform(0, 0.5)
                logger.warning(f"API call {api_method_name} failed with {e.status_code}. Retrying in {wait_time:.2f}s. Attempt {retries}/{MAX_RETRIES}.")
                await asyncio.sleep(wait_time)
            else:
                # Non-retryable SandboxApiClientError
                logger.error(f"API call {api_method_name} failed with non-retryable error: {e}")
                raise HTTPException(status_code=e.status_code or 500, detail=str(e))
        except Exception as e:
            # Unexpected errors not from SandboxApiClientError
            logger.exception(f"Unexpected error calling Sandbox API method {api_method_name}: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected internal server error occurred.")

    # Should not be reached if MAX_RETRIES > 0 and an exception was always raised
    logger.info(f"Last exception: {last_exception}")
    if last_exception:
        raise HTTPException(status_code=last_exception.status_code or 500, detail=str(last_exception))

    logger.error("API call failed after exhausting retries.")
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="API call failed after exhausting retries.")
