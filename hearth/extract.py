"""Turning what someone said into a belief.

All the language work happens here, on the write path, and never on the read
path. That split is the whole reason Hearth can answer inside the 500ms round
trip Alexa+ allows: by the time a question arrives, every belief is already
structured as (domain, slot, value), so resolving is a comparison rather than an
inference.

Two implementations, same signature:

  - `llm_extract`   the real one, an OpenAI-compatible chat completion
  - `rule_extract`  a deterministic fallback covering the household domains the
                    demo uses, so the whole system runs, and every test passes,
                    with no key and no network

The fallback is not a mock standing in for the real thing. It is a real, if
narrow, extractor, and it is what runs in CI.
"""
import json
import os
import re

SYSTEM = (
    "You convert a sentence spoken in a household into structured beliefs. "
    "A belief is (domain, slot, value): domain is the thing being governed "
    "(thermostat, shopping, meals, lights, media, security), slot is the "
    "setting within it (target, brand, dinner, bedtime), value is what it was "
    "set to. If the sentence is about one named person rather than the whole "
    "house, set scope to that person's name. If it is only true inside a "
    "situation that will end (a visit, an illness, a cold snap), set context to "
    "a short name for that situation. Ignore small talk. Respond as JSON: "
    '{"beliefs":[{"domain":str,"slot":str,"value":str,"scope":str|null,'
    '"context":str|null}]}'
)

# Deterministic patterns for the fallback. Ordered: first match wins.
RULES = [
    # Specific before general: a sentence naming the thermostat should not be
    # caught by the bare-number rule underneath it.
    (r"\b(?:therm\w*|heat\w*|temperature|degrees?)\b.*?(\d{1,2})\b", "thermostat", "target", 1),
    (r"\bkeep it (?:at|on)\s+(\d{1,2})\b", "thermostat", "target", 1),
    (r"\b(?:switch\w* to|buy|get|use)\s+([A-Z][\w']+)\s+coffee\b", "shopping", "coffee", 1),
    (r"\bcoffee\b.*?\b(?:to|buy|get)\s+([A-Z][\w']+)", "shopping", "coffee", 1),
    (r"\b(?:dinner|eats?|eating)\b.*?\b(\d{1,2}[:.]\d{2})\b", "meals", "dinner", 1),
    (r"\b(?:bed|bedtime|lights out)\b.*?\b(\d{1,2}[:.]\d{2})\b", "lights", "bedtime", 1),
    # Bare imperative. In a house, an unqualified number is almost always the
    # temperature, and the model path handles the cases where it is not.
    (r"\b(?:make it|set it to|put it on|turn it (?:up|down) to)\s+(\d{1,2})\b",
     "thermostat", "target", 1),
]

CONTEXT_HINTS = [
    (r"while ([\w' ]+?) (?:is|are) (?:here|staying|visiting)", "{0}'s visit"),
    (r"until ([\w' ]+?) (?:goes|go) home", "{0}'s visit"),
    (r"\b(cold snap|heatwave|half term|the flu)\b", "the {0}"),
]


def _find_context(text: str) -> str | None:
    for pat, tmpl in CONTEXT_HINTS:
        m = re.search(pat, text, re.I)
        if m:
            return tmpl.format(m.group(1).strip())
    return None


def _find_scope(text: str, member_names: dict) -> str | None:
    """Scope to a person only when the sentence is *about* them, not said by them."""
    for name, mid in member_names.items():
        if re.search(rf"\b(?:for|{name}'s)\s+{name}?\b".replace("  ", " "), text, re.I) \
           or re.search(rf"\bfor {name}\b", text, re.I) \
           or re.search(rf"\b{name}'s\b", text, re.I):
            return mid
    return None


def rule_extract(text: str, member_names: dict | None = None) -> list[dict]:
    member_names = member_names or {}
    out = []
    for pat, domain, slot, group in RULES:
        m = re.search(pat, text, re.I)
        if not m:
            continue
        try:
            value = m.group(group)
        except IndexError:
            continue
        if not value:
            continue
        out.append({
            "domain": domain, "slot": slot, "value": value.strip(),
            "scope": _find_scope(text, member_names),
            "context": _find_context(text),
        })
        break
    return out


