# 08 — Plan d'Implémentation du Framework & Protocole de Vérification

Ce document définit le plan de construction du framework **StructuredAI** lui-même. Par cohérence dogfooding avec le document fondateur, **chaque module Python du framework doit respecter strictement `<= 100 lignes`**.

---

## 1. Arborescence Modulaire Cible (`<= 100 lignes` par fichier)

```text
structuredAI/
├── .env.example
├── install.sh                             # Installeur unique Fedora (dépendances, llama-server, Zed, .env)
├── start.sh                               # Lanceur & CLI pilotage (start/doctor/status/pause/retry/stop)
├── README.md
├── .zed/
│   ├── tasks.json                         # Tâches Zed liées au framework & $ZED_FILE
│   └── settings.json                      # Configuration cockpit Zed
├── docs/                                  # Documentation complète (01 -> 10 + templates)
├── structuredai/                          # Code du framework (chaque .py <= 100 lignes)
│   ├── __init__.py
│   ├── config.py                          # Chargement .env + validation Fail-Fast + calcul budget RAM
│   ├── time_budget.py                     # TimeBudgetManager (horloge active, 5 horizons, dégradation)
│   ├── llm_client.py                      # Client HTTP stateless + contrôle débit/JSON/GBNF
│   ├── gbnf_schemas.py                    # Grammaires GBNF + JSON Schemas des 6 micro-agents
│   ├── prompts.py                         # Prompts ultra-compacts (<150 tok) + balises anti-injection
│   ├── stack_detector.py                  # Détection auto stack + mode greenfield/brownfield
│   ├── stack_adapter.py                   # Exécution des 6 hooks sandboxés + stack.toml + DEPS_REALITY
│   ├── ast_reality.py                     # Extraction AST/Tree-sitter + fenêtrage legacy + REALITY.md
│   ├── graph_ops.py                       # Tri topologique, CycleDetector DAG, Ripple NEEDS_REVERIFY
│   ├── validators.py                      # wc -l <= 100, ImportPreflight, AntiTrivial & Monotonicity
│   ├── security_gate.py                   # PathJail, PROTECTED_PATHS, DangerousCallScanner, env strip
│   ├── error_distiller.py                 # Compression erreurs <= 180 tok + Stagnation & Degeneration
│   ├── git_tx.py                          # Branche ai-auto, staging sélectif, tags green-step-NNN
│   ├── watchdog.py                        # Verrou flock, RSS (1Go), disque, rotation logs, thermique
│   ├── steering.py                        # Pilotage live depuis Zed via STEERING.md
│   ├── state_machine.py                   # Transitions state.json atomiques + WAL events.jsonl
│   ├── telemetry.py                       # Génération DASHBOARD.md, ERRORS.md, RUN_REPORT.md
│   └── main.py                            # Boucle principale multi-jours + CLI start/doctor/status
└── tests/                                 # Tests unitaires et Chaos Testing du framework
```

---

## 2. Ordre d'Implémentation Recommandé (4 Jalons)

| Jalon | Modules livrés | Critère de validation du jalon |
| :--- | :--- | :--- |
| **M1 — Noyau Config, Temps & LLM** | `config.py`, `time_budget.py`, `llm_client.py`, `gbnf_schemas.py`, `watchdog.py` | Validation `.env`, verrou `flock`, `llama-server` `< 900 Mo` sur port `18080`, détection débit `< 5 tok/s`. |
| **M2 — Stack, Graphe & Sécurité** | `stack_detector.py`, `stack_adapter.py`, `ast_reality.py`, `graph_ops.py`, `validators.py`, `security_gate.py`, `error_distiller.py` | Extraction AST + `DEPS_REALITY`, blocage cycles DAG, anti-triche tests, `PathJail`/`PROTECTED_PATHS`. |
| **M3 — Machine à États, Git & Pilotage Zed** | `prompts.py`, `git_tx.py`, `steering.py`, `state_machine.py`, `telemetry.py`, `main.py` | Cycle complet `0_INGEST` -> `6_LOCKED` -> `NEEDS_REVERIFY` -> `FROZEN` pilotable via `.zed/tasks.json` et `STEERING.md`. |
| **M4 — Installeur Fedora, Lanceur & Chaos Testing** | `install.sh`, `start.sh`, `.zed/`, `tests/` | `./install.sh` + `./start.sh doctor` + les **12 tests de chaos** passent sans fuite RAM/disque ni corruption Git. |

---

## 3. Protocole de *Chaos Testing* (Obligatoire avant un Run Multi-Jours)

Avant de confier un projet de 24h à plusieurs jours à une IA locale légère, le framework doit survivre à **12 scénarios de panne simulée** :

1. **Chaos 1 — Hallucination JSON / `<think>` sauvage** : rejet propre, nettoyage et retry sans crash.
2. **Chaos 2 — Oscillation Ping-Pong (`A -> B -> A`)** : détection via `history_hashes` (`K=5`), escalade puis Circuit Breaker.
3. **Chaos 3 — Mort subite ou dégradation de `llama-server`** : `SIGKILL` ou débit `< 5 tok/s` -> relance automatique par `watchdog.py`.
4. **Chaos 4 — Boucle infinie en test (`while True: pass`)** : `SUBPROCESS_TIMEOUT_SEC` tue tout le groupe (`killpg`) sans zombie.
5. **Chaos 5 — Test factice / sur-mocking (`assert True`)** : blocage par `AntiTrivialTestGate`.
6. **Chaos 6 — Coupure & Reprise (`--resume`)** : `SIGINT` à 50 % puis reprise exacte avec horloge `active` immunisée contre un saut NTP simulé.
7. **Chaos 7 — Cycle de dépendances DAG (`A -> B -> A`)** : rejet immédiat en `0_ARCHITECT` / `ImportPreflightChecker`.
8. **Chaos 8 — *Reward Hacking* (vidage de code / suppression d'assertions)** : blocage par `DegenerationGuard` et `TestMonotonicityGate`.
9. **Chaos 9 — Réécriture de `SPEC.md` ou fuite `.env`** : blocage par `PROTECTED_PATHS` + staging Git sélectif.
10. **Chaos 10 — Saturation disque (`DISK_MIN_FREE_MB`) & log géant** : rotation gzip de `events.jsonl`, purge des tags `> 20` et caches.
11. **Chaos 11 — Rupture de signature amont (*Ripple*)** : modification d'un module verrouillé -> bascule automatique des dépendants en `NEEDS_REVERIFY`.
12. **Chaos 12 — Collision de port `8080` & double lancement** : port IA isolé en `18080` + rejet immédiat d'une 2e instance par `flock`.

---

## 4. Checklist Pré-Vol Avant un Run Autonome Multi-Jours

Avant de lancer une session de 24h à 7 jours :
- [ ] **Alimentation secteur & anti-veille** (`systemd-inhibit --what=sleep:idle`) actifs.
- [ ] **Espace disque libre** vérifié (`>= 5 Go` libres recommandés pour caches + builds).
- [ ] **Validation `.env`** : `TARGET_PROJECT_DIR`, `RUN_DURATION`, `TIME_ACCOUNTING_MODE=active`, `RAM_LIMIT_MB=1024`, port IA `18080`.
- [ ] **Dry-Run de 15 minutes (`RUN_DURATION=15m`)** validant `tok/s`, RSS `< 900 Mo`, température `< 80°C` et exécution des tests.
- [ ] **État Git initial propre** sur la branche humaine avant création de `ai-auto`.
- [ ] **`SPEC.md` structuré avec `REQ-01..N`** testables (voir [docs/templates/SPEC.template.md](templates/SPEC.template.md)).
