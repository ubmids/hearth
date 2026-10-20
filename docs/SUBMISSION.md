# Submission copy: Hearth, Amazon "Build, Ship, Shape", Alexa+ track

Deadline **Friday 23 October 2026, 12:00 PDT (19:00 UTC)**. Devpost:
amazonappdev2026.

Judging: Stage One pass/fail (fits the theme, really uses the required tech),
then four equally weighted criteria, Tech Implementation, Design, Potential
Impact, Quality of the Idea (ties go to Tech Implementation), plus up to 10% for
the friction log (`docs/FRICTION_LOG.md`, 12 platform entries).

**Stage One gate.** The track requires "a working Agent Skill or a self-hosted
MCP server, implementing MCP spec version 2025-11-25 … over Streamable HTTP",
or a simulated Alexa+ experience whose source is in the repo. Hearth is the MCP
server (and ships an Agent Skill), and the simulated client is in the repo at
`hearth/web/alexa.html`. Hearth's own conformance tests assert the protocol
version on the handshake and the header, and the official MCP conformance
suite (`@modelcontextprotocol/conformance` 0.1.16, `scripts/conformance.sh`)
passes every scenario that applies to it.

**Pre-existing work.** The repository was first committed on 14 September
2026, inside the hackathon window, and all of its code was written for this
event. It takes design ideas, not code, from the author's earlier single-user
memory server Cortex (`ubmids/cortex`, July 2026): retiring a fact with a
reason instead of deleting it, and an audit trail. A verbatim-overlap check
finds about 15 shared non-trivial lines out of roughly 2,500 (see
`docs/SPEC.md`).

**Track and mini challenge.** Primary track: **Alexa+**. Mini challenge:
**Open Source**, with `alexa-plus-mcp-checks` (see "Open Source mini challenge"
below).

---

## Project name

Hearth

## Tagline / elevator pitch (200 characters)

> Alexa+ can act now. Hearth makes that safe for a family caring for a parent:
> it stops a second blood thinner, carries the carer's handover to the family,
> and keeps an honest record.

(181 characters.)

## Text description

> **Rose, 84, in her kitchen:** Alexa, I'm just going to take my blood thinner.
>
> **Alexa:** Hold on, Rose. Grace gave you today's warfarin at 9:10 this
> morning. Your warfarin is once a day, so not another until tomorrow.

Nobody told Alexa that in the moment. Grace, the home aide, logged the morning
dose four hours earlier. Ada, Rose's daughter, set the rule twelve days ago from
the cardiologist's letter. Hearth held both, and it was Hearth's server, not the
language model, that refused the dose and wrote the refusal down.

### The problem

63 million Americans are family caregivers (AARP and the National Alliance for
Caregiving, 2025). Care for one parent gets split between a daughter with the
doctor's letters, a son two states away, a paid aide on weekday mornings, and
the parent herself, who forgets. Nobody holds the whole picture, and the gaps
are where people get hurt: older Americans have about 100,000 emergency
hospitalisations a year for adverse drug events, two thirds of them
unintentional overdoses, and warfarin is involved in a third (Budnitz et al.,
NEJM 2011).

The one device in that house that hears everybody is the speaker in the
kitchen. Alexa+ can take actions now, which makes it useful there and also
dangerous there. An assistant acting for a family has to know who said what,
whose word counts, what has already been done today, and it has to be able to
say why.

### What Hearth does

Hearth is an Alexa+ add-on, built as a self-hosted MCP server. It is the
family's shared memory and its conscience.

- **It stops the second dose.** `give_dose` checks the family's rule against
  today's record and refuses. The check runs in server code, so once the
  assistant reports the dose, nothing the model says can turn the refusal into
  a yes. The name on the bottle ("warfarin sodium", "Jantoven 5 mg") reaches
  the same rule, and a medicine with no rule gets "check with Ada first", not
  "logged".
