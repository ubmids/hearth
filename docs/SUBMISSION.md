# Submission copy, Hearth — Amazon Developer Hackathon, Alexa+ track

Deadline **Friday 23 October 2026, 12:00 PDT**. Devpost: amazonappdev2026.

Judging is Stage One pass/fail viability, then four equally weighted criteria at
25% each: Tech Implementation, Design, Potential Impact, Quality of the Idea.
Up to 10% bonus for a friction log, which `docs/FRICTION_LOG.md` already is.

**Stage One gate, confirmed met:** the track requires "a working Agent Skill or
a self-hosted MCP server, implementing MCP spec version 2025-11-25 over
Streamable HTTP". Hearth is exactly that, hand-rolled, with 61 conformance
tests asserting the version on the handshake and on the `mcp-protocol-version`
response header. The rules do not require a deployed or published app, so the
Amazon developer account is not on the critical path for this submission.

---

## Elevator pitch (200 characters)

Alexa+ takes actions now, so a wrong answer became a wrong action. Hearth gives
it a household memory with provenance, supersession and contest resolution, and
an action ledger that answers "why did you do that?"

## Text description

Alexa+ is agentic now. It takes actions instead of answering questions, and
that flips the failure mode: a wrong answer is annoying, a wrong action is a
breach of trust.

A home is the hardest place to get this right, because household state is
*contested*. Several people, competing preferences, different authority, and
facts that quietly expire. Dad set the thermostat rule. The kid overrode it.
Someone is ill this week. You switched coffee brands in March. A stateless
assistant re-derives all of it from nothing every turn, and when it gets it
wrong you have no way to find out why.

Hearth is a self-hosted MCP server that gives an agent a household memory with
the three things ordinary memory stores do not have.

**Provenance.** Every belief records who said it, when, and in what context. Not
"thermostat at 19" but "Dad, three weeks ago, during the cold snap".

**Supersession.** Beliefs are retired, never overwritten. You can ask what the
assistant used to think and when it changed its mind.

**Contest resolution.** When two people hold conflicting beliefs, Hearth
resolves by scope, then authority, then recency, and then *explains the
resolution* in a spoken sentence instead of silently picking one.

On top sits the **action ledger**: every autonomous action is recorded against
the specific memories that justified it. Ask "why did you do that?" and get a
real chain rather than a plausible reconstruction. Retire one belief and the
behaviour changes, demonstrably.

One design decision is worth calling out because it is the difference between a
demo and a product. There is a single server-side phrasing layer, so nothing a
human ever reads or hears names a domain or a slot. `thermostat.target = 19`
comes back as "The thermostat is set to 19 degrees". `meals.dinner = 17:00` is
"Dinner is at five". A domain the household invented this morning, that the
server has never seen before, still gets a sentence. An agent that leaks
`thermostat.target` into a spoken reply has broken the illusion that it lives
in your house, and no amount of prompt engineering downstream can put that
back.

## What is built

- Beliefs with provenance, scope, context and expiry
- Contest resolution by scope, then authority, then recency, each with a spoken
  reason
- Action ledger answering "why did you do that?"
- One server-side phrasing layer covering domains it has never seen
- MCP 2025-11-25 over Streamable HTTP, hand-rolled, 7 tools
- OAuth 2.1 authorization code flow with PKCE S256, both well-known documents
- `Server-Timing` on every MCP response, so the server's own cost is checkable
  by anyone from anywhere rather than asserted by me
- 127 tests, of which 61 are Alexa+ conformance

Three conformance details Alexa+ requires that a general-purpose MCP SDK gets
wrong by default, each asserted in `tests/test_conformance.py`:

1. the `401` must carry **no** `WWW-Authenticate` header, against the RFC 9728
   convention every SDK follows
2. **both** well-known documents are required, not only the RFC 9728 one
3. a bearer token arriving in the query string must be refused, not accepted

