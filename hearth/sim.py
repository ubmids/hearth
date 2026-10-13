"""The simulated Alexa+ client's two server-side helpers: a planner and a voice.

SIMULATED. Alexa+ itself is not available to hackathon entrants (the MCP
toolkit is "available to select partners only"), so the page at /alexa stands
in for it. The page is a real MCP client: it authorises with OAuth 2.1 + PKCE,
sends initialize, tools/list, resources/read and tools/call over Streamable
HTTP to /mcp, and draws Hearth's MCP App card the way an Echo Show would. What
it cannot do is be Alexa's language model, so two things live here:

  plan()   which tool calls an utterance becomes. A model when one is
           configured (any OpenAI-compatible endpoint, with Hearth's real
           tools/list as its function list), else a deterministic intent
           router that covers the demo's sentences. The page shows which.
  speak()  a voice. Amazon Polly neural when AWS credentials are set, else
           Piper (offline, neural, CPU) when a voice model is configured,
           else nothing, and the page falls back to the browser's own voice.

Neither is on the MCP path. Every word the assistant says comes back from
Hearth's tools; the planner only decides which tools to call.
"""
import datetime as dt
import hashlib
import hmac
import io
import json
import os
import re
import wave

from .care import MED_ALIASES

# --- planning ---------------------------------------------------------------
MEDS = r"(warfarin|blood thinners?|tablets?|pills?|medicines?|medication|metformin|furosemide|metoprolol|water pills?|heart pills?|dose)"
ITEMS = r"(warfarin|blood thinners?|ensure|pill organi[sz]er|furosemide|metformin|metoprolol|tablets|pills)"
APPTS = r"(cardiology|cardiologist|dentist|doctor|podiatrist|eye clinic|appointment|check-?up|physio\w*|hospital)"


def _med(text: str) -> str:
    low = text.lower()
    for alias, med in MED_ALIASES.items():
        if alias in low:
            return med
    m = re.search(r"\b(warfarin|metformin|furosemide|metoprolol)\b", low)
    return m.group(1) if m else "warfarin"


def plan_rules(said: str, speaker: str, context: dict | None = None) -> list[dict]:
    """Utterance to tool calls, for the sentences a care household says most.

    Deliberately small and readable: it is the stand-in for Alexa's model in a
    demo, not a product, and anything it does not recognise goes to `remember`,
    which is what an assistant should do with a household statement anyway.
    """
    s = said.strip()
    low = s.lower().rstrip("?.! ")
    ctx = context or {}

    if re.search(r"\b(what did i miss|catch me up|what'?s new|anything (?:new|happen)|how(?:'s| is) (?:mom|mum|she) (?:doing|been))\b", low):
        return [{"name": "catch_up", "arguments": {"person": speaker}}]
    if re.search(r"\bwhy\b", low):
        dom = ("medication" if re.search(MEDS + r"|\bstop", low) else
               "diet" if re.search(r"coffee|wine|alcohol", low) else
               "thermostat" if re.search(r"warm|cold|thermostat|heat", low) else None)
        return [{"name": "why", "arguments": {"domain": dom} if dom else {}}]
    if re.search(r"\b(what have you done|show (?:me )?the record|the record)\b", low):
        return [{"name": "record", "arguments": {"limit": 8}}]
    if ctx.get("checkout") and re.fullmatch(r"(yes|yeah|yep|go ahead|do it|place (?:the|it)|please do|ok(?:ay)?|sure|pay)[\w ,]*", low):
        return [{"host": "checkout.complete", "checkout": ctx["checkout"]}]
    if re.search(r"\b(has|did|have)\b.*\b(had|taken|take|got)\b", low) and re.search(MEDS, low):
        return [{"name": "check_dose", "arguments": {"medication": _med(low),
                                                      "asked_by": speaker}}]
    if (re.search(r"\b(take|taking|took|give|giving|gave|have|having)\b", low)
            and re.search(MEDS, low) and not re.search(r"\ba day\b|\bdaily\b", low)):
        return [{"name": "give_dose", "arguments": {"medication": _med(low),
                                                     "given_by": speaker}}]
    if re.search(r"\b(re-?order|order more|running (?:low|out)|nearly out|almost out|need more|down to)\b", low):
        m = re.search(ITEMS, low)
        item = m.group(1) if m else "warfarin"
        qty = 2 if re.search(r"\b(two|2)\s+(?:packs|cases|boxes)\b", low) else 1
        return [{"name": "reorder", "arguments": {"item": _med(item) if re.search(MEDS, item) else item,
                                                   "asked_by": speaker, "quantity": qty}}]
    m = re.search(APPTS, low)
    if m and re.search(r"\b(moved|move|book|reschedul\w*|changed|is now|sort)\b", low):
        when = re.search(r"\b((?:on )?(?:mon|tues|wednes|thurs|fri|satur|sun)day(?: at [\w:. ]+?)?|tomorrow(?: at [\w:. ]+?)?|at \d[\w:. ]*?)(?:[,.]|\bsort\b|$)", low)
        what = {"cardiologist": "cardiology", "appointment": "appointment"}.get(m.group(1), m.group(1))
        return [{"name": "arrange", "arguments": {
            "what": what, "when": (when.group(1) if when else "tomorrow at 10am").removeprefix("on "),
            "asked_by": speaker}}]
    if re.search(r"\b(can|could|may)\b.*\b(have|get)\b.*\bcoffee\b", low):
        return [{"name": "whats_true", "arguments": {"domain": "diet", "slot": "coffee_cutoff",
                                                      "about": "Mom"}}]
    if re.search(r"\b(can|could|may)\b.*\b(have|get)\b.*\b(wine|beer|drink|alcohol)\b", low):
        return [{"name": "whats_true", "arguments": {"domain": "diet", "slot": "alcohol",
                                                      "about": "Mom"}}]
    if re.search(r"\b(who'?s|who is) taking\b", low) or re.search(r"\bwhen is\b.*" + APPTS, low):
        return [{"name": "catch_up", "arguments": {"person": speaker}}]
    return [{"name": "remember", "arguments": {"said": s, "speaker": speaker}}]


