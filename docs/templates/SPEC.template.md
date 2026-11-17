# SPEC : <Nom du Projet>

> **Conseil d'utilisation (modèles <= 1B)** : Gardez ce fichier sous **800 tokens (~50–70 lignes)**. Soyez factuel, modulaire et orienté critères d'acceptation testables. Placez ce fichier dans `TARGET_PROJECT_DIR` (ou pointez `INITIAL_SPEC_PATH` vers lui).

## 1. Objectif & Périmètre
Décrivez en 2 à 3 phrases ce que doit faire l'application, son interface principale (CLI, API HTTP, bibliothèque, service) et ses utilisateurs.

## 2. Stack & Contraintes Techniques
- **Langage / Runtime** : ex. Python 3.12 / TypeScript Node 22 / Rust 1.82 / Go 1.23
- **Dépendances autorisées** : listez uniquement les bibliothèques nécessaires (ex. `fastapi`, `pydantic`, ou *standard library only*).
- **Contraintes** : ex. exécution offline, stockage SQLite/JSON local, limite `<= 100` lignes par fichier.

## 3. Architecture Cible Souhaitée (Hauts Modules)
1. **`core/`** : modèles de données, logique métier pure, validation.
2. **`adapters/`** : persistance, entrées/sorties, clients externes.
3. **`cli/` ou `api/`** : point d'entrée exposant les fonctionnalités.

## 4. Exigences Fonctionnelles Testables
- **REQ-01** : <Action claire + entrée attendue + sortie ou erreur attendue>.
- **REQ-02** : <Action claire + entrée attendue + sortie ou erreur attendue>.
- **REQ-03** : <Action claire + gestion explicite des cas limites / erreurs>.

## 5. Critères d'Acceptation Globaux
- Tous les tests unitaires et d'intégration passent (`exit code 0`).
- Aucune erreur de syntaxe ni de linter.
- Présence d'un `README.md` d'utilisation rapide dans le projet cible.
