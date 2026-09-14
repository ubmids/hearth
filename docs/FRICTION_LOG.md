# Friction log: building a self-hosted MCP server for Alexa+

Recorded while building Hearth between 14 September and submission. Every entry
is something that actually cost time on this build, in the format the hackathon
rules ask for: task attempted, steps taken, expected versus actual, severity,
workaround, suggestion.

Entries are ordered by how much they would cost a developer who hits them cold.
Nothing here is hypothetical; each one is reproducible from this repository, and
the tests that pin the resolved behaviour are named where they exist.

---

## 1. The `401` must omit `WWW-Authenticate`, which inverts the spec every MCP SDK follows

**Severity: high.** Silent, and it breaks the integration rather than degrading it.

**Task attempted.** Return the correct unauthenticated response from a
self-hosted MCP server.

**Steps taken.** Read the Alexa+ MCP toolkit quickstart, then implemented the
`401` path the way RFC 9728 and the MCP authorization spec describe it, with a
`WWW-Authenticate` header pointing at the protected resource metadata.

**Expected.** That following RFC 9728 would be correct, since the same docs cite
RFC 9728 for the metadata document one paragraph earlier.

**Actual.** The quickstart requires the opposite: "Your MCP server returns
`401 Unauthorized` (without a `WWW-Authenticate` header) for unauthenticated
requests." A developer who reaches for an off-the-shelf MCP server library gets
the header added for them, correctly by the standard and wrongly for Alexa+,
with nothing to indicate a problem.

**Workaround.** Implemented the Streamable HTTP transport directly rather than
using an SDK, specifically so the response headers are under our control. Pinned
by `tests/test_conformance.py::test_401_has_no_www_authenticate`.

**Suggestion.** Two changes. State *why* the header is omitted, because a
requirement that contradicts the cited RFC reads like a documentation error and
invites developers to "fix" it. And add an explicit warning that common MCP
server libraries emit the header by default, with a note on how to suppress it
in the popular ones. This is the single most likely reason a correct-looking
server fails to connect.

---

## 2. The 500ms latency requirement does not say where it is measured from

**Severity: high**, and it disproportionately affects developers outside the US.

**Task attempted.** Verify the server meets "a round-trip query response latency
of less than 500 ms" before submitting.

**Steps taken.** Deployed to a host in Oregon and measured the full round trip
from the development machine in Lagos.

**Expected.** A pass or fail I could act on.

**Actual.** An ambiguous number. The application's own contribution is 0.04ms,
confirmed by a `Server-Timing` header. From Lagos the round trip is 329ms at p50
and 680ms at worst, which fails. From a datacentre in Helsinki the same
deployment is 201ms at p50 and 211ms at worst, which passes. Nothing about the
server changed between those two results; the only variable was the distance
from the client.

A developer in Lagos, Nairobi, Jakarta or São Paulo measuring their own server
will conclude they have failed a requirement they have comfortably met, and may
rearchitect or abandon a working design chasing latency that is not theirs.

**Workaround.** Measured from three vantage points and stamped every response
with `Server-Timing` so the application's share is separable from the network's.
Numbers and method are in the README.

**Suggestion.** State the measurement point explicitly, for example "measured
from Alexa+ service infrastructure in AWS us-east-1, not from your development
machine." Better still, publish a hosted probe that reports the round trip as
Alexa+ sees it, so a developer anywhere can check the number that actually
counts. This costs Amazon very little and removes a real disadvantage for
participants who are far from your infrastructure.

---

## 3. Two well-known documents are required, and only one path is given literally

**Severity: medium.** Costs a deploy cycle to discover.

**Task attempted.** Serve the metadata documents an Alexa+ client fetches.

**Steps taken.** The docs name `/.well-known/oauth-authorization-server`
literally, and describe the other as "a Protected Resource Metadata (PRM)
document at the well-known URI according to RFC 9728."

**Expected.** Both paths written out, since one of them is.

**Actual.** The PRM path has to be recovered from RFC 9728 itself
(`/.well-known/oauth-protected-resource`). The asymmetry is the trap: a
developer who sees one literal path reasonably assumes it is the only one.

**Workaround.** Serve both, plus the path-suffixed PRM variant, and assert their
presence in `tests/test_conformance.py::test_both_well_known_documents`.

**Suggestion.** Write both paths out literally, in a single code block, showing
the exact JSON each should return for a minimal server.

---

## 4. `resource` and client registration are underspecified for a self-hosted server

**Severity: medium.**

**Task attempted.** Implement the authorization code flow for an add-on where
the server is both the resource and its own authorization server.

**Steps taken.** Followed the OAuth 2.1 and PKCE requirements as listed.

**Expected.** Guidance on where `client_id` comes from, given that Dynamic
Client Registration is explicitly unsupported.

**Actual.** The docs state DCR is not supported but do not say how Alexa+
obtains a client identifier for a self-hosted server, nor whether the developer
chooses it, registers it in `addon.json`, or receives one at deploy time. The
`resource` parameter is required and must be "your MCP server's canonical URI",
but there is no statement about trailing slashes or whether the value must match
the PRM `resource` byte for byte.

**Workaround.** Pre-registered a client from configuration, normalised trailing
slashes on both sides, and enforced audience binding per RFC 8707, pinned by
`tests/test_conformance.py::test_wrong_resource_is_rejected`.

**Suggestion.** One short section: where `client_id` comes from, whether
comparison of `resource` is exact or normalised, and a worked example of the
three requests with real values filled in.

---

## 5. The Ring track is presented as open but gated behind partner approval

**Severity: medium**, and it is a planning cost rather than a coding one.

**Task attempted.** Decide which tracks to enter.

**Steps taken.** Read the track list, which says "any Ring API, SDK, simulator,
or device listed in Ring's developer documentation is acceptable", then followed
through to the Ring developer documentation.

**Expected.** Self-serve credentials, as with the Alexa+ track.

**Actual.** Ring's Partner API requires partner onboarding to obtain a client
ID, client secret and HMAC key. That is an approval queue of unknown length
inside a hackathon with a fixed deadline, and it is not discoverable from the
hackathon page.

**Workaround.** Chose different tracks.

**Suggestion.** Mark on the track list which tracks need approval or hardware
and what the expected turnaround is, so entrants spend their first day building
rather than discovering they cannot.

---

## 6. The Bee track's device requirement contradicts the general device rule

**Severity: low to medium.**

**Steps taken.** Compared two statements in the same ruleset.

**Actual.** One says no physical device is strictly mandated and that simulators
are acceptable. The Bee track says the project must use data "recorded and
processed through an actual Bee device or Apple Watch running Bee software" and
that "mentioning Bee without demonstrating a live data interaction does not
count". Both cannot be true for Bee.

**Suggestion.** State the hardware requirement per track and drop the general
rule, or add "except Bee" to it.

---

## What went well, since a friction log that only complains is not useful

- The MCP toolkit quickstart is concrete about the OAuth requirements. The
  `code_challenge_methods_supported` requirement in particular is stated as a
  must-be-present rather than left to a default, which caught a real omission.
- Accepting a simulated Alexa+ experience as an alternative to a registered
  add-on means the track is genuinely startable on day one, unlike Ring and Bee.
- Naming the spec version (2025-11-25) rather than "the latest" removed all
  ambiguity about which transport to implement.
