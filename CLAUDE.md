# Hearth

`design/DESIGN.md` is binding for anything a family or a judge sees: `/alexa`,
`/console`, the MCP App card, the APL card, the skill icon and carousel, the
README images, the Devpost gallery and thumbnail, and the video cards
(`demo/cards.html`). Change the rule there first if it is wrong.
`design/directions.html` shows the three directions considered.

The five rules most likely to be broken:

1. **Only token colours.** No hex outside the token table; run
   `python3 design/contrast.py` after touching a colour. No gradients, glows,
   Alexa cyan or light-bar decoration.
2. **The stop colour means "Hearth refused" and nothing else.** One alarm per
   screen; every status also has a glyph and a word.
3. **Readable across a kitchen.** On the 768x480 card canvas: title 44 px or
   more, items 22 px or more, nothing under 18 px, and no card clips with its
   longest real content.
4. **The family first, the plumbing on request.** No protocol pills or
   monospace outside "Under the hood", the receipt line and the tech card.
5. **Honest at every size.** "Simulated Alexa+" and "sandbox" stay visible and
   legible on every surface, and no PLACEHOLDER card ships.

Tests must stay green (`for t in tests/test_*.py; do [ "$t" = tests/test_live.py ] || python3 $t; done`
and `python3 skill/tests/test_skill.py`). The `const SCRIPT = [` block in
`alexa.html` and the `x.<key>` reads in `console.html` are parsed by tests.
Commits go out under Subomi's name only, with no co-author or "Generated with"
lines, and `master` and `first-place` move together.
