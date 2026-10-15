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
import time
import wave

from .care import MED_ALIASES, local

# --- planning ---------------------------------------------------------------
# Medicines by name, brand and kitchen word. Brands matter: a person reaching
# for the box says "my Coumadin", and that used to fall through to `remember`
# ("Nothing durable to remember in that"), so the refusal never ran.
NAMED_MEDS = (r"warfarin|coumadin|jantoven|metformin|furosemide|lasix|metoprolol|"
              r"lisinopril|atorvastatin|amlodipine|aspirin|paracetamol|tylenol|"
              r"ibuprofen|advil|insulin|vitamin \w+")
MEDS = (r"(" + NAMED_MEDS + r"|blood thinners?|tablets?|pills?|medicines?|"
        r"medication|water pills?|heart pills?|dose)")
ITEMS = r"(warfarin|blood thinners?|ensure|pill organi[sz]er|furosemide|metformin|metoprolol|tablets|pills)"
APPTS = r"(cardiology|cardiologist|dentist|doctor|podiatrist|eye clinic|appointment|check-?up|physio\w*|hospital)"


def _med(text: str) -> str | None:
    """The medicine named in what was said, or None if none was named.

    None matters. "I'm taking my pills" used to become warfarin by default, so
    a dose of something else was logged against the blood thinner and the real
    warfarin was then refused. An unnamed medicine is passed on as said, and
    Hearth asks which one before it writes anything down.
    """
    low = text.lower()
    for alias, med in MED_ALIASES.items():
        if alias in low:
            return med
    m = re.search(r"\b(" + NAMED_MEDS + r")\b", low)
    # Said as it was said: Hearth normalises the name, and a medicine it has
    # no rule for gets "check with Ada", not a guess at which one it was.
    return m.group(1) if m else None


def _said_med(low: str, ctx: dict) -> str:
    """What to pass as `medication`: the named one; else, for "it" or "them"
    straight after a turn about one medicine, that medicine; else the word
    that was said ("pills"), which Hearth answers with "which medicine?"."""
    named = _med(low)
    if named:
        return named
    if ctx.get("medication") and re.search(r"\b(it|them|that one)\b", low):
        return str(ctx["medication"])
    m = re.search(MEDS, low)
    return m.group(1) if m else "it"


_QUESTION_START = re.compile(
    r"^(?:alexa,?\s*)?(?:should|shall|can|could|may|do|does|did|is|am|are|has|"
    r"have|was|were|when|what|which|how|will|would|must|ought)\b")
_QUESTION_ANY = re.compile(
    r"\b(?:is it (?:ok|okay|safe|all right|alright|time)|am i (?:allowed|due|ok|"
    r"okay|supposed)|is that (?:ok|okay|all right|alright|safe)|do i need|or not)\b")


def is_question(said: str) -> bool:
    """A question about a dose must never record one. Speech arrives without
    punctuation, so a leading modal or auxiliary counts as a question mark."""
    s = said.strip()
    low = s.lower().strip(" .!")
    return (s.endswith("?") or bool(_QUESTION_START.match(low))
            or bool(_QUESTION_ANY.search(low)))


_NUMBERS = {"two": 2, "three": 3, "four": 4, "five": 5, "both": 2, "a couple of": 2}


