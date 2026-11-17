# 04 — Adaptation Universelle aux Projets & Stacks Technologiques

Pour que **StructuredAI** fonctionne aussi bien sur une API Python que sur un microservice Rust, un frontend TypeScript, un outil CLI Go, un projet C/C++ ou une stack maison, le noyau d'orchestration **ne contient aucune logique codée en dur liée à un langage**. Tout passe par un **Adaptateur de Stack (`StackAdapter`)** et une phase initiale d'**Ingestion (`0_INGEST`)**.

---

## 1. Mode *Greenfield* vs Mode *Brownfield*

Selon `PROJECT_MODE=auto|greenfield|brownfield` et l'inspection de `TARGET_PROJECT_DIR` :

### 1.1 Mode *Greenfield* (Nouveau projet)
* Déclenché lorsque `TARGET_PROJECT_DIR` ne contient aucun code source existant (seulement `SPEC.md` et éventuellement `.git` / `.env`).
* L'Architecte initialise le squelette minimal de la stack cible (`pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, etc.) en respectant l'invariant de modularité dès le premier commit.

### 1.2 Mode *Brownfield* (Projet existant)
* Déclenché lorsqu'un dépôt ou du code source préexiste dans `TARGET_PROJECT_DIR`.
* **Protocole d'Ingestion Sécurisée (Phase H0)** :
  1. **Inventaire non-destructif & Filtre Binaire/Taille** : scan de l'arborescence en respectant `.gitignore` ; tout fichier non UTF-8, binaire ou `> MAX_INGEST_FILE_BYTES (256 Ko)` est ignoré pour éviter la saturation mémoire.
  2. **Extraction AST immédiate sans LLM** : génération déterministe des `REALITY.md` pour les fichiers existants + construction du cache **`DEPS_REALITY.md`** listant les versions et exports réels des bibliothèques tierces installées.
  3. **Respect des Monolithes Existants (`Legacy Guard` + Patch Fenêtré)** : les fichiers existants `> 100` lignes sont marqués `LEGACY_EXEMPT`. Comme un fichier de 800 lignes dépasse la fenêtre `4096 tokens`, l'agent **ne le lit jamais en entier** : il reçoit uniquement un **index AST (noms + plages de lignes)** et travaille soit via un patch chirurgical sur une plage `<= 80` lignes, soit en plaçant la nouvelle logique dans un module annexe `<= 100` lignes appelé par un hook minimal.
  4. **Baseline verte initiale** : exécution des tests existants avant toute modification pour établir le premier tag *High-Watermark* (`green-baseline`).

---

## 2. Auto-Détection de Stack (`StackDetector`)

Si `TARGET_STACK=auto`, le détecteur analyse la racine de `TARGET_PROJECT_DIR` (et le contenu de `SPEC.md` en *Greenfield*) selon l'ordre de priorité suivant :

| Empreinte détectée (fichiers / mots-clés SPEC) | Profil activé | Extracteur AST par défaut |
| :--- | :--- | :--- |
| `pyproject.toml`, `requirements.txt`, `setup.py`, `*.py` | `python` | Module natif `ast` de Python |
| `tsconfig.json`, `package.json` (avec TS) | `node_ts` | `tree-sitter-typescript` / regex typée |
| `package.json` (JS pur) | `node_js` | `tree-sitter-javascript` / regex ESM-CJS |
| `Cargo.toml`, `*.rs` | `rust` | `tree-sitter-rust` / parseur `pub fn|struct|enum|trait` |
| `go.mod`, `*.go` | `go` | `go doc` / `tree-sitter-go` |
| `CMakeLists.txt`, `Makefile`, `meson.build`, `*.c/*.cpp/*.h` | `c_cpp` | `ctags` / `tree-sitter-cpp` |
| `pom.xml`, `build.gradle*`, `*.java` | `java` | `tree-sitter-java` / `javap` |
| `index.html` sans bundler serveur | `web_static` | Parseur DOM / liens assets + validation HTML/CSS |
| `STACK_PROFILE_PATH` défini ou `TARGET_STACK=custom` | `custom` | Commandes définies dans `stack.toml` / `.env` |

