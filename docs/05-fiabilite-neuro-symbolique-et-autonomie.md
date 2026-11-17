# 05 — Innovations de Fiabilité Neuro-Symbolique & Autonomie (`< 1B`)

Un modèle de langage de `0.8B` paramètres possède une vitesse remarquable (~60–80 tok/s sur CPU), mais souffre de quatre faiblesses connues en génie logiciel autonome : **hallucination de noms d'imports**, **répétition en boucle sur les erreurs**, **saturation de sa fenêtre de 4096 tokens par du bruit** et **génération de tests factices** (*fake green*).

**StructuredAI** compense ces faiblesses par **six innovations neuro-symboliques** où le code déterministe encadre et vérifie chaque sortie probabiliste.

---

## 1. Innovation A — Compression Ascendante Hybride (`AST + LLM`)

### Le problème classique
Demander à un modèle `0.8B` de lire 100 lignes de code et de réécrire de mémoire les signatures exactes dans `REALITY.md` produit 10 à 20 % d'erreurs subtiles (un paramètre inversé, un type de retour inventé, un import oublié). Sur 24 heures, ces micro-erreurs s'accumulent en cascade.

### La solution StructuredAI (`2_EXTRACT`)
La création de `REALITY.md` est **scindée en deux sources** :
1. **Vérité Structurelle 100 % Déterministe (`StackAdapter.extract_symbols`)** : le parseur AST/Tree-sitter/ctags extrait mécaniquement les noms exacts de classes, fonctions, arguments, types, constantes et imports. **Zéro token LLM, zéro hallucination.**
2. **Résumé Sémantique Ultra-Court (LLM, max 60 tokens)** : le micro-agent Extracteur reçoit uniquement le code source et produit une description en **1 à 2 phrases maximum** du rôle métier du module.

### Agrégation Hiérarchique Anti-Explosion
Lorsque la profondeur dépasse 1 niveau de dossier, chaque dossier maintient un `REALITY.md` d'index qui n'inclut que les **symboles publics exportés** des enfants (max `20` lignes par dossier). Même sur un projet de 150 fichiers, la racine voit l'intégralité de la carte applicative en **moins de 1 500 tokens**.

---

## 2. Innovation B — Pré-Vol d'Imports, Dépendances Tierces & Anti-Cycles (`ImportPreflightChecker`)

### Le problème classique
Le Codeur en `1_DRAFT` invente un import local inexistant, utilise une API obsolète d'une bibliothèque tierce (ex. Pydantic v1 au lieu de v2), ou introduit une dépendance circulaire (`A -> B -> A`) qui bloque le graphe.

### La solution StructuredAI
Dès `1_DRAFT` et `4_REBALANCE`, avant même d'exécuter un linter ou des tests, le pré-vol vérifie déterministiquement :
1. **Imports locaux (`REALITY.md`)** : vérifie que le module et le symbole importé existent dans les exports AST réels. Sinon, rejet en `< 50 ms` avec liste des symboles disponibles.
2. **Dépendances tierces (`DEPS_REALITY.md`)** : vérifie que le paquet tiers est bien installé dans l'environnement (`importlib.util.find_spec`, `node require.resolve`, `Cargo.toml`/`go.mod`) et injecte uniquement les signatures réelles de la version installée.
3. **Graphe sans cycle (`CycleDetector`)** : contrôle topologique interdisant toute référence circulaire entre nœuds ; en cas de cycle, ordonne d'extraire les types partagés vers un module feuille.

---

## 3. Innovation C — Distillation Chirurgicale des Erreurs (`ErrorDistiller`)

### Le problème classique
Injecter une traceback brute de `pytest`, `tsc` ou `cargo` (souvent 80 à 200 lignes) consomme jusqu'à **1 800 tokens**, ce qui noie le modèle `0.8B` et réduit son attention sur le `CONTRACT.md`.

### La solution StructuredAI
Avant réinjection dans le prompt de correction, `ErrorDistiller` applique un filtrage déterministe par regex/parseur selon la stack :
1. Supprime les chemins système internes (`site-packages`, `node_modules`, frames runtime).
2. Extrait exclusivement :
   * Le **type d'erreur et le message racine** (`AssertionError`, `TypeError`, `E0308 mismatched types`).
   * Le **numéro de ligne exact** dans le fichier cible.
   * Une **fenêtre locale de `+/- 3` lignes** autour de la ligne fautive.
3. Tronque strictement le tout à **<= 180 tokens**.

---

## 4. Innovation D — Détecteur de Stagnation & Escalade Stratégique (`StagnationDetector`)

### Le problème classique
Un modèle à `temperature=0.2` confronté à une erreur persistante régénère souvent **exactement le même code** aux essais 2, 3, 4 et 5, brûlant inutilement le budget temps et les 5 essais du Circuit Breaker.

### La solution StructuredAI
À chaque échec d'un nœud, l'orchestrateur calcule deux empreintes et maintient un **historique glissant `history_hashes` (`K = 5`)** :
* `code_hash = sha256(normalized_code)`
* `err_hash = sha256(distilled_error_type_and_line)`