- **It carries the carer's handover.** At the end of her shift Grace says
  "I'm off. Mom ate half her lunch, she was a bit dizzy after her walk, and
  we're nearly out of Ensure." One tool call: the handover goes on the family
  board and to the family's phones, Ensure goes on the shared shopping list,
  and the dizziness is flagged to Ada, who has the say over Mom's health, and
  pinned in front of her for two days. Hearth does not judge whether it
  matters; it makes sure the person who decides hears it today. Tom's
  catch-up that evening includes the handover, and when Ada says "order
  what's on the list", it is the Ensure Grace reported that gets priced, and
  paying for it ticks it off the list.
- **A medication rule changes only in the name of the person with the say.** When Tom says
  "Mom's warfarin is twice a day", Hearth files it as a proposal and answers
  "Ada has the say over Mom's warfarin, so it stays once a day until Ada
  confirms." Ada settles it by saying the rule herself, and any change made in
  her name is pinned on her board, because Hearth cannot hear who is speaking.
- **One request, five steps.** "Mom's cardiology moved to Thursday at ten,
  sort it out." Hearth moves the calendar entry, assigns Tom because the family
  rota says he does Thursdays, cancels Tuesday's ride and books a new one for
  9:15 (a sandbox ride provider), leaves a note for Tom and Grace on the family
  board and pushes it to Tom's phone (a real ntfy notification), and warns if a
  dose falls during the trip. That is one sentence and one tool call, and every
  step is on the record. The calendar, rota and board are Hearth's own books,
  not outside services.
- **It remembers across sessions and devices.** That evening, Tom asks his own
  (simulated) Echo Dot "What did I miss with Mom?" Hearth knows when he last talked to the
  house and tells him only what has changed since, including the dose it
  stopped.
- **It settles disagreements, and says how.** "Mom's coffee stops at three. Tom
  said six, but Ada has the say over what she eats and drinks."
- **It lets situations end.** "No wine while she's on the antibiotics" holds
  until "Mom finished the antibiotics", then stops applying by itself.
- **It buys the Alexa+ way.** "Reorder her warfarin" prices the refill and
  checks it against Ada's $50 limit and last week's orders. The card shows
  those checks and a Pay button. Per the Alexa+ payments docs, Alexa+ then
  runs the checkout on Hearth's Universal Commerce Protocol endpoints (voice
  PIN, the card on the account, idempotent completion); in the demo the
  simulated client plays that part against a sandbox merchant. Hearth never
  charges anything itself.
- **It keeps an honest record.** The server writes down every tool call as it
  happens, with what it read and what it wrote, in a hash chain whose head it
  signs after every call into a witness file kept apart from the record.
  Truncating it, or editing, deleting or reordering an entry and recomputing
  the hashes, fails the check. Each result hands the client a receipt, and
  "show me the record" checks the receipt the device kept, which catches a
  rewrite even by someone holding the signing key, up to that receipt. If the
  assistant reports an action it never checked with Hearth first, "why did you
  do that?" says so.
- **It draws on the screen and talks on a speaker.** Results carry an MCP Apps
  card sized for the Echo Show, plus a complete spoken sentence for an Echo Dot
  with no screen.

### How it is built

- **MCP 2025-11-25 over Streamable HTTP**, hand-rolled: 15 tools with
  annotations, `structuredContent`, and an **MCP Apps** view
  (`ui://hearth/card-<hash>.html`, `text/html;profile=mcp-app`) named in
  `_meta.ui.resourceUri` on both the tool and the result.
- **OAuth 2.1 authorization code flow with PKCE (S256)**, both well-known
  documents, and the three places Alexa+ departs from stock MCP: a `401` with
  no `WWW-Authenticate` header, both metadata documents required, and bearer
  tokens in the query string refused.
- **UCP checkout** (`/.well-known/ucp`, `/checkout-sessions`, `…/complete`,
  `…/cancel`), with `Idempotency-Key` replay, business failures returned as
  200 with `messages[]`, and `Cache-Control: no-store`.
- **No model on the read path.** Resolving what is true is a dictionary lookup
  (scope, then authority, then recency, with a reason), so the server's share
  of the 500 ms Alexa+ allows is tiny; the rest is network. The server's own
  time is stamped on every response in `Server-Timing`: p50 about 0.1 ms for `check_dose` on our test box, flat
  from the first call to the 5,000th, because the record is appended, never
  rewritten.
