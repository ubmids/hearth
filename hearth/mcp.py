"""MCP over Streamable HTTP, hand-rolled.

Alexa+ requires spec 2025-11-25, where the old standalone HTTP+SSE transport is
gone and Streamable HTTP is the only transport. Underneath it is JSON-RPC 2.0
over a single POST endpoint, which is small enough to implement directly, and
implementing it directly is the point: the Alexa+ conformance details live in
the headers and the 401, and an SDK that helpfully adds a `WWW-Authenticate`
header would fail Amazon's check without ever telling us.

The tools deliberately read like household speech rather than database calls,
because the model calling them is transcribing a person: `remember`,
`whats_true`, `why`, `stand_down`.
"""
import hashlib
import os
import time
import uuid

from . import care as carelib
from . import phrasing

PROTOCOL_VERSION = "2025-11-25"
SERVER_INFO = {"name": "hearth", "version": "0.1.0",
               "title": "Hearth household memory"}


def _err(rpc_id, code, message, data=None):
    e = {"code": code, "message": message}
    if data is not None:
        e["data"] = data
    return {"jsonrpc": "2.0", "id": rpc_id, "error": e}


def _ok(rpc_id, result):
    return {"jsonrpc": "2.0", "id": rpc_id, "result": result}


def _text(payload, card=None, **data):
    """MCP tool results are content blocks, not bare values.

    `card` is what a screen draws. It travels as `structuredContent`, which is
    what an MCP Apps view receives in `ui/notifications/tool-result` and what
    Alexa+ hydrates natively when there is no view, and the tool result names
    the view in `_meta.ui.resourceUri` because the Alexa+ docs read it there
    (the MCP Apps spec reads it off the tool definition; both are set). The
    text block stays the whole spoken answer, so a speaker with no screen loses
    nothing.
    """
    out = {"content": [{"type": "text", "text": payload}], "isError": False}
    if card is not None or data:
        out["structuredContent"] = {"speech": payload, **data,
                                    **({"card": card} if card else {})}
    if card is not None:
        out["_meta"] = {"ui": {"resourceUri": CARD_URI}}
    return out


# --- the view: one self-contained MCP App, served at a content-hashed URI ---
_CARD_PATH = os.path.join(os.path.dirname(__file__), "web", "card.html")


def _card_html() -> str:
    with open(_CARD_PATH, encoding="utf-8") as f:
        return f.read()


# The Alexa+ layout guide asks for a content hash in the URI, so a changed view
# is a new resource rather than a stale cache entry on somebody's Echo Show.
CARD_URI = ("ui://hearth/card-"
            + hashlib.sha256(_card_html().encode()).hexdigest()[:8] + ".html")
APP_MIME = "text/html;profile=mcp-app"
_UI = {"ui": {"resourceUri": CARD_URI, "visibility": ["model", "app"]}}

# MCP tool annotations. Hints only, and the spec says a client must treat them
# as untrusted, which is why the refusals that matter are enforced in code.
_READ = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}
_WRITE = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False,
          "openWorldHint": False}
_WORLD = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False,
          "openWorldHint": True}