| Motif détecté | Diagnostic | Action automatique d'Escalade Stratégique |
| :--- | :--- | :--- |
| `code_hash` déjà vu dans `history_hashes` | Boucle directe (`A -> A`) ou oscillation ping-pong (`A -> B -> A`) | Passe temporairement `temperature` à `0.45`, interdit explicitement la dernière approche et injecte les signatures exactes des voisins. |
| `err_hash` identique 2 fois malgré diff | L'approche algorithmique du nœud est erronée | Force une **scission préventive** (`split_contract`) si `> 45` lignes ou bascule vers le modèle critique s'il est configuré. |
| `line_count > 100` répété 2 fois | Le contrat du nœud est trop dense pour 1 fichier | Retour ciblé vers `0_ARCHITECT` pour éclater en 2 sous-fichiers (`>= 15` lignes chacun). |
| Chute suspecte de code (*Degeneration Guard*) | `> 50%` de LOC en moins sans scission ou corps réduit à un retour constant (`return {}` / `return True`) | Rejet immédiat pour éviter que l'IA ne "triche" en vidant la logique métier pour faire passer les tests. |
| Détection de placeholder (`TODO`, `pass`, `...`, `// rest of code`) | Paresse / troncature du petit modèle | Rejet immédiat sans exécuter le linter + injonction stricte de complétude. |

Si malgré l'escalade le seuil `MAX_RETRIES_PER_NODE=5` est atteint, le **Circuit Breaker** classe le nœud `FAILED_MANUAL_REVIEW`, journalise dans `ERRORS.md`, restaure le dernier commit sain et débloque la file.

---

## 5. Innovation E — Garde Anti-Tests-Factices & Monotonie (`AntiTrivialTestGate`)

### Le problème classique
Sous pression sur plusieurs jours, un modèle léger peut tricher (*Reward Hacking*) en générant `assert True`, en mockant la fonction qu'il teste, en avalant les exceptions (`except Exception: pass`) ou en supprimant une assertion gênante d'un test précédemment vert.

### La solution StructuredAI
Avant d'accepter `6_LOCKED`, le validateur applique **6 contrôles AST déterministes** :
1. **Présence d'import réel** : le fichier de test doit importer au moins un symbole du module cible.
2. **Invocation effective & Anti-Sur-Mocking** : au moins un appel réel non mocké au module cible ; interdit de mocker/patcher le module testé lui-même (`<= 0%` de patch sur la cible directe).
3. **Assertions non triviales** : présence d'au moins `2` assertions distinctes (cas nominal + cas d'erreur/limite) comparant des expressions non constantes (`assert 1 == 1` interdit).
4. **Interdiction des blocs `except` silencieux** dans le code et les tests.
5. **Monotonie des Tests (`ENABLE_TEST_MONOTONICITY_GATE`)** : lors d'une mise à jour en `4_REBALANCE` ou `7_HARDENING`, le nombre de fonctions de test et d'assertions ne doit **jamais diminuer** par rapport au dernier commit vert du nœud.
6. **Non-vacuité du runner** : le runner doit rapporter `executed_tests >= 1` (bloque un faux succès `0 tests collected, exit 0`).

---

## 6. Innovation F — Isolation Transactionnelle Git, *High-Watermark* & Intégration Continue

Un simple `git commit` par fichier ne protège pas contre les régressions inter-modules sur plusieurs jours ni contre les fuites de secrets.

1. **Branche Autonome Dédiée (`GIT_WORK_BRANCH=ai-auto`)** : la branche principale humaine (`main`/`master`) n'est **jamais modifiée** directement.
2. **Staging Sélectif Strict** : l'orchestrateur n'exécute **jamais** `git add -A` aveuglément. Seuls les fichiers validés du nœud sont stagés ; `.env*`, `.orchestrator/`, `*.key`, `*.pem` sont bloqués par filtre pré-commit.
3. **Invalidation en Cascade (*Ripple*) & Checkpoints d'Intégration** : si l'AST d'un nœud change, tous ses dépendants `6_LOCKED` passent en `NEEDS_REVERIFY`. Tous les `INTEGRATION_CHECK_INTERVAL=5` nœuds verrouillés, l'orchestrateur lance la **suite de tests complète + smoke test du point d'entrée**.
4. **Tags *High-Watermark* Verts (`green-step-NNN`)** : posés **uniquement** lorsque la suite globale + smoke test passent (avec rétention des `MAX_GREEN_TAGS_KEEP=20` derniers tags et `git gc --auto` périodique).
5. **Sauvegarde de Sortie en Phase H4 (`FROZEN`)** : toute tentative tardive en `7_HARDENING` tourne sur `hardening-wip` ; en cas de régression en fin de session, `git reset --hard <last_green_tag>` garantit un livrable **100 % compilable et testé**.

---

## 7. Innovation G — Matrice de Traçabilité `SPEC.md` (`REQ-*`)

Pour éviter qu'un modèle léger ne dérive pendant 72h en polissant des détails secondaires tout en oubliant une exigence clé de `SPEC.md`, l'orchestrateur extrait dès `0_INGEST` la liste des exigences `REQ-01..N`, oblige `0_ARCHITECT` à affecter chaque `REQ-*` à au moins un nœud + test, et vérifie en `3_CRITIQUE` et `RUN_REPORT.md` qu'aucun `REQ-*` n'est orphelin.
