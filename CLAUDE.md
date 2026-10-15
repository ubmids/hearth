# Hearth

`design/DESIGN.md` is binding for anything a family or a judge sees: `/alexa`,
`/console`, the MCP App card, the APL card, the skill icon and carousel, the
README images, the Devpost gallery and thumbnail, and the video cards
(`demo/cards.html`). Change the rule there first if it is wrong.
`design/directions.html` shows the three directions considered.

The chosen direction is C, Pharmacy Label: every answer is drawn as a label.
The five rules most likely to be broken:

1. **Red means "Hearth refused", and nothing else.** The red sticker and red
   row mark only on a refused dose or order, or a refusal reported later. An
   overruled preference is never red. Every sticker is a word, every row mark
   a glyph.
2. **Medicine looks like medicine; the household does not.** Dose cards get
   the solid black medicine header. Handover, list, order, appointments, the
   record and what is true get the outlined household header and the blue
   "For the family" sticker. Yellow is the rule and who set it.
3. **Readable across a kitchen.** On the 768x480 card canvas: title 44 px or
   more, items 22 px or more, nothing under 18 px, no card clips with its
   longest real content. Capitals only on label headers and sticker words.
4. **The family first, the plumbing on request.** No protocol pills or
   monospace outside "Under the hood", label times, the receipt line and the
   tech card. Only token colours (`python3 design/contrast.py`); no gradients,
   glows, shadows on labels, rounded labels or Alexa cyan.
5. **Honest at every size.** "Simulated Alexa+" and "sandbox" stay visible and
   legible on every surface, and no PLACEHOLDER card ships.

Tests must stay green (`for t in tests/test_*.py; do [ "$t" = tests/test_live.py ] || python3 $t; done`
and `python3 skill/tests/test_skill.py`). The `const SCRIPT = [` block in
`alexa.html` and the `x.<key>` reads in `console.html` are parsed by tests.
Commits go out under Subomi's name only, with no co-author or "Generated with"
lines, and `master` and `first-place` move together.