- **An Agent Skill** (`skills/hearth-care/SKILL.md`, open Agent Skills format)
  that teaches any agent to use Hearth safely. The simulated client's model
  planner loads it, and `demo/assistant.py` runs Claude Code as a second MCP
  client with the same skill.
- **One household per account**, isolated, persisted to disk.
- **A classic Alexa skill that is an MCP client of Hearth** (`skill/`, ASK SDK
  for Python): Alexa's NLU picks the intent, the skill makes the `tools/call`
  over Streamable HTTP, says Hearth's text verbatim, and draws Hearth's card in
  APL on an Echo Show. Its MCP client is standard-library only, because
  Alexa-hosted skills run Python 3.8 and the official MCP SDK needs 3.10
  (friction log entry 12). Its tests drive the real handler against a running
  Hearth, on Python 3.8 as well as 3.12; `docs/ALEXA_TEST.md` has the steps
  for the developer console's simulator.
- **Tests**: Hearth's own suite (conformance tests written from the Alexa+
  requirements as documented, the care household, the record, resolution,
  phrasing, extraction, the listing, the simulator), an interop test in which
  the official MCP Python SDK client talks to Hearth unmodified, and the
  official MCP conformance suite in CI. Parts of the suite came from hand
  mutation testing of `oauth.py`, `household.py` and `app.py`.

### Simulated, and why

Alexa+ add-on tooling (the MCP Toolkit, the CLI, the Web Simulator) is
"available to select partners only", and hackathon entrants cannot get
access. So the video shows a **simulated Alexa+ client**, labelled as such on
every screen, at `/alexa`. It is a real MCP client: it authorises with PKCE,
opens an MCP session per device (kitchen Echo Show, Tom's Echo Dot, Ada's
Alexa app), lists tools, reads Hearth's MCP App and hosts it the way an Echo
Show would, calls tools over Streamable HTTP, and plays the host's part in
checkout. The MCP traffic can be shown live beside the conversation. A language
model stands in for Alexa's: it is given Hearth's real `tools/list` and Hearth's
Agent Skill, and chooses every tool call; the header names the model. In the
video it is a small open model on the laptop (Qwen2.5 7B Instruct through Ollama),
which planned every filmed line correctly in one to three seconds; Amazon
Bedrock (Converse API) or any OpenAI-compatible endpoint is one setting away.
A small model is enough because the safety is in the server. Three things
never depend on the model's reading, and the header says when any steps in: a
question never records a dose, a dose being taken always reaches `give_dose`,
and an appointment stays on the weekday the person said. The public deployment
has no model key, so there the offline rules plan, and the header says so. **Every word Alexa says is the text Hearth
returned**, except the order confirmation after "yes", which is the host's own
line built from the completed checkout session.

Also simulated: the ride service and the pharmacy are sandbox providers. Nothing
books a car or charges a card. Hearth is not a medical device: it enforces the
rules the family gives it and knows no pharmacology.

### What's next

The day the Alexa+ toolkit opens: `alexa-ai new mcp --mcp-server-url
https://…/mcp`. Then a per-voice speaker identifier from Alexa+ (friction log
entry 8), so that who has the say over medication no longer depends on the
model naming the speaker. After that, pharmacy and ride partners through the
same UCP and tool surfaces, and the signed checkpoint pushed to each family
member's phone every day, so that every entry before it is covered by a copy
the operator does not hold.

## Testing instructions (for judges)

No account or credentials are needed.

1. Open https://hearth-sh3u.onrender.com/alexa (the first load can take up to
   a minute if the free instance was asleep). The page signs itself in with
   OAuth 2.1 + PKCE and opens an MCP session per simulated device. **Under the
   hood** (top right, or the T key) shows the live MCP traffic.
2. Press **→** to play the scenes in order, or pick a person (Rose, Grace,
   Tom, Ada) and type, for example "I'm just going to take my blood thinner"
   as Rose. Every Alexa line is Hearth's own answer.
