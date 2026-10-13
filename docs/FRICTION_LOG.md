# Friction log: building a self-hosted MCP server for Alexa+

Recorded while building Hearth between 14 September and submission. Every entry
is something that actually cost time on this build, in the format the hackathon
rules ask for: task attempted, steps taken, expected versus actual, severity,
workaround, suggestion.

Entries 1 to 4 come from the first build (transport and OAuth). Entries 5 to 11
come from the October rebuild around a care household, when Hearth added MCP
Apps visuals, a checkout, cross-session memory and a simulated Alexa+ client,
and every one of them is a place where the Alexa+ add-on documentation and the
thing being built disagreed or went quiet. Source pages are linked. Two entries
about the hackathon's track structure, rather than the developer platform, are
kept separately at the end.

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

## 5. The Alexa+ add-on tools are partner-only, and the setup guides do not say so

**Severity: high.** It decides what a developer can test at all, and it is
discovered late.

**Task attempted.** Register Hearth as an add-on and test it end to end in the
Alexa+ Web Simulator.

**Steps taken.** Followed the MCP Toolkit quickstart, which walks through
`alexa-ai new mcp`, `alexa-ai deploy` and testing in the Web Simulator. Our own
spec, written from that page in September, records the spike as "green, no
device needed … testable in the web simulator".

**Expected.** That a quickstart is something a developer can start.

**Actual.** The Category SDK, MCP Toolkit, CLI and Web Simulator are "in preview
and available to select partners only - there is currently no way for hackathon
participants to apply for or gain access". The hackathon FAQ says so, and adds
that this "is called out on Amazon's add-on docs home page, though it's
sometimes missing from individual setup-guide pages, which has caused some
confusion" ([FAQ](https://amazonappdev2026.devpost.com/details/faqs)). That is
exactly what happened here: the plan for the demo video assumed a simulator
that cannot be reached.

**Workaround.** Built a clearly labelled simulated Alexa+ client (`/alexa`) that
is a real MCP client: OAuth 2.1 + PKCE, initialize, tools/list, resources/read
for the MCP App, tools/call, all over Streamable HTTP, with the traffic on
screen.

**Suggestion.** Put the availability banner on every setup page, not only the
docs home. Better: publish a conformance harness (or a stripped-down public
simulator) that exercises the MCP handshake, the OAuth flow and MCP Apps
rendering without the gated pieces. Most of what a developer needs to check is
protocol, and protocol does not need to be gated.

---

## 6. Where `_meta.ui.resourceUri` goes: the Alexa+ docs and the MCP Apps spec disagree

**Severity: medium.** Silent: the wrong placement means plain text instead of
the card, with no error.

**Task attempted.** Return rich visuals for screen devices.

**Steps taken.** The quickstart says "If you expect to provide visuals, follow
the MCP Apps standard". The MCP Apps specification (SEP-1865, stable
2026-01-26) declares the view on the **tool definition**:
`_meta.ui.resourceUri` alongside `inputSchema`. The Alexa+ client lifecycle page
says "Alexa+ renders your custom visuals for your MCP App UI as long as you have
resourceUri defined in the **tool response**", and its example puts
`_meta.ui.resourceUri` on the result, with two extra keys, `invoking` and
`invoked`, that are not in the MCP Apps spec
([client lifecycle](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-client-lifecycle.html)).

**Expected.** One place, matching the standard the docs point to.

**Actual.** Two places, and two undocumented keys. Without access to Alexa+
(entry 5) there is no way to find out which one it actually reads.

**Workaround.** Set it in both places; leave `invoking`/`invoked` out until they
are defined. Pinned by
`tests/test_care.py::test_tools_name_their_view_and_the_view_is_served_as_an_mcp_app`.

**Suggestion.** State that Alexa+ reads the tool definition per the MCP Apps
spec (or that it reads both), and either define `invoking`/`invoked` or remove
them from the example.

---

## 7. The lifecycle example negotiates protocol 2025-03-26, while the requirement is 2025-11-25

**Severity: medium.** A developer who copies the example ships the wrong
version string, and the version is the one thing Stage One checks.

**Steps taken.** Compared the client lifecycle page's example exchange with the
requirement on the quickstart and in the hackathon rules.

**Actual.** The example's `initialize` shows `"protocolVersion": "2025-03-26"`
(twice), the release in which Streamable HTTP was introduced, while the
quickstart and the rules require 2025-11-25.

**Workaround.** Hearth answers `2025-11-25` on `initialize` and in the
`MCP-Protocol-Version` header, asserted in `tests/test_conformance.py`.

**Suggestion.** Update the example to 2025-11-25, and say what Alexa+ does when
a server answers with an older version (refuse, or downgrade).

---

## 8. Alexa+ does not tell an add-on who is speaking

**Severity: high for any household add-on.** It moves a trust decision from
the platform to the language model.

**Task attempted.** Apply a family's authority rules: Ada holds her mother's
health care proxy, so her rule about medication stands over her brother's.

**Steps taken.** Looked for a speaker or person identifier in the request,
`_meta`, headers or the permissions model.

**Expected.** Alexa already recognises voices in a household, so some opaque
per-person identifier on the call.

