# Engineering notes

The README is the product. This file is the notebook behind it: measurements,
the bugs that shaped the design, and the operational details a reviewer with
the repo open will want. Nothing here is needed to understand what Hearth does.

See also: [the record and the honest ledger](#the-record), the
[friction log](FRICTION_LOG.md), and the [submission copy](SUBMISSION.md).

## The record

Until October the action ledger held only what the agent reported through the
`did` tool. Hearth did not act; the agent did, and then described itself. A
model that skipped the call left no trace.

Now the server writes the record itself. `HearthMCP.handle` wraps every
`tools/call` and, before the response leaves, appends one entry to
`hearth/trace.py`: the tool, its arguments, the outcome (`ok`, `refused`,
`error`), the belief ids the resolver actually weighed (collected inside
`Household.resolve`, not claimed by the tool), the ids written (beliefs whose
status changed, new doses, rides, board posts, checkouts), the ledger action if
one was taken, the MCP session, and the time it took. Entries are SHA-256
chained (`prev` + canonical JSON), so editing or deleting one breaks
`Trace.verify()` at that entry. Checkout calls, which are REST rather than MCP,
and console actions go on the same record.

Two consequences:

- Actions Hearth takes itself (logging or refusing a dose, each step of an
  `arrange`, opening and completing a checkout) are written by the code that
  takes them, bound to the resolution that decided them.
- Actions the agent reports through `did` are filed as `reported`, and Hearth
  checks its own record for a `whats_true` on the same setting in the same MCP
  session within ten minutes. If there was none, "why did you do that?" says
  so: *"That action was reported to me afterwards; I was not asked before it
  was taken."*

What the chain does not prove: that the operator of the server did not rewrite
the whole file and recompute every hash. Anchoring the head hash somewhere the
operator cannot write (a signed daily digest sent to the family) is the obvious
next step and is not built.

## Live

https://hearth-sh3u.onrender.com — console at `/console`, MCP at `/mcp`.

`python3 tests/test_live.py https://hearth-sh3u.onrender.com` runs the whole
conformance suite against the deployment, including a real OAuth 2.1 PKCE
exchange over the wire.

### Latency, measured rather than claimed

Amazon requires "a round-trip query response latency of less than 500 ms."

| measured from | p50 | worst |
|---|---|---|
| the server's own `Server-Timing` header | 0.04ms | 0.05ms |
| a datacentre in Helsinki | 201ms | 211ms |
| a home connection in Lagos | 329ms | 680ms |

The server's contribution is four hundredths of a millisecond. Everything else
is distance. It passes comfortably from a datacentre and fails from the author's
home, and the second number is the irrelevant one, because Alexa+ calls from AWS
and not from Lagos.

Two earlier versions of this measurement were wrong and are worth recording. The
first ran in-process and reported 0.8ms, which proved nothing about a network
requirement. The second opened a fresh TCP and TLS connection per request, which
from a distant client is two full round trips of pure handshake before the
server sees anything, and reported 618ms. A real MCP client holds the connection
open, which is what Streamable HTTP is for.

### Cold start

The deployment is on a free instance, which sleeps after 15 minutes idle. First
byte after a sleep was 641ms, over the requirement, and that is exactly what a
judge opening the link after a quiet night would hit. The fix is the Starter
plan, which does not sleep. Until then `.github/workflows/keep-warm.yml` pings
it, which is a mitigation and not a fix.

### Multi-tenancy

Every authenticated subject gets its own household. A single shared house was
fine while the only client was a test and wrong the moment the service was
reachable: two people opening the demo wrote into the same home, and the live
deployment had already collected other people's thermostats before anyone
noticed. In a real add-on the subject arrives from account linking, and the same
leak would be between actual families.

### The listing

`addon.json` is written and validated. Six icon sizes and the carousel image are
generated from SVG in `assets/src/` and served by the service itself, so the
listing depends on no second host that could be down or parked during judging.
`/privacy` and `/terms` are served from here too. Every limit Amazon imposes is
pinned by `tests/test_manifest.py`, because each one is a silent rejection
rather than a build error.

### Before the add-on is registered, read this

`HEARTH_REDIRECT_URIS` is an allowlist, and on the deployment it currently holds
one entry: the console. That closes the open redirector, and it also means
**any client whose callback is not on the list is refused**, which will include
Alexa+ itself.

When the add-on is registered and Amazon's callback URL is known, it has to be
added to that variable and the service redeployed. Setting an environment
variable through Render's API does **not** restart the process, so the value is
read at the next deploy and not before; that cost an hour of a live service
still handing codes to a hostile redirect after the fix was supposedly applied.

Leaving the variable unset falls back to a shape check only (https, or
loopback), which accepts any https URI. That is weaker, though PKCE means an
attacker who captures a code cannot exchange it without the verifier. The
allowlist is the right default and the one entry is the thing to remember.

### Still to do (as of the original submission)

Only `alexa-ai deploy` and the demo video, both of which need an Amazon
developer account. The model write path also still wants a real key; it is
exercised against a protocol stub in `tests/test_extract.py`, which proves the
code handles a model correctly but not that a model writes good beliefs.