The suite was then mutation tested with a sibling tool from the same sprint,
which is a different question from coverage: not which lines ran, but whether
anything would have noticed if they were wrong. It took the phrasing layer from
68% to 96% and surfaced seven real holes, two of them genuine source defects.
The best of them is the kind no coverage tool reports: a test named
`test_the_reason_given_is_the_one_that_settled_it` passed with the wrong loser
selected, because both losers in its fixture happened to be beaten by the same
rule. Without that fix the console can print "This one is about Ada" under an
answer actually settled on authority, which is the exact failure this product
exists to prevent.

Live at https://hearth-sh3u.onrender.com, console at `/console`, MCP at `/mcp`.

---

## Product Feedback (REQUIRED FIELD)

> The rules require this and most entrants will write two sentences. It is also
> the field that feeds the friction log bonus, so it is worth the space. Every
> claim below is drawn from `docs/FRICTION_LOG.md`, which has the full
> reproduction steps, severity ratings and suggested fixes for each.

### Which developer tools, APIs and SDKs did you use, and for what?

- **MCP spec 2025-11-25 over Streamable HTTP**, hand-rolled rather than taken
  from an SDK. This was not preference. Three of the Alexa+ conformance
  requirements are things a general-purpose MCP SDK gets wrong by default, and
  the most important of them is a header the SDK is *correct* to send under RFC
  9728 and that Alexa+ requires you to omit. Owning the transport was the only
  way to satisfy both.
- **OAuth 2.1 authorization code flow with PKCE S256**, hand-rolled for the
  same reason, plus both well-known discovery documents.
- **FastAPI and uvicorn** for the HTTP surface, **Render** for hosting.
- **`alexa-ai` CLI** for add-on registration, and **cloudflared** to expose a
  local server during development.

### What worked well

Setup was genuinely quick. The Streamable HTTP transport choice is the right
one and the deprecation of standalone HTTP+SSE is stated clearly. Naming the
spec version explicitly in the documentation, `2025-11-25` rather than "the
latest", removed a whole class of ambiguity and I wish more platforms did it.
The conformance requirements, once found, are precise enough to write tests
against, which is why there are 61 of them.

### What needs improvement

Six issues, in `docs/FRICTION_LOG.md` with full detail. The two that cost most:

1. **The `401` must omit `WWW-Authenticate`, which inverts the spec every MCP
   SDK follows.** Severity high, because it is silent and it breaks the
   integration outright rather than degrading it. An SDK that does the RFC 9728
   correct thing produces a server Alexa+ will not talk to, and nothing in the
   error surface points at the header.
2. **The 500ms latency requirement does not say where it is measured from.**
   Severity high, and it disproportionately affects developers outside the
   United States. Measured from Lagos, a warm round trip to a US region is 357ms
   at p50 before the server does any work at all, while the server's own
   `Server-Timing` reports 0.05ms. If the budget is client-observed, the
   requirement is partly a geography test. If it is server-side, saying so would
   cost one sentence and save a lot of misdirected optimisation.

Also: two well-known documents are required and only one path is given
literally; `resource` and client registration are underspecified for a
self-hosted server; the Ring track is presented as open but is gated behind
partner approval, which is a planning cost paid before any code is written; and
the Bee track's device requirement contradicts the general device rule.

### How was the onboarding experience?

Good on transport, thin on conformance. Everything needed to stand up an MCP
server is easy to find. Everything needed to stand up an MCP server *that
Alexa+ will actually accept* had to be assembled from spec documents,
observation and inference. The gap between those two is where all six friction
log entries live. A single "conformance checklist" page listing the handful of
places Alexa+ deliberately departs from general MCP practice would have saved
most of a week and would cost Amazon an afternoon to write.

### Would you build with these tools again? **Yes.**

The protocol choice is sound and the agentic surface is the genuinely
interesting one to build against. The reservations are documentation
reservations, not architectural ones, and documentation is the cheapest thing
on this list to fix. The thing that would most change the experience for the
next developer is publishing the departures from stock MCP as a checklist
rather than leaving each one to be discovered by a failed integration.

