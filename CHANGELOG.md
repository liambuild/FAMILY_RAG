# Changelog

Toutes les modifications notables de ce projet sont documentées dans ce fichier.

Format basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/),
versionnage selon [Semantic Versioning](https://semver.org/lang/fr/).

---

## [Unreleased]

### Ajouté
- `.gitignore` — exclusion des secrets, caches Python et index vectoriel
- `.dockerignore` — réduction du contexte de build Docker
- `.env.example` — gabarit documenté de toutes les variables d'environnement
- `CHANGELOG.md` — journal des modifications (ce fichier)

### Modifié
- `docker-compose.yml` — binding du port 8000 restreint à `127.0.0.1` (accès local uniquement)
- `docker-compose.yml` — transmet `LLM_MODEL`, `TOP_K` et `TEMPERATURE` au conteneur ; ils étaient jusqu'ici ignorés (F9)
- `app/entrypoint.sh` — `OLLAMA_HOST` est testé en premier, sans doublon (F10)
- `app/rag_engine.py` — un index illisible n'est plus supprimé au chargement : l'erreur est journalisée (S6)
- `app/config.py`, `app/main.py` — `model_config` et `TemplateResponse(request, ...)` (plus d'avertissements de dépréciation)

### Supprimé
- Dépendances inutilisées `python-multipart`, `python-magic`, `aiofiles` et paquets système `libmagic1`, `poppler-utils`
