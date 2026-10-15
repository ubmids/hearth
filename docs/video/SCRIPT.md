# Demo video: "Hold on, Rose"

**Target 2:50, hard limit 3:00. The refusal is heard from 0:07 (0:05 with a real voice for Rose) and is over by 0:15.**

The video is built by two scripts, so most of it is already rendered and only
the human parts need a person:

- `demo/film.py` records the simulated Alexa+ run in film mode (the screen,
  every line spoken at its moment, a timeline).
- `demo/rough_cut.py` cuts that take together with the title cards, lower
  thirds and narration. Every piece that needs a real person is a red
  **PLACEHOLDER** card until the real clip is dropped into `inserts/`. Then
  the same command produces the final video.

Marks used below:

- **[PRE]**: pre-rendered by the scripts. Nobody needs to do anything.
- **[VOICE: who]**: a line spoken by a person. Placeholder voices (macOS
  `say`) are in the current cut. Real people are better: the judges' audit
  says synthetic family voices read as "a robot play".
- **[ON CAMERA: who]**: needs a real person filmed.
- **[SUBOMI: screen]**: needs Subomi's own screen or phone recorded.

Alexa's voice stays synthetic on purpose: it is the assistant.

## Second by second

Times are from take 4 (15 Oct, Qwen2.5-VL 7B planning on the laptop,
placeholder voices). Real voices are usually quicker than the placeholders,
which is where the margin under 3:00 comes from. The take 4 cut with every
placeholder in is 2:59.7: `rough_cut.py` prints the real total each time.

