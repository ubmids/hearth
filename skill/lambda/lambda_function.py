"""Hearth as a classic Alexa custom skill: a real MCP client of Hearth's /mcp.

Alexa+ add-on tools are partner-only, so this is the route to a real Echo:
a classic custom skill (ASK SDK for Python) whose handler is an MCP client.
Alexa's own NLU picks the intent and fills the slots; each intent becomes one
Hearth `tools/call` over Streamable HTTP; the skill says Hearth's text
verbatim and, on a device with a screen, draws Hearth's card in APL.
Anything no intent matches goes to Hearth's planner and then to the tools it
names, so the skill never writes an answer of its own. The only words it
composes are the ones a host owns: the launch and help lines, the
checkout confirmation, and the safety line when Hearth cannot be reached.

Configuration, by environment variable or `config.json` beside this file:
  HEARTH_URL              https://your-hearth.example (no trailing /mcp)
  HEARTH_TOKEN            the value of HEARTH_SKILL_TOKEN on the server
  HEARTH_DEFAULT_SPEAKER  who is talking when nobody is recognised (Rose)
  HEARTH_CARED_FOR        who "Mom" is, for questions about her (Mom)
  HEARTH_DEVICES          JSON {deviceId: name}, e.g. Tom's Echo Dot -> Tom
  HEARTH_PEOPLE           JSON {personId: name}, from Alexa voice profiles
"""
from __future__ import annotations

import json
import os
import time

from ask_sdk_core.dispatch_components import AbstractExceptionHandler
from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.utils import (get_slot, get_supported_interfaces,
                                is_intent_name, is_request_type)
from ask_sdk_model.interfaces.alexa.presentation.apl import RenderDocumentDirective

import apl
from hearth_client import Hearth, HearthError, spoken_text

_HERE = os.path.dirname(os.path.abspath(__file__))


def config() -> dict:
    cfg = {}
    path = os.path.join(_HERE, "config.json")
    if os.path.exists(path):
        with open(path) as f:
            cfg = json.load(f)
    def get(key, default=""):
        return os.getenv(key) or cfg.get(key) or default
    def mapping(key):
        v = get(key, {})
        return json.loads(v) if isinstance(v, str) and v else (v or {})
    return {"url": get("HEARTH_URL"), "token": get("HEARTH_TOKEN"),
            "default_speaker": get("HEARTH_DEFAULT_SPEAKER", "Rose"),
            "cared_for": get("HEARTH_CARED_FOR", "Mom"),
            "devices": mapping("HEARTH_DEVICES"), "people": mapping("HEARTH_PEOPLE")}


# --- who is talking -----------------------------------------------------
def speaker_of(handler_input, cfg) -> str:
    """Recognised voice first (a classic skill gets `context.System.person`
    when personalisation is on, which Alexa+ add-ons do not: friction log
    entry 8), then "this is Tom" earlier in the session, then whose device
    it is, then the household default."""
    env = handler_input.request_envelope
    system = env.context.system
    person = getattr(system, "person", None)
    if person is not None and getattr(person, "person_id", None) in cfg["people"]:
        return cfg["people"][person.person_id]
    attrs = handler_input.attributes_manager.session_attributes
    if attrs.get("speaker"):
        return attrs["speaker"]
    device = getattr(system.device, "device_id", None) if system.device else None
    if device in cfg["devices"]:
        return cfg["devices"][device]
    return cfg["default_speaker"]


def slot(handler_input, name) -> str:
    s = get_slot(handler_input, name)
    if s is None or not s.value:
        return ""
    # A resolved synonym ("Coumadin" -> warfarin) when Alexa found one, else
    # the words as heard. Hearth normalises either way.
    try:
        for r in s.resolutions.resolutions_per_authority or []:
            if r.status.code.value == "ER_SUCCESS_MATCH" and r.values:
                return r.values[0].value.name
    except AttributeError:
        pass
    return s.value