**Actual.** The only identity that reaches the server is the OAuth bearer token,
which is the account, not the person. The functional requirements say to
"verify each household member's data stays isolated", but there is no
documented way to tell household members apart
([functional requirements](https://developer.amazon.com/docs/alexaplus/add-ons/functional-requirements.html)).

**Workaround.** Every Hearth tool that depends on who is talking takes the name
as an argument (`speaker`, `asked_by`, `given_by`), and the tool descriptions
and the Agent Skill tell the model to ask when it does not know. That works,
and it means a rule about who may change a medication schedule rests on the
model's reading of who spoke.

**Suggestion.** Pass an opaque, stable, per-recognised-voice identifier (and a
confidence) in `_meta`, behind a customer permission. It need not be a name;
an add-on can map it to one.

---

## 9. Payments: the rules are clear, the hand-off cannot be tried

**Severity: medium.**

**Task attempted.** Let the family reorder a prescription inside a spending
limit.

**Steps taken.** Read the payments pages: Alexa+ owns the checkout experience;
the add-on implements Universal Commerce Protocol checkout sessions
(`POST /checkout-sessions`, `…/{id}/complete`, `…/cancel`) declared in
`/.well-known/ucp`; an MCP App triggers payment with a `ui/message` ("Pay for
this order"), and "Don't use tools/call for payment actions".

**Expected.** A sandbox payment handler, or a way to see the `UCP-Agent`,
`Idempotency-Key` and completion calls Alexa would make.

**Actual.** All of it sits behind the gated toolkit (entry 5). The pages also
do not say how a voice-only device, which has no MCP App to send `ui/message`,
starts the payment.

**Workaround.** Implemented the session endpoints to the documented shape
(sandbox merchant, idempotent completion, spending-limit and duplicate checks),
and had the simulated client play the host's part. Covered in
`tests/test_care.py`.

**Suggestion.** A public sandbox for the UCP hand-off, and one sentence on the
voice-only trigger.

---

## 10. Tool annotations: required confirmation is described, the link to MCP's hints is not

**Severity: low to medium.**

**Steps taken.** The functional requirements say to "require explicit
confirmation with key details before any high-consequence action" and to
"detect and prevent duplicate transactions". MCP 2025-11-25 already has
`readOnlyHint`, `destructiveHint`, `idempotentHint` and `openWorldHint`.

**Actual.** The add-on docs never mention the annotations, so it is unclear
whether Alexa+ uses them to decide when to confirm, or ignores them.

**Workaround.** Hearth sets them on all 13 tools and enforces the consequential
refusals (a second dose, an order over the limit) in server code, since the MCP
spec says clients must treat annotations as untrusted anyway.

**Suggestion.** Say whether Alexa+ reads tool annotations, and which ones
trigger a confirmation turn.

---

## 11. "Agent Skill" names three different things, and none of them says what Alexa+ loads

**Severity: medium.** It decides which of the two Stage One paths a developer
takes ("a working Agent Skill or a self-hosted MCP server"), and the docs
cannot settle it.

**Task attempted.** Ship an Agent Skill alongside the MCP server, since the
rules list Agent Skills as a creative choice.

**Steps taken.** Searched the Alexa+ add-on docs and the hackathon pages for
what an Alexa+ Agent Skill is.

**Expected.** One definition: the format, where it is loaded, and whether
Alexa+ itself reads it at runtime.

**Actual.** Three meanings, none of them the runtime one:

- the hackathon rules use "Agent Skill" as a deliverable equal to an MCP
  server, and link the open Agent Skills format;
- the MCP Toolkit overview uses "the add-on Agent Skill (agentic onboarding
  experience)" for a skill that helps a coding agent *deploy* an add-on
  ([MCP Toolkit overview](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-overview.html));
- the Category SDK has an "Action Skill", again for a coding agent (Kiro,
  Claude Code, Cursor) building an add-on, not for Alexa+ using one.

Nothing says whether Alexa+ reads a `SKILL.md` that an add-on ships, which is
the one meaning that would change how an add-on behaves for customers. The
older word "Alexa Skill" (the ASK kind) is still in every search result too.

**Workaround.** Hearth ships `skills/hearth-care/SKILL.md` in the open Agent
Skills format: which tool to call for which request, the safety rules that must
never be overridden, and how payment is handed off. It is written for any
agent that uses Hearth, and `demo/assistant.py` runs it with Claude Code as the
MCP client against the same server, so it is exercised, not just written.

**Suggestion.** One paragraph on the add-ons home page: whether Alexa+ loads
skills from an add-on at runtime and from where, and a different name for the
onboarding skill (an "add-on builder skill") so the two stop colliding.

---

## About the hackathon, not the platform

These two cost planning time rather than build time, and are kept apart so the
platform entries above are read first.

### A. The Ring track is presented as open but gated behind partner approval

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

### B. The Bee track's device requirement contradicts the general device rule

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

### C. Whether the server must stay up through judging

The FAQ says the MCP server "doesn't need to stay running after you submit"; an
organiser's forum answer says it "needs to be live and accessible till the end
of the judging period". We are planning for the second.

---

## What went well, since a friction log that only complains is not useful

- The MCP toolkit quickstart is concrete about the OAuth requirements. The
  `code_challenge_methods_supported` requirement in particular is stated as a
  must-be-present rather than left to a default, which caught a real omission.
- Accepting a simulated Alexa+ experience as an alternative to a registered
  add-on means the track is genuinely startable on day one, unlike Ring and Bee,
  and the FAQ is unusually direct about why it is needed.
- Pointing at the MCP Apps standard for visuals, rather than inventing an
  Alexa-only format, meant the same card renders in any MCP Apps host. The
  layout guide (768x480 canvas, one self-contained file, content hash in the
  URI, Card/List/Carousel/Map only) was specific enough to build to blind.
- Naming the spec version (2025-11-25) rather than "the latest" removed all
  ambiguity about which transport to implement.
