# Submission copy: Hearth, Amazon "Build, Ship, Shape", Alexa+ track

Deadline **Friday 23 October 2026, 12:00 PDT (19:00 UTC)**. Devpost:
amazonappdev2026. Aim to submit by 21 October; nothing is gained by waiting.

Judging: Stage One pass/fail (fits the theme, really uses the required tech),
then four equally weighted criteria, Tech Implementation, Design, Potential
Impact, Quality of the Idea (ties go to Tech Implementation), plus up to 10% for
the friction log (`docs/FRICTION_LOG.md`, 11 platform entries).

**Stage One gate.** The track requires "a working Agent Skill or a self-hosted
MCP server, implementing MCP spec version 2025-11-25 … over Streamable HTTP",
or a simulated Alexa+ experience whose source is in the repo. Hearth is the MCP
server (and ships an Agent Skill), and the simulated client is in the repo at
`hearth/web/alexa.html`. 62 conformance tests assert the protocol version on
the handshake and the header.

**Pre-existing work.** The repository was first committed on 14 September
2026, inside the hackathon window, so all of it is new work.

---

## Project name

Hearth

## Tagline / elevator pitch (200 characters)

> Alexa+ can act now. Hearth makes that safe in a home caring for a parent: it
> stops a second blood thinner, sorts out appointments across services, and
> keeps an honest record.

(174 characters.)

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
  today's record and refuses. The check runs in server code, so it holds
  whatever the model would have said.
- **One request, five services.** "Mom's cardiology moved to Thursday at ten,
  sort it out." Hearth moves the calendar entry, assigns Tom because the family
  rota says he does Thursdays, cancels Tuesday's ride, books a new one for 9:15,
  tells the family board, and warns if a dose falls during the trip. That is one
  sentence and one tool call, and every step is on the record.
- **It remembers across sessions and devices.** That evening, Tom asks his own
  Echo Dot "What did I miss with Mom?" Hearth knows when he last talked to the
  house and tells him only what has changed since, including the dose it
  stopped.
- **It settles disagreements, and says how.** "Mom's coffee stops at three. Tom
  said six, but Ada has the say over what she eats and drinks."
- **It lets situations end.** "No wine while she's on the antibiotics" holds
  until "Mom finished the antibiotics", then stops applying by itself.
- **It buys the Alexa+ way.** "Reorder her warfarin" prices the refill and
  checks it against Ada's $50 limit and last week's orders. The card shows
  those checks and a Pay button. Alexa+ then runs the checkout on Hearth's
  Universal Commerce Protocol endpoints (voice PIN, the card on the account,
  idempotent completion), and Hearth never charges anything itself.
- **It keeps an honest record.** The server writes down every tool call as it
  happens, with what it read and what it wrote, in a hash chain. If the
  assistant reports an action it never checked with Hearth first, "why did you
  do that?" says so.
- **It draws on the screen and talks on a speaker.** Results carry an MCP Apps
  card sized for the Echo Show, plus a complete spoken sentence for an Echo Dot
  with no screen.

### How it is built

- **MCP 2025-11-25 over Streamable HTTP**, hand-rolled: 13 tools with
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
  (scope, then authority, then recency, with a reason), so every answer fits
  the 500 ms Alexa+ allows. The server's own time is stamped on every response
  in `Server-Timing`, typically under 2 ms.
- **An Agent Skill** (`skills/hearth-care/SKILL.md`, open Agent Skills format)
  that teaches any agent to use Hearth safely. `demo/assistant.py` runs it with
  Claude Code as the MCP client against the same server.
- **One household per account**, isolated, persisted to disk.
- **160 tests**, 62 of them Alexa+ conformance, plus an interop test in which
  the official MCP Python SDK client talks to Hearth unmodified. The suite has
  been mutation tested.

### Simulated, and why

Alexa+ add-on tooling (the MCP Toolkit, the CLI, the Web Simulator) is
"available to select partners only", and hackathon entrants cannot get
access. So the video shows a **simulated Alexa+ client**, labelled as such on
every screen, at `/alexa`. It is a real MCP client: it authorises with PKCE,
opens an MCP session per device (kitchen Echo Show, Tom's Echo Dot, Ada's
Alexa app), lists tools, reads Hearth's MCP App and hosts it the way an Echo
Show would, calls tools over Streamable HTTP, and plays the host's part in
checkout. The MCP traffic is shown live beside the conversation. A small
planner stands in for Alexa's language model (a configured model, taught by
Hearth's Agent Skill, or built-in rules; the header says which). **Every word Alexa says is the text Hearth
returned.**

Also simulated: the ride service and the pharmacy are sandbox providers. Nothing
books a car or charges a card. Hearth is not a medical device: it enforces the
rules the family gives it and knows no pharmacology.

### What's next

The day the Alexa+ toolkit opens: `alexa-ai new mcp --mcp-server-url
https://…/mcp`. Then a per-voice speaker identifier from Alexa+ (friction log
entry 8), so that who has the say over medication no longer depends on the
model naming the speaker. After that, pharmacy and ride partners through the
same UCP and tool surfaces, and a signed daily digest of the record sent to the
family, so that even the operator cannot rewrite it unnoticed.

## Built with

`mcp` (spec 2025-11-25, Streamable HTTP) · `mcp-apps` · `universal-commerce-protocol`
· `oauth2.1-pkce` · `agent-skills` · `alexa-plus` (simulated) · `python` ·
`fastapi` · `uvicorn` · `piper-tts` · `amazon-polly` (optional) · `playwright`
(rehearsal) · `claude-code` (second MCP client)

## Links

- Repository: https://github.com/ubmids/hearth (make it public, or share it
  privately with testing@devpost.com)
- Video: (YouTube/Vimeo URL, public)
- Audio of the scenes, for judges who prefer it: `demo/hold-on-rose.m4a`

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
- **Amazon Polly** neural voices for the simulated client when AWS keys are
  set; **Piper** offline otherwise.
- We could **not** use the `alexa-ai` CLI, the MCP Toolkit, the local inspector
  or the Web Simulator: all four are partner-only (friction log entry 5).

### What worked well

The protocol choice. Naming the version outright (`2025-11-25`, not "the
latest") removed a whole class of ambiguity. Streamable HTTP is the right
transport and the deprecation of HTTP+SSE is clearly stated. Pointing add-on
visuals at MCP Apps rather than a proprietary format, and payments at UCP, means
the same server works with any MCP host. Hearth's second client, Claude Code,
needed no changes. The functional requirements (confirm before high-consequence
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
and it is why the same server works in our simulator and in another assistant
without changes. The reservations are about documentation and access, which
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

---

## Before submitting

- [ ] Video under 3:00, public on YouTube or Vimeo, recorded from
      `docs/DEMO_SCRIPT.md`; SIMULATED ALEXA+ visible throughout
- [ ] Repository public with the MIT licence visible, or shared privately with
      testing@devpost.com (decide; the task did not authorise changing
      visibility)
- [ ] Merge `first-place` into `master` (or point the submission at the branch)
- [ ] Product feedback and feature requests pasted from above
- [ ] Friction log attached or linked: `docs/FRICTION_LOG.md`
- [ ] Optional live URL: the Render workspace is suspended for billing. Either
      restore it (and set `HEARTH_REDIRECT_URIS` to include `<issuer>/alexa`)
      or leave the live URL out; the rules do not require one
- [ ] Secret sweep before the repo goes public
- [ ] Submitted by 21 October; hard deadline 23 October, 12:00 PDT
