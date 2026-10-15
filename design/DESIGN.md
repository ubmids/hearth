# Hearth design spec

This file is binding. Any change to a surface a judge or a family sees (the
simulated Alexa+ page, the console, the MCP App card, the APL card, the skill
icon and carousel, the README images, the Devpost gallery, the thumbnail, the
video cards) follows it. If a rule here is wrong, change the rule in this file
first, in the same commit.

**Chosen direction: C, Pharmacy Label** (Subomi, 15 Oct 2026). The three
directions considered are in [`directions.html`](directions.html). C is
adjusted for the three risks flagged there: capitals only on short label
headers and sticker words, a household label for scenes that are not
medicine, and an order of work that puts the Echo Show card first.

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

1. **Every card is a label.** Hearth's answers are drawn the way a family
   already reads instructions about care: a header, facts in ruled rows, one
   sticker that says what matters. *Test:* every card in the ten scenes has a
   label header, rows separated by rules, and at most one sticker in the
   header area.
2. **Red means "Hearth refused", and nothing else.** The red sticker and the
   red row mark appear only on a refused dose, a refused order, or a refusal
   reported in a catch-up or the record. *Test:* in the ten scenes, red
   appears in scene 1 (the dose), and in the catch-up and record rows that
   report it; nowhere else. An overruled preference is not a refusal and is
   never red.
3. **Medicine looks like medicine; the household does not.** Dose cards use
   the medicine label (solid black header, "For Mom", the drug name). The
   handover, the list, the order, appointments, the record and what is true
   use the household label (outlined header, blue "For the family" sticker).
   *Test:* no non-dose card has a solid black header; no dose card has a blue
   sticker.
4. **Readable across a kitchen, and by an 84-year-old.** Sentence case for
   titles, facts and body; capitals only for label headers (at most four
   words) and sticker words (at most three). *Test:* on the 768x480 canvas the
   title is 44 px or more, item text 22 px or more, nothing under 18 px; no
   card clips with its longest real content (the record, "sort it out").
5. **The family first, the plumbing on request.** Protocol detail is the
   second layer. *Test:* the first screen of `/alexa` shows the four people
   and the device; the MCP traffic sits behind "Under the hood" (button or
   `T`); no monospace outside the traffic panel, times on a label, the
   receipt line and the tech card.
6. **Devices look like their devices.** Echo Show landscape 16:10, Echo Dot
   as a puck with a ring, Alexa app as a portrait phone. *Test:* Ada's scenes
   render in a portrait frame; the Dot shows idle, speaking and note-waiting.
7. **Honest at every size.** *Test:* "Simulated Alexa+" is visible in every
   sim screenshot, gallery image and sim video frame, at 4.5:1 or better;
   "sandbox" appears beside every ride and pharmacy result.

## The label grammar

Two labels, one system. Same paper, same rules, same type, same row layout.

| | Medicine label | Household label |
|---|---|---|
| Used for | a dose given, checked or refused; "which medicine?"; a medicine with no rule | handover, shopping list, order, appointments ("sorted"), catch-up, the record, what is true, why |
| Header | solid `--rule` bar, `--paper` text: `HEARTH · FOR MOM` left, the drug name right | outlined: `--rule` text on `--paper`, 3 px rule under it: `HEARTH · HOUSEHOLD` left, the card's own header right (`HANDOVER`, `SORTED`, `SHOPPING LIST`, `THE RECORD`) |
| Frame | 3 px `--rule` border all round | 3 px `--rule` border all round |
| Sticker in the header area | red `STOPPED` on a refusal; green `LOGGED` / `TAKEN TODAY`; outlined `CHECK FIRST` when there is no rule | blue `FOR THE FAMILY`; outlined `NEEDS ADA` (the person who decides) when something is flagged; red `REFUSED` only on a refused order |
| Rule chip | yellow `RULE · ADA`: the rule and who set it | yellow `ADA'S RULE` when a preference is in force |

Stickers:

| Sticker | Colour | Means | Never |
|---|---|---|---|
| Red | `--red` on `--on-red` | Hearth refused it | anything else, including a broken record (that is outlined `CHECK FAILED`) |
| Yellow | `--yellow`, `--on-yellow` text | the rule, and who set it | warnings |
| Blue | `--blue`, `--on-blue` text | for the family: a note, a plan, a purchase | medicine |
| Green | `--green`, `--on-green` text | done, logged, paid | a refusal |
| Outlined | `--rule` border, `--ink` text | needs a person: who decides, or check first | decoration |

Row marks (the square at the start of each row): green check for done, red
cross for a refusal, outlined exclamation for needs attention, outlined dot
for information, struck-through text (no colour) for a preference that was
overruled.

## Reference board