---

## Feature requests (optional field, priority in brackets)

1. **[High] A conformance checklist page** listing every point where Alexa+
   departs from general MCP practice, with the `WWW-Authenticate` omission
   first. This single page would have prevented four of my six friction
   entries.
2. **[High] State where the 500ms budget is measured.** One sentence. Right now
   a developer outside the US cannot tell whether they are failing a
   requirement or failing a speed-of-light test.
3. **[Medium] Give both well-known document paths literally**, rather than one
   path and one description.
4. **[Medium] A conformance test harness**, even a curl script, that a
   self-hosted server can be pointed at before registration. I wrote 61 tests
   to answer questions the platform could answer itself.
5. **[Low] Mark gated tracks as gated on the track list.** The Ring track reads
   as open until you try to register.

---

## Demo video script

Under 3 minutes, YouTube or Vimeo, public. Must show the project functioning
for the device it was built for. The rules explicitly allow "a simulated
Alexa+ experience built using any AI or agentic tool of your choice", so drive
the live MCP server with an MCP client standing in for Alexa+ rather than
waiting on Alexa+ access.

**0:00 to 0:20, the stake.** On screen: the console. Say: "Alexa+ takes actions
now. That means a wrong answer just became a wrong action, and the hardest
place in the world to get that right is a house, because a house does not have
one opinion. It has four people and a history."

**0:20 to 0:55, contest resolution.** Show Dad setting a thermostat rule, then
the kid overriding it. Ask the house what the thermostat should be. It answers
*and explains which belief won and why*. Say: "Not a silent pick. A resolution,
with a reason, in a sentence you would actually say out loud."

**0:55 to 1:30, the action ledger.** The assistant takes an autonomous action.
Ask "why did you do that?". Show the real chain back to the specific memories.
Then **retire one belief and watch the behaviour change**. Say: "This is the
part that cannot be faked with a prompt. The action is linked to the memories
that justified it, so removing one changes what happens next."

**1:30 to 2:00, supersession.** Ask what the house used to think, and when it
changed its mind. Say: "Beliefs are retired, never overwritten. A house that
cannot tell you what it used to believe cannot be audited."

**2:00 to 2:30, the phrasing layer.** Invent a brand new domain live, something
the server has never seen. Show it still coming back as an English sentence,
never as `domain.slot`. Say: "One phrasing layer, server side. Nothing anybody
hears ever names a slot, including for a domain this house invented ten seconds
ago."

**2:30 to 2:50, conformance and honesty.** Show `tests/test_conformance.py`
running, 61 green. Say: "Alexa+ departs from stock MCP in three places that an
SDK gets wrong by default, including a 401 that must omit a header the spec
tells you to send. All three are asserted here. And the server stamps its own
timing on every response, so you do not have to take my word for what it
costs."

**Close.** Back to the console.

### Shot list

1. Console, cold.
2. Two conflicting beliefs, then the resolution with its spoken reason.
3. An action, then "why did you do that?", then retiring a belief.
4. The supersession history.
5. A new domain invented live, phrased in English.
6. `tests/test_conformance.py` running green, and a `Server-Timing` header.

---

## Before submitting, the checklist

- [ ] Demo video under 3 minutes, on YouTube or Vimeo, publicly visible
- [ ] Repository public with an open-source licence visible in the About
      section, or shared privately with testing@devpost.com
- [ ] Repository contains all source, assets and instructions to run it
- [ ] Product Feedback field filled in, above
- [ ] Friction log attached, `docs/FRICTION_LOG.md`, for the 10% bonus
- [ ] Feature requests submitted with priorities
- [ ] **Render cold start**: a judge hitting a sleeping free instance waits 80
      seconds. $7 for one month removes the single worst first impression in
      this submission. Do this before the video, not after.
- [ ] Secret sweep before flipping the repo public
- [ ] Submitted before 23 October, 12:00 PDT
