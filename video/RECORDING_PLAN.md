# Hearth: recording plan for tonight (Tue 20 Oct)

> **Superseded 20 Oct: nothing to record.** The narrated video is built in
> Subomi's ElevenLabs voice: `~/Desktop/hackathons/hearth-video/hearth-narrated.mp4`
> (2:39) with `hearth-narrated.srt`, from `python3 demo/narrated_cut.py`
> (script in `video/NARRATION.md`; upload and form steps in
> `~/Desktop/hackathons/hearth-video/SUBMIT.md`).

## What's broken or missing (checked 20 Oct, 11:00 to 12:30 WAT)

Nothing blocks the video. Every app shot is already filmed (take 5), and the
cut was rebuilt today from that take with no errors.

| # | Problem | Effect | Fix tonight |
|---|---|---|---|
| 1 | `inserts/amazon.mp4` was never recorded. It needs the Amazon developer console and a classic skill (`docs/ALEXA_TEST.md`, about 40 min). | Without it, the cut shows a red PLACEHOLDER slate. | **Skip it** with `--skip=amazon`. The rules don't require it, because the simulated Alexa+ path is allowed. |
| 2 | Nothing has been recorded yet: no narration, no face, no phone buzz. | macOS `say` reads the narrator lines, and the "why" card is a red placeholder. | Record 4 voice memos (below). Any line you don't record shows as an on-screen caption with `--captions`. |
| 3 | The four family voices (Rose, Grace, Tom, Ada) are macOS `say`. | The earlier audit said it sounds a bit like "a robot play". | Leave it tonight. Fixing it means four people and a new take (`docs/video/SHOTS.md`, optional section). |
| 4 | The live site shows times in the server's time zone, e.g. "Grace gave it at 5:55 this morning" at noon in Lagos. | Cosmetic. The video uses take 5, which is already right. | None. |
| 5 | `/console` opened in a new tab shows its own household ("Hearth has not acted yet"), not the one a visitor just used on `/alexa`. | A judge might expect to see their own calls there. | None tonight. It's worth one line in the testing notes. |

**Fixed today:** `demo/rough_cut.py --captions`. Any narration line you
haven't recorded now shows as a caption in the label style, never as a red
placeholder or a robot narrator. A version with zero recordings, 2:45.9,
is already rendered here:
`~/Desktop/hackathons/hearth-video/hearth-demo-captions-only.mp4`.
**You can upload that as it is if tonight goes badly.**

## The facts

- **Event:** Build, Ship, Shape, Amazon Developer Hackathon (Devpost), Alexa+ track.
- **Deadline:** Fri 23 Oct 2026, 12:00 PDT, which is **20:00 Lagos time (WAT)**. Plan to submit Thu 22 Oct.
- **Video rules (official rules page, checked 20 Oct):**
  - Under 3 minutes. Judges stop watching at 3:00.
  - Must show the project working. The Alexa+ simulated path is allowed if the video clearly shows it's simulated. Ours says so in the header, on every device frame and on the close card.
  - Public on YouTube or Vimeo, in English.
  - No copyrighted music.
  - **No voiceover or face is required.**
- **Length now:**
  - About 2:45 with the four voice memos and the two skips.
  - 2:46 captions-only.
  - The cut prints the real total every time.

## The story in 3 beats

1. **Problem (0:00 to 0:38).**
   - A family shares the care of Mom. Rose, 84, is about to take a second blood thinner.
   - Hearth stops it because Grace already gave today's dose.
   - Then the "why": 63M family caregivers, and warfarin is in 1 in 3 overdose hospitalisations.
2. **Demo (0:38 to 2:26).** One afternoon, every scene feeding the next:
   - Grace's handover reaches Tom's catch-up.
   - Ada moves an appointment, and Hearth rebooks the ride and tells Tom.
   - Ada orders what Grace put on the list.
   - The signed record shows it all.
3. **Why it matters (2:26 to end).**
   - The safety lives in the server, not the model. It passes the official MCP conformance suite, with a small open model planning on a laptop.
   - "The memory, and the conscience, of a family caring for someone."

## Shot list (all pre-rendered except the rows marked YOU)

Times are from today's captions-only cut. Real memos move them by a second or two.

| time | segment | what's on screen | sound | source |
|---|---|---|---|---|
| 0:00 | hero | Kitchen Echo Show, simulated. Rose's line, then the red **Already taken today** label, then the MCP traffic panel slides in once. | Rose, Alexa, then **YOU: n-traffic** over the traffic panel | take 5 |
| 0:22 | oncam | "Why this matters" card: 63M / 1 in 3 | **YOU: n-oncam** (or your face, `oncam.mp4`) | card |
| 0:38 | handover | Grace hands over. The label gets three ticks: list, flag, family board. | Grace, Alexa | take 5 |
| 0:59 | catchup | Tom's Echo Dot: what did I miss | Tom, Alexa | take 5 |
| 1:25 | arrange | Ada: cardiology moved to Thursday. Calendar, rota, ride, board, phone. | Ada, Alexa | take 5 |
| 1:47 | order | Ada orders the list, sandbox checkout | Ada, Alexa | take 5 |
| 2:12 | record | "Show me the record": 7 calls, 1 refused, intact | Ada, Alexa | take 5 |
| 2:26 | tech | Conformance card: six PASS lines and badges | **YOU: n-tech** | card |
| 2:39 | close | hearth. github.com/ubmids/hearth. "Alexa+ is simulated in this video" | **YOU: n-close** | card |

