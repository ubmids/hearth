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
  board        the family notice board, which is how siblings hear about it
  checkouts    pharmacy reorders, shaped like Alexa+'s UCP checkout sessions

The rides provider and the pharmacy are sandboxes, named as such everywhere
they surface. Nothing here books a real car or charges a real card.

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
RIDES = "Hearth sandbox rides"


def tz():
    return ZoneInfo(os.getenv("HEARTH_TZ", "America/New_York"))


def local(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, tz())


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def med_name(text: str) -> str:
    t = re.sub(r"\b(my|her|his|mum's|mom's|the|a|an|tablets?|pills?|dose)\b", " ",
               str(text or "").lower())
    t = re.sub(r"\s+", " ", t).strip()
    if t in MED_ALIASES:
        return MED_ALIASES[t]
    for alias, med in MED_ALIASES.items():
        if alias in str(text).lower():
            return med
    return t.replace(" ", "_")


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
    KINDS = ("doses", "appointments", "rides", "board", "checkouts")

    def __init__(self, store=None):
        self.store = store
        data = (store.load_aux("care") if store else None) or {}
        for k in self.KINDS:
            setattr(self, k, list(data.get(k, [])))

    def save(self):
        if self.store:
            self.store.save_aux("care", {k: getattr(self, k) for k in self.KINDS})

    def post(self, text, *, to=None, by=None, now=None) -> dict:
        p = {"id": _id("note"), "at": now or time.time(), "to": list(to or []),
             "by": by, "text": text}
        self.board.append(p)
        return p