TOOLS = [
    {
        "name": "remember",
        "title": "Remember what someone said",
        "description": ("Record a household preference, rule or decision, attributed to "
                        "the person who said it. Use whenever someone states how they "
                        "want something to be, even in passing."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "said": {"type": "string", "description": "The sentence, as spoken."},
                "speaker": {"type": "string", "description": "Name of the person who said it."},
            },
            "required": ["said", "speaker"],
        },
    },
    {
        "name": "whats_true",
        "title": "What is true right now",
        "description": ("Resolve what the household currently wants for a setting, and "
                        "why. Call this before acting on anything the household has an "
                        "opinion about."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "e.g. thermostat, shopping, meals"},
                "slot": {"type": "string", "description": "e.g. target, coffee, dinner"},
                "about": {"type": "string", "description": "Optional person this concerns."},
            },
            "required": ["domain", "slot"],
        },
    },
    {
        "name": "did",
        "title": "Record an action taken",
        "description": ("Log an action taken on the household's behalf, bound to the "
                        "beliefs that justified it. Call immediately after acting."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "what": {"type": "string", "description": "e.g. set the thermostat to 19"},
                "domain": {"type": "string"},
                "slot": {"type": "string"},
                "about": {"type": "string"},
            },
            "required": ["what", "domain", "slot"],
        },
    },
    {
        "name": "why",
        "title": "Why did you do that",
        "description": "Explain the most recent action, naming who set what and when.",
        "inputSchema": {
            "type": "object",
            "properties": {"domain": {"type": "string"}},
        },
    },
    {
        "name": "stand_down",
        "title": "Retire a belief",
        "description": ("Stop applying something a member previously said. Use when "
                        "someone explicitly takes back a rule."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "belief_id": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["belief_id"],
        },
    },
    {
        "name": "end_context",
        "title": "End a situation",
        "description": ("Close a situation, expiring everything asserted only for it. "
                        "Use when a visit ends, an illness passes, a cold snap breaks."),
        "inputSchema": {
            "type": "object",
            "properties": {"context": {"type": "string"}},
            "required": ["context"],
        },
    },
    {
        "name": "household",
        "title": "Who lives here",
        "description": "List the members, their authority, and the beliefs standing now.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "check_dose",
        "title": "Has she had her medicine",
        "description": ("Answer whether a medicine has been given today, by whom and "
                        "when, and whether another dose is allowed. Call for any "
                        "question like 'did Mum take her blood thinner?'."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "medication": {"type": "string", "description": "As said: 'warfarin', 'her blood thinner'."},
                "person": {"type": "string", "description": "Who takes it. Optional; defaults to the person being cared for."},
                "asked_by": {"type": "string", "description": "Name of the person asking."},
            },
            "required": ["medication"],
        },
    },
    {
        "name": "give_dose",
        "title": "Log a dose, or stop a second one",
        "description": ("Call whenever someone says they are taking, giving or about "
                        "to take a medicine. Hearth checks the household's rule and "
                        "today's record and REFUSES a dose over the daily limit. Say "
                        "its answer as given; never tell anyone to go ahead if it "
                        "refused."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "medication": {"type": "string"},
                "given_by": {"type": "string", "description": "Who is giving it. If she is taking it herself, her name."},
                "person": {"type": "string", "description": "Who takes it. Optional."},
            },
            "required": ["medication", "given_by"],
        },
    },
    {
        "name": "arrange",
        "title": "Sort out an appointment",
        "description": ("Book or move an appointment and do everything that follows "
                        "from it in one go: the calendar, who takes her (by the "
                        "household rota), the ride, medication due during the trip, "
                        "and telling the family. Use for 'her cardiology moved to "
                        "Thursday at ten, sort it out'."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "what": {"type": "string", "description": "e.g. cardiology, dentist"},
                "when": {"type": "string", "description": "ISO 8601 local time, or as said: 'Thursday at 10am'."},
                "asked_by": {"type": "string"},
                "person": {"type": "string"},
                "where": {"type": "string"},
            },
            "required": ["what", "when", "asked_by"],
        },
    },
    {
        "name": "reorder",
        "title": "Reorder from the pharmacy",
        "description": ("Prepare a pharmacy checkout for a refill or supplies, checked "
                        "against the household's spending limit and recent orders. It "
                        "does not pay: payment is confirmed by the customer through "
                        "Alexa+ checkout."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "item": {"type": "string"},
                "asked_by": {"type": "string"},
                "quantity": {"type": "integer", "minimum": 1},
            },
            "required": ["item", "asked_by"],
        },
    },
    {
        "name": "catch_up",
        "title": "What did I miss",
        "description": ("Tell a family member what happened since they last asked: "
                        "doses, refusals, appointments, orders, new rules. Hearth "
                        "knows when each person last checked in, across sessions "
                        "and devices."),
        "inputSchema": {
            "type": "object",
            "properties": {"person": {"type": "string", "description": "Who is asking."}},
            "required": ["person"],
        },
    },
    {
        "name": "record",
        "title": "Show the record",
        "description": ("The server's own record of every tool call, newest first, "
                        "with its integrity check. Use when someone asks what the "
                        "assistant has done."),
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}},
        },
    },
]

