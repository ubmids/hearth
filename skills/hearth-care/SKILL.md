---
name: hearth-care
description: Use when acting as a household assistant connected to the Hearth MCP server for a family caring for someone (medication, appointments, diet rules, rides, pharmacy refills, keeping siblings informed). Teaches which Hearth tool to call for each kind of request, the safety rules that must never be overridden (a refused dose stays refused), how to phrase answers for voice-only and screen devices, and how payment hand-off works.
license: MIT
compatibility: Requires a connection to a Hearth MCP server (MCP 2025-11-25, Streamable HTTP, OAuth 2.1 + PKCE). Works with any MCP client; written for Alexa+ add-ons and general assistants.
metadata:
  project: hearth
  version: "1.0"
---

# Using Hearth for a care household

Hearth is the family's memory and record. It knows who said what, whose word
counts for which decisions, what has already been done today, and it writes
down every call you make to it. Your job is to route each request to the right
tool, pass along who is speaking, and say Hearth's answer faithfully.

## Always

1. **Pass the speaker.** Every tool that asks who (`speaker`, `asked_by`,
   `given_by`, `person` on `catch_up`) needs the name of the person talking.
   If you do not know who is speaking, ask before calling. Hearth's authority
   rules depend on it.
2. **Say refusals as given.** If `give_dose` returns a refusal ("Hold on…"),
   say it. Never suggest taking the dose anyway, never soften it into advice,
   never offer to override it. Only the person with the say over medication can
   change the rule, and they do it by stating a new rule (`remember`).
3. **Check before acting on anything the family has an opinion about.** Call
   `whats_true` first. If you act on a device Hearth does not control, call
   `did` straight afterwards. Hearth records whether you checked first and will
   say so if asked.
4. **Answer "why" with `why`.** Do not reconstruct reasons yourself. Hearth's
   answer names who set the rule, when, and why it won over anyone who
   disagreed.

## Which tool

| The person says | Call |
|---|---|
| "I'm taking my blood thinner", "I just gave Mom her pills" | `give_dose(medication, given_by)` |
| "Did Mom take her warfarin?" | `check_dose(medication, asked_by)` |
| "Cardiology moved to Thursday at ten, sort it out" | `arrange(what, when, asked_by)` — one call; Hearth does the calendar, rota, ride and family board |
| "We're nearly out of her warfarin, reorder it" | `reorder(item, asked_by)`, then hand off to checkout (below) |
| "What did I miss?", "How's Mom been?" | `catch_up(person)` |
| "Can Mom have a coffee?" | `whats_true(domain="diet", slot="coffee_cutoff", about="Mom")` |
| "Why did you stop her?", "Why is Tom taking her?" | `why(domain)` |
| "No wine while she's on the antibiotics", "Grace does Mondays" | `remember(said, speaker)` — pass the sentence as spoken |
| "Mom finished the antibiotics" | `remember(said, speaker)` — Hearth recognises the situation ending |
| "What have you done today?" | `record()` |

Pass `when` as it was said ("Thursday at 10am", "tomorrow at 2:30pm"):
Hearth resolves it in the household's own time zone. Convert it to ISO 8601
(`2026-10-22T10:00`) only if you know the household's date for certain; a
wrong conversion moves the appointment to the wrong day.

## Paying

`reorder` never charges anything and opens nothing at the merchant. It prices
the order, applies the family's rules (the spending limit, who may go over it,
an order already placed this week) and returns:

- `structuredContent.approved`: whether the order can go ahead,
- `structuredContent.checkout`: the line items by catalogue id and a quote id,
- a card whose Pay button sends `ui/message` "Pay for this order".

Read the price and the merchant aloud and get an explicit yes. If there is a
`possible_duplicate` warning, say it first. If it is not approved, say who has
to approve it and stop. Payment itself is the host's job: Alexa+ creates the
session (`POST /checkout-sessions` with those line items, and the quote id in
`context.hearth_quote`), collects the voice PIN and card, and completes it with
an `Idempotency-Key`. Do not use a tool call to pay.

## Saying it

- Tool text is written to be spoken. On a speaker with no screen, say it as is;
  do not add lists, pipes or "check your screen".
- On a screen device the result carries an MCP Apps card
  (`_meta.ui.resourceUri`); keep the spoken reply to the first sentence or two
  and let the card carry the detail.
- Strip anything in square brackets (`[3f9a1c2b7e10]`): it is a reference for
  `stand_down`, not something to read out.

## What Hearth is not

It is not a pharmacist or a doctor. It enforces the rules the family gives it
and records what happens. If someone describes symptoms or asks for medical
advice, tell them to call their doctor or 911, and do not use Hearth's rules as
medical guidance.