def _count(low: str) -> int:
    """How many were taken: "I took two aspirin" is two doses, not one."""
    m = re.search(r"\b(\d+|two|three|four|five|both|a couple of)\s+(?:of\s+)?"
                  r"(?:my\s+|her\s+|his\s+|the\s+)?" + MEDS, low)
    if not m:
        return 1
    n = m.group(1)
    return max(1, min(10, int(n) if n.isdigit() else _NUMBERS[n]))


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
    if re.search(r"\b(i'?m off|i am off|heading off|end of (?:my|the) shift|handover|"
                 r"hand(?:ing)? over|that'?s me done|before i go|i'?m leaving)\b", low):
        # Before the dose and reorder rules: a handover mentions both ("she
        # had her warfarin", "we're out of Ensure") and is neither.
        return [{"name": "handover", "arguments": {"note": s, "given_by": speaker}}]
    if re.search(r"\b(shopping list|on the list|the list)\b", low):
        if re.search(r"\b(order|buy|get)\b", low) and not re.search(r"\b(put|add)\b", low):
            return [{"name": "reorder", "arguments": {"item": "the list", "asked_by": speaker}}]
        m = re.search(r"\b(?:put|add)\s+(.+?)\s+(?:on|to)\s+(?:the\s+)?(?:shopping\s+)?list", low)
        if m:
            return [{"name": "shopping_list", "arguments": {"add": m.group(1), "asked_by": speaker}}]
        return [{"name": "shopping_list", "arguments": {"asked_by": speaker}}]
    if re.search(r"\bwhy\b", low):
        dom = ("medication" if re.search(MEDS + r"|\bstop", low) else
               "diet" if re.search(r"coffee|wine|alcohol", low) else
               "thermostat" if re.search(r"warm|cold|thermostat|heat", low) else None)
        return [{"name": "why", "arguments": {"domain": dom} if dom else {}}]
    if re.search(r"\b(what have you done|show (?:me )?the record|the record)\b", low):
        return [{"name": "record", "arguments": {"limit": 8}}]
    if (ctx.get("checkout")
            and re.fullmatch(r"(yes|yeah|yep|go ahead|do it|place (?:the|it)|please do|ok(?:ay)?|sure|pay)[\w ,]*", low)
            and not re.search(r"\b(took|taken|take|taking|gave|given|giving)\b", low)):
        return [{"host": "checkout.complete", "checkout": ctx["checkout"]}]
    if re.search(r"\b(re-?order|order more|running (?:low|out)|nearly out|almost out|need more|down to)\b", low):
        m = re.search(ITEMS, low)
        item = m.group(1) if m else (_med(low) or "warfarin")
        qty = 2 if re.search(r"\b(two|2)\s+(?:packs|cases|boxes)\b", low) else 1
        return [{"name": "reorder", "arguments": {
            "item": (_med(item) or item) if re.search(MEDS, item) else item,
            "asked_by": speaker, "quantity": qty}}]
    mentions_dose = (bool(re.search(MEDS, low))
                     or bool(re.search(r"\b(took|taken|gave|given)\b.*\b(it|them)\b", low))
                     or bool(ctx.get("medication") and re.search(
                         r"\b(take|taking|had|have|give)\b.*\b(it|them|that one)\b", low)))
    if mentions_dose and is_question(s):
        # "Should I take my tablet now?" is a question. It is answered from
        # the record and changes nothing; only a report of a dose is logged.
        return [{"name": "check_dose", "arguments": {"medication": _said_med(low, ctx),
                                                      "asked_by": speaker}}]
    if (mentions_dose
            and re.search(r"\b(take|taking|took|taken|give|giving|gave|given|have|"
                          r"having|had|time for)\b", low)
            and not re.search(r"\ba day\b|\bdaily\b|\bevery\b|\bnot\b|n't\b|\bwait\b|"
                              r"\blater\b|\bskip", low)):
        args = {"medication": _said_med(low, ctx), "given_by": speaker}
        n = _count(low)
        if n > 1:
            args["count"] = n
        return [{"name": "give_dose", "arguments": args}]
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


_SKILL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "skills", "hearth-care", "SKILL.md")


