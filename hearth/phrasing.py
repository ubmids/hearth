"""Saying a belief the way the household would say it.

(domain, slot, value) is how Hearth thinks, and it has to stay that way: it is
what makes a contest a dictionary lookup instead of an inference, which is what
keeps the read path inside the 500ms Alexa+ allows. What it must not do is reach
the surface. No house has a `meals.dinner` of `17:00`. It has dinner at five,
and an interface that shows the first is showing people the inside of a machine
they never asked to see.

This sits beside the resolver rather than in the page for exactly the reason the
resolution itself does (see `_state` in app.py): the console has to say what
Alexa+ would be told, and a second rendering written in JavaScript would drift
from this one and end up quietly disagreeing with it on camera.

Everything here degrades. A household can name a domain anything it likes, so
every lookup falls through to a phrasing built from the words it was handed, and
nothing in this file raises on a domain it has never seen. Teaching Hearth to
say a new setting well is one line in SETTINGS; saying it passably takes none.
"""
import re

# How a value is read out. The unit is a property of the setting, not of the
# string: "19" is degrees under the thermostat and a volume under the speakers,
# and only the household knows which.
DEGREES = "degrees"
TIME = "time"
PLAIN = "plain"

# (domain, slot) -> (subject, verb, unit).
#
# `{whose}` in a subject is filled with a possessive: the member the belief is
# about, else the tail of a dotted domain, else "the". That is what lets one
# line cover bedroom.ada, bedroom.sam and a bedroom nobody has claimed.
SETTINGS = {
    ("thermostat", "target"): ("the thermostat", "is set to", DEGREES),
    ("thermostat", "night"): ("the thermostat overnight", "is set to", DEGREES),
    ("meals", "dinner"): ("dinner", "is at", TIME),
    ("meals", "lunch"): ("lunch", "is at", TIME),
    ("meals", "breakfast"): ("breakfast", "is at", TIME),
    ("lights", "bedtime"): ("lights out", "is at", TIME),
    ("lights", "brightness"): ("the lights", "are set to", PLAIN),
    ("shopping", "coffee"): ("the coffee", "is", PLAIN),
    ("shopping", "milk"): ("the milk", "is", PLAIN),
    ("media", "volume"): ("the volume", "is set to", PLAIN),
    ("bedroom", "lights"): ("{whose} bedroom lights", "are", PLAIN),
    ("bedroom", "bedtime"): ("{whose} bedtime", "is at", TIME),
}

# What a member has the say over, for the people panel. Grants name a domain
# with no slot, so they need their own phrasing rather than a subject.
DOMAIN_LABELS = {
    "thermostat": "the thermostat",
    "shopping": "the shopping",
    "meals": "mealtimes",
    "lights": "the lights",
    "media": "what plays",
    "security": "the locks and alarm",
}

_NUMBER = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
           7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven",
           12: "twelve"}


def possessive(name: str) -> str:
    """Ada's, Dad's, Gus'. Public because the console's replies need it too."""
    return f"{name}'" if name.endswith("s") else f"{name}'s"


def _clock(value: str):
    """(hour, minute) if this value is a time of day, else None."""
    m = re.fullmatch(r"\s*(\d{1,2})[:.](\d{2})\s*", str(value))
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    return (h, mi) if h < 24 and mi < 60 else None


def _spoken_clock(h: int, mi: int) -> str:
    """Five, half past five, quarter to nine. Anything else stays on the dial.

    Written-out minutes past the hour read worse than the digits do once they
    stop landing on a quarter, so "twenty-three minutes past seven" is not an
    improvement on 7:23 and this deliberately stops trying.
    """
    h12 = h % 12 or 12
    nxt = (h12 % 12) + 1
    if mi == 0:
        return _NUMBER[h12]
    if mi == 15:
        return f"quarter past {_NUMBER[h12]}"
    if mi == 30:
        return f"half past {_NUMBER[h12]}"
    if mi == 45:
        return f"quarter to {_NUMBER[nxt]}"
    return f"{h12}:{mi:02d}"