3. On this public deployment the planner is the offline rules (the header
   says so), because no model key is kept on the server. To run it with a
   model: `pip install -r requirements.txt`, set
   `HEARTH_SIM_LLM_BASE_URL`, `HEARTH_SIM_LLM_API_KEY` and
   `HEARTH_SIM_LLM_MODEL` for any OpenAI-compatible endpoint (or
   `HEARTH_BEDROCK_MODEL` and AWS credentials for Bedrock), then
   `uvicorn hearth.app:app --port 8000` and open `http://localhost:8000/alexa`.
4. Any MCP client can use `https://hearth-sh3u.onrender.com/mcp` after the
   OAuth flow; `/console` is the household's operator view.

## Open Source mini challenge

- **Contribution URL:** https://github.com/ubmids/alexa-plus-mcp-checks
- **Project repository URL:** https://github.com/ubmids/hearth
- **GitHub username:** ubmids
- **What it is:** `alexa-plus-mcp-checks`, a new MIT-licensed pytest plugin and
  GitHub Action that checks any self-hosted MCP server against the places where
  the Alexa+ MCP toolkit departs from stock MCP (a `401` without
  `WWW-Authenticate`, both well-known documents with `S256`, query-string
  tokens refused, MCP Apps `_meta.ui.resourceUri` on the tool and the result,
  the 500 ms budget) and the MCP 2025-11-25 transport rules (Origin 403,
  protocol-version 400, session 400, batches refused, bad arguments as
  `isError`).
- **How it works:** `pytest --alexa-mcp-url https://host/mcp` (or the
  `alexa-mcp-check` command, or the Action) runs 13 checks with plain-English
  failures naming the requirement and its source. Its own suite (35 tests)
  runs every check against a conformant stdlib fake server and 18 broken
  variants, each of which must fail exactly its own check.
- **Why it matters:** the Alexa+ add-on tools and simulator are partner-only, so
  most developers cannot find out whether their server would connect. Most of
  what goes wrong is protocol, and protocol does not need gated access. Run
  against Hearth's code from before this week's fixes, it caught four MUST
  violations (Origin, protocol version, batch, isError) and one SHOULD
  (session); against the
  current code all 13 pass (`docs/hearth-before-run.txt`, `docs/hearth-run.txt`
  in that repository).

## Built with

`mcp` (spec 2025-11-25, Streamable HTTP) · `mcp-apps` · `universal-commerce-protocol`
· `oauth2.1-pkce` · `agent-skills` · `alexa-plus` (simulated) · `alexa-skills-kit`
(classic skill, `ask-sdk-core`, APL) · `python` · `fastapi` · `uvicorn` ·
`ollama` + `qwen2.5` (the planner in the video, on the laptop) ·
`amazon-bedrock` (Converse API, optional planner) · `ed25519` (signed record
checkpoints) · `ntfy` (phone push) · `piper-tts` · `amazon-polly` (optional) ·
`playwright` (rehearsal) · `@modelcontextprotocol/conformance` (CI)

## Links

- Repository: https://github.com/ubmids/hearth (MIT)
- Live MCP endpoint: https://hearth-sh3u.onrender.com/mcp (simulated client at
  https://hearth-sh3u.onrender.com/alexa)
- Video: (YouTube/Vimeo URL)
- Transcript of the filmed afternoon: `demo/transcript.md`

---

## Product feedback (required field)

Every claim below comes from `docs/FRICTION_LOG.md`, which has full
reproduction steps, severity, workaround and suggestion for each.

### Which developer tools, APIs and SDKs did you use, and for what?

- **MCP spec 2025-11-25 over Streamable HTTP**, hand-rolled rather than taken
  from an SDK. Three of the Alexa+ requirements are things a general MCP SDK
  gets wrong by default, the main one being a `WWW-Authenticate` header that
  RFC 9728 tells you to send and Alexa+ requires you to omit. Owning the
  transport was the only way to satisfy both.
