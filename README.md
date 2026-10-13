# Hearth

**The memory and the conscience of a family caring for someone.
An Alexa+ add-on, built as a self-hosted MCP server.**

> **Rose, 84, in her kitchen:** Alexa, I'm just going to take my blood thinner.
>
> **Alexa:** Hold on, Rose. Grace gave you today's warfarin at 9:10 this morning.
> Your warfarin is once a day, so not another until tomorrow.

![The simulated Alexa+ kitchen Echo Show stopping a second warfarin, with the live MCP traffic beside it](docs/img/hold-on-rose.jpg)

[Listen to the whole household (2 min)](demo/hold-on-rose.m4a) ·
[transcript](demo/transcript.md). Every Alexa line is Hearth's real answer.

Nobody told Alexa that in the moment. Grace, the home aide, logged the morning
dose four hours earlier. Ada, Rose's daughter, set the rule twelve days ago from
the cardiologist's letter. Hearth held both, and it was Hearth, not the language
model, that refused the dose and wrote the refusal down.

## Why this matters

**63 million Americans** are family caregivers, nearly 50% more than in 2015
([AARP and the National Alliance for Caregiving, 2025](https://www.aarp.org/pri/topics/ltss/family-caregiving/caregiving-in-the-us-2025/)).
Care for one parent is split between a daughter with the doctor's letters, a son
two states away, a paid aide on weekday mornings, and the parent herself, who
forgets. Nobody holds the whole picture, and the gaps are where people get hurt.

Older Americans have about **100,000 emergency hospitalizations a year** for
adverse drug events. Two thirds are **unintentional overdoses**, and **warfarin
is involved in a third** of them
([Budnitz et al., NEJM 2011](https://pubmed.ncbi.nlm.nih.gov/22111719/)).

The one device in that house that hears everybody is the speaker in the
kitchen. Alexa+ can act now, which makes it useful there and dangerous there:
an assistant that acts on a family's behalf has to know who said what, whose
word counts, what has already been done today, and it has to be able to say
why.

## What Hearth does

| | |
|---|---|
| **Stops the second dose** | `give_dose` checks the family's rule (once a day, set by Ada, who holds the health care proxy) against today's record (given 9:10, by Grace) and refuses. In code, on the server, whatever the model would have said. |
| **Sorts it out across services, in one request** | "Mom's cardiology moved to Thursday at ten, sort it out." Calendar moved, Tom assigned because the family rota says he does Thursdays, Tuesday's ride cancelled, a new ride booked for 9:15, the family board told, and a dose that falls during the trip called out. Five services, one sentence, every step on the record. |
| **Remembers across sessions and devices** | Tom, on his own Echo Dot that evening: "What did I miss with Mom?" Hearth knows when he last talked to the house and tells him only what changed since, including the dose it stopped. |
| **Settles disagreements, and says how** | Tom says Mom can have coffee till six; Ada said three because it keeps her up. "Mom's coffee stops at three. Tom said six, but Ada has the say over what she eats and drinks." |
| **Lets situations end** | "No wine while she's on the antibiotics" holds until "Mom finished the antibiotics", then stops applying by itself. |
| **Buys, the Alexa+ way** | "We're nearly out of her warfarin, reorder it" prices the refill against the family's spending limit and last week's orders, and offers Pay. Alexa+ then opens the checkout session on Hearth's Universal Commerce Protocol endpoints, takes the PIN and the card, and completes it. Hearth never charges anything itself. |
| **Keeps an honest record** | Every tool call is written by the server as it happens, hash-chained, with what it read and wrote. If the assistant reports an action it never checked with Hearth first, "why did you do that?" says so. |
| **Draws it on the screen** | Results carry an MCP Apps card (`ui://hearth/card-…`), sized for the Echo Show, and a complete spoken sentence for a speaker with no screen. |

## How it is built

```
 Alexa+ (or the simulated client at /alexa)
    │  MCP 2025-11-25 · Streamable HTTP · OAuth 2.1 + PKCE (S256)
    ▼
 /mcp ──► HearthMCP ──► every tools/call written to the record (SHA-256 chain)
              │
              ├── beliefs: who said it, when, about whom, in what situation
              │     resolved by scope, then authority, then recency, with a reason
              ├── care: doses · appointments · rota · rides* · family board
              ├── checkout: /checkout-sessions (UCP shape) · pharmacy*
              └── MCP App: resources/read ui://hearth/card-<hash>.html
                                                    * sandbox providers
```

- **MCP spec 2025-11-25 over Streamable HTTP**, hand-rolled, 13 tools with
  annotations, `structuredContent` on every visual result, and an
  [MCP Apps](https://github.com/modelcontextprotocol/ext-apps) view named in
  `_meta.ui.resourceUri` on both the tool and the result (the Alexa+ docs read
  it from the result, the MCP Apps spec from the tool).
- **OAuth 2.1 authorization code flow with PKCE S256**, both well-known
  documents, and the three places Alexa+ departs from stock MCP: a `401` with
  no `WWW-Authenticate`, both metadata documents required, bearer tokens in the
  query string refused.
- **No model on the read path.** Resolving what is true is a dictionary lookup,
  so every answer fits inside the 500 ms Alexa+ allows. The server's own share
  is stamped on each response in `Server-Timing` (under 1 ms).
- **One household per account**, isolated, persisted to disk.

## Try it

```bash
pip install -r requirements.txt
uvicorn hearth.app:app --port 8000
open http://localhost:8000/alexa        # the simulated Alexa+ client
```

Press **→** to play the scenes, or pick a person and type (or press Mic in
Chrome). The right-hand panel is the live MCP traffic.

**The client is a simulation, and says so on screen.** Alexa+ add-on tooling
is available to select partners only, so it is not open to hackathon
entrants. `/alexa` is a real MCP client standing in for it: it authorises with
PKCE, opens an MCP session per device, lists tools, reads Hearth's MCP App and
hosts it the way an Echo Show would, and calls tools over Streamable HTTP. What
it cannot be is Alexa's language model: a small planner chooses which tool to
call (a configured model taught by Hearth's Agent Skill, or built-in rules;
the header says which), and every word
the assistant says is the text Hearth returned.

Voice: Amazon Polly neural if AWS keys are set, otherwise
[Piper](https://github.com/rhasspy/piper) offline (`pip install -r requirements-sim.txt`,
then set `HEARTH_PIPER_VOICE` to a voice model), otherwise the browser's voice.
See `.env.example`.

**Any MCP client can use it.** `demo/assistant.py` runs Claude Code as the
client, with Hearth's Agent Skill (`skills/hearth-care/SKILL.md`) as its
instructions, against the same server, then reads back the server's record of
what it called.

To reach it from Alexa+ once the toolkit is available to you:

```bash
cloudflared tunnel --url http://localhost:8000
alexa-ai new mcp --name "Hearth" --mcp-server-url https://<tunnel>/mcp
```

## Tests

```bash
for t in tests/test_*.py; do [ "$t" = tests/test_live.py ] || python3 $t; done
python3 tests/test_live.py https://<deployment>    # the same checks over the network
```

160 tests, all green: 62 Alexa+ conformance, 24 care and record, 23 contest
resolution, 18 phrasing, 17 extraction, 9 listing, 6 simulator, and one
interop test in which the **official MCP Python SDK client** (`pip install -r
requirements-dev.txt`) negotiates 2025-11-25 with Hearth over a real socket,
lists the tools, gets the refused dose with its card, and closes its session.
`python3 demo/shots.py http://localhost:8000 shots` plays every scene on the
simulated client in a headless browser and fails on any page error. The suite has
been mutation tested; see [docs/ENGINEERING.md](docs/ENGINEERING.md).

## What is real and what is not

- Real: the MCP server, OAuth, the record, the refusals, the resolution, the
  MCP App, the checkout endpoints, the simulated client's MCP traffic.
- Sandbox: the ride provider and the pharmacy. Nothing books a car or charges a
  card. Both are named "sandbox" wherever they appear.
- Simulated: Alexa+ itself (see above).
- Not a medical device. Hearth enforces the rules the family gives it; it does
  not know pharmacology. The rule extractor without a model key is a small,
  deterministic set of patterns; `HEARTH_LLM_*` plugs in any OpenAI-compatible
  model for the write path.

## More

- [docs/SUBMISSION.md](docs/SUBMISSION.md) — the Devpost copy
- [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) — the video, second by second
- [docs/FRICTION_LOG.md](docs/FRICTION_LOG.md) — building for Alexa+, honestly
- [docs/ENGINEERING.md](docs/ENGINEERING.md) — latency, the record, the bugs that shaped it
- [skills/hearth-care/SKILL.md](skills/hearth-care/SKILL.md) — an Agent Skill that teaches any agent to use Hearth safely

Built for Build, Ship, Shape: the Amazon Developer Hackathon 2026, Alexa+ track.
MIT licence.
