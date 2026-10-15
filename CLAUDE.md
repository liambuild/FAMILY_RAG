# FAMILY_RAG

RAG familial local open source : FastAPI + LangChain + FAISS + Ollama, interface Alpine.js, déploiement Docker Compose.
Projet public avec des utilisateurs existants : je ne le déploie pas moi-même, la cible est leur installation (Linux et Docker Desktop).

## Chantier en cours : modernisation
- Références : AUDIT.md (constat + plan par lots, section 6) et DECISIONS.md (mes arbitrages, prioritaires sur l'audit).
- Avant de coder, lis la section du lot demandé dans AUDIT.md et les décisions qui le concernent. Vérifie que ses prérequis sont fusionnés.
- Une branche `lot-N` par lot, créée depuis `modernisation`. Jamais de commit direct sur `main` ni sur `modernisation`.
- Un seul lot par session. Un problème repéré hors du lot en cours se note dans AUDIT.md, il ne se corrige pas.
- Fin de lot : tests verts, commit `lot N: <résumé>`, lot marqué comme fait dans AUDIT.md, push, puis PR vers `modernisation` avec `gh pr create`.

## Commandes
- Tests : `.venv/bin/python -m pytest -q`
- Application : `docker compose up --build`

## Règles
- Stabilité avant nouveauté : aucune nouvelle dépendance sans me la proposer d'abord.
- Tout changement de comportement ou de format d'index se documente dans le README pour les utilisateurs existants.
- Ne jamais supprimer ni réindexer automatiquement un index existant.
- Toute version de dépendance se vérifie en ligne, jamais de mémoire.
