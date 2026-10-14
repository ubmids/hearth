"""The care household: the things Hearth now does, not only remembers.

Hearth began as a memory an agent consulted before it acted. In a home caring
for an elderly parent that is not enough, because the action that matters most,
a second dose of a blood thinner, is not something the agent does. Mum does it,
at four in the afternoon, having forgotten that her carer gave her one at nine.
The only thing that can stop it is something that knows both facts at once: the
rule (one a day, who said so, on whose authority) and the event (given at 9:10,
by whom). Hearth holds both, so it is Hearth that refuses, and Hearth that
writes the refusal down.

Four services sit behind the tools, each a small book persisted next to the
household:

  doses        every dose given, by whom, to whom, when
  appointments the calendar, with who is escorting and which ride is booked
  rides        rides booked for appointments (a sandbox provider)
  board        the family notice board, which is how siblings hear about it;
               a post is also pushed to each recipient's phone when they have
               a channel configured (hearth/notify.py, ntfy or a webhook)
  checkouts    pharmacy reorders, shaped like Alexa+'s UCP checkout sessions

Calendar, rota, doses and board are Hearth's own books in this process, not
outside services. The rides provider and the pharmacy are sandboxes, named as
such everywhere they surface. Nothing here books a real car or charges a real
card. The phone push is real when configured.

Every function takes `now`, so the tests pin the clock instead of racing it.
"""
import os
import re
import time
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import phrasing

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday",
            "saturday", "sunday"]

# What people call a medicine in a kitchen, mapped to what is on the box.
MED_ALIASES = {
    "blood thinner": "warfarin", "blood thinners": "warfarin",
    "coumadin": "warfarin", "jantoven": "warfarin",
    "water pill": "furosemide", "water pills": "furosemide", "lasix": "furosemide",
    "heart pill": "metoprolol", "heart pills": "metoprolol",
}

# The sandbox pharmacy. Prices in cents, as the checkout protocol carries them.
CATALOG = {
    "warfarin": {"id": "rx-warfarin-5mg-30", "title": "Warfarin 5 mg, 30 tablets",
                 "price": 1240, "rx": True},
    "furosemide": {"id": "rx-furosemide-20mg-30",
                   "title": "Furosemide 20 mg, 30 tablets", "price": 890, "rx": True},
    "metoprolol": {"id": "rx-metoprolol-25mg-30",
                   "title": "Metoprolol 25 mg, 30 tablets", "price": 1075, "rx": True},
    "ensure": {"id": "otc-ensure-24", "title": "Ensure Original, 24 bottles",
               "price": 3899, "rx": False},
    "pill organiser": {"id": "otc-pillbox-7", "title": "Weekly pill organiser",
                       "price": 799, "rx": False},
}

PHARMACY = "Hearth sandbox pharmacy"
UCP_VERSION = "2026-04-08"
RIDES = "Hearth sandbox rides"


def tz():
    return ZoneInfo(os.getenv("HEARTH_TZ", "America/New_York"))


def local(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, tz())


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


_STRENGTH = re.compile(r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|µg|g|ml|iu|units?)\b")
_FILLER = re.compile(r"\b(my|her|his|your|mum's|mom's|the|a|an|tablets?|pills?|"
                     r"capsules?|dose|doses|some|of)\b")


def med_name(text: str, known=()) -> str:
    """What a medicine is called in the household's rules, from what was said.

    By containment, not equality: "warfarin sodium" (the name on the bottle),
    "Jantoven 5mg tablet" and "her blood thinner" all have to land on
    `warfarin`, because a dose logged under any other name is a dose the
    daily limit never sees. That was a real hole (red-team audit 028, #6):
    "warfarin sodium" was logged as a new medicine with no rule and the second
    dose of the day went through.

    `known` adds the medicines this household has rules for.
    """
    raw = str(text or "").lower()
    t = _FILLER.sub(" ", _STRENGTH.sub(" ", raw))
    t = re.sub(r"\s+", " ", t).strip(" .,!?")
    if t in MED_ALIASES:
        return MED_ALIASES[t]
    names = {m: m for m in set(MED_ALIASES.values()) | set(known)
             | {k for k, v in CATALOG.items() if v["rx"]}}
    names.update(MED_ALIASES)
    # Longest first, so "blood thinners" wins over "blood thinner" and a
    # household rule for "metoprolol succinate" over plain "metoprolol".
    for alias in sorted(names, key=len, reverse=True):
        if re.search(r"(?<![\w])" + re.escape(alias.replace("_", " ")) + r"(?![\w])",
                     raw.replace("_", " ")):
            return names[alias]
    return t.replace(" ", "_")