> [!TIP]
> **Projets Polyglottes / Monorepos** (ex. `backend/` en Rust ou Python + `frontend/` en TypeScript) : le `StackRouter` associe un `StackAdapter` **par sous-dossier racine** (`backend/` -> `python`, `frontend/` -> `node_ts`) en se basant sur le manifeste le plus proche dans l'arborescence.

---

## 3. Contrat d'Interface `StackAdapter` (Les 6 Hooks Déterministes)

Chaque profil de stack implémente exactement **6 hooks déterministes** exécutés par le noyau Python dans un sous-processus isolé et borné par `SUBPROCESS_TIMEOUT_SEC` :

| # | Hook | Rôle dans la machine à états | Exemples concrets |
| :--- | :--- | :--- | :--- |
| **1** | `bootstrap()` | Prépare l'environnement isolé une fois en `0_INGEST` | `python -m venv .venv`, `npm ci`, `cargo fetch` |
| **2** | `check_syntax(file)` | Validation ultra-rapide (< 2s) dès `1_DRAFT` | `python -m py_compile`, `tsc --noEmit`, `go vet`, `cargo check -q` |
| **3** | `lint(file)` | Vérifie règles de style, variables mortes, typage en `4_REBALANCE` & `5_SYNTHESIS` | `ruff check`, `eslint`, `cargo clippy`, `golangci-lint` |
| **4** | `run_tests(target_test)` | Exécution **ciblée** sur le module courant en `5_SYNTHESIS`, et **globale** en H4 / tag vert | `pytest -q <test_file>`, `vitest run <file>`, `cargo test <mod>` |
| **5** | `extract_symbols(file)` | Extraction 100 % déterministe des exports, signatures et imports pour `REALITY.md` | Python `ast`, `tree-sitter`, `ctags --output-format=json` |
| **6** | `build_check()` | Vérification finale de compilation / packaging en `6_LOCKED` / `FROZEN` | `npm run build`, `cargo build`, `go build ./...` |

---

## 4. Catalogue des Profils de Stacks Intégrés

| Stack | Extensions code (`<= 100L`) | Convention fichier test | Commande Syntaxe | Commande Lint | Commande Test ciblé |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`python`** | `.py` | `tests/**/test_<name>.py` | `python -m py_compile {file}` | `ruff check {file}` | `pytest -q --tb=short {test_file}` |
| **`node_ts`** | `.ts`, `.tsx` | `**/*.test.ts` | `npx tsc --noEmit` | `npx eslint {file}` | `npx vitest run {test_file}` |
| **`rust`** | `.rs` | `tests/<name>_test.rs` ou `mod tests` | `cargo check --message-format=short` | `cargo clippy -- -D warnings` | `cargo test {module}` |
| **`go`** | `.go` | `<pkg>/<name>_test.go` | `go vet ./{pkg_dir}` | `golangci-lint run {pkg_dir}` | `go test -v ./{pkg_dir} -run {test_pattern}` |
| **`c_cpp`** | `.c`, `.h`, `.cpp`, `.hpp` | `tests/test_<name>.c` | `gcc/g++ -fsyntax-only -Wall {file}` | `clang-tidy {file}` | `ctest --output-on-failure -R {name}` |
| **`java`** | `.java` | `src/test/.../<Name>Test.java` | `mvn test-compile` / `javac` | `checkstyle` (si configuré) | `mvn -q test -Dtest={TestClass}` |
| **`web_static`** | `.html`, `.js`, `.mjs` | `tests/<name>.test.mjs` | `node --check {file}` | `eslint` / `stylelint` | `node --test {test_file}` |

*(Chaque commande est automatiquement ignorée avec un avertissement journalisé si l'outil optionnel, ex. `clang-tidy`, n'est pas installé sur la machine hôte, tandis que les vérifications critiques — syntaxe et tests — sont obligatoires).*

---

## 5. Adaptation Intelligente de la Règle des 100 Lignes & Anti-Explosion