Screens checked today with headless Chrome, in `video/shots/` (not in git):
- `local-*.png`: a fresh local server, all 10 scripted scenes and the console.
- `live-*.png`: the same walk against https://hearth-sh3u.onrender.com, which is up, answered in 1 s, and showed no page errors.

## Setup checklist (5 minutes)

- [ ] **Do Not Disturb on**, on both the phone and the Mac (Control Centre, Focus).
- [ ] A quiet room with soft things around: a bedroom with curtains beats a kitchen. Fan and AC off.
- [ ] **Phone: Voice Memos app.**
  - Settings, Voice Memos, Audio Quality: **Lossless**.
  - Hold the phone about 20 cm from your mouth, slightly below it, not pointing straight at it.
- [ ] Free disk on the Mac: about 7 GB is free. The cut needs under 200 MB, so it's fine. Don't screen-record anything long.
- [ ] Optional, for the face clip: phone in landscape on a stack of books at eye level, window light in front of you, not behind.

Nothing to start: no servers, no browser, no test accounts. The app footage
is already filmed.

## Do this, in order (about 25 minutes)

1. **Record 4 voice memos.** Read SCRIPT.md, then record each line 2 or 3 times in one memo and keep the best take.
   - Trim each memo in Voice Memos (the ... menu, Edit Recording, Trim) so it starts and ends within half a second of your words.
   - Rename them exactly: `n-traffic`, `n-oncam`, `n-tech`, `n-close`.
2. **AirDrop them to the Mac.** Move them into `~/Desktop/hackathons/hearth-video/inserts/` (the folder already holds `conformance.txt`). They arrive as `.m4a`, which is right.
3. **Optional, skip if tired: the face clip.** 12 s of you saying the n-oncam line to camera, saved as `inserts/oncam.mov`. If it exists, it replaces the card.
4. **Optional: the phone buzz** (`docs/video/SHOTS.md`, row 4). Needs the free ntfy app. If you do it, drop `,buzz` from the skip list below.
5. **Build the video:**
   ```bash
   cd ~/Desktop/hackathons/hearth && python3 demo/rough_cut.py ~/Desktop/hackathons/hearth-video/take5 --inserts=~/Desktop/hackathons/hearth-video/inserts --skip=buzz,amazon --captions
   ```
   - It prints every segment and the total. No line should say PLACEHOLDER.
   - The total should read "under 3:00".
   - Ignore the "placeholder voices (macOS say) for: Rose, Grace..." note. That's issue 3 above.
6. **Watch it once**: `open ~/Desktop/hackathons/hearth-video/take5/hearth-demo.mp4`. If a memo sounds bad, re-record that one memo, replace the file and re-run step 5. It takes about a minute.
7. **Upload (not tonight if you don't want to; the deadline is Fri 20:00 WAT).**
   - YouTube Studio, Create, Upload video: `take5/hearth-demo.mp4`.
   - Title: "Hearth: an Alexa+ add-on for families caring for a parent". Visibility: **Public**.
   - Subtitles: upload `take5/hearth-demo.srt`, "With timing".
   - Paste the URL into `docs/SUBMISSION.md` under Links.

## If something breaks

- **rough_cut.py errors:** upload `~/Desktop/hackathons/hearth-video/hearth-demo-captions-only.mp4`. It's complete, honest and 2:46. Its captions file is `hearth-demo-captions-only.srt` next to it.
- **A memo won't import, or the volume is wrong:** delete that one file from `inserts/`. With `--captions`, its line becomes a caption.
- **Over 3:00 (only possible with long face or buzz clips):**
  - Re-trim `oncam` to 10 s first.
  - Next, add `record` to `--skip`.
  - Never cut the hero or the order.
- **You want to show the live site instead:** open https://hearth-sh3u.onrender.com/alexa about 2 minutes early (the free server can be slow to wake). Then Cmd+Shift+5, "Record Selected Portion" over the browser at 100% zoom, and press "Next scene" (or →) ten times. You don't need to do this, though: take 5 is the same app.

## Recording tools on this Mac

- **Voice:**
  - iPhone Voice Memos, then AirDrop. This is the simplest.
  - Or QuickTime Player, File, New Audio Recording. Pick the mic with the arrow next to the red button. File, Export As, Audio Only (.m4a).
- **Face:** the iPhone camera, 1080p, landscape. AirDrop the .mov.
- **Screen** (only for the live fallback): Cmd+Shift+5, Options, Microphone: None. The app's sound isn't needed because Alexa's voice is in take 5.
- **Size:** the cut is H.264 at about 0.5 MB per second, so roughly 70 to 90 MB. YouTube takes it as is, with no export step.