# What people say when they have not said which medicine it is.
UNNAMED = {"", "it", "them", "that", "this", "one", "that_one", "medicine",
           "medicines", "medication", "medications", "meds", "pill", "tablet",
           "capsule", "something", "usual", "my_usual"}


def unnamed(text) -> bool:
    """True when what was said does not name a medicine ("my pills", "it").
    A dose of an unnamed medicine is never written down: it would be logged
    against whichever medicine a guess picked, and the real dose of that one
    refused later."""
    return med_name(text) in UNNAMED


def med_spoken(med: str) -> str:
    """`vitamin_d` is a key; "vitamin D" is what a person hears."""
    words = med.replace("_", " ").split()
    return " ".join(w.upper() if len(w) == 1 else w for w in words)


# --- saying times the way a person would ------------------------------------
def clock(ts: float) -> str:
    d = local(ts)
    return f"{d.hour % 12 or 12}:{d.minute:02d} {'am' if d.hour < 12 else 'pm'}"


def when_said(ts: float, now: float | None = None) -> str:
    """'at 9:10 this morning', 'yesterday at 6:00 pm', 'on Thursday at 10:00 am'."""
    now = now or time.time()
    d, n = local(ts), local(now)
    if d.date() == n.date():
        part = ("this morning" if d.hour < 12 else
                "this afternoon" if d.hour < 17 else "this evening")
        return f"at {d.hour % 12 or 12}:{d.minute:02d} {part}"
    if d.date() == (n - timedelta(days=1)).date():
        return f"yesterday at {clock(ts)}"
    if d.date() == (n + timedelta(days=1)).date():
        return f"tomorrow at {clock(ts)}"
    gap = (d.date() - n.date()).days
    if abs(gap) < 7:
        return f"on {d.strftime('%A')} at {clock(ts)}"
    if -21 <= gap < 0:
        return f"{-gap} days ago"
    return f"on {d.strftime('%A %-d %B')} at {clock(ts)}"


def parse_when(text, now: float | None = None) -> float | None:
    """A time as an agent or a person would pass it. ISO 8601 first, because
    that is what a model filling a schema sends; then "Thursday at 10",
    "tomorrow at 2:30pm", "10am", which is what a person says."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    s = str(text).strip()
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=tz())
        return d.timestamp()
    except ValueError:
        pass
    n = local(now or time.time())
    low = s.lower()
    day = n.date()
    m = re.search(r"\b(" + "|".join(WEEKDAYS) + r")\b", low)
    if "tomorrow" in low:
        day = (n + timedelta(days=1)).date()
    elif m:
        ahead = (WEEKDAYS.index(m.group(1)) - n.weekday()) % 7 or 7
        day = (n + timedelta(days=ahead)).date()
    t = re.search(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?", low)
    if not t:
        if m or "tomorrow" in low:
            hour, minute = 9, 0
        else:
            return None
    else:
        hour, minute = int(t.group(1)), int(t.group(2) or 0)
        mer = (t.group(3) or "").replace(".", "")
        if mer == "pm" and hour < 12:
            hour += 12
        elif mer == "am" and hour == 12:
            hour = 0
        elif not mer and 1 <= hour <= 6:
            hour += 12                  # "at 3" in a care home is the afternoon
    if hour > 23 or minute > 59:
        return None
    return datetime(day.year, day.month, day.day, hour, minute,
                    tzinfo=tz()).timestamp()


# --- the books ------------------------------------------------------------
class CareBook:
    KINDS = ("doses", "appointments", "rides", "board", "quotes", "checkouts")

    def __init__(self, store=None):
        self.store = store
        data = (store.load_aux("care") if store else None) or {}
        for k in self.KINDS:
            setattr(self, k, list(data.get(k, [])))
        self.notifier = None          # set by Care; sends a post to phones

    def save(self):
        if self.store:
            self.store.save_aux("care", {k: getattr(self, k) for k in self.KINDS})

    def post(self, text, *, to=None, by=None, now=None, pin_for=None,
             about=None) -> dict:
        """`pin_for` seconds keeps a post in front of its readers on every
        catch-up until then, not only the first: used for the notes Hearth
        writes to a medication holder, which must not be missed because
        somebody using the holder's name has spoken since."""
        at = now or time.time()
        p = {"id": _id("note"), "at": at, "to": list(to or []),
             "by": by, "text": text}
        if pin_for:
            p["pin_until"] = at + pin_for
        if about:
            p["about"] = about
        self.board.append(p)
        if self.notifier:
            self.notifier(p)
        return p


