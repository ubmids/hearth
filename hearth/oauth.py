"""OAuth 2.1 with PKCE, to the letter of what Alexa+ asks for.

This is the part of the submission most of the field will skip or fake, which is
why it is worth doing properly. Three requirements here are easy to get wrong:

  1. The 401 carries NO `WWW-Authenticate` header. That is the opposite of the
     RFC 9728 convention every other MCP host follows, and it is stated
     explicitly in the Alexa+ toolkit docs. Following the RFC here fails Amazon.
  2. TWO well-known documents are required, not one: the RFC 9728 Protected
     Resource Metadata at /.well-known/oauth-protected-resource AND the
     authorization server metadata at /.well-known/oauth-authorization-server.
  3. `code_challenge_methods_supported` must be present and must include S256.
     Absent is a failure, not a default.

Dynamic Client Registration, OpenID Connect and Step-Up Authorization are all
unsupported by Alexa+ today, so the client is pre-registered from config.
"""
import base64
import hashlib
import os
import secrets
import time
from dataclasses import dataclass, field
from urllib.parse import urlencode

AUTH_CODE_TTL = 60            # seconds; codes are single-use and short-lived
TOKEN_TTL = 3600


def s256(verifier: str) -> str:
    """The S256 transform: BASE64URL(SHA256(ASCII(verifier))), no padding."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


@dataclass
class PendingAuth:
    code: str
    client_id: str
    redirect_uri: str
    code_challenge: str
    resource: str
    scope: str
    subject: str
    issued_at: float = field(default_factory=time.time)

    def expired(self, now=None) -> bool:
        return (now or time.time()) - self.issued_at > AUTH_CODE_TTL


@dataclass
class Token:
    value: str
    subject: str
    resource: str
    scope: str
    issued_at: float = field(default_factory=time.time)

    def expired(self, now=None) -> bool:
        return (now or time.time()) - self.issued_at > TOKEN_TTL


class AuthServer:
    def __init__(self, issuer: str, resource: str,
                 client_id: str | None = None,
                 redirect_uris: list[str] | None = None,
                 scopes: list[str] | None = None):
        self.issuer = issuer.rstrip("/")
        self.resource = resource.rstrip("/")
        self.client_id = client_id or os.getenv("HEARTH_CLIENT_ID", "hearth-dev-client")
        self.redirect_uris = redirect_uris or []
        self.scopes = scopes or ["household.read", "household.write"]
        self._pending: dict[str, PendingAuth] = {}
        self._tokens: dict[str, Token] = {}

    # --- metadata documents ------------------------------------------------
    def protected_resource_metadata(self) -> dict:
        """RFC 9728. Tells the client which authorization server guards us."""
        return {
            "resource": self.resource,
            "authorization_servers": [self.issuer],
            "scopes_supported": self.scopes,
            "bearer_methods_supported": ["header"],   # never the query string
        }

    def authorization_server_metadata(self) -> dict:
        return {
            "issuer": self.issuer,
            "authorization_endpoint": f"{self.issuer}/authorize",
            "token_endpoint": f"{self.issuer}/token",
            "scopes_supported": self.scopes,
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code"],
            "token_endpoint_auth_methods_supported": ["none"],  # public client + PKCE
            "code_challenge_methods_supported": ["S256"],       # required, must include S256
            # Dynamic Client Registration is not supported by Alexa+, so the
            # client id has to come from somewhere. Publishing it here lets a
            # client discover it instead of it being hardcoded in three places.
            "client_id_hint": self.client_id,
        }

    # --- authorization code flow ------------------------------------------
    def authorize(self, *, client_id, redirect_uri, code_challenge,
                  code_challenge_method, resource, scope="", state="",
                  subject="household") -> tuple[str, dict]:
        """Returns (redirect_url, error_dict). Exactly one is meaningful."""
        if client_id != self.client_id:
            return "", {"error": "invalid_client"}
        if code_challenge_method != "S256":
            # OAuth 2.1 removes `plain`. Accepting it would be a downgrade.
            return "", {"error": "invalid_request",
                        "error_description": "code_challenge_method must be S256"}
        if not code_challenge:
            return "", {"error": "invalid_request",
                        "error_description": "code_challenge required"}
        if resource.rstrip("/") != self.resource:
            # RFC 8707. Binding the code to the resource is what stops a token
            # minted for one MCP server being replayed against another.
            return "", {"error": "invalid_target",
                        "error_description": "resource must be the canonical MCP URI"}
        if self.redirect_uris and redirect_uri not in self.redirect_uris:
            return "", {"error": "invalid_request",
                        "error_description": "redirect_uri not registered"}

        code = secrets.token_urlsafe(32)
        self._pending[code] = PendingAuth(
            code=code, client_id=client_id, redirect_uri=redirect_uri,
            code_challenge=code_challenge, resource=resource.rstrip("/"),
            scope=scope, subject=subject)
        params = {"code": code}
        if state:
            params["state"] = state
        sep = "&" if "?" in redirect_uri else "?"
        return f"{redirect_uri}{sep}{urlencode(params)}", {}

    def exchange(self, *, grant_type, code, code_verifier, client_id,
                 redirect_uri="", resource="") -> tuple[dict, dict]:
        """Returns (token_response, error). Exactly one is meaningful."""
        if grant_type != "authorization_code":
            return {}, {"error": "unsupported_grant_type"}
        pending = self._pending.pop(code, None)       # single use, pop not get
        if pending is None:
            return {}, {"error": "invalid_grant", "error_description": "unknown or used code"}
        if pending.expired():
            return {}, {"error": "invalid_grant", "error_description": "code expired"}
        if pending.client_id != client_id:
            return {}, {"error": "invalid_client"}
        if redirect_uri and redirect_uri != pending.redirect_uri:
            return {}, {"error": "invalid_grant", "error_description": "redirect_uri mismatch"}
        if not code_verifier:
            return {}, {"error": "invalid_request", "error_description": "code_verifier required"}
        if not secrets.compare_digest(s256(code_verifier), pending.code_challenge):
            return {}, {"error": "invalid_grant", "error_description": "PKCE verification failed"}
        if resource and resource.rstrip("/") != pending.resource:
            return {}, {"error": "invalid_target"}

        tok = Token(value=secrets.token_urlsafe(32), subject=pending.subject,
                    resource=pending.resource, scope=pending.scope)
        self._tokens[tok.value] = tok
        return {"access_token": tok.value, "token_type": "Bearer",
                "expires_in": TOKEN_TTL, "scope": tok.scope}, {}

    # --- resource-side verification ---------------------------------------
    def verify(self, authorization_header: str | None) -> Token | None:
        if not authorization_header:
            return None
        parts = authorization_header.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None
        tok = self._tokens.get(parts[1].strip())
        if tok is None or tok.expired():
            return None
        return tok

    def issue_for_testing(self, subject="household", scope="") -> str:
        """Mint a token directly. Tests and the local demo only; never routed."""
        tok = Token(value=secrets.token_urlsafe(32), subject=subject,
                    resource=self.resource, scope=scope)
        self._tokens[tok.value] = tok
        return tok.value