PLANNER_SYSTEM = (
    "You are standing in for Alexa+ in a home caring for an elderly parent. "
    "Given who is speaking and what they said, call the Hearth tools that "
    "fulfil it. Always pass the speaker's name where a tool asks who. Prefer "
    "one tool call; use more only if the request needs them. Never answer "
    "without a tool.")


def plan_model(said, speaker, tools, context=None):
    """Plan with any OpenAI-compatible model, using Hearth's own tool list.

    Returns None when no model is configured or the call fails, and the caller
    falls back to the rules. Configured by HEARTH_SIM_LLM_BASE_URL / _API_KEY /
    _MODEL, falling back to the extraction model's HEARTH_LLM_* settings.
    """
    base = os.getenv("HEARTH_SIM_LLM_BASE_URL") or os.getenv("HEARTH_LLM_BASE_URL")
    key = os.getenv("HEARTH_SIM_LLM_API_KEY") or os.getenv("HEARTH_LLM_API_KEY")
    model = (os.getenv("HEARTH_SIM_LLM_MODEL") or os.getenv("HEARTH_LLM_MODEL")
             or "gpt-4o-mini")
    if not (base and key):
        return None
    try:
        import httpx
        fns = [{"type": "function", "function": {
            "name": t["name"], "description": t["description"],
            "parameters": t["inputSchema"]}} for t in tools]
        r = httpx.post(f"{base.rstrip('/')}/chat/completions",
                       headers={"Authorization": f"Bearer {key}"},
                       json={"model": model, "temperature": 0, "tools": fns,
                             "messages": [
                                 {"role": "system", "content": PLANNER_SYSTEM},
                                 {"role": "user",
                                  "content": f"{speaker} says: {said}"}]},
                       timeout=12.0)
        r.raise_for_status()
        calls = r.json()["choices"][0]["message"].get("tool_calls") or []
        out = [{"name": c["function"]["name"],
                "arguments": json.loads(c["function"].get("arguments") or "{}")}
               for c in calls]
        known = {t["name"] for t in tools}
        out = [c for c in out if c["name"] in known]
        return out or None
    except Exception:
        return None


