# 06 — Contrats, Prompts Ultra-Compacts & Grammaires GBNF

Sous un budget strict de **`4096 tokens`**, la moindre verbosité dégrade la précision d'un modèle `0.8B`. Ce document définit la **budgétisation mathématique du contexte**, les **6 micro-prompts système** (`< 150 tokens` chacun) et les **contraintes structurelles** (GBNF / JSON Schema / délimiteurs) garantissant zéro bavardage hors format.

---

## 1. Budgétisation Stricte de la Fenêtre `4096 tokens`

Chaque appel HTTP *stateless* respecte l'allocation maximale suivante (vérifiée avant envoi par un estimateur déterministe `chars / 3.2` ou tokenizer local) :

| Zone du Prompt | Budget max (tokens) | Contenu exact |
| :--- | :--- | :--- |
| **1. System Prompt** | `<= 150` | Rôle unique, contraintes absolues (no `<think>`, <= 100 lignes, JSON pur). |
| **2. Contexte Contrat / État** | `<= 1 200` | `CONTRACT.md` local + `REALITY.md` des dépendances directes uniquement. |
| **3. Cible / Diff / Erreur distillée** | `<= 1 400` | Code courant (`<= 100` lignes) + éventuelle erreur distillée (`<= 180` tokens). |
| **4. Marge de sécurité tokenizer** | `~322` | Tampon anti-troncature pour tokens spéciaux et JSON wrapper. |
| **5. Réponse Générée (`max_tokens`)** | `1 024` | Sortie structurée GBNF / JSON Schema strictement bornée. |
| **Total Plafond** | **`4 096`** | **Jamais dépassé.** |

> [!WARNING]
> Si la zone 2 + 3 dépasse `2 600` tokens (par exemple trop de `REALITY.md` voisins), le `PromptBuilder` applique un **élagage topologique** : seuls les `REALITY.md` cités dans `depends_on` du `CONTRACT.md` sont conservés, puis les signatures sont résumées aux noms publics.

---

## 2. Règles d'Or d'Ingénierie de Prompts pour Modèles `< 1B`

1. **Impératif télégraphique** : aucun mot de politesse, aucune métaphore. Verbes d'action directs (`Génère`, `Scinde`, `Corrige`, `Retourne JSON`).
2. **Suppression explicite du raisonnement interne (`LLM_DISABLE_THINKING=true`)** :
   * Paramètre serveur/requête (`chat_template_kwargs: {"enable_thinking": false}` / `--reasoning-budget 0`).
   * Nettoyage regex défensif côté client si une balise `<think>...</think>` apparaît malgré tout.
3. **Isolation Anti-Prompt-Injection (`<UNTRUSTED_CODE>`)** : tout contenu provenant d'un dépôt *Brownfield*, d'un fichier legacy ou d'une trace d'erreur est encapsulé entre balises `<UNTRUSTED_CODE>...</UNTRUSTED_CODE>` avec consigne système de traiter son contenu strictement comme donnée (jamais comme instruction).
4. **Contrôle de Santé de Sortie (`LLM Output Sanity`)** : si le serveur retourne une chaîne vide, un JSON tronqué ou un débit `< MIN_LLM_TOKENS_PER_SEC (5 tok/s)`, `llm_client.py` marque l'appel en anomalie et notifie le Watchdog.
5. **Schémas JSON plats et peu imbriqués** : les modèles `0.8B` échouent dans les JSON profonds à 4–5 niveaux d'imbrication. Chaque sortie possède au maximum 2 niveaux.
6. **Code en bloc JSON échappé ou champ unique** : privilégier un champ `"code": "..."` strictement validé par grammaire GBNF.

---

## 3. Spécification des 6 Micro-Agents

