# Shot list and how to finish the video

Everything lives in `~/Desktop/hackathons/hearth-video/`, outside the repo
(media does not belong in git).

```
hearth-video/
  take5/              the current take (15 Oct, Pharmacy Label design)
    sim-run.mp4       the simulated Alexa+ afternoon, 7 scenes, every line voiced
    hearth-demo.mp4   the cut, from rough_cut.py: 2:57.3 with every placeholder in
    hearth-demo.srt   captions for the upload
    cut.json          each segment, its source, and whether it is a placeholder
  inserts/            YOUR FILES GO HERE (conformance.txt is already there)
  voices/             optional: real people's lines, for a new take
```

## Finish it: four files, then one command

Record on the phone, AirDrop to the Mac, and save each file into
`~/Desktop/hackathons/hearth-video/inserts/` with exactly this name.

| # | file | what | by |
|---|---|---|---|
| 1 | `amazon.mp4` | **8 s** screen recording of the Alexa developer console Test tab: type `open hearth care`, then `I'm just going to take my blood thinner`, until the red card shows. Steps: `docs/ALEXA_TEST.md`. Cmd+Shift+5, selected portion, at least 1280 wide. | **18 Oct** |
| 2 | `n-traffic.m4a` | Voice Memo: "Over MCP, a model chose give dose. Hearth's server refused it, and signed the refusal into the record." | 20 Oct |
| 2 | `n-tech.m4a` | Voice Memo: "MCP 2025-11-25, passing the official conformance suite. And the model choosing every call is a small open one on this laptop. It doesn't need to know warfarin. Hearth does." | 20 Oct |
| 2 | `n-close.m4a` | Voice Memo: "Hearth. The memory, and the conscience, of a family caring for someone." | 20 Oct |
| 3 | `oncam.mp4` (or `.mov`) | **12 s** of you to camera, landscape, head and shoulders, phone on a stand at eye level, window light from the side. One true sentence, or the fallback: "I built Hearth for families splitting the care of a parent: a daughter with the doctor's letters, a son two states away, an aide on weekday mornings. Nobody holds the whole picture. That gap is where doses get doubled." | 20 Oct |
| 4 | `buzz.mp4` (or `.mov`) | **3 s** of a phone lying screen up on a table as the push arrives (below). | 20 Oct |

**The push for `buzz.mp4`.** Install the free **ntfy** app on the phone and
subscribe to a hard-to-guess topic, say `hearth-ada-7q2x`. Start filming the
phone, then on the Mac send Hearth's own handover push with Hearth's own
sender:

```bash
cd ~/Desktop/hackathons/hearth && python3 -c "from hearth.notify import _send; _send('https://ntfy.sh/hearth-ada-7q2x', {'by': 'Grace', 'text': 'Grace flagged at handover: she was a bit dizzy after her walk.'}, 'Ada')"
```

The banner reads "Hearth: from Grace". Keep the 3 seconds around it.

**Then the one command** (any time; re-run it after each file you add):

```bash
cd ~/Desktop/hackathons/hearth && python3 demo/rough_cut.py ~/Desktop/hackathons/hearth-video/take5 --inserts=~/Desktop/hackathons/hearth-video/inserts
```

It needs only ffmpeg: the cards rendered for take 5 are reused. It prints each
segment, marks any still a PLACEHOLDER, and prints the total. With the four
files at the lengths above the total is about 2:55. If it says OVER 3:00,
trim `oncam` first, then `amazon`, never below 8 s.

When nothing says PLACEHOLDER (the people's voices may stay `say`, see below),
upload `take5/hearth-demo.mp4` to YouTube as **public**, title "Hearth: an
Alexa+ add-on for families caring for a parent", add `take5/hearth-demo.srt`
as captions, and paste the URL into `docs/SUBMISSION.md` under Links.

## Optional: the four people's real voices (20 minutes, a new take)

The placeholder people's voices are macOS `say`; the judges' audit says
synthetic family voices read as "a robot play", and real voices are quicker,
which brings the total to about 2:50. Rose (older woman), Grace (the aide),
Tom (Subomi can do Tom), Ada (a woman, 40s). One file per line in `voices/`:

| file | line |
|---|---|
| `00-rose.m4a` | "Alexa, I'm just going to take my blood thinner." |
| `01-grace.m4a` | "Alexa, I'm off. Mom ate half her lunch, she was a bit dizzy after her walk, and we're nearly out of Ensure." |
| `02-tom.m4a` | "Alexa, what did I miss with Mom today?" |
| `03-ada.m4a` | "Alexa, Mom's cardiology moved to Thursday at 10. Sort it out." |
| `04-ada.m4a` | "Alexa, order what's on the list." |
| `05-ada.m4a` | "Yes, go ahead." |
| `06-ada.m4a` | "Alexa, show me the record." |

A new take needs a fresh local Hearth, the local planner and playwright
(`pip install -r requirements-dev.txt`), so ask an agent, or:

```bash
cd ~/Desktop/hackathons/hearth
# HEARTH_TZ: any zone where it is now mid-afternoon (the device clock follows it)
export HEARTH_TZ=America/Sao_Paulo HEARTH_ISSUER=http://localhost:8000 HEARTH_DATA=/tmp/hearth-take6/db
export HEARTH_SIM_LLM_PROVIDER=openai HEARTH_SIM_LLM_BASE_URL=http://localhost:11434/v1
export HEARTH_SIM_LLM_API_KEY=ollama HEARTH_SIM_LLM_MODEL=qwen2.5:7b-instruct
export HEARTH_SIM_LLM_TIMEOUT=30 HEARTH_SIM_LLM_WARMUP=1
mkdir -p /tmp/hearth-take6 && python3 -m uvicorn hearth.app:app --port 8000 &   # wait ~40 s for the warm-up
python3 demo/film.py http://localhost:8000 ~/Desktop/hackathons/hearth-video/take6 \
    --voices=~/Desktop/hackathons/hearth-video/voices
python3 demo/rough_cut.py ~/Desktop/hackathons/hearth-video/take6 \
    --inserts=~/Desktop/hackathons/hearth-video/inserts
```

`film.py` prints REDO if any scene was not planned by the model alone (it
timed out to the offline rules, or a guard stepped in): run that take again.

## Which model plans a take

The header names it. Take 5 is `qwen2.5:7b-instruct` through Ollama on the
laptop, which is free and says "on this machine": a point in itself, since the
safety is in the server and the planner can be small. On a busy Mac a call
takes 3 to 8 s, so keep `HEARTH_SIM_LLM_TIMEOUT=30` and the warm-up on, or the
first scenes fall back to the offline rules. The other options (a hosted
model through a relay, or Amazon Bedrock with `HEARTH_BEDROCK_MODEL`,
`AWS_REGION`, `AWS_BEARER_TOKEN_BEDROCK`) cost money and are not needed.
