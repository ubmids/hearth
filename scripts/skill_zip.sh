#!/usr/bin/env bash
# Build the ZIP the Alexa developer console's Code tab imports ("Import Code"):
# a lambda/ folder with the skill's handler, Hearth's MCP client, the APL card,
# requirements.txt and, if you made one, config.json (your Hearth URL and skill
# token). The ZIP lands in out/, which git ignores, because config.json holds
# the token.
#
#   cp skill/lambda/config.example.json skill/lambda/config.json   # then edit it
#   scripts/skill_zip.sh            # -> out/hearth-care-lambda.zip
set -euo pipefail
cd "$(dirname "$0")/.."
src=skill/lambda
work=$(mktemp -d)
mkdir -p "$work/lambda" out
cp "$src/lambda_function.py" "$src/hearth_client.py" "$src/apl.py" "$src/requirements.txt" "$work/lambda/"
if [ -f "$src/config.json" ]; then
  python3 - "$src/config.json" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))
assert c.get("HEARTH_URL", "").startswith("https://"), "config.json: HEARTH_URL must be the https URL of Hearth"
assert len(c.get("HEARTH_TOKEN", "")) >= 32 and " " not in c["HEARTH_TOKEN"], "config.json: HEARTH_TOKEN must be the 32+ character skill token"
PY
  cp "$src/config.json" "$work/lambda/"
  echo "config.json included (HEARTH_URL and token checked)"
else
  echo "no skill/lambda/config.json. Alexa-hosted skills have no environment variables, so make one first; a self-hosted Lambda can set HEARTH_URL and HEARTH_TOKEN instead." >&2
fi
rm -f out/hearth-care-lambda.zip
(cd "$work" && zip -qr - lambda) > out/hearth-care-lambda.zip
rm -rf "$work"
unzip -l out/hearth-care-lambda.zip | tail -n +2
