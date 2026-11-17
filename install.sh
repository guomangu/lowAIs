#!/usr/bin/env bash
# ==============================================================================
# StructuredAI - Installeur Unique Adaptatif pour Fedora & Zed
# Usage : ./install.sh  (sans aucune option requise)
# ==============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$ROOT_DIR/.env"
AUTO_YES=false
NO_LAUNCH=false

for arg in "$@"; do
  case "$arg" in
    --yes|-y) AUTO_YES=true ;;
    --no-launch) NO_LAUNCH=true ;;
  esac
done
[ ! -t 0 ] && AUTO_YES=true

log()  { printf "\033[1;34m[StructuredAI]\033[0m %s\n" "$*"; }
ok()   { printf "\033[1;32m[OK]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[WARN]\033[0m %s\n" "$*"; }
err()  { printf "\033[1;31m[ERREUR]\033[0m %s\n" "$*" >&2; }

ask_default() {
  local prompt="$1" default="$2" ans=""
  if $AUTO_YES; then
    printf "%s" "$default"
    return 0
  fi
  read -r -p "$prompt [$default] : " ans
  printf "%s" "${ans:-$default}"
}

detect_fedora() {
  if [ -f /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    if [[ "${ID:-}" != "fedora" && "${ID_LIKE:-}" != *"fedora"* ]]; then
      warn "Distribution détectée (${PRETTY_NAME:-inconnue}) non Fedora ; adaptation au mieux via dnf."
    else
      ok "Système Fedora détecté : ${PRETTY_NAME:-Fedora} (${ARCH:-$(uname -m)})"
    fi
  fi
}

detect_physical_threads() {
  local cores=""
  cores=$(lscpu -p=Core,Socket 2>/dev/null | grep -v '^#' | sort -u | wc -l || true)
  if [ -z "$cores" ] || [ "$cores" -eq 0 ] 2>/dev/null; then
    cores=$(nproc 2>/dev/null || echo 4)
  fi
  [ "$cores" -lt 2 ] && cores=2
  [ "$cores" -gt 6 ] && cores=6
  printf "%s" "$cores"
}

ensure_local_bin_path() {
  mkdir -p "$HOME/.local/bin"
  if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    export PATH="$HOME/.local/bin:$PATH"
    if [ -f "$HOME/.bashrc" ] && ! grep -q '\.local/bin' "$HOME/.bashrc"; then
      printf '\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$HOME/.bashrc"
    fi
  fi
}

install_fedora_deps() {
  log "Vérification des dépendances système Fedora..."
  local pkgs=()
  command -v git >/dev/null || pkgs+=(git)
  command -v python3 >/dev/null || pkgs+=(python3 python3-pip)
  command -v curl >/dev/null || pkgs+=(curl)
  command -v flatpak >/dev/null || pkgs+=(flatpak)
  command -v systemd-run >/dev/null || pkgs+=(systemd)

  local need_build_llama=false
  if ! command -v llama-server >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/llama-server" ]; then
    if dnf -q list --available llama-cpp >/dev/null 2>&1; then
      pkgs+=(llama-cpp)
    else
      need_build_llama=true
      pkgs+=(cmake gcc-c++ libcurl-devel)
    fi
  fi

  if [ "${#pkgs[@]}" -gt 0 ]; then
    log "Installation des paquets manquants via dnf : ${pkgs[*]}"
    sudo dnf install -y "${pkgs[@]}"
  fi

  if $need_build_llama && ! command -v llama-server >/dev/null 2>&1; then
    build_llama_cpp
  fi
  ok "Dépendances système & moteur IA prêts."
}

build_llama_cpp() {
  local src_dir="$HOME/.local/share/structuredai/llama.cpp"
  log "Compilation optimisée de llama-server pour ce CPU..."
  mkdir -p "$(dirname "$src_dir")"
  if [ ! -d "$src_dir/.git" ]; then
    git clone --depth 1 https://github.com/ggml-org/llama.cpp.git "$src_dir"
  fi
  cmake -S "$src_dir" -B "$src_dir/build" -DGGML_NATIVE=ON -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=ON
  cmake --build "$src_dir/build" --target llama-server -j "$(detect_physical_threads)"
  ln -sf "$src_dir/build/bin/llama-server" "$HOME/.local/bin/llama-server"
}

find_zed_cmd() {
  if command -v zed >/dev/null 2>&1; then
    echo "zed"
  elif command -v zeditor >/dev/null 2>&1; then
    echo "zeditor"
  elif flatpak info dev.zed.Zed >/dev/null 2>&1; then
    echo "flatpak run dev.zed.Zed"
  else
    echo ""
  fi
}

install_and_connect_zed() {
  log "Vérification et connexion de l'éditeur Zed..."
  local zed_cmd
  zed_cmd="$(find_zed_cmd)"
  if [ -z "$zed_cmd" ]; then
    log "Zed absent : installation via Flatpak (Flathub)..."
    flatpak remote-add --if-not-exists --user flathub https://flathub.org/repo/flathub.flatpakrepo
    flatpak install -y --user flathub dev.zed.Zed
    zed_cmd="flatpak run dev.zed.Zed"
  fi
  if ! command -v zed >/dev/null 2>&1 && flatpak info dev.zed.Zed >/dev/null 2>&1; then
    cat > "$HOME/.local/bin/zed" << 'EOF'
#!/usr/bin/env bash
exec flatpak run dev.zed.Zed "$@"
EOF
    chmod +x "$HOME/.local/bin/zed"
  fi
  ok "Zed prêt ($zed_cmd)."
}

setup_python_venv() {
  log "Préparation de l'environnement Python (.venv)..."
  if [ ! -d "$ROOT_DIR/.venv" ]; then
    python3 -m venv "$ROOT_DIR/.venv"
  fi
  "$ROOT_DIR/.venv/bin/python" -m pip install --upgrade pip >/dev/null 2>&1 || true
  "$ROOT_DIR/.venv/bin/pip" install -q pytest ruff >/dev/null 2>&1 || warn "Installation offline : pytest/ruff non téléchargés."
  ok "Environnement Python prêt."
}

configure_env_assistant() {
  if [ -f "$ENV_FILE" ] && ! $AUTO_YES; then
    local regen
    regen=$(ask_default "Un fichier .env existe déjà. Le conserver ? (o/n)" "o")
    if [[ "$regen" =~ ^[oOyY] ]]; then
      ok "Configuration .env existante conservée."
      return 0
    fi
  elif [ -f "$ENV_FILE" ] && $AUTO_YES; then
    ok "Configuration .env existante conservée."
    return 0
  fi

  log "Assistant de configuration (.env modifiable à tout moment) :"
  local def_proj="$HOME/Documents/mon-projet-ia"
  local proj_dir choice duration stack ram_mb threads model_name hf_repo hf_quant gguf_name model_path
  local provider="llama_cpp" base_url="http://127.0.0.1:18080/v1" auto_srv="true"

  proj_dir=$(ask_default "1/4 Dossier du projet cible (où l'IA crée fichiers/dossiers)" "$def_proj")
  proj_dir="${proj_dir/#\~/$HOME}"

  if $AUTO_YES; then
    choice="1"
  else
    echo "2/4 Modèle IA local :"
    echo "    1) Qwen3.5-0.8B (Q4_K_M, ~550 Mo — Recommandé budget <= 1 Go RAM)"
    echo "    2) Qwen2.5-Coder-1.5B (Q4_K_M, ~1.1 Go — Si >= 2 Go RAM disponibles)"
    echo "    3) Autre modèle / API OpenAI-compatible (Ollama ou endpoint distant)"
    choice=$(ask_default "Votre choix (1/2/3)" "1")
  fi

  case "$choice" in
    2)
      model_name="qwen2.5-coder-1.5b-q4_k_m"
      hf_repo="Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF"
      hf_quant="Q4_K_M"
      gguf_name="qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"
      ram_mb="1792"
      ;;
    3)
      provider=$(ask_default "    Provider (llama_cpp / ollama / openai_compat)" "openai_compat")
      base_url=$(ask_default "    URL base (/v1)" "http://127.0.0.1:11434/v1")
      model_name=$(ask_default "    Identifiant modèle" "qwen3.5:0.8b")
      hf_repo=""
      hf_quant="Q4_K_M"
      gguf_name=""
      ram_mb=$(ask_default "    Plafond RAM (Mo)" "1024")
      [ "$provider" != "llama_cpp" ] && auto_srv="false"
      ;;
    *)
      model_name="qwen3.5-0.8b-q4_k_m"
      hf_repo="bartowski/Qwen_Qwen3.5-0.8B-GGUF"
      hf_quant="Q4_K_M"
      gguf_name="Qwen_Qwen3.5-0.8B-Q4_K_M.gguf"
      ram_mb="1024"
      ;;
  esac

  duration=$(ask_default "3/4 Durée autonome cible (ex: 30m, 4h, 24h, 72h)" "24h")
  stack=$(ask_default "4/4 Stack technologique (auto, python, node_ts, rust, go, custom)" "auto")
  threads="$(detect_physical_threads)"
  model_path=""
  [ -n "$gguf_name" ] && model_path="$HOME/.local/share/structuredai/models/$gguf_name"

  cp "$ROOT_DIR/.env.example" "$ENV_FILE"
  python3 - "$ENV_FILE" "$proj_dir" "$duration" "$stack" "$model_name" "$hf_repo" "$hf_quant" "$model_path" "$ram_mb" "$threads" "$provider" "$base_url" "$auto_srv" << 'PYEOF'