| Product | Take | Avoid |
|---|---|---|
| US prescription labels and auxiliary warning stickers | The whole system: a black header, heavy rules, facts in rows, a coloured sticker that says one thing. Every carer already reads these under stress. | Capitals for everything, and the tiny print. |
| USPS and FedEx shipping labels | A label for things that are not medicine: the same rules and grid, a different header. The model for the household label. | Barcodes as decoration. |
| NHS.UK care cards (non-urgent, urgent, emergency) | A three-level tone system that a frightened reader understands without colour: a heading word plus a band. Plain verbs. | The institutional blue and the form-heavy layout. |
| GOV.UK Design System | Type-led hierarchy, 19 px minimum body, "warning text" with an icon and a bold first word, every colour at AA. | Austerity: Hearth is in a home, not a tax office. |
| Apple Health, Medications | The dose log: "Taken 9:10 AM", a schedule in words, a calm list where the time is the headline. | Tiny pastel pill icons and the hidden-in-a-tab navigation. |
| IBM Plex Sans Condensed and Plex Mono | Condensed fits a label's long facts at a large size; Plex Mono's slashed zero keeps 9:10 and 10:00 apart. | Light weights: nothing under 400. |
| Google Nest Hub, ambient and photo frame | Glanceable at distance, full-bleed, one fact per screen, warm at night. | Photo wallpaper behind text. |
| Amazon Echo Show home and APL guidance | The 16:10 canvas, safe margins, big touch targets, voice first and screen second. | Alexa cyan and the light-bar gradient: that is Amazon's brand, not ours. |
| CaringBridge | The family-update journal tone: short notes, who wrote them, when. | Its dated web layout and donation chrome. |
| Lotsa Helping Hands / Caring Village | The care rota as a shared calendar: "Tom does Thursdays". | Clutter: a dozen modules on one screen. |
| Things 3 | Quiet check marks, generous rows, hierarchy from weight not boxes. | Its productivity framing. |
| Stripe receipts | The record as a receipt: the human line first, the identifier in small print at the foot. | Monospace everywhere. |
| Withings Health Mate | Health data that does not shout; one accent per metric. | Gamified streaks. |

## Tokens (Direction C, Pharmacy Label)

### Colour

Contrast is computed with the WCAG 2.1 relative-luminance formula
(`python3 design/contrast.py` reproduces every number and exits non-zero on a
failure). AA is 4.5:1 for text, 3:1 for large text and UI boundaries.

| Token | Light | Dark | Use | Contrast (light / dark) |
|---|---|---|---|---|
| `--desk` | `#ECECE7` | `#0B0B0B` | page background, what a label sits on | ink on it 16.61 / 18.00 |
| `--paper` | `#FFFFFF` | `#161616` | the label | |
| `--line` | `#D2D2CB` | `#34342F` | page dividers only (decorative) | 1.52 / 1.45 |
| `--rule` | `#111111` | `#EDEDE8` | label borders, row rules, the medicine header | 18.88 / 15.41 |
| `--ink` | `#0B0B0B` | `#F5F5F0` | text | 19.68 / 16.55 |
| `--ink-2` | `#3A3A3A` | `#C8C8C2` | secondary text | 11.37 / 10.77 |
| `--ink-3` | `#595954` | `#A0A09A` | meta, timestamps (the floor) | 7.04 / 6.88 on paper, 5.94 / 7.49 on desk |
| `--red` | `#C8201A` | `#FF5A4E` | refused, and only refused | 5.71 / 5.88 on paper |
| `--on-red` | `#FFFFFF` | `#140303` | text on red | 5.71 / 6.54 |
| `--red-tint` | `#FCE9E7` | `#3A1411` | the refused row's background | red on it 4.88 / 5.30 |
| `--yellow` | `#FFD43B` | `#FFD43B` | the rule chip (background only) | on-yellow 13.81 / 13.81 |
| `--on-yellow` | `#0B0B0B` | `#0B0B0B` | text on yellow | |
| `--blue` | `#1F4FB5` | `#8DB0FF` | "for the family" | 7.38 / 8.43 on paper |
| `--on-blue` | `#FFFFFF` | `#0B0B0B` | text on blue | 7.38 / 9.17 |
| `--blue-tint` | `#E6EDFA` | `#16213A` | household highlight rows | blue on it 6.28 / 7.46 |
| `--green` | `#006B47` | `#4FD19A` | done, logged, paid | 6.57 / 9.41 on paper |
| `--on-green` | `#FFFFFF` | `#04140D` | text on green | 6.57 / 9.83 |
| `--green-tint` | `#E2F2EA` | `#0F2A1F` | | green on it 5.67 / 7.96 |

Yellow is never text and never a boundary on its own: it is always a filled
chip with `--on-yellow` text. No other hex value appears in product code.
Status is never colour alone: every sticker is a word, every row mark a glyph.

The product pages are light. The MCP App card also has the dark set, used
when the host asks for a dark theme.

### Type

Google Fonts, two families (the APL card uses Amazon Ember, the device font,
at the same sizes and weights):

