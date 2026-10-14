#!/usr/bin/env bash
# A small local model on CPU as the simulated client's planner, with no API key.
#
#   scripts/local_planner.sh            # downloads once, then serves on :8790
#
# llama.cpp's prebuilt CPU server and Qwen2.5-3B-Instruct Q4_K_M (2.0 GiB),
# the combination measured in docs/LOCAL_PLANNER.md. Needs ~3.7 GB RAM and
# 8 free threads. Then, in the shell that runs Hearth:
#
#   export HEARTH_SIM_LLM_BASE_URL=http://127.0.0.1:8790/v1
#   export HEARTH_SIM_LLM_API_KEY=local
#   export HEARTH_SIM_LLM_MODEL=qwen2.5-3b-instruct-q4_k_m
#   export HEARTH_SIM_LLM_TIMEOUT=15 HEARTH_SIM_LLM_WARMUP=1
#
# Measured on a busy 24-thread box it was 2-12 s a line, so it is NOT the
# default and not recommended for filming; see docs/LOCAL_PLANNER.md.
set -euo pipefail
DIR="${LOCAL_MODEL_DIR:-$(dirname "$0")/../local-model}"
BUILD="${LLAMA_BUILD:-b11606}"
MODEL_URL="https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf"
mkdir -p "$DIR"; cd "$DIR"
if [ ! -x "llama-$BUILD/llama-server" ]; then
  curl -fL -o llama.tar.gz \
    "https://github.com/ggml-org/llama.cpp/releases/download/$BUILD/llama-$BUILD-bin-ubuntu-x64.tar.gz"
  tar xzf llama.tar.gz && rm llama.tar.gz
fi
[ -f qwen2.5-3b-instruct-q4_k_m.gguf ] || curl -fL -o qwen2.5-3b-instruct-q4_k_m.gguf "$MODEL_URL"
exec env CUDA_VISIBLE_DEVICES= "llama-$BUILD/llama-server" \
  -m qwen2.5-3b-instruct-q4_k_m.gguf --jinja -t "${THREADS:-8}" -c 8192 \
  --host 127.0.0.1 --port "${PORT:-8790}"
