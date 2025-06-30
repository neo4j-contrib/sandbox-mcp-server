from typing import Annotated, Optional, Any
from pydantic import BaseModel, Field


USECASE_DESCRIPTION = (
    "The name of the use case for the sandbox, possible values are: "
    "blank-sandbox,bloom,citations,contact-tracing,cybersecurity,entity-resolution,fincen,"
    "fraud-detection,graph-data-science,graph-data-science-blank-sandbox,healthcare-analytics,"
    "icij-offshoreleaks,icij-paradise-papers,legis-graph,movies,network-management,"
    "openstreetmap,pole,recommendations,twitch,twitter-trolls,wwc2019,yelp,twitter-v2"
)


class StartSandboxBody(BaseModel):
    usecase: Annotated[str, Field(description=USECASE_DESCRIPTION)]


class StopSandboxBody(BaseModel):
    sandbox_hash_key: Annotated[str, Field(description="The unique hash key identifying the sandbox.")]


class ExtendSandboxBody(BaseModel):
    sandbox_hash_key: Annotated[Optional[str], Field(description="Specific sandbox to extend. If None, all user's sandboxes are extended.")] = None


class AuraUploadBody(BaseModel):
    sandbox_hash_key: Annotated[str, Field(description="The unique hash key identifying the sandbox backup to upload.")]
    aura_uri: Annotated[str, Field(description="The Aura instance URI (e.g., neo4j+s://xxxx.databases.neo4j.io).")]
    aura_password: Annotated[str, Field(description="Password for the Aura instance.")]
    aura_username: Annotated[Optional[str], Field(description="Username for the Aura instance (defaults to 'neo4j').")] = "neo4j"


class BackupDownloadUrlBody(BaseModel):
    key: Annotated[str, Field(description="The S3 key of the backup file to download.")]


class FastApiCypherQueryBody(BaseModel):
    """
    Base request model for Cypher queries.
    """

    hash_key: str = Field(
        ...,
        description="The hash key of the sandbox to query.",
        json_schema_extra={"examples": ["abcdef1234567890"]},
    )
    params: Optional[dict[str, Any]] = Field(
        None,
        description="Optional parameters to pass to the Cypher query.",
        json_schema_extra={"examples": [{"name": "John"}]},
    )


class FastApiReadCypherQueryBody(FastApiCypherQueryBody):
    """
    Request model for Read Cypher queries.
    """

    query: str = Field(
        ...,
        description="The Read Cypher query to execute.",
        json_schema_extra={"examples": ["MATCH (n: Person {name: $name}) RETURN n.name as name, n.age as age"]},
    )


class FastApiWriteCypherQueryBody(FastApiCypherQueryBody):
    """
    Request model for Write Cypher queries.
    """

    query: str = Field(
        ...,
        description="The Write Cypher query to execute.",
        json_schema_extra={"examples": ["MERGE (n: Person {name: $name})"]},
    )


class FastApiReadCypherQueryResponse(BaseModel):
    """
    Response for a Read Cypher query.
    """

    data: list[dict[str, Any]] = Field(
        ...,
        description="The results of the Read Cypher query.",
        json_schema_extra={"examples": [{"name": "John", "age": 30}]},
    )
    count: int = Field(
        ..., description="The number of rows returned by the query.", json_schema_extra={"examples": [1]}
    )
