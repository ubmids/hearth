# Hearth design spec

This file is binding. Any change to a surface a judge or a family sees (the
simulated Alexa+ page, the console, the MCP App card, the APL card, the skill
icon and carousel, the README images, the Devpost gallery, the thumbnail, the
video cards) follows it. If a rule here is wrong, change the rule in this file
first, in the same commit.

Status: Phase 1 (15 Oct 2026). Three directions are in
[`directions.html`](directions.html). The tokens below are **Direction A, Care
Card**, the recommendation. If Subomi picks B or C, replace the Tokens section
with that direction's values from `directions.html`; everything else stands.

## What the judges score

Design is one of four equal criteria (rules section 6):

> "a complete, coherent product experience … Is the interaction model
> intuitive and well-considered for the target device or platform?"

The target devices are a kitchen Echo Show seen from across the room, an Echo
Dot with no screen, and a phone in Ada's hand. Judges "may judge solely on the
text description, images and video", so the gallery, the thumbnail and the
first ten seconds of the video carry as much weight as the live pages.

## Audit, 15 Oct (before)

Screenshots of every surface were taken with headless Chrome against a local
server (`/alexa` all ten scenes, `?film=1`, `/console` at 1600 and 390 px, the
five video card types, and a contact sheet of the take 4 rough cut).

What reads as generic or AI-made today:

1. **Four palettes for one product.** `/alexa` is cool navy with Alexa cyan
   (`#0b0d10`, `#1ec8ff`) and a radial blue glow; the card and the console are
   brown with an orange ember (`#1a1411`, `#ff7a45`); the video cards are navy
   with amber (`#ffc04d`); the skill icon is brown with an orange gradient
   flame. Nothing says these are the same product.
2. **It looks like a developer dashboard.** The first screen's header is six
   monospace pills (`MCP 2025-11-25 · Streamable HTTP`, `OAuth 2.1 + PKCE ✓`,
   `voice: browser voice`, `planner: offline rules`) and half the screen is a
   JSON traffic log. The family, the people this is for, appear only as four
   grey chips at the bottom.
3. **System fonts with no voice.** `ui-sans-serif`, Inter, Helvetica and Menlo,
   with hierarchy made of 11 px uppercase grey labels. Nothing is written for
   older eyes or for a speaker three metres away.
4. **Devices are drawn wrong.** Ada's phone is drawn as a landscape Echo Show
   frame. The Echo Dot is a grey gradient blob. The Echo Show light bar is a
   blue gradient, which is Amazon's device language worn as decoration.
5. **Cards clip.** On the 768x480 canvas the record card cuts its third entry
   in half and the "Sorted" footer runs into the receipt pill. The record card
   shows tool names (`whats_true`, `checkout.complete`) to a family.
6. **Film mode is half empty.** The device sits in the left 45 % of a 1920 px
   frame; Alexa's replies are flung to the far right, so the eye ping-pongs
   and the right half is dead space for three minutes.
7. **Text below contrast.** `/alexa` dim text `#5f6b78` on `#11151a` is 3.37:1
   and the console's section labels `#6f5f54` on `#14100e` are 3.10:1, both
   under the 4.5:1 AA minimum, at 11 to 12 px.
8. **Rounded bordered boxes everywhere**: every log line, every rule, every
   device button, every stat on the video cards is a rounded rectangle with a
   1 px border. Pills on top of boxes on top of panels.
9. **Stale and placeholder copy.** The console says Mom "has the say over the
   thermostat"; the skill carousel still tells the old thermostat story ("Dad:
   turn it up to 24"); the console strap is a different tagline from the
   README; the wordmark is "Hearth." on one page and "hearth." on another;
   "1× daily" and "9:00am" are developer formats; three red PLACEHOLDER cards
   sit in the rough cut.
10. **Phone width is broken.** `/alexa` at 390 px stacks the traffic log over
    the device and wraps header pills into three-line blobs.

What is good and stays: the card content model (eyebrow, title, body, up to
four items with a status, footer, receipt), the plain sentences Hearth speaks,
the honest "Simulated Alexa+" labelling, the one-red-card refusal as the hero.

