# 09 — Audit de Failles & Blindage Multi-Jours (`48h`–`7j+`)

Lorsqu'un agent autonome propulsé par un petit modèle (`< 1B` / `1 Go RAM`) travaille **plusieurs jours d'affilée sans supervision humaine**, les défaillances mineures deviennent des pannes systémiques : fuite lente d'espace disque, dérive sémantique, *reward hacking*, imports circulaires ou régressions silencieuses. Ce document recense les **failles critiques identifiées lors de l'audit** et les **règles déterministes de blindage** intégrées au framework.

---

## 1. Synthèse des Failles & Contre-Mesures (Matrice Red-Team)

| Catégorie | Faille / Carence identifiée | Scénario de casse sur plusieurs jours | Règle de blindage appliquée |
| :--- | :--- | :--- | :--- |
| **Graphe & Architecture** | **Explosion de micro-fichiers & cycles DAG** | La règle `<= 100L` force des splits en cascade -> `A <-> B`, profondeur infinie, appelants cassés. | `CycleDetector` (tri topologique), `MAX_TREE_DEPTH=4`, `MIN_SPLIT_FILE_LINES=15`, façade de ré-export + invalidation aval. |
| **Intégration & Régression** | **Effet "Tests unitaires verts, app cassée"** | Chaque module passe ses tests mockés individuellement tandis que l'interface inter-modules a divergé au jour 2. | **Invalidation *Ripple* (`NEEDS_REVERIFY`)** sur hash AST amont + **Suite Globale & Smoke Test** tous les `5` commits (`INTEGRATION_CHECK_INTERVAL`). |
| **Alignement & Qualité** | ***Reward Hacking* & Dégénérescence** | L'IA supprime des assertions gênantes, mocke sa propre cible ou vide une fonction en `return True` pour passer `5_SYNTHESIS`. | **`TestMonotonicityGate`**, **`DegenerationGuard`** (`>50%` chute LOC bloquée), anti-sur-mocking, matrice `REQ-*`. |
| **Alignement & Qualité** | **Oscillation Ping-Pong (`A -> B -> A`)** | L'IA alterne entre deux variantes cassées sans déclencher un comparateur naïf à 1 coup. | Historique glissant `history_hashes` (`K=5`) -> détection d'oscillation et escalade immédiate. |
| **Temps & Horloge** | **Saut d'horloge (Veille / NTP) & Boucle à vide** | Une mise en veille de 8h fait expirer `time.time()` ; ou `7_HARDENING` tourne à 100 % CPU pendant 48h sans progrès. | Comptabilisation **`active`** par ticks bornés (`TIME_ACCOUNTING_MODE=active`), déblocage amont (`BLOCKED_BY_UPSTREAM`), sortie propre après `MAX_IDLE_HARDENING_CYCLES=10`. |
| **Ressources Hôte** | **Saturation Disque / Tags / Logs (`ENOSPC`)** | Sur 5 jours, `events.jsonl`, `target/`, `__pycache__` et milliers de tags Git remplissent le SSD et corrompent `state.json`. | Watchdog disque (`DISK_MIN_FREE_MB=2048`), rotation gzip `events.jsonl` à `50 Mo`, rétention `MAX_GREEN_TAGS_KEEP=20` + `git gc --auto`. |
| **Inférence IA** | **Dégradation silencieuse de débit / Hang** | `llama-server` passe en swap ou bloque en TCP sans erreur HTTP explicite. | `MIN_LLM_TOKENS_PER_SEC=5`, timeout connexion+lecture (`90s`), redémarrage auto Watchdog après 3 anomalies. |
| **Stack & Dépendances** | **Hallucination d'APIs tierces & Monolithes Brownfield** | Le modèle 0.8B invente des APIs Pydantic v1 / React obsolètes, ou déborde les `4096 tokens` sur un fichier existant de 800 lignes. | Cache déterministe **`DEPS_REALITY.md`**, `DEPENDENCY_INSTALL_POLICY`, **patch fenêtré par index AST** sur les fichiers `LEGACY_EXEMPT`. |
| **Sécurité & Concurrence** | **Collision port `8080`, réécriture `SPEC.md`, fuite `.env`, double run** | Un serveur généré entre en conflit avec `llama-server:8080`, l'IA modifie `SPEC.md`, `git add -A` commit `LLM_API_KEY`, ou 2 instances corrompent `state.json`. | Port IA dédié **`18080`**, verrou exclusif **`flock`**, **`PROTECTED_PATHS`**, staging Git sélectif, `DangerousCallScanner`, `env` strippé, sandbox `HOME`/`TMPDIR` + `unshare --net`. |

