# **Spécification Technique : Orchestrateur Multi-Agents Dialectique & Récursif (Budget 1 Go RAM)**

## **1\. Contexte Matériel et Contraintes Système**

> * **Machine cible :** Samsung Galaxy Book2 Pro (CPU Intel Core 12e génération / GPU intégré Intel Iris Xe).  
> * **Système d'exploitation :** Fedora 44 (Environnement GNOME / Wayland).  
> * **Contrainte mémoire stricte :** **1 Go de RAM maximum** alloué à l'ensemble de la stack d'inférence IA.  
> * **Objectif opérationnel :** Exécution autonome d'un système de développement logiciel pendant **24 heures consécutives** sans intervention humaine, piloté par le temps et la convergence des tests, capable de générer un projet complet à partir d'une spécification initiale.

## **2\. Stack d'Inférence & Configuration du Modèle**

### **2.1 Choix du Modèle**

> * **Modèle retenu :** Qwen3.5-0.8B (Quantification GGUF Q4\_K\_M).  
> * **Justification :** Meilleur ratio vitesse/fiabilité sous la barre du gigaoctet (\~550 à 650 Mo de poids en RAM, \~60 à 80+ tokens/sec sur CPU Intel mobile), excellente maîtrise du français et respect strict des formats structurés (JSON/Markdown).

### **2.2 Infrastructure d'Exécution**

> * **Interface manuelle (tests/supervision) :** **Alpaca** (installé via Flatpak, interface native GTK4 ultra-légère) utilisant le moteur llama.cpp.  
> * **Moteur d'exécution autonome (boucle 24h) :** llama-server (llama.cpp) lancé en arrière-plan de manière persistante (pour éviter de recharger les poids depuis le SSD à chaque étape), interrogé via requêtes HTTP *stateless* (/v1/chat/completions avec nettoyage complet du contexte à chaque appel).  
> * **Optimisation mémoire & CPU :**  
  * Quantification du cache KV (-ctk q8\_0 \-ctv q8\_0) pour maintenir l'empreinte totale (poids \+ contexte \+ serveur) sous 850 Mo.  
  * Limitation des threads aux cœurs physiques performants (P-cores) pour optimiser le débit et limiter la chauffe.

### **2.3 Paramètres d'Inférence Obligatoires**

> * **Mode Thinking / Reasoning (\<think\>) :** **DÉSACTIVÉ** (consomme trop de tokens de contexte et dégrade la vitesse et la stabilité sur un modèle 0.8B).  
> * **Context Size (n\_ctx) :** 4096 tokens stricts.  
> * **Température :** 0.2 (déterminisme élevé, réduction maximale des hallucinations).  
> * **Contrainte de sortie :** Utilisation systématique des **grammaires GBNF** de llama.cpp ou de **PydanticAI / Outlines** pour forcer des sorties JSON valides au niveau des logits (interdiction physique de bavardage hors schéma).

## **3\. Règles Fondamentales de Génie Logiciel (Invariants)**

Pour pallier la fenêtre de contexte réduite (4096 tokens) et éviter l'effet tunnel ou la dérive cumulative sur 24 heures, l'orchestrateur applique des garde-fous déterministes stricts :