## Principles

Each one has a test. A surface that fails a test is not done.

1. **Readable from across the kitchen.** The Echo Show card is read at two to
   three metres by an 84-year-old. *Test:* on the 768x480 canvas, title is at
   least 44 px, item text at least 22 px, nothing below 18 px; no card clips
   at 768x480 with its longest real content (record, sort it out).
2. **Who, then what, then why.** Every card and every board note names the
   person: who did it, whose rule it was, who has the say. *Test:* each card in
   the ten scenes names at least one family member; no card shows a tool name,
   a snake_case word or a bare hash above the footer.
3. **Calm by default, one alarm.** The stop colour means one thing, "Hearth
   refused", and nothing else uses it. *Test:* the stop colour appears on at
   most one element group per screen (the stop card and its spoken line); no
   looping animation except the device light while speaking; motion honours
   `prefers-reduced-motion`.
4. **One product, one palette.** Sim, console, MCP App card, APL card, icon,
   README images, gallery, video cards and thumbnail all draw from the tokens
   below. *Test:* `grep -oE '#[0-9a-fA-F]{6}'` over `hearth/web`, `demo/cards.html`,
   `skill/lambda/apl.py` and `assets/src` finds only token values.
5. **The family first, the plumbing on request.** Protocol detail is real and
   judges want it, but it is the second layer. *Test:* the first screen of
   `/alexa` shows the household and the device; the MCP traffic is one click
   (or `T`) away and labelled "Under the hood"; no monospace text outside the
   traffic panel, the receipt line and the tech card.
6. **Devices look like their devices.** Echo Show landscape 16:10 with a
   speaker bar, Echo Dot as a fabric puck with a light ring, Alexa app as a
   portrait phone. *Test:* Ada's scenes render in a portrait frame; the Dot
   shows its ring state (idle, listening, speaking, note waiting).
7. **Honest at every size.** The simulation and the sandboxes are named on
   every surface, legibly. *Test:* "Simulated Alexa+" is visible in every
   screenshot, every gallery image and every video frame of the sim, at 4.5:1
   or better; "sandbox" appears beside every ride and pharmacy result.

## Reference board

| Product | Take | Avoid |
|---|---|---|
| NHS.UK care cards (non-urgent, urgent, emergency) | A three-level tone system that a frightened reader understands without colour: a heading word plus a band. Plain verbs. | The institutional blue and the form-heavy layout. |
| GOV.UK Design System | Type-led hierarchy, 19 px minimum body, "warning text" with an icon and a bold first word, every colour at AA. | Austerity: Hearth is in a home, not a tax office. |
| Apple Health, Medications | The dose log: "Taken 9:10 AM", a schedule in words, a calm list where the time is the headline. | Tiny pastel pill icons and the hidden-in-a-tab navigation. |
| Atkinson Hyperlegible (Braille Institute) | A typeface designed for low-vision readers; distinct `I l 1` and `0 O` matter for doses and times. | Using it for every role: pair it with a serif for human words. |
| Google Nest Hub, ambient and photo frame | Glanceable at distance, full-bleed, one fact per screen, warm at night. | Photo wallpaper behind text. |
| Amazon Echo Show home and APL guidance | The 16:10 canvas, safe margins, big touch targets, voice first and screen second. | Alexa cyan and the light-bar gradient: that is Amazon's brand, not ours. |
| CaringBridge | The family-update journal tone: short notes, who wrote them, when. | Its dated web layout and donation chrome. |
| Lotsa Helping Hands / Caring Village | The care rota as a shared calendar: "Tom does Thursdays". | Clutter: a dozen modules on one screen. |
| Things 3 | Quiet check marks, generous rows, hierarchy from weight not boxes. | Its productivity framing. |
| Stripe receipts | The record as a receipt: the human line first, the identifier in small print at the foot. | Monospace everywhere. |
| Withings Health Mate | Health data that does not shout; one accent per metric. | Gamified streaks. |
| Pharmacy auxiliary labels ("Take once a day") | A real, familiar object for medicine rules; Direction C is built on it. | Novelty: in A and B it stays a reference, not a costume. |

