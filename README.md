# Hearth

**The household memory Alexa+ can be trusted with.**

Alexa+ is agentic now. It takes actions instead of answering questions, and that flips
the failure mode: a wrong answer is annoying, a wrong action is a breach of trust.

A home is the hardest place to get this right, because household state is *contested*.
Several people, competing preferences, different authority, and facts that quietly expire.
Dad set the thermostat rule. The kid overrode it. Someone is ill this week. You switched
coffee brands in March. A stateless assistant re-derives all of it from nothing every turn,
and when it gets it wrong you have no way to find out why.

Hearth is a self-hosted MCP server that gives an agent a household memory with the three
things ordinary memory stores do not have.

- **Provenance** — every belief records who said it, when, and in what context. Not
  "thermostat at 19" but "Dad, three weeks ago, during the cold snap."
- **Supersession** — beliefs are retired, not overwritten. You can ask what the assistant
  used to think and when it changed its mind.
- **Contest resolution** — when two people hold conflicting beliefs, Hearth resolves by
  authority and recency and then *explains the resolution*, instead of silently picking one.

On top sits the **action ledger**: every autonomous action is recorded against the specific
memories that justified it. Ask "why did you do that?" and get a real chain. Retire one
belief and the behaviour changes.

## Run it

```bash
pip install -r requirements.txt
python3 demo.py                      # the twenty-second story, no key, no network
python3 tests/test_contest.py        # 6 household situations an ordinary store gets wrong
python3 tests/test_conformance.py    # 12 Alexa+ conformance requirements
uvicorn hearth.app:app --port 8000   # the MCP server
```

To reach it from Alexa+, expose it and register the add-on:

```bash
cloudflared tunnel --url http://localhost:8000
alexa-ai new mcp --name "Hearth" --mcp-server-url https://<tunnel>/mcp
```

Everything runs with no API key. The extraction write path uses a deterministic
rule extractor when no model is configured, and that is what CI runs.

## Status

Core, transport and auth are done and tested. 18 tests green.

- Beliefs with provenance, scope, context and expiry
- Contest resolution by scope, then authority, then recency, each with a spoken reason
- Action ledger answering "why did you do that?"
- MCP 2025-11-25 over Streamable HTTP, hand-rolled, 7 tools
- OAuth 2.1 authorization code flow with PKCE S256, both well-known documents
- Read path measured at 0.8ms against the 500ms Alexa+ round-trip budget

Three conformance details Alexa+ requires that a general-purpose MCP SDK gets
wrong by default, each asserted in `tests/test_conformance.py`:

1. the `401` must carry **no** `WWW-Authenticate` header, against RFC 9728 convention
2. **both** well-known documents are required, not only the RFC 9728 one
3. a bearer token arriving in the query string must be refused, not accepted

Still to do: detecting context-ending utterances ("the cold snap is over") on the
extraction path rather than calling `end_context` directly, the add-on manifest
and icons, and a deployment.

## Built for
Build, Ship, Shape: Amazon Developer Hackathon 2026, Alexa+ track. Deadline 23 Oct 2026.
Derived in part from Cortex, an earlier MCP memory server by the same author; the household
provenance, authority and action-ledger layers are new work for this event.

## Licence
MIT