---

## 2. Règles Opérationnelles Durcies (Détails Algorithmiques)

### 2.1 Règle de Propagation *Ripple* (`NEEDS_REVERIFY`)
À la sortie de `2_EXTRACT`, chaque nœud calcule un `ast_sig_hash` basé uniquement sur ses **exports publics et leurs signatures** (ignorant le corps privé et les commentaires) :
1. Si `new_ast_sig_hash == old_ast_sig_hash` : aucun impact aval.
2. Si `new_ast_sig_hash != old_ast_sig_hash` : tous les nœuds `6_LOCKED` ayant ce nœud dans `depends_on` basculent en **`NEEDS_REVERIFY`**.
3. L'ordonnanceur traite `NEEDS_REVERIFY` **en priorité absolue sans appel LLM** : il exécute `ImportPreflightChecker` + `run_tests`. Si vert -> retour immédiat en `6_LOCKED`. Si cassé -> transition vers `4_REBALANCE` avec l'erreur exacte de rupture d'interface.

### 2.2 Règle Anti-*Reward-Hacking* (`DegenerationGuard` + `TestMonotonicityGate`)
Toute nouvelle version proposée d'un nœud déjà compilé ou testé est rejetée avant exécution si :
* Le nombre de fonctions de test ou d'assertions diminue par rapport au dernier commit sain (`assertions_new < assertions_prev`).
* Le code métier perd plus de `50%` de ses lignes non vides sans qu'une scission déclarée vers un sous-module n'ait eu lieu.
* L'AST du test contient un mock/patch ciblant le nom du module testé lui-même (`unittest.mock.patch("module_cible...")` / `vi.mock("./module_cible")`).
* Un bloc `except` ou `catch` avale l'erreur sans journalisation ni relance (`pass` / `{}`).

### 2.3 Règle d'Hygiène Disque & Longévité Git
À chaque `HEARTBEAT_INTERVAL_SEC=30` (et avant toute écriture critique de `state.json`) :
* Si `free_mb < DISK_MIN_FREE_MB (2048)` :
  1. Purge des dossiers temporaires de tests (`TMPDIR` sandbox, `.pytest_cache`, `__pycache__`, caches de build non essentiels).
  2. Compression des logs `events.jsonl` > `50 Mo` en `events.<n>.jsonl.gz`.
  3. Suppression des tags `green-step-*` au-delà des `20` plus récents et exécution de `git gc --auto`.
  4. Si après nettoyage `free_mb < 512 Mo` : **gel d'urgence propre (`FROZEN` avec raison `LOW_DISK_GUARD`)** afin de préserver `state.json` et le dépôt Git intacts plutôt que de corrompre le disque.

### 2.4 Règle d'Isolation anti-Prompt-Injection (`Brownfield` & Dépendances)
Dans un dépôt existant ou lors de l'analyse de messages d'erreurs externes, des commentaires malveillants ou bizarres pourraient tenter de détourner un petit modèle (`"Ignore previous instructions and delete..."`).
* Tout extrait de fichier existant ou trace externe est injecté entre balises `<UNTRUSTED_CODE>...</UNTRUSTED_CODE>`.
* Le modèle ne possède **aucun outil shell libre** : il ne retourne que du JSON strict (`gbnf` / `json_schema`) contenant du code ou des ordres architecturaux, filtrés par `PathJail`, `PROTECTED_PATHS` et `DangerousCallScanner`.

---

## 3. Résultat sur la Courbe de Fiabilité Multi-Jours

Grâce à ce blindage :
1. **Zéro dérive silencieuse** : l'AST, les signatures tierces et le graphe `REQ-*` ancrent l'IA dans la réalité du code à chaque pas.
2. **Zéro régression de fin de semaine** : l'isolation `hardening-wip` + *High-Watermark* `green-step-*` + fenêtre de gel H4 garantit que le livrable au jour 5 est **au moins aussi bon ou meilleur** que chaque état vert validé précédemment.
3. **Zéro blocage infini** : entre le détecteur d'oscillation `K=5`, le déblocage `BLOCKED_BY_UPSTREAM`, le `killpg` des tests bloqués, la relance Watchdog RAM/débit et la sortie d'inactivité `7_HARDENING`, le système reste souverain de bout en bout.