## Tokens (Direction A, Care Card)

### Colour

Contrast is computed with the WCAG 2.1 relative-luminance formula
(`design/contrast.py` reproduces every number). AA is 4.5:1 for text, 3:1 for
large text and UI boundaries.

| Token | Light | Dark | Use | Contrast (light / dark) |
|---|---|---|---|---|
| `--bg` | `#F4F5F1` | `#101412` | page | |
| `--surface` | `#FFFFFF` | `#171D1A` | cards, device screen | |
| `--sunk` | `#E9ECE5` | `#0B0E0D` | wells, the traffic panel | |
| `--line` | `#D3D8CF` | `#2A332E` | dividers only (decorative) | 1.45 / 1.31 |
| `--line-strong` | `#6B7770` | `#5F6D66` | input and button borders | 4.26 on bg / 3.42 on bg |
| `--ink` | `#16201B` | `#EDF1EE` | text | 16.71 / 15.01 on surface |
| `--ink-2` | `#46524B` | `#B4BFB8` | secondary text | 8.17 / 9.03 |
| `--ink-3` | `#5F6B64` | `#8F9B94` | meta, timestamps (the floor) | 5.56 / 5.94 |
| `--care` | `#1D5C47` | `#7CC9A5` | brand, done, primary action | 7.85 / 8.76 |
| `--care-tint` | `#E1EFE7` | `#16302A` | done band background | care on it 6.62 / 7.22 |
| `--on-care` | `#FFFFFF` | `#0B1A13` | text on a care button | 7.85 / 9.18 |
| `--stop` | `#B42318` | `#FF8C7E` | refused, and only refused | 6.57 / 7.58 |
| `--stop-tint` | `#FCEBE8` | `#3A1814` | stop band background | stop on it 5.69 / 7.05 |
| `--caution` | `#7A4A00` | `#F0C25A` | flagged, needs attention, "Simulated" | 7.48 / 10.24 |
| `--caution-tint` | `#FFF0C7` | `#33280E` | caution band background | caution on it 6.61 / 8.66 |

No other hex value appears in product code. Status is never colour alone:
every status carries a glyph (check, cross, exclamation, dot) and a word.

### Type

Google Fonts, three families, all chosen for this audience:

- **Atkinson Hyperlegible Next** (400, 600, 700): every UI word, every card,
  the video captions. Built by the Braille Institute for low-vision readers;
  its `1`, `l` and `I` and its `0` and `O` cannot be confused, which matters
  when the content is "9:10" and "once a day".
- **Newsreader** italic (400, opsz 6..72): only for words a person said, the
  quoted rule ("Dr. Patel says Mom takes one warfarin a day") and the lines in
  the conversation. It makes the human voice visibly different from Hearth's.
- **Atkinson Hyperlegible Mono** (400): only the traffic panel, the receipt
  line and the tech card.

Scale (ratio 1.25, px):

| Step | Web | Echo Show card (768x480) | Video (1920x1080) |
|---|---|---|---|
| caption | 14 | 18 | 28 |
| meta | 15 | 18 | 32 |
| body | 17 | 22 | 40 |
| lead | 20 | 26 | 48 |
| title | 28 | 44 | 72 |
| display | 40 | 56 | 104 |

Line height 1.4 for body, 1.1 for titles. Letter-spacing 0 except eyebrows
(+0.06em, 600, sentence case, not all caps).

### Spacing, radius, motion

- Spacing: 4 px base: 4, 8, 12, 16, 24, 32, 48, 64. Card padding on the Echo
  Show canvas 32 px; web cards 24 px; section gaps 48 px.
- Radius: 0 for the card on a device (it is the screen), 6 for buttons and
  inputs, 10 for web surfaces, and real device radii for device frames only.
  No pills except the one "Simulated Alexa+" label.
- Motion: 160 ms ease-out for state, 240 ms fade and 8 px rise for a new card,
  items arriving 60 ms apart. The device light is the only loop. All of it off
  under `prefers-reduced-motion: reduce`.

## Inventory

Screens:

