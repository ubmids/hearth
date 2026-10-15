# Testing Hearth on Amazon's own surfaces

Checked against Amazon's docs, the hackathon FAQ and the organisers' forum
answers on 15 Oct 2026. Links at the end.

## The short version

| Surface | Can an entrant use it? | Status for Hearth |
|---|---|---|
| Alexa+ add-on (MCP Toolkit, `alexa-ai` CLI, Alexa+ web simulator, Local Inspector) | **No.** Preview, select partners only, no way to apply. | Not possible for anyone in the hackathon. Hearth is built to the documented contract and ready for it. |
| Simulated Alexa+ (a web page that is a real MCP client) | **Yes**, accepted by the rules and the FAQ. | Done and live: `/alexa` (and `/alexa?film=1` for the video). |
| Classic Alexa custom skill, tested in the developer console's **Test tab simulator** (with the Echo Show display) | **Yes**, free developer account, no publishing. | Built and tested locally on Python 3.8, the version Alexa-hosted runs. **Needs Subomi's Amazon login**: steps below, about 30 minutes. |
| The same skill on a real Echo registered to the same Amazon account | **Yes**, a development skill works on your own devices. | Same steps, plus the device. |
| An existing AI assistant calling the same MCP server | **Yes**, the FAQ calls it "a nice bonus". | `demo/assistant.py` (Claude Code) is written; not yet run. |

What Amazon says, word for word:

- Alexa+ docs home: "At this time, Category SDK and MCP Toolkit are available
  to select partners only."
- Hackathon FAQ: "Amazon's Alexa+ Add-on developer tools (Category SDK, MCP
  Toolkit, CLI, and Web Simulator) are in preview and available to select
  partners only - there is currently no way for hackathon participants to apply
  for or gain access." And: "there's no way for any participant to connect a
  self-hosted MCP server to a real Alexa+ device or developer console", while
  "A web page that acts as an actual MCP client (sending initialize,
  tools-list, and tools-call requests over Streamable HTTP)" satisfies the
  requirement.
- Emerson Sklar (Alexa Chief Evangelist), forum: "You could certainly build an
  Alexa skill that invokes your MCP, and then demo it on your echo."

So the most Amazon-real thing any entrant can show is a classic skill that is
an MCP client of their server, running in the console simulator or on an Echo.
That is `skill/`.

## Before you start (5 minutes, on the laptop)

1. **Wake the server.** The free Render instance can sleep, and Alexa waits at
   most 8 seconds for a skill. `curl -s https://hearth-sh3u.onrender.com/healthz`
   should print `{"ok":true,...}` within a couple of seconds. If it takes
   longer than that, run it again until it is fast.
2. **Make a skill token.** `openssl rand -hex 24` prints 48 characters. Keep
   it in your password manager, not in the repo.
3. **Give it to Hearth.** Render dashboard → service **hearth** → Environment →
   *Add Environment Variable* → `HEARTH_SKILL_TOKEN` = the token → *Save,
   rebuild and deploy*. Wait for "Live", then check (prints `200`):

   ```bash
   T=<the token>
   curl -s -o /dev/null -w '%{http_code}\n' -X POST https://hearth-sh3u.onrender.com/mcp \
     -H "Authorization: Bearer $T" -H 'Content-Type: application/json' \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"check","version":"1"}}}'
   ```

   This is Hearth's own credential for one fixed household, not a paid API key.
   The free instance has no disk, so that household is re-seeded at every
   restart, which is what you want for a demo.
4. **Build the code ZIP.**

   ```bash
   cd ~/Desktop/hackathons/hearth
   cp skill/lambda/config.example.json skill/lambda/config.json
   # edit config.json: HEARTH_URL = https://hearth-sh3u.onrender.com, HEARTH_TOKEN = <the token>
   scripts/skill_zip.sh          # -> out/hearth-care-lambda.zip (git ignores out/ and config.json)
   ```

## In the Alexa developer console (about 25 minutes, needs your Amazon login)

Use the Amazon account your Echo is registered to, if you have one. The
console is at https://developer.amazon.com/alexa/console/ask.

1. **Create Skill.** Name `Hearth Care` → Primary locale **English (US)** →
   *Next* → experience **Other** → model **Custom** → hosting
   **Alexa-hosted (Python)**, region **US East (N. Virginia)** → *Next* →
   template **Start from Scratch** → *Next* → *Create Skill*. Wait for the
   build (a minute or two).
2. **Interaction model.** *Build* tab → *Interaction Model* → *JSON Editor* →
   *Drag and drop a .json file*: `skill/skill-package/interactionModels/custom/en-US.json`
   (or paste it) → *Save* → *Build skill*. Wait for "Build Successful".
   The invocation name is `hearth care`.
3. **Screen.** *Build* → *Interfaces* (left menu, under Assets) → turn on
   **Alexa Presentation Language** → tick **Hub Landscape** and **Hub Round**
   (add others if offered) → *Save* → *Build skill* again.
4. **Optional, recognised voices.** *Build* → *Permissions* (bottom left) →
   turn on **Skill Personalization** (scope `alexa::person_id:read`). Only
   matters on a real Echo with Voice ID set up; skip it for the simulator.
5. **Code.** *Code* tab → *Import Code* → choose `out/hearth-care-lambda.zip`
   → confirm it replaces `lambda/` files → *Deploy*. Wait for "Deployment
   successful". (Alexa-hosted runs Python 3.8; `skill/tests/test_skill.py`
   passes on 3.8, see "Checks" below.) If *Import Code* is not offered, open
   each file under `lambda/` and paste the matching file from `skill/lambda/`,
   and create `lambda/config.json` with *New File*.