# --- intent -> Hearth tool call ------------------------------------------
def calls_for(intent: str, h, who: str, cfg) -> list[dict]:
    mom = cfg["cared_for"]
    if intent == "GiveDoseIntent":
        return [{"name": "give_dose", "arguments": {
            "medication": slot(h, "medication") or "blood thinner", "given_by": who}}]
    if intent == "CheckDoseIntent":
        return [{"name": "check_dose", "arguments": {
            "medication": slot(h, "medication") or "blood thinner", "asked_by": who}}]
    if intent == "CatchUpIntent":
        return [{"name": "catch_up", "arguments": {"person": who}}]
    if intent == "WhyIntent":
        return [{"name": "why", "arguments": {"domain": "medication"}}]
    if intent == "ArrangeIntent":
        day, at = slot(h, "day"), slot(h, "time")
        if len(day) == 10 and day[4] == "-" and at[:2].isdigit():
            when = f"{day}T{at}"                  # ISO, local to the household
        else:
            when = " at ".join(x for x in (day, at) if x) or "tomorrow at 10am"
        return [{"name": "arrange", "arguments": {
            "what": slot(h, "appointment") or "appointment", "when": when,
            "asked_by": who}}]
    if intent == "ReorderIntent":
        return [{"name": "reorder", "arguments": {
            "item": slot(h, "item") or "warfarin", "asked_by": who}}]
    if intent == "CanHaveIntent":
        thing = (slot(h, "thing") or "").lower()
        rule = "coffee_cutoff" if "coffee" in thing else "alcohol"
        return [{"name": "whats_true", "arguments": {
            "domain": "diet", "slot": rule, "about": mom}}]
    if intent == "RecordIntent":
        return [{"name": "record", "arguments": {"limit": 8}}]
    if intent == "HandoverIntent":
        return [{"name": "handover", "arguments": {
            "note": slot(h, "note") or "", "given_by": who}}]
    if intent == "ShoppingListIntent":
        item = slot(h, "item")
        return [{"name": "shopping_list", "arguments": (
            {"add": item, "asked_by": who} if item else {"asked_by": who})}]
    if intent == "OrderListIntent":
        return [{"name": "reorder", "arguments": {"item": "the list", "asked_by": who}}]
    return []


# --- answering --------------------------------------------------------------
def client(handler_input, cfg) -> Hearth:
    attrs = handler_input.attributes_manager.session_attributes
    return Hearth(cfg["url"], cfg["token"], session_id=attrs.get("mcp_session"))


def answer(handler_input, speech: str, card: dict | None = None,
           record: dict | None = None, keep_open: bool = True):
    rb = handler_input.response_builder
    rb.speak(_ssml_safe(speech))
    if card and _has_screen(handler_input):
        d = apl.directive(card, record)
        rb.add_directive(RenderDocumentDirective(
            token=d["token"], document=d["document"], datasources=d["datasources"]))
    if keep_open:
        rb.set_should_end_session(False)
    else:
        rb.set_should_end_session(True)
    return rb.response


def _has_screen(handler_input) -> bool:
    try:
        return get_supported_interfaces(handler_input).alexa_presentation_apl is not None
    except AttributeError:
        return False


def _ssml_safe(text: str) -> str:
    return text.replace("&", " and ").replace("<", " ").replace(">", " ")


def run(handler_input, calls: list[dict], who: str, cfg):
    """Make the calls, speak what Hearth said, draw the last card."""
    attrs = handler_input.attributes_manager.session_attributes
    hearth = client(handler_input, cfg)
    spoken, card, record = [], None, None
    t0 = time.perf_counter()
    for c in calls:
        if c.get("host") == "checkout.complete":
            text, card = pay(hearth, attrs.get("checkout"), who)
            attrs.pop("checkout", None)
            spoken.append(text)
            continue
        result = hearth.call_tool(c["name"], c["arguments"])
        spoken.append(spoken_text(result))
        sc = result.get("structuredContent") or {}
        if sc.get("card"):
            card, record = sc["card"], sc.get("record")
        if sc.get("checkout") and sc.get("approved"):
            attrs["checkout"] = sc["checkout"]       # "yes" pays for it
    attrs["mcp_session"] = hearth.session_id
    system = handler_input.request_envelope.context.system
    # deviceId and personId are logged so they can be mapped to names in
    # HEARTH_DEVICES and HEARTH_PEOPLE: CloudWatch is where to find them.
    print(json.dumps({"hearth": [c.get("name") or c.get("host") for c in calls],
                      "speaker": who, "ms": round((time.perf_counter() - t0) * 1000),
                      "device": getattr(system.device, "device_id", None)
                      if system.device else None,
                      "person": getattr(getattr(system, "person", None),
                                        "person_id", None)}))
    return answer(handler_input, " ".join(s for s in spoken if s) or
                  "Hearth had nothing to say to that.", card, record)


def pay(hearth: Hearth, hint: dict | None, who: str):
    """The host's step in checkout. Alexa+ would take the voice PIN and the
    card; a classic skill cannot, so this completes the sandbox merchant's
    session with a sandbox token and says so on the screen."""
    if not hint:
        return "There is nothing waiting to be paid for.", None
    s = hearth.checkout(hint, who)
    if s.get("status") != "completed":
        return ((s.get("messages") or [{}])[0].get("content")
                or "I could not place that order."), None
    total = next(t["amount"] for t in s["totals"] if t["type"] == "total")
    title = s["line_items"][0]["item"]["title"]
    card = {"pattern": "card", "tone": "ok", "eyebrow": "Order placed · sandbox",
            "title": title, "body": f"${total / 100:.2f} · arriving tomorrow",
            "items": [{"label": "Order", "detail": s.get("order_id", ""), "status": "done"},
                      {"label": "Family board", "detail": "Everyone has been told.",
                       "status": "done"}],
            "footer": "Sandbox merchant: no payment was taken"}
    return (f"Done. {title} is ordered, {total // 100} dollars {total % 100:02d}, "
            f"arriving tomorrow. I've told the family."), card


