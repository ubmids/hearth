# Demo video: "Hold on, Rose"

Target **2:45**, hard limit 3:00. Amazon's advice: "Treat your video like a
pitch, not a tutorial… Make the required tool impossible to miss." So the video
opens on the payoff, says "simulated Alexa+" and "MCP" on screen from the first
frame, and shows the protocol traffic once, briefly, at 0:13.

**The hero lands at 0:04 and is over by 0:13.**

## What is on screen

The simulated Alexa+ client at `/alexa?film=1`, full screen. Film mode shows
the device and the conversation at full width, with no scene button and no
persona chips, and keeps the MCP traffic panel off screen until you press
**T**. It labels itself SIMULATED ALEXA+ in the header and on every device frame,
which the rules require.

The header names the planner. Film only when it reads
`planner: model:<id> on Amazon Bedrock + skill:hearth-care` (or another model):
in film mode the page puts up a red "Not ready to film" banner if no model is
configured. The model chooses every tool call, the dose lines included; if the
dose guard ever steps in, the header says `· dose guard`, and that take should
be redone rather than hidden.

Every Alexa line is the text Hearth's tools returned, except the order
confirmation after "Yes, go ahead", which is the host's (the part Alexa+ plays
in checkout), built from the completed checkout session.

## Second by second

Durations are measured at about 2.6 spoken words a second for Alexa and 2.5
for people, against the real lines the server returns today.

| time | picture | sound | on-screen text |
|---|---|---|---|
| **0:00–0:04** | Kitchen Echo Show, idle clock. Rose's line types into the box and sends. | **Rose:** "Alexa, I'm just going to take my blood thinner." (9 words) | lower third: **Simulated Alexa+ · Hearth, an Alexa+ add-on on MCP** |
| **0:04–0:13** | The card turns red: **Already taken today**. Grace gave it 9:10. Ada's rule, once a day. | **Alexa:** "Hold on, Rose. Grace gave you today's warfarin at 9:10 this morning. Your warfarin is once a day, so not another until tomorrow." (23 words) | |
| 0:13–0:20 | Press **T**: the traffic panel slides in on `tools/call give_dose` → `200 · record #n refused`. Press **T** again; it slides out. This is the only time the panel is on screen. | Narrator: "A model on Bedrock chose the tool. Hearth's server refused the dose, and signed it into the record." (17 words) | **The server refused it, not the model** |
| 0:20–0:32 | Subomi on camera, or a title card over the kitchen. | "Sixty-three million Americans care for a family member. Warfarin is in a third of the overdoses that put older Americans in hospital." (22 words) | **63M family caregivers (AARP 2025)** · **warfarin: ⅓ of overdose hospitalisations (NEJM 2011)** |
| 0:32–0:55 | **Tom's Echo Dot** (voice only). | **Tom:** "Alexa, what did I miss with Mom today?" **Alexa:** "Since you last checked in, on Sunday at 7:30 pm, here's what's new. A note from Grace. Mom slept well… Grace gave Mom her warfarin at 9:10 this morning. At 1:40 this afternoon, Mom went to take a second warfarin and I stopped her." (8 + 49 words) | **Memory across sessions and devices** |
| 0:55–1:17 | **Ada's Alexa app.** The card fills, one green tick per step. Then cut to Tom's Echo Dot: its ring pulses yellow. | **Ada:** "Alexa, Mom's cardiology moved to Thursday at 10. Sort it out." **Alexa:** "Done. Mom's cardiology is now Thursday at 10:00 am. Tom is taking Mom, since Tom does Thursdays. I cancelled the old ride, booked a ride for 9:15 am, and left a note for Tom and Grace on the family board and sent it to Tom's phone." (11 + 46 words) | **One request · five steps** · calendar, rota, ride (sandbox), board |
| 1:17–1:22 | A real phone on the table buzzes: the ntfy notification "Hearth: from Ada · Mom's cardiology is now Thursday at 10:00 am…". | (the buzz) | **A real push to Tom's phone** |
| 1:22–1:44 | **Kitchen Echo Show.** Refill card: two green checks, *Paid through Alexa+*, **Pay $12.40**. Then *Simulated Alexa+ checkout*, and *Order placed · sandbox*. | **Grace:** "Alexa, we're nearly out of her warfarin. Reorder it." **Alexa:** "Warfarin 5 mg, 30 tablets, $12.40 from the Hearth sandbox pharmacy, delivered tomorrow. Shall I place the order?" **Grace:** "Yes, go ahead." **Alexa:** "Done. Warfarin 5 mg, 30 tablets is ordered, 12 dollars 40, arriving tomorrow. I've told the family." | **Purchases, the Alexa+ way:** UCP checkout · sandbox pharmacy |
| 1:44–1:56 | Tom's Echo Dot. | **Tom:** "Alexa, can Mom have a coffee?" **Alexa:** "Mom's coffee stops at three. Ada set it 12 days ago, to three. Tom said six, but Ada has the say over what she eats and drinks." (6 + 27 words) | **Who has the say, settled out loud** |
| 1:56–2:12 | **Ada's Alexa app.** The record card: N calls, #n refused in red. | **Ada:** "Alexa, show me the record." **Alexa:** "N calls on the record, 1 refused, and it matches its signed checkpoint and the receipt this device kept: nothing up to call N has been changed or removed." (5 + 28 words) | **Every call signed as it happens · a receipt kept off the server** |
| 2:12–2:30 | Terminal: `scripts/conformance.sh` printing its `PASS` lines, then `curl -i` showing `mcp-protocol-version: 2025-11-25` and `Server-Timing`. | Narrator: "MCP 2025-11-25 over Streamable HTTP, passing the official conformance suite. OAuth 2.1 with PKCE, an MCP App on the Echo Show, and UCP checkout. Any MCP client can use it." (30 words) | **MCP 2025-11-25 · Streamable HTTP · OAuth 2.1 + PKCE · MCP Apps · UCP** |
| 2:30–2:39 | *Optional, if recorded:* Claude Code calling the same server with the `hearth-care` Agent Skill (`demo/assistant.py`), the refusal in its terminal. Otherwise hold the conformance shot. | Narrator: "Here is Claude Code, with Hearth's Agent Skill, hitting the same refusal." (12 words) | **Same server, another assistant** |
| 2:39–2:45 | Back to the red card from 0:04. | Narrator: "Hearth. The memory, and the conscience, of a family caring for someone." | **hearth** · github.com/ubmids/hearth · *Alexa+ is simulated: add-on tools are partner-only* |