6. **Test tab.** *Test* → change "Skill testing is enabled in" from **Off** to
   **Development**. Tick **Device Display** (and pick an Echo Show viewport if
   asked) so the APL card shows.
7. **Type, in this order** (each line is a demo scene; the expected answer is
   Hearth's own text):

   | Type | Expect |
   |---|---|
   | `open hearth care` | "Hearth here. Go ahead, Rose." |
   | `I'm just going to take my blood thinner` | "Hold on, Rose. Grace gave you today's warfarin at … Your warfarin is once a day, so not another until tomorrow." and a **red** card |
   | `this is grace` then `I'm off mom ate half her lunch she was a bit dizzy after her walk and we're nearly out of ensure` | "Thanks, Grace. I've left the handover for Ada and Tom on the family board, put ensure on the shopping list, and flagged one thing for Ada: …" |
   | `this is tom` then `what did I miss with mom today` | the catch-up, including the refusal and Grace's handover |
   | `this is ada` then `mom's cardiology moved to thursday at ten sort it out` | "Done. Mom's cardiology is now Thursday at 10:00 am. Tom is taking Mom…" |
   | `order what's on the list` then `yes` | Ensure priced at $38.99, then ordered (sandbox: no payment taken) |
   | `show me the record` | "N calls on the record, 1 refused, and it matches its signed checkpoint…" |

   One-shot also works: `tell hearth care I'm just going to take my blood thinner`.
8. **Record it.** Screen-record the browser (Cmd+Shift+5, selected portion)
   while you type the first two lines. That is the "Amazon surface" shot in
   the video (`docs/video/SCRIPT.md`, 1:58).
9. **On a real Echo (if you have one).** The development skill is already
   enabled on every device registered to the same account. "Alexa, open hearth
   care", then "I'm just going to take my blood thinner". On an Echo Show the
   red card appears. Film it from the side with the phone.

If something fails: *Code* → *CloudWatch Logs* (top of the Code tab) shows the
skill's one JSON line per turn and any error. "I can't reach Hearth" means the
URL or token in `config.json` does not match Render, or the instance was
asleep: run the `healthz` curl and try again.

## For the browser agent (Claude in Chrome)

Subomi signs in to developer.amazon.com himself first. Then the agent does
steps 1 to 7 above in his Chrome, with these limits:

- It never types or reads the Amazon password, and stops at any 2FA prompt.
- It uploads only `skill/skill-package/interactionModels/custom/en-US.json` and
  `out/hearth-care-lambda.zip`. The token is already inside the ZIP, which
  Subomi built in "Before you start", so the agent never handles it.
- It does not touch *Distribution*, *Certification* or *Submit for review*. The
  skill stays in Development.
- At step 7 it types each line, waits for the reply, and screenshots the
  simulator with the card visible.

## Write down what went wrong

Every surprise in the console is a friction-log entry worth points, and the
judges marked the current entries down for coming from reading, not doing.
For each, note: what you were trying to do, the exact click or command, what
you expected, what happened, how long it cost, and what you did instead. Paste
the notes to an agent and it will add them to `docs/FRICTION_LOG.md`.

## Checks already done on the laptop

- `python3 skill/tests/test_skill.py`: 9 tests drive the real `lambda_handler`
  with Alexa's request envelopes against a running Hearth, and every reply
  equals the text Hearth recorded for that call.
- The same 9 tests pass with the handler on **Python 3.8.20**, Alexa-hosted's
  version:
  `HEARTH_SERVER_PYTHON=<python 3.10+ with Hearth's requirements> <python3.8> skill/tests/test_skill.py`
  (3.8 needs `ask-sdk-core` and, for the test's clock only, `backports.zoneinfo`).
- The skill's MCP client uses only the standard library, so the official MCP
  Python SDK, which needs Python 3.10 or later, is not needed on Alexa-hosted.
- Not yet checked: anything on Amazon's side (console build, APL rendering in
  the simulator, an Echo). That is the list above.

## Sources

- Alexa+ add-ons home: https://developer.amazon.com/en-US/docs/alexaplus/add-ons/home.html
- Alexa+ development stages: https://developer.amazon.com/en-US/docs/alexaplus/add-ons/alexa-plus-add-on-development-stages.html
- Hackathon FAQ: https://amazonappdev2026.devpost.com/details/faqs
- Hackathon rules: https://amazonappdev2026.devpost.com/rules
- Forum, a skill that invokes your MCP: https://amazonappdev2026.devpost.com/forum_topics/45263
- Forum, live through judging: https://amazonappdev2026.devpost.com/forum_topics/45493
- Create an Alexa-hosted skill: https://developer.amazon.com/en-US/docs/alexa/hosted-skills/alexa-hosted-skills-create.html
- Alexa-hosted runtime (Python 3.8): https://developer.amazon.com/en-US/docs/alexa/hosted-skills/build-a-skill-end-to-end-using-an-alexa-hosted-skill.html
- Test your skill: https://developer.amazon.com/en-US/docs/alexa/devconsole/test-your-skill.html
- APL in the simulator: https://developer.amazon.com/en-US/docs/alexa/alexa-presentation-language/test-apl-skills-dev-console.html
- Test on your own device: https://developer.amazon.com/en-US/docs/alexa/test/test-your-skill-overview.html
- Personalization: https://developer.amazon.com/en-US/docs/alexa/custom-skills/add-personalization-to-your-skill.html