# --- handlers ------------------------------------------------------------
sb = SkillBuilder()
INTENTS = ("GiveDoseIntent", "CheckDoseIntent", "CatchUpIntent", "WhyIntent",
           "ArrangeIntent", "ReorderIntent", "CanHaveIntent", "RecordIntent",
           "HandoverIntent", "ShoppingListIntent", "OrderListIntent")


@sb.request_handler(can_handle_func=is_request_type("LaunchRequest"))
def launch(handler_input):
    who = speaker_of(handler_input, config())
    return answer(handler_input, f"Hearth here. Go ahead, {who}.")


@sb.request_handler(can_handle_func=lambda h: any(is_intent_name(i)(h) for i in INTENTS))
def tool_intent(handler_input):
    cfg = config()
    who = speaker_of(handler_input, cfg)
    intent = handler_input.request_envelope.request.intent.name
    return run(handler_input, calls_for(intent, handler_input, who, cfg), who, cfg)


@sb.request_handler(can_handle_func=is_intent_name("RememberIntent"))
def remember_or_plan(handler_input):
    """Everything else: Hearth's planner decides which tools, then the
    skill calls them. A household statement ends up at `remember`."""
    cfg = config()
    who = speaker_of(handler_input, cfg)
    said = slot(handler_input, "statement")
    if not said:
        return answer(handler_input, "Sorry, I didn't catch that.")
    attrs = handler_input.attributes_manager.session_attributes
    hearth = client(handler_input, cfg)
    try:
        calls = hearth.plan(said, who, {"checkout": attrs.get("checkout")})["calls"]
    except HearthError:
        calls = [{"name": "remember", "arguments": {"said": said, "speaker": who}}]
    return run(handler_input, calls, who, cfg)


@sb.request_handler(can_handle_func=is_intent_name("IAmIntent"))
def i_am(handler_input):
    name = slot(handler_input, "name").strip().title()
    if name:
        handler_input.attributes_manager.session_attributes["speaker"] = name
    return answer(handler_input, f"Hello, {name}." if name else "Who is this?")


@sb.request_handler(can_handle_func=is_intent_name("AMAZON.YesIntent"))
def yes(handler_input):
    cfg = config()
    attrs = handler_input.attributes_manager.session_attributes
    if not attrs.get("checkout"):
        return answer(handler_input, "There is nothing waiting for a yes.")
    return run(handler_input, [{"host": "checkout.complete"}],
               speaker_of(handler_input, cfg), cfg)


@sb.request_handler(can_handle_func=is_intent_name("AMAZON.NoIntent"))
def no(handler_input):
    handler_input.attributes_manager.session_attributes.pop("checkout", None)
    return answer(handler_input, "All right, I won't order it.")


@sb.request_handler(can_handle_func=is_intent_name("AMAZON.HelpIntent"))
def help_(handler_input):
    return answer(handler_input,
                  "Tell me when someone takes or gives a medicine, ask what you "
                  "missed, or tell me a family rule, and I'll check it with Hearth.")


@sb.request_handler(can_handle_func=lambda h: any(is_intent_name(i)(h) for i in (
    "AMAZON.CancelIntent", "AMAZON.StopIntent", "AMAZON.NavigateHomeIntent")))
def stop(handler_input):
    return answer(handler_input, "Okay.", keep_open=False)


@sb.request_handler(can_handle_func=is_intent_name("AMAZON.FallbackIntent"))
def fallback(handler_input):
    return answer(handler_input, "Sorry, I didn't catch that. Say it another way?")


@sb.request_handler(can_handle_func=is_request_type("SessionEndedRequest"))
def ended(handler_input):
    return handler_input.response_builder.response


class Unreachable(AbstractExceptionHandler):
    """Hearth down, or a credential wrong. For a dose, the safe answer is to
    wait, never to guess, so that is what the skill says."""

    def can_handle(self, handler_input, exception):
        return True

    def handle(self, handler_input, exception):
        print(json.dumps({"error": str(exception)[:300]}))
        req = handler_input.request_envelope.request
        intent = getattr(getattr(req, "intent", None), "name", "")
        if intent == "GiveDoseIntent":
            line = ("I can't reach Hearth to check today's doses, so please don't "
                    "take it until someone has checked.")
        else:
            line = "I can't reach Hearth just now. Please try again in a minute."
        return answer(handler_input, line, keep_open=False)


sb.add_exception_handler(Unreachable())
lambda_handler = sb.lambda_handler()