La règle des `<= 100` lignes est vitale pour la fenêtre de contexte `4096 tokens`, mais une application naïve sur plusieurs jours provoquerait une explosion combinatoire de micro-fichiers et de dossiers :
1. **Fichiers de code source** : plafond strict `MAX_LINES_PER_FILE=100` (avertissement dès `85` lignes en `3_CRITIQUE`).
2. **Plancher anti-fragmentation (`MIN_SPLIT_FILE_LINES=15`)** : interdit de scinder un fichier en fragments triviaux de moins de `15` lignes ; si un dossier contient trop de micro-fichiers `< 20` lignes, `3_CRITIQUE` peut ordonner leur regroupement cohérent.
3. **Plafond d'arborescence (`MAX_TREE_DEPTH=4`, `MAX_FILES_PER_DIR=5`)** : limite la profondeur maximale à 4 niveaux. Les fichiers d'index (`__init__.py`, `index.ts`, `mod.rs`) et les fichiers de tests ne comptent pas dans la limite des 5 modules métier par dossier.
4. **Scission sûre (Façade + Propagation)** : lorsqu'un fichier `foo.py` est scindé en `foo.py` + `foo_helpers.py`, le module principal ré-exporte les symboles déplacés ou déclenche automatiquement `NEEDS_REVERIFY` sur tous ses appelants afin d'éviter toute cassure silencieuse et tout import circulaire.
5. **Politique de Dépendances (`DEPENDENCY_INSTALL_POLICY`)** : le codeur ne peut pas installer de paquets arbitraires à la volée ; les dépendances autorisées sont déclarées au niveau `0_ARCHITECT` selon la politique `.env` (`none` | `manifest_only` | `allow_verified`) et indexées dans `DEPS_REALITY.md`.
6. **Fichiers exemptés (`LINE_LIMIT_EXEMPT_EXTS`)** : `.md`, `.json`, `.toml`, `.yaml`, `.lock`, `.sql`, `.css`, `.svg` ne sont pas bloqués à 100 lignes s'ils sont déclaratifs (plafond de lisibilité à `300` lignes pour les schémas générés).

---

## 6. Déclaration d'une Stack Personnalisée (`stack.toml`)

Pour adapter le framework à n'importe quelle stack exotique (Elixir, Zig, PHP/Laravel, Flutter, scripts Bash/Ansible, etc.), l'utilisateur fournit un fichier `stack.toml` référencé par `STACK_PROFILE_PATH` (voir le modèle complet dans [docs/templates/stack.template.toml](templates/stack.template.toml)) :

```toml
[stack]
name = "zig_custom"
code_extensions = [".zig"]
exempt_extensions = [".md", ".zon", ".json"]
test_file_pattern = "tests/{stem}_test.zig"

[commands]
bootstrap = "zig version"
syntax_check = "zig ast-check {file}"
lint = "zig fmt --check {file}"
test_targeted = "zig test {test_file}"
test_suite = "zig build test"
build_check = "zig build"

[symbols]
extractor = "regex"
export_regex = "^pub\\s+(fn|const|struct|enum)\\s+([A-Za-z0-9_]+)"
```

---

## 7. Isolation des Exécutions & Sécurité du Système Hôte

Un agent autonome qui génère et exécute du code pendant plusieurs jours peut involontairement créer une boucle infinie, saturer le système, écraser un fichier critique ou entrer en collision avec le serveur IA :
* **Process Group Kill (`setsid` + `SIGKILL`)** : chaque hook est lancé dans un nouveau groupe de processus ; en cas de dépassement de `SUBPROCESS_TIMEOUT_SEC` (`45s`), tout l'arbre des processus enfants est tué proprement.
* **Isolation Réseau & Sandbox Éphémère (`ALLOW_NETWORK_IN_TESTS=false`)** : exécution avec `HOME` et `TMPDIR` éphémères isolés (vidés après test), variables secrètes (`LLM_API_KEY`) strippées de `env`, isolation réseau `unshare --net` lorsque supportée par le noyau, et vérification `git status` post-test pour détecter tout fichier parasite créé hors sandbox.
* **Confinement `PathJail` & `PROTECTED_PATHS`** : toute écriture passe par `Path(target).resolve().is_relative_to(TARGET_PROJECT_DIR.resolve())` sans suivre les liens symboliques externes. En outre, `SPEC.md`, `.env*`, `.git/`, `stack.toml` et `.orchestrator/state.json` sont en lecture seule absolue pour les agents.
* **Scanner Pré-Exécution (`DangerousCallScanner`)** : avant d'exécuter un test ou script généré, blocage AST/regex des appels destructeurs (`rm -rf`, écritures hors projet, modification de `os.environ`, écoute sur le port réservé `18080`).
