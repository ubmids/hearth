# Hearth spec

## Spike result: Alexa+ self-hosted MCP is green, no device needed

Confirmed against the Alexa+ MCP Toolkit quickstart. Testable in the web simulator, and no
allowlist is documented.

### Hard requirements

- **Transport:** Streamable HTTP, MCP spec 2025-11-25. Standalone HTTP+SSE is deprecated.
- **Latency budget: 500ms round trip.** This is a design constraint, not a footnote. Memory
  resolution has to be fast, so ranking and conflict resolution run in-process against a
  warm store. No model call on the hot path.
- **Auth: OAuth 2.1 with PKCE (S256).**
  - `401 Unauthorized` without a `WWW-Authenticate` header for unauthenticated requests
  - Protected Resource Metadata at `/.well-known/oauth-authorization-server`
  - `S256` present in `code_challenge_methods_supported`
  - accept the `resource` parameter on authorize and token requests
  - PKCE `code_verifier` on token requests, Bearer token in `Authorization`
  - not supported yet: Dynamic Client Registration, OpenID Connect, Step-Up Auth
- **Registration:** `alexa-ai new mcp --name ... --mcp-server-url ...`, then `alexa-ai deploy`.
  `addon.json` needs descriptions, six icon sizes, privacy and terms URLs.
- Local development is exposed with a cloudflared tunnel.

The OAuth surface is where most of the field will cut corners. Doing it properly is a cheap
Tech Implementation win.

## Reuse from Cortex

Cortex already ships, tested: `mcp_server.py`, `supersede(reason=...)`, per-access audit trail
with provenance, exportable audit report, salience-scaled decay. Hearth forks that spine.

## New work for this event

- **Household model.** Members, authority, scope. A belief belongs to a person, not a house.
- **Contest resolution.** Conflicting beliefs resolved by authority and recency, with the
  resolution explained rather than silently applied.
- **Expiry.** Beliefs that were true in a context that has passed ("during the cold snap").
- **Action ledger.** Every autonomous action recorded against the memories that justified it,
  queryable as "why did you do that?".

## Demo script (20 seconds)

Assistant does something reasonable and wrong. Ask why. It names the belief, who said it and
when. Retire that belief out loud. Ask again. Behaviour is now correct.

## Amazon mini-challenge pairing
Open Source. New public repo, MIT, all commits inside the window.