import pathlib, sys
env_p, proj, dur, stk, mod, repo, quant, mpath, ram, thr, prov, burl, asrv = sys.argv[1:]
rss = str(max(256, int(int(ram) * 0.85)))
updates = {
    "TARGET_PROJECT_DIR": proj, "RUN_DURATION": dur, "TARGET_STACK": stk,
    "LLM_PROVIDER": prov, "LLM_BASE_URL": burl, "LLM_AUTO_START_SERVER": asrv,
    "LLM_MODEL": mod, "LLM_HF_REPO": repo, "LLM_HF_QUANT": quant,
    "LLM_MODEL_PATH": mpath, "RAM_LIMIT_MB": ram, "LLAMA_RSS_RESTART_MB": rss,
    "CPU_THREADS": thr,
}
lines = []
for ln in pathlib.Path(env_p).read_text(encoding="utf-8").splitlines():
    if "=" in ln and not ln.strip().startswith("#"):
        k = ln.split("=", 1)[0].strip()
        if k in updates:
            lines.append(f"{k}={updates[k]}")
            continue
    lines.append(ln)
pathlib.Path(env_p).write_text("\n".join(lines) + "\n", encoding="utf-8")
PYEOF
  ok ".env généré (CPU_THREADS=$threads, RAM_LIMIT_MB=$ram_mb, TARGET_PROJECT_DIR=$proj_dir)."
}

