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

## Status
Scaffold. See `docs/SPEC.md`.

## Built for
Build, Ship, Shape: Amazon Developer Hackathon 2026, Alexa+ track. Deadline 23 Oct 2026.
Derived in part from Cortex, an earlier MCP memory server by the same author; the household
provenance, authority and action-ledger layers are new work for this event.

## Licence
MIT
