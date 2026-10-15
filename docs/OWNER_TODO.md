# Owner to-do (delete this file before the repo goes public)

`git rm docs/OWNER_TODO.md && git commit -m "docs: remove the to-do list"`
before flipping visibility. It holds no secrets, only steps.

## Where things stand (15 Oct)

- **Live and current.** Render auto-deploys `master` (which now equals
  `first-place`). `/healthz` shows `members:4`, `/alexa` plays all ten scenes
  against the live server in a headless browser, and `tests/test_live.py`
  passes everything except the round-trip-under-500-ms check from Lagos,
  where the network alone is 715 ms and the server's own share is 0.7 ms.
- **The live planner is the offline rules**, labelled as such. No model key is
  on Render, on purpose. To show a model to judges later, add
  `HEARTH_SIM_LLM_BASE_URL`, `HEARTH_SIM_LLM_API_KEY` and
  `HEARTH_SIM_LLM_MODEL` (any OpenAI-compatible endpoint), or
  `HEARTH_BEDROCK_MODEL` + `AWS_REGION` + `AWS_BEARER_TOKEN_BEDROCK`, in the
  Render dashboard. Any visitor to `/alexa` then spends that key, so use a
  capped one.
- **Keep-warm.** The app pings itself every 10 minutes (`HEARTH_KEEPALIVE`,
  on). GitHub Actions cannot run while the repo is private (billing), so the
  `keep-warm` workflow only takes over once the repo is public: then set the
  repo variable `HEARTH_LIVE_URL=https://hearth-sh3u.onrender.com`.
- **Free-hours risk.** The workspace has two free services, `hearth` and
  `gate-api`, sharing 750 free instance hours a month. Hearth awake all of
  November is 720 hours. If `gate-api` gets traffic, Hearth can be suspended
  in the middle of judging (9 to 20 Nov). Either suspend `gate-api` for
  November or put Hearth on Starter ($7). Starter also removes the cold start.
- **The video** is rendered with placeholders: see `docs/video/SHOTS.md`. The
  current cut is `~/Desktop/hackathons/hearth-video/take4/hearth-demo.mp4`.

## Your steps, in order

1. **Amazon developer console (40 min, by 18 Oct).** `docs/ALEXA_TEST.md`:
   make the skill token, add `HEARTH_SKILL_TOKEN` on Render, build the ZIP,
   create the Alexa-hosted skill, test in the simulator, screen-record 10 s.
   Note anything that goes wrong for the friction log.
2. **Film and record (about 1 h, by 20 Oct).** `docs/video/SHOTS.md` steps 1
   to 5: narration, 12 s on camera, the phone buzz, the console recording,
   optionally real voices for Rose, Grace, Ada and Tom.
3. **Render the final cut** (`docs/video/SHOTS.md` step 6, or ask an agent).
   Upload public to YouTube or Vimeo, with `hearth-demo.srt` as captions.
   Paste the URL into `docs/SUBMISSION.md` under Links.
4. **Free hours (by 1 Nov).** Suspend `gate-api` for November, or upgrade
   Hearth to Starter.
5. **Make both repos judgeable (by 21 Oct).** Delete this file first.
   - `gh repo edit ubmids/alexa-plus-mcp-checks --visibility public --accept-visibility-change-consequences`
     (the Open Source mini is ineligible while it is private).
   - `gh repo edit ubmids/hearth --visibility public --accept-visibility-change-consequences`.
     If you keep it private instead, share it with testing@devpost.com and
     `chris-trag`, `knmeiss`, `giolaq`, `anishamalde`, `mosesroth`,
     `emersonsklar` no more than 7 days before submitting.
   - Then set the repo variable `HEARTH_LIVE_URL` (keep-warm) and check that
     both repos' About sections show "MIT License".
6. **Submit by 21 Oct** (hard deadline 23 Oct, 12:00 PDT / 19:00 UTC). Paste
   from `docs/SUBMISSION.md`: description, testing instructions, product
   feedback, feature requests, the Open Source fields, the live URL and the
   video URL. Link `docs/FRICTION_LOG.md`.

## Optional

- **Claude Code as a second client** ("a nice bonus", per the FAQ):
  `HEARTH_ISSUER=http://127.0.0.1:8775 uvicorn hearth.app:app --port 8775 &`
  then `python3 demo/assistant.py http://127.0.0.1:8775` with a logged-in
  `claude`. Commit `demo/assistant.md`. If it is not run, delete the sentence
  about it in `docs/SUBMISSION.md` and README.
- **A name change** (Kinsay, Kinrule): only if decided before filming.