| Micro-Agent | État | Entrées injectées | Sortie JSON exigée |
| :--- | :--- | :--- | :--- |
| **1. Architecte de dossier** | `0_ARCHITECT` | `SPEC.md` (ou `CONTRACT.md` parent) + arborescence actuelle + stack | `subfolders[]`, `files[]` (`path`, `purpose`, `depends_on`, `priority`, `contract_rules`) |
| **2. Codeur Unitaire** | `1_DRAFT` | `CONTRACT.md` cible + `REALITY.md` dépendances + règle `<=100L` | `filename`, `code`, `exports_summary` |
| **3. Extracteur Sémantique** | `2_EXTRACT` | Code source + signatures AST déjà extraites | `purpose_summary` (<= 2 phrases), `side_effects` |
| **4. Architecte Critique** | `3_CRITIQUE` | `SPEC.md` racine + tous `REALITY.md` agrégés + compteurs de lignes | `converged` (bool), `orders[]` (`target_path`, `action`, `reason`) |
| **5. Refactorer** | `4_REBALANCE` | Code v1 + `REFACTOR_ORDERS.md` ciblé + `REALITY.md` voisins | `actions_taken`, `files[]` (`path`, `code`) — permet la scission 1 -> 2 fichiers |
| **6. Optimiseur & Testeur** | `5_SYNTHESIS` | Code v2 + `CONTRACT.md` + convention tests de la stack | `optimized_code`, `test_path`, `test_code` |

### Exemples de Micro-Prompts Système (`< 120 tokens`)

**Micro-Agent `1_DRAFT` (Codeur Unitaire)** :
```text
Rôle: Codeur Unitaire expert {stack}.
Règles strictes:
1. Implémente UNIQUEMENT le contrat fourni.
2. Code complet sans TODO, pass, ... ni placeholder.
3. Maximum {max_lines} lignes.
4. Utilise exclusivement les imports des modules listés dans REALITY.
5. Réponds UNIQUEMENT en JSON valide conforme au schéma.
```

**Micro-Agent `3_CRITIQUE` (Architecte Critique)** :
```text
Rôle: Architecte Critique.
Compare SPEC.md aux signatures REALITY.md.
Détecte uniquement:
1. Incompatibilités de types/noms d'appels entre modules.
2. Fichiers >= 85 lignes à scinder.
3. Manques critiques par rapport à SPEC.md.
Si tout est cohérent, retourne converged=true et orders=[].
Réponds UNIQUEMENT en JSON valide.
```

---

## 4. Grammaires GBNF & Adaptation Multi-Backends (`LLM_STRUCTURED_MODE`)

Parce que `.env` autorise plusieurs fournisseurs IA (`llama_cpp`, `ollama`, `openai_compat`), `ConstraintEngine` traduit automatiquement le contrat de sortie selon `LLM_STRUCTURED_MODE` :

| Mode `.env` | Mécanisme utilisé | Fiabilité syntaxique | Backends compatibles |
| :--- | :--- | :--- | :--- |
| **`gbnf`** *(recommandé)* | Grammaire GBNF injectée au niveau des logits (`grammar` dans `/v1/chat/completions`) | **100 %** (impossible physiquement de sortir du JSON invalide) | `llama_cpp` (`llama-server`) |
| **`json_schema`** | Champ `response_format: {type: "json_schema", json_schema: ...}` | **~98–100 %** | `llama_cpp` récent, `ollama`, `openai_compat` |
| **`json_object`** | Champ `response_format: {type: "json_object"}` + validation Pydantic | **~90–95 %** (+ 1 retry parseur) | Tous backends OpenAI-compat |
| **`delimited`** | Balises strictes `<<<JSON>>>...<<<END>>>` si backend basique sans contrainte native | **~85–90 %** (fallback ultime) | Modèles locaux anciens |

### Exemple de Grammaire GBNF de Référence (`1_DRAFT` — Codeur)
```gbnf
root   ::= "{" ws "\"filename\":" ws string "," ws "\"code\":" ws string "," ws "\"exports_summary\":" ws string ws "}"
ws     ::= ([ \t\n] ws)?
string ::= "\"" ([^"\\] | "\\" (["\\/bfnrt] | "u" [0-9a-fA-F]{4}))* "\""
```

### Exemple de Schéma JSON de Référence (`3_CRITIQUE` — Critique)
```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["converged", "orders"],
  "properties": {
    "converged": { "type": "boolean" },
    "orders": {
      "type": "array",
      "maxItems": 6,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["target_path", "action", "reason"],
        "properties": {
          "target_path": { "type": "string" },
          "action": { "enum": ["FIX_INTERFACE", "SPLIT_FILE", "ADD_MISSING", "REMOVE_DUPLICATE"] },
          "reason": { "type": "string", "maxLength": 200 }
        }
      }
    }
  }
}
```
*(Limité à `maxItems: 6` pour éviter que le critique ne sature `max_tokens=1024` et garde chaque cycle de refactorisation chirurgical).*
