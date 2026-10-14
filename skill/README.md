# Hearth Care: a classic Alexa skill that is an MCP client of Hearth

Alexa+ add-on tools are available to select partners only, so no hackathon
entrant can put an add-on on a real Echo. A classic Alexa custom skill can be on
a real Echo today, and the organisers said on the forum (topic 45263) that "you
could certainly build an Alexa skill that invokes your MCP, and then demo it on
your echo". This is that skill.

```
 Echo Show / Echo Dot / Alexa app
    │  Alexa's own speech recognition and NLU pick the intent and fill the slots
    ▼
 skill/lambda/lambda_function.py   (ASK SDK for Python, AWS Lambda)
    │  one intent → one Hearth tool call
    │  MCP 2025-11-25 · Streamable HTTP · initialize → tools/call · Mcp-Session-Id
    ▼
 Hearth /mcp  ──►  the same server, the same tools, the same record
    │
    ▼
 the skill says Hearth's text verbatim, and on a screen draws Hearth's card in APL
```

- **A real MCP client.** `hearth_client.py` (standard library only) sends
  `initialize`, `notifications/initialized` and `tools/call` over Streamable
  HTTP, carries the `Mcp-Session-Id` in the Alexa session, sends
  `MCP-Protocol-Version: 2025-11-25`, and reopens a session Hearth no longer
  knows. Every call lands on Hearth's signed, hash-chained record, like any client's.
- **Hearth's words, not the skill's.** The reply is the text block of Hearth's
  tool result, minus belief references like `[9fa924226edd]`. The skill writes
  only the launch and help lines, the checkout confirmation, and one safety
  line: if Hearth cannot be reached when someone is about to take a medicine,
  it says "please don't take it until someone has checked", never a guess.
- **Alexa's NLU does the planning.** Eight intents map straight to Hearth tools
  (`give_dose`, `check_dose`, `catch_up`, `why`, `arrange`, `reorder`,
  `whats_true`, `record`), with Alexa resolving "Coumadin" or "blood thinner" to
  warfarin and "Thursday at ten" to a date and a time. Anything else ("Mom
  finished the antibiotics") goes to Hearth's planner and then to the tools it
  names.
- **APL on a screen.** On a device that supports APL, Hearth's card
  (`structuredContent.card`) is drawn with the same colours as Hearth's MCP App:
  red for a refusal, green for done. On an Echo Dot it is voice only.
- **Who is speaking.** A recognised voice (`context.System.person.personId`,
  with skill personalisation on) maps to a name; otherwise "this is Tom" for the
  rest of the session; otherwise whose device it is (`HEARTH_DEVICES`);
  otherwise `HEARTH_DEFAULT_SPEAKER` (Rose, in the kitchen). A classic skill
  can get a recognised-voice id; an Alexa+ add-on cannot (friction log entry 8).
- **Checkout.** "Yes" after a reorder completes Hearth's UCP checkout session
  with a sandbox token. A classic skill cannot take a voice PIN or charge a
  card, so the screen says "Sandbox merchant: no payment was taken".

## Tested locally against a running Hearth

```bash
pip install -r requirements.txt -r skill/lambda/requirements.txt
python3 skill/tests/test_skill.py
```

The test starts a real Hearth on a free port (with `HEARTH_SKILL_TOKEN` set),
then drives the skill's real `lambda_handler` with the JSON envelopes Alexa
sends, for all nine demo scenes plus brand names, "this is Tom", a lost
session, an unreachable server and a wrong credential. Each reply is compared
with the text Hearth itself recorded for that call. It also checks the
interaction model: every intent handled, every slot typed, no duplicate
samples, every demo line covered by a sample. CI runs it.

What has **not** been tested: the skill on Amazon's side. It has not been
deployed to Lambda, built in the developer console, run in the console's test
simulator, or spoken to on an Echo. The APL document has not been opened in
the APL authoring tool. Those are the steps below.

## Deploy it (Subomi)

You need: a free Amazon developer account (the same Amazon account as the Echo
you will film), and Hearth deployed somewhere public over HTTPS.

**1. Give Hearth a skill credential.** On the Hearth deployment (Render or
wherever `first-place` runs), set two environment variables and redeploy:

```bash
HEARTH_SKILL_TOKEN=$(openssl rand -hex 24)      # 48 characters; keep it
HEARTH_DATA=<path on a persistent disk>/hearth.json   # so the household survives restarts
```

Check: `curl -s -o /dev/null -w '%{http_code}\n' -X POST https://<hearth>/mcp -H "Authorization: Bearer $HEARTH_SKILL_TOKEN" -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"check","version":"1"}}}'`
should print `200`.

**2. Create the skill** at https://developer.amazon.com/alexa/console/ask:
*Create Skill* → name **Hearth Care** → locale **English (US)** → type
**Other** / **Custom** → hosting **Alexa-hosted (Python)** → template **Start
from Scratch** → *Create*. (Alexa-hosted needs no AWS account.)

**3. Interaction model.** *Build* → *Interaction Model* → *JSON Editor* → paste
`skill/skill-package/interactionModels/custom/en-US.json` → *Save* →
*Build skill*. The invocation name is `hearth care` (change it here and in the
JSON if the product is renamed).

**4. Screen.** *Build* → *Interfaces* → turn on **Alexa Presentation Language**
(tick Hub Landscape and Hub Round at least) → *Save* → *Build skill*.

**5. Code.** *Code* tab, in the `lambda/` folder: replace `lambda_function.py`,
add `hearth_client.py` and `apl.py` from `skill/lambda/`, and make
`requirements.txt` contain `ask-sdk-core>=1.19`. Create `lambda/config.json`
from `config.example.json` with your Hearth URL and the token from step 1
(never commit that file; it is in `.gitignore`). *Save* → *Deploy*.

**6. Try it in the console.** *Test* tab → set testing to **Development** →
type `open hearth care`, then `I'm just going to take my blood thinner`. Expect
"Hold on, Rose. Grace gave you today's warfarin at …" and the red card on the
simulated Echo Show. If the reply is "I can't reach Hearth", check step 1 and
the URL in `config.json`; *Code* → *CloudWatch Logs* shows the error line.

**7. On the Echo.** A development skill is enabled on every Echo registered to
the same Amazon account. In the kitchen: "Alexa, open hearth care", then
"I'm just going to take my blood thinner". One-shot also works: "Alexa, tell
hearth care I'm just going to take my blood thinner."

**8. Optional: people and devices.** Every turn logs a JSON line with
`device` and `person` ids (CloudWatch). Put the Echo Dot's id in
`HEARTH_DEVICES` as `"…": "Tom"` so Tom's device speaks as Tom. If your console
offers skill personalisation (recognised voices), turn it on and map
`personId`s in `HEARTH_PEOPLE`; otherwise say "this is Tom" first.

**Self-hosted Lambda instead** (if you prefer your own AWS account): create a
Python 3.12 Lambda, upload `skill/lambda/` with `ask-sdk-core` installed into
the zip, set `HEARTH_URL` and `HEARTH_TOKEN` as environment variables, add the
Alexa Skills Kit trigger with your skill id, and put the function ARN in the
skill's *Endpoint*. `skill/skill-package/skill.json` is a starting manifest for
`ask deploy`; its icon and privacy URLs are placeholders.

**On camera**, label it: *"Classic Alexa skill calling Hearth's MCP server.
Alexa+ add-on tools are partner-only."*