def _words(domain: str, slot: str) -> str:
    """The generic subject for a setting nobody has written phrasing for.

    A dotted domain reads best from the inside out, because the tail is the
    specific thing: garage.left plus door is "the left garage door", not "the
    garage left door". Duplicated words are dropped so lights.lights does not
    stutter.
    """
    parts = list(reversed(domain.split("."))) + [slot]
    seen, out = set(), []
    for p in parts:
        w = p.replace("_", " ").strip()
        if w and w.lower() not in seen:
            seen.add(w.lower())
            out.append(w)
    return " ".join(out)


def _entry(domain: str, slot: str):
    """(subject template, verb, unit, tail) for this setting.

    Exact match first, then the head of a dotted domain, so bedroom.ada borrows
    the phrasing written for bedroom and keeps the "ada" to fill {whose} with.
    """
    if (domain, slot) in SETTINGS:
        return (*SETTINGS[(domain, slot)], None)
    head, _, tail = domain.partition(".")
    if tail and (head, slot) in SETTINGS:
        return (*SETTINGS[(head, slot)], tail)
    # No verb for a setting nobody described: it depends on the value, and
    # only the caller has one. See statement().
    return ("the " + _words(domain, slot), "", PLAIN, None)


def _unit(domain: str, slot: str, value: str) -> str:
    """A known setting keeps its unit; an unknown one is read off the value.

    Sniffing stops at times deliberately. A bare number in a domain this file
    has never met is not necessarily a temperature, and announcing degrees for
    a shoe size would be worse than saying nothing clever at all.
    """
    _, _, unit, _ = _entry(domain, slot)
    if unit == DEGREES and not str(value).strip().lstrip("-").isdigit():
        return PLAIN                       # "off" is not a temperature
    if unit == PLAIN and _clock(value):
        return TIME
    return unit


def subject(domain: str, slot: str, about: str | None = None) -> str:
    """What the setting is called out loud. "the thermostat", "Ada's dinner"."""
    template, _, _, tail = _entry(domain, slot)
    if "{whose}" in template:
        whose = (possessive(about) if about else
                 possessive(tail.replace("_", " ").title()) if tail else "the")
        return template.format(whose=whose)
    if about:
        # "the thermostat" belonging to one person is "Ada's thermostat", never
        # "Ada's the thermostat".
        bare = template[4:] if template.startswith("the ") else template
        return f"{possessive(about)} {bare}"
    return template


def spoken(domain: str, slot: str, value: str) -> str:
    """The value as it would be said inside a sentence."""
    unit = _unit(domain, slot, value)
    if unit == DEGREES:
        return f"{value} degrees"
    clock = _clock(value)
    if unit == TIME and clock:
        return _spoken_clock(*clock)
    return str(value)


def reading(domain: str, slot: str, value: str) -> str:
    """The value as it would be shown, short enough to be the thing you see
    first. The sentence underneath it carries the nuance."""
    unit = _unit(domain, slot, value)
    if unit == DEGREES:
        return f"{value}°"
    clock = _clock(value)
    if unit == TIME and clock:
        h, mi = clock
        return f"{h % 12 or 12}:{mi:02d}{'am' if h < 12 else 'pm'}"
    return str(value)


def statement(domain: str, slot: str, value: str, about: str | None = None) -> str:
    """One sentence stating where the setting stands now."""
    _, verb, _, _ = _entry(domain, slot)
    if not verb:
        # A time is at, everything else is set to. Guessing this much is safe
        # because the value has already been recognised as a clock.
        verb = "is at" if _unit(domain, slot, value) == TIME else "is set to"
    s = subject(domain, slot, about)
    return f"{s[:1].upper()}{s[1:]} {verb} {spoken(domain, slot, value)}."


def describe(domain: str, slot: str, value: str, about: str | None = None) -> dict:
    """Everything the surface needs to name one setting without naming a slot."""
    s = subject(domain, slot, about)
    return {
        "subject": s,
        "title": f"{s[:1].upper()}{s[1:]}",
        "reading": reading(domain, slot, value),
        "statement": statement(domain, slot, value, about),
    }


