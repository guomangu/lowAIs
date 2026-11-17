#!/usr/bin/env bash
# ==============================================================================
# StructuredAI - Lanceur & Contrôle Opérationnel (.env + cgroup 1Go + Zed)
# Usage : ./start.sh [start|doctor|status|pause|resume|priority <f>|retry <f>|stop]
# ==============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${STRUCTURED_AI_ENV:-$ROOT_DIR/.env}"
ACTION="${1:-start}"
shift || true

if [ ! -f "$ENV_FILE" ]; then
  echo "[ERREUR] Fichier .env introuvable ($ENV_FILE). Lancez d'abord : ./install.sh" >&2
  exit 1
fi

PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
[ ! -x "$PYTHON_BIN" ] && PYTHON_BIN="$(command -v python3)"
export PATH="$ROOT_DIR/.venv/bin:$PATH"
export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"

read_env() {
  "$PYTHON_BIN" - "$ENV_FILE" "$1" "$2" << 'PYEOF'
import os, pathlib, sys
env_p, key, default = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
vals = {}
for ln in env_p.read_text(encoding="utf-8").splitlines():
    s = ln.strip()
    if s and not s.startswith("#") and "=" in s:
        k, v = s.split("=", 1)
        vals[k.strip()] = os.path.expandvars(v.strip().strip('"').strip("'"))
print(vals.get(key, default))
PYEOF
}

TARGET_DIR="$(read_env TARGET_PROJECT_DIR "$ROOT_DIR/workspace")"
RAM_LIMIT_MB="$(read_env RAM_LIMIT_MB "1024")"
ZED_SYNC="$(read_env ZED_SYNC_TASKS "true")"
AUTO_START_LLM="$(read_env LLM_AUTO_START_SERVER "true")"

sync_zed_if_enabled() {
  [ "$ZED_SYNC" != "true" ] && return 0
  mkdir -p "$TARGET_DIR/.zed"
  "$PYTHON_BIN" - "$ROOT_DIR/.zed/tasks.json" "$TARGET_DIR/.zed/tasks.json" "$ROOT_DIR" "$ENV_FILE" << 'PYEOF'
import json, pathlib, sys
src, dst, root, env_f = map(pathlib.Path, sys.argv[1:])
if src.exists():
    tasks = json.loads(src.read_text(encoding="utf-8"))
    for t in tasks:
        if t.get("command") == "./start.sh":
            t["command"] = str(root / "start.sh")
            t["env"] = {"STRUCTURED_AI_ENV": str(env_f)}
        elif t.get("command") == ".venv/bin/pytest":
            t["command"] = str(root / ".venv/bin/pytest")
            t["cwd"] = str(root)
    dst.write_text(json.dumps(tasks, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PYEOF
  if command -v flatpak >/dev/null 2>&1 && flatpak info dev.zed.Zed >/dev/null 2>&1; then
    flatpak override --user --filesystem="$TARGET_DIR" dev.zed.Zed 2>/dev/null || true
    flatpak override --user --env=STRUCTUREDAI_LOCAL_API_KEY=local dev.zed.Zed 2>/dev/null || true
  fi
  "$PYTHON_BIN" -m structuredai.zed_config "$ROOT_DIR" "$ENV_FILE" >/dev/null 2>&1 || true
}

if [ "$ACTION" = "start" ]; then
  sync_zed_if_enabled
  if command -v systemd-run >/dev/null 2>&1 && [ "$AUTO_START_LLM" = "true" ] && systemd-run --user --scope -p MemoryMax=64M true >/dev/null 2>&1; then
    HARD_CAP_MB=$((RAM_LIMIT_MB + 256))
    echo "[StructuredAI] Démarrage sous cgroup (MemoryHigh=${RAM_LIMIT_MB}M, MemoryMax=${HARD_CAP_MB}M, Swap=0)..."
    exec systemd-run --user --scope -p "MemoryHigh=${RAM_LIMIT_MB}M" -p "MemoryMax=${HARD_CAP_MB}M" -p MemorySwapMax=0 \
      "$PYTHON_BIN" -m structuredai.main start --env "$ENV_FILE" "$@"
  fi
  exec "$PYTHON_BIN" -m structuredai.main start --env "$ENV_FILE" "$@"
fi

exec "$PYTHON_BIN" -m structuredai.main "$ACTION" "$@" --env "$ENV_FILE"
