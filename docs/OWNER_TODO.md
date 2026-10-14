# Owner to-do (delete this file before the repo goes public)

`git rm docs/OWNER_TODO.md && git commit -m "docs: remove the to-do list"`
before flipping visibility. It holds no secrets, only steps.

## What was fixed on `first-place` (14 Oct)

| commit | fix |
|---|---|
| `92b2119` | A question about a dose never records one. "Should I take my tablet now?" goes to `check_dose`; an unnamed medicine gets "which medicine?"; "two aspirin" counts as two; the classic skill's "can I take my…" moved to CheckDoseIntent. `tests/test_dose_safety.py` covers questions, reports, confirmations and the exact 8:55/9:10 scene. |
| `f9e298e` | The record is tamper-evident for real: every call's head is Ed25519-signed into a separate witness file, and every result returns a `{seq, hash}` receipt that `record` checks. Truncation, edit+rehash, reorder and deletion all fail (in memory and on disk). The copy says exactly what each layer catches (`docs/ENGINEERING.md` table). |
| `98821af` | A real model plans on camera: Amazon Bedrock (Converse, API key or SigV4) first, any OpenAI-compatible endpoint second, offline rules last. Film mode `/alexa?film=1`: no scene button or chips, traffic panel on **T**, red banner if no model. Tested with a fake Bedrock. |
| `36c2a26` | "Told Tom" is real: board posts push to `HEARTH_NOTIFY_<NAME>` (ntfy or webhook), delivery status on the post, `/inbox/<name>`, yellow ring on the simulated Echo Dot. Alexa says "sent it to Tom's phone" only when it did. |
| `59ee862` | Demo script at 2:45, hero at 0:04, traffic shown once at 0:13. |
| `7822e03` + this commit | Internal notes out of public copy; claims matched to code. |

## Your steps, in order

### 1. Model key (Bedrock preferred)

In the AWS console, region us-east-1: Bedrock → Model access → enable one
tool-calling model (Claude Haiku 4.5 or Amazon Nova Pro). Bedrock → API keys
→ create a long-term key. Find the exact id with
`aws bedrock list-inference-profiles --region us-east-1` (Claude usually needs
the `us.` inference profile, e.g. `us.anthropic.claude-haiku-4-5-20251001-v1:0`;
Nova: `us.amazon.nova-pro-v1:0`).

```bash
cd hearth
export HEARTH_BEDROCK_MODEL=<id> AWS_REGION=us-east-1 AWS_BEARER_TOKEN_BEDROCK=<key>
python3 -c "from hearth import sim; from hearth.mcp import TOOLS
for s,w in [('Should I take my tablet now?','Rose'),(\"Alexa, I'm just going to take my blood thinner.\",'Rose'),('What did I miss with Mom today?','Tom')]:
    print(sim.plan(s,w,TOOLS), sim.LAST)"
```

Expect `model:<id> on Amazon Bedrock + skill:hearth-care` with no `· dose guard`,
and check_dose / give_dose / catch_up. If `sim.LAST` shows a `bedrock:` error:
wrong id or model access not granted; if the model rejects tool choice, add
`HEARTH_SIM_LLM_TOOL_CHOICE=auto`. Fallback instead of Bedrock:
`HEARTH_SIM_LLM_BASE_URL=https://api.openai.com/v1 HEARTH_SIM_LLM_API_KEY=… HEARTH_SIM_LLM_MODEL=gpt-4o-mini`.
Aim for under 2 s per turn; if slower, try the other model.

### 2. Phone push and record key

Install the ntfy app, subscribe to a hard-to-guess topic, test with
`curl -d hello https://ntfy.sh/<topic>`, then
`export HEARTH_NOTIFY_TOM=https://ntfy.sh/<topic>`.
Record key: `export HEARTH_RECORD_KEY=$(python3 -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip('='))")`
(keep it; changing it makes old checkpoints fail).

### 3. Film

Follow `docs/DEMO_SCRIPT.md` ("How to record it"), at `/alexa?film=1`. Check
the header names the model and no red banner shows. Redo any take whose header
says `· dose guard`.