def verdict(basis: str, *, winner: str, about: str | None,
            domain: str, slot: str) -> dict:
    """Why this one won, in the terms a household argues in.

    `basis` names the rule the resolver used, and a rule name is a fact about
    Hearth rather than about the house. "won on authority" tells a visitor
    nothing; "Dad has the final say over the thermostat" tells them everything,
    and it is the same sentence either way.
    """
    thing = subject(domain, slot)
    if basis == "authority":
        return {"chip": f"{winner} has the say",
                "line": f"{winner} has the final say over {thing}."}
    if basis == "recency":
        return {"chip": "most recent word",
                "line": ("Nobody here outranks anyone else on this, so the most "
                         f"recent word stands, and it was {winner}'s.")}
    if basis == "scope":
        who = about or "one person"
        return {"chip": f"about {who}",
                "line": (f"This one is about {who}, so it comes ahead of the "
                         "rule for the whole house.")}
    return {"chip": "", "line": ""}


def domain_label(domain: str) -> str:
    """A grant, said out loud. "thermostat" -> "the thermostat"."""
    wild = domain.endswith(".*")
    d = domain[:-2] if wild else domain
    if d in DOMAIN_LABELS:
        label = DOMAIN_LABELS[d]
    elif "." in d:
        head, _, tail = d.partition(".")
        label = f"{possessive(tail.replace('_', ' ').title())} {head.replace('_', ' ')}"
    else:
        label = "the " + d.replace("_", " ")
    return f"{label} and everything under it" if wild else label


def authority_line(grants) -> str:
    """What this member has the say over, or what it means to have none."""
    if not grants:
        return "no say of their own, so recency decides"
    labels = [domain_label(g) for g in grants]
    if len(labels) == 1:
        return f"has the say over {labels[0]}"
    return "has the say over " + ", ".join(labels[:-1]) + f" and {labels[-1]}"


def said(domain: str, slot: str, value: str, content: str = "",
         about: str | None = None) -> str:
    """What to show in a list of everything anyone has ever said.

    The sentence a member actually spoke beats any rendering of the belief it
    became, because it is the evidence. The rendering is only there for beliefs
    that arrived some other way, such as an import or a backdated seed.
    """
    said_out_loud = (content or "").strip()
    if said_out_loud:
        return f"“{said_out_loud}”"
    return statement(domain, slot, value, about)


def confirm(statements, *, speaker: str = "", context: str | None = None) -> str:
    """What the house says back when a sentence became one or more beliefs.

    Full sentences joined with a space, never stitched into a list with their
    first letters lowered: "Ada's dinner" cannot survive that treatment, and a
    confirmation that mangles somebody's name is worse than a plain one.
    """
    body = " ".join(statements)
    line = f"Noted, on {speaker}'s word. {body}" if speaker else f"Noted. {body}"
    if context:
        line += f" That holds only while {context} lasts."
    return line


def closed(context: str, statements) -> str:
    """What the house says back when a sentence ended a situation."""
    if not statements:
        return f"Understood, {context} is over."
    n = "One thing" if len(statements) == 1 else f"{len(statements)} things"
    return (f"Understood, {context} is over. {n} stopped applying. "
            + " ".join(statements))


def standing(live: bool, status: str, ended_reason: str = "") -> str:
    """Where a belief stands, for a list that shows the dead ones too.

    Keeping superseded beliefs is the point of the store, so the list has to say
    what happened to each one in a way that distinguishes "somebody took this
    back" from "the situation it belonged to is over". They are different facts
    about the house and `status` alone flattens them into one word.
    """
    if live:
        return "standing"
    if ended_reason.startswith("context ended: "):
        return f"{ended_reason.removeprefix('context ended: ')} ended"
    return ended_reason or {"superseded": "stood down",
                            "expired": "no longer applies"}.get(status, status)


def value_spoken(belief) -> str:
    """A belief's value, said out loud. This is what Resolution.explain takes
    when the sentence is going in front of a person rather than into a tool
    result, and it is the whole reason explain has the hook."""
    return spoken(belief.domain, belief.slot, belief.value)
