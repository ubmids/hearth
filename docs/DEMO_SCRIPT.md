# Demo video: "Hold on, Rose"

Target **2:50**, hard limit 3:00 (judges are not required to watch past it).
Amazon's own advice: "Treat your video like a pitch, not a tutorial… Make the
required tool impossible to miss." So the video opens on the payoff, says
"simulated Alexa+" and "MCP" on screen from the first frame, and shows the
protocol traffic inside the first minute.

**The hero lands at 0:03 and is over by 0:14.** Everything after that explains
it and then goes wider.

## What is on screen

The simulated Alexa+ client at `/alexa`, full screen, 1600×900 or larger. It
labels itself SIMULATED ALEXA+ in the header and on every device frame, which
the rules require. Left half: the device (Kitchen Echo Show, Tom's Echo Dot,
Ada's Alexa app) with Hearth's MCP App card. Right half: the live MCP traffic.

The Alexa lines are Hearth's real answers. Nothing on the Alexa side is
scripted: if the server changed, the video would say something different.

## Second by second

| time | picture | sound | on-screen text |
|---|---|---|---|
| **0:00–0:03** | Echo Show idle, the kitchen clock. Rose's line appears in the transcript. | **Rose:** "Alexa, I'm just going to take my blood thinner." | lower third: **Simulated Alexa+ · Hearth, an Alexa+ add-on on MCP** |
| **0:03–0:14** | The card turns red: **Already taken today**. Grace gave it 9:10. Ada's rule, once a day. | **Alexa:** "Hold on, Rose. Grace gave you today's warfarin at 9:10 this morning. Your warfarin is once a day, so not another until tomorrow." | |
| 0:14–0:20 | Slide the traffic panel into focus: `tools/call give_dose` then `200 · record #1 refused`. | Narrator (Subomi): "That wasn't the language model being careful. Hearth's server refused the dose, from the family's own rule, and wrote the refusal down." | **The server refused it. And recorded it.** |
| 0:20–0:34 | Subomi on camera, 10 seconds, in a real kitchen, Echo or phone in shot. | "Sixty-three million Americans look after a family member. Care for one parent gets split between a daughter with the doctor's letters, a son two states away and a paid aide. Nobody holds the whole picture. Warfarin is involved in a third of the overdoses that put older Americans in hospital." | **63M family caregivers (AARP 2025)** · **warfarin: ⅓ of overdose hospitalisations (NEJM 2011)** |
| 0:34–0:50 | Back to `/alexa`. Device switches to **Tom's Echo Dot** (voice only). | **Tom:** "Alexa, what did I miss with Mom today?" **Alexa:** "Since you last checked in, on Sunday at 7:30 pm: … Grace gave Mom her warfarin at 9:10 this morning. At 1:40 this afternoon, Mom went to take a second warfarin and I stopped her." | **Memory across sessions and devices** |
| 0:50–1:12 | **Ada's Alexa app.** The card fills with five green ticks, one by one. Traffic: a single `tools/call arrange`. | **Ada:** "Alexa, Mom's cardiology moved to Thursday at 10. Sort it out." **Alexa:** "Done. Mom's cardiology is now Thursday at 10 am. Tom is taking Mom, since Tom does Thursdays. I cancelled the old ride, booked a ride for 9:15, and told Tom and Grace on the family board." | **One request · five services** (calendar, rota, rides, board) |
| 1:12–1:36 | **Kitchen Echo Show.** Refill card: two green checks, *Paid through Alexa+*, **Pay $12.40**. Then the traffic: `POST /checkout-sessions` → `…/complete (UCP)` → `completed`. | **Grace:** "Alexa, we're nearly out of her warfarin. Reorder it." **Alexa:** "Warfarin 5 mg, 30 tablets, $12.40 from the Hearth sandbox pharmacy, delivered tomorrow. Shall I place the order?" **Grace:** "Yes, go ahead." **Alexa:** "Done… I've told the family." | **Purchases, the Alexa+ way:** Alexa+ owns payment (UCP checkout) · sandbox pharmacy |
| 1:36–1:50 | Tom asks about coffee. | **Tom:** "Alexa, can Mom have a coffee?" **Alexa:** "Mom's coffee stops at three. Ada set it 12 days ago. Tom said six, but Ada has the say over what she eats and drinks." | **Disagreements, settled out loud** |
| 1:50–2:02 | Ada ends the antibiotics. | **Ada:** "Mom finished the antibiotics." **Alexa:** "Understood, the antibiotics are over. Ada's rule that Mom's alcohol is off limits no longer applies." | **Rules that end by themselves** |
| 2:02–2:16 | **"Alexa, show me the record."** Card: N calls, chain intact, #1 refused in red. Zoom on the traffic panel's `record #n` badges. | **Alexa:** "9 calls on the record, 1 refused, and the chain is intact: nothing has been edited or removed." Narrator: "Every tool call, written by the server as it happens, hash-chained. Not what the assistant says it did." | **An honest record** |
| 2:16–2:30 | Split screen: a terminal running Claude Code with the `hearth-care` Agent Skill, calling the same server (`demo/assistant.py`), its `tools/call` lines scrolling. | Narrator: "Hearth is a standard MCP server, so any assistant can use it. Here's Claude, following Hearth's Agent Skill, on the same household." | **Same server · any MCP client · Agent Skill** |
| 2:30–2:45 | Terminal: `tests/test_conformance.py` scrolling green, then `curl -i` showing `mcp-protocol-version: 2025-11-25` and `Server-Timing`. | Narrator: "MCP 2025-11-25 over Streamable HTTP, OAuth 2.1 with PKCE, and the three places Alexa+ departs from stock MCP, all tested. The server spends under two milliseconds on a call." | **MCP 2025-11-25 · Streamable HTTP · OAuth 2.1 + PKCE · MCP Apps · UCP checkout** |
| 2:45–2:52 | Back to the Echo Show, the red card from 0:03. | Narrator: "Hearth. The memory, and the conscience, of a family caring for someone." | **hearth** · github.com/ubmids/hearth · *Alexa+ is simulated: add-on tools are partner-only* |

If time runs long, cut the coffee scene (1:36–1:50) first, then the
antibiotics. Never cut 0:00–0:20, the purchase, or the record.

## How to record it

1. **Set the scene clock.** The demo is written for an afternoon, after
   Grace's 9:10 dose. Run the server with `HEARTH_TZ` set to a zone where it is
   after about 1 pm. If it is morning there, the seed puts the dose half an
   hour ago instead, which is true but says less.

   ```bash
   pip install -r requirements.txt -r requirements-sim.txt
   HEARTH_ISSUER=http://localhost:8000 HEARTH_TZ=America/New_York \
   HEARTH_PIPER_VOICE=voices/en_US-amy-medium.onnx \
   HEARTH_PIPER_VOICE_ROSE=voices/en_US-kristin-medium.onnx \
   HEARTH_PIPER_VOICE_TOM=voices/en_US-ryan-high.onnx \
   HEARTH_PIPER_VOICE_ADA=voices/en_US-lessac-medium.onnx \
   HEARTH_PIPER_VOICE_GRACE=voices/en_US-hfc_female-medium.onnx \
   uvicorn hearth.app:app --port 8000
   ```

   Voices are from huggingface.co/rhasspy/piper-voices. With AWS keys set
   (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`), Amazon Polly neural voices
   are used instead, which suits an Amazon video better: `HEARTH_TTS=polly`.

2. **Open** `http://localhost:8000/alexa` in Chrome, full screen (F11). It
   authorises and opens its MCP sessions on load; the traffic panel fills.
   Wait for the "Session …" line, then clear nothing: the handshake on the
   right (`/.well-known/…`, `/token`, `initialize`, `tools/list`,
   `resources/read ui://hearth/card-…`) is worth having in shot at 0:14.
3. **Press →** for each scene. The page speaks each line, the person's and
   Alexa's, and lights the device while Alexa talks.
4. **Rehearse first, headless:** `python3 demo/shots.py http://localhost:8000 shots`
   plays all nine scenes, prints what Alexa says and fails on any page error.
5. **Fallback audio:** `demo/hold-on-rose.m4a` is the whole conversation
   rendered offline (`demo/voice.py`), with `demo/hold-on-rose.srt` as
   captions, if screen-recording the page's audio is awkward.
6. **The Claude segment** (2:16): `python3 demo/assistant.py http://localhost:8000`
   with a logged-in `claude` on PATH. It writes `demo/assistant.md`; record the
   terminal while it runs.

## Rules this video has to satisfy

- **Says it is simulated.** The header badge and every device label say
  SIMULATED; the closing card says why. Never call it a real Echo.
- **Shows the required technology working**, not just named: the MCP traffic
  is on screen from 0:14, and every line in it is a real request.
- **Under 3:00**, public on YouTube or Vimeo, no copyrighted music.
- **A real person.** Subomi on camera for ten seconds at 0:20.