- **IBM Plex Sans Condensed** (400, 500, 600, 700): every word on a label,
  every page, the video cards. Condensed lets a long fact ("Booked a ride at
  9:15 am, 45 minutes before") stay on one line at 22 px.
- **IBM Plex Mono** (400, 600): times and doses on a label (`9:10 am`), the
  receipt line, the traffic panel, the tech card.

Capitals: label headers (four words at most), sticker words (three at most),
nothing else. Titles, facts and body are sentence case.

Scale (px):

| Step | Web | Echo Show card (768x480) | Video (1920x1080) |
|---|---|---|---|
| header and sticker (caps, 600, +0.06em) | 13 | 18 | 28 |
| meta | 15 | 18 | 30 |
| body and row text | 17 | 22 | 40 |
| lead | 20 | 26 | 48 |
| title (700) | 30 | 46 | 80 |
| display (700) | 44 | 56 | 120 |

Line height 1.3 for row text, 1.05 for titles.

### Spacing, radius, motion

- Spacing: 4 px base: 4, 8, 12, 16, 24, 32, 48, 64. Label padding on the
  768x480 canvas 24 px; rows 10 px top and bottom.
- Radius: 0 for labels, stickers and buttons. Only device frames are rounded.
- Rules: 3 px label border, 2 px row rules on the device, 1.5 px on the web.
- Motion: 160 ms ease-out for state, 220 ms for a new label (fade, 6 px rise),
  rows arrive 50 ms apart. The device ring is the only loop. All of it off
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
- Skill icon (`assets/src/icon.svg`) and carousel (`assets/src/carousel.html`),
  rendered to `hearth/web/assets/` by `assets/src/render.py`.
- Devpost thumbnail and gallery, README hero: `docs/img/`, made from the real
  scenes by `demo/gallery.py`.

Components: medicine label; household label; stickers (red, yellow, blue,
green, outlined); row mark; list row; person (initial, name, role, "has the
say over"); rule (what, value, who set it, when, why it won); quote; board
note; record entry (number, time, human action, outcome, receipt in small
print); device frames; Simulated label; say bar; buttons (primary, secondary,
quiet); lower third; title card; end card.

Phase 2 constraints found in the tests: `tests/test_sim.py` and
`skill/tests/test_skill.py` parse the `const SCRIPT = [` block in `alexa.html`
(keep its format); `tests/test_phrasing.py` requires `x.title`, `x.reading`,
`x.verdict.chip`, `x.verdict.line` and friends in `console.html`;
`skill/tests/test_skill.py` asserts the APL stop colour, so a change to
`--red` moves that assertion in the same commit. Card
titles and items come from the server and are covered by tests: restyle them,
do not reword them in Phase 2 unless the test moves with them.

## Submission assets

- **Thumbnail** (Devpost, 3:2, 1500x1000, PNG): a medicine label reading
  "Hold on, Rose." with the red STOPPED sticker, the Echo Show beside it, and
  the wordmark. Nothing else. *Test:* downscaled to 300 px wide, "Hold on,
  Rose." is readable and the red STOPPED sticker is recognisable.
- **Gallery** (3:2, 1500x1000, six images, same frame on each): 1 the refusal,
  2 the handover, 3 Tom's catch-up on the Dot, 4 "sort it out" on Ada's phone,
  5 the order, 6 under the hood (traffic plus conformance). Each has one
  sentence of caption at the top in `--ink` on `--desk`, the device below, the
  Simulated label in frame. No collages, no device mock-ups from stock.
- **README hero**: image 1 of the gallery. Alt text says what it shows.
- **Video title cards**: `--desk` background with one household label on it,
  the wordmark in the label header, one line of at most eight words at display
  size, optional one-line sub at lead size. Statistics are rows on a label:
  the number at display size, the source as meta.
- **Lower thirds**: a small household label, bottom left inside a 96 px safe
  margin: a caps header and at most two sentence-case lines, on screen at
  least four seconds, never over the card.
- **Captions** (burned in): IBM Plex Sans Condensed 40 px, `--ink` on a
  `--paper` scrim at 92 %, bottom centre, at most two lines of 42 characters.
- **End card**: wordmark, tagline, repo URL, the simulation note at caption
  size, held four seconds.
- **Tech card**: the one place the terminal look is allowed; Plex Mono on a
  household label, not a black terminal.
- **Placeholder cards never ship.** `rough_cut.py` refuses a final render while
  any placeholder remains, or the cut is not final.

## Do and don't

Do:

- write the person's name before the action ("Grace gave it at 9:10");
- use words for times and frequencies ("once a day", "9:10 this morning");
- keep one idea per card and at most four rows;
- put the receipt and hash in the footer, in Plex Mono at meta size;
- test every surface at 390 px, at 768x480 and at 1920x1080.

Don't:

- use Alexa cyan, a light-bar gradient or any Amazon logo as decoration;
- use emoji, gradients, glows, glass blur, shadows on labels or radial washes;
- round a label, a sticker or a button;
- set a title or a fact in capitals;
- put a blue sticker on medicine, or a black medicine header on anything else;
- put protocol words on the first screen outside "Under the hood";
- use red for anything that is not a refusal;
- ship a PLACEHOLDER card, a thermostat, or "Lorem";
- centre body text, or set anything a family reads under 14 px on the web.