read_env_val() {
  python3 - "$ENV_FILE" "$1" "$2" << 'PYEOF'
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

sync_zed_and_project() {
  local proj_dir spec_rel
  proj_dir="$(read_env_val TARGET_PROJECT_DIR "$HOME/Documents/mon-projet-ia")"
  spec_rel="$(read_env_val INITIAL_SPEC_PATH "SPEC.md")"
  mkdir -p "$proj_dir/.zed" "$proj_dir/.orchestrator"
  if [ ! -f "$proj_dir/$spec_rel" ] && [[ "$spec_rel" != /* ]]; then
    cp "$ROOT_DIR/docs/templates/SPEC.template.md" "$proj_dir/$spec_rel"
    ok "SPEC.md modèle créé dans $proj_dir/$spec_rel"
  fi
  if [ ! -f "$proj_dir/.orchestrator/STEERING.md" ]; then
    PYTHONPATH="$ROOT_DIR" python3 - "$proj_dir/.orchestrator/STEERING.md" << 'PYEOF'
import pathlib, sys
from structuredai.steering import ensure_steering_file
ensure_steering_file(pathlib.Path(sys.argv[1]))
PYEOF
  fi
  python3 - "$ROOT_DIR/.zed/tasks.json" "$proj_dir/.zed/tasks.json" "$ROOT_DIR" "$ENV_FILE" << 'PYEOF'
import json, pathlib, sys
src, dst, root, env_f = map(pathlib.Path, sys.argv[1:])
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
  cp -f "$ROOT_DIR/.zed/settings.json" "$proj_dir/.zed/settings.json"
  PYTHONPATH="$ROOT_DIR" python3 -m structuredai.zed_config "$ROOT_DIR" "$ENV_FILE"

  if flatpak info dev.zed.Zed >/dev/null 2>&1; then
    flatpak override --user --filesystem="$ROOT_DIR" dev.zed.Zed
    flatpak override --user --filesystem="$proj_dir" dev.zed.Zed
    flatpak override --user --env=STRUCTUREDAI_LOCAL_API_KEY=local dev.zed.Zed
    ok "Permissions Flatpak Zed & assistant IA local configurés."
  fi
}

download_model_if_needed() {
  local provider auto_start mpath repo quant
  provider="$(read_env_val LLM_PROVIDER "llama_cpp")"
  auto_start="$(read_env_val LLM_AUTO_START_SERVER "true")"
  mpath="$(read_env_val LLM_MODEL_PATH "")"
  repo="$(read_env_val LLM_HF_REPO "bartowski/Qwen_Qwen3.5-0.8B-GGUF")"
  quant="$(read_env_val LLM_HF_QUANT "Q4_K_M")"

  if [ "$provider" != "llama_cpp" ] || [ "$auto_start" != "true" ] || [ -z "$mpath" ]; then
    return 0
  fi
  if [ -f "$mpath" ]; then
    ok "Modèle GGUF déjà présent : $mpath"
    return 0
  fi
  mkdir -p "$(dirname "$mpath")"
  log "Résolution du fichier GGUF ($quant) depuis Hugging Face ($repo)..."
  local dl_url
  dl_url=$(python3 - "$repo" "$quant" << 'PYEOF'
import json, sys, urllib.request
repo, quant = sys.argv[1], sys.argv[2].lower()
url = f"https://huggingface.co/api/models/{repo}"
try:
    with urllib.request.urlopen(url, timeout=20) as r:
        data = json.loads(r.read().decode("utf-8"))
    files = [s["rfilename"] for s in data.get("siblings", []) if s.get("rfilename", "").lower().endswith(".gguf")]
    matches = [f for f in files if quant in f.lower()]
    pick = matches[0] if matches else (files[0] if files else "")
    if pick:
        print(f"https://huggingface.co/{repo}/resolve/main/{pick}")
except Exception as exc:
    print(f"ERROR:{exc}", file=sys.stderr)
PYEOF
  ) || true
  if [ -z "$dl_url" ]; then
    warn "Impossible de résoudre automatiquement le GGUF sur $repo. Téléchargez-le manuellement vers $mpath."
    return 0
  fi
  log "Téléchargement : $dl_url -> $mpath"
  if curl -fL -C - --retry 3 --retry-delay 2 --progress-bar -o "$mpath.part" "$dl_url"; then
    local fsize
    fsize=$(stat -c%s "$mpath.part" 2>/dev/null || echo 0)
    if [ "$fsize" -ge 10485760 ]; then
      mv "$mpath.part" "$mpath"
      ok "Modèle téléchargé avec succès : $mpath ($(($fsize / 1048576)) Mo)"
    else
      rm -f "$mpath.part"
      warn "Fichier téléchargé trop petit (<10 Mo) ; téléchargement annulé."
    fi
  else
    warn "Échec du téléchargement depuis $dl_url. Relancez ./install.sh plus tard."
  fi
}

launch_zed_workspace() {
  $NO_LAUNCH && return 0
  local proj_dir zed_open zed_cmd
  proj_dir="$(read_env_val TARGET_PROJECT_DIR "$HOME/Documents/mon-projet-ia")"
  zed_open="$(read_env_val ZED_AUTO_OPEN "true")"
  [ "$zed_open" != "true" ] && return 0
  zed_cmd="$(find_zed_cmd)"
  if [ -n "$zed_cmd" ]; then
    log "Ouverture de Zed sur $proj_dir (avec SPEC.md et .env)..."
    export STRUCTUREDAI_LOCAL_API_KEY="local"
    if [ "$zed_cmd" = "flatpak run dev.zed.Zed" ]; then
      nohup flatpak run dev.zed.Zed "$proj_dir" "$proj_dir/SPEC.md" "$ENV_FILE" >/dev/null 2>&1 &
    else
      nohup "$zed_cmd" "$proj_dir" "$proj_dir/SPEC.md" "$ENV_FILE" >/dev/null 2>&1 &
    fi
    ok "Zed lancé ! L'assistant IA local ($proj_dir) est configuré par défaut."
  fi
}

main() {
  detect_fedora
  ensure_local_bin_path
  install_fedora_deps
  install_and_connect_zed
  setup_python_venv
  configure_env_assistant
  sync_zed_and_project
  download_model_if_needed
  "$ROOT_DIR/start.sh" doctor || warn "Vérifiez votre .env avant le lancement."
  launch_zed_workspace
  ok "Installation terminée !"
}

main
