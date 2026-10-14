"""A small, real MCP client for Hearth: Streamable HTTP, spec 2025-11-25.

Standard library only, so the skill's Lambda has nothing to install for it.
It does what any MCP client does: `initialize`, then `notifications/initialized`,
then `tools/call`, carrying the `Mcp-Session-Id` the server issued and the
`MCP-Protocol-Version` it negotiated. It also speaks to Hearth's UCP checkout
endpoints for the one step where the host, not the add-on, acts (payment).

Sessions are kept by the caller (the skill stores the id in the Alexa session
attributes) because a Lambda may be a different process on every turn. A
server that no longer knows the session answers 404, and the client opens a
fresh one and retries once, as the transport spec says a client should.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

PROTOCOL_VERSION = "2025-11-25"
CLIENT_INFO = {"name": "hearth-alexa-skill", "version": "0.1.0",
               "title": "Hearth classic Alexa skill bridge"}


class HearthError(Exception):
    pass


class Hearth:
    def __init__(self, base_url: str, token: str, session_id: str | None = None,
                 timeout: float = 6.0):
        self.base = base_url.rstrip("/")
        self.token = token
        self.session_id = session_id
        self.timeout = timeout
        self._id = 0
        self.calls = []                     # (method, ms) for the logs

    # --- transport --------------------------------------------------------
    def _request(self, method, path, body=None, headers=None):
        data = None if body is None else json.dumps(body).encode()
        h = {"Authorization": f"Bearer {self.token}",
             "Content-Type": "application/json",
             "Accept": "application/json, text/event-stream",
             **(headers or {})}
        req = urllib.request.Request(self.base + path, data=data, headers=h,
                                     method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read()
                return r.status, dict(r.headers), (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                payload = json.loads(raw) if raw else None
            except ValueError:
                payload = {"raw": raw[:200].decode("utf-8", "replace")}
            return e.code, dict(e.headers), payload
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise HearthError(f"Hearth is not reachable: {e}") from e

    def _rpc(self, method, params=None, notify=False):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        if not notify:
            self._id += 1
            msg["id"] = self._id
        headers = {"MCP-Protocol-Version": PROTOCOL_VERSION}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        return self._request("POST", "/mcp", msg, headers)

    # --- lifecycle --------------------------------------------------------
    def initialize(self):
        msg = {"jsonrpc": "2.0", "id": 0, "method": "initialize",
               "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                          "clientInfo": CLIENT_INFO}}
        status, headers, body = self._request("POST", "/mcp", msg)
        if status != 200 or not body or "result" not in body:
            raise HearthError(f"initialize failed: {status} {body}")
        sid = {k.lower(): v for k, v in headers.items()}.get("mcp-session-id")
        if not sid:
            raise HearthError("initialize returned no Mcp-Session-Id")
        self.session_id = sid
        self._rpc("notifications/initialized", notify=True)
        return body["result"]

    def ensure_session(self):
        if not self.session_id:
            self.initialize()

    def call_tool(self, name: str, arguments: dict) -> dict:
        """tools/call, returning the MCP result object. A stale session is
        reopened once; anything else that is not a result is an error."""
        self.ensure_session()
        for attempt in (1, 2):
            status, _, body = self._rpc("tools/call",
                                        {"name": name, "arguments": arguments})
            if status in (400, 404) and attempt == 1 and (
                    status == 404 or "Mcp-Session-Id" in json.dumps(body or {})):
                self.session_id = None
                self.initialize()
                continue
            if status == 401:
                raise HearthError("Hearth refused the skill's credential (401)")
            if status != 200 or not body:
                raise HearthError(f"tools/call {name} failed: {status} {body}")
            if "error" in body:
                raise HearthError(f"tools/call {name}: {body['error'].get('message')}")
            return body["result"]
        raise HearthError("could not open an MCP session")

    def plan(self, said: str, speaker: str, context: dict | None = None) -> dict:
        """Hearth's simulator planner (rules, or a configured model with the
        hearth-care Agent Skill), for utterances no intent matched."""
        status, _, body = self._request("POST", "/sim/plan",
                                        {"said": said, "speaker": speaker,
                                         "context": context or {}})
        if status != 200 or not body:
            raise HearthError(f"planner failed: {status}")
        return body

    # --- the host's part of checkout (UCP) ---------------------------------
    def checkout(self, hint: dict, buyer: str) -> dict:
        """Create and complete a checkout session from a reorder's hint.
        Sandbox merchant: nothing is charged."""
        ucp = {"UCP-Agent": 'profile="hearth-alexa-skill"'}
        status, _, s = self._request(
            "POST", "/checkout-sessions",
            {"line_items": hint["line_items"], "buyer": {"first_name": buyer},
             "context": {"language": "en-US", "address_country": "US",
                         "hearth_quote": hint.get("quote")}},
            {**ucp, "Idempotency-Key": f"create-{hint.get('quote')}"})
        if status not in (200, 201) or not s:
            raise HearthError(f"checkout create failed: {status}")
        if s.get("status") != "ready_for_complete":
            return s
        status, _, s2 = self._request(
            "POST", f"/checkout-sessions/{s['id']}/complete",
            {"payment": {"instruments": [{
                "handler_id": "amazon_pay_network_token", "type": "card",
                "credential": {"type": "network_token", "token": "sandbox-token"}}]}},
            {**ucp, "Idempotency-Key": f"complete-{s['id']}"})
        if status != 200 or not s2:
            raise HearthError(f"checkout complete failed: {status}")
        return s2


_REF = re.compile(r"\s*\[[0-9a-f]{6,}\]")


def spoken_text(result: dict) -> str:
    """The sentence Hearth returned, exactly, minus the belief references
    ("[9fa924226edd]") that are for a model to quote back, not for a person
    to hear. This is what the skill says; it never writes its own."""
    blocks = [c.get("text", "") for c in result.get("content", [])
              if c.get("type") == "text"]
    return _REF.sub("", " ".join(blocks)).strip()
