# 10 — Cockpit Zed, Installation Fedora (`install.sh`) & Pilotage (`start.sh`)

Ce guide décrit l'expérience utilisateur complète sous **Fedora** (et dérivés comme Ultramarine Linux) avec **Zed** comme cockpit de supervision et de pilotage en temps réel, sans besoin d'Alpaca.

---

## 1. Installation en Une Commande (`./install.sh`)

À la racine du dépôt, lancez simplement sans option :
```bash
./install.sh
```

Le script s'adapte dynamiquement à l'utilisateur courant (`$USER`, `$HOME`, CPU, RAM) sur tout système Fedora :
1. **Dépendances système (`dnf`)** : installe uniquement les paquets manquants (`git`, `python3`, `python3-pip`, `curl`, `flatpak`, `util-linux`, `systemd`, et `llama-cpp` depuis les dépôts Fedora si disponible ; sinon compile `llama-server` dans `~/.local/share/structuredai/llama.cpp`).
2. **Zed Editor (`dev.zed.Zed`)** : détecte Zed (natif ou Flatpak), l'installe via Flathub s'il est absent, crée un alias `~/.local/bin/zed`, et accorde les droits Flatpak sur `structuredAI` et `TARGET_PROJECT_DIR`.
3. **Environnement Python `.venv`** : crée `.venv` et installe les outils de vérification (`pytest`, `ruff`).
4. **Assistant `.env` interactif** : génère `.env` avec des valeurs intelligentes par défaut (modifiables à tout moment) : dossier projet cible, modèle IA léger (`Qwen3.5-0.8B-Q4_K_M`), durée (`24h`), plafond RAM (`1024 Mo`) et threads P-cores.
5. **Téléchargement GGUF** : résout et télécharge le modèle configuré depuis `LLM_HF_REPO` / `LLM_HF_QUANT` si absent localement.
6. **Ouverture dans Zed** : synchronise `.zed/tasks.json` et ouvre le workspace dans Zed pour vous donner immédiatement la main.

---

## 2. Visualiser & Influencer l'Agent Depuis Zed

Une fois dans Zed (dans `structuredAI` ou directement dans `TARGET_PROJECT_DIR`) :

### 2.1 Visualisation en Direct
* **Tableau de bord** : ouvrez `.orchestrator/DASHBOARD.md` puis activez l'aperçu Markdown côte à côte (`Ctrl+Shift+V` ou `Markdown: Open Preview to the Side`). Zed recharge automatiquement le fichier à chaque mise à jour.
* **Activité Git** : ouvrez le panneau Git de Zed pour inspecter les micro-commits atomiques sur la branche `ai-auto`.
* **Erreurs éventuelles** : consultez `.orchestrator/ERRORS.md` si un nœud passe en `FAILED_MANUAL_REVIEW`.

### 2.2 Influencer l'Exécution en Direct (`.orchestrator/STEERING.md`)
L'orchestrateur lit `.orchestrator/STEERING.md` au début de chaque itération, sans interrompre ni corrompre l'état courant. Vous pouvez soit l'éditer directement dans Zed, soit utiliser les **Tâches Zed** (`Alt+Shift+T` ou `task: spawn`) :

| Directive dans `STEERING.md` | Effet immédiat au cycle suivant |
| :--- | :--- |
| `STATUS: PAUSE` | Met l'agent en pause propre après le nœud courant (libère le CPU). |
| `STATUS: RUN` | Reprend l'exécution immédiatement. |
| `STATUS: STOP` | Déclenche une clôture propre vers `FROZEN` + `RUN_REPORT.md`. |
| `PRIORITY: src/api/routes.py` | Place ce fichier en tête de la file prioritaire. |
| `RETRY: src/core/parser.py` | Réactive un nœud `FAILED_MANUAL_REVIEW` (ex. après correction manuelle dans Zed). |
| `SKIP: src/legacy/old.py` | Exclut ce nœud du cycle autonome. |
| `NOTE [src/core/parser.py]: Utilise datetime.fromisoformat` | Injecte votre consigne humaine dans le prochain contexte du nœud, puis s'archive automatiquement. |

---

## 3. Commandes du Lanceur Unifié (`./start.sh`)

Toutes ces actions sont aussi accessibles directement depuis les tâches `.zed/tasks.json` dans Zed :

```bash
./start.sh                 # Valide .env, encapsule RAM (systemd-run), lance/reprend la boucle
./start.sh doctor          # Diagnostic complet (RAM, disque, llama-server, Git, Zed, .env)
./start.sh status          # Affiche le DASHBOARD.md et l'état du processus
./start.sh pause           # Met la boucle en pause propre via STEERING.md
./start.sh resume          # Relance après pause
./start.sh priority <path> # Priorise un module cible
./start.sh retry <path>    # Réinitialise un nœud FAILED_MANUAL_REVIEW
./start.sh stop            # Arrêt propre avec sauvegarde state.json
```