def llm_extract(text: str, member_names: dict | None = None) -> list[dict]:
    """Same contract, model-backed. Any OpenAI-compatible endpoint."""
    base = os.getenv("HEARTH_LLM_BASE_URL")
    key = os.getenv("HEARTH_LLM_API_KEY")
    model = os.getenv("HEARTH_LLM_MODEL", "gpt-4o-mini")
    if not (base and key):
        return rule_extract(text, member_names)
    try:
        import httpx
        names = ", ".join(member_names or {}) or "(unknown)"
        r = httpx.post(
            f"{base.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model, "temperature": 0,
                  "response_format": {"type": "json_object"},
                  "messages": [
                      {"role": "system", "content": SYSTEM},
                      {"role": "user",
                       "content": f"Household members: {names}\nSentence: {text}"},
                  ]},
            timeout=10.0,
        )
        r.raise_for_status()
        data = json.loads(r.json()["choices"][0]["message"]["content"])
        beliefs = data.get("beliefs", [])
        # Map person names back to ids; the model answers in names, we store ids.
        for b in beliefs:
            if b.get("scope"):
                b["scope"] = (member_names or {}).get(b["scope"], None)
        return [b for b in beliefs if b.get("domain") and b.get("slot") and b.get("value")]
    except Exception:
        # A write path that fails closed loses what someone just said. Falling
        # back to the deterministic extractor keeps the household working.
        return rule_extract(text, member_names)


def extract(text: str, member_names: dict | None = None) -> list[dict]:
    return llm_extract(text, member_names)


# --- context endings -------------------------------------------------------
# A context that can open but never close is a leak: the belief rides forever
# and the house quietly obeys a rule nobody remembers setting. Detecting the
# ending is the same problem as detecting the opening, and it was missing.

END_PATTERNS = [
    r"\b([\w' ]+?) (?:has |have )?(?:gone|went) home\b",
    r"\b([\w' ]+?)(?:'s)? (?:visit|stay) is over\b",
    r"\bthe (cold snap|heatwave|half term|flu) (?:is|has) (?:over|ended|passed|broken)\b",
    # Captures the weather word so it can be matched against an open context
    # by name: "cold" lands on "the cold snap", and on nothing if none is open.
    r"\b(?:it'?s|it is|its) (?:not |no longer )(cold|hot|warm|freezing) ?(?:any ?more)?\b",
    r"\b([\w' ]+?) (?:is|are) better now\b",
    r"\bstop (?:with )?the ([\w' ]+?)(?: thing)?\b",
]


def detect_context_end(text: str, open_contexts: list[str]) -> str | None:
    """Return the open context this sentence closes, if any.

    Matched against the contexts actually open, not in the abstract: "Gran's
    gone home" should close "Gran's visit" and nothing else, and a sentence that
    names a context nobody opened closes nothing.
    """
    if not open_contexts:
        return None
    low = text.lower()

    # Direct naming first: "the cold snap is over" against context "the cold snap".
    for ctx in open_contexts:
        bare = ctx.lower().removeprefix("the ").removesuffix("'s visit")
        if re.search(rf"\b{re.escape(ctx.lower())}\b.*\b(over|ended|done|finished|passed|broken)\b", low) \
           or re.search(rf"\b{re.escape(bare)}\b.*\b(over|ended|done|finished|passed|broken|gone home)\b", low):
            return ctx

    # Then the patterns, mapping whatever they capture back onto an open context.
    for pat in END_PATTERNS:
        m = re.search(pat, low)
        if not m:
            continue
        subject = (m.group(1) if m.groups() else "").strip()
        for ctx in open_contexts:
            c = ctx.lower()
            if subject and (subject in c or c.removesuffix("'s visit") == subject
                            or c.removeprefix("the ") == subject):
                return ctx
        if not subject and len(open_contexts) == 1:
            return open_contexts[0]
    return None
