import httpx
import json
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives import serialization
from .helpers import get_logger
from jwt.algorithms import RSAAlgorithm
from fastapi import Request, HTTPException, status
from typing import Any
from .models import Auth0Settings

logger = get_logger(__name__)


async def verify_auth(request: Request) -> dict[str, Any]:
    """
    Verify the authentication token from the request headers.

    Parameters
    ----------
    request: Request
        The incoming request object

    Returns
    -------
    dict[str, Any]
        The decoded JWT payload and the token

        {
            "claims": dict[str, Any],
            "token": str
        }
    """

    try:
        import jwt

        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header")

        token = " ".join(auth_header.split(" ")[1:])
        if token.startswith("ApiKey "):
            return {"claims": {"sub": "api_key"}, "token": token, "type": "api_key"}

        header = jwt.get_unverified_header(token)

        # Check if this is a JWE token (encrypted token)
        if header.get("alg") == "dir" and header.get("enc") == "A256GCM":
            raise ValueError(
                "Token is encrypted, offline validation not possible. "
                "This is usually due to not specifying the audience when requesting the token."
            )

        # Otherwise, it's a JWT, we can validate it offline
        if header.get("alg") in ["RS256", "HS256"]:
            claims = jwt.decode(
                token,
                request.app.state.jwks_public_key,
                algorithms=["RS256", "HS256"],
                audience=Auth0Settings().auth0_audience,
                issuer=f"https://{Auth0Settings().auth0_domain}/",
                options={"verify_signature": True},
            )
            logger.info(f"Verified auth: {claims}")
            return {"claims": claims, "token": token, "type": "jwt"}

    except Exception as e:
        logger.error(f"Auth error: {str(e)}")

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


async def fetch_jwks_public_key(url: str) -> str:
    """
    Fetch JWKS from a given URL and extract the primary public key in PEM format.

    Parameters
    ----------
    url: str
        The JWKS URL to fetch from

    Returns
    -------
    str
        PEM-formatted public key as a string
    """
    logger.info(f"Fetching JWKS from: {url}")
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()
        jwks_data = response.json()

        if not jwks_data or "keys" not in jwks_data or not jwks_data["keys"]:
            logger.error("Invalid JWKS data format: missing or empty 'keys' array")
            raise ValueError("Invalid JWKS data format: missing or empty 'keys' array")

        # Just use the first key in the set
        jwk = json.dumps(jwks_data["keys"][0])

        # Convert JWK to PEM format
        public_key = RSAAlgorithm.from_jwk(jwk)
        if isinstance(public_key, RSAPublicKey):
            pem = public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            pem_str = pem.decode("utf-8")
            logger.info("Successfully extracted public key from JWKS")
            return pem_str
        else:
            logger.error("Invalid JWKS data format: expected RSA public key")
            raise ValueError("Invalid JWKS data format: expected RSA public key")