def plan(said, speaker, tools, context=None) -> dict:
    ctx = context or {}
    rules = plan_rules(said, speaker, ctx)
    if rules and "host" in rules[0]:
        return {"planner": "rules", "calls": rules}       # the host's own step
    calls = plan_model(said, speaker, tools, ctx)
    if calls:
        model = (os.getenv("HEARTH_SIM_LLM_MODEL") or os.getenv("HEARTH_LLM_MODEL")
                 or "model")
        return {"planner": f"model:{model}", "calls": calls}
    return {"planner": "rules", "calls": rules}


# --- voice ------------------------------------------------------------------
POLLY_VOICES = {"alexa": "Joanna", "rose": "Ruth", "mom": "Ruth", "tom": "Matthew",
                "ada": "Danielle", "grace": "Kendra"}


def tts_provider() -> str:
    want = os.getenv("HEARTH_TTS", "auto").lower()
    if want in ("polly", "auto") and os.getenv("AWS_ACCESS_KEY_ID") \
            and os.getenv("AWS_SECRET_ACCESS_KEY"):
        return "polly"
    if want in ("piper", "auto") and os.getenv("HEARTH_PIPER_VOICE"):
        try:
            import piper  # noqa: F401
            return "piper"
        except ImportError:
            pass
    return "browser"


def _sign(key, msg):
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def polly_request(text, voice, now=None, region=None):
    """A SigV4-signed SynthesizeSpeech request, built by hand so the simulator
    needs no AWS SDK. Returns (url, headers, body)."""
    region = region or os.getenv("AWS_REGION", "us-east-1")
    host = f"polly.{region}.amazonaws.com"
    body = json.dumps({"Text": text, "OutputFormat": "mp3", "VoiceId": voice,
                       "Engine": "neural"})
    now = now or dt.datetime.now(dt.timezone.utc)
    amz_date, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body.encode()).hexdigest()
    headers = {"content-type": "application/json", "host": host,
               "x-amz-date": amz_date}
    token = os.getenv("AWS_SESSION_TOKEN")
    if token:
        headers["x-amz-security-token"] = token
    signed = ";".join(sorted(headers))
    canonical = "\n".join(["POST", "/v1/speech", "",
                           "".join(f"{k}:{headers[k]}\n" for k in sorted(headers)),
                           signed, payload_hash])
    scope = f"{day}/{region}/polly/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope,
                         hashlib.sha256(canonical.encode()).hexdigest()])
    k = _sign(("AWS4" + os.environ["AWS_SECRET_ACCESS_KEY"]).encode(), day)
    for part in (region, "polly", "aws4_request"):
        k = _sign(k, part)
    sig = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
    headers["authorization"] = (
        f"AWS4-HMAC-SHA256 Credential={os.environ['AWS_ACCESS_KEY_ID']}/{scope}, "
        f"SignedHeaders={signed}, Signature={sig}")
    return f"https://{host}/v1/speech", headers, body


_PIPER = {}


def speak(text: str, who: str = "alexa") -> tuple[bytes | None, str, str]:
    """(audio, mime type, provider). Audio is None when the browser should
    speak instead, which is the free fallback that always works."""
    provider = tts_provider()
    text = re.sub(r"\s*\[[0-9a-f]{6,}\]", "", text or "").strip()[:1500]
    if not text:
        return None, "", provider
    if provider == "polly":
        try:
            import httpx
            voice = os.getenv(f"HEARTH_POLLY_VOICE_{who.upper()}") or \
                POLLY_VOICES.get(who.lower(), "Joanna")
            url, headers, body = polly_request(text, voice)
            r = httpx.post(url, headers=headers, content=body, timeout=15)
            r.raise_for_status()
            return r.content, "audio/mpeg", "polly"
        except Exception:
            provider = "piper" if os.getenv("HEARTH_PIPER_VOICE") else "browser"
    if provider == "piper":
        try:
            from piper import PiperVoice
            path = (os.getenv(f"HEARTH_PIPER_VOICE_{who.upper()}")
                    or os.getenv("HEARTH_PIPER_VOICE"))
            if path not in _PIPER:
                _PIPER[path] = PiperVoice.load(path)
            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                _PIPER[path].synthesize_wav(text, w)
            return buf.getvalue(), "audio/wav", "piper"
        except Exception:
            pass
    return None, "", "browser"