Then refresh the assets the copy points at, which still show the old build:
`pip install -r requirements-dev.txt && playwright install chromium && SHOTS_FILM=1 python3 demo/shots.py http://localhost:8000 shots`,
then convert the matching PNGs over the old JPGs, e.g.
`sips -s format jpeg shots/01-*.png --out docs/img/hold-on-rose.jpg` (likewise
catch-up, sort-it-out, reorder, record), and re-render
`demo/hold-on-rose.m4a` with `demo/voice.py` (needs Piper voices). Until it is
re-rendered, `demo/transcript.md` and `.srt` still have the old line "the chain
is intact: nothing has been edited or removed": re-render, or delete the audio
and its links in README and SUBMISSION.

### 4. Claude Code bonus

`HEARTH_ISSUER=http://127.0.0.1:8765 uvicorn hearth.app:app --port 8765 &`
then `python3 demo/assistant.py http://127.0.0.1:8765` (needs a logged-in
`claude`). Commit `demo/assistant.md` and film 10 s of it for 2:30. If it does
not work, delete the sentence "and `demo/assistant.py` runs Claude Code…" from
`docs/SUBMISSION.md` and the matching paragraph in README.

### 5. Redeploy Render (I did not touch it)

Service `hearth` (`srv-dajsdofqj5pc73etlgeg`, https://hearth-sh3u.onrender.com)
auto-deploys from **`master`**, which is why it still serves the old build
(`/healthz` says `members:3`, `/alexa` is 404). It is on the **free** plan
(sleeps; render.yaml says starter).

1. Dashboard → hearth → Environment: set `HEARTH_ISSUER=https://hearth-sh3u.onrender.com`,
   `HEARTH_RESOURCE=https://hearth-sh3u.onrender.com/mcp`,
   `HEARTH_REDIRECT_URIS=https://hearth-sh3u.onrender.com/console,https://hearth-sh3u.onrender.com/alexa`,
   `HEARTH_RECORD_KEY`, `HEARTH_BEDROCK_MODEL`, `AWS_REGION`,
   `AWS_BEARER_TOKEN_BEDROCK` (so judges see a model plan). Leave
   `HEARTH_NOTIFY_TOM` off unless you are happy for judges to push to it.
   Env changes only apply at the next deploy.
2. Merge `first-place` into `master`
   (`gh pr create -R ubmids/hearth --base master --head first-place --title "first-place"` then merge it).
   The merge auto-deploys. (Alternative: Settings → Branch → `first-place`, then Manual Deploy → Deploy latest commit.)
3. Check: `curl https://hearth-sh3u.onrender.com/healthz` shows `"members":4`,
   and `/alexa` returns 200. Consider Starter plan so it never cold-starts; or
   set the repo variable `HEARTH_LIVE_URL` to turn on keep-warm.

### 6. Open Source mini: what must go public

Both repos have MIT licences. A full-history sweep of both (keys, tokens,
private IPs, personal emails, private box names) found nothing secret; the only
hit is a CPU model name in old `docs/LOCAL_PLANNER.md` history (`02fbed4`),
harmless.

- **`ubmids/alexa-plus-mcp-checks`: must be public**, or the mini entry is
  ineligible. `gh repo edit ubmids/alexa-plus-mcp-checks --visibility public --accept-visibility-change-consequences`
- **`ubmids/hearth`: make public** (the mini asks for the project repo URL),
  after deleting this file:
  `gh repo edit ubmids/hearth --visibility public --accept-visibility-change-consequences`.
  If you keep it private instead, share it with testing@devpost.com and
  `chris-trag`, `knmeiss`, `giolaq`, `anishamalde`, `mosesroth`, `emersonsklar`
  no more than 7 days before submitting.
- `ubmids/cortex` (cited in SUBMISSION) is already public.

### 7. Submit (moved here from SUBMISSION.md)

- [ ] Video under 3:00, public on YouTube or Vimeo, SIMULATED ALEXA+ visible
- [ ] Video URL into `docs/SUBMISSION.md` → Links
- [ ] Product feedback and feature requests pasted from SUBMISSION.md
- [ ] Friction log linked: `docs/FRICTION_LOG.md`
- [ ] Live URL checked (step 5)
- [ ] Submit by 21 Oct; hard deadline 23 Oct 2026, 19:00 UTC

## What I could not do, and why

- Call a real model or Bedrock: no key yet, so the planner is tested only
  against fake Bedrock and OpenAI-compatible servers (step 1 is the real check).
- Deploy, change Render, flip visibility, run `demo/assistant.py`, or
  re-render images and audio: off limits for me, or a model call, or a large
  download (steps 3 to 6).
- A real Echo segment: you are not filming one, so the script uses the Claude
  Code segment or holds the conformance shot.
