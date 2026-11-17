# 02 — Configuration `.env`, Choix de l'IA & Gestion Matérielle (`<= 1 Go RAM`)

La flexibilité de **StructuredAI** repose sur un principe simple : **zéro paramètre critique codé en dur**. Le fichier `.env` pilote l'IA utilisée, la durée de la mission, le dossier cible, la stack et les seuils matériels. Au démarrage, l'orchestrateur applique une validation **Fail-Fast** : si un chemin est invalide, si le budget RAM calculé dépasse `RAM_LIMIT_MB` ou si le serveur IA ne répond pas, l'exécution s'arrête immédiatement avec un diagnostic clair avant de gaspiller du temps.

---

## 1. Référence Complète des Variables `.env`

### 1.1 Cible, Mode & Stockage
| Variable | Type / Valeurs | Défaut | Rôle |
| :--- | :--- | :--- | :--- |
| `TARGET_PROJECT_DIR` | Chemin absolu | *(Requis)* | Dossier racine où l'agent crée/modifie le projet cible. Verrouillé par `PathJail`. |
| `PROJECT_MODE` | `auto` \| `greenfield` \| `brownfield` | `auto` | `auto` choisit `greenfield` si le dossier ne contient que `SPEC.md`/`.git`, sinon `brownfield`. |
| `INITIAL_SPEC_PATH` | Chemin (relatif ou absolu) | `SPEC.md` | Spécification initiale décrivant le logiciel à produire ou faire évoluer. |
| `METADATA_STORAGE` | `shadow` \| `inline` | `shadow` | `shadow` isole `CONTRACT.md`/`REALITY.md` dans `.orchestrator/tree/` pour garder le code propre. |
| `ORCHESTRATOR_STATE_DIR` | Nom de dossier | `.orchestrator` | Dossier interne hébergeant `state.json`, `events.jsonl`, `DASHBOARD.md`, `RUN_REPORT.md`. |

### 1.2 Moteur Temporel
| Variable | Type / Valeurs | Défaut | Rôle |
| :--- | :--- | :--- | :--- |
| `RUN_DURATION` | Durée (`30m`, `4h`, `24h`, `86400s`) | `24h` | Budget temps total de la session autonome. |
| `TIME_PROFILE` | `balanced` \| `sprint` \| `hardening` | `balanced` | Pondération des 5 horizons temporels (voir [doc 03](03-moteur-temporel-et-cycle-dialectique.md)). |
| `FREEZE_WINDOW_RATIO` | Flottant (`0.02`–`0.20`) | `0.05` | Pourcentage final réservé au gel, audit et stabilisation sans refactorisation risquée. |
| `NODE_TIME_CAP_RATIO` | Flottant (`0.05`–`0.25`) | `0.10` | Part maximale du temps total qu'un seul nœud peut consommer avant bascule. |
| `HEARTBEAT_INTERVAL_SEC` | Entier (s) | `30` | Intervalle de vérification mémoire/thermique et rafraîchissement des métriques. |
| `RESUME_MODE` | `auto` \| `fresh` \| `strict` | `auto` | `auto` reprend `state.json` existant avec le temps restant ; `fresh` repart à zéro. |

### 1.3 Choix de l'IA & Inférence
| Variable | Type / Valeurs | Défaut | Rôle |
| :--- | :--- | :--- | :--- |
| `LLM_PROVIDER` | `llama_cpp` \| `ollama` \| `openai_compat` | `llama_cpp` | Adaptateur HTTP utilisé par `llm_client.py`. |
| `LLM_BASE_URL` | URL | `http://127.0.0.1:18080/v1` | Endpoint `/v1/chat/completions` (port dédié `18080` pour éviter toute collision avec les apps web en `8080`). |
| `LLM_API_KEY` | Chaîne | *(vide)* | Jeton Bearer si `openai_compat` distant ou sécurisé (strippé des sous-processus de tests). |
| `LLM_MODEL` | Chaîne | `qwen3.5-0.8b-q4_k_m` | Nom du modèle envoyé dans le payload JSON. |
| `LLM_MODEL_PATH` | Chemin `.gguf` | *(optionnel)* | Chemin du modèle local si `LLM_AUTO_START_SERVER=true`. |
| `LLM_AUTO_START_SERVER` | Booléen | `true` | Lance et supervise automatiquement `llama-server` en sous-processus. |
| `LLM_CTX_SIZE` | Entier (`2048`–`32768`) | `4096` | Taille de fenêtre de contexte stricte. |
| `LLM_MAX_OUTPUT_TOKENS` | Entier | `1024` | Borne stricte de génération par appel (évite les boucles de tokens infinis). |
| `LLM_TEMPERATURE` | Flottant (`0.0`–`1.0`) | `0.2` | Basse température pour maximiser le déterminisme structurel. |
| `LLM_DISABLE_THINKING` | Booléen | `true` | Force la suppression des blocs `<think>...</think>` sur les modèles hybrides. |
| `LLM_STRUCTURED_MODE` | `gbnf` \| `json_schema` \| `json_object` \| `delimited` | `gbnf` | Mécanisme de contrainte de format adapté au backend choisi. |
| `LLM_CRITIQUE_MODEL` | Chaîne | *(vide)* | Optionnel : modèle plus capable réservé uniquement à `3_CRITIQUE` (routage dual). |
| `LLM_TIMEOUT_SEC` | Entier (s) | `90` | Timeout par requête HTTP (connexion + lecture stream/body). |
| `MIN_LLM_TOKENS_PER_SEC` | Flottant | `5.0` | Seuil de débit minimal : en dessous sur 2 appels consécutifs, le Watchdog redémarre le serveur IA. |