class Care:
    """The care services, bound to one household, its ledger and its books."""

    def __init__(self, household, ledger, book: CareBook):
        self.h, self.ledger, self.book = household, ledger, book

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

    def _name(self, name):
        m = self.h.member_named(name) if name else None
        return m.name if m else (str(name).strip().title() if name else "someone")

    # --- doses ------------------------------------------------------------
    def dose_status(self, medication, person=None, now=None) -> dict:
        now = now or time.time()
        med = med_name(medication)
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
        limit = None
        if per_day.winner and str(per_day.winner.value).isdigit():
            limit = int(per_day.winner.value)
        return {"medication": med, "person": who, "per_day": per_day,
                "due": due, "given": given, "limit": limit,
                "remaining": (None if limit is None else max(0, limit - len(given)))}

    def give(self, medication, given_by, person=None, now=None) -> dict:
        """Record a dose, or refuse one that would go over the day's limit.

        The refusal is the whole point and it is decided here, in code, from the
        household's own rule and its own record of what was given. It does not
        depend on the agent remembering to ask, and it is written to the ledger
        whether or not the agent ever mentions it.
        """
        now = now or time.time()
        st = self.dose_status(medication, person, now)
        who, med = st["person"], st["medication"]
        pid = who.id if who else None
        giver = self._name(given_by)
        self_given = bool(who and who.answers_to(given_by))
        her = "you" if self_given else (who.name if who else "them")
        if st["limit"] is not None and st["remaining"] == 0:
            last = st["given"][-1]
            # The note is filed in the third person because it is read back
            # later to whoever asks why; the reply to Mom says "you".
            note = (f"{self._name_id(last['given_by'])} gave "
                    f"{who.name if who else 'them'} today's {med} "
                    f"{when_said(last['at'], now)}.")
            a = self.ledger.record(
                f"stopped a second {med} for {who.name if who else 'them'}",
                f"medication.{med}", resolution=st["per_day"], outcome="refused",
                by=giver, source="hearth", note=note, at=now)
            st.update(outcome="refused", action=a, note=note,
                      spoken_note=(f"{self._name_id(last['given_by'])} gave you "
                                   f"today's {med} {when_said(last['at'], now)}."
                                   if self_given else note))
            return st
        dose = {"id": _id("dose"), "medication": med, "person": pid,
                "given_by": (self.h.member_named(given_by).id
                             if self.h.member_named(given_by) else giver),
                "at": now}
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
        text = (f"{her}'s {appt['what']}: {local(at).strftime('%A')} "
                f"{clock(at)}. Ride at {clock(ride['pickup'])}."
                + (f" {escort} is taking {her}." if escort else
                   " Nobody is taking her yet."))
        self.book.post(text, to=everyone, by=asker, now=now)
        step("board", f"Told {', '.join(everyone[:-1]) + ' and ' + everyone[-1] if len(everyone) > 1 else (everyone[0] if everyone else 'nobody')} on the family board.")
        self.book.save()
        return {"appointment": appt, "ride": ride, "escort": escort,
                "steps": steps, "person": who}

    # --- the pharmacy: a checkout, never a silent charge -------------------
    def reorder(self, item, asked_by, quantity=1, person=None, now=None) -> dict:
        """Open a checkout session for a refill. It does not pay.

        Alexa+ owns payment: the add-on exposes checkout sessions and Alexa
        collects the confirmation and the card. So the tool's job is to build a
        correct session, check it against the household's rules (the spending
        limit, who may approve more, an order already on its way) and hand it
        over. Completing it happens at /checkout-sessions/{id}/complete.
        """
        now = now or time.time()
        key = med_name(item)
        entry = CATALOG.get(key) or next(
            (v for k, v in CATALOG.items() if k in str(item).lower()), None)
        if entry is None:
            raise ValueError(f"the sandbox pharmacy does not stock {item!r}")
        who = self.person(person)
        asker = self._name(asked_by)
        quantity = max(1, int(quantity or 1))
        total = entry["price"] * quantity
        messages = []

        # A duplicate is the transaction version of a double dose.
        recent = [c for c in self.book.checkouts
                  if c["status"] == "completed" and now - c["completed_at"] < 7 * 86400
                  and any(li["item"]["id"] == entry["id"] for li in c["line_items"])]
        if recent:
            messages.append({"type": "warning", "code": "possible_duplicate",
                             "content": f"{entry['title']} was already ordered "
                                        f"{when_said(recent[-1]['completed_at'], now)} "
                                        f"by {recent[-1]['buyer']}."})

        limit_r = self.h.resolve("purchases", "limit", now=now,
                                 name_domain=phrasing.domain_label)
        limit = (float(str(limit_r.winner.value).lstrip("$")) * 100
                 if limit_r.winner else None)
        asker_m = self.h.member_named(asked_by)
        approver = next((m for m in self.h.members.values()
                         if m.authority_over("purchases") >= 100), None)
        can_approve = bool(asker_m and asker_m.authority_over("purchases") >= 100)
        if limit is not None and total > limit and not can_approve:
            messages.append({"type": "error", "code": "requires_approval",
                             "content": f"That is over the "
                                        f"{phrasing.spoken('purchases', 'limit', limit_r.winner.value)} "
                                        f"{limit_r.winner and self.h.name_of(limit_r.winner.holder)} "
                                        f"allows without asking. "
                                        f"{approver.name if approver else 'Someone'} "
                                        f"has to approve it."})
        status = ("incomplete" if any(m["type"] == "error" for m in messages)
                  else "ready_for_complete")
        session = {
            "id": _id("chk"), "status": status, "currency": "USD",
            "line_items": [{"id": _id("li"), "quantity": quantity,
                            "item": {"id": entry["id"], "title": entry["title"],
                                     "price": entry["price"]},
                            "totals": [{"type": "subtotal", "amount": total}]}],
            "totals": [{"type": "subtotal", "amount": total},
                       {"type": "fulfillment", "amount": 0},
                       {"type": "total", "amount": total}],
            "fulfillment": {"type": "delivery", "estimate": "tomorrow",
                            "to": who.name if who else None},
            "merchant": PHARMACY, "sandbox": True,
            "messages": messages, "buyer": asker, "for": who.id if who else None,
            "created_at": now, "completed_at": None, "order_id": None,
        }
        self.book.checkouts.append(session)
        self.book.save()
        self.ledger.record(
            f"opened a {PHARMACY} checkout for {entry['title']}, "
            f"${total / 100:.2f}", "purchases",
            resolution=limit_r if limit_r.winner else None, by=asker,
            source="hearth", at=now,
            outcome="done" if status == "ready_for_complete" else "refused")
        return session

    def complete(self, session_id, idempotency_key=None, now=None) -> tuple[dict | None, str | None]:
        now = now or time.time()
        s = next((c for c in self.book.checkouts if c["id"] == session_id), None)
        if s is None:
            return None, "not_found"
        if s["status"] == "completed":
            # Idempotent: the same key, or a retry of the same session, gets the
            # same order back and never a second charge.
            return s, None
        if s["status"] != "ready_for_complete":
            return s, "not_ready"
        s["status"] = "completed"
        s["completed_at"] = now
        s["order_id"] = _id("ord")
        s["idempotency_key"] = idempotency_key
        title = s["line_items"][0]["item"]["title"]
        total = next(t["amount"] for t in s["totals"] if t["type"] == "total")
        self.book.post(f"{s['buyer']} ordered {title} (${total / 100:.2f}), "
                       f"arriving tomorrow.", to=[m.name for m in self.h.members.values()],
                       by=s["buyer"], now=now)
        self.book.save()
        self.ledger.record(f"ordered {title} for ${total / 100:.2f} "
                           f"({PHARMACY}, confirmed by {s['buyer']})", "purchases",
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
            if p["at"] > since and (not me or me.name in p["to"]):
                items.append({"at": p["at"], "kind": "board", "outcome": "done",
                              "line": f"From {p['by']}: {p['text']}"})
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
