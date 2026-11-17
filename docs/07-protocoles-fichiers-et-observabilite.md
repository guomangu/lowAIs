# 07 — Protocoles des Artefacts Internes, Télémétrie & Exploitation Humaine

Pendant une exécution autonome de plusieurs heures (jusqu'à 24h), les fichiers sur disque constituent **la seule mémoire** du système (Invariant I2 : Zéro mémoire conversationnelle) et **l'unique interface de supervision** pour l'utilisateur humain.

---

## 1. Mode `shadow` vs Mode `inline` (`METADATA_STORAGE`)

Pour s'adapter proprement à tout dépôt réel (ex. Next.js, Rust Cargo, Go, Python), StructuredAI sépare la **mémoire de travail de l'IA** du **code source métier** :

| Mode | Organisation dans `TARGET_PROJECT_DIR` | Avantages | Cas d'usage |
| :--- | :--- | :--- | :--- |
| **`shadow`** *(défaut)* | Tous les artefacts (`state.json`, `CONTRACT.md`, `REALITY.md`, `REFACTOR_ORDERS.md`, `DASHBOARD.md`) vivent dans `.orchestrator/` (exclu via `.git/info/exclude`). | Zéro pollution des dossiers sources ; aucun risque de casser un bundler/router Next.js ou Go embed. | Projets *Brownfield* et projets *Greenfield* destinés à la production. |
| **`inline`** | `CONTRACT.md` et `REALITY.md` sont écrits directement dans chaque sous-dossier métier ; `state.json` et logs restent dans `.orchestrator/`. | Navigation humaine directe dans les dossiers de code avec documentation locale accolée. | Projets éducatifs, prototypage rapide, audit dossier par dossier. |

### Arborescence standard en mode `shadow`
```text
<TARGET_PROJECT_DIR>/
├── SPEC.md                          # Graine humaine initiale
├── src/                             # Code pur généré par les agents
├── tests/                           # Tests unitaires et d'intégration
└── .orchestrator/                   # Espace interne (auto-exclu si souhaité)
    ├── state.json                   # État courant (écriture atomique)
    ├── orchestrator.lock            # Verrou exclusif flock anti-double lancement
    ├── DEPS_REALITY.md              # Cache AST/signatures des bibliothèques tierces installées
    ├── events.jsonl                 # Journal WAL append-only (rotation auto à 50 Mo)
    ├── DASHBOARD.md                 # Tableau de bord temps réel (auto-rafraîchi)
    ├── ERRORS.md                    # Registre des nœuds FAILED_MANUAL_REVIEW
    ├── RUN_REPORT.md                # Bilan final généré en phase FROZEN (H4)
    └── tree/                        # Miroir structurel de l'arborescence cible
        └── src/core/
            ├── CONTRACT.md
            ├── REALITY.md
            └── REFACTOR_ORDERS.md
```

---

## 2. Spécification des Artefacts Dialectiques

### 2.1 `SPEC.md` (Graine Humaine)
C'est le point de départ fourni par l'utilisateur. Un `SPEC.md` optimisé pour un modèle léger doit être **concis (`<= 800 tokens`)**, structuré par exigences testables, sans prose superflue (voir le modèle dans [docs/templates/SPEC.template.md](templates/SPEC.template.md)).

### 2.2 `CONTRACT.md` (Contrat Local — Descente `0_ARCHITECT`)
Strictement borné à `<= 25` lignes pour laisser la place au code dans les `4096` tokens :
```markdown
# CONTRACT: src/core/parser.py
- **Priorité**: 12 | **Dépendances**: `src/core/types.py`
- **Responsabilité**: Parser une durée texte ("24h", "30m", "86400s") en secondes entières.
- **Exports requis**:
  - `parse_duration(raw: str) -> int` (lève `DurationError` si <= 0 ou format invalide)
- **Contraintes**: Aucune dépendance externe ; max 100 lignes.
```

### 2.3 `REALITY.md` (Vérité Terrain Hybride AST + LLM — Montée `2_EXTRACT`)
Strictement borné à `<= 15` lignes par fichier (ou `<= 20` lignes par index de dossier) :
```markdown
# REALITY: src/core/parser.py (68 lignes)
## [AST_SIGNATURES] (Source déterministe)
- `imports`: `re`, `src.core.types.DurationError`
- `def parse_duration(raw: str) -> int`
- `def _extract_unit(token: str) -> tuple[int, str]`
## [SEMANTIC_PURPOSE] (LLM <= 2 phrases)
Convertit les chaînes de durée (`s`, `m`, `h`, `d`) en entier positif avec validation stricte.
```

### 2.4 `REFACTOR_ORDERS.md` (Antithèse `3_CRITIQUE`)
Liste numérotée d'actions atomiques ciblées (max 6 ordres par cycle) :
```markdown
# REFACTOR_ORDERS (Cycle 1/2)
1. [FIX_INTERFACE] `src/cli/main.py`: appelle `parse_time()` inexistant ; remplacer par `parse_duration()` de `src/core/parser.py`.
2. [SPLIT_FILE] `src/core/engine.py` (94 lignes): proche du seuil 100L ; extraire les helpers de validation dans `src/core/validators.py`.
```

### 2.5 `ERRORS.md` (Registre Circuit Breaker)
Lorsqu'un nœud échoue après `MAX_RETRIES_PER_NODE=5` tentatives :
```markdown
## [FAILED_MANUAL_REVIEW] src/adapters/net_client.py
- **Horodatage**: 2026-11-18T03:14:22Z | **Temps consommé**: 212s | **Essais**: 5/5
- **Dernier état**: `5_SYNTHESIS` | **Cause distillée**: `TimeoutError in test_retry_backoff (line 34)`
- **Action Git**: Restauré vers commit sain `8f12d0a`.
```

---

## 3. Télémétrie Temps Réel & Pilotage Humain

### 3.1 Tableau de Bord Live (`.orchestrator/DASHBOARD.md`)
Régénéré toutes les `DASHBOARD_REFRESH_CYCLES=5` transitions (et consultable à tout moment sans interrompre la boucle) :

```markdown
# StructuredAI — Live Dashboard (`run_20261117_194000`)
- **Horizon Actif** : `H2_ALIGN_SYNTH` | **Temps Actif** : `38h 42m / 72h 00m` (53.8%)
- **Modèle IA** : `qwen3.5-0.8b-q4_k_m` (`llama_cpp`) | **Débit moyen** : `68.4 tok/s`
- **Ressources** : `812 Mo / 1024 Mo` RAM | Disque libre : `42.6 Go` | CPU Temp : `69°C` | Restarts : `2`
- **Progression Nœuds** : `18` LOCKED | `2` NEEDS_REVERIFY | `3` EN COURS | `1` FAILED_MANUAL_REVIEW
- **Couverture Exigences (`SPEC.md`)** : `11 / 12 REQ-*` implémentées & testées
- **Dernier Tag Vert** : `green-step-004` (il y a 18 min — Suite + Smoke Test PASS : 42/42)
```

### 3.2 Journal Événementiel Structuré (`.orchestrator/events.jsonl`)
Chaque ligne JSON enregistre les métriques permettant d'auditer ou de tracer des courbes post-exécution (avec rotation et compression gzip automatique à `MAX_EVENTS_LOG_MB=50`) :
* `ts`, `node`, `from_state`, `to_state`, `horizon`, `duration_ms`
* `prompt_tokens`, `completion_tokens`, `tok_per_sec`
* `ram_rss_mb`, `disk_free_mb`, `cpu_temp_c`, `error_hash`, `git_sha`

### 3.3 Rapport Final de Clôture (`.orchestrator/RUN_REPORT.md`)
Produit automatiquement lors de l'entrée en phase finale `FROZEN` (`95% – 100%` du temps ou sortie d'inactivité `7_HARDENING`) :
1. **Résumé Exécutif** : état final (tag Git livré, statut suite globale + smoke test, temps actif réel).
2. **Matrice de Couverture `SPEC.md`** : statut de chaque `REQ-*` (implémenté, testé, bloqué ou manquant).
3. **Inventaire des Modules** : liste des modules `6_LOCKED`, `BLOCKED_BY_UPSTREAM` et `FAILED_MANUAL_REVIEW`.
4. **Santé & Performance Multi-Jours** : pic RAM, espace disque restant, nombre de redémarrages Watchdog, pauses thermiques, cascades *Ripple* gérées, tentatives de stagnation/dégénérescence bloquées.
5. **Actions Humaines Recommandées** : résumé ciblé de `ERRORS.md` et commande `git diff main..ai-auto` prête à l'inspection.