- `/alexa`: household strip (four people, where each is, who has the say),
  device stage (Echo Show, Echo Dot, Alexa app), conversation, say bar, scene
  stepper, "Under the hood" drawer (the MCP traffic). `?film=1` is the same
  page with the stepper and chips hidden and the stage centred.
- `/console`: the household board: who lives here and who has the say, what
  stands now, open situations, the family board, what Hearth did and why,
  everything ever said, the say box.
- `card.html` (MCP App, Card and List patterns, Pay button) and its twin
  `skill/lambda/apl.py` (APL): the same layout, the same tokens.
- `/privacy`, `/terms` (`_page` in `hearth/app.py`).
- Skill icon (`assets/src/icon.svg` and PNGs) and carousel
  (`assets/src/carousel.svg`, still the thermostat story: rewrite).

Components: status mark; card; list row; person (initial, name, role, "has the
say over"); rule (what, value, who set it, when, why it won); quote; board
note; record entry (number, time, human action, outcome, receipt in small
print); device frames; Simulated label; say bar; buttons (primary, secondary,
quiet); lower third; title card; end card.

Phase 2 constraints found in the tests: `tests/test_sim.py` and
`skill/tests/test_skill.py` parse the `const SCRIPT = [` block in `alexa.html`
(keep its format); `tests/test_phrasing.py` requires `x.title`, `x.reading`,
`x.verdict.chip`, `x.verdict.line` and friends in `console.html`;
`skill/tests/test_skill.py` asserts the APL stop colour is `#ff6b4a`, so
changing that colour means updating that assertion in the same commit. Card
titles and items come from the server and are covered by tests: restyle them,
do not reword them in Phase 2 unless the test moves with them.

## Submission assets

- **Thumbnail** (Devpost, 3:2, 1500x1000, PNG): the Echo Show with the stop
  card, the words "Hold on, Rose." and the wordmark. Nothing else. *Test:*
  downscaled to 300 px wide, "Hold on, Rose." is readable and the red
  "Stopped" band on the device is recognisable.
- **Gallery** (3:2, 1500x1000, six images, same frame on each): 1 the refusal,
  2 the handover, 3 Tom's catch-up on the Dot, 4 "sort it out" on Ada's phone,
  5 the order, 6 under the hood (traffic plus conformance). Each has one
  sentence of caption at the top in `--ink` on `--bg`, the device below, the
  Simulated label in frame. No collages, no device mock-ups from stock.
- **README hero**: image 1 of the gallery. Alt text says what it shows.
- **Video title cards**: `--bg` background, the wordmark top left, one line of
  at most eight words at display size, optional one-line sub at lead size. No
  boxes around statistics: the number at display size, the source in caption.
- **Lower thirds**: bottom left, inside a 96 px safe margin, `--surface` with
  a 6 px left band in the scene's tone, at most two lines, on screen at least
  four seconds, never over the card.
- **Captions** (burned in): Atkinson Hyperlegible Next 40 px, `--ink` on a
  `--surface` scrim at 92 %, bottom centre, at most two lines of 42 characters.
- **End card**: wordmark, tagline, repo URL, the simulation note at caption
  size, held four seconds.
- **Tech card**: the one place the terminal look is allowed; it uses the
  tokens' mono and colours, not a black terminal.
- **Placeholder cards never ship.** `rough_cut.py` refuses a final render while
  any placeholder remains, or the cut is not final.

## Do and don't

Do:

- write the person's name before the action ("Grace gave it at 9:10");
- use words for times and frequencies ("once a day", "9:10 this morning");
- keep one idea per card and at most four rows;
- put the receipt and hash in the footer at caption size;
- test every surface at 390 px, at 768x480 and at 1920x1080.

Don't:

- use Alexa cyan, a light-bar gradient or any Amazon logo as decoration;
- use emoji, gradients, glows, glass blur or radial background washes;
- wrap things in rounded bordered boxes to make them look designed;
- put protocol words on the first screen outside "Under the hood";
- use the stop colour for anything that is not a refusal;
- ship a PLACEHOLDER card, a thermostat, or "Lorem";
- centre body text, or set anything a family reads under 14 px on the web.
