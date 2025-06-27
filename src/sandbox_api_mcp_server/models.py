from pydantic import Field
from pydantic_settings import BaseSettings


class Auth0Settings(BaseSettings):
    """
    For this to work, you need an .env file in the root of the project with the following variables:
    AUTH0_DOMAIN=your-tenant.auth0.com
    AUTH0_AUDIENCE=https://your-tenant.auth0.com/api/v2/
    AUTH0_CLIENT_ID=your-client-id
    AUTH0_CLIENT_SECRET=your-client-secret
    """

    auth0_domain: str = Field(default="", validation_alias="AUTH0_DOMAIN")
    auth0_audience: str = Field(
        default="", validation_alias="AUTH0_AUDIENCE"
    )
    auth0_client_id: str = Field(default="", validation_alias="AUTH0_CLIENT_ID")
    auth0_client_secret: str = Field(default="none", validation_alias="AUTH0_CLIENT_SECRET")

    @property
    def auth0_jwks_url(self):
        return f"https://{self.auth0_domain}/.well-known/jwks.json"

    @property
    def auth0_oauth_metadata_url(self):
        return f"https://{self.auth0_domain}/.well-known/openid-configuration"
