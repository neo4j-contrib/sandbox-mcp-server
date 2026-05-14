"""Tests for auth.verify_auth and auth.fetch_jwks_public_key.

We mint our own RSA key pair so we can sign a JWT and feed the matching public key
to verify_auth — no network, no real Auth0.
"""
from __future__ import annotations

import json

import httpx
import jwt
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from jwt.algorithms import RSAAlgorithm

from sandbox_api_mcp_server.auth import fetch_jwks_public_key, verify_auth

from tests.conftest import AUTH0_AUDIENCE, AUTH0_DOMAIN, make_request


@pytest.fixture(scope="module")
def rsa_keypair():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_jwk = json.loads(RSAAlgorithm.to_jwk(private.public_key()))
    return {"private_pem": private_pem, "public_pem": public_pem, "public_jwk": public_jwk}


# ---------- verify_auth ----------

class TestVerifyAuthMissingOrBadHeader:
    async def test_no_authorization_header(self):
        req = make_request(headers={})
        with pytest.raises(HTTPException) as exc:
            await verify_auth(req)
        assert exc.value.status_code == 401

    async def test_non_bearer_authorization(self):
        req = make_request(headers={"authorization": "Basic abc"})
        with pytest.raises(HTTPException) as exc:
            await verify_auth(req)
        assert exc.value.status_code == 401


class TestVerifyAuthApiKey:
    async def test_api_key_returns_api_key_type(self):
        req = make_request(headers={"authorization": "Bearer ApiKey secret-token"})
        result = await verify_auth(req)
        assert result["type"] == "api_key"
        assert result["claims"] == {"sub": "api_key"}
        assert result["token"] == "ApiKey secret-token"


class TestVerifyAuthJwt:
    async def test_valid_rs256_jwt(self, rsa_keypair):
        token = jwt.encode(
            {"sub": "alice", "aud": AUTH0_AUDIENCE, "iss": f"https://{AUTH0_DOMAIN}/"},
            rsa_keypair["private_pem"],
            algorithm="RS256",
        )
        req = make_request(
            headers={"authorization": f"Bearer {token}"},
            jwks_public_key=rsa_keypair["public_pem"],
        )
        result = await verify_auth(req)
        assert result["type"] == "jwt"
        assert result["claims"]["sub"] == "alice"
        assert result["token"] == token

    async def test_wrong_audience_rejected(self, rsa_keypair):
        token = jwt.encode(
            {"sub": "alice", "aud": "https://OTHER.example.com", "iss": f"https://{AUTH0_DOMAIN}/"},
            rsa_keypair["private_pem"],
            algorithm="RS256",
        )
        req = make_request(
            headers={"authorization": f"Bearer {token}"},
            jwks_public_key=rsa_keypair["public_pem"],
        )
        with pytest.raises(HTTPException) as exc:
            await verify_auth(req)
        assert exc.value.status_code == 401

    async def test_wrong_signature_rejected(self, rsa_keypair):
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        other_pem = other_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
        token = jwt.encode(
            {"sub": "alice", "aud": AUTH0_AUDIENCE, "iss": f"https://{AUTH0_DOMAIN}/"},
            other_pem,
            algorithm="RS256",
        )
        req = make_request(
            headers={"authorization": f"Bearer {token}"},
            jwks_public_key=rsa_keypair["public_pem"],
        )
        with pytest.raises(HTTPException) as exc:
            await verify_auth(req)
        assert exc.value.status_code == 401


# ---------- fetch_jwks_public_key ----------

class TestFetchJwksPublicKey:
    async def test_returns_pem_from_first_jwk(self, rsa_keypair):
        url = "https://tenant.example.com/.well-known/jwks.json"
        with respx.mock() as r:
            r.get(url).mock(return_value=httpx.Response(200, json={"keys": [rsa_keypair["public_jwk"]]}))
            pem = await fetch_jwks_public_key(url)
        assert pem.startswith("-----BEGIN PUBLIC KEY-----")
        assert "-----END PUBLIC KEY-----" in pem
        # And the key is functionally identical to the one we minted.
        assert pem.strip() == rsa_keypair["public_pem"].strip()

    async def test_empty_keys_raises(self):
        url = "https://tenant.example.com/.well-known/jwks.json"
        with respx.mock() as r:
            r.get(url).mock(return_value=httpx.Response(200, json={"keys": []}))
            with pytest.raises(ValueError):
                await fetch_jwks_public_key(url)

    async def test_missing_keys_field_raises(self):
        url = "https://tenant.example.com/.well-known/jwks.json"
        with respx.mock() as r:
            r.get(url).mock(return_value=httpx.Response(200, json={}))
            with pytest.raises(ValueError):
                await fetch_jwks_public_key(url)

    async def test_http_error_propagates(self):
        url = "https://tenant.example.com/.well-known/jwks.json"
        with respx.mock() as r:
            r.get(url).mock(return_value=httpx.Response(500))
            with pytest.raises(httpx.HTTPStatusError):
                await fetch_jwks_public_key(url)
