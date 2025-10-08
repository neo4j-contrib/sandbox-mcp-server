"""
Auth0 authentication configuration for FastMCP.

This module documents the Auth0 authentication setup. The actual authentication
is handled at the FastAPI layer via the verify_auth dependency, which supports:
- OAuth2/JWT tokens from Auth0
- API Key authentication for backward compatibility

Future Enhancement:
    Implement OAuthAuthorizationServerProvider for native FastMCP OAuth support.
    This would provide DCR-compliant OAuth authentication directly in the MCP protocol.

    The provider would need to implement:
    - get_client() - Retrieve client information
    - register_client() - Handle dynamic client registration
    - authorize() - Handle OAuth authorization flow
    - exchange_code() - Exchange authorization code for tokens
    - refresh_token() - Refresh access tokens

    Reference: https://github.com/modelcontextprotocol/python-sdk/blob/main/src/mcp/server/auth/provider.py
"""

from ..models import Auth0Settings


def get_auth0_settings():
    """
    Get Auth0 settings for reference.

    Authentication is currently handled by FastAPI's verify_auth dependency.
    This function is provided for future OAuth provider implementation.

    Returns
    -------
    Auth0Settings
        Configured Auth0 settings
    """
    return Auth0Settings()