| time | what | sound | lower third | who |
|---|---|---|---|---|
| **0:00 to 0:06** | Kitchen Echo Show, simulated, full screen. Rose's line types into the box as she says it. | **Rose:** "Alexa, I'm just going to take my blood thinner." | *Simulated Alexa+ · Hearth, an Alexa+ add-on on MCP 2025-11-25* | [PRE] [VOICE: Rose, an older woman] |
| **0:07 to 0:15** | The card turns red: **Already taken today**. Grace gave it at 9:10. Ada's rule: once a day. | **Alexa:** "Hold on, Rose. Grace gave you today's warfarin at 9:10 this morning. Your warfarin is once a day, so not another until tomorrow." | | [PRE] |
| 0:15 to 0:21 | The MCP traffic panel slides in on `tools/call give_dose`, then out. The only time it is on screen. | **Narrator:** "Over MCP, a model chose give dose. Hearth's server refused it, and signed the refusal into the record." | *MCP traffic, live · The server refused it, not the model* | [PRE] [VOICE: Subomi narrates] |
| 0:20 to 0:34 | **A real person, to camera.** Kitchen or desk, natural light, phone on a stand, head and shoulders. | Subomi, in his own words. If no truer story: "I built Hearth for families splitting the care of a parent: a daughter with the doctor's letters, a son two states away, an aide on weekday mornings. Nobody holds the whole picture. That gap is where doses get doubled." | *63M family caregivers (AARP 2025) · warfarin: 1 in 3 overdose hospitalisations of older adults (NEJM 2011)*, added in the edit | [ON CAMERA: Subomi] (a real carer saying one true sentence is even better) |
| 0:34 to 0:55 | Kitchen Echo Show. Grace's card: **Grace's shift, handed over**, three ticks: shopping list, flagged, family board. | **Grace:** "Alexa, I'm off. Mom ate half her lunch, she was a bit dizzy after her walk, and we're nearly out of Ensure." **Alexa:** "Thanks, Grace. I've left the handover for Ada and Tom on the family board, put Ensure on the shopping list, and flagged one thing for Ada: she was a bit dizzy after her walk. Sent to Ada's and Tom's phones." | *One sentence · The handover, the shopping list, and a flag to the person with the say over Mom's health* | [PRE] [VOICE: Grace] |
| 0:55 to 0:58 | **A real phone on a table buzzes**: the ntfy notification "Hearth: from Grace. Grace flagged at handover: she was a bit dizzy after her walk." | the buzz | *A real push to Ada's phone* | [SUBOMI: phone] |
| 0:58 to 1:20 | Tom's Echo Dot (voice only, the ring was yellow: a note waiting). | **Tom:** "Alexa, what did I miss with Mom today?" **Alexa:** "Since you last checked in, on Tuesday at 7:30 pm, here's what's new. A note from Grace. Mom slept well. Grace gave Mom her warfarin at 9:10 this morning. At 3:07 this afternoon, Mom went to take a second warfarin and I stopped her. Grace handed over: Mom ate half her lunch, she was a bit dizzy after her walk, and we're nearly out of Ensure." | *Memory · Across sessions, people and devices* | [PRE] [VOICE: Tom, Subomi can do this one] |
| 1:20 to 1:41 | Ada's Alexa app. The card fills, one tick per step: calendar, rota, rides, board. | **Ada:** "Alexa, Mom's cardiology moved to Thursday at 10. Sort it out." **Alexa:** "Done. Mom's cardiology is now Thursday at 10:00 am. Tom is taking Mom, since Tom does Thursdays. I cancelled the old ride, booked a ride for 9:15 am, and left a note for Tom and Grace on the family board and sent it to Tom's phone." | *One request · Calendar, rota, ride, family board, phone* | [PRE] [VOICE: Ada] |
| 1:41 to 2:06 | Ada's Alexa app. The refill card, then *Simulated Alexa+ checkout*, then *Order placed · sandbox*. | **Ada:** "Alexa, order what's on the list." **Alexa:** "Ensure Original, 24 bottles, $38.99 from the Hearth sandbox pharmacy, delivered tomorrow. Shall I place the order?" **Ada:** "Yes, go ahead." **Alexa:** "Done. Ensure Original, 24 bottles is ordered, 38 dollars 99, arriving tomorrow. I've told the family." | *The list Grace started · Paid the Alexa+ way: UCP checkout* | [PRE] [VOICE: Ada] |
| 2:06 to 2:16 | **The same server on Amazon's own Alexa**: the developer console's Test tab, Device Display on, typing "I'm just going to take my blood thinner", the red APL card. | (keyboard, then the simulator's voice) | *A classic Alexa skill on Amazon's simulator, calling the same MCP server* | [SUBOMI: screen], steps in `docs/ALEXA_TEST.md` |
| 2:16 to 2:28 | Ada's Alexa app. The record card: 7 calls, #1 refused in red. | **Ada:** "Alexa, show me the record." **Alexa:** "7 calls on the record, 1 refused, and it matches its signed checkpoint and the receipt this device kept: nothing up to call 5 has been changed or removed." | *An honest record · Every call signed as it happens* | [PRE] [VOICE: Ada] |
| 2:28 to 2:40 | The tech card: `scripts/conformance.sh`, six real PASS lines, and badges for OAuth 2.1 + PKCE, MCP Apps, UCP checkout, the Agent Skill and the signed record. | **Narrator:** "MCP 2025-11-25, passing the official conformance suite. And the model choosing every call is a small open one on this laptop. It doesn't need to know warfarin. Hearth does." | | [PRE] [VOICE: Subomi narrates] |
| 2:40 to 2:46 | The close card: **hearth.** · github.com/ubmids/hearth · "Alexa+ is simulated in this video: add-on tools are available to select partners only." | **Narrator:** "Hearth. The memory, and the conscience, of a family caring for someone." | | [PRE] [VOICE: Subomi narrates] |

Running total: about 2:49 with a model planner. `rough_cut.py` prints the
real total and warns over 3:00.

**If it runs long**, cut in this order: the "Mom slept well" note is already
short; then trim the on-camera piece to 10 s; then drop the record scene and
say its line in the tech narration instead (`rough_cut.py --skip=record`). Never cut 0:00 to 0:20, the
handover, the order, or the Amazon console shot.

## Why it is built this way

- **The hero lands inside 10 seconds.** Amazon's advice: "Treat your video like a pitch,
  not a tutorial." The first thing a judge sees is a second blood thinner
  being stopped.
- **MCP traffic in the first 20 seconds, once.** Required tech "impossible to
  miss", but not half the screen for three minutes.
- **A real person at 0:20.** Every past Amazon grand-prize video had one.
- **One household, one afternoon, each scene feeding the next.** Grace's
  handover reaches Tom's catch-up, Ada's phone and the shopping list. Ada then
  orders what Grace put on the list. That is the "multi-service agent with
  memory" the rubric's creative examples describe, shown and not claimed.
- **An Amazon surface.** The classic skill in the developer console simulator
  is the only Amazon-run surface any entrant can reach (Alexa+ add-on tools are
  partner-only), so it gets 10 seconds.
- **Says it is simulated**, in the header, on every device frame, in the
  first lower third and on the close card. The rules require it.

## Recording the human parts

All files go in `~/Desktop/hackathons/hearth-video/`. Shot by shot, with
file names, see `docs/video/SHOTS.md`.