class Care:
    """The care services, bound to one household, its ledger and its books."""

    def __init__(self, household, ledger, book: CareBook, notifier=None):
        from .notify import Notifier
        self.h, self.ledger, self.book = household, ledger, book
        if book.notifier is None:
            book.notifier = notifier or Notifier(save=book.save)

    # --- who --------------------------------------------------------------
    def person(self, name=None):
        """The member being cared for. Named, or else the one the medication
        rules are about, because in a care household that is who "her" is."""
        if name:
            m = self.h.member_named(name)
            if m:
                return m
        for b in self.h.beliefs:
            if b.domain.startswith("medication.") and b.scope and b.is_live():
                return self.h.members.get(b.scope)
        return None

    def known_meds(self) -> set:
        """Every medicine this household has a rule for."""
        return {b.domain.partition(".")[2] for b in self.h.beliefs
                if b.domain.startswith("medication.")}

    def say_holder(self, domain):
        """The member with the say over this domain by explicit grant, if any.
        For medication that is the health care proxy, in the demo Ada."""
        return next((m for m in self.h.members.values()
                     if m.authority_over(domain) >= 100), None)

    def _name(self, name):
        m = self.h.member_named(name) if name else None
        return m.name if m else (str(name).strip().title() if name else "someone")

    # --- doses ------------------------------------------------------------
    def dose_status(self, medication, person=None, now=None) -> dict:
        now = now or time.time()
        med = med_name(medication, self.known_meds())
        who = self.person(person)
        pid = who.id if who else None
        domain = f"medication.{med}"
        per_day = self.h.resolve(domain, "per_day", for_member=pid, now=now,
                                 name_domain=phrasing.domain_label)
        due = self.h.resolve(domain, "time", for_member=pid, now=now,
                             name_domain=phrasing.domain_label)
        today = local(now).date()
        given = [d for d in self.book.doses
                 if d["medication"] == med and d.get("person") == pid
                 and local(d["at"]).date() == today]
        taken = sum(int(d.get("count", 1)) for d in given)
        limit = None
        if per_day.winner and str(per_day.winner.value).isdigit():
            limit = int(per_day.winner.value)
        return {"medication": med, "person": who, "per_day": per_day,
                "due": due, "given": given, "taken": taken, "limit": limit,
                "remaining": (None if limit is None else max(0, limit - taken))}

    def give(self, medication, given_by, person=None, now=None, count=1) -> dict:
        """Record a dose, or refuse one that would go over the day's limit.

        The refusal is the whole point and it is decided here, in code, from the
        household's own rule and its own record of what was given. It does not
        depend on the agent remembering to ask, and it is written to the ledger
        whether or not the agent ever mentions it.
        """
        now = now or time.time()
        count = max(1, min(10, int(count or 1)))
        st = self.dose_status(medication, person, now)
        who, med = st["person"], st["medication"]
        pid = who.id if who else None
        giver = self._name(given_by)
        self_given = bool(who and who.answers_to(given_by))
        her = "you" if self_given else (who.name if who else "them")
        if st["limit"] is not None and st["remaining"] < count:
            # The note is filed in the third person because it is read back
            # later to whoever asks why; the reply to Mom says "you".
            if st["given"]:
                last = st["given"][-1]
                note = (f"{self._name_id(last['given_by'])} gave "
                        f"{who.name if who else 'them'} today's {med} "
                        f"{when_said(last['at'], now)}.")
                spoken = (f"{self._name_id(last['given_by'])} gave you "
                          f"today's {med} {when_said(last['at'], now)}.")
            else:
                note = spoken = (f"That would be {count} {med} at once, more "
                                 f"than a day allows.")
            a = self.ledger.record(
                f"stopped a second {med} for {who.name if who else 'them'}",
                f"medication.{med}", resolution=st["per_day"], outcome="refused",
                by=giver, source="hearth", note=note, at=now)
            st.update(outcome="refused", action=a, note=note,
                      spoken_note=spoken if self_given else note)
            return st
        dose = {"id": _id("dose"), "medication": med, "person": pid,
                "given_by": (self.h.member_named(given_by).id
                             if self.h.member_named(given_by) else giver),
                "at": now}
        if count > 1:
            dose["count"] = count
        self.book.doses.append(dose)
        self.book.save()
        a = self.ledger.record(
            f"logged {med} for {who.name if who else 'them'}, given by {giver}",
            f"medication.{med}", resolution=st["per_day"], by=giver,
            source="hearth", at=now,
            note=("Nobody has told me how often it is taken."
                  if st["limit"] is None else ""))
        st = self.dose_status(med, who.name if who else None, now)
        st.update(outcome="done", action=a, dose=dose)
        return st

    def _name_id(self, member_id_or_name):
        m = self.h.members.get(member_id_or_name)
        return m.name if m else str(member_id_or_name)

    # --- appointments: several services, one request ----------------------
    def arrange(self, what, when, asked_by, person=None, where=None,
                now=None) -> dict:
        """Move or book an appointment and do everything that follows from it.

        One sentence from a carer, "cardiology moved to Thursday at ten, sort
        it out", is four services: the calendar, the rota (who takes her on a
        Thursday, by the household's own rule), the ride, and the family board.
        Each step is decided by the household's beliefs and written to the
        ledger as its own action, so "why is Tom taking her?" has an answer.
        """
        now = now or time.time()
        at = parse_when(when, now)
        if at is None:
            raise ValueError(f"I could not tell when {when!r} is")
        who = self.person(person)
        pid = who.id if who else None
        her = who.name if who else "them"
        asker = self._name(asked_by)
        what = str(what).strip()
        steps = []

        def step(service, line, status="done", resolution=None, domain=None):
            a = self.ledger.record(line[:1].lower() + line[1:].rstrip("."),
                                   domain or service, resolution=resolution,
                                   by=asker, source="hearth", at=now,
                                   outcome="done" if status == "done" else status)
            steps.append({"service": service, "line": line, "status": status,
                          "action": a.id})

        # 1. calendar
        appt = next((x for x in self.book.appointments
                     if x["status"] == "booked" and x.get("person") == pid
                     and (what.lower() in x["what"].lower()
                          or x["what"].lower() in what.lower())), None)
        if appt:
            old = appt["at"]
            appt["at"] = at
            if where:
                appt["where"] = where
            step("calendar", f"Moved {her}'s {appt['what']} from "
                             f"{local(old).strftime('%A')} {clock(old)} to "
                             f"{local(at).strftime('%A')} {clock(at)}.")
        else:
            appt = {"id": _id("appt"), "what": what, "person": pid, "at": at,
                    "where": where or "", "status": "booked",
                    "escort": None, "ride": None}
            self.book.appointments.append(appt)
            step("calendar", f"Booked {her}'s {what} for "
                             f"{local(at).strftime('%A')} {clock(at)}.")

        # 2. rota: who takes her, by the household's rule for that weekday
        day = WEEKDAYS[local(at).weekday()]
        rota = self.h.resolve("rota", day, now=now,
                              name_domain=phrasing.domain_label)
        escort = rota.winner.value if rota.winner else None
        appt["escort"] = escort
        if escort:
            step("rota", f"{escort} is taking {her}: {escort} does "
                         f"{day.title()}s.", resolution=rota)
        else:
            step("rota", f"Nobody is on the rota for {day.title()}s, so "
                         f"nobody is taking {her} yet.", status="needs_attention",
                 resolution=rota)

        # 3. ride, cancelling the old one first
        if appt.get("ride"):
            old_ride = next((r for r in self.book.rides
                             if r["id"] == appt["ride"]), None)
            if old_ride and old_ride["status"] == "booked":
                old_ride["status"] = "cancelled"
                step("rides", f"Cancelled the {local(old_ride['pickup']).strftime('%A')} "
                              f"ride ({RIDES}).")
        lead_r = self.h.resolve("transport", "lead_minutes", now=now)
        lead = int(lead_r.winner.value) if (lead_r.winner and
                                            str(lead_r.winner.value).isdigit()) else 45
        ride = {"id": _id("ride"), "appointment": appt["id"], "pickup": at - lead * 60,
                "for": pid, "with": escort, "status": "booked", "provider": RIDES}
        self.book.rides.append(ride)
        appt["ride"] = ride["id"]
        step("rides", f"Booked a ride at {clock(ride['pickup'])}, {lead} minutes "
                      f"before ({RIDES}).",
             resolution=lead_r if lead_r.winner else None)

        # 4. medication that falls inside the trip, so nobody misses a dose
        back = at + 2 * 3600
        for b in self.h.beliefs:
            if (b.domain.startswith("medication.") and b.slot == "time"
                    and b.is_live(now) and b.scope == pid):
                hh, mm = map(int, re.split("[:.]", b.value)[:2])
                due = local(at).replace(hour=hh, minute=mm).timestamp()
                if ride["pickup"] <= due <= back:
                    med = b.domain.partition(".")[2]
                    step("doses", f"{her}'s {med} is due at {clock(due)}, during "
                                  f"the trip. Reminded {escort or 'the family'} to "
                                  f"bring it.", status="needs_attention")

        # 5. the family board
        everyone = [m.name for m in self.h.members.values()
                    if m.id != pid and m.name != asker]
        text = (f"{her}'s {appt['what']} is now {local(at).strftime('%A')} at "
                f"{clock(at)}, with a ride at {clock(ride['pickup'])}."
                + (f" {escort} is taking {her}." if escort else
                   " Nobody is taking her yet."))
        post = self.book.post(text, to=everyone, by=asker, now=now)
        names = (", ".join(everyone[:-1]) + " and " + everyone[-1] if len(everyone) > 1
                 else (everyone[0] if everyone else "nobody"))
        pushed = [d["to"] for d in post.get("delivered", [])]
        line = f"Left a note for {names} on the family board"
        if pushed:
            line += (" and sent it to " + " and ".join(f"{n}'s phone" for n in pushed))
        step("board", line + ".")
        self.book.save()
        return {"appointment": appt, "ride": ride, "escort": escort,
                "steps": steps, "person": who,
                "notified": [{"to": d["to"], "via": d["via"]}
                             for d in post.get("delivered", [])],
                "told": everyone}

    # --- the pharmacy: a quote here, a checkout there, never a silent charge --
    #
    # The Alexa+ payments model, followed as documented: the add-on's tool
    # prepares the purchase and its MCP App offers a "Pay" button; that button
    # sends `ui/message` "Pay for this order"; Alexa+ then creates the checkout
    # session itself (POST /checkout-sessions, line_items carrying item ids as
    # hints), collects the voice PIN and the card, and completes it (POST
    # /checkout-sessions/{id}/complete). The merchant's backend owns price,
    # availability and every business rule. Hearth's rules are the family's:
    # the spending limit, who may go over it, and an order already on its way.

    def _sku(self, item):
        key = med_name(item)
        entry = CATALOG.get(key) or next(
            (v for k, v in CATALOG.items()
             if k in str(item).lower() or v["id"] == str(item)), None)
        if entry is None:
            raise ValueError(f"the sandbox pharmacy does not stock {item!r}")
        return entry

    def _house_rules(self, entry, quantity, asked_by, now):
        """(messages, limit resolution) for buying this, by this person, now."""
        total = entry["price"] * quantity
        messages = []
        recent = [c for c in self.book.checkouts
                  if c["status"] == "completed" and now - c["completed_at"] < 7 * 86400
                  and any(li["item"]["id"] == entry["id"] for li in c["line_items"])]
        if recent:
            # A duplicate is the transaction version of a double dose.
            messages.append({"type": "warning", "code": "possible_duplicate",
                             "content": f"{entry['title']} was already ordered "
                                        f"{when_said(recent[-1]['completed_at'], now)} "
                                        f"by {recent[-1]['buyer']}.",
                             "severity": "requires_buyer_review"})
        limit_r = self.h.resolve("purchases", "limit", now=now,
                                 name_domain=phrasing.domain_label)
        limit = (float(str(limit_r.winner.value).lstrip("$")) * 100
                 if limit_r.winner else None)
        asker = self.h.member_named(asked_by) if asked_by else None
        approver = next((m for m in self.h.members.values()
                         if m.authority_over("purchases") >= 100), None)
        if (limit is not None and total > limit
                and not (asker and asker.authority_over("purchases") >= 100)):
            messages.append({"type": "error", "code": "requires_approval",
                             "content": f"That is over the "
                                        f"{phrasing.spoken('purchases', 'limit', limit_r.winner.value)} "
                                        f"{self.h.name_of(limit_r.winner.holder)} "
                                        f"allows without asking. "
                                        f"{approver.name if approver else 'Someone'} "
                                        f"has to approve it.",
                             "severity": "requires_buyer_input"})
        return messages, limit_r

    def reorder(self, item, asked_by, quantity=1, person=None, now=None) -> dict:
        """Prepare a refill: price it and check it against the family's rules.

        Nothing is created at the merchant and nothing is charged. The quote
        is remembered so that the checkout Alexa+ opens from it carries who
        asked, which is what decides whether it may go over the limit.
        """
        now = now or time.time()
        entry = self._sku(item)
        who = self.person(person)
        asker = self._name(asked_by)
        quantity = max(1, int(quantity or 1))
        total = entry["price"] * quantity
        messages, limit_r = self._house_rules(entry, quantity, asked_by, now)
        approved = not any(m["type"] == "error" for m in messages)
        # What was checked and passed, so a screen can show the family the
        # rules held, not only when they fail.
        codes = {m["code"] for m in messages}
        checks = []
        if limit_r.winner and "requires_approval" not in codes:
            checks.append(f"Within {self.h.name_of(limit_r.winner.holder)}'s "
                          f"${str(limit_r.winner.value).lstrip('$')} limit")
        if "possible_duplicate" not in codes:
            checks.append("Not ordered in the last week")
        quote = {"id": _id("q"), "sku": entry["id"], "title": entry["title"],
                 "quantity": quantity, "price": entry["price"], "total": total,
                 "asked_by": asker, "for": who.id if who else None,
                 "approved": approved, "messages": messages, "checks": checks,
                 "at": now}
        self.book.quotes.append(quote)
        self.book.save()
        self.ledger.record(
            f"priced {entry['title']} at ${total / 100:.2f} for {asker}"
            + ("" if approved else ", which needs approval"), "purchases",
            resolution=limit_r if limit_r.winner else None, by=asker,
            source="hearth", at=now, outcome="done" if approved else "refused")
        return quote

    def _session(self, entry, quantity, buyer, messages, now, quote=None):
        total = entry["price"] * quantity
        status = ("incomplete" if any(m["type"] == "error" for m in messages)
                  else "ready_for_complete")
        return {
            "id": _id("cs"), "status": status, "currency": "USD",
            "line_items": [{"id": _id("li"), "quantity": quantity,
                            "item": {"id": entry["id"], "title": entry["title"],
                                     "price": entry["price"]},
                            "totals": [{"type": "subtotal", "amount": total},
                                       {"type": "total", "amount": total}]}],
            "totals": [{"type": "subtotal", "amount": total},
                       {"type": "shipping", "amount": 0},
                       {"type": "tax", "amount": 0},
                       {"type": "total", "amount": total}],
            "ucp": {"version": UCP_VERSION,
                    "capabilities": {"dev.ucp.shopping.checkout": [{"version": UCP_VERSION}]},
                    "payment_handlers": {"com.amazon.payments.network_token": [{
                        "id": "amazon_pay_network_token", "version": UCP_VERSION,
                        "available_instruments": [{"type": "card", "constraints": {
                            "brands": ["visa", "mastercard"]}}]}]}},
            "messages": messages,
            "links": [{"type": "terms_of_use", "title": "Sandbox merchant terms",
                       "url": "/terms"}],
            "expires_at": datetime.fromtimestamp(now + 3600, ZoneInfo("UTC"))
                                  .strftime("%Y-%m-%dT%H:%M:%SZ"),
            # Hearth's own fields, outside the UCP shape.
            "merchant": PHARMACY, "sandbox": True, "buyer": buyer,
            "quote": quote["id"] if quote else None,
            "created_at": now, "completed_at": None, "order_id": None,
            "idempotency": {},
        }

    def create_session(self, line_items, buyer=None, quote_id=None, now=None) -> dict:
        """POST /checkout-sessions. Price comes from the catalog, never the
        request; the family's rules are applied again, on the quote's asker
        when the session came from one."""
        now = now or time.time()
        li = (line_items or [{}])[0]
        entry = self._sku((li.get("item") or {}).get("id", ""))
        quantity = max(1, int(li.get("quantity") or 1))
        quote = next((q for q in self.book.quotes if q["id"] == quote_id
                      and q["sku"] == entry["id"] and q["quantity"] == quantity),
                     None)
        asker = quote["asked_by"] if quote else buyer
        messages, _ = self._house_rules(entry, quantity, asker, now)
        s = self._session(entry, quantity, asker or "the account holder", messages,
                          now, quote)
        self.book.checkouts.append(s)
        self.book.save()
        return s

    def complete(self, session_id, idempotency_key=None, now=None) -> tuple[dict | None, str | None]:
        """POST /checkout-sessions/{id}/complete.

        Business failures come back as the session with an error in
        `messages[]` (HTTP 200, as the Alexa+ contract asks); only protocol
        problems are errors. A repeated Idempotency-Key gets the stored result.
        """
        now = now or time.time()
        s = next((c for c in self.book.checkouts if c["id"] == session_id), None)
        if s is None:
            return None, "not_found"
        if idempotency_key and idempotency_key in s.get("idempotency", {}):
            return s, None
        if s["status"] == "completed":
            # Never a second charge for one session, whatever the key.
            return s, None
        if s["status"] != "ready_for_complete":
            if not any(m.get("code") == "not_ready" for m in s["messages"]):
                s["messages"].append({"type": "error", "code": "not_ready",
                                      "content": "This checkout cannot be completed.",
                                      "severity": "requires_buyer_input"})
            return s, "not_ready"
        s["status"] = "completed"
        s["completed_at"] = now
        s["order_id"] = _id("ord")
        if idempotency_key:
            s["idempotency"][idempotency_key] = s["order_id"]
        title = s["line_items"][0]["item"]["title"]
        total = next(t["amount"] for t in s["totals"] if t["type"] == "total")
        self.book.post(f"{s['buyer']} ordered {title} (${total / 100:.2f}), "
                       f"arriving tomorrow.", to=[m.name for m in self.h.members.values()],
                       by=s["buyer"], now=now)
        self.book.save()
        self.ledger.record(f"ordered {title} for ${total / 100:.2f} "
                           f"({PHARMACY}, paid through Alexa+ checkout)", "purchases",
                           by=s["buyer"], source="hearth", at=now)
        return s, None

    def cancel(self, session_id, now=None):
        s = next((c for c in self.book.checkouts if c["id"] == session_id), None)
        if s is None:
            return None, "not_found"
        if s["status"] == "completed":
            return s, "already_completed"
        s["status"] = "canceled"
        self.book.save()
        return s, None

    # --- what changed since you last asked ---------------------------------
    def catch_up(self, person_name, since: float, now=None, limit=5) -> list[dict]:
        """What happened in the house since this person last talked to it.

        `since` comes from Hearth's own record of the last call made on this
        person's behalf, across every session and device, so a sibling who
        checks in from another state on Thursday hears what the carer did on
        Tuesday without anybody having to tell them.
        """
        now = now or time.time()
        items = []
        me = self.h.member_named(person_name)
        for a in self.ledger.actions:
            if a.at <= since or a.source != "hearth":
                continue
            if a.domain in ("calendar", "rota", "rides", "board", "doses"):
                continue                         # summarised by the board post
            if me and a.by and me.answers_to(a.by):
                continue                         # you know what you did
            items.append({"at": a.at, "kind": "action", "outcome": a.outcome,
                          "line": _action_line(a, now)})
        for d in self.book.doses:
            if d["at"] > since and not (me and d["given_by"] == me.id):
                items.append({"at": d["at"], "kind": "dose", "outcome": "done",
                              "line": f"{self._name_id(d['given_by'])} gave "
                                      f"{self._name_id(d['person'])} her "
                                      f"{d['medication']} {when_said(d['at'], now)}."})
        for p in self.book.board:
            fresh = p["at"] > since or p.get("pin_until", 0) > now
            if fresh and (not me or me.name in p["to"]):
                items.append({"at": p["at"], "kind": "board", "outcome": "done",
                              # Said aloud, "From Grace: Mom slept well" after
                              # "since Sunday:" is a colon too many; a post that
                              # already names its author needs no attribution.
                              "line": p["text"] if p["text"].startswith(p["by"] + " ")
                              else f"A note from {p['by']}. {p['text']}"})
        for b in self.h.beliefs:
            if b.stated_at > since and not (me and b.holder == me.id):
                items.append({"at": b.stated_at, "kind": "rule", "outcome": "done",
                              "line": f"{self.h.name_of(b.holder)} said: "
                                      + phrasing.statement(
                                          b.domain, b.slot, b.value,
                                          self.h.name_of(b.scope) if b.scope else None)})
            for ev in b.audit:
                if ev.get("action") == "expired" and ev["at"] > since:
                    items.append({"at": ev["at"], "kind": "ended", "outcome": "done",
                                  "line": f"{b.ended_reason.removeprefix('context ended: ').capitalize()} "
                                          f"ended, so "
                                          + phrasing.statement(
                                              b.domain, b.slot, b.value,
                                              self.h.name_of(b.scope) if b.scope else None)[:-1]
                                          + " no longer applies."})
        items.sort(key=lambda x: x["at"])
        # The refusal is the line a sibling most needs, so it is never the one
        # that falls off the end of a voice reply capped at five.
        urgent = [i for i in items if i["outcome"] == "refused"]
        rest = [i for i in items if i["outcome"] != "refused"]
        keep = urgent + rest[-(limit - len(urgent)):] if limit > len(urgent) else urgent
        return sorted(keep, key=lambda x: x["at"])


def _action_line(a, now) -> str:
    when = when_said(a.at, now)
    m = re.fullmatch(r"stopped a second (\S+) for (.+)", a.what)
    if a.outcome == "refused" and m:
        return (f"{when[:1].upper()}{when[1:]}, {m.group(2)} went to take a second "
                f"{m.group(1)} and I stopped her.")
    return f"{when[:1].upper()}{when[1:]}, {a.by or 'someone'} asked and I {a.what}."