def skill_instructions() -> str:
    """The hearth-care Agent Skill's body, without its front matter.

    An agent that uses Hearth is meant to load this skill; the simulated
    Alexa+ loads it too, so the model standing in for Alexa's is taught the
    same rules (pass the speaker, never soften a refusal, pay through the
    host) as any other assistant would be."""
    try:
        with open(_SKILL, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return ""
    if text.startswith("---"):
        text = text.split("---", 2)[2]
    return text.strip()


def _user_turn(said, speaker, ctx) -> str:
    """What the model is told about this turn: who spoke, what they said, and
    the two bits of conversation state a host would carry."""
    lines = [f"{speaker} says: {said}"]
    # A host knows the date; without it a model turns "Thursday" into
    # whichever date it guesses, and the appointment moves to a Sunday.
    n = local(ctx["now"]) if ctx.get("now") else local(time.time())
    lines.append(f"(It is {n:%A} {n.day} {n:%B %Y}, {n:%H:%M} where the household is.)")
    if ctx.get("medication"):
        lines.append(f"(The last medicine discussed was {ctx['medication']}.)")
    if ctx.get("device"):
        lines.append(f"(Heard on: {ctx['device']}.)")
    return "\n".join(lines)


def _system() -> str:
    return PLANNER_SYSTEM + "\n\n" + skill_instructions()


# --- providers ----------------------------------------------------------------
# Which model stands in for Alexa+'s, chosen by environment:
#
#   HEARTH_SIM_LLM_PROVIDER  bedrock | openai | rules | auto (default)
#   bedrock: HEARTH_BEDROCK_MODEL (a model or inference profile id),
#            AWS_REGION, and either AWS_BEARER_TOKEN_BEDROCK (a Bedrock API
#            key) or AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (SigV4).
#   openai:  HEARTH_SIM_LLM_BASE_URL, HEARTH_SIM_LLM_API_KEY,
#            HEARTH_SIM_LLM_MODEL (any OpenAI-compatible endpoint).
#
# auto tries Bedrock first when it is configured, then the OpenAI-compatible
# endpoint, then the offline rules. Alexa+ itself runs on Bedrock, which is
# why it is first.

def _bedrock_ready() -> bool:
    return bool(os.getenv("HEARTH_BEDROCK_MODEL") and (
        os.getenv("AWS_BEARER_TOKEN_BEDROCK")
        or (os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"))))


def _openai_ready() -> bool:
    return bool((os.getenv("HEARTH_SIM_LLM_BASE_URL") or os.getenv("HEARTH_LLM_BASE_URL"))
                and (os.getenv("HEARTH_SIM_LLM_API_KEY") or os.getenv("HEARTH_LLM_API_KEY")))


def providers() -> list[str]:
    """The model providers to try, in order. Empty means the offline rules."""
    want = os.getenv("HEARTH_SIM_LLM_PROVIDER", "auto").lower()
    if want == "rules":
        return []
    order = {"bedrock": ["bedrock", "openai"], "openai": ["openai"]}.get(
        want, ["bedrock", "openai"])
    ready = {"bedrock": _bedrock_ready, "openai": _openai_ready}
    return [p for p in order if ready[p]()]


def _openai_model() -> str:
    return (os.getenv("HEARTH_SIM_LLM_MODEL") or os.getenv("HEARTH_LLM_MODEL")
            or "gpt-4o-mini")


def model_label(provider: str) -> str:
    if provider == "bedrock":
        return f"model:{os.getenv('HEARTH_BEDROCK_MODEL')} on Amazon Bedrock"
    from urllib.parse import urlparse
    host = urlparse(os.getenv("HEARTH_SIM_LLM_BASE_URL")
                    or os.getenv("HEARTH_LLM_BASE_URL") or "").hostname or ""
    # A small open model on the same laptop is worth saying out loud: the
    # safety is in Hearth's server, so the planner does not have to be big.
    local = host in ("localhost", "127.0.0.1", "::1")
    return f"model:{_openai_model()}" + (" on this machine" if local else "")


def _timeout() -> float:
    return float(os.getenv("HEARTH_SIM_LLM_TIMEOUT", "12"))


def plan_openai(said, speaker, tools, context=None):
    """Plan with any OpenAI-compatible chat completions endpoint."""
    import httpx
    base = os.getenv("HEARTH_SIM_LLM_BASE_URL") or os.getenv("HEARTH_LLM_BASE_URL")
    key = os.getenv("HEARTH_SIM_LLM_API_KEY") or os.getenv("HEARTH_LLM_API_KEY")
    fns = [{"type": "function", "function": {
        "name": t["name"], "description": t["description"],
        "parameters": t["inputSchema"]}} for t in tools]
    r = httpx.post(f"{base.rstrip('/')}/chat/completions",
                   headers={"Authorization": f"Bearer {key}"},
                   json={"model": _openai_model(), "temperature": 0, "tools": fns,
                         "messages": [
                             {"role": "system", "content": _system()},
                             {"role": "user",
                              "content": _user_turn(said, speaker, context or {})}]},
                   timeout=_timeout())
    r.raise_for_status()
    calls = r.json()["choices"][0]["message"].get("tool_calls") or []
    return [{"name": c["function"]["name"],
             "arguments": json.loads(c["function"].get("arguments") or "{}")}
            for c in calls]


def bedrock_request(body: dict, now=None):
    """(url, headers, raw body) for a Bedrock Converse call. A Bedrock API key
    goes as a bearer token; otherwise the request is SigV4 signed by hand, as
    Polly's is, so the simulator needs no AWS SDK."""
    from urllib.parse import quote
    region = os.getenv("AWS_REGION", "us-east-1")
    model = os.environ["HEARTH_BEDROCK_MODEL"]
    host = f"bedrock-runtime.{region}.amazonaws.com"
    path = f"/model/{quote(model, safe='')}/converse"
    base = os.getenv("HEARTH_BEDROCK_ENDPOINT") or f"https://{host}"
    raw = json.dumps(body)
    token = os.getenv("AWS_BEARER_TOKEN_BEDROCK")
    if token:
        return (base.rstrip("/") + path,
                {"content-type": "application/json", "authorization": f"Bearer {token}"},
                raw)
    # SigV4 for every service but S3 encodes each path segment twice: the
    # ':' in a model id is %3A on the wire and %253A in the canonical request.
    headers = _sigv4("POST", host, quote(path, safe="/"), raw, "bedrock", region, now)
    return base.rstrip("/") + path, headers, raw


def plan_bedrock(said, speaker, tools, context=None):
    """Plan with a model on Amazon Bedrock through the Converse API, with
    Hearth's own tools/list as its tool config."""
    import httpx
    choice = os.getenv("HEARTH_SIM_LLM_TOOL_CHOICE", "any")
    body = {
        "system": [{"text": _system()}],
        "messages": [{"role": "user", "content": [
            {"text": _user_turn(said, speaker, context or {})}]}],
        "toolConfig": {
            "tools": [{"toolSpec": {"name": t["name"], "description": t["description"],
                                    "inputSchema": {"json": t["inputSchema"]}}}
                      for t in tools],
            "toolChoice": {"any": {}} if choice == "any" else {"auto": {}}},
        "inferenceConfig": {"temperature": 0, "maxTokens": 600},
    }
    url, headers, raw = bedrock_request(body)
    r = httpx.post(url, headers=headers, content=raw, timeout=_timeout())
    r.raise_for_status()
    content = r.json()["output"]["message"].get("content") or []
    return [{"name": c["toolUse"]["name"], "arguments": c["toolUse"].get("input") or {}}
            for c in content if "toolUse" in c]


PLANNERS = {"bedrock": plan_bedrock, "openai": plan_openai}
LAST = {"provider": None, "error": None}


def plan_model(said, speaker, tools, context=None):
    """Plan with the configured model(s). Returns None when none is configured
    or every one fails, and the caller falls back to the offline rules."""
    known = {t["name"] for t in tools}
    LAST.update(provider=None, error=None)
    for p in providers():
        try:
            out = [c for c in PLANNERS[p](said, speaker, tools, context)
                   if c["name"] in known]
        except Exception as e:          # a provider down is a fallback, not a crash
            LAST["error"] = f"{p}: {type(e).__name__}"
            continue
        if out:
            LAST["provider"] = p
            return out
    return None


def configured() -> bool:
    return bool(providers())


def planner_label() -> str:
    """What the page's header says before anyone has spoken."""
    ps = providers()
    return (model_label(ps[0]) + " + skill:hearth-care") if ps else "offline rules"


def warm_up(tools) -> bool:
    """One throwaway plan, so a local model has the 2,700-token prefix (system
    prompt, Agent Skill, tool list) in its cache before anyone speaks. Measured
    on a 3B model on CPU: the first call costs about 15 s of prompt
    processing and later ones reuse it. Returns whether the model answered."""
    if not configured():
        return False
    timeout = os.environ.get("HEARTH_SIM_LLM_TIMEOUT")
    os.environ["HEARTH_SIM_LLM_TIMEOUT"] = os.getenv("HEARTH_SIM_LLM_WARMUP_TIMEOUT", "120")
    try:
        return plan_model("Has Mom had her warfarin today?", "Tom", tools) is not None
    finally:
        if timeout is None:
            os.environ.pop("HEARTH_SIM_LLM_TIMEOUT", None)
        else:
            os.environ["HEARTH_SIM_LLM_TIMEOUT"] = timeout


DOSE_TOOLS = ("give_dose", "check_dose")


def plan(said, speaker, tools, context=None) -> dict:
    """Utterance to tool calls: a model when one is configured, the offline
    rules when not. Two things never depend on the model's reading, and the
    label says when either stepped in:

      - a question never records a dose (a give_dose on a question becomes
        check_dose);
      - a dose being taken always reaches give_dose (a 3B model once sent
        "time for my warfarin" to `remember`, and the refusal never ran).
    """
    ctx = context or {}
    rules = plan_rules(said, speaker, ctx)
    if rules and "host" in rules[0]:
        return {"planner": "host: checkout", "calls": rules}  # Alexa+'s own step
    calls = plan_model(said, speaker, tools, ctx)
    if not calls:
        return {"planner": "offline rules", "calls": rules}
    label = model_label(LAST["provider"] or "openai") + " + skill:hearth-care"
    guarded = False
    if is_question(said) and any(c["name"] == "give_dose" for c in calls):
        calls = [({"name": "check_dose", "arguments": {
                      "medication": c["arguments"].get("medication", "it"),
                      "asked_by": speaker}}
                  if c["name"] == "give_dose" else c) for c in calls]
        guarded = True
    if (rules[0].get("name") == "give_dose"
            and not any(c["name"] in DOSE_TOOLS for c in calls)):
        calls = [rules[0]] + [c for c in calls if c["name"] != "remember"]
        guarded = True
    return {"planner": label + (" · dose guard" if guarded else ""), "calls": calls}


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
    return (f"https://{host}/v1/speech",
            _sigv4("POST", host, "/v1/speech", body, "polly", region, now), body)


def _sigv4(method, host, canonical_path, body, service, region, now=None) -> dict:
    """AWS Signature Version 4 headers for a JSON POST."""
    now = now or dt.datetime.now(dt.timezone.utc)
    amz_date, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body.encode()).hexdigest()
    headers = {"content-type": "application/json", "host": host,
               "x-amz-date": amz_date}
    token = os.getenv("AWS_SESSION_TOKEN")
    if token:
        headers["x-amz-security-token"] = token
    signed = ";".join(sorted(headers))
    canonical = "\n".join([method, canonical_path, "",
                           "".join(f"{k}:{headers[k]}\n" for k in sorted(headers)),
                           signed, payload_hash])
    scope = f"{day}/{region}/{service}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope,
                         hashlib.sha256(canonical.encode()).hexdigest()])
    k = _sign(("AWS4" + os.environ["AWS_SECRET_ACCESS_KEY"]).encode(), day)
    for part in (region, service, "aws4_request"):
        k = _sign(k, part)
    sig = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
    headers["authorization"] = (
        f"AWS4-HMAC-SHA256 Credential={os.environ['AWS_ACCESS_KEY_ID']}/{scope}, "
        f"SignedHeaders={signed}, Signature={sig}")
    return headers


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
