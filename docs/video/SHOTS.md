# Shot list and how to finish the video

Everything lives in `~/Desktop/hackathons/hearth-video/` (outside the repo:
media does not belong in git).

```
hearth-video/
  take1/              a film.py take: screen.webm, audio/, timeline.json, sim-run.mp4
    hearth-demo.mp4   the cut, from rough_cut.py
    cut.json          each segment, its source, and whether it is a placeholder
  voices/             real people's lines, for film.py --voices
  inserts/            real footage and narration, for rough_cut.py --inserts
```

## What is already rendered

| piece | where | made by |
|---|---|---|
| The whole simulated Alexa+ afternoon, 7 scenes, with Alexa's voice at each answer | `take1/sim-run.mp4` | `demo/film.py` |
| Lower thirds, stats card, tech card (real `scripts/conformance.sh` output), close card | `take1/cut/*.png` | `demo/rough_cut.py` + `demo/cards.html` |
| A full cut with placeholders | `take1/hearth-demo.mp4` | `demo/rough_cut.py` |

## What needs a person (about 90 minutes in all)

Do them in this order. Each one makes the cut better on its own, so stop
wherever time runs out.

### 1. Narration, Subomi (10 minutes, any quiet room)

Record on the phone's Voice Memos, one file per line, then AirDrop them into
`inserts/`:

| file | line |
|---|---|
| `n-traffic.m4a` | "Over MCP, a model chose give dose. Hearth's server refused it, and signed the refusal into the record." |
| `n-tech.m4a` | "MCP 2025-11-25, passing the official conformance suite. And the model choosing every call is a small open one on this laptop. It doesn't need to know warfarin. Hearth does." |
| `n-close.m4a` | "Hearth. The memory, and the conscience, of a family caring for someone." |

### 2. On camera, Subomi or a real carer (20 minutes)

`inserts/oncam.mp4`, 12 to 14 seconds, landscape, head and shoulders, phone
on a stand at eye level, window light from the side, phone mic within a metre.
Say one true thing. If there is a person in your life who has missed or
doubled a dose, or who looks after a parent, say that in one sentence. If not,
the fallback line is in `SCRIPT.md` at 0:20. A real carer saying it is worth
more than anything else in the video: if a friend or neighbour does this
work, ask them for 15 seconds.

### 3. The phone buzz (5 minutes)

1. Install **ntfy** on the phone and subscribe to a hard-to-guess topic.
2. Start Hearth with `HEARTH_NOTIFY_ADA=https://ntfy.sh/<topic>`.
3. Film the phone lying on a table, screen up. Trigger Grace's handover (play
   the take, or type the line at `/alexa`). Keep 3 seconds: the buzz and the
   banner "Hearth: from Grace".
4. Save as `inserts/buzz.mp4`.

### 4. The Amazon console shot (40 minutes, needs the Amazon login)

Follow `docs/ALEXA_TEST.md`. Screen-record the Test tab (Cmd+Shift+5,
selected portion, at least 1280 wide) while typing `open hearth care` and
`I'm just going to take my blood thinner`, until the red card shows. Keep
10 seconds and save as `inserts/amazon.mp4`. If you have an Echo Show, film it
there as well and use whichever looks better.

### 5. The four people's lines (20 minutes, optional but worth it)

Four voices: Rose (older woman), Grace (the aide), Tom (Subomi can do Tom),
Ada (a woman, 40s). Record each line as its own file in `voices/`, named by
scene:

| file | line |
|---|---|
| `00-rose.m4a` | "Alexa, I'm just going to take my blood thinner." |
| `01-grace.m4a` | "Alexa, I'm off. Mom ate half her lunch, she was a bit dizzy after her walk, and we're nearly out of Ensure." |
| `02-tom.m4a` | "Alexa, what did I miss with Mom today?" |
| `03-ada.m4a` | "Alexa, Mom's cardiology moved to Thursday at 10. Sort it out." |
| `04-ada.m4a` | "Alexa, order what's on the list." |
| `05-ada.m4a` | "Yes, go ahead." |
| `06-ada.m4a` | "Alexa, show me the record." |

Then record a new take with them (step 6). The typing on screen follows each
recording's length.

### 6. Re-render (5 minutes, on the laptop, or ask an agent)

```bash
cd ~/Desktop/hackathons/hearth
# a fresh Hearth for the take: see the top of demo/film.py for the env
# (planner model, HEARTH_TZ set to a zone where it is mid-afternoon, ntfy topic)
python3 demo/film.py http://localhost:8000 ~/Desktop/hackathons/hearth-video/take2 \
    --voices=~/Desktop/hackathons/hearth-video/voices
python3 demo/rough_cut.py ~/Desktop/hackathons/hearth-video/take2 \
    --inserts=~/Desktop/hackathons/hearth-video/inserts
```

`rough_cut.py` prints every segment, flags any that are still placeholders,
and prints the total length. When nothing says PLACEHOLDER and the total is
under 3:00, upload `hearth-demo.mp4` to YouTube or Vimeo as **public**, title
"Hearth: an Alexa+ add-on for families caring for a parent", and paste the URL
into `docs/SUBMISSION.md`.

## Which model plans the take

The header names it. Options, cheapest first:

1. **A local model** (free): `HEARTH_SIM_LLM_BASE_URL=http://localhost:11434/v1`,
   `HEARTH_SIM_LLM_MODEL=qwen2.5:7b-instruct` (native tool calls, about 1 s a
   line on an M2 Pro when nothing else is using the GPU) or `qwen2.5vl:7b`
   (no tool API, so Hearth asks it for JSON; also right on every demo line).
   The header says "on this machine", which is a point in itself: the safety
   is in the server, so the planner can be small.
2. **Claude Haiku through a relay**: set the OpenAI-compatible base URL to the
   relay, the model to `claude-haiku-4-5-20251001`, and
   `HEARTH_SIM_LLM_LOCAL=0` so the header does not say "on this machine".
   About 5,000 input tokens a line, so a few cents a take.
3. **Amazon Bedrock**: `HEARTH_BEDROCK_MODEL`, `AWS_REGION`,
   `AWS_BEARER_TOKEN_BEDROCK`. Header: "on Amazon Bedrock". The most on-brand,
   since Alexa+ runs on Bedrock; needs an AWS account with model access.

Redo any take whose header shows `· dose guard` or `· day as said` on a
filmed scene: the guards are right to step in, but the take should show the
model getting it right.