### 1.4 Contraintes Matérielles, Stack, Git & Sécurité
Toutes les variables `RAM_LIMIT_MB`, `LLAMA_RSS_RESTART_MB`, `LLAMA_KV_CACHE_TYPE`, `CPU_THREADS`, `SUBPROCESS_TIMEOUT_SEC`, `THERMAL_PAUSE_C`, `COOLDOWN_MS`, `TARGET_STACK`, `MAX_LINES_PER_FILE`, `MAX_RETRIES_PER_NODE`, `GIT_*`, etc. sont pré-documentées dans [`.env.example`](../.env.example).

---

## 2. Profils de Modèles IA & Matrice de Compatibilité

Le choix dans `.env` permet d'ajuster instantanément le compromis vitesse / mémoire / capacité selon le matériel disponible :

| Profil | Modèle recommandé | Backend (`LLM_PROVIDER`) | Mode Structuré (`LLM_STRUCTURED_MODE`) | Empreinte RAM totale estimée | Cas d'usage idéal |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Ultra-Strict `<= 1 Go`** | `Qwen3.5-0.8B` (`Q4_K_M`) | `llama_cpp` | `gbnf` | **~720 – 850 Mo** | Laptop contraint à 1 Go RAM, autonomie 24h haute vitesse (~60–80 tok/s CPU). |
| **Micro-Edge `< 600 Mo`** | `SmolLM2-360M-Instruct` (`Q4_K_M`) | `llama_cpp` | `gbnf` | **~450 – 550 Mo** | Machines embarquées / conteneurs 512–600 Mo ; tâches simples et scripts compacts. |
| **Confort `1.5 Go`** | `Gemma-3-1B` ou `Llama-3.2-1B` (`Q4_K_M`) | `llama_cpp` / `ollama` | `gbnf` / `json_schema` | **~950 – 1 150 Mo** | Projets multi-langages quand `RAM_LIMIT_MB` peut monter à `1280`–`1536 Mo`. |
| **Codeur Léger `2 Go`** | `Qwen2.5-Coder-1.5B` (`Q4_K_M`) | `llama_cpp` / `ollama` | `gbnf` / `json_schema` | **~1 400 – 1 700 Mo** | Codebases complexes si 2 Go de RAM sont disponibles. |
| **Hybride / API** | Local `0.8B` + `LLM_CRITIQUE_MODEL` API | `llama_cpp` + `openai_compat` | `gbnf` + `json_schema` | **~850 Mo local** | Garder 95% des appels en local `0.8B` et déléguer la Passe 2 (`3_CRITIQUE`) si autorisé. |

---

## 3. Calculateur Déterministe de Budget RAM (`<= 1024 Mo`)

Avant de lancer `llama-server`, l'orchestrateur calcule le budget mémoire théorique :

$$\text{RAM}_{\text{totale}} = \text{Poids}_{\text{GGUF}} + \text{KV}_{\text{cache}} + \text{Overhead}_{\text{llama}} + \text{Orchestrateur}_{\text{Python}} + \text{Marge}_{\text{Subprocess}}$$

### Exemple réel : `Qwen3.5-0.8B-Q4_K_M` sur Fedora 44 (`RAM_LIMIT_MB=1024`)
| Composant | Configuration | Mémoire estimée |
| :--- | :--- | :--- |
| Poids du modèle (`Q4_K_M`) | `mlock` désactivé (chargement mmap contrôlé) | ~550 Mo |
| Cache KV (`n_ctx=4096`) | `-ctk q8_0 -ctv q8_0` (2× moins lourd que `f16`) | ~60–90 Mo |
| Runtime `llama-server` | `--parallel 1` (une seule requête simultanée) | ~80 Mo |
| Orchestrateur Python pur | Sans pandas/torch/frameworks agents | ~35–50 Mo |
| Exécution temporaire `pytest`/`ruff`/`tsc` | Un sous-processus à la fois (`SUBPROCESS_TIMEOUT_SEC=45`) | ~100–150 Mo |
| **Total pic mesuré** | **Sous plafond 1 Go** | **~825 – 920 Mo** |

