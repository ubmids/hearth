# A local model as the simulated client's planner, measured

The simulated Alexa+ page (`/alexa`) has to decide which Hearth tool an
utterance becomes. With no model configured, the built-in rules decide, and the
header says `planner: rules`. With any OpenAI-compatible endpoint configured
(`HEARTH_SIM_LLM_*`), a model decides, taught by the `hearth-care` Agent
Skill, and the header says `model:… + skill:hearth-care`.

This page records what happens with no API key at all: a small model on CPU.
Measured 14 October 2026.

## Setup

- llama.cpp prebuilt CPU server, build b11606, run with `CUDA_VISIBLE_DEVICES=`.
- Qwen2.5-3B-Instruct, Q4_K_M GGUF (2.0 GiB).
- `llama-server --jinja -t 8 -c 8192`; resident memory 3.35–3.7 GB after load.
- AMD Ryzen 9 9900X (24 threads). **The machine was busy**: two unrelated model
  servers were using about 12 cores, load average 16–25, swap full. Decode ran
  at 4–9 tokens/s. An idle machine would be faster; that was not measured.
- Script: `scripts/local_planner.sh` downloads both and starts the server.

## What it costs

The fixed prompt (planner instructions, the Agent Skill, 13 tool schemas) is
about 2,674 tokens. llama.cpp caches it, so after the first request a new line
costs 11–26 prompt tokens and the wait is almost all the model writing its tool
call (19–56 tokens).

| line | expected | first call | warm median / max | model chose |
|---|---|---|---|---|
| Rose: I'm just going to take my blood thinner. | give_dose | 12.0 s (timed out) | 7.2 / 7.5 s | give_dose, "blood thinner", Rose |
| Tom: what did I miss with Mom today? | catch_up | 6.9 s | 5.1 / 5.4 s | catch_up, Tom |
| Tom: Why did you stop her? | why | 5.7 s | 4.4 / 5.6 s | why |
| Ada: cardiology moved to Thursday at 10. Sort it out. | arrange | 12.0 s (timed out) | 12.0 / 12.0 s (3 of 4 timed out; 9.2 s with a long timeout) | arrange, cardiology, 2026-10-15T10:00, Ada |
| Grace: nearly out of her warfarin. Reorder it. | reorder | 5.9 s | 3.7 / 4.3 s | reorder, warfarin, Grace |
| Grace: Yes, go ahead. | checkout (host) | never reaches the model | – | the host step, from context |
| Tom: can Mom have a coffee? | whats_true | 4.5 s | 3.9 / 4.2 s | whats_true, diet, coffee_cutoff, Mom |
| Ada: Mom finished the antibiotics. | remember | 3.8 s | 3.2 / 3.8 s | remember, Ada |
| Ada: show me the record. | record | 3.5 s | 2.2 / 2.4 s | record |

The very first request after starting the server took 18.7 s (15 s of it
processing the prompt).

## Verdict

- **Accuracy is fine**: the right tool with sensible arguments on all 8 lines
  that reach the model, identical on every repeat.
- **Latency is not camera-safe as measured**: most lines take 3–7 s, the
  appointment line about 12 s. Alexa answers in about a second; a 4-second
  pause after somebody speaks breaks the scene.
- **When the model times out, the rules answer**, and they pick the same tool,
  so the scene stays correct; it just waits, and the page shows `rules`.
- **For filming**: use the rules planner (leave `HEARTH_SIM_LLM_*` unset), or a
  hosted model with tool calling. Use the local model on camera only if, on an
  idle machine, every warm line comes back in under about 2 s.

## Settings that help

- `HEARTH_SIM_LLM_TIMEOUT` (seconds, default 12): how long a plan may take
  before the rules answer instead.
- `HEARTH_SIM_LLM_WARMUP=1`: Hearth sends one throwaway plan at startup, with
  `HEARTH_SIM_LLM_WARMUP_TIMEOUT` (default 120 s), so the first person to speak
  does not pay the 15-second prompt.
- The base URL must end in `/v1` for llama.cpp
  (`HEARTH_SIM_LLM_BASE_URL=http://127.0.0.1:8790/v1`).
