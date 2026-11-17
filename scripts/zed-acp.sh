#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"
export STRUCTURED_AI_ENV="${STRUCTURED_AI_ENV:-$ROOT_DIR/.env}"
exec python3 -m structuredai.zed_acp