_ANNOTATE = {
    "remember": _WRITE, "whats_true": _READ, "did": _WRITE, "why": _READ,
    "stand_down": {**_WRITE, "destructiveHint": True}, "end_context": _WRITE,
    "household": _READ, "check_dose": _READ, "give_dose": _WRITE,
    "arrange": _WORLD, "reorder": _WORLD, "catch_up": _READ, "record": _READ,
}
_VISUAL = {"whats_true", "why", "check_dose", "give_dose", "arrange", "reorder",
           "catch_up", "record"}
for _t in TOOLS:
    _t["annotations"] = {"title": _t["title"], **_ANNOTATE[_t["name"]]}
    if _t["name"] in _VISUAL:
        _t["_meta"] = _UI


class HearthMCP:
    """Dispatches MCP JSON-RPC against a Household and its Ledger."""

    def __init__(self, household, ledger, extractor=None, end_detector=None,
                 trace=None, care=None):
        from .care import Care, CareBook
        from .trace import Trace
        self.h = household
        self.ledger = ledger
        self.extract = extractor
        self.detect_end = end_detector
        self.trace = trace if trace is not None else Trace()
        self.care = care if care is not None else Care(household, ledger, CareBook())
        self.sessions: dict[str, float] = {}
        self._session = None
        self._now = None

    # --- session -----------------------------------------------------------
    def new_session(self) -> str:
        sid = uuid.uuid4().hex
        self.sessions[sid] = time.time()
        return sid

    # --- dispatch ----------------------------------------------------------
    def handle(self, msg: dict, session: str | None = None) -> dict | None:
        """Returns a JSON-RPC response, or None for a notification.

        Every tools/call is written to the trace before the response is
        returned, whatever it was and however it ended. That is what makes the
        ledger honest: the agent no longer decides what gets recorded.
        """
        if (isinstance(msg, dict) and msg.get("method") == "tools/call"
                and msg.get("jsonrpc") == "2.0"):
            return self._traced(msg, session)
        return self._dispatch(msg)

    def _traced(self, msg, session):
        t0 = time.perf_counter()
        params = msg.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        h, book = self.h, self.care.book
        before_b = {b.id: b.status for b in h.beliefs}
        before_a = len(self.ledger.actions)
        before_book = {k: len(getattr(book, k)) for k in book.KINDS}
        h.reads, self._session = [], session
        try:
            res = self._dispatch(msg)
        finally:
            reads, h.reads, self._session = list(dict.fromkeys(h.reads)), None, None
        writes = [b.id for b in h.beliefs if before_b.get(b.id) != b.status]
        for k in book.KINDS:
            writes += [x["id"] for x in getattr(book, k)[before_book[k]:]]
        new_actions = self.ledger.actions[before_a:]
        result = (res or {}).get("result") or {}
        if "error" in (res or {}):
            outcome, summary = "error", res["error"]["message"]
        else:
            refused = any(a.outcome == "refused" for a in new_actions)
            outcome = ("error" if result.get("isError") else
                       "refused" if refused else "ok")
            summary = ((result.get("content") or [{}])[0].get("text") or "")
        e = self.trace.append(
            tool=str(name), args=args if isinstance(args, dict) else {},
            outcome=outcome, summary=summary, session=session, reads=reads,
            writes=writes, action=new_actions[-1].id if new_actions else None,
            ms=(time.perf_counter() - t0) * 1000, at=self._now)
        # The receipt travels with the answer, so whatever draws the result can
        # show the entry it was written as, and anyone can check it later.
        if isinstance(result.get("structuredContent"), dict):
            result["structuredContent"]["record"] = {
                "seq": e.seq, "hash": e.hash[:12], "outcome": outcome}
        return res

    def _dispatch(self, msg: dict) -> dict | None:
        if msg.get("jsonrpc") != "2.0":
            return _err(msg.get("id"), -32600, "Invalid Request: jsonrpc must be '2.0'")
        method, rpc_id = msg.get("method"), msg.get("id")
        params = msg.get("params") or {}

        if method and method.startswith("notifications/"):
            return None                       # notifications get no response body
        if method == "initialize":
            return _ok(rpc_id, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False},
                                 "resources": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
                "instructions": (
                    "Hearth is the memory and the record of a household caring "
                    "for someone. Pass the name of whoever is speaking. Call "
                    "give_dose whenever anyone takes or gives a medicine and say "
                    "its answer as given: it refuses a dose over the limit. Call "
                    "whats_true before acting on anything the household may have "
                    "an opinion about, and why when asked to justify something. "
                    "If you act on a device Hearth does not control, call did "
                    "afterwards; it is filed as reported by you. Every call is "
                    "recorded by the server as it happens."),
            })
        if method == "ping":
            return _ok(rpc_id, {})
        if method == "tools/list":
            return _ok(rpc_id, {"tools": TOOLS})
        if method == "resources/list":
            return _ok(rpc_id, {"resources": [{
                "uri": CARD_URI, "name": "hearth-card", "title": "Hearth card",
                "description": "The card Hearth draws on a screen device.",
                "mimeType": APP_MIME}]})
        if method == "resources/read":
            if params.get("uri") != CARD_URI:
                return _err(rpc_id, -32002, "Resource not found",
                            {"uri": params.get("uri")})
            return _ok(rpc_id, {"contents": [{
                "uri": CARD_URI, "mimeType": APP_MIME, "text": _card_html(),
                "_meta": {"ui": {"csp": {"connectDomains": [], "resourceDomains": [],
                                         "frameDomains": [], "baseUriDomains": []},
                                 "prefersBorder": False}}}]})
        if method == "tools/call":
            name = params.get("name")
            args = params.get("arguments") or {}
            fn = getattr(self, f"_tool_{name}", None)
            if fn is None:
                return _err(rpc_id, -32602, f"Unknown tool: {name}")
            try:
                return _ok(rpc_id, fn(**args))
            except TypeError as e:
                return _err(rpc_id, -32602, f"Invalid arguments for {name}: {e}")
            except Exception as e:                       # tool errors are results,
                return _ok(rpc_id, {                     # not protocol errors
                    "content": [{"type": "text", "text": f"Hearth could not do that: {e}"}],
                    "isError": True})
        return _err(rpc_id, -32601, f"Method not found: {method}")

    # --- helpers -----------------------------------------------------------
    def _member_id(self, name):
        if not name:
            return None
        m = self.h.member_named(name)
        return m.id if m else None

    def _names(self):
        """Every name a member answers to, so "Rose" and "Mom" are one person.
        Pronouns are left out: "I" in a sentence is the speaker, not Mom."""
        out = {}
        for mid, m in self.h.members.items():
            out[m.name] = mid
            for a in m.aliases:
                if a.lower() not in ("i", "me", "my"):
                    out.setdefault(a, mid)
        return out

    # --- tools -------------------------------------------------------------
    def _open_contexts(self):
        return sorted({b.context for b in self.h.beliefs if b.context and b.is_live()})

    def _tool_remember(self, said, speaker):
        holder = self._member_id(speaker)
        if holder is None:
            holder = self.h.add_member(speaker).id      # a new voice in the house

        # A sentence can close a situation as easily as it can open one, and the
        # closing is the half that gets forgotten. Check it first: "Gran's gone
        # home" is not a new belief, it is the end of several old ones.
        ending = self.detect_end(said, self._open_contexts()) if self.detect_end else None
        if ending:
            return self._ended(ending, self.h.end_context(ending))

        found = (self.extract or (lambda t, n: []))(said, self._names())
        if not found:
            return _text(f"Nothing durable to remember in that, from {speaker}.")
        # A tool result is prose a model reads before it says something out
        # loud, so field names and hex ids in it are exactly what leaks into
        # what a person hears. The sentence is the answer; the id is metadata a
        # model needs only to stand a belief down later, so it goes at the end
        # where it reads as a reference rather than part of the reply.
        out = []
        cared = self.care.person()
        for b in found:
            value = str(b["value"]).replace("{speaker}", self.h.name_of(holder))
            scope = b.get("scope")
            if scope is None and cared and b["domain"].split(".")[0] in (
                    "diet", "medication"):
                # In a care household a rule about medicine or diet with no
                # name in it is about the person being cared for.
                scope = cared.id
            belief = self.h.assert_belief(
                holder, b["domain"], b["slot"], value, content=said,
                scope=scope, context=b.get("context"))
            b = {**b, "value": value}
            about = self.h.name_of(belief.scope) if belief.scope else None
            line = phrasing.statement(b["domain"], b["slot"], b["value"], about)
            if belief.context:
                line += f" That holds only while {belief.context} lasts."
            out.append(f"{line} [{belief.id}]")
        # Possessed through phrasing, so the text Alexa+ is handed and the line
        # the console shows cannot disagree about somebody's name.
        return _text(f"Noted, on {phrasing.possessive(speaker)} word. "
                     + " ".join(out))

    def _tool_whats_true(self, domain, slot, about=None):
        mid = self._member_id(about)
        r = self.h.resolve(domain, slot, for_member=mid,
                           name_domain=phrasing.domain_label)
        if r.winner is None:
            return _text("Nobody has set "
                         + phrasing.subject(domain, slot, mid)
                         + ".")
        named = self.h.name_of(mid) if about and mid else None
        line = (phrasing.statement(domain, slot, r.winner.value, named)
                + " " + r.explain(self.h.name_of, say=phrasing.value_spoken))
        d = phrasing.describe(domain, slot, r.winner.value, named)
        items = [{"label": self.h.name_of(r.winner.holder),
                  "detail": phrasing.said(domain, slot, r.winner.value,
                                          r.winner.content),
                  "meta": carelib.when_said(r.winner.stated_at)
                          + (f", during {r.winner.context}" if r.winner.context else ""),
                  "status": "won"}]
        items += [{"label": self.h.name_of(b.holder),
                   "detail": phrasing.said(b.domain, b.slot, b.value, b.content),
                   "meta": why, "status": "lost"} for b, why in r.losers[:3]]
        v = phrasing.verdict(r.basis, winner=self.h.name_of(r.winner.holder),
                             about=named, domain=domain, slot=slot)
        return _text(line, {"pattern": "card", "tone": "info",
                            "eyebrow": d["title"], "title": d["reading"],
                            "body": v["line"] or d["statement"], "items": items})

    def _tool_did(self, what, domain, slot, about=None):
        """The agent reporting an action it took outside Hearth.

        Kept, because Alexa+ will act on devices Hearth never touches. But it
        is filed as reported, not performed, and Hearth checks its own record
        of this session for whether the agent asked before it acted. "Why did
        you do that?" then says so if it did not.
        """
        r = self.h.resolve(domain, slot, for_member=self._member_id(about),
                           name_domain=phrasing.domain_label)
        checked = self.trace.consulted(domain, slot, self._session) is not None
        a = self.ledger.record(what, domain, resolution=r, source="reported",
                               checked=checked, at=self._now)
        # Report the value it acted on, not just the verb. "Done, set the
        # thermostat" tells the household nothing they did not already know,
        # and the number is the part they would repeat back.
        if r.winner is None:
            return _text(f"Done. {what.capitalize()}.")
        return _text("Done. "
                     + phrasing.statement(domain, slot, r.winner.value,
                                          self.h.name_of(self._member_id(about))
                                          if about else None)
                     + ("" if checked else
                        " Noted that I was not asked before this was done."))

    def _tool_why(self, domain=None):
        a = (self.ledger.last(domain) if domain else self.ledger.last())
        if a is None and domain:
            # "why did you stop her?" arrives with whatever domain the model
            # guessed, and a guess that misses should still find the answer.
            a = next((x for x in reversed(self.ledger.actions)
                      if x.domain.startswith(domain) or domain in x.domain), None)
            a = a or self.ledger.last()
        line = self.ledger.why(action_id=a.id) if a else self.ledger.why()
        card = None
        if a is not None:
            w = a.resolution.winner if a.resolution else None
            items = []
            if w:
                items.append({"label": f"{self.h.name_of(w.holder)} said",
                              "detail": phrasing.said(w.domain, w.slot, w.value,
                                                      w.content),
                              "meta": carelib.when_said(w.stated_at),
                              "status": "won"})
                for lb, why in a.resolution.losers[:2]:
                    items.append({"label": f"{self.h.name_of(lb.holder)} said",
                                  "detail": phrasing.said(lb.domain, lb.slot,
                                                          lb.value, lb.content),
                                  "meta": why, "status": "lost"})
            if a.note:
                items.append({"label": "On the record", "detail": a.note,
                              "status": "info"})
            card = {"pattern": "list", "tone": "stop" if a.outcome == "refused" else "info",
                    "eyebrow": "Why", "title": f"I {a.what}",
                    "items": items,
                    "footer": ("Taken by Hearth and recorded at the time"
                               if a.source == "hearth" else
                               "Reported by the assistant"
                               + ("" if a.checked else ", without asking first"))}
        return _text(line, card)

    def _tool_stand_down(self, belief_id, reason="a member stood it down"):
        b = self.h.retire(belief_id, reason=reason)
        if b is None:
            return _text("No standing belief has that reference.")
        # The reason travels with the retirement. Someone asking later why the
        # house changed its mind gets "Dad changed his mind" rather than a
        # silent disappearance, which is the same promise the action ledger
        # makes about everything else.
        return _text(f"Stood down, {reason}. "
                     f"{phrasing.statement(b.domain, b.slot, b.value)} "
                     "no longer applies.")

    def _tool_end_context(self, context):
        if not context:
            # Said out loud, "Nothing was riding on None" is worse than useless.
            # A model that calls this without naming a situation gets asked.
            return _text("Which situation ended?")
        ended = self.h.end_context(context)
        if not ended:
            return _text(f"Nothing was riding on {context}.")
        return self._ended(context, ended)

    def _ended(self, context, ended):
        """What the house says when a situation closes, naming who each rule
        was about: "Mom's alcohol is off limits", never "the alcohol"."""
        # Each rule is named with whose it was, so the family hears what has
        # stopped and on whose word it had been holding.
        def rule(b):
            said = phrasing.statement(b.domain, b.slot, b.value,
                                      self.h.name_of(b.scope) if b.scope else None)
            said = said.rstrip(".")
            if said.startswith("The "):
                said = "the " + said[4:]
            return f"{self.h.name_of(b.holder)}'s rule that {said} no longer applies."
        return _text(f"Understood, {context} {phrasing.is_are(context)} over. "
                     + " ".join(rule(b) for b in ended))

    def _tool_household(self):
        lines = [f"{m.name} ({m.role}"
                 + (f", owns {', '.join(m.grants)}" if m.grants else "") + ")"
                 for m in self.h.members.values()]
        live = [b for b in self.h.beliefs if b.is_live()]
        lines += [f"  {b.domain}.{b.slot} = {b.value} from {self.h.name_of(b.holder)}"
                  + (f" [{b.context}]" if b.context else "") for b in live]
        return _text("\n".join(lines) or "Nobody has said anything yet.")

    # --- the care household ------------------------------------------------
    def _dose_items(self, st):
        return [{"label": f"{self.care._name_id(d['given_by'])} gave it",
                 "detail": carelib.when_said(d["at"], self._now).capitalize(),
                 "status": "done"} for d in st["given"]]

    def _rule_meta(self, st):
        w = st["per_day"].winner
        if not w:
            return "Nobody has told me how often it is taken."
        return (f"{self.h.name_of(w.holder)} set it to "
                f"{phrasing.spoken(w.domain, w.slot, w.value)}, "
                f"{carelib.when_said(w.stated_at, self._now)}")

    def _tool_check_dose(self, medication, person=None, asked_by=None):
        st = self.care.dose_status(medication, person, self._now)
        who, med = st["person"], st["medication"]
        her = who.name if who else "They"
        if not st["given"]:
            line = f"No, {her} has not had {med} today."
            if st["due"].winner:
                line += (" It is due at "
                         + phrasing.spoken("meals", "x", st["due"].winner.value) + ".")
        else:
            last = st["given"][-1]
            line = (f"Yes. {self.care._name_id(last['given_by'])} gave {her} "
                    f"{med} {carelib.when_said(last['at'], self._now)}.")
            if st["remaining"] == 0:
                line += " That is today's dose, so not another until tomorrow."
            elif st["remaining"]:
                line += f" {st['remaining']} more allowed today."
        tone = "ok" if st["given"] else "warn"
        return _text(line, {
            "pattern": "card", "tone": tone, "eyebrow": f"{her} · {med}",
            "title": ("Taken today" if st["given"] else "Not taken yet today"),
            "body": self._rule_meta(st), "items": self._dose_items(st)},
            medication=med, given_today=len(st["given"]), limit=st["limit"])

    def _tool_give_dose(self, medication, given_by, person=None):
        st = self.care.give(medication, given_by, person, now=self._now)
        who, med = st["person"], st["medication"]
        her = who.name if who else "them"
        self_given = bool(who and who.answers_to(given_by))
        if st["outcome"] == "refused":
            name = who.aliases[0] if (self_given and who.aliases) else ""
            line = (f"Hold on{', ' + name if name else ''}. {st['spoken_note']} "
                    f"{'Your' if self_given else phrasing.possessive(her)} {med} is "
                    f"{phrasing.spoken('medication', 'per_day', str(st['limit']))}, "
                    f"so not another until tomorrow.")
            return _text(line, {
                "pattern": "card", "tone": "stop", "eyebrow": f"{her} · {med}",
                "title": "Already taken today",
                "body": "Not another until tomorrow.",
                "items": self._dose_items(st) + [{
                    "label": "The rule", "detail": self._rule_meta(st),
                    "meta": (phrasing.said("", "", "", st["per_day"].winner.content)
                             if st["per_day"].winner and st["per_day"].winner.content
                             else None),
                    "status": "info"}],
                "footer": "Second dose stopped by Hearth and recorded"},
                outcome="refused", medication=med)
        line = (f"Logged. {phrasing.possessive(her)} {med}, given by "
                f"{self.care._name(given_by)} "
                f"{carelib.when_said(st['dose']['at'], self._now)}.")
        if st["limit"] is None:
            line += " Nobody has told me how often it is taken, so I cannot check the limit."
        elif st["remaining"] == 0:
            line += " That is all for today."
        return _text(line, {
            "pattern": "card", "tone": "ok", "eyebrow": f"{her} · {med}",
            "title": "Dose logged", "body": self._rule_meta(st),
            "items": self._dose_items(st)}, outcome="done", medication=med)

    def _tool_arrange(self, what, when, asked_by, person=None, where=None):
        out = self.care.arrange(what, when, asked_by, person, where, now=self._now)
        a, who = out["appointment"], out["person"]
        her = who.name if who else "them"
        # Said shorter than it is drawn: the card lists every service, the
        # voice says what changed and anything somebody now has to do.
        day = carelib.local(a["at"]).strftime("%A")
        speech = f"Done. {phrasing.possessive(her)} {a['what']} is now {day} at {carelib.clock(a['at'])}."
        if out["escort"]:
            speech += (f" {out['escort']} is taking {her}, since {out['escort']} "
                       f"does {day}s.")
        cancelled = any(s["service"] == "rides" and s["line"].startswith("Cancelled")
                        for s in out["steps"])
        told = next((s["line"] for s in out["steps"] if s["service"] == "board"), "")
        speech += (f" I {'cancelled the old ride, ' if cancelled else ''}booked a ride "
                   f"for {carelib.clock(out['ride']['pickup'])}, and "
                   + told[:1].lower() + told[1:])
        for s in out["steps"]:
            if s["status"] == "needs_attention":
                speech += " " + s["line"]
        return _text(speech, {
            "pattern": "list", "tone": "ok", "eyebrow": "Sorted",
            "title": f"{phrasing.possessive(her)} {a['what']}, "
                     f"{carelib.local(a['at']).strftime('%A')} {carelib.clock(a['at'])}",
            "items": [{"label": s["service"].title(), "detail": s["line"],
                       "status": s["status"]} for s in out["steps"]],
            "footer": f"{len(out['steps'])} services, one request. "
                      "Rides are a sandbox provider."},
            steps=out["steps"], appointment=a["id"])

    def _tool_reorder(self, item, asked_by, quantity=1):
        q = self.care.reorder(item, asked_by, quantity, now=self._now)
        price = f"${q['total'] / 100:.2f}"
        errors = [m for m in q["messages"] if m["type"] == "error"]
        warns = [m for m in q["messages"] if m["type"] == "warning"]
        if errors:
            line = f"{q['title']} is {price}. {errors[0]['content']}"
        else:
            line = (f"{q['title']}, {price} from the {carelib.PHARMACY}, "
                    f"delivered tomorrow."
                    + (f" Note: {warns[0]['content']}" if warns else "")
                    + " Shall I place the order?")
        card = {"pattern": "card", "tone": "stop" if errors else
                ("warn" if warns else "info"),
                "eyebrow": "Pharmacy · sandbox", "title": q["title"],
                "body": price + " · delivered tomorrow",
                "items": [{"label": m["type"].title(), "detail": m["content"],
                           "status": "lost" if m["type"] == "error" else "info"}
                          for m in q["messages"]]
                         + [{"label": "Checked", "detail": c, "status": "done"}
                            for c in q.get("checks", [])]
                         + ([] if errors else [{
                             "label": "Paid through Alexa+",
                             "detail": "Voice PIN and the card on the account. "
                                       "Hearth never charges it.",
                             "status": "info"}])}
        # What Alexa+ needs to open the checkout itself when the customer says
        # yes or taps Pay: the line items, by catalogue id, and the quote they
        # came from. The price is not passed; the merchant owns it.
        checkout = {"line_items": [{"item": {"id": q["sku"]}, "quantity": q["quantity"]}],
                    "quote": q["id"]}
        if not errors:
            card["cta"] = {"label": f"Pay {price}", "message": "Pay for this order",
                           "checkout": checkout}
        return _text(line, card, checkout=checkout, approved=not errors,
                     total=q["total"], currency="USD")

    def _tool_catch_up(self, person):
        # When this person last talked to the house: the last call made on
        # their behalf, or the last thing they said that became a rule,
        # whichever is later. Both are Hearth's own record, across sessions.
        me = self.h.member_named(person)
        last = self.trace.last_by(person)
        marks = [last.at] if last else []
        if me:
            marks += [b.stated_at for b in self.h.beliefs if b.holder == me.id]
        since = max(marks) if marks else (self._now or time.time()) - 7 * 86400
        items = self.care.catch_up(person, since, now=self._now)
        name = me.name if me else str(person).title()
        when = carelib.when_said(since, self._now)
        if not items:
            line = f"Nothing new since you last checked in, {when}."
        else:
            line = (f"Since you last checked in, {when}: "
                    + " ".join(i["line"] for i in items))
        return _text(line, {
            "pattern": "list", "tone": "info", "eyebrow": f"For {name}",
            "title": "While you were away",
            "body": f"Since {when}",
            "items": [{"label": carelib.when_said(i["at"], self._now).capitalize(),
                       "detail": i["line"],
                       "status": "lost" if i["outcome"] == "refused" else "done"}
                      for i in items]}, since=since, count=len(items))

    def _tool_record(self, limit=10):
        ok, bad = self.trace.verify()
        recent = list(reversed(self.trace.entries))[:max(1, min(int(limit or 10), 50))]
        refused = sum(1 for e in self.trace.entries if e.outcome == "refused")
        n = len(self.trace.entries)
        calls = f"{n} call" if n == 1 else f"{n} calls"
        line = (f"{calls} on the record, "
                + (f"{refused} refused, " if refused else "")
                + ("and the chain is intact: nothing has been edited or removed."
                   if ok else f"and the chain is broken at entry {bad}."))
        return _text(line, {
            "pattern": "list", "tone": "ok" if ok else "stop",
            "eyebrow": "The record", "title": calls.capitalize(),
            "body": "Written by the server as each call happened. "
                    + ("Integrity check passed." if ok else f"Broken at #{bad}."),
            "items": [{"label": f"#{e.seq} {e.tool}", "detail": e.summary[:120],
                       "meta": carelib.when_said(e.at, self._now),
                       "status": {"ok": "done", "refused": "lost"}.get(e.outcome, "info")}
                      for e in recent]}, intact=ok)
