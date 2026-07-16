#!/usr/bin/env bash
# End-to-end demo: extract -> chunk -> voice-cloned TTS on one short
# public-domain story ("Oshidori" from Kwaidan, ~2 minutes of audio).
set -euo pipefail
cd "$(dirname "$0")/.."

BOOK=kwaidan-stories-and-studies-of-strange-things
UNIT=unit3

if ! python3 -c "import chatterbox" 2>/dev/null; then
  echo "Chatterbox TTS not found. Set up the environment first:"
  echo "  python3 -m venv venv-tts && source venv-tts/bin/activate"
  echo "  pip install -r requirements.txt"
  echo "  # RTX 50-series GPUs also need:"
  echo "  pip install torch==2.7.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cu128"
  exit 1
fi

# First run: create the private voice registry from the tracked template.
if [ ! -f configs/voices.json ]; then
  cp configs/voices.json.example configs/voices.json
  echo "Created configs/voices.json from template."
fi

if python3 -c "import torch, sys; sys.exit(0 if torch.cuda.is_available() else 1)"; then
  echo "CUDA GPU detected."
else
  echo "WARNING: no CUDA GPU detected — generation will run on CPU and may take a long time."
fi

# --start-after skips the Project Gutenberg header baked into the chapter XHTML
python3 scripts/extract_unit.py --book "$BOOK" --unit "$UNIT" --start-after "OSHIDORI" --max-words 300
python3 scripts/chunk_text.py  --book "$BOOK" --unit "$UNIT"
python3 scripts/run_benchmark.py --book "$BOOK" --unit "$UNIT" --phase 2 --production

echo
echo "Demo complete — listen to the result:"
ls output/"$BOOK"/"$UNIT"/*.wav
