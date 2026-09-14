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
import time
import uuid

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


def _text(payload):
    """MCP tool results are content blocks, not bare values."""
    return {"content": [{"type": "text", "text": payload}], "isError": False}


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
]


class HearthMCP:
    """Dispatches MCP JSON-RPC against a Household and its Ledger."""

    def __init__(self, household, ledger, extractor=None):
        self.h = household
        self.ledger = ledger
        self.extract = extractor
        self.sessions: dict[str, float] = {}

    # --- session -----------------------------------------------------------
    def new_session(self) -> str:
        sid = uuid.uuid4().hex
        self.sessions[sid] = time.time()
        return sid

    # --- dispatch ----------------------------------------------------------
    def handle(self, msg: dict) -> dict | None:
        """Returns a JSON-RPC response, or None for a notification."""
        if msg.get("jsonrpc") != "2.0":
            return _err(msg.get("id"), -32600, "Invalid Request: jsonrpc must be '2.0'")
        method, rpc_id = msg.get("method"), msg.get("id")
        params = msg.get("params") or {}

        if method and method.startswith("notifications/"):
            return None                       # notifications get no response body
        if method == "initialize":
            return _ok(rpc_id, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
                "instructions": (
                    "Hearth holds this household's standing preferences. Call "
                    "whats_true before acting on anything the household may have "
                    "an opinion about, call did straight after acting, and call "
                    "why when asked to justify something."),
            })
        if method == "ping":
            return _ok(rpc_id, {})
        if method == "tools/list":
            return _ok(rpc_id, {"tools": TOOLS})
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
        for mid, m in self.h.members.items():
            if m.name.lower() == str(name).lower():
                return mid
        return None

    def _names(self):
        return {m.name: mid for mid, m in self.h.members.items()}

    # --- tools -------------------------------------------------------------
    def _tool_remember(self, said, speaker):
        holder = self._member_id(speaker)
        if holder is None:
            holder = self.h.add_member(speaker).id      # a new voice in the house
        found = (self.extract or (lambda t, n: []))(said, self._names())
        if not found:
            return _text(f"Nothing durable to remember in that, from {speaker}.")
        out = []
        for b in found:
            belief = self.h.assert_belief(
                holder, b["domain"], b["slot"], b["value"], content=said,
                scope=b.get("scope"), context=b.get("context"))
            line = f"{b['domain']}.{b['slot']} = {b['value']} (from {speaker}, id {belief.id})"
            if belief.context:
                line += f", only during {belief.context}"
            out.append(line)
        return _text("Remembered: " + "; ".join(out))

    def _tool_whats_true(self, domain, slot, about=None):
        r = self.h.resolve(domain, slot, for_member=self._member_id(about))
        if r.winner is None:
            return _text(f"Nobody has set {domain}.{slot}.")
        return _text(f"{r.winner.value}. " + r.explain(self.h.name_of))

    def _tool_did(self, what, domain, slot, about=None):
        r = self.h.resolve(domain, slot, for_member=self._member_id(about))
        a = self.ledger.record(what, domain, resolution=r)
        return _text(f"Logged: {what} (action {a.id})")

    def _tool_why(self, domain=None):
        return _text(self.ledger.why(domain=domain))

    def _tool_stand_down(self, belief_id, reason="a member stood it down"):
        b = self.h.retire(belief_id, reason=reason)
        if b is None:
            return _text("No standing belief with that id.")
        return _text(f"Stood down: {b.domain}.{b.slot} = {b.value} ({reason}).")

    def _tool_end_context(self, context):
        ended = self.h.end_context(context)
        if not ended:
            return _text(f"Nothing was riding on {context}.")
        return _text(f"Ended {context}. {len(ended)} belief(s) stopped applying: "
                     + "; ".join(f"{b.domain}.{b.slot}={b.value}" for b in ended))

    def _tool_household(self):
        lines = [f"{m.name} ({m.role}"
                 + (f", owns {', '.join(m.grants)}" if m.grants else "") + ")"
                 for m in self.h.members.values()]
        live = [b for b in self.h.beliefs if b.is_live()]
        lines += [f"  {b.domain}.{b.slot} = {b.value} from {self.h.name_of(b.holder)}"
                  + (f" [{b.context}]" if b.context else "") for b in live]
        return _text("\n".join(lines) or "Nobody has said anything yet.")