- **MCP Apps** (SEP-1865, 2026-01-26) for the Echo Show cards, following the
  Alexa+ quickstart's "follow the MCP Apps standard".
- **Universal Commerce Protocol** checkout sessions for the refill, per the
  Alexa+ payments pages.
- **OAuth 2.1 with PKCE S256**, hand-rolled, plus both discovery documents.
- **Agent Skills** (open format) for `skills/hearth-care`.
- **Piper** offline neural voices for the simulated client (the demo audio).
  An **Amazon Polly** neural path is wired for when AWS keys are set; its
  request signing is unit-tested but it has not been run against AWS.
- **Alexa Skills Kit** (`ask-sdk-core`, APL) for the classic skill in
  `skill/`, tested locally against Hearth on Python 3.8, the Alexa-hosted
  runtime.
- We could **not** use the `alexa-ai` CLI, the MCP Toolkit, the local inspector
  or the Web Simulator: all four are partner-only (friction log entry 5).

### What worked well

The protocol choice. Naming the version outright (`2025-11-25`, not "the
latest") removed a whole class of ambiguity. Streamable HTTP is the right
transport and the deprecation of HTTP+SSE is clearly stated. Pointing add-on
visuals at MCP Apps rather than a proprietary format, and payments at UCP, means
the same server works with any MCP host: the official MCP Python SDK client
talks to Hearth with no changes on either side. The functional requirements (confirm before high-consequence
actions, detect duplicate transactions, keep household members' data isolated)
are the right ones and shaped the design.

### What needs improvement

The two that cost most:

1. **The add-on tools are partner-only, and the setup guides do not say so**
   (high). The quickstart walks through `alexa-ai new` and the Web Simulator;
   only the docs home page and the hackathon FAQ say entrants cannot get
   access. The demo plan assumed a simulator that cannot be reached.
2. **Alexa+ does not tell an add-on who is speaking** (high for any household
   add-on). The bearer token is the account, not the person. A family's rule
   about who may change a medication schedule ends up resting on the language
   model's reading of who spoke.

Also: the `401` must omit `WWW-Authenticate` against every SDK's default; where
the 500 ms budget is measured is not stated (from Lagos, network alone is
357 ms at p50); one of the two required well-known paths is given only by
description; the docs and the MCP Apps spec disagree on where
`_meta.ui.resourceUri` goes; the lifecycle example negotiates protocol
2025-03-26; the UCP hand-off cannot be tried and the voice-only payment trigger
is undocumented; tool annotations are never connected to confirmation turns;
and "Agent Skill" names three different things.

### How was the onboarding experience?

Good on transport, thin on conformance, and closed at the point where you would
test. Everything needed to stand up an MCP server is easy to find. Everything
needed to stand up one that Alexa+ will accept had to be pieced together from
spec pages, a client-lifecycle page that contradicts the quickstart, and
inference. A one-page conformance checklist, plus a public harness for the
protocol parts that do not need to be gated, would save every developer most
of a week.

### Would you build with these tools again?

**Yes.** Building on open standards (MCP, MCP Apps, UCP) is the right call,
and it is why the same server works in our simulator and with the official
MCP SDK client without changes. The reservations are about documentation and access, which
are the cheapest things here to fix.

## Feature requests (priority in brackets)

1. **[High] A per-voice speaker identifier** in `_meta`, behind a customer
   permission, so an add-on can apply household roles without trusting the
   model to name the speaker.
2. **[High] A public conformance harness or stripped-down simulator** for the
   MCP handshake, OAuth and MCP Apps rendering. Protocol does not need to be
   gated.
3. **[High] A conformance checklist page** listing every departure from stock
   MCP, `WWW-Authenticate` first.
4. **[Medium] Say where the 500 ms budget is measured.** One sentence.
5. **[Medium] A UCP sandbox payment handler**, and the voice-only trigger for
   payment.
6. **[Medium] Say whether Alexa+ reads tool annotations** and which ones
   trigger a confirmation turn.
7. **[Low] Rename the onboarding "Agent Skill"** and say whether Alexa+ loads
   skills shipped by an add-on.