Running total: 2:45. If a take runs long, shorten the 0:20 line first, then
drop the optional 2:30 segment. Never cut 0:00–0:20, the sort-it-out push,
the purchase, or the record.

## How to record it

1. **Start the server** with a model planner, the phone push and a scene
   clock in the afternoon (the seed puts Grace's dose at 9:10, so it has to be
   after about 1 pm in `HEARTH_TZ`):

   ```bash
   pip install -r requirements.txt
   export HEARTH_ISSUER=http://localhost:8000 HEARTH_TZ=America/New_York
   export HEARTH_BEDROCK_MODEL=<model or inference profile id> AWS_REGION=us-east-1
   export AWS_BEARER_TOKEN_BEDROCK=<Bedrock API key>
   export HEARTH_NOTIFY_TOM=https://ntfy.sh/<your private topic>
   export HEARTH_RECORD_KEY=<base64url 32-byte seed>   # see .env.example
   uvicorn hearth.app:app --port 8000
   ```

   Voices: with `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` set,
   `HEARTH_TTS=polly` uses Amazon Polly neural voices; otherwise Piper
   (`pip install -r requirements-sim.txt`, `HEARTH_PIPER_VOICE=…onnx`) or the
   browser's voice. Real people reading the four human lines beat any of them.

2. **Subscribe a phone** to the ntfy topic in the ntfy app, and put it on the
   table in shot for 1:17.
3. **Open** `http://localhost:8000/alexa?film=1` in Chrome, full screen. It
   authorises and opens its MCP sessions on load. Check the header reads
   `planner: model:… on Amazon Bedrock` and there is no red banner.
4. **Press →** for each scene: the next line is typed into the box and sent,
   and the model plans it live. Or press **Mic** and say the line. Press **T**
   once at 0:13 to show the traffic, and again to hide it.
5. **Rehearse headless first:** `python3 demo/shots.py http://localhost:8000 shots`
   plays every scene and fails on any page error (needs `playwright`).
6. **Fallback audio:** `demo/hold-on-rose.m4a` is an earlier offline rendering
   (`demo/voice.py`); re-render it before using it, since the record and
   sort-it-out lines have changed.

## Rules this video has to satisfy

- **Says it is simulated.** The header badge and every device label say
  SIMULATED; the closing card says why. Never call it a real Echo.
- **Shows the required technology working**, not just named: the MCP traffic
  at 0:13 and the conformance run at 2:12 are real requests.
- **Under 3:00**, public on YouTube or Vimeo, no copyrighted music.