> 1. **Règle des 100 lignes :** Aucun fichier de code généré ne doit dépasser **100 lignes** (wc \-l \<= 100). Si un fichier dépasse cette limite, il est immédiatement rejeté ou scindé en sous-modules.  
> 2. **Zéro mémoire conversationnelle :** Les agents ne discutent pas entre eux. Chaque invocation repart d'un contexte vierge (0 historique) alimenté uniquement par les fichiers Markdown locaux du dossier concerné.  
> 3. **Interdiction des frameworks multi-agents lourds :** Pas de CrewAI, LangGraph ou AutoGen (leurs prompts système internes consomment 1 500 à 3 000 tokens). L'orchestrateur doit être un **script Python autonome et déterministe** pilotant une machine à états.  
> 4. **Compression ascendante obligatoire :** Lorsqu'une information remonte vers les niveaux supérieurs de l'arborescence, le code est compressé en signatures pures (noms de fonctions, types d'entrées/sorties, dépendances) sur 5 à 15 lignes maximum (REALITY.md).  
> 5. **Isolation transactionnelle Git :** Chaque unité de code validée déclenche un git commit atomique. En cas de corruption ultérieure, l'orchestrateur effectue un git checkout automatique.

## **4\. Architecture Récursive : Cycle Dialectique en 3 Passes**

Le projet est construit récursivement dossier par dossier, de la racine vers les feuilles. Chaque unité de travail (dossier ou fichier) subit **3 passes complètes** selon une logique **Thèse → Antithèse → Synthèse**, combinant des mouvements verticaux de **Descente (Top-Down)** et de **Montée (Bottom-Up)**.  
`[SPEC.md Racine]`  
       `│`  
       `▼ (1. DESCENTE - Thèse : Découpage & Contrats)`  
`[Dossiers & CONTRACT.md] ──► [Codeur : Fichiers v1 <= 100 lignes]`  
       `│`  
       `▲ (2. MONTÉE - Thèse : Extraction des signatures réelles)`  
`[REALITY.md agrégés] ──────► [Architecte Racine]`  
       `│`  
       `▼ (3. DESCENTE - Antithèse : Rééquilibrage & Refactoring)`  
`[REFACTOR_ORDERS.md] ─────► [Refactorer : Alignement & Scission v2]`  
       `│`  
       `▲ (4. MONTÉE - Antithèse : Vérification de convergence)`  
`[Validation Globale] ─────► (Max 2 cycles de rééquilibrage)`  
       `│`  
       `▼ (5. DESCENTE - Synthèse : Optimisation & Tests Unitaires)`  
`[Optimiseur & Testeur] ───► [Code v3 + Tests Verts + Linter OK]`  
       `│`  
       `▲ (6. MONTÉE - Clôture : Verrouillage & Commit)`  
`[Statut LOCKED + Git Commit]`

### **Détail des 3 Passes**

#### **Passe 1 : La THÈSE (Phase d'Action — Création brute)**

> * **Descente (Top-Down) :** L'Architecte découpe la SPEC.md parente en sous-dossiers et rédige un CONTRACT.md local (définissant strictement les entrées, sorties et responsabilités). Le Codeur génère une première version du fichier (v1, max 100 lignes).  
> * **Montée (Bottom-Up) :** Dès que la syntaxe de base est valide, l'agent Extracteur génère un fichier REALITY.md (résumé technique de 10 lignes contenant les signatures exactes et imports réels du fichier créé) et le remonte jusqu'à la racine.

#### **Passe 2 : L'ANTITHÈSE (Phase de Rééquilibrage — Critique et Alignement global)**

> * **Montée critique (Sommet) :** L'Architecte racine confronte la SPEC.md initiale avec l'ensemble des REALITY.md remontés du terrain. Il identifie les incohérences de typage, les doublons fonctionnels entre dossiers ou les fichiers proches de la limite des 100 lignes, et émet un fichier REFACTOR\_ORDERS.md.  
> * **Descente corrective :** Les agents redescendent avec REFACTOR\_ORDERS.md. Le Refactorer modifie le code (v2), harmonise les appels entre modules et scinde tout fichier trop dense.  
> * **Critère de convergence :** Pour éviter toute boucle infinie sur 24h, la Passe 2 est bornée à **2 cycles de rééquilibrage maximum** par nœud (ou s'arrête dès que REFACTOR\_ORDERS.md est vide).

#### **Passe 3 : La SYNTHÈSE (Verrouillage, Tests et Optimisation)**

> * **Descente finale :** L'Optimiseur nettoie le code mort et gère les cas limites (v3). Le Testeur génère un fichier de test unitaire dédié (test\_\*.py / \*.test.ts).  
> * **Montée de clôture :** L'orchestrateur exécute de manière déterministe le compteur de lignes (\<= 100), le linter/compilateur et la suite de tests. Si tout est vert, le nœud passe à l'état LOCKED et un git commit est exécuté.

## **5\. Machine à États & Micro-Agents Spécialisés**

L'état global du projet est persisté sur disque dans un fichier state.json. À chaque itération, l'orchestrateur lit l'état du nœud courant et injecte uniquement le prompt système minimaliste du micro-agent correspondant (budget total par appel : **\< 2 500 tokens**).

| État dans state.json | Phase & Direction | Micro-Agent activé | Entrées fournies (Contexte strict) | Sortie exigée (JSON GBNF) | Garde-fou déterministe |
| :---- | :---- | :---- | :---- | :---- | :---- |
| 0\_ARCHITECT | Thèse (Descente) | **Architecte de dossier** | SPEC.md parent \+ arborescence | Sous-dossiers \+ CONTRACT.md | Unicité des chemins, max 5 fichiers/dossier |
| 1\_DRAFT | Thèse (Descente) | **Codeur Unitaire** | CONTRACT.md \+ Règles de style | Code source v1 | wc \-l \<= 100 \+ syntaxe valide |
| 2\_EXTRACT | Thèse (Montée) | **Extracteur** | Code source v1 | REALITY.md (signatures) | Longueur \<= 15 lignes |
| 3\_CRITIQUE | Antithèse (Sommet) | **Architecte Critique** | SPEC.md racine \+ tous REALITY.md | REFACTOR\_ORDERS.md | Max 2 passages par nœud |
| 4\_REBALANCE | Antithèse (Descente) | **Refactorer** | Code v1 \+ REFACTOR\_ORDERS.md | Code aligné v2 (ou scission) | wc \-l \<= 100 \+ Linter |
| 5\_SYNTHESIS | Synthèse (Descente) | **Optimiseur & Testeur** | Code v2 \+ CONTRACT.md final | Code v3 \+ fichier de test | Linter \+ Exécution des tests (PASS) |
| 6\_LOCKED | Synthèse (Montée) | *(Script Python pur)* | Fichiers validés | Mise à jour index global | git commit atomique |

## **6\. Gestion du Temps (24h) et Tolérance aux Pannes**

> 1. **Budget d'essais par nœud (Circuit Breaker) :** Si un fichier échoue à passer le linter, la limite des 100 lignes ou les tests unitaires après **5 tentatives consécutives** de correction (réinjection de l'erreur exacte dans le prompt), l'orchestrateur marque le fichier FAILED\_MANUAL\_REVIEW, journalise l'erreur dans ERRORS.md, restaure le dernier commit sain et passe à la branche suivante afin de ne jamais bloquer le cycle de 24 heures.  
> 2. **Ordonnancement temporel :** L'orchestrateur tourne dans une boucle principale contrôlée par time.time() \< start\_time \+ 86400\. Si l'ensemble de l'arborescence atteint l'état 6\_LOCKED avant la fin des 24 heures, le système déclenche un **macro-cycle global d'audit et d'optimisation** (réouverture des nœuds en Passe 2/3 pour améliorer la couverture de tests et la performance).

## **7\. Instructions pour l'Implémentation (À destination de Gemini / Antigravity)**

Pour préparer et générer cet environnement de travail, merci de structurer le projet orchestrateur (lui-même respectant la règle des **\< 100 lignes par fichier**) selon l'arborescence suivante :

> 1. config.py : Paramètres de connexion à llama-server (localhost:8080), température (0.2), contexte (4096), durée cible (24h) et seuils de tentatives (max\_retries \= 5).  
> 2. llm\_client.py : Client HTTP *stateless* vers llama-server avec support des schémas JSON / grammaires GBNF et désactivation explicite des balises \<think\>.  
> 3. prompts.py : Les 6 prompts système ultra-concis (\< 150 tokens chacun) en français/anglais technique pour les micro-agents (Architecte, Codeur, Extracteur, Critique, Refactorer, Optimiseur/Testeur).  
> 4. validators.py : Fonctions déterministes de vérification (check\_line\_count \<= 100, exécution du linter, exécution des tests unitaires, opérations git commit / git checkout).  
> 5. state\_machine.py : Gestionnaire de l'arbre d'états (state.json) implémentant les transitions Thèse (Descente/Montée) → Antithèse (Critique/Rééquilibrage) → Synthèse (Verrouillage).  
> 6. main.py : Boucle principale temporelle (24h) orchestrant la machine à états, la journalisation et le *circuit breaker*.  
> 7. setup\_fedora.sh : Script d'installation et de lancement de llama-server avec Qwen3.5-0.8B-Q4\_K\_M.gguf configuré pour consommer moins de 1 Go de RAM sous Fedora 44\.