> [!IMPORTANT]
> **Règle d'or `--parallel 1`** : `llama-server` doit impérativement être démarré avec `-np 1` (1 seul slot parallèle) et `-c 4096`. Sans `-np 1`, `llama-server` peut pré-allouer plusieurs slots KV et dépasser 1 Go dès le démarrage !

### Paramètres recommandés pour `llama-server`
```bash
llama-server \
  -m "$LLM_MODEL_PATH" \
  --host 127.0.0.1 --port 18080 \
  -c "$LLM_CTX_SIZE" \
  -np 1 \
  -t "$CPU_THREADS" \
  -ctk "$LLAMA_KV_CACHE_TYPE" -ctv "$LLAMA_KV_CACHE_TYPE" \
  --no-warmup \
  --reasoning-budget 0
```
*(Note : le port `18080` évite toute collision avec des applications générées utilisant `8080`. Le drapeau exact de désactivation du reasoning dépend de la version de `llama.cpp`, doublé côté payload par `chat_template_kwargs: {"enable_thinking": false}` lorsque `LLM_DISABLE_THINKING=true`, et filtré côté parseur).*

---

## 4. Isolation Système, Watchdog Multi-Jours (RAM, Disque, Débit, Thermique)

Sur une exécution continue de **plusieurs jours** (24h à 7j+) sur ordinateur portable ou poste dédié, six défaillances système doivent être neutralisées automatiquement :

1. **Dérive RSS / Fragmentation mémoire** : si `RSS(llama-server) + RSS(orchestrator) > LLAMA_RSS_RESTART_MB` (ex. `880 Mo`), le Watchdog termine proprement `llama-server` entre deux transitions d'état, attend la libération RAM, et le relance automatiquement en `< 2 secondes`. L'état étant persisté dans `state.json`, aucune donnée n'est perdue.
2. **Dégradation silencieuse de débit / Hang réseau (`MIN_LLM_TOKENS_PER_SEC`)** : si `llama-server` répond avec une chaîne vide ou tombe sous `5 tok/s` pendant 2 requêtes consécutives (signe de swap ou contention), ou en cas de timeout lecture HTTP (`LLM_TIMEOUT_SEC`), le client incrémente un compteur ; à 3 anomalies consécutives, le Watchdog redémarre le serveur IA (ou applique un backoff exponentiel pour un endpoint distant).
3. **Hard Cap via `cgroups v2` (`systemd-run`)** : sous Linux/Fedora, le script lanceur encapsule le serveur IA dans un scope cgroup strict :
   ```bash
   systemd-run --user --scope -p MemoryMax=920M -p MemorySwapMax=0 ...
   ```
   Désactiver le swap (`MemorySwapMax=0`) garantit qu'un défaut mémoire échoue vite et déclenche le redémarrage par le Watchdog plutôt que de paralyser le SSD pendant des heures.
4. **Watchdog Disque & Inodes (`DISK_MIN_FREE_MB=2048`)** : sur plusieurs jours, les caches (`target/`, `node_modules/.cache`, `__pycache__`) et logs peuvent saturer le SSD (`ENOSPC`, corrompant même les écritures atomiques). À chaque heartbeat :
   * Vérification de l'espace libre (`shutil.disk_usage`) ; sous `2048 Mo`, nettoyage des caches temporaires de tests et exécution de `git gc --auto`.
   * Rotation & compression gzip automatique de `events.jsonl` dès `MAX_EVENTS_LOG_MB=50`.
   * Rétention glissante des tags Git (`MAX_GREEN_TAGS_KEEP=20`).
5. **Verrou d'Instance Unique (`flock`) & Port Libre** : au démarrage, l'orchestrateur pose un verrou noyau `fcntl.flock` exclusif sur `.orchestrator/orchestrator.lock` et vérifie la disponibilité du port LLM afin d'interdire tout double lancement concurrent sur le même projet.
6. **Chauffe CPU & Nettoyage des Secrets (`env`)** :
   * Épingler `CPU_THREADS` sur les `P-cores` limite la chauffe ; au-dessus de `THERMAL_PAUSE_C` (`85°C`), pause adaptative jusqu'à `< 75°C`, plus `COOLDOWN_MS=100` entre appels.
   * Avant d'exécuter tout code/test généré, `LLM_API_KEY` et les variables sensibles de l'hôte sont **strippés** du dictionnaire `env` du sous-processus.